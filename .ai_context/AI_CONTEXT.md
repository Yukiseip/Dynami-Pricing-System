# AI Context: Dynamic Pricing System

> Este documento está diseñado específicamente para que un modelo de lenguaje (LLM) o asistente de IA pueda comprender rápidamente el codebase, responder preguntas técnicas precisas, y ayudar a extender o debuggear el sistema.

## Identidad del Sistema

**Nombre:** Dynamic Pricing System for E-commerce  
**Dominio:** Retail / E-commerce de electrónica  
**Propósito:** Calcular precios óptimos para productos propios basándose en competencia, stock y demanda, de forma automática y explicable.  
**Frecuencia:** Pipeline ejecuta cada hora (`@hourly`).  
**Escala objetivo:** 1,000 SKUs (demo) → 1,000,000 SKUs (producción).

## Stack y Versiones

```yaml
Python: 3.11
FastAPI: 0.109.0
Pydantic: 2.5.3
SQLAlchemy: ">=1.4.36,<2.0" # Compatible con Airflow 2.8.x
PostgreSQL: 15-alpine
Airflow: 2.8.1
Qdrant: latest (client 1.7.1)
dbt-core: 1.7.4
sentence-transformers: 2.3.1
torch: 2.1.2
Streamlit: 1.30.0
```

## Estructura de Directorios para IA

Cuando un usuario pregunte "¿dónde está X?", usa esta tabla:

| Concepto | Ruta | Tipo |
|----------|------|------|
| Generación de datos sintéticos | `scripts/generate_datasets.py` | Script |
| Ingesta a Bronze | `src/ingestion/ingest_*.py` | Módulos Python |
| Utilidades DB | `src/ingestion/db_utils.py` | Módulo |
| Modelos dbt Bronze | `dbt/models/bronze/` | SQL + YAML |
| Modelos dbt Silver | `dbt/models/silver/` | SQL + YAML |
| Modelos dbt Gold | `dbt/models/gold/` | SQL + YAML |
| Config dbt | `dbt/dbt_project.yml`, `dbt/profiles.yml` | YAML |
| Embeddings NLP | `src/matching/embeddings.py` | Módulo |
| Matching algorithm | `src/matching/matcher.py` | Módulo |
| Motor de pricing | `src/pricing/engine.py` | Módulo |
| Config pricing | `src/pricing/config.py`, `config/pricing_config.yaml` | Python + YAML |
| API FastAPI | `src/api/main.py` | Módulo |
| Schemas API | `src/api/schemas.py` | Módulo |
| Dashboard Streamlit | `dashboard/app.py` | Script |
| DAGs Airflow | `airflow/dags/dag_*.py` | Scripts Python |
| Tests unitarios | `tests/test_pricing_engine.py` | pytest |
| Docker Compose | `docker-compose.yml` | YAML |
| Dockerfiles | `docker/Dockerfile.*` | Docker |
| Infra Terraform | `terraform/*.tf` | HCL |

## Contratos de Datos Clave

### ProductSignals (Input del motor)
```python
@dataclass
class ProductSignals:
    product_id: str
    name: str
    category: str
    cost_price: float        # OBLIGATORIO, > 0
    current_price: float
    avg_comp_price: Optional[float]
    min_comp_price: Optional[float]
    stock: int = 0
    stock_status: str = "normal"   # Enum: out_of_stock | critical_low | normal | overstock
    velocity_score: float = 0.0    # Ratio sales_7d / visits_7d
    sales_7d: int = 0
```

### PricingRecommendation (Output del motor)
```python
@dataclass
class PricingRecommendation:
    product_id: str
    current_price: float
    suggested_price: float
    min_allowed_price: float       # cost_price * (1 + min_margin_pct)
    competitive_price: Optional[float]
    demand_adjustment: float       # % de ajuste por demanda
    stock_adjustment: float        # % de ajuste por stock
    base_price_used: float         # Precio base antes de ajustes
    action: str                    # Enum: decrease | increase | maintain
    reasoning: str                 # Explicación legible en español
    confidence: str                # Enum: high | medium | low
```

## Reglas de Negocio del Motor

### 1. Floor de Rentabilidad
```
min_allowed_price = cost_price * (1 + min_margin_pct)
# min_margin_pct por defecto = 10%
```
El precio sugerido NUNCA puede ser menor que `min_allowed_price`.

### 2. Precio Base Competitivo
```
Si hay min_comp_price:
    competitive_price = min_comp_price - undercut_buffer  # undercut_buffer = $1.00
    base_price = max(min_allowed_price, competitive_price)
Si NO hay competencia:
    base_price = min_allowed_price * 1.05  # 5% sobre mínimo
```

### 3. Ajuste por Demanda (Velocity)
```
velocity = sales_7d / visits_7d

Si velocity >= 0.15:    # Alta conversión
    demand_adj = +0% a +10% (lineal)
Elif velocity >= 0.05:  # Normal
    demand_adj = 0%
Else:                   # Baja conversión
    demand_adj = -5% a 0% (lineal)
```

### 4. Ajuste por Stock
```
stock_status == "overstock" (stock > 400):     stock_adj = -5%
stock_status == "critical_low" (stock < 20):   stock_adj = +3%
stock_status == "normal":                      stock_adj = 0%
stock_status == "out_of_stock":                Mantener precio actual, no calcular
```

### 5. Precio Final
```
suggested_price = base_price * (1 + demand_adj + stock_adj)
suggested_price = max(suggested_price, min_allowed_price)
```

## DAGs y su Propósito

| DAG ID | Propósito | Schedule | Dependencias |
|--------|-----------|----------|--------------|
| `ingest_daily` | Regenerar datos e ingestar a Bronze | `@daily` | Ninguna (standalone) |
| `run_dbt_models` | Ejecutar transformaciones dbt | `None` (triggered) | ingest_daily |
| `product_matching` | Generar embeddings y matching | `None` (triggered) | run_dbt_models |
| `dynamic_pricing_pipeline` | **Pipeline maestro completo** | `@hourly` | Orquesta todo internamente |

**DAG maestro interno:**
```
ingest_data → validate_data_quality → run_dbt_transformations 
→ generate_embeddings → run_product_matching → run_pricing_engine
```

## Variables de Entorno Críticas

```env
# PostgreSQL
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=dynamic_pricing
POSTGRES_USER=pricing_user
POSTGRES_PASSWORD=pricing_pass_dev_2024

# Qdrant
QDRANT_HOST=qdrant
QDRANT_PORT=6333
QDRANT_COLLECTION=product_embeddings

# Matching
EMBEDDING_MODEL=all-MiniLM-L6-v2
SIMILARITY_THRESHOLD=0.85
SIMILARITY_REVIEW_THRESHOLD=0.70

# Pricing Engine
MIN_MARGIN_PCT=0.10
MAX_DEMAND_ADJUSTMENT=0.10
MAX_STOCK_ADJUSTMENT=0.05
UNDERCUT_BUFFER=1.00
```

## Patrones de Código Comunes

### Conexión a PostgreSQL
```python
from src.ingestion.db_utils import get_engine
engine = get_engine()
df = pd.read_sql("SELECT * FROM gold.fct_pricing_signals", engine)
```

### Cliente Qdrant
```python
from src.matching.embeddings import get_qdrant_client, COLLECTION_NAME
client = get_qdrant_client()
collections = [c.name for c in client.get_collections().collections]
```

### Cargar Configuración
```python
from src.pricing.config import load_config
config = load_config()  # Lee config/pricing_config.yaml
```

### Ejecutar Motor de Pricing
```python
from src.pricing.engine import calculate_price, ProductSignals
signals = ProductSignals(product_id="SKU-001", name="Test", category="Audio",
                         cost_price=100.0, current_price=150.0, stock=50,
                         stock_status="normal", velocity_score=0.08)
rec = calculate_price(signals)
print(rec.suggested_price, rec.reasoning)
```

## Errores Comunes y Soluciones

| Error | Causa | Solución |
|-------|-------|----------|
| `FileNotFoundError: data/raw/catalog.csv` | No se ejecutó `generate_datasets.py` | `python scripts/generate_datasets.py` |
| `sqlalchemy.exc.OperationalError: Connection refused` | PostgreSQL no está listo | Esperar healthcheck: `docker-compose ps` |
| `ModuleNotFoundError: No module named 'src'` | PYTHONPATH no configurado | `export PYTHONPATH=/app` (en Docker) o `export PYTHONPATH=$(pwd)` (local) |
| `dbt not found` | dbt no instalado en el entorno | `pip install dbt-core dbt-postgres` |
| `Qdrant connection refused` | Qdrant no está levantado | `docker-compose up -d qdrant` |
| `pytest fails: cost_price inválido` | Datos de test inconsistentes | Revisar fixture `normal_product` tiene cost_price=100.0 |
| `Airflow DAG not appearing` | Error de importación en DAG | Revisar logs: `docker logs pricing_airflow_scheduler` |

## Extensiones Sugeridas

Cuando un usuario pida "agregar X al sistema", usa estas guías:

### Agregar una nueva fuente de datos
1. Crear `src/ingestion/ingest_nueva_fuente.py` (patrón: leer CSV/JSON → validar → to_sql a bronze)
2. Agregar modelo Bronze en `dbt/models/bronze/raw_nueva_fuente.sql`
3. Agregar modelo Silver en `dbt/models/silver/stg_nueva_fuente.sql`
4. Agregar tests en `dbt/models/silver/schema.yml`
5. Agregar tarea al DAG maestro

### Agregar una nueva regla de pricing
1. Modificar `src/pricing/config.py` para agregar el parámetro
2. Implementar función de ajuste en `src/pricing/engine.py` (patrón: `map_X_to_adjustment`)
3. Agregar test en `tests/test_pricing_engine.py`
4. Actualizar `config/pricing_config.yaml`

### Agregar un nuevo endpoint a la API
1. Definir schema en `src/api/schemas.py` (heredar de `BaseModel`)
2. Implementar handler en `src/api/main.py` (usar `get_engine()` para queries)
3. Documentar con docstrings (FastAPI genera docs automáticamente)

### Agregar un nuevo gráfico al Dashboard
1. Modificar `dashboard/app.py`
2. Usar `plotly.express` o `plotly.graph_objects`
3. Asegurar que la query SQL esté en `gold.fct_pricing_signals` o `gold.pricing_recommendations`
4. Agregar filtros en la sidebar si aplica

## Constraints y Límites

- **Máximo productos en generación sintética:** 100,000 (limitado por memoria de Pandas)
- **Dimensión de embeddings:** 384 fijo (all-MiniLM-L6-v2)
- **Top K matching:** 3 candidatos por producto
- **SLA pipeline:** 10 minutos
- **Margen mínimo:** 10% (configurable)
- **Ajuste máximo por demanda:** +10% / -5%
- **Ajuste máximo por stock:** +3% / -5%

## Idiomas y Convenciones

- **Código:** Python 3.11 con type hints obligatorios
- **Docstrings:** Google style (Args, Returns, Raises)
- **SQL:** dbt models con Jinja2 (`{{ ref() }}`, `{{ source() }}`)
- **Variables:** snake_case en Python, lower_snake en SQL
- **Comentarios:** Español (proyecto hispanohablante)
- **Logs:** Español con emojis para checkpoints
- **Tests:** pytest con fixtures, mínimo 80% coverage en `src/pricing/`

## Contacto y Metadata

- **Autor:** Proyecto de portafolio
- **Licencia:** MIT
- **Última actualización:** 2024
- **Repositorio:** `dynamic-pricing-de`
