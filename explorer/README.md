# Suburb price explorer

A single static page: pick a NSW suburb, see median house and unit prices by year,
sales per year, and the latest sales.

Build the data, then serve this folder:

    python -I pipeline/suburb_aggregates.py /path/to/sales.parquet explorer/data
    python -m http.server -d explorer 8000

`explorer/data/` is generated (about 9 MB) and not committed. The page reads
`data/suburbs.json` on load and `data/recent/<letter>.json` when a suburb is picked.

## How the numbers are built

See the docstring at the top of `pipeline/suburb_aggregates.py`. In short:

- Excludes rows flagged in cleaning (`contract_date_ok`, `price_ok`,
  `n_properties_in_sale = 1`) and prices under $10,000.
- House vs unit: current format uses nature of property `R` and strata status;
  1990 to Mar 2001 archive rows carry no property type, so they use residential
  zoning and strata plan (`SP nnnn`) legal descriptions. Pre-2001 house medians
  can include some vacant residential lots.
- Suburb is locality plus postcode, with stray postcodes (under 20% of a
  locality's sales) folded into the main one. Suburbs need 30 sales to appear,
  and a yearly median needs 5.
