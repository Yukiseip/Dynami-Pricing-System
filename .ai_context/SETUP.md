# Setup Guide: Dynamic Pricing System

> Guía paso a paso para instalar, configurar y ejecutar el sistema por primera vez. Diseñada para desarrolladores y para que una IA pueda guiar a usuarios sin ambigüedades.

## Requisitos Previos

### Hardware
- **RAM:** Mínimo 6GB libres (8GB recomendado)
- **Disco:** 10GB libres
- **CPU:** 2 cores mínimo (4 recomendado)

### Software
- **Docker:** 24.0.0 o superior
- **Docker Compose:** 2.20.0 o superior
- **Git:** 2.30 o superior
- **Python:** 3.11 (solo para desarrollo local sin Docker)
- **curl:** Para verificar endpoints

### Verificar prerequisitos

```bash
docker --version        # Debe mostrar 24.x o superior
docker-compose --version # Debe mostrar 2.20 o superior
git --version           # Debe mostrar 2.30 o superior
python3 --version       # Debe mostrar 3.11.x
```

## Instalación Paso a Paso

### Paso 1: Clonar el repositorio

```bash
git clone https://github.com/tuusuario/dynamic-pricing-de.git
cd dynamic-pricing-de
```

### Paso 2: Configurar variables de entorno

```bash
# Copiar archivo de ejemplo
cp .env.example .env
```

El archivo `.env` ya contiene valores por defecto para desarrollo local. **No modificar** a menos que:
- Tengas conflictos de puertos (5432, 6333, 8080, 8000, 8501, 9000, 9001)
- Necesites passwords más seguros para demo pública

**Puertos utilizados:**
| Puerto | Servicio | Descripción |
|--------|----------|-------------|
| 5432 | PostgreSQL | Base de datos principal |
| 6333 | Qdrant | Vector DB REST API |
| 6334 | Qdrant | Vector DB gRPC |
| 8080 | Airflow | Web UI |
| 8000 | FastAPI | API REST |
| 8501 | Streamlit | Dashboard |
| 9000 | MinIO | API S3-compatible |
| 9001 | MinIO | Consola web |

### Paso 3: Crear estructura de datos

```bash
# Crear directorios necesarios (si no existen)
mkdir -p data/raw data/processed
mkdir -p airflow/logs
```

### Paso 4: Levantar infraestructura base

```bash
# Levantar PostgreSQL, Qdrant y MinIO primero
docker-compose up -d postgres qdrant minio

# Verificar que están healthy (esperar ~30 segundos)
docker-compose ps
```

Deberías ver:
```
NAME                    STATUS
pricing_postgres        Up 10 seconds (healthy)
pricing_qdrant          Up 10 seconds (healthy)
pricing_minio           Up 10 seconds (healthy)
```

**Si alguno muestra `restarting` o `unhealthy`:**
```bash
# Ver logs para diagnosticar
docker-compose logs postgres
docker-compose logs qdrant

# Problema común: puerto ocupado
# Solución: Modificar el puerto en docker-compose.yml y .env
```

### Paso 5: Verificar conexiones

```bash
# PostgreSQL
docker exec pricing_postgres pg_isready -U pricing_user -d dynamic_pricing
# Debe responder: accepting connections

# Qdrant
curl -s http://localhost:6333/healthz
# Debe responder: {"status":"ok"}

# MinIO
curl -s http://localhost:9000/minio/health/live
# Debe responder: nada (HTTP 200) o error si no está listo aún
```

### Paso 6: Inicializar Airflow

```bash
# El servicio airflow-init se ejecuta automáticamente al hacer up
docker-compose up -d airflow-init

# Verificar que completó exitosamente
docker-compose logs airflow-init
# Debe mostrar: "Airflow initialized successfully"
```

**Si falla:**
```bash
# Limpiar y reintentar
docker-compose down
docker volume rm dynamic-pricing-de_postgres_data  # opcional, borra datos
docker-compose up -d airflow-init
```

### Paso 7: Levantar servicios de aplicación

```bash
# Levantar webserver, scheduler, API y dashboard
docker-compose up -d airflow-webserver airflow-scheduler api dashboard

# Verificar todos los servicios
docker-compose ps
```

Deberías ver 7 servicios en estado `Up`:
- pricing_postgres
- pricing_qdrant
- pricing_minio
- pricing_airflow_init (completed)
- pricing_airflow_webserver
- pricing_airflow_scheduler
- pricing_api
- pricing_dashboard

### Paso 8: Generar datos sintéticos

```bash
# Instalar dependencias localmente (solo para scripts)
pip install pandas numpy faker

# Generar datasets
python scripts/generate_datasets.py --n-products 1000 --seed 42

# Verificar archivos generados
ls -la data/raw/
# Debe mostrar: catalog.csv, competitors.csv, inventory_demand.csv
```

### Paso 9: Ejecutar pipeline inicial

```bash
# Opción A: Disparar DAG maestro desde Airflow
docker exec pricing_airflow_scheduler airflow dags trigger dynamic_pricing_pipeline

# Opción B: Ejecutar pasos manualmente (para entender el flujo)

# 9.1 Ingesta
python -m src.ingestion.ingest_catalog
python -m src.ingestion.ingest_competitors
python -m src.ingestion.ingest_inventory

# 9.2 dbt (requiere dbt instalado)
cd dbt
dbt run
dbt test
cd ..

# 9.3 Matching
python -c "
import pandas as pd
from src.ingestion.db_utils import get_engine
from src.matching.embeddings import generate_and_index_embeddings
engine = get_engine()

# Embeddings propios
df_own = pd.read_sql('SELECT product_id, name_original AS name, category FROM silver.stg_products', engine)
generate_and_index_embeddings(df_own, source='own', name_col='name', product_id_col='product_id', category_col='category')

# Embeddings competencia
df_comp = pd.read_sql('SELECT CONCAT(competitor_id, "_", ROW_NUMBER() OVER()) AS id, product_name_competitor AS name, category, competitor_price, competitor_id FROM silver.stg_competitor_prices', engine)
generate_and_index_embeddings(df_comp, source='competitor', name_col='name', product_id_col='id', price_col='competitor_price', category_col='category')
"

# 9.4 Matching
python -c "from src.matching.matcher import run_matching_pipeline; run_matching_pipeline()"

# 9.5 Pricing
python -c "from src.pricing.engine import run_pricing_pipeline; run_pricing_pipeline()"
```

### Paso 10: Verificar que todo funciona

```bash
# 10.1 Verificar tablas en PostgreSQL
docker exec pricing_postgres psql -U pricing_user -d dynamic_pricing -c   "SELECT 'bronze.raw_products' as tabla, COUNT(*) as filas FROM bronze.raw_products UNION ALL
   SELECT 'silver.stg_products', COUNT(*) FROM silver.stg_products UNION ALL
   SELECT 'gold.fct_pricing_signals', COUNT(*) FROM gold.fct_pricing_signals UNION ALL
   SELECT 'gold.pricing_recommendations', COUNT(*) FROM gold.pricing_recommendations;"

# Debe mostrar ~1000 filas en cada tabla

# 10.2 Verificar API
curl -s http://localhost:8000/health | python -m json.tool

# 10.3 Verificar sugerencia de precio
curl -s http://localhost:8000/pricing/suggestion/SKU-00001 | python -m json.tool

# 10.4 Verificar Airflow UI
# Abrir navegador en http://localhost:8080
# Login: admin / admin
# Debe mostrar el DAG "dynamic_pricing_pipeline" en verde

# 10.5 Verificar Dashboard
# Abrir navegador en http://localhost:8501
# Debe mostrar KPIs y gráficos
```

## Configuración de Desarrollo (sin Docker)

> **Nota:** Solo recomendado para modificar código fuente. Para ejecutar el sistema completo, usar Docker.

### Instalar dependencias Python

```bash
# Crear virtual environment
python3.11 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# o: .venv\Scripts\activate  # Windows

# Instalar dependencias
pip install -r requirements.txt

# Instalar dbt
pip install dbt-core dbt-postgres

# Verificar instalación
python -c "import fastapi, qdrant_client, sentence_transformers, streamlit; print('OK')"
```

### Configurar PostgreSQL local

```bash
# Si tienes PostgreSQL instalado localmente
createdb dynamic_pricing
createuser pricing_user
psql -c "ALTER USER pricing_user WITH PASSWORD 'pricing_pass_dev_2024';"
psql -c "GRANT ALL PRIVILEGES ON DATABASE dynamic_pricing TO pricing_user;"
```

### Configurar Qdrant local

```bash
# Opción 1: Docker solo para Qdrant
docker run -p 6333:6333 -v qdrant_data:/qdrant/storage qdrant/qdrant:latest

# Opción 2: Instalar binario (Linux)
# Descargar desde https://github.com/qdrant/qdrant/releases
```

### Ejecutar tests

```bash
export PYTHONPATH=$(pwd)
pytest tests/test_pricing_engine.py -v
```

### Ejecutar API en modo desarrollo

```bash
export PYTHONPATH=$(pwd)
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

### Ejecutar Dashboard en modo desarrollo

```bash
export PYTHONPATH=$(pwd)
streamlit run dashboard/app.py --server.port=8501
```

## Solución de Problemas de Instalación

### Error: "port is already allocated"

```bash
# Encontrar proceso que usa el puerto
sudo lsof -i :5432  # PostgreSQL
sudo lsof -i :8080  # Airflow

# Matar proceso o cambiar puerto en docker-compose.yml
# Ejemplo: cambiar "5432:5432" por "5433:5432"
```

### Error: "no space left on device"

```bash
# Limpiar imágenes y volúmenes Docker no utilizados
docker system prune -a
docker volume prune

# Verificar espacio en disco
df -h
```

### Error: "airflow-init exited with code 1"

```bash
# Verificar que PostgreSQL está listo
docker-compose logs postgres

# Si PostgreSQL está reiniciando, esperar 30 segundos y reintentar
docker-compose up -d airflow-init

# Si persiste, limpiar volúmenes
docker-compose down -v
docker-compose up -d
```

### Error: "ModuleNotFoundError: No module named 'src'"

```bash
# Asegurar que PYTHONPATH incluye la raíz del proyecto
export PYTHONPATH=$(pwd)

# Verificar estructura
ls src/__init__.py  # Debe existir
```

### Error: "dbt profile not found"

```bash
# dbt busca profiles.yml en ~/.dbt/ por defecto
# Crear symlink o especificar --profiles-dir
cd dbt
dbt run --profiles-dir .
```

## Verificación Post-Instalación

Ejecuta el script de verificación para confirmar que todo está operativo:

```bash
chmod +x scripts/verify_setup.sh
./scripts/verify_setup.sh
```

**Resultado esperado:**
```
==========================================
  DYNAMIC PRICING - VERIFICACIÓN FINAL
==========================================

🐳 SERVICIOS DOCKER
✅ PostgreSQL running
✅ Qdrant running
✅ MinIO running
✅ Airflow webserver running
✅ API running
✅ Dashboard running

🌐 ENDPOINTS
✅ API health
✅ API docs
✅ Airflow UI
✅ Qdrant healthz

🗄️  BASE DE DATOS
✅ bronze.raw_products existe
✅ silver.stg_products existe
✅ gold.fct_pricing_signals existe
✅ gold.pricing_recommendations existe

🧪 TESTS
✅ Unit tests pasan

==========================================
  RESULTADO: 16 pasados, 0 fallidos
==========================================
  🎉 Sistema listo para demo!
```

## Próximos Pasos

1. **Explorar la API:** Visita `http://localhost:8000/docs` para ver la documentación interactiva
2. **Revisar el Dashboard:** Abre `http://localhost:8501` y filtra por categorías
3. **Monitorear Airflow:** En `http://localhost:8080` puedes ver el DAG ejecutándose cada hora
4. **Modificar reglas de pricing:** Edita `config/pricing_config.yaml` y reinicia la API
5. **Agregar tests:** Extinde `tests/test_pricing_engine.py` con nuevos casos de edge

## Desinstalación

```bash
# Detener todos los servicios
docker-compose down

# Eliminar volúmenes (borra todos los datos)
docker-compose down -v

# Eliminar imágenes construidas localmente
docker image rm dynamic-pricing-de_api

# Opcional: limpiar todo Docker
docker system prune -a --volumes
```
