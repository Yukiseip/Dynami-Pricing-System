# 📘 Manual de Uso: Dynamic Pricing System

Bienvenido al **Manual de Uso** del Sistema de Pricing Dinámico. Este documento está diseñado para explicar detalladamente qué hace el proyecto, cómo funciona internamente y cuáles son los pasos exactos para operarlo, visualizar los resultados y entender sus recomendaciones.

---

## 1. 🎯 ¿Qué hace realmente este proyecto?

El **Dynamic Pricing System** es una plataforma automatizada diseñada para e-commerce. Su objetivo principal es **calcular y ajustar los precios de tus productos de forma automática** basándose en tres factores clave:

1.  **La Competencia:** Observa a qué precio están vendiendo productos similares tus competidores.
2.  **Tu Inventario (Stock):** Analiza si tienes exceso de mercancía (overstock) o si estás a punto de quedarte sin existencias (critical low).
3.  **La Demanda (Velocidad de ventas):** Mide qué tanto interés hay en un producto basándose en cuántas visitas se convierten en ventas reales.

A diferencia de un sistema de "caja negra", este motor aplica reglas de negocio claras (explicadas más abajo) y asegura que **nunca vendas por debajo de tu margen de ganancia mínimo**.

---

## 2. 🏗️ ¿Cómo funciona internamente? (El Flujo)

El sistema opera de forma secuencial y cíclica (orquestado para ejecutarse cada hora). El flujo de vida de los datos es el siguiente:

1.  **Ingesta de Datos:** El sistema recopila la información cruda (tu catálogo, el inventario actual y los precios raspados de competidores) y los almacena en la base de datos PostgreSQL (Capa Bronze).
2.  **Limpieza y Transformación (dbt):** Los datos crudos se limpian, se normalizan y se cruzan entre sí (Capa Silver y Gold) para tenerlos listos para el análisis.
3.  **Inteligencia Artificial (Matching):** Un modelo de Procesamiento de Lenguaje Natural lee las descripciones de tus productos y las de la competencia. Las convierte en vectores (números) y usa una base de datos vectorial (**Qdrant**) para identificar qué producto del competidor es exactamente igual al tuyo, aunque se llamen ligeramente distinto.
4.  **Cálculo de Precios (Motor):** Con el cruce hecho, el motor aplica las reglas matemáticas (ej. "bajar 5% el precio si hay mucho stock").
5.  **Exposición:** Los precios finales calculados se envían a una **API (FastAPI)** para que tu tienda online los consuma, y a un **Dashboard (Streamlit)** para que los analistas los revisen.

---

## 3. 🚀 Guía de Operación Paso a Paso

A continuación, se detalla cómo operar el sistema asumiendo que ya has realizado la instalación base con Docker.

### Paso 1: Iniciar la Infraestructura
Asegúrate de que todos los servicios (Bases de datos, Airflow, API y Dashboard) estén corriendo.
Abre tu terminal y ejecuta:
```bash
docker-compose up -d
```
Verifica que los servicios estén sanos:
```bash
docker-compose ps
```

### Paso 2: Generar e Ingestar Datos
Si es la primera vez que lo corres o deseas simular un nuevo día de ventas, necesitas generar datos sintéticos e ingestarlos.

```bash
# 1. Generar datos ficticios (Simula el catálogo y la competencia)
python scripts/generate_datasets.py --n-products 1000

# 2. Subir los datos crudos a la Base de Datos
python -m src.ingestion.ingest_catalog
python -m src.ingestion.ingest_competitors
python -m src.ingestion.ingest_inventory
```

### Paso 3: Ejecutar el Pipeline en Airflow (El "Cerebro")
Airflow es el encargado de hacer que todo el proceso ocurra de manera ordenada.
1. Abre tu navegador y ve a: **http://localhost:8080**
2. Inicia sesión con las credenciales por defecto (`User: admin`, `Pass: admin`).
3. En la lista de DAGs, busca el llamado `dynamic_pricing_pipeline`.
4. Este es el pipeline maestro. Puedes esperar a que se ejecute en su hora programada o forzar su ejecución manual haciendo clic en el botón **"Trigger DAG"** (el ícono de 'Play').
5. Podrás ver en tiempo real cómo los bloques cambian a verde:
   `Ingesta -> dbt_transformations -> NLP Matching -> Pricing Engine`.

### Paso 4: Visualizar los Resultados (Dashboard para Analistas)
Una vez que Airflow termine exitosamente, el motor ya habrá calculado los nuevos precios.
1. Abre tu navegador y ve a: **http://localhost:8501**
2. Se abrirá la interfaz de **Streamlit**.
3. En este panel interactivo podrás:
   - Ver los productos a los que se les subió, bajó o mantuvo el precio.
   - Revisar el "Razonamiento" (*Reasoning*). Por ejemplo, el sistema te dirá textualmente: *"Se redujo el precio 5% por exceso de inventario"*.
   - Filtrar productos por categoría.

### Paso 5: Consumir los Precios (API para Desarrolladores)
Si tu tienda online necesita consultar el precio de un artículo específico en tiempo real, debe conectarse a la API.
1. Ve a **http://localhost:8000/docs** para ver la documentación interactiva de la API.
2. Puedes probar el endpoint `GET /pricing/suggestion/{product_id}` introduciendo el código de un producto (ej. `SKU-001`).
3. La API te responderá con un JSON detallando el precio actual, el sugerido, y el motivo del cambio.

---

## 4. 🧠 ¿Cómo toma decisiones el sistema? (Reglas de Negocio)

Para que confíes en las recomendaciones, es vital entender cómo decide el sistema. Nunca funciona al azar; se basa en 4 reglas estrictas:

1. **La Regla de Oro (Floor de Rentabilidad):**
   * *Regla:* El sistema suma el costo base del producto + un 10% de margen mínimo.
   * *Resultado:* El precio sugerido **nunca** podrá bajar de esa cifra. Jamás venderás a pérdida.
2. **Reacción a la Competencia:**
   * *Regla:* El sistema identifica al competidor más barato (y que sea confiable). Tratará de colocar tu precio `$1.00` por debajo de él, siempre y cuando no rompa la Regla de Oro.
3. **Ajuste por Velocidad de Demanda:**
   * *Regla:* Si el sistema detecta que el producto se vende muy rápido (alta conversión), se permite el lujo de **subir el precio** (hasta un 10%) para maximizar ganancias. Si no se vende nada, puede bajarlo (hasta un 5%) para estimular la compra.
4. **Ajuste por Inventario (Stock):**
   * *Regla:* Si tienes más de 400 unidades acumuladas en bodega, baja el precio un 5% para vaciar almacén. Si te quedan menos de 20 unidades, sube el precio un 3% para rentabilizar las últimas piezas y evitar quedarte en ceros (*out of stock*).

---

## 5. ⚠️ Solución de Problemas Comunes (Troubleshooting)

* **¿No aparecen precios en el Dashboard?**
  Asegúrate de que el DAG en Airflow haya terminado en color verde (Success). Si está rojo, revisa el log de la tarea fallida haciendo clic sobre ella.
* **¿Error de conexión a la Base de Datos al ejecutar scripts?**
  Asegúrate de que el contenedor de PostgreSQL esté activo ejecutando `docker-compose ps`.
* **¿Los productos no hacen "Match" con los competidores?**
  Revisa el contenedor de Qdrant. Si la inteligencia artificial no encuentra un match exacto con un nivel de confianza alto (Similarity Threshold > 0.85), asumirá que el producto no tiene competencia directa y fijará el precio basándose solo en tus costos.
