# NSW Valuer General property sales data: inventory

Source: NSW Valuer General bulk property sales information (CC BY 4.0, see creative_commons.txt in each ZIP).
Sample on hand: yearly ZIPs 1990–2025 and weekly ZIPs 2026-01-05 to 2026-07-13 (64 files, ~470 MB zipped, ~1.85 GB of .DAT text, ~7.4M sale records).

## Packaging (three layouts)

| Years | Layout |
|---|---|
| 1990–2000 | One `ARCHIVE_SALES_YYYY.DAT` per year |
| 2001 | Both: `Archive Sales 2001/ARCHIVE_SALES_2001.DAT` (Jan–Mar) plus weekly folders of current-format DATs (from 29 Mar 2001) |
| 2002–2014 | Folders named by week (`April 16, 2003/`, `April 02, 2012 (NME)/` ...) holding one DAT per LGA district code (`NNN_SALES_DATA_NNME_DDMMYYYY.DAT`) |
| 2015–2025 | Yearly ZIP of 51–53 weekly ZIPs (`YYYYMMDD.zip`; 2019 nests them under `2019/`) |
| Weekly (current) | Flat ZIP of per-district DATs + creative_commons.txt |

## Record formats (semicolon-delimited, latin-1)

Every DAT has an `A` header record and a `Z` trailer (record counts).

**Archive format (1990–early 2001)**: `B` records, 22 fields, one per sale:
district code, source, valuation number, property id, unit, house no, street, locality, postcode, contract date (DD/MM/YYYY), price, legal description, area, area type (M/H), dimensions, land use code, zoning, ... No separate settlement date.

**Current format (Mar 2001–today)**: one sale is a group of records sharing district + property id + sale counter:
- `B` (25 fields): district, property id, sale counter, download timestamp, property name, unit, house no, street, locality, postcode, area, area type (M=m², H=ha), contract date (YYYYMMDD), settlement date, price, zoning, nature of property (R/V/3), primary purpose, strata lot no, component code, sale code, % interest, dealing number.
- `C`: legal description (lot/plan).
- `D`: purchaser/vendor role markers (P/V). Names are withheld (the "NNME" in filenames).
- 2022 onward the `A` header gains an extra `RTSALEDATA` field; field positions in B/C/D are unchanged.

## Gotchas found

- Weekly files are by **date processed**, not sale date: each week includes late-registered sales going back years (some to the 1970s–90s). Dedupe on district + property id + dealing number + contract date.
- Bad dates exist (e.g. 1000-11-17, 2029, 2102). Need validation.
- Zoning codes changed (old letter codes like `R`/`A`, current LEP codes like `R2`).
- 2018 yearly has 51 weeks; to confirm whether a week is missing.
- Not on hand yet: weekly files after 2026-07-13.
