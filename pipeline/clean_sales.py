"""Run clean_sales.sql: dedupe and flag the raw parse.

Usage: python -I pipeline/clean_sales.py RAW_PARQUET OUT_PARQUET
"""
import os
import sys

import duckdb


def main(raw, out):
    sql_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clean_sales.sql")
    sql = open(sql_path).read()
    sql = sql.replace("$raw", "'" + raw.replace("'", "''") + "'")
    sql = sql.replace("$out", "'" + out.replace("'", "''") + "'")
    con = duckdb.connect()
    con.execute(sql)
    n = con.execute(f"SELECT count(*) FROM read_parquet(?)", [out]).fetchone()[0]
    print(f"{n:,} cleaned sales -> {out}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
