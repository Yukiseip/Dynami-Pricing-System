-- Modelo Silver: Limpieza de inventario (alternativa si viene de sistema separado)
{{ config(materialized='table', schema='silver') }}

SELECT
    product_id,
    GREATEST(0, COALESCE(stock, 0)) AS stock,
    COALESCE(sales_7d, 0) AS sales_7d,
    COALESCE(sales_30d, 0) AS sales_30d,
    COALESCE(visits_7d, 0) AS visits_7d,
    COALESCE(velocity_score, 0.0) AS velocity_score,
    updated_at::TIMESTAMP AS updated_at,
    CURRENT_TIMESTAMP AS processed_at
FROM {{ source('bronze', 'raw_inventory') }}
WHERE product_id IS NOT NULL
