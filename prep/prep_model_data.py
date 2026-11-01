"""Prepare the E-commerce checkout parquet files for the Power BI model.

Input : the raw parquet files (one row per product line inside a checkout), e.g. 0000.parquet and 0001.parquet.
Output: four lean parquet files in OUT with integer keys and without personal data (name, email):
    fact_line.parquet      one row per product line            (checkout_key, product_key, qty, unit_price, line_amount)
    fact_checkout.parquet  one row per checkout                (checkout_key, customer_key, order_date, lines, units, order_amount, order_no)
    dim_customer.parquet   one row per customer                (customer_key, age, country, lifetime_orders, lifetime_revenue, revenue_rank_pct)
    dim_product.parquet    one row per product                 (product_key, product_name, product_code, list_price)
Why: merging 2.18M rows on GUID strings inside Power Query is slow and memory hungry. Integer keys make the model
smaller and every relationship faster. The script also proves the totals reconcile.

Usage:  python prep_model_data.py <folder with raw parquet files> <output folder>
"""
import sys, glob, json, os
import numpy as np
import pandas as pd

src = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\999429\Desktop\Taj\E-commerce"
out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(src, "data")
os.makedirs(out, exist_ok=True)

files = sorted(glob.glob(os.path.join(src, "*.parquet")))
files = [f for f in files if os.path.basename(f)[:4].isdigit()]          # raw files are named 0000.parquet, 0001.parquet ...
raw = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
print("raw rows", len(raw), "from", [os.path.basename(f) for f in files])

# ---- keys -----------------------------------------------------------------------------------------
raw["date"] = pd.to_datetime(raw["date"]).dt.normalize()
prod_ids = np.sort(raw["product_id"].unique());   prod_key = pd.Series(np.arange(1, len(prod_ids) + 1, dtype="int32"), index=prod_ids)
cust_ids = np.sort(raw["user_id"].unique());      cust_key = pd.Series(np.arange(1, len(cust_ids) + 1, dtype="int32"), index=cust_ids)
co = raw.drop_duplicates("checkout_id")[["checkout_id", "user_id", "date", "n_products_checkout", "total_amount"]]
co = co.sort_values(["date", "checkout_id"]).reset_index(drop=True)
co["checkout_key"] = np.arange(1, len(co) + 1, dtype="int32")
co_key = pd.Series(co["checkout_key"].values, index=co["checkout_id"].values)

# ---- fact_line --------------------------------------------------------------------------------------
fl = pd.DataFrame({
    "checkout_key": raw["checkout_id"].map(co_key).astype("int32"),
    "product_key": raw["product_id"].map(prod_key).astype("int32"),
    "qty": raw["n_items"].astype("int32"),
    "unit_price": raw["product_price"].round(2),
})
fl["line_amount"] = (fl["unit_price"] * fl["qty"]).round(2)
fl = fl.sort_values(["checkout_key", "product_key"]).reset_index(drop=True)

# ---- fact_checkout ----------------------------------------------------------------------------------
agg = fl.groupby("checkout_key").agg(lines=("qty", "size"), units=("qty", "sum"), line_total=("line_amount", "sum"))
fc = co[["checkout_key", "user_id", "date", "n_products_checkout", "total_amount"]].set_index("checkout_key").join(agg).reset_index()
fc["customer_key"] = fc["user_id"].map(cust_key).astype("int32")
assert (fc["lines"] == fc["n_products_checkout"]).all(), "n_products_checkout must equal the number of lines"
diff = (fc["total_amount"] - fc["line_total"]).abs().max()
assert diff < 0.02, f"order total must equal the sum of its lines (max diff {diff})"
fc = fc.sort_values(["customer_key", "date", "checkout_key"])
fc["order_no"] = (fc.groupby("customer_key").cumcount() + 1).astype("int32")      # 1 = the customer's first order
fc = fc.sort_values("checkout_key").reset_index(drop=True)
fact_checkout = pd.DataFrame({
    "checkout_key": fc["checkout_key"], "customer_key": fc["customer_key"], "order_date": fc["date"].dt.date,
    "lines": fc["lines"].astype("int32"), "units": fc["units"].astype("int32"), "order_amount": fc["total_amount"].round(2),
    "order_no": fc["order_no"],
})

# ---- dim_customer (no name, no email) -----------------------------------------------------------------
cu = raw.drop_duplicates("user_id")[["user_id", "age", "country"]].copy()
cu["customer_key"] = cu["user_id"].map(cust_key).astype("int32")
life = fact_checkout.groupby("customer_key").agg(lifetime_orders=("order_no", "max"), lifetime_revenue=("order_amount", "sum"))
cu = cu.set_index("customer_key").join(life).reset_index().sort_values("customer_key").reset_index(drop=True)
order = cu.sort_values(["lifetime_revenue", "customer_key"], ascending=[False, True]).reset_index()
rank_pct = pd.Series((np.arange(len(order)) + 1) / len(order), index=order["customer_key"].values)
dim_customer = pd.DataFrame({
    "customer_key": cu["customer_key"], "age": cu["age"].astype("int32"), "country": cu["country"].str.strip(),
    "lifetime_orders": cu["lifetime_orders"].astype("int32"), "lifetime_revenue": cu["lifetime_revenue"].round(2),
    "revenue_rank_pct": cu["customer_key"].map(rank_pct).round(6),
})

# ---- dim_product ----------------------------------------------------------------------------------------
pr = raw.drop_duplicates("product_id")[["product_id", "product_name", "product_price"]].copy()
pr["product_key"] = pr["product_id"].map(prod_key).astype("int32")
pr = pr.sort_values("product_key").reset_index(drop=True)
dim_product = pd.DataFrame({"product_key": pr["product_key"], "product_name": pr["product_name"].str.strip().str.title(),
                            "product_code": pr["product_id"].str[:8].str.upper(), "list_price": pr["product_price"].round(2)})

# ---- write ---------------------------------------------------------------------------------------------
for name, df in [("fact_line", fl), ("fact_checkout", fact_checkout), ("dim_customer", dim_customer), ("dim_product", dim_product)]:
    p = os.path.join(out, name + ".parquet")
    df.to_parquet(p, index=False, compression="snappy", row_group_size=500_000)
    print(f"{name:14s} {len(df):>10,} rows  {os.path.getsize(p)/1e6:6.1f} MB")

# ---- reconciliation (expected totals to compare with the report after the first refresh) ---------------
f = fact_checkout
tot = dict(
    revenue=round(float(f["order_amount"].sum()), 2), revenue_from_lines=round(float(fl["line_amount"].sum()), 2),
    orders=int(len(f)), customers=int(f["customer_key"].nunique()), units=int(f["units"].sum()), order_lines=int(len(fl)),
    products_sold=int(fl["product_key"].nunique()), countries=int(dim_customer["country"].nunique()),
    avg_order_value=round(float(f["order_amount"].mean()), 2), orders_per_customer=round(len(f) / f["customer_key"].nunique(), 2),
    repeat_customers_pct=round(float((dim_customer["lifetime_orders"] >= 2).mean() * 100), 1),
    returning_orders_pct=round(float((f["order_no"] > 1).mean() * 100), 1),
    first_date=str(f["order_date"].min()), last_date=str(f["order_date"].max()),
)
json.dump(tot, open(os.path.join(out, "expected_totals.json"), "w"), indent=2)
print(json.dumps(tot, indent=2))
