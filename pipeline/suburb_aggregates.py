"""Build the per-suburb aggregates that feed the suburb price explorer.

Usage: python -I pipeline/suburb_aggregates.py SALES_PARQUET OUT_DIR

Writes:
  OUT_DIR/suburbs.json        one record per suburb: yearly house/unit medians and
                              counts, last-12-month figures, plus an NSW-wide series
  OUT_DIR/recent/<A-Z>.json   the latest sales per suburb, sharded by first letter

Rules (see docs/suburb-aggregates.md):
  * Only rows with contract_date_ok, price_ok, n_properties_in_sale = 1 and a
    price of at least $10,000 count (drops nominal and related-party transfers).
  * House / unit:
      current format (Mar 2001 on): nature_of_property = 'R' (residence);
        unit when strata (strata lot or unit number), else house.
      archive format (1990 to Mar 2001): no property type is recorded, so rows with
        residential zoning ('A') or no zoning count; unit when strata, unit number
        or a strata plan (SP nnnn) in the legal description, else house. Vacant
        residential lots can't be told apart, so pre-2001 house medians run a
        little low.
  * Suburb = locality + postcode. Postcodes are noisy (typos, PO boxes), so for
    each locality any postcode with under 20% of that locality's sales is folded
    into its main postcode. Suburbs with fewer than MIN_SALES sales are dropped.
  * A yearly median is published only when it rests on MIN_YEAR_COUNT sales.
"""
import json
import os
import sys

import duckdb

MIN_PRICE = 10_000
MIN_SALES = 30
MIN_YEAR_COUNT = 5
RECENT_PER_SUBURB = 40

PREP = r"""
CREATE OR REPLACE TEMP TABLE s AS
SELECT
    locality,
    coalesce(nullif(postcode, '0'), '') AS postcode,
    contract_date,
    contract_year,
    purchase_price AS price,
    address,
    area_m2,
    CASE
        WHEN record_format = 'current' AND nature_of_property = 'R'
            THEN CASE WHEN is_strata THEN 'u' ELSE 'h' END
        WHEN record_format = 'archive' AND coalesce(zoning, 'A') = 'A'
            THEN CASE WHEN is_strata
                        OR regexp_matches(coalesce(legal_description, ''), '(^|\s)SP\s*\d')
                      THEN 'u' ELSE 'h' END
    END AS ptype
FROM read_parquet($sales)
WHERE contract_date_ok AND price_ok AND n_properties_in_sale = 1
  AND purchase_price >= $min_price
  AND contract_year >= 1990 AND locality IS NOT NULL;
DELETE FROM s WHERE ptype IS NULL;

-- fold minor postcodes into each locality's main postcode
CREATE OR REPLACE TEMP TABLE pc AS
WITH c AS (SELECT locality, postcode, count(*) n FROM s GROUP BY ALL),
t AS (SELECT locality, postcode, n, sum(n) OVER (PARTITION BY locality) tot,
             row_number() OVER (PARTITION BY locality ORDER BY n DESC, postcode) rk FROM c)
SELECT t.locality, t.postcode,
       CASE WHEN t.n >= 0.2 * t.tot AND t.postcode <> '' THEN t.postcode ELSE m.postcode END AS pc
FROM t JOIN t m ON m.locality = t.locality AND m.rk = 1;

UPDATE s SET postcode = pc.pc FROM pc
WHERE s.locality = pc.locality AND s.postcode = pc.postcode;

CREATE OR REPLACE TEMP TABLE sub AS
SELECT locality, postcode, count(*) n FROM s GROUP BY ALL HAVING count(*) >= $min_sales;
"""


def title(name):
    small = {"OF", "THE", "AND"}
    return " ".join(w.capitalize() if i == 0 or w not in small else w.lower()
                    for i, w in enumerate(name.split()))


def main(sales, out_dir):
    con = duckdb.connect()
    con.execute("SET enable_progress_bar = false")
    sql = (PREP.replace("$sales", "'" + sales.replace("'", "''") + "'")
               .replace("$min_price", str(MIN_PRICE))
               .replace("$min_sales", str(MIN_SALES)))
    con.execute(sql)

    max_date = con.execute("SELECT max(contract_date) FROM s").fetchone()[0]
    y0, y1 = con.execute("SELECT min(contract_year), max(contract_year) FROM s").fetchone()
    years = list(range(y0, y1 + 1))

    yearly = con.execute("""
        SELECT locality, postcode, contract_year, ptype, count(*) n, median(price) med
        FROM s JOIN sub USING (locality, postcode) GROUP BY ALL""").fetchall()
    l12 = con.execute(f"""
        SELECT locality, postcode, ptype, count(*) n, median(price) med
        FROM s JOIN sub USING (locality, postcode)
        WHERE contract_date > DATE '{max_date}' - INTERVAL 12 MONTH GROUP BY ALL""").fetchall()
    nsw = con.execute("""
        SELECT contract_year, ptype, count(*) n, median(price) med FROM s GROUP BY ALL""").fetchall()
    nsw12 = con.execute(f"""
        SELECT ptype, count(*) n, median(price) med FROM s
        WHERE contract_date > DATE '{max_date}' - INTERVAL 12 MONTH GROUP BY ALL""").fetchall()

    idx = {y: i for i, y in enumerate(years)}

    def blank():
        return {"h": [None] * len(years), "u": [None] * len(years),
                "hn": [0] * len(years), "un": [0] * len(years)}

    def put(rec, year, ptype, n, med):
        i = idx[year]
        rec[ptype + "n"][i] = n
        rec[ptype][i] = int(round(med)) if n >= MIN_YEAR_COUNT else None

    subs = {}
    for loc, pc, yr, pt, n, med in yearly:
        rec = subs.setdefault((loc, pc), blank())
        put(rec, yr, pt, n, med)
    for loc, pc, pt, n, med in l12:
        rec = subs[(loc, pc)]
        rec[pt + "12"] = int(round(med)) if n >= MIN_YEAR_COUNT else None
        rec[pt + "12n"] = n

    names = {}
    for loc, pc in subs:
        names.setdefault(loc, []).append(pc)

    out = []
    for (loc, pc), rec in sorted(subs.items()):
        sid = (loc + " " + pc).strip().replace(" ", "-").lower()
        rec.update({"id": sid, "name": title(loc), "pc": pc,
                    "dup": len(names[loc]) > 1})
        out.append(rec)

    state = blank()
    for yr, pt, n, med in nsw:
        put(state, yr, pt, n, med)
    for pt, n, med in nsw12:
        state[pt + "12"] = int(round(med))
        state[pt + "12n"] = n

    os.makedirs(os.path.join(out_dir, "recent"), exist_ok=True)
    meta = {"years": years, "data_to": str(max_date), "min_year_count": MIN_YEAR_COUNT,
            "min_price": MIN_PRICE, "source": "NSW Valuer General bulk property sales (CC BY 4.0)"}
    with open(os.path.join(out_dir, "suburbs.json"), "w") as f:
        json.dump({"meta": meta, "nsw": state, "suburbs": out}, f, separators=(",", ":"))

    recent = con.execute(f"""
        SELECT locality, postcode, contract_date, price, ptype, address, area_m2 FROM (
            SELECT s.*, row_number() OVER (PARTITION BY locality, postcode
                                           ORDER BY contract_date DESC, address) rn
            FROM s JOIN sub USING (locality, postcode))
        WHERE rn <= {RECENT_PER_SUBURB}
        ORDER BY locality, postcode, contract_date DESC""").fetchall()
    shards = {}
    for loc, pc, d, price, pt, addr, area in recent:
        sid = (loc + " " + pc).strip().replace(" ", "-").lower()
        letter = sid[0].upper() if sid[0].isalpha() else "0"
        a = int(round(area)) if area and pt == "h" else None
        shards.setdefault(letter, {}).setdefault(sid, []).append(
            [d.isoformat(), int(price), pt, addr, a])
    for letter, data in shards.items():
        with open(os.path.join(out_dir, "recent", letter + ".json"), "w") as f:
            json.dump(data, f, separators=(",", ":"))

    print(f"{len(out):,} suburbs, years {y0}-{y1}, data to {max_date} -> {out_dir}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
