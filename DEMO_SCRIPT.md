# Demo script

Full walkthrough: navigation, all four prediction tasks, anchor time.
Target runtime **3:00–3:30** after trimming. Raw capture runs longer because
of model latency — see Prep and the wait column.

## Prep

Latency is the only thing that can wreck this recording.

| Task | Time per call |
|---|---|
| Churn / Engagement / Spend (one customer) | ~5 s |
| Executive summary (200 customers × 3 metrics) | 3 queries, ~15–25 s |
| **Recommendations (one customer)** | **~66 s** |

Before recording:

1. `./dashboard.sh`, open <http://localhost:8080>, go to tab **3 · Demo**.
2. Click **Executive summary** and let all three metrics complete. Results are
   cached per metric, so it redraws instantly on camera.
3. Run one **Recommend** prediction on C166 and discard it. This is the 66 s
   call — do it now, not on camera.
4. Reload, return to tab 3. Everything below is then fast or already warm.

Record in one take and trim the spinners in the edit. Clicks are the beats.

---

## 1 · Framing (0:00–0:25)

| Time | On screen | Say |
|---|---|---|
| 0:00 | Tab **1 · About the demo** | "A relational foundation model, queried live." |
| 0:10 | Scroll the tab briefly | "No training run. No feature engineering. One graph, many questions." |
| 0:18 | Tab **2 · Data model** | "Three ordinary tables: customers, products, transactions." |

## 2 · The data (0:25–0:50)

| Time | On screen | Say |
|---|---|---|
| 0:25 | Data model tab — keys and foreign keys | "Primary keys become entities. Foreign keys become edges. Timestamps make it temporal." |
| 0:40 | Tab **3 · Demo**, header stats | "200 customers, 60 products, 7,120 transactions, 2.6 years of history." |

## 3 · Navigation (0:50–1:20)

Show that the same graph is viewable through four lenses.

| Time | On screen | Say |
|---|---|---|
| 0:50 | Explore → **1 · Region / Districts → Graph view** | "Eight districts. This is the whole book of business." |
| 1:00 | → **2 · Category → Graph view** | "Same data, grouped by what people buy." |
| 1:08 | → **3 · Product → Graph view** | "Or by product." |
| 1:14 | → **4 · Customer → Neighbors** | "Or down to one customer and who sits next to them in the graph." |

## 4 · Executive summary (1:20–1:50)

| Time | On screen | Say |
|---|---|---|
| 1:20 | Explore → **Executive summary** (cached, instant) | "Score every customer in one pass — churn, engagement and spend." |
| 1:32 | Point at **Avg churn** and **Value at risk** | "Average churn risk, and the money actually at stake behind it." |
| 1:42 | Explore → **Score all customers** (table) | "Same numbers as a ranked table, which is how you'd actually use it." |

## 5 · Churn (1:50–2:15)

| Time | On screen | Say |
|---|---|---|
| 1:50 | Metric → **Churn**. Graph recolours | "Red is risk." |
| 1:56 | Click **C166 — Olivia Young**. Hover shows $37,639 lifetime | "Enterprise account, East Strategic district." |
| 2:03 | **Predict with KumoRFM** → result + PQL panel | "Six percent chance she goes quiet for 90 days. She bought five days ago — the model agrees with the data." |
| 2:10 | Point at the PQL in the right panel | "And that's the exact query sent to the model." |

## 6 · Engagement (2:15–2:35)

| Time | On screen | Say |
|---|---|---|
| 2:15 | Metric → **Engagement**. Graph recolours | "Change one line of the query." |
| 2:22 | Predict on the same customer → ~99% | "Ninety-nine percent chance she buys in the next 30 days." |
| 2:30 | — | "Same graph. Same model. No retraining between those two answers." |

## 7 · Spend and recommendations (2:35–3:00)

| Time | On screen | Say |
|---|---|---|
| 2:35 | Metric → **Spend**, predict | "Expected spend next month — a regression, from the same graph." |
| 2:45 | Metric → **Recommend** (use the warm result) | "And the top five products she's likely to buy." |
| 2:52 | Hover a highlighted product node | "Highlighted on the graph, with how many of her co-purchasers bought each one." |

> If the recommendation call is cold, cut away here. 66 seconds of spinner will
> lose the room.

## 8 · Anchor time, and the close (3:00–3:25)

| Time | On screen | Say |
|---|---|---|
| 3:00 | Drag **anchor time** back to mid-2023. Numbers change | "Move the anchor and the model only sees events before that date." |
| 3:10 | Predictions update | "Future rows define the labels, never the features. That's what keeps it honest." |
| 3:18 | Hold on the full ecosystem view | "One graph, four questions, no training. That's the whole idea." |

---

## Notes

- Hops and depth in the graph visual are illustrative — they are not sent to
  the model. Don't claim otherwise on camera.
- Exact numbers shift between runs: the model samples 1,000 in-context
  examples per call. Narrate the shape of the answer, not the decimals.
- If `localhost:8080` shows an unexpected UI, an older server is still bound to
  the port: `lsof -ti:8080 | xargs kill`, then relaunch.
