# Operations Guide: Dynamic Pricing System

> Guía práctica para operar, monitorear y troubleshootear el sistema en ambientes de desarrollo y demo.

## Tabla de Comandos Esenciales

### Docker Compose

```bash
# Levantar todo el stack
docker-compose up -d

# Levantar solo infraestructura base
docker-compose up -d postgres qdrant minio

# Ver estado de servicios
docker-compose ps

# Ver logs de un servicio específico
docker-compose logs -f postgres
docker-compose logs -f api
docker-compose logs -f airflow-scheduler

# Reconstruir un servicio
docker-compose up -d --build api

# Detener todo
docker-compose down

# Detener y eliminar volúmenes (⚠️ pierde datos)
docker-compose down -v

# Ejecutar comando en contenedor
docker exec pricing_postgres psql -U pricing_user -d dynamic_pricing -c "SELECT COUNT(*) FROM gold.fct_pricing_signals;"
```

### PostgreSQL

```bash
# Conectarse a la base de datos
docker exec -it pricing_postgres psql -U pricing_user -d dynamic_pricing

# Comandos útiles dentro de psql
\dt                    # Listar tablas
\dt bronze.*          # Listar tablas de schema bronze
\dt silver.*          # Listar tablas de schema silver
\dt gold.*            # Listar tablas de schema gold
\d bronze.raw_products # Describir tabla

# Queries de verificación rápida
SELECT COUNT(*) FROM bronze.raw_products;
SELECT COUNT(*) FROM silver.stg_products;
SELECT COUNT(*) FROM gold.fct_pricing_signals;
SELECT COUNT(*) FROM gold.pricing_recommendations;
SELECT * FROM silver.product_matches WHERE status = 'review' LIMIT 10;

# Ver tamaño de tablas
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename))
FROM pg_tables WHERE schemaname IN ('bronze', 'silver', 'gold') ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

### Airflow

```bash
# Listar DAGs
docker exec pricing_airflow_scheduler airflow dags list

# Disparar DAG manualmente
docker exec pricing_airflow_scheduler airflow dags trigger dynamic_pricing_pipeline

# Ver últimas ejecuciones
docker exec pricing_airflow_scheduler airflow dags list-runs -d dynamic_pricing_pipeline

# Ver tasks de una ejecución
docker exec pricing_airflow_scheduler airflow tasks list dynamic_pricing_pipeline

# Ver logs de un task específico
docker exec pricing_airflow_scheduler airflow tasks logs dynamic_pricing_pipeline run_pricing_engine 2024-01-01

# Marcar un DAG como unpaused
docker exec pricing_airflow_scheduler airflow dags unpause dynamic_pricing_pipeline

# Borrar historial de ejecuciones (limpieza)
docker exec pricing_airflow_scheduler airflow dags delete -y dynamic_pricing_pipeline
```

### dbt

```bash
# Ejecutar desde contenedor de Airflow (tiene dbt instalado)
docker exec -it pricing_airflow_scheduler bash
cd /opt/airflow/dbt

# Comandos dbt
dbt debug                           # Verificar conexión
dbt run                             # Ejecutar todos los modelos
dbt run --select bronze             # Solo Bronze
dbt run --select silver             # Solo Silver
dbt run --select gold               # Solo Gold
dbt test                            # Ejecutar tests
dbt test --select silver            # Tests de Silver
dbt docs generate                   # Generar documentación
dbt docs serve                      # Servir documentación en localhost:8080
```

### API

```bash
# Health check
curl http://localhost:8000/health

# Obtener sugerencia para un producto
curl http://localhost:8000/pricing/suggestion/SKU-00001

# Batch con filtros
curl "http://localhost:8000/pricing/batch?category=Audio&action=decrease&limit=5"

# Matches pendientes
curl http://localhost:8000/matches/pending

# Documentación interactiva (abrir en navegador)
# http://localhost:8000/docs
```

### Qdrant

```bash
# Health check
curl http://localhost:6333/healthz

# Listar colecciones
curl http://localhost:6333/collections

# Info de colección
curl http://localhost:6333/collections/product_embeddings

# Contar puntos
curl -X POST http://localhost:6333/collections/product_embeddings/points/count   -H "Content-Type: application/json" -d '{"exact": true}'

# Buscar puntos (ejemplo)
curl -X POST http://localhost:6333/collections/product_embeddings/points/search   -H "Content-Type: application/json"   -d '{
    "vector": [0.1, 0.2, 0.3, ...],  # 384 dimensiones
    "limit": 3,
    "with_payload": true
  }'
```

### Tests

```bash
# Ejecutar tests unitarios
cd dynamic-pricing-de
pytest tests/test_pricing_engine.py -v

# Con coverage
pytest tests/ --cov=src --cov-report=html --cov-report=term

# Ver reporte HTML
coverage html
# Abrir htmlcov/index.html
```

## Troubleshooting

### Problema: PostgreSQL no inicia o reinicia en loop

**Síntomas:** `docker-compose ps` muestra postgres como `restarting` o `unhealthy`.

**Causas posibles:**
1. Puerto 5432 ya está en uso por otra instancia de PostgreSQL local
2. Volumen corrupto de datos

**Solución:**
```bash
# Verificar puerto en uso
lsof -i :5432
# Si hay otro proceso, detenerlo o cambiar el puerto en docker-compose.yml

# Si el volumen está corrupto
docker-compose down -v
docker-compose up -d postgres
```

### Problema: Airflow no muestra los DAGs

**Síntomas:** UI en `http://localhost:8080` no lista ningún DAG o muestra errores de importación.

**Causas posibles:**
1. Error de sintaxis en un archivo DAG
2. PYTHONPATH no configurado correctamente
3. Dependencias faltantes

**Solución:**
```bash
# Ver logs del scheduler
docker-compose logs -f airflow-scheduler

# Buscar errores de importación
docker exec pricing_airflow_scheduler python -c "import sys; sys.path.insert(0, '/opt/airflow/src'); from matching.embeddings import get_qdrant_client"

# Verificar que los archivos existen
docker exec pricing_airflow_scheduler ls -la /opt/airflow/dags/

# Si hay error de módulo, verificar requirements
docker exec pricing_airflow_scheduler pip list | grep -i qdrant
```

### Problema: API responde 404 para todos los endpoints

**Síntomas:** `curl http://localhost:8000/health` devuelve 404.

**Causas posibles:**
1. La app no se cargó correctamente
2. Puerto mal mapeado

**Solución:**
```bash
# Verificar que la API está corriendo
docker-compose ps | grep api

# Ver logs
docker-compose logs -f api

# Verificar que el health endpoint existe
docker exec pricing_api curl -s http://localhost:8000/health
```

### Problema: dbt falla con "relation does not exist"

**Síntomas:** `dbt run` falla porque no encuentra tablas fuente.

**Causas posibles:**
1. No se ejecutó la ingesta primero
2. Schema no creado

**Solución:**
```bash
# Verificar que las tablas bronze existen
docker exec pricing_postgres psql -U pricing_user -d dynamic_pricing -c "\dt bronze.*"

# Si no existen, ejecutar ingesta manual
python scripts/generate_datasets.py
python -m src.ingestion.ingest_catalog
python -m src.ingestion.ingest_competitors
python -m src.ingestion.ingest_inventory

# Luego ejecutar dbt
cd dbt && dbt run
```

### Problema: Matching no encuentra resultados

**Síntomas:** `silver.product_matches` está vacía o tiene muy pocos registros.

**Causas posibles:**
1. Qdrant no tiene embeddings indexados
2. Umbral de similitud muy alto
3. Categorías no coinciden entre productos propios y competencia

**Solución:**
```bash
# Verificar colección en Qdrant
curl http://localhost:6333/collections/product_embeddings

# Verificar conteo de puntos
curl -X POST http://localhost:6333/collections/product_embeddings/points/count -H "Content-Type: application/json" -d '{}'

# Si está vacío, regenerar embeddings
# Ejecutar task del DAG o manualmente:
python -c "
import pandas as pd
from src.ingestion.db_utils import get_engine
from src.matching.embeddings import generate_and_index_embeddings
engine = get_engine()
df = pd.read_sql('SELECT product_id, name_original AS name, category FROM silver.stg_products', engine)
generate_and_index_embeddings(df, source='own', name_col='name', product_id_col='product_id', category_col='category')
"
```

### Problema: Dashboard muestra "No hay datos disponibles"

**Síntomas:** Streamlit muestra error de conexión o DataFrame vacío.

**Causas posibles:**
1. Pipeline no se ejecutó aún
2. PostgreSQL no accesible desde el contenedor de dashboard

**Solución:**
```bash
# Verificar que las tablas gold existen
docker exec pricing_postgres psql -U pricing_user -d dynamic_pricing -c "SELECT COUNT(*) FROM gold.pricing_recommendations;"

# Si es 0, ejecutar pipeline
docker exec pricing_airflow_scheduler airflow dags trigger dynamic_pricing_pipeline

# Verificar conectividad desde dashboard
docker exec pricing_dashboard python -c "from src.ingestion.db_utils import get_engine; e=get_engine(); print(e.connect())"
```

### Problema: Tests unitarios fallan

**Síntomas:** `pytest tests/test_pricing_engine.py` reporta errores.

**Causas posibles:**
1. PYTHONPATH no incluye la raíz del proyecto
2. Dependencias faltantes
3. Cambios en el código que rompen tests

**Solución:**
```bash
# Ejecutar desde raíz del proyecto
cd dynamic-pricing-de
export PYTHONPATH=$(pwd)
pytest tests/test_pricing_engine.py -v

# Si falla por imports, instalar dependencias
pip install -r requirements.txt

# Si un test específico falla, ejecutar solo ese test con verbose
pytest tests/test_pricing_engine.py::test_price_never_below_minimum_margin -v --tb=long
```

## Monitoreo y Alertas

### Verificar salud del sistema completo

```bash
chmod +x scripts/verify_setup.sh
./scripts/verify_setup.sh
```

### Métricas manuales de salud

```bash
# 1. Pipeline ejecutó en última hora?
docker exec pricing_postgres psql -U pricing_user -d dynamic_pricing -c   "SELECT MAX(computed_at) FROM gold.pricing_recommendations;"

# 2. Cobertura de matching
 docker exec pricing_postgres psql -U pricing_user -d dynamic_pricing -c   "SELECT COUNT(DISTINCT own_product_id)::float / (SELECT COUNT(*) FROM silver.stg_products) * 100 AS coverage_pct FROM silver.product_matches;"

# 3. Productos sin stock
 docker exec pricing_postgres psql -U pricing_user -d dynamic_pricing -c   "SELECT COUNT(*) FROM gold.fct_pricing_signals WHERE stock_status = 'out_of_stock';"

# 4. Recomendaciones por acción
 docker exec pricing_postgres psql -U pricing_user -d dynamic_pricing -c   "SELECT action, COUNT(*) FROM gold.pricing_recommendations GROUP BY action;"
```

## Mantenimiento

### Limpiar datos antiguos

```bash
# Truncar tablas bronze (conservar silver/gold)
docker exec pricing_postgres psql -U pricing_user -d dynamic_pricing -c   "TRUNCATE TABLE bronze.raw_products, bronze.raw_competitors, bronze.raw_inventory;"

# Regenerar todo desde cero
python scripts/generate_datasets.py
python -m src.ingestion.ingest_catalog
python -m src.ingestion.ingest_competitors
python -m src.ingestion.ingest_inventory
cd dbt && dbt run && dbt test
```

### Backup de la base de datos

```bash
# Backup
docker exec pricing_postgres pg_dump -U pricing_user -d dynamic_pricing > backup_$(date +%Y%m%d).sql

# Restore
cat backup_20240101.sql | docker exec -i pricing_postgres psql -U pricing_user -d dynamic_pricing
```

### Actualizar dependencias

```bash
# Actualizar requirements.txt
pip freeze > requirements.txt

# Reconstruir imágenes
docker-compose down
docker-compose up -d --build
```
