# E-commerce Order Ledger — Power BI Dashboard

An interactive Power BI report on **395,856 e-commerce orders** placed by **98,068 customers** between **1 Jan 2020 and 10 Mar 2022**. Every chart on the report is an HTML visual driven by DAX, so the layout, animation and tooltips are fully custom while still reacting to the model's filters.

## The idea and the business question

An order ledger holds a lot of numbers, but a manager usually wants three answers fast:

> **How is revenue developing, where does it come from, and are customers coming back?**

The report is built around that question:

1. **Sales & Markets** — how much revenue, in which months, and from which countries?
2. **Customers & Basket** — who buys (age, loyalty, value tier), how big is a basket, and which price bands carry the revenue?
3. A built-in **reconciliation check** proves that revenue from order totals equals revenue from order lines, so the numbers can be trusted.

## Pages

| Page | What it answers | Main content |
|---|---|---|
| **Intro** | What is in this data, and do the totals reconcile? | Headline (orders, customers, countries), date range, revenue-match stamp, entry buttons to the other pages |
| **Sales & Markets** | How much, when and where? | KPI strip, written insights, monthly revenue, month heat map, top countries, filter drawer |
| **Customers & Basket** | Who buys, how loyal are they, what do they put in the basket? | KPI strip, basket value, repeat-purchase ladder, loyalty tiers, age bands, price bands, filter drawer |

The file also keeps three earlier hidden pages (an alternative cream-coloured "receipt ledger" design of the same three pages). They are not part of the navigation.

## Key findings

All figures below were computed from the parquet files in `data/` (the same tables the model loads). Currency is not specified in the source, so amounts are shown as plain currency units.

**Scale and reconciliation**

| Measure | Value |
|---|---|
| Revenue | 2,745,448,362.77 (2.75B) |
| Orders | 395,856 |
| Customers | 98,068 |
| Units sold | 10,890,702 |
| Order lines | 2,178,515 |
| Products sold | 40,000 |
| Average order value | 6,935 |
| Orders per customer | 4.04 |
| Revenue from order totals vs. from order lines | identical (2,745,448,362.77) |

**Revenue over time**
- 2020 revenue was 1.283B and 2021 was 1.248B (**−2.7%**). 2022 covers only 1 Jan to 10 Mar.
- Over the same window (1 Jan to 10 Mar), revenue went 238.8M (2020), 237.8M (2021), 214.0M (2022): **−10.0% in 2022 vs 2021**.
- The average complete month brings in about 104.1M. The strongest month is July 2020 (121.6M) and the weakest complete month is March 2021 (80.2M).
- Seasonality over 2020–2021: July and August are the strongest months (9.3% and 9.4% of revenue), April the weakest (6.7%).

**Customers**
- **92.3%** of customers placed two or more orders; only 7.7% bought once.
- Customers with 6 or more orders are 21.3% of customers but bring **36.5% of revenue**.
- The top 10% of customers by lifetime revenue generate **21.5%** of revenue; the next 40% generate 51.1%; the bottom 50% generate 27.4%.
- The share of returning orders climbs from 19.7% (Q1 2020) to 97.7% (Q1 2022). This is partly a window effect, because the data starts in January 2020 and every customer's first order inside the window counts as "first".
- Order value does not differ by age: the average order is between 6,930 and 6,947 in every age band. The 55–65 band brings the largest revenue share (23.0%) and 18–24 the smallest (14.4%).

**Basket and products**
- Orders are spread almost evenly over 1 to 10 products (about 10% each). Average order value rises roughly **1,260 per extra product** (1,259 for one product, 12,638 for ten), so basket size, not item price, drives order value. The average basket is 5.5 products and 27.5 units.
- The 400–500 price band carries **35.8%** of revenue while selling about the same number of units as the other bands; the 0–99 band carries 4.1%.
- Revenue is not concentrated: the top 10% of products bring 20.3% of revenue, and the top 10 of 243 countries/territories together bring only 5.3%.

> **Note on the data:** distributions are very even (basket sizes, ages, countries), and the model notes call the country names synthetic. Treat the findings as a demonstration of the analysis and the report, not as a real business case.

## Features

- Three-page report with a custom navigation bar and page-navigation buttons.
- **Filter drawer** on both analysis pages (Year, Age Band, Customer Type, Country/Territory, Country), opened and closed with bookmarks. Filters persist across pages and have Reset / Apply controls.
- KPI strip where every value is compared with the unfiltered portfolio.
- Written insight cards that update with the filters.
- Month heat map, monthly revenue chart, top-country bars, basket-value curve, repeat-purchase ladder, loyalty / age / price-band charts.
- An **i** icon on each chart with a tooltip that explains what it shows and how to read it.
- Friendly empty state when the filters match no orders.
- Reconciliation stamp on the Intro page (order totals vs. order lines).

## How it is built

**Data preparation (Python).** `prep/prep_model_data.py` turns the raw checkout export (one row per product line) into four lean parquet files. It replaces GUIDs with integer keys, drops customer names and emails, and asserts that every order total equals the sum of its lines and that the line count matches. It writes `expected_totals.json` for the post-refresh check.

**Star schema.** Two fact tables and three dimensions, all single-direction, many-to-one:

| Table | Grain | Rows |
|---|---|---|
| `Checkout` (fact) | one row per order | 395,856 |
| `Order Line` (fact) | one row per product on an order | 2,178,515 |
| `Customer` (dimension) | one row per customer | 98,068 |
| `Product` (dimension) | one row per product | 40,000 |
| `Date` (dimension) | one row per day, built in Power Query | Jan 2020 – Mar 2022 |

Relationships: `Order Line → Checkout`, `Order Line → Product`, `Checkout → Customer`, `Checkout → Date`. Headline measures read only the 396K-row `Checkout` table; only product-level measures read `Order Line`.

**Power Query (M).** One text parameter, `Data Folder Path`, points to the folder with the parquet files. Each query reads a parquet file, renames columns and sets types, then adds the business columns: age band, loyalty tier, value tier (top 10% / next 40% / bottom 50% by lifetime revenue), country-vs-territory flag, price band, and first-order-vs-returning. The `Date` table is generated in M from the first to the last order month, with a flag for the partial last month.

**DAX.** A `Key Measures` table (17 measures: Revenue, Orders, Customers, Units Sold, Avg Order Value, Repeat Customer %, Returning Order %, Top 10% Customers Share, and others) and an `HTML Visuals` table (39 measures) that build the HTML for each visual. Revenue is taken from the order total, never from the repeated line field, and the partial last month is excluded from the monthly average.

**HTML-content visuals.** Each chart is a DAX measure that returns an HTML + CSS string (inline SVG and CSS animation included), rendered by the **HTML Content** custom visual. This gives full control over layout and styling while keeping everything connected to slicers and filters.

**Bookmarks.** Four bookmarks open and close the filter drawer on each analysis page.

## Run it

1. Clone the repo or download the files.
2. Open `Ecommerce.pbix` in **Power BI Desktop**. The HTML Content visual is embedded in the file; if Desktop asks, allow or install **HTML Content** from AppSource.
3. Go to **Home → Transform data → Edit parameters** and set **Data Folder Path** to the full path of the `data` folder on your machine (for example `C:\path\to\Ecommerce\data`). Click **Close & Apply**.
4. **Refresh.** The first load reads about 2.2M rows and can take a minute or two.
5. Check the Intro page against the expected totals:

| Measure | Expected |
|---|---|
| Revenue | 2,745,448,362.77 (2.75B) |
| Orders | 395,856 |
| Customers | 98,068 |
| Units sold | 10,890,702 |
| Order lines | 2,178,515 |
| Products | 40,000 |
| Average order value | 6,935 |
| Orders per customer | 4.04 |
| Repeat customers | 92.3% |
| First / last order date | 2020-01-01 / 2022-03-10 |

The same numbers are in `data/expected_totals.json`. The Intro page prints a "Totals match" stamp when revenue from order totals equals revenue from order lines.

**Rebuilding `data/` (optional).** The raw export (`0000.parquet`, `0001.parquet`) is not in this repo because it contains customer names and emails. If you have it:

```bash
pip install pandas pyarrow
python prep/prep_model_data.py <folder with raw parquet files> <output folder>
```

## Project structure

```
Ecommerce/
├── Ecommerce.pbix               # the Power BI report and model
├── data/
│   ├── fact_checkout.parquet    # one row per order
│   ├── fact_line.parquet        # one row per product line
│   ├── dim_customer.parquet     # customers (no names or emails)
│   ├── dim_product.parquet      # products
│   └── expected_totals.json     # numbers to compare after refresh
├── prep/
│   └── prep_model_data.py       # raw export -> the four parquet files
├── .gitignore
└── README.md
```

This project was built with Claude AI as a coding partner, and HTML for the visuals.

## About

**Ahmed Elgayar** — Data & BI Engineer.
