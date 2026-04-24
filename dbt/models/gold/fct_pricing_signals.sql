-- Modelo Gold: Tabla analítica principal con todas las señales para el motor de pricing
{{ config(materialized='table', schema='gold') }}

WITH products AS (
    SELECT * FROM {{ ref('stg_products') }}
),

competitors AS (
    SELECT
        product_id_own,
        AVG(competitor_price) AS avg_comp_price,
        MIN(competitor_price) AS min_comp_price,
        MAX(competitor_price) AS max_comp_price,
        COUNT(DISTINCT competitor_id) AS n_competitors,
        MIN(price_timestamp) AS oldest_comp_price,
        MAX(price_timestamp) AS newest_comp_price
    FROM {{ ref('stg_competitor_prices') }}
    GROUP BY product_id_own
),

final AS (
    SELECT
        p.product_id,
        p.name_original,
        p.name_normalized,
        p.category,
        p.cost_price,
        p.current_price,
        p.margin_current,
        p.stock,
        p.stock_status,
        p.sales_7d,
        p.sales_30d,
        p.visits_7d,
        p.velocity_score,

        -- Datos de competencia (NULL si no hay match)
        c.avg_comp_price,
        c.min_comp_price,
        c.max_comp_price,
        c.n_competitors,
        c.newest_comp_price,

        -- Posición de precio vs competencia
        CASE
            WHEN c.avg_comp_price IS NULL THEN 'no_competition_data'
            WHEN p.current_price < c.min_comp_price * 0.95 THEN 'much_cheaper'
            WHEN p.current_price < c.avg_comp_price THEN 'cheaper'
            WHEN p.current_price BETWEEN c.avg_comp_price * 0.98
                 AND c.avg_comp_price * 1.02 THEN 'at_market'
            WHEN p.current_price > c.max_comp_price * 1.05 THEN 'much_more_expensive'
            ELSE 'more_expensive'
        END AS price_position,

        -- Diferencial de precio vs competencia (%)
        CASE
            WHEN c.avg_comp_price IS NOT NULL AND c.avg_comp_price > 0
            THEN ROUND(((p.current_price - c.avg_comp_price) / c.avg_comp_price)::numeric, 4)
            ELSE NULL
        END AS price_diff_pct_vs_avg,

        CURRENT_TIMESTAMP AS computed_at

    FROM products p
    LEFT JOIN competitors c ON p.product_id = c.product_id_own
)

SELECT * FROM final
