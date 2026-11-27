# Pipeline

1. `python -I pipeline/parse_sales.py RAW_DIR sales_raw.parquet`
   Reads every `*.zip` in RAW_DIR (yearly and weekly NSW Valuer General files), handles
   both record formats and all packaging styles, writes one row per sale record found.
2. `python -I pipeline/clean_sales.py sales_raw.parquet sales.parquet`
   Keeps the latest version of re-sent sales, drops archive/current overlap in 2001,
   adds `address`, `area_m2`, `is_strata`, `n_properties_in_sale` and quality flags
   `contract_date_ok`, `price_ok`.

Full rebuild of 1990 to mid-2026 takes about 2.5 minutes.

Analysis tips:
- Filter `contract_date_ok AND price_ok` for price stats.
- `n_properties_in_sale > 1` means the price covers several properties; exclude for medians.
- `nature_of_property`: R = residence, V = vacant land, 3 = other (current format only).
3. `python -I pipeline/suburb_aggregates.py sales.parquet explorer/data`
   Per-suburb yearly house/unit medians and counts, last-12-month figures and the
   latest 40 sales per suburb, for the suburb price explorer (`explorer/`). About 5 seconds.
