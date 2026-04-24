-- Modelo Silver: Limpieza de precios de competencia
{{ config(materialized='table', schema='silver') }}

WITH source AS (
    SELECT * FROM {{ source('bronze', 'raw_competitors') }}
),

cleaned AS (
    SELECT
        competitor_id,
        product_id_own,
        LOWER(TRIM(product_name_competitor)) AS product_name_competitor,
        INITCAP(TRIM(category)) AS category,
        CASE WHEN competitor_price > 0 THEN competitor_price ELSE NULL END AS competitor_price,
        timestamp::TIMESTAMP AS price_timestamp,
        is_confirmed_match,
        ingested_at,
        CURRENT_TIMESTAMP AS processed_at
    FROM source
    WHERE
        product_id_own IS NOT NULL
        AND competitor_price > 0
        AND competitor_id IS NOT NULL
)

SELECT * FROM cleaned
