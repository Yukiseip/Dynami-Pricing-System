# Arquitectura del Sistema de Dynamic Pricing

## Visión General

Este documento describe la arquitectura técnica completa del sistema de Dynamic Pricing. Está diseñado para que una IA o un nuevo desarrollador pueda comprender los flujos de datos, las dependencias entre componentes y las decisiones de diseño en menos de 15 minutos.

## Diagrama de Componentes

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FUENTES DE DATOS                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                         │
│  │  catalog    │  │ competitors │  │  inventory  │  (CSV sintéticos)        │
│  │   .csv      │  │   .csv      │  │  _demand.csv│                         │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                         │
└─────────┼────────────────┼────────────────┼────────────────────────────────┘
          │                │                │
          ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CAPA BRONZE (Raw Data)                             │
│  PostgreSQL: bronze.raw_products | bronze.raw_competitors | bronze.raw_inventory│
│  • Sin transformaciones                                                        │
│  • Metadata de ingesta (ingested_at, source_file)                              │
│  • Validaciones básicas: NOT NULL, precios > 0                               │
└─────────────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          CAPA SILVER (Limpieza)                              │
│  PostgreSQL: silver.stg_products | silver.stg_competitor_prices | silver.stg_inventory│
│  • Normalización de nombres (minúsculas, sin caracteres especiales)          │
│  • Cálculo de margen actual                                                  │
│  • Clasificación de stock: out_of_stock | critical_low | normal | overstock  │
│  • Tests dbt: unique, not_null, accepted_values, expression_is_true          │
└─────────────────────────────────────────────────────────────────────────────┘
          │
          ├────────────────────────────────────┐
          │                                    │
          ▼                                    ▼
┌─────────────────────────────┐    ┌──────────────────────────────────────────┐
│      CAPA GOLD (Analytics)   │    │         VECTOR DB (Qdrant)               │
│  gold.fct_pricing_signals    │    │  Colección: product_embeddings           │
│  • Señales agregadas         │    │  • Dimensión: 384 (all-MiniLM-L6-v2)     │
│  • Posición vs competencia   │    │  • Distancia: Cosine                     │
│  • Diferencial de precio %   │    │  • Payload: product_id, source, category │
│                              │    │  • Indexado por categoría                │
│  gold.pricing_recommendations│    │                                          │
│  • Precio sugerido           │    │  silver.product_matches                  │
│  • Reasoning explicable      │    │  • status: accepted | review | rejected  │
│  • Confianza: high/medium/low│    │  • similarity_score >= 0.70              │
└─────────────┬────────────────┘    └──────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PRESENTACIÓN Y API                                 │
│  ┌─────────────────────────┐    ┌─────────────────────────────────────────┐ │
│  │    FastAPI (:8000)      │    │   Streamlit Dashboard (:8501)           │ │
│  │  • /health              │    │  • KPIs de revenue at risk              │ │
│  │  • /pricing/suggestion  │    │  • Scatter: Precio propio vs competencia│ │
│  │  • /pricing/batch       │    │  • Tabla de recomendaciones             │ │
│  │  • /matches/pending     │    │  • Filtros por categoría/acción         │ │
│  └─────────────────────────┘    └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Flujo de Datos Detallado

### 1. Ingesta (Bronze)
**Responsable:** `src/ingestion/`, DAG `ingest_daily`

Los datos se generan sintéticamente mediante `scripts/generate_datasets.py` y se cargan en PostgreSQL usando SQLAlchemy + Pandas `to_sql()`.

**Schema Bronze:**
```sql
CREATE TABLE bronze.raw_products (
    product_id VARCHAR(20) PRIMARY KEY,
    name VARCHAR(500),
    category VARCHAR(100),
    base_price DECIMAL(10,2),
    cost_price DECIMAL(10,2),
    current_price DECIMAL(10,2),
    stock INT,
    sales_7d INT,
    sales_30d INT,
    visits_7d INT,
    velocity_score DECIMAL(5,4),
    created_at TIMESTAMP,
    ingested_at TIMESTAMP,
    source_file VARCHAR(255)
);
```

**Puntos clave:**
- `if_exists='replace'` en cada ejecución (idempotente para demo)
- `chunksize=500` para evitar sobrecarga de memoria
- `pool_pre_ping=True` en SQLAlchemy para reconexión automática

### 2. Transformación dbt (Silver → Gold)
**Responsable:** `dbt/models/`, DAG `run_dbt_models`

**Bronze → Silver:**
- `stg_products`: Limpieza de nombres con `REGEXP_REPLACE`, cálculo de `margin_current`, clasificación `stock_status`
- `stg_competitor_prices`: Normalización de nombres, validación `competitor_price > 0`
- `stg_inventory`: Coalesce de nulos, validación `stock >= 0`

**Silver → Gold:**
- `fct_pricing_signals`: JOIN de productos + agregaciones de competencia. Calcula `price_position` (much_cheaper | cheaper | at_market | more_expensive | much_more_expensive | no_competition_data)

**Tests:**
- `not_null`, `unique` en claves primarias
- `dbt_utils.expression_is_true` para constraints de negocio (precio > 0, margen > 0)
- `accepted_values` para `stock_status`

### 3. Matching Inteligente (NLP + Vectores)
**Responsable:** `src/matching/`, DAG `product_matching`

**Embeddings:**
- Modelo: `sentence-transformers/all-MiniLM-L6-v2` (384 dimensiones, ~22MB)
- Input text: `f"{category}: {name}".lower()`
- Batch size: 64 para inferencia
- IDs en Qdrant: `abs(hash(f"{source}_{product_id}_{idx}")) % (2**63)`

**Algoritmo de Matching:**
1. Para cada producto propio, generar embedding
2. Buscar en Qdrant filtrando por `source=competitor` y misma categoría
3. Umbral aceptado: `>= 0.85` (automático)
4. Umbral revisión: `>= 0.70` (manual)
5. Descartado: `< 0.70`

**Salida:** Tabla `silver.product_matches` con columnas:
- `own_product_id`, `competitor_product_id`
- `similarity_score` (cosine similarity)
- `status`: accepted | review | rejected

### 4. Motor de Pricing
**Responsable:** `src/pricing/engine.py`, DAG `dynamic_pricing_pipeline`

**Inputs (ProductSignals):**
- `cost_price`, `current_price`, `avg_comp_price`, `min_comp_price`
- `stock`, `stock_status`, `velocity_score`

**Lógica de cálculo:**
```
min_allowed_price = cost_price * (1 + min_margin_pct)     # Floor de rentabilidad
base_price = max(min_allowed_price, min_comp_price - undercut_buffer)

demand_adj = map_velocity_to_demand_adjustment(velocity_score)
# velocity >= 0.15 → +0% a +10%
# velocity 0.05-0.15 → 0%
# velocity < 0.05 → -5% a 0%

stock_adj = map_stock_to_adjustment(stock, stock_status)
# overstock (>400) → -5%
# critical_low (<20) → +3%
# normal → 0%

suggested_price = base_price * (1 + demand_adj + stock_adj)
suggested_price = max(suggested_price, min_allowed_price)
```

**Outputs (PricingRecommendation):**
- `suggested_price`, `action` (increase/decrease/maintain)
- `reasoning`: String legible explicando cada factor
- `confidence`: high (comp+velocity), medium (uno de dos), low (ninguno)

### 5. API REST
**Responsable:** `src/api/main.py`

**Patrón:** FastAPI + SQLAlchemy + Pandas para queries

**Endpoints:**
- `GET /health`: Verifica PostgreSQL, Qdrant, y conteos de tablas Gold
- `GET /pricing/suggestion/{product_id}`: JOIN de `gold.pricing_recommendations` + `gold.fct_pricing_signals`
- `GET /pricing/batch`: Filtros por categoría, acción, confianza. Ordenado por `ABS(price_delta)` DESC
- `GET /matches/pending`: Matches con `status='review'` (similitud 0.70-0.85)

**Performance:**
- Queries simples con índices implícitos en PKs
- Sin joins complejos en endpoints de lectura frecuente
- Cache de Streamlit: `@st.cache_data(ttl=300)`

## Dependencias entre Servicios

```
postgres (5432)
  ├── airflow-init (depende: postgres healthy)
  ├── airflow-webserver (depende: airflow-init completed)
  ├── airflow-scheduler (depende: airflow-init completed)
  ├── api (depende: postgres healthy, qdrant healthy)
  └── dashboard (depende: postgres healthy)

qdrant (6333)
  └── api (depende: qdrant healthy)

minio (9000/9001)
  └── (standalone, usado para artefactos ML futuros)
```

## Esquema de Base de Datos Completo

### Bronze (Raw)
- `bronze.raw_products`: Catálogo propio
- `bronze.raw_competitors`: Precios de competencia
- `bronze.raw_inventory`: Stock y demanda

### Silver (Clean)
- `silver.stg_products`: Productos limpios con margen y stock_status
- `silver.stg_competitor_prices`: Precios competencia validados
- `silver.stg_inventory`: Inventario normalizado
- `silver.product_matches`: Resultados del matching NLP

### Gold (Analytics)
- `gold.fct_pricing_signals`: Tabla analítica principal con señales agregadas
- `gold.pricing_recommendations`: Recomendaciones del motor de pricing

## Decisiones de Diseño Críticas

### 1. Medallion Architecture (Bronze-Silver-Gold)
**Por qué:** Separa responsabilidades. Bronze = persistencia raw, Silver = calidad, Gold = negocio. Permite re-ejecutar transformaciones sin re-ingestar.

### 2. Reglas vs ML
**Por qué reglas:** El dominio de pricing requiere explicabilidad regulatoria y comercial. Las reglas permiten ajustar parámetros sin reentrenar modelos.
**Cuándo ML:** Si se dispone de histórico de A/B tests de precios, se puede entrenar un modelo de elasticidad de demanda y combinarlo con las reglas como guardrails.

### 3. Embeddings para Matching
**Por qué:** Los competidores usan nombres diferentes para el mismo producto (e.g., "Wireless Headphones Sony Pro" vs "Sony Pro Wireless Headset"). El matching exacto falla. Los embeddings capturan semántica.
**Alternativa:** Fuzzy matching (Levenshtein) funciona para typos pero no para paráfrasis.

### 4. Airflow como Orquestador
**Por qué:** El pipeline tiene 6 etapas con dependencias complejas (dbt debe terminar antes de embeddings, matching antes de pricing). Airflow gestiona retries, SLAs, y observabilidad.
**Alternativa:** Prefect o Dagster son válidos; Airflow se eligió por ser el estándar de industria.

## Consideraciones de Seguridad

- **.env**: Nunca commitear. Incluye passwords de PostgreSQL y MinIO.
- **PostgreSQL**: Usuario dedicado (`pricing_user`), no root.
- **API**: Sin autenticación en versión demo. Para producción, agregar OAuth2/JWT.
- **Airflow**: Cambiar `AIRFLOW_ADMIN_PASSWORD` en producción.

## Métricas y Observabilidad

### Logs
- `loguru` en todos los módulos Python
- Niveles: INFO (pipeline), SUCCESS (checkpoints), WARNING (errores recuperables), ERROR (fallos)

### Métricas de Negocio (Dashboard)
- Revenue at Risk: `(current_price - suggested_price) * sales_7d` (solo cuando sugiere bajar)
- Margen Promedio: `AVG(margin_current)`
- Mal Posicionados: Productos con `price_position` en extremos
- Sin Match: Productos sin `avg_comp_price`

### Métricas Técnicas
- Tiempo de ejecución del pipeline (SLA: 10 min)
- Tasa de éxito de tests dbt
- Cobertura de matching: `% productos con >= 1 match`
