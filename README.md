# KumoRFM Dashboard

## Description

A browser dashboard for the NVIDIA Kumo Relational foundation model. It builds
a graph from three CSV tables — 200 customers, 60 products, 7,120 transactions
over 2.6 years — and answers four predictive questions against a live NIM
endpoint. No model is trained; only the query changes.

| Task | PQL |
|---|---|
| Churn | `PREDICT COUNT(transactions.*, 0, 90, days)=0 FOR EACH customers.customer_id` |
| Engagement | `PREDICT COUNT(transactions.*, 0, 30, days)>0 FOR EACH customers.customer_id` |
| Spend | `PREDICT SUM(transactions.amount, 0, 30, days) FOR EACH customers.customer_id` |
| Recommend | `PREDICT LIST_DISTINCT(transactions.product_id, 0, 30, days) RANK TOP 5 FOR EACH customers.customer_id` |

`server.py` is a FastAPI bridge: the browser cannot drive the Python client, so
the server builds the graph once at startup and exposes `/predict` and
`/predict_batch`. It contains no scoring logic — every number comes from the
model.

A 65-second walkthrough is in [`media/kumorfm-demo.mp4`](media/kumorfm-demo.mp4).

## Steps to deploy

> **An API key is required.** This demo makes live calls to a Kumo Relational
> NIM endpoint — it ships no model and no cached predictions, so without a key
> and a reachable endpoint nothing will run. No key is included in this repo.
> Get one for the shared NVIDIA endpoint from the `#kumo-usecase-intake` Slack
> channel, or point `KUMO_URL` at a NIM you host yourself.

Requires Python 3.10–3.13, plus that endpoint and key.

```bash
cp .env.example .env     # set KUMO_API_KEY (required) and KUMO_URL
./dashboard.sh           # creates .venv, installs deps, starts the server
```

`dashboard.sh` exits immediately if `KUMO_API_KEY` is empty.

Open <http://localhost:8080/>.

`dashboard.sh` checks `/v1/models` first and refuses to start if the endpoint
advertises a model id other than `kumo-relational`, which is the failure that
otherwise surfaces mid-demo.

Other options:

```bash
./dashboard.sh --port 9000    # if 8080 is taken
python demo.py                # same four tasks on the command line
python generate_data.py       # regenerate the CSVs in data/
```

## How to use the dashboard

Three tabs: **1 · About the demo**, **2 · Data model**, **3 · Demo**. The demo
runs in tab 3.

**Explore** (left) picks the lens — Region/Districts, Category, Product, or
Customer — each with a graph view. **Executive summary** scores every customer
on churn, engagement and spend in one pass and reports averages and value at
risk. **Score all customers** returns the same as a sortable table.

**Metric** (top right of the canvas) switches between Churn, Engagement, Spend
and Recommend; node colour follows the selected metric.

**Anchor time** sets the "as of" date. The model sees only events before it and
predicts the window after — this is what prevents leakage, and predictions
genuinely change when you move it.

Click a customer node, then **Predict with KumoRFM** to score that one entity.
The right-hand panel shows the result and the exact PQL that was sent.
Recommendations highlight products on the graph, with co-purchaser counts on
hover.

Note: hops and depth in the graph visualisation are illustrative. They are not
model parameters and are not sent to the endpoint.
