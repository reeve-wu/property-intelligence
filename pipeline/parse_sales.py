"""Parse NSW Valuer General bulk property sales ZIPs into one Parquet table.

Handles both record formats (archive 1990-2001, current 2001-) and all
packaging styles (single DAT, week folders, ZIPs nested in yearly ZIPs).

Usage:
    python -I pipeline/parse_sales.py RAW_DIR OUT_PARQUET

Every sale record found is written, tagged with its source file, so that
dedupe and cleaning can happen in a separate, re-runnable step (clean_sales.sql).
"""
import io
import os
import sys
import zipfile
from datetime import date

import pyarrow as pa
import pyarrow.parquet as pq

SCHEMA = pa.schema([
    ("record_format", pa.string()),      # 'archive' or 'current'
    ("district_code", pa.string()),
    ("property_id", pa.string()),
    ("sale_counter", pa.string()),
    ("download_ts", pa.string()),
    ("property_name", pa.string()),
    ("unit_number", pa.string()),
    ("house_number", pa.string()),
    ("street_name", pa.string()),
    ("locality", pa.string()),
    ("postcode", pa.string()),
    ("area", pa.float64()),
    ("area_type", pa.string()),          # M = square metres, H = hectares
    ("contract_date", pa.date32()),
    ("settlement_date", pa.date32()),
    ("purchase_price", pa.int64()),
    ("zoning", pa.string()),
    ("nature_of_property", pa.string()),
    ("primary_purpose", pa.string()),
    ("strata_lot_number", pa.string()),
    ("component_code", pa.string()),
    ("sale_code", pa.string()),
    ("interest_pct", pa.float64()),
    ("dealing_number", pa.string()),
    ("legal_description", pa.string()),
    ("dimensions", pa.string()),
    ("n_purchasers", pa.int16()),
    ("n_vendors", pa.int16()),
    ("source_zip", pa.string()),
    ("source_member", pa.string()),
])
COLS = [f.name for f in SCHEMA]


def walk(z, prefix=""):
    """Yield (member_path, bytes) for every .DAT, descending into nested ZIPs."""
    for n in z.namelist():
        if n.lower().endswith(".zip"):
            yield from walk(zipfile.ZipFile(io.BytesIO(z.read(n))), prefix + n + "!")
        elif n.upper().endswith(".DAT"):
            yield prefix + n, z.read(n)


def ymd(s):
    s = s.strip()
    if len(s) == 8 and s.isdigit():
        try:
            return date(int(s[:4]), int(s[4:6]), int(s[6:]))
        except ValueError:
            return None
    return None


def dmy(s):
    s = s.strip()
    if len(s) == 10 and s[2] == "/" and s[5] == "/":
        return ymd(s[6:] + s[3:5] + s[:2])
    return None


def num(s, cast=float):
    s = s.strip()
    if not s:
        return None
    try:
        return cast(s) if cast is float else int(float(s))
    except ValueError:
        return None


def s_(x):
    x = x.strip()
    return x or None


def parse_dat(text, source_zip, member):
    rows = []
    current = None  # current-format B row being assembled from C/D lines

    def flush():
        if current is not None:
            rows.append(current)

    for line in text.splitlines():
        if len(line) < 2 or line[1] != ";":
            continue
        t = line[0]
        f = line.split(";")
        if t == "B" and len(f) <= 23:          # archive format (22 fields)
            flush(); current = None
            f += [""] * (22 - len(f))
            rows.append({
                "record_format": "archive",
                "district_code": s_(f[1]),
                "property_id": s_(f[4]),
                "unit_number": s_(f[5]),
                "house_number": s_(f[6]),
                "street_name": s_(f[7]),
                "locality": s_(f[8]),
                "postcode": s_(f[9]),
                "contract_date": dmy(f[10]),
                "purchase_price": num(f[11], int),
                "legal_description": s_(f[12]),
                "area": num(f[13]),
                "area_type": s_(f[14]),
                "dimensions": s_(f[15]),
                "component_code": s_(f[16]),
                "zoning": s_(f[17]),
                "source_zip": source_zip,
                "source_member": member,
            })
        elif t == "B":                         # current format (25 fields)
            flush()
            f += [""] * (25 - len(f))
            current = {
                "record_format": "current",
                "district_code": s_(f[1]),
                "property_id": s_(f[2]),
                "sale_counter": s_(f[3]),
                "download_ts": s_(f[4]),
                "property_name": s_(f[5]),
                "unit_number": s_(f[6]),
                "house_number": s_(f[7]),
                "street_name": s_(f[8]),
                "locality": s_(f[9]),
                "postcode": s_(f[10]),
                "area": num(f[11]),
                "area_type": s_(f[12]),
                "contract_date": ymd(f[13]),
                "settlement_date": ymd(f[14]),
                "purchase_price": num(f[15], int),
                "zoning": s_(f[16]),
                "nature_of_property": s_(f[17]),
                "primary_purpose": s_(f[18]),
                "strata_lot_number": s_(f[19]),
                "component_code": s_(f[20]),
                "sale_code": s_(f[21]),
                "interest_pct": num(f[22]),
                "dealing_number": s_(f[23]),
                "n_purchasers": 0,
                "n_vendors": 0,
                "source_zip": source_zip,
                "source_member": member,
            }
        elif t == "C" and current is not None and len(f) > 5:
            ld = f[5].strip()
            if ld:
                prev = current.get("legal_description")
                current["legal_description"] = ld if not prev else prev + ", " + ld
        elif t == "D" and current is not None and len(f) > 5:
            role = f[5].strip()
            if role == "P":
                current["n_purchasers"] += 1
            elif role == "V":
                current["n_vendors"] += 1
    flush()
    return rows


def main(raw_dir, out_path):
    zips = sorted(p for p in os.listdir(raw_dir) if p.lower().endswith(".zip"))
    writer = pq.ParquetWriter(out_path, SCHEMA, compression="zstd")
    total = 0
    try:
        for zname in zips:
            batch = []
            for member, data in walk(zipfile.ZipFile(os.path.join(raw_dir, zname))):
                batch.extend(parse_dat(data.decode("latin-1"), zname, member))
            if batch:
                table = pa.Table.from_pydict(
                    {c: [r.get(c) for r in batch] for c in COLS}, schema=SCHEMA)
                writer.write_table(table)
            total += len(batch)
            print(f"{zname}: {len(batch):,} sales", flush=True)
    finally:
        writer.close()
    print(f"TOTAL {total:,} sale records -> {out_path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
