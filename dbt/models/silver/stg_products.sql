-- Modelo Silver: Limpieza y normalización del catálogo de productos
{{ config(materialized='table', schema='silver') }}

WITH source AS (
    SELECT * FROM {{ source('bronze', 'raw_products') }}
),

cleaned AS (
    SELECT
        product_id,

        -- Normalizar nombre: minúsculas, sin caracteres especiales
        LOWER(TRIM(REGEXP_REPLACE(name, '[^a-zA-Z0-9 \-]', '', 'g'))) AS name_normalized,
        name AS name_original,

        -- Normalizar categoría
        INITCAP(TRIM(category)) AS category,

        -- Precios con validación básica
        CASE WHEN cost_price > 0 THEN cost_price ELSE NULL END AS cost_price,
        CASE WHEN current_price > 0 THEN current_price ELSE NULL END AS current_price,
        CASE WHEN base_price > 0 THEN base_price ELSE NULL END AS base_price,

        -- Métricas calculadas
        CASE
            WHEN cost_price > 0 AND current_price > 0
            THEN ROUND(((current_price - cost_price) / current_price)::numeric, 4)
            ELSE NULL
        END AS margin_current,

        -- Stock y demanda
        GREATEST(0, COALESCE(stock, 0)) AS stock,
        COALESCE(sales_7d, 0) AS sales_7d,
        COALESCE(sales_30d, 0) AS sales_30d,
        COALESCE(visits_7d, 0) AS visits_7d,
        COALESCE(velocity_score, 0.0) AS velocity_score,

        -- Clasificación de stock
        CASE
            WHEN COALESCE(stock, 0) = 0 THEN 'out_of_stock'
            WHEN COALESCE(stock, 0) < 20 THEN 'critical_low'
            WHEN COALESCE(stock, 0) >= 400 THEN 'overstock'
            ELSE 'normal'
        END AS stock_status,

        ingested_at,
        CURRENT_TIMESTAMP AS processed_at

    FROM source
    WHERE
        product_id IS NOT NULL
        AND current_price > 0
        AND cost_price > 0
        AND cost_price < current_price  -- Precio de venta debe superar el costo
)

SELECT * FROM cleaned
