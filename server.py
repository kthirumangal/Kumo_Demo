"""
Dashboard server: serves the UI and relays predictions from KumoRFM.

    browser  ->  POST /predict  ->  this server  ->  nvidia_sdfm  ->  KumoRFM

The graph is built and bound once at startup. This file contains NO scoring
logic: every number it returns came from the model.
"""

from __future__ import annotations

import inspect
import os
import warnings
from pathlib import Path

import pandas as pd
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

# Migrated 2026-10-20: nvidia-sdfm / kumorfm -> kumo-relational-client
# (model id `kumo-relational`). Original in legacy/server_kumorfm.py.
from kumo_relational_client import RelationalClient, relational

warnings.filterwarnings("ignore", message=".*anchor.*timestamp.*")

HERE = Path(__file__).parent.resolve()
DATA = Path(os.environ.get("KUMO_DATA_DIR", HERE / "data"))
URL = (os.environ.get("KUMO_URL")
       or os.environ.get("KUMORFM_URL", "https://rfm-nim.dev.kumoai.cloud"))
KEY = (os.environ.get("KUMO_API_KEY")
       or os.environ.get("KUMORFM_API_KEY") or None)
PORT = int(os.environ.get("KUMO_PORT", "8080"))
BIND = os.environ.get("KUMO_BIND", "0.0.0.0")
RUN_MODE = os.environ.get("KUMO_RUN_MODE", "fast")

app = FastAPI(title="KumoRFM dashboard")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

S: dict = {"model": None, "products": None, "customers": None, "error": None}

# PQL per task. {H} is the horizon in days, {K} the top-N for ranking.
TASKS = {
    "churn":     "PREDICT COUNT(transactions.*, 0, {H}, days)=0 FOR EACH customers.customer_id",
    "engage":    "PREDICT COUNT(transactions.*, 0, {H}, days)>0 FOR EACH customers.customer_id",
    "spend":     "PREDICT SUM(transactions.amount, 0, {H}, days) FOR EACH customers.customer_id",
    "recommend": "PREDICT LIST_DISTINCT(transactions.product_id, 0, {H}, days) "
                 "RANK TOP {K} FOR EACH customers.customer_id",
}
DEFAULT_H = {"churn": 90, "engage": 30, "spend": 30, "recommend": 30}


def startup() -> None:
    customers = pd.read_csv(DATA / "customers.csv", parse_dates=["signup_date"])
    products = pd.read_csv(DATA / "products.csv", parse_dates=["launch_date"])
    transactions = pd.read_csv(DATA / "transactions.csv", parse_dates=["transaction_date"])
    S["products"] = products.set_index("product_id")
    S["customers"] = customers
    print(f"[data] {len(customers)} customers, {len(products)} products, "
          f"{len(transactions)} transactions")

    graph = relational.Graph.from_data({
        "customers": customers, "products": products, "transactions": transactions,
    })
    graph["customers"].primary_key = "customer_id"
    graph["products"].primary_key = "product_id"
    graph["transactions"].primary_key = "transaction_id"
    graph["transactions"].time_column = "transaction_date"
    try:
        graph.validate()
    except AttributeError:
        pass

    client = RelationalClient(url=URL, api_key=KEY) if KEY else RelationalClient(url=URL)
    print(f"[api ] {URL} ready={client.health_ready()} models={client.models()}")
    S["model"] = client.relational(graph)
    print("[api ] graph bound; ready for predictions")


def call_predict(query: str, kw: dict):
    """Send only the kwargs this client version accepts, so a renamed or
    dropped kwarg degrades one control instead of failing the request."""
    model = S["model"]
    try:
        params = inspect.signature(model.predict).parameters
        if not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
            kw = {k: v for k, v in kw.items() if k in params}
    except (TypeError, ValueError):
        pass
    return model.predict(query, **kw)


class BatchReq(BaseModel):
    task: str = "churn"
    entities: list[str] | None = None      # None = every customer
    horizon: int | None = None
    anchor: str | None = None


class Req(BaseModel):
    task: str = "churn"
    entity: str
    horizon: int | None = None
    anchor: str | None = None
    top_k: int = 5


@app.get("/health")
def health():
    if S["error"]:
        return JSONResponse({"ok": False, "error": S["error"]}, status_code=503)
    return {"ok": True, "endpoint": URL, "bound": S["model"] is not None}


@app.post("/predict")
def predict(r: Req):
    if S["model"] is None:
        return JSONResponse({"ok": False, "error": S["error"] or "not initialized"},
                            status_code=503)
    if r.task not in TASKS:
        return JSONResponse({"ok": False, "error": f"unknown task {r.task}"},
                            status_code=400)

    horizon = r.horizon or DEFAULT_H[r.task]
    query = TASKS[r.task].format(H=horizon, K=r.top_k)

    kw = {"indices": [r.entity], "run_mode": RUN_MODE}
    if r.anchor:
        try:
            kw["anchor_time"] = pd.Timestamp(r.anchor)
        except Exception:
            pass

    try:
        df = call_predict(query, kw)
    except Exception as e:
        return JSONResponse(
            {"ok": False, "query": query, "error": f"{type(e).__name__}: {e}"},
            status_code=500)

    out = {"ok": True, "task": r.task, "query": query, "horizon": horizon,
           "anchor": str(kw["anchor_time"].date()) if "anchor_time" in kw else None,
           "columns": [str(c) for c in df.columns]}

    if r.task == "recommend":
        items = []
        for _, row in df.iterrows():
            pid = str(row.get("CLASS", ""))
            meta = S["products"].loc[pid] if pid in S["products"].index else None
            items.append({
                "id": pid,
                "name": str(meta["product_name"]) if meta is not None else pid,
                "category": str(meta["category"]) if meta is not None else "",
                "score": float(row["SCORE"]) if "SCORE" in df.columns else None,
            })
        out["kind"] = "ranked"
        out["items"] = items
    elif r.task == "spend":
        out["kind"] = "number"
        out["value"] = float(df["PREDICTION"].iloc[0])
    else:
        # classification: TRUE_PROB is the positive class. Never surface
        # FALSE_PROB as the answer - that silently inverts it.
        col = next((c for c in df.columns if str(c).upper() == "TRUE_PROB"), None)
        if col is None:
            col = next((c for c in df.columns if "TRUE" in str(c).upper()), None)
        out["kind"] = "probability"
        out["value"] = float(df[col].iloc[0]) if col is not None else None
        out["column"] = str(col) if col is not None else None
        if "PREDICTION" in df.columns:
            out["label"] = str(df["PREDICTION"].iloc[0])

    out["table"] = df.astype(str).to_dict(orient="records")
    return out


@app.post("/predict_batch")
def predict_batch(r: BatchReq):
    """Score many entities in ONE call - this is how these models get used in
    practice: whole book at once, then rank."""
    if S["model"] is None:
        return JSONResponse({"ok": False, "error": S["error"] or "not initialized"},
                            status_code=503)
    if r.task not in ("churn", "engage", "spend"):
        return JSONResponse({"ok": False, "error": "batch supports churn|engage|spend"},
                            status_code=400)

    ents = r.entities or S["customers"]["customer_id"].astype(str).tolist()
    horizon = r.horizon or DEFAULT_H[r.task]
    query = TASKS[r.task].format(H=horizon, K=5)

    kw = {"indices": ents, "run_mode": RUN_MODE}
    if r.anchor:
        try:
            kw["anchor_time"] = pd.Timestamp(r.anchor)
        except Exception:
            pass

    import time
    t0 = time.time()
    try:
        df = call_predict(query, kw)
    except Exception as e:
        return JSONResponse(
            {"ok": False, "query": query, "error": f"{type(e).__name__}: {e}"},
            status_code=500)
    elapsed = round(time.time() - t0, 1)

    ent_col = next((c for c in df.columns if str(c).upper() == "ENTITY"), df.columns[0])
    if r.task == "spend":
        val_col = next((c for c in df.columns if str(c).upper() == "PREDICTION"), None)
    else:
        val_col = next((c for c in df.columns if str(c).upper() == "TRUE_PROB"), None)

    rows = []
    if val_col is not None:
        for _, row in df.iterrows():
            try:
                rows.append({"entity": str(row[ent_col]), "value": float(row[val_col])})
            except Exception:
                pass

    return {"ok": True, "task": r.task, "query": query, "horizon": horizon,
            "anchor": str(kw["anchor_time"].date()) if "anchor_time" in kw else None,
            "n": len(rows), "seconds": elapsed, "column": str(val_col),
            "results": rows}


@app.get("/")
def index():
    f = HERE / "dashboard.html"
    return FileResponse(f) if f.exists() else {"ok": True, "msg": "dashboard.html missing"}


if __name__ == "__main__":
    try:
        startup()
    except Exception as e:
        S["error"] = f"{type(e).__name__}: {e}"
        print(f"\n[FATAL] {S['error']}")
        print(f"  endpoint : {URL}")
        print(f"  api key  : {'set' if KEY else 'NOT SET'}")
        print(f"  data dir : {DATA}")
        print("  starting anyway so /health reports it\n")
    print(f"\n  Dashboard: http://localhost:{PORT}/\n")
    uvicorn.run(app, host=BIND, port=PORT, log_level="warning")
