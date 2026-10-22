#!/usr/bin/env python3
"""
Generate the demo dataset. Seeded, so it is byte-identical every run.

Schema (three tables, two foreign keys):

    customers                products
      customer_id (PK)         product_id (PK)
      signup_date              category
      segment                  price
      region                   launch_date
      ...

    transactions
      transaction_id (PK)
      customer_id  -> customers.customer_id   (FK)
      product_id   -> products.product_id     (FK)
      transaction_date
      amount, quantity

Why this shape:
  * product_id as a foreign key is what makes RANK TOP link prediction
    (recommendations) possible - KumoRFM rejects LIST_DISTINCT on a plain
    string column.
  * ~2.5 years of history so 90-day aggregation windows have data behind
    the anchor instead of warning about a truncated context.

Usage:  python generate_data.py [--out data]
"""

import argparse
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 20240201
START = date(2021, 7, 1)
END = date(2024, 1, 31)

N_CUSTOMERS = 200
N_PRODUCTS = 60

CATEGORIES = {
    "Electronics": (80, 900),
    "Home":        (25, 300),
    "Clothing":    (20, 180),
    "Sports":      (30, 400),
    "Books":       (10,  60),
}
REGIONS = ["North", "South", "East", "West"]
SEGMENTS = ["Enterprise", "SMB", "Consumer"]

# Each district has an owning account manager. Districts are region-aligned so
# rollups have structure to find (risk is rarely spread evenly across districts).
DISTRICTS = [
    ("North Enterprise", "Dana Whitfield", "North"),
    ("North Mid-Market", "Marcus Reyes",   "North"),
    ("South Growth",     "Priya Raman",    "South"),
    ("South Retail",     "Tom Okafor",     "South"),
    ("East Strategic",   "Lena Fischer",   "East"),
    ("East Volume",      "Yuki Tanaka",    "East"),
    ("West Enterprise",  "Sofia Marino",   "West"),
    ("West Emerging",    "Andre Dubois",   "West"),
]

FIRST = ["Alice","Bob","Carol","David","Eve","Frank","Grace","Henry","Iris","Jack",
         "Karen","Leo","Mia","Noah","Olivia","Paul","Quinn","Rachel","Samuel","Tanya",
         "Uma","Vincent","Wendy","Xavier","Yasmine","Zoe","Aaron","Bella","Caleb","Diana"]
LAST = ["Johnson","Smith","Davis","Wilson","Martinez","Thompson","Lee","Brown","White",
        "Robinson","Garcia","Anderson","Taylor","Jackson","Martin","Harris","Moore",
        "Jones","Clark","Lewis","Young","Patel","Miller","Walker","Hall"]


def daterange_days():
    return (END - START).days


def main(out_dir: Path):
    rng = random.Random(SEED)
    out_dir.mkdir(parents=True, exist_ok=True)
    span = daterange_days()

    # ---------------------------------------------------------------- products
    products = []
    cat_list = list(CATEGORIES)
    for i in range(1, N_PRODUCTS + 1):
        cat = cat_list[(i - 1) % len(cat_list)]
        lo, hi = CATEGORIES[cat]
        price = round(rng.uniform(lo, hi), 2)
        launch = START + timedelta(days=rng.randint(0, int(span * 0.3)))
        products.append({
            "product_id": f"P{i:03d}",
            "product_name": f"{cat} Item {i:03d}",
            "category": cat,
            "price": price,
            "launch_date": launch.isoformat(),
        })

    by_cat = {}
    for p in products:
        by_cat.setdefault(p["category"], []).append(p)

    # ---------------------------------------------------------------- customers
    customers = []
    for i in range(1, N_CUSTOMERS + 1):
        # signup spread across the first ~70% of the window so everyone has history
        signup = START + timedelta(days=rng.randint(0, int(span * 0.7)))
        segment = rng.choice(SEGMENTS)
        region = rng.choice(REGIONS)
        # assign to a portfolio in the customer's region
        books = [d for d in DISTRICTS if d[2] == region]
        district, manager, _ = rng.choice(books)

        # churners stop buying partway through; retained customers stay active
        # districts differ in health - that is what a manager rollup should reveal
        book_risk = {"North Enterprise": .18, "North Mid-Market": .30,
                     "South Growth": .26, "South Retail": .44,
                     "East Strategic": .16, "East Volume": .38,
                     "West Enterprise": .21, "West Emerging": .47}
        churned = rng.random() < book_risk.get(district, .32)
        # each customer prefers 1-2 categories -> gives the graph real structure
        prefs = rng.sample(cat_list, rng.choice([1, 2, 2, 3]))

        base_freq = {"Enterprise": 14, "SMB": 21, "Consumer": 30}[segment]
        freq_days = max(6, int(rng.gauss(base_freq, base_freq * 0.3)))

        customers.append({
            "customer_id": f"C{i:03d}",
            "name": f"{rng.choice(FIRST)} {rng.choice(LAST)}",
            "signup_date": signup.isoformat(),
            "segment": segment,
            "region": region,
            "district": district,
            "manager": manager,
            "_churned": churned,
            "_prefs": prefs,
            "_freq": freq_days,
            "_signup": signup,
        })

    # ---------------------------------------------------------------- transactions
    transactions = []
    tid = 1
    for c in customers:
        signup = c["_signup"]
        # churners go quiet somewhere in the last third of the window
        if c["_churned"]:
            stop = END - timedelta(days=rng.randint(40, 260))
            if stop <= signup:
                stop = signup + timedelta(days=30)
        else:
            stop = END

        day = signup + timedelta(days=rng.randint(0, 20))
        while day < stop:
            cat = rng.choice(c["_prefs"])
            prod = rng.choice(by_cat[cat])
            qty = rng.choice([1, 1, 1, 2, 2, 3])
            jitter = rng.uniform(0.85, 1.25)
            amount = round(prod["price"] * qty * jitter, 2)
            transactions.append({
                "transaction_id": f"T{tid:05d}",
                "customer_id": c["customer_id"],
                "product_id": prod["product_id"],
                "transaction_date": day.isoformat(),
                "amount": amount,
                "quantity": qty,
            })
            tid += 1
            gap = max(2, int(rng.gauss(c["_freq"], c["_freq"] * 0.45)))
            day = day + timedelta(days=gap)

    transactions.sort(key=lambda t: t["transaction_date"])

    # ---------------------------------------------------------------- write
    import csv

    for c in customers:
        for k in ("_churned", "_prefs", "_freq", "_signup"):
            c.pop(k)

    def write(name, rows, fields):
        path = out_dir / name
        with path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        print(f"  {name:20} {len(rows):>6} rows")

    print(f"Writing to {out_dir}/")
    write("customers.csv", customers,
          ["customer_id", "name", "signup_date", "segment", "region",
           "district", "manager"])
    write("products.csv", products,
          ["product_id", "product_name", "category", "price", "launch_date"])
    write("transactions.csv", transactions,
          ["transaction_id", "customer_id", "product_id",
           "transaction_date", "amount", "quantity"])

    # ---------------------------------------------------------------- summary
    dates = [t["transaction_date"] for t in transactions]
    per_cust = {}
    for t in transactions:
        per_cust[t["customer_id"]] = per_cust.get(t["customer_id"], 0) + 1
    last_seen = {}
    for t in transactions:
        last_seen[t["customer_id"]] = max(last_seen.get(t["customer_id"], ""),
                                          t["transaction_date"])
    quiet = sum(1 for d in last_seen.values()
                if (END - date.fromisoformat(d)).days > 90)

    print()
    print(f"  date range        {min(dates)} -> {max(dates)}")
    print(f"  tx per customer   min {min(per_cust.values())}  "
          f"avg {sum(per_cust.values())/len(per_cust):.1f}  max {max(per_cust.values())}")
    print(f"  quiet >90d        {quiet}/{len(customers)} customers "
          f"({quiet/len(customers)*100:.0f}%)  <- the churn signal")
    print(f"  history before END  {(END - START).days} days")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data")
    a = ap.parse_args()
    main(Path(a.out))
