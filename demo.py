#!/usr/bin/env python3
"""
KumoRFM demo — four predictive tasks on one relational graph, no training.

Every number printed comes from the KumoRFM foundation model. This script only
builds the graph, sends PQL, and displays what came back.

    export KUMORFM_URL=https://rfm-nim.dev.kumoai.cloud
    export KUMORFM_API_KEY=...
    python demo.py                 # all tasks
    python demo.py --task churn    # one task
    python demo.py --entity C042   # a specific customer
"""

from __future__ import annotations

import argparse
import os
import sys
import warnings

import pandas as pd

warnings.filterwarnings("ignore", message=".*Context anchor timestamp.*")

URL = os.environ.get("KUMORFM_URL", "https://rfm-nim.dev.kumoai.cloud")
KEY = os.environ.get("KUMORFM_API_KEY") or None


def head(title: str) -> None:
    print(f"\n\033[1m{'─' * 72}\n{title}\n{'─' * 72}\033[0m")


def sub(title: str) -> None:
    print(f"\n\033[1m▸ {title}\033[0m")


# --------------------------------------------------------------------- tasks
TASKS = {
    "churn": {
        "title": "Churn — will this customer go quiet for 90 days?",
        "query": "PREDICT COUNT(transactions.*, 0, 90, days)=0 "
                 "FOR EACH customers.customer_id",
        "reads": "TRUE_PROB is the probability of NO purchases in the next 90 days.",
    },
    "active": {
        "title": "Engagement — will this customer buy in the next 30 days?",
        "query": "PREDICT COUNT(transactions.*, 0, 30, days)>0 "
                 "FOR EACH customers.customer_id",
        "reads": "TRUE_PROB is the probability of at least one purchase.",
    },
    "spend": {
        "title": "Forecast — how much will this customer spend in 30 days?",
        "query": "PREDICT SUM(transactions.amount, 0, 30, days) "
                 "FOR EACH customers.customer_id",
        "reads": "PREDICTION is the expected spend in dollars.",
    },
    "recommend": {
        "title": "Recommendation — which products come next?",
        # LIST_DISTINCT must target a FOREIGN KEY column (product_id), not a
        # plain string; that is what makes this a link-prediction task.
        "query": "PREDICT LIST_DISTINCT(transactions.product_id, 0, 30, days) "
                 "RANK TOP 5 FOR EACH customers.customer_id",
        "reads": "Each row is a candidate product with its score.",
    },
}


def load(data_dir: str):
    import pathlib
    d = pathlib.Path(data_dir)
    missing = [f for f in ("customers.csv", "products.csv", "transactions.csv")
               if not (d / f).exists()]
    if missing:
        print(f"Missing in {d}/: {', '.join(missing)}")
        print("Run:  python generate_data.py")
        sys.exit(1)

    customers = pd.read_csv(d / "customers.csv", parse_dates=["signup_date"])
    products = pd.read_csv(d / "products.csv", parse_dates=["launch_date"])
    transactions = pd.read_csv(d / "transactions.csv", parse_dates=["transaction_date"])
    return customers, products, transactions


def build_graph(kumorfm, customers, products, transactions):
    graph = kumorfm.Graph.from_data({
        "customers": customers,
        "products": products,
        "transactions": transactions,
    })
    graph["customers"].primary_key = "customer_id"
    graph["products"].primary_key = "product_id"
    graph["transactions"].primary_key = "transaction_id"
    graph["transactions"].time_column = "transaction_date"
    graph.validate()
    return graph


def context_for(entity, customers, transactions, anchor=None):
    """Facts from the raw data, so results can be sanity-checked."""
    row = customers[customers.customer_id == entity]
    if row.empty:
        return None
    row = row.iloc[0]
    tx = transactions[transactions.customer_id == entity]
    if anchor is not None:
        tx = tx[tx.transaction_date <= anchor]
    if tx.empty:
        return f"{row['name']} · {row['segment']} · no purchases before anchor"
    last = tx.transaction_date.max()
    ref = anchor if anchor is not None else transactions.transaction_date.max()
    return (f"{row['name']} · {row['segment']} · {row['region']} · "
            f"{len(tx)} purchases · last {(ref - last).days}d before anchor · "
            f"${tx.amount.sum():,.0f} lifetime")


def run_task(model, key, entity, anchor, products):
    spec = TASKS[key]
    sub(spec["title"])
    print(f"  PQL: {spec['query']}")
    if anchor is not None:
        print(f"  anchor_time: {anchor.date()}")

    kwargs = {"indices": [entity], "run_mode": "fast"}
    if anchor is not None:
        kwargs["anchor_time"] = anchor

    try:
        df = model.predict(spec["query"], **kwargs)
    except Exception as exc:
        print(f"  FAILED: {type(exc).__name__}: {exc}")
        return False

    # join product names onto recommendations so output is readable
    if key == "recommend" and "CLASS" in df.columns:
        names = products.set_index("product_id")[["product_name", "category"]]
        df = df.join(names, on="CLASS")

    print()
    for line in df.to_string(index=False).splitlines():
        print("   " + line)
    print(f"\n  \033[2m{spec['reads']}\033[0m")
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entity", default=None, help="customer_id (default: an active one)")
    ap.add_argument("--task", default=None, choices=list(TASKS), help="run one task")
    ap.add_argument("--anchor", default=None, help="anchor date YYYY-MM-DD")
    ap.add_argument("--data", default="data")
    args = ap.parse_args()

    head("1 · Connect")
    try:
        from nvidia_sdfm import SDFMClient, kumorfm
        import nvidia_sdfm
    except ImportError as exc:
        print(f"  SDK not installed: {exc}\n")
        print("  pip install --index-url "
              "https://urm.nvidia.com/artifactory/api/pypi/nv-shared-pypi/simple \\")
        print('    "nvidia-sdfm[kumorfm]==0.2.1" "kumorfm==2.28.0"')
        print("\n  (needs VPN; on Apple Silicon run inside a linux/amd64 container)")
        sys.exit(1)

    print(f"  nvidia_sdfm {getattr(nvidia_sdfm, '__version__', '?')}")
    print(f"  endpoint    {URL}")
    print(f"  api key     {'set (%d chars)' % len(KEY) if KEY else 'NOT SET'}")
    client = SDFMClient(URL, KEY) if KEY else SDFMClient(URL)
    print(f"  ready       {client.health_ready()}")
    print(f"  models      {client.models()}")

    head("2 · Data")
    customers, products, transactions = load(args.data)
    print(f"  customers    {len(customers):>6}")
    print(f"  products     {len(products):>6}")
    print(f"  transactions {len(transactions):>6}   "
          f"{transactions.transaction_date.min().date()} → "
          f"{transactions.transaction_date.max().date()}")
    print("  links        transactions.customer_id → customers.customer_id")
    print("               transactions.product_id  → products.product_id")

    head("3 · Graph")
    graph = build_graph(kumorfm, customers, products, transactions)
    model = client.kumorfm(graph)

    # pick a demo entity: someone with recent activity, so results are meaningful
    entity = args.entity
    if entity is None:
        recent = transactions[
            transactions.transaction_date >
            transactions.transaction_date.max() - pd.Timedelta(days=30)
        ]
        counts = recent.customer_id.value_counts()
        entity = counts.index[0] if len(counts) else customers.customer_id.iloc[0]

    anchor = pd.Timestamp(args.anchor) if args.anchor else None

    head(f"4 · Predictions for {entity}")
    ctx = context_for(entity, customers, transactions, anchor)
    if ctx:
        print(f"  \033[2m{ctx}\033[0m")

    keys = [args.task] if args.task else list(TASKS)
    ok = sum(run_task(model, k, entity, anchor, products) for k in keys)

    head("Summary")
    print(f"  {ok}/{len(keys)} tasks returned predictions from KumoRFM")
    print("  One graph, one model, no training — only the query changed.\n")

    try:
        client.close()
    except Exception:
        pass


if __name__ == "__main__":
    main()
