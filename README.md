# 💰 Dynamic Pricing System for E-commerce

> Sistema de pricing dinámico end-to-end para e-commerce.
> Ajusta precios automáticamente cada hora basándose en datos de la competencia, niveles de inventario y demanda en tiempo real.

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109-green?logo=fastapi)
![Airflow](https://img.shields.io/badge/Airflow-2.8.1-red?logo=apacheairflow)
![dbt](https://img.shields.io/badge/dbt-1.7.4-orange?logo=dbt)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue?logo=postgresql)
![Qdrant](https://img.shields.io/badge/Qdrant-1.7-purple)

---

**🛠️ System Preview:**

<div align="center">
  <table border="0">
    <tr>
      <td><img src="Captura de pantalla 2026-04-22 013005.png" width="100%" alt="Airflow"></td>
      <td><img src="Captura de pantalla 2026-04-22 013014.png" width="100%" alt="Dashboard"></td>
    </tr>
    <tr>
      <td><img src="Captura de pantalla 2026-04-22 013346.png" width="100%" alt="Dashborad2"></td>
      <td><img src="Captura de pantalla 2026-04-22 013356.png" width="100%" alt="Metricas"></td>
    </tr>
  </table>
</div>

## 📖 ¿Qué hace este proyecto?

Este proyecto es una solución integral (End-to-End) de Data Engineering y Machine Learning diseñada para resolver el problema de la fijación de precios en e-commerce. 
En un mercado competitivo, los precios deben reaccionar rápidamente a los movimientos de la competencia, evitando al mismo tiempo pérdidas por falta de margen o por exceso/falta de stock.

**Principales características:**
- **Monitoreo automatizado:** Recopila datos de catálogo propio, inventario, demanda y precios de competidores.
- **Matching Inteligente:** Utiliza Modelos de Procesamiento de Lenguaje Natural (NLP) y Bases de Datos Vectoriales para relacionar automáticamente los productos propios con los de la competencia, incluso si tienen nombres distintos.
- **Motor Explicable:** Calcula el precio óptimo basado en reglas de negocio claras (costos, márgenes mínimos, stock y velocidad de ventas), sin ser una "caja negra".
- **Orquestación robusta:** Todo el proceso se ejecuta de manera automatizada y programada mediante un pipeline de datos robusto.

---

## ⚙️ ¿Cómo funciona? (Arquitectura y Flujo)

El sistema opera bajo un pipeline automatizado de 6 pasos (orquestado por Airflow cada hora):

```text
┌─────────────────────────────────────────────────────────────────┐
│                    Dynamic Pricing Pipeline                     │
│                     (Airflow - cada hora)                       │
│                                                                 │
│  [CSV/API] → [Bronze] → [Silver] → [Gold] → [API/Dashboard]     │
│               dbt raw    dbt stg    dbt fct   FastAPI/Streamlit │
└─────────────────────────────────────────────────────────────────┘
```

1. **Ingesta de Datos:** Scripts en Python leen datos crudos (catálogo, competidores, inventario) y los insertan en el esquema `Bronze` de PostgreSQL.
2. **Data Quality:** Validaciones para asegurar que no existan datos corruptos (ej. precios negativos) antes de procesar.
3. **Transformación (dbt):** Se aplica la arquitectura Medallion. 
   - *Bronze* a *Silver*: Limpieza, normalización y deduplicación.
   - *Silver* a *Gold*: Agregación y cálculo de métricas de negocio (ej. `fct_pricing_signals`).
4. **Generación de Embeddings:** Se transforman los nombres de los productos (propios y de competidores) en vectores matemáticos usando un modelo de lenguaje, guardándolos en **Qdrant**.
5. **Product Matching:** Se busca similitud vectorial (Cosine Similarity) para identificar automáticamente qué producto de la competencia equivale a nuestro producto.
6. **Pricing Engine:** Con los datos de la competencia (gracias al match) y nuestros datos de stock/demanda, el motor calcula el precio sugerido y lo guarda en la base de datos para ser consumido por la API.

---

## 🛠️ ¿Qué se usó y para qué? (Stack Tecnológico)

El stack fue seleccionado para simular un entorno productivo moderno y escalable:

| Tecnología | Propósito en el Proyecto |
|------------|---------------------------|
| **Apache Airflow (2.8.1)** | **Orquestación.** Define y programa el DAG (Directed Acyclic Graph) que ejecuta todo el pipeline E2E, controlando dependencias, reintentos (retries) y SLAs. |
| **dbt (Data Build Tool)** | **Transformación de datos.** Gestiona los modelos SQL para pasar los datos de crudos (Bronze) a limpios (Silver) y listos para negocio (Gold). Incluye testing integrado. |
| **PostgreSQL (15)** | **Data Warehouse / RDBMS.** Almacena las capas Medallion y los resultados finales. Permite transacciones ACID y consultas analíticas. |
| **Sentence-Transformers (MiniLM)** | **NLP / Machine Learning.** Modelo ligero (`all-MiniLM-L6-v2`) que convierte descripciones de productos en embeddings para el motor de similitud. |
| **Qdrant** | **Base de Datos Vectorial.** Almacena los embeddings y realiza búsquedas de similitud ultrarrápidas (Approximate Nearest Neighbors) para hacer el matching de productos. |
| **FastAPI** | **Consumo (API REST).** Expone los precios sugeridos y el estado del sistema mediante endpoints asíncronos y de alto rendimiento. |
| **Streamlit** | **Consumo (Dashboard).** Interfaz de usuario interactiva para que los analistas revisen los ajustes de precio y las métricas del pipeline. |
| **Docker & Docker Compose** | **Contenerización.** Empaqueta todos los servicios (DBs, Airflow, API, Dashboard) para que el entorno sea reproducible en cualquier máquina. |
| **Terraform** | **Infraestructura como Código (IaC).** Define la infraestructura cloud (AWS: VPC, EC2, RDS) requerida para un eventual pase a producción. |

---

## 🧠 Profundizando en el Pricing Engine

El motor de pricing está diseñado para ser determinista y auditable (no es una "caja negra"). 

**Fórmula principal:**
```python
Precio Base = max(
    costo × (1 + margen_mínimo),            # Nunca perder dinero (Floor de rentabilidad)
    (min_precio_competencia - $1.00)        # Ser ligeramente más barato que la competencia
)

Precio Final = Precio Base × (1 + ajuste_demanda + ajuste_stock)
```

**Reglas de Ajuste:**
- **Demanda:** 
  - Alta (velocity > 0.15): Incrementa precio (+0% a +10%).
  - Baja (velocity < 0.05): Disminuye precio (hasta -5%) para estimular ventas.
- **Inventario:**
  - Crítico (< 20 unds): Incrementa precio (+3%) para evitar quiebre de stock.
  - Overstock (≥ 400 unds): Disminuye precio (-5%) para liberar almacén.
  - Sin stock (0 unds): Mantiene el último precio (protección).

---

## 📐 Estructura del Repositorio

El proyecto está modularizado de la siguiente manera:

```text
dynamic-pricing-de/
├── airflow/            # DAGs de orquestación (pipeline principal)
├── config/             # Archivos YAML de configuración (parámetros de pricing)
├── dashboard/          # Interfaz de Streamlit
├── data/               # Archivos CSV crudos
├── dbt/                # Modelos y tests de transformación SQL (Bronze/Silver/Gold)
├── docker/             # Dockerfiles e inicialización de BDs
├── scripts/            # Generación de datos sintéticos
├── src/                # Código fuente en Python
│   ├── api/            # Endpoints FastAPI
│   ├── ingestion/      # Conexión DB y carga inicial
│   ├── matching/       # Lógica NLP y Qdrant Vector DB
│   └── pricing/        # Motor de cálculo de precios
├── terraform/          # Despliegue AWS
└── tests/              # Pruebas unitarias con Pytest
```

---

## 🚀 Ejecución Local (Quick Start)

### Requisitos Previos
- Docker Desktop (con WSL 2 en Windows)
- Python 3.11
- Mínimo 8 GB RAM disponibles

### Pasos para iniciar:

**1. Clonar y configurar entorno:**
```bash
git clone <repo>
cd dynamic-pricing-de
cp .env.example .env
# Opcional: Ajustar credenciales en el archivo .env
```

**2. Iniciar Servicios Base (Bases de datos):**
```bash
docker-compose up -d postgres qdrant minio
# Verificar que están 'healthy'
docker-compose ps
```

**3. Generar e Ingestar Datos (Entorno Local Python):**
```bash
pip install -r requirements.txt
# Generar CSVs sintéticos
python scripts/generate_datasets.py --n-products 1000

# Ingestar a PostgreSQL (Capa Bronze)
python -m src.ingestion.ingest_catalog
python -m src.ingestion.ingest_competitors
python -m src.ingestion.ingest_inventory
```

**4. Ejecutar Transformaciones dbt:**
```bash
cd dbt
dbt run
dbt test
cd ..
```

**5. Levantar el resto de servicios (Airflow, API, Dashboard):**
```bash
docker-compose up -d

# Servicios disponibles en:
# - Airflow (Orquestador): http://localhost:8080  (User: admin / Pass: admin)
# - API FastAPI (Docs): http://localhost:8000/docs
# - Streamlit Dashboard: http://localhost:8501
```

---

## 📡 API Endpoints

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/health` | Estado del sistema |
| GET | `/pricing/suggestion/{product_id}` | Precio sugerido individual |
| GET | `/pricing/batch?category=Audio&action=decrease` | Consulta masiva con filtros |
| GET | `/matches/pending` | Matches pendientes de revisión |

---

## 🧪 Testing

El proyecto incluye una suite de pruebas para asegurar que el motor de precios aplique correctamente todas las reglas matemáticas y lógicas (precio mínimo, reglas de stock/demanda, etc.).

```bash
pytest tests/ -v --tb=short
```

---

## ☁️ Infraestructura AWS (Terraform)

El proyecto incluye la infraestructura como código para desplegar la base de datos y la instancia principal en AWS.

```bash
cd terraform
terraform init
terraform plan -var="db_password=super_secret_password"
terraform apply
```
*Infraestructura provisionada: VPC, EC2 (t3.medium) para Airflow/API, RDS PostgreSQL (db.t3.micro), Security Groups.*
