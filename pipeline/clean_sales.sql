-- Build the cleaned sales table from the raw parse.
-- Run with:  python -I pipeline/clean_sales.py RAW_PARQUET OUT_PARQUET
-- ($raw and $out are substituted by clean_sales.py)

CREATE OR REPLACE TEMP VIEW raw AS SELECT * FROM read_parquet($raw);

-- Current format: the same sale is re-sent in later weekly files when it is
-- corrected. Keep the most recently downloaded version of each dealing.
CREATE OR REPLACE TEMP VIEW cur AS
SELECT * EXCLUDE (rn) FROM (
    SELECT *, row_number() OVER (
        PARTITION BY district_code, property_id, dealing_number, contract_date
        ORDER BY download_ts DESC, source_zip DESC, source_member DESC) AS rn
    FROM raw WHERE record_format = 'current'
) WHERE rn = 1;

-- Archive format: only exact duplicates exist. Also drop early-2001 archive
-- rows that reappear in the current-format files.
CREATE OR REPLACE TEMP VIEW arc AS
SELECT DISTINCT ON (district_code, property_id, unit_number, house_number, street_name,
                    locality, contract_date, purchase_price, legal_description, area) *
FROM raw a
WHERE record_format = 'archive'
  AND NOT EXISTS (
      SELECT 1 FROM cur c
      WHERE c.contract_date = a.contract_date
        AND c.purchase_price = a.purchase_price
        AND (c.property_id = a.property_id
             OR (c.locality = a.locality AND c.street_name = a.street_name
                 AND coalesce(c.house_number, '') = coalesce(a.house_number, ''))));

-- Sales that span several properties report the full price on each property.
CREATE OR REPLACE TEMP VIEW multi AS
SELECT district_code, dealing_number, count(DISTINCT property_id) AS n_properties_in_sale
FROM cur WHERE dealing_number IS NOT NULL
GROUP BY ALL;

COPY (
    SELECT
        s.record_format,
        s.district_code,
        s.property_id,
        s.dealing_number,
        s.unit_number,
        s.house_number,
        s.street_name,
        s.locality,
        s.postcode,
        concat_ws(' ',
            CASE WHEN s.unit_number IS NOT NULL THEN s.unit_number || '/' END
                || coalesce(s.house_number, ''),
            s.street_name, s.locality, s.postcode) AS address,
        s.property_name,
        s.contract_date,
        s.settlement_date,
        year(s.contract_date) AS contract_year,
        s.purchase_price,
        s.interest_pct,
        CASE s.area_type WHEN 'H' THEN s.area * 10000 WHEN 'M' THEN s.area END AS area_m2,
        s.area,
        s.area_type,
        s.zoning,
        s.nature_of_property,
        s.primary_purpose,
        s.strata_lot_number,
        s.strata_lot_number IS NOT NULL OR s.unit_number IS NOT NULL AS is_strata,
        s.component_code,
        s.sale_code,
        s.legal_description,
        s.dimensions,
        s.n_purchasers,
        s.n_vendors,
        coalesce(m.n_properties_in_sale, 1) AS n_properties_in_sale,
        -- quality flags: keep the rows, let analysis filter on these
        (s.contract_date IS NOT NULL
            AND s.contract_date >= DATE '1985-01-01'
            AND s.contract_date <= coalesce(s.settlement_date, current_date)
            AND s.contract_date <= current_date) AS contract_date_ok,
        (s.purchase_price IS NOT NULL AND s.purchase_price > 0) AS price_ok,
        s.source_zip,
        s.download_ts
    FROM (SELECT * FROM cur UNION ALL BY NAME SELECT * FROM arc) s
    LEFT JOIN multi m USING (district_code, dealing_number)
    ORDER BY s.contract_date, s.district_code, s.property_id
) TO $out (FORMAT parquet, COMPRESSION zstd);
