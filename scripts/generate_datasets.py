"""
generate_datasets.py
====================
Genera automáticamente todos los datasets necesarios para el sistema de Dynamic Pricing.
Produce: catalog.csv, competitors.csv, inventory_demand.csv

Uso:
    python scripts/generate_datasets.py
    python scripts/generate_datasets.py --output-dir data/raw --seed 42 --n-products 1000

Notas:
    - Reproducible con --seed fijo
    - No requiere dataset externo (100% sintético pero realista)
    - Usa distribuciones de precio reales del mercado de electrónica
"""

import argparse
import random
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

fake = Faker(["en_US"])


# ============================================================
# CONFIGURACIÓN DE CATEGORÍAS Y DISTRIBUCIONES
# ============================================================

CATEGORIES = {
    "Accessories": {
        "weight": 0.40,
        "price_range": (10, 100),
        "examples": [
            "USB-C Cable {brand} {model}",
            "Wireless Mouse {brand}",
            "Mechanical Keyboard {brand} {model}",
            "HDMI Cable {spec} {length}m",
            "Phone Case {brand} {model}",
            "Screen Protector {brand}",
            "Webcam {brand} {resolution}p",
            "USB Hub {brand} {ports}-Port",
            "Laptop Stand {brand}",
            "Cable Management Kit {brand}",
        ],
    },
    "Audio": {
        "weight": 0.30,
        "price_range": (50, 400),
        "examples": [
            "Wireless Headphones {brand} {model}",
            "True Wireless Earbuds {brand} {model}",
            "Bluetooth Speaker {brand} {model}",
            "Noise Canceling Headset {brand}",
            "Studio Monitor {brand} {size}-inch",
            "Soundbar {brand} {watts}W",
            "Gaming Headset {brand} {model}",
        ],
    },
    "Tablets": {
        "weight": 0.15,
        "price_range": (200, 1200),
        "examples": [
            "Tablet {brand} {model} {storage}GB",
            "Android Tablet {brand} {screen}-inch",
            "Drawing Tablet {brand} {model}",
            "E-Reader {brand} {model} {storage}GB",
        ],
    },
    "Laptops": {
        "weight": 0.10,
        "price_range": (500, 2500),
        "examples": [
            "Laptop {brand} {model} {ram}GB RAM {storage}GB SSD",
            "Gaming Laptop {brand} {model} {gpu}",
            "Ultrabook {brand} {model} {screen}-inch",
            "Chromebook {brand} {model}",
        ],
    },
    "Smart Home": {
        "weight": 0.05,
        "price_range": (30, 300),
        "examples": [
            "Smart Bulb {brand} {watts}W",
            "Smart Plug {brand} {model}",
            "Security Camera {brand} {resolution}p",
            "Smart Doorbell {brand} {model}",
        ],
    },
}

BRANDS = [
    "Logitech", "Anker", "Belkin", "JBL", "Sony", "Samsung", "LG", "Asus",
    "Dell", "HP", "Lenovo", "Acer", "Razer", "SteelSeries", "HyperX",
    "Corsair", "Jabra", "Bose", "Sennheiser", "AudioTechnica", "Plantronics",
    "Philips", "TP-Link", "Netgear", "Western Digital", "Seagate", "Crucial",
    "Kingston", "Sandisk", "Elgato", "Rode", "Blue", "Focusrite",
]

MODELS = [
    "Pro", "Elite", "Ultra", "Max", "Plus", "X", "S", "Mini", "Lite",
    "Air", "Neo", "One", "Go", "Flex", "Edge", "Prime", "Core", "Boost",
    "V2", "V3", "Gen2", "Gen3", "2023", "2024", "SE", "HD",
]

COMPETITOR_NAMES = [
    "TechZone", "ElectroMart", "GadgetHub", "DigiStore", "ByteShop",
    "CircuitCity", "VoltMarket", "PixelPro", "NanoTech", "MegaBytes",
]

COMPETITOR_AGGRESSIVENESS = {
    "TechZone": "medium",
    "ElectroMart": "low",
    "GadgetHub": "high",
    "DigiStore": "medium",
    "ByteShop": "high",
    "CircuitCity": "low",
    "VoltMarket": "medium",
    "PixelPro": "low",
    "NanoTech": "high",
    "MegaBytes": "medium",
}


# ============================================================
# GENERADORES DE NOMBRES
# ============================================================

def generate_product_name(category: str, rng: np.random.Generator) -> str:
    """Genera nombre de producto realista para una categoría dada."""
    template = rng.choice(CATEGORIES[category]["examples"])
    brand = rng.choice(BRANDS)
    model = rng.choice(MODELS)

    replacements = {
        "{brand}": brand,
        "{model}": model,
        "{spec}": rng.choice(["4K", "8K", "FHD", "QHD"]),
        "{length}": str(rng.choice([1, 2, 3, 5])),
        "{resolution}": str(rng.choice([720, 1080, 1440, 4096])),
        "{ports}": str(rng.choice([4, 7, 10, 13])),
        "{size}": str(rng.choice([5, 6, 8])),
        "{screen}": str(rng.choice([11, 13, 14, 15, 16, 17])),
        "{watts}": str(rng.choice([9, 13, 18, 25, 60, 100])),
        "{storage}": str(rng.choice([64, 128, 256, 512, 1000])),
        "{ram}": str(rng.choice([8, 16, 32, 64])),
        "{gpu}": rng.choice(["RTX 4060", "RTX 4070", "RX 7600", "Arc A770"]),
    }

    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)
    return template


def generate_competitor_product_name(original_name: str, rng: np.random.Generator) -> str:
    """
    Genera variación semántica del nombre de producto para simular
    como competidores describen el mismo producto con nombres diferentes.
    """
    words = original_name.split()
    variations = []

    for word in words:
        r = rng.random()
        if r < 0.05:  # 5%: omitir palabra poco relevante
            if word.lower() not in ["with", "and", "for", "the"]:
                variations.append(word)
        elif r < 0.10:  # 5%: abreviar
            if len(word) > 5:
                variations.append(word[:3] + ".")
            else:
                variations.append(word)
        else:  # 90%: mantener igual
            variations.append(word)

    # Ocasionalmente agregar sufijo de competidor
    if rng.random() < 0.20:
        suffixes = ["- Black", "- White", "- Silver", "(Refurbished)", "(Bundle)"]
        variations.append(rng.choice(suffixes))

    return " ".join(variations)


# ============================================================
# GENERADORES DE PRECIOS
# ============================================================

def simulate_competitor_price(
    base_price: float, aggressiveness: str, rng: np.random.Generator
) -> float:
    """Simula precio de competidor según su nivel de agresividad comercial."""
    multipliers = {
        "low": (0.95, 1.20),     # Competidor premium / menos agresivo
        "medium": (0.85, 1.10),  # Competidor promedio
        "high": (0.75, 0.95),    # Competidor agresivo en precio
    }
    low, high = multipliers.get(aggressiveness, (0.85, 1.10))
    price = base_price * rng.uniform(low, high)
    return round(price, 2)


# ============================================================
# GENERADORES DE MÉTRICAS DE DEMANDA
# ============================================================

def generate_demand_metrics(
    product_id: str,
    category: str,
    price: float,
    rng: np.random.Generator,
) -> dict:
    """
    Genera métricas de demanda realistas.
    Productos de bajo precio tienen más ventas que los de alto precio.
    """
    max_price = CATEGORIES[category]["price_range"][1]
    price_factor = 1 - (price / max_price) * 0.6  # Más caro = menos ventas

    if category in ["Laptops", "Tablets"]:
        base_daily_sales = rng.normal(3, 1) * price_factor
        base_daily_visits = rng.normal(50, 15) * price_factor
    elif category == "Audio":
        base_daily_sales = rng.normal(10, 3) * price_factor
        base_daily_visits = rng.normal(120, 30) * price_factor
    elif category == "Accessories":
        base_daily_sales = rng.normal(25, 8) * price_factor
        base_daily_visits = rng.normal(200, 50) * price_factor
    else:  # Smart Home
        base_daily_sales = rng.normal(8, 2) * price_factor
        base_daily_visits = rng.normal(80, 20) * price_factor

    sales_7d = max(0, int(base_daily_sales * 7 + rng.normal(0, 2)))
    sales_30d = max(0, int(sales_7d * 4 + rng.normal(0, 5)))
    visits_7d = max(1, int(base_daily_visits * 7 + rng.normal(0, 10)))

    velocity_score = round(sales_7d / max(visits_7d, 1), 4)

    return {
        "sales_7d": sales_7d,
        "sales_30d": sales_30d,
        "visits_7d": visits_7d,
        "velocity_score": velocity_score,
    }


# ============================================================
# GENERADOR PRINCIPAL: CATÁLOGO
# ============================================================

def generate_catalog(n_products: int, rng: np.random.Generator) -> pd.DataFrame:
    """Genera el catálogo completo de productos propios."""
    print(f"📦 Generando catálogo con {n_products} productos...")

    records = []
    category_weights = [v["weight"] for v in CATEGORIES.values()]
    category_names = list(CATEGORIES.keys())

    for i in range(n_products):
        product_id = f"SKU-{i+1:05d}"
        category = rng.choice(category_names, p=category_weights)
        name = generate_product_name(category, rng)

        price_min, price_max = CATEGORIES[category]["price_range"]
        base_price = round(float(rng.uniform(price_min, price_max)), 2)

        cost_price = round(base_price * rng.uniform(0.60, 0.85), 2)
        current_price = round(base_price * rng.uniform(0.95, 1.10), 2)

        stock = int(rng.choice(
            [rng.integers(0, 20), rng.integers(20, 100), rng.integers(100, 500)],
            p=[0.20, 0.30, 0.50],
        ))

        demand = generate_demand_metrics(product_id, category, current_price, rng)

        records.append({
            "product_id": product_id,
            "name": name,
            "category": category,
            "base_price": base_price,
            "cost_price": cost_price,
            "current_price": current_price,
            "stock": stock,
            **demand,
            "created_at": datetime.now().isoformat(),
        })

    df = pd.DataFrame(records)
    print(f"  ✅ Catálogo: {len(df)} productos en {df['category'].nunique()} categorías")
    return df


# ============================================================
# GENERADOR: COMPETENCIA
# ============================================================

def generate_competitors(catalog: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Genera datos de competencia con variaciones semánticas en nombres."""
    print("🏪 Generando datos de competencia...")

    records = []

    for _, product in catalog.iterrows():
        n_competitors = int(rng.choice([1, 2, 3], p=[0.30, 0.45, 0.25]))

        competitors_for_product = rng.choice(
            COMPETITOR_NAMES, size=n_competitors, replace=False
        )

        for competitor in competitors_for_product:
            comp_name = generate_competitor_product_name(product["name"], rng)
            aggressiveness = COMPETITOR_AGGRESSIVENESS[competitor]
            comp_price = simulate_competitor_price(
                product["base_price"], aggressiveness, rng
            )

            # Timestamp en las últimas 24 horas
            hours_ago = rng.uniform(0, 24)
            timestamp = datetime.now() - timedelta(hours=float(hours_ago))

            records.append({
                "competitor_id": competitor,
                "product_id_own": product["product_id"],
                "product_name_competitor": comp_name,
                "category": product["category"],
                "competitor_price": comp_price,
                "timestamp": timestamp.isoformat(),
                "is_confirmed_match": False,  # Pendiente de matching automático
            })

    df = pd.DataFrame(records)
    print(f"  ✅ Competencia: {len(df)} registros de {df['competitor_id'].nunique()} competidores")
    return df


# ============================================================
# GENERADOR: INVENTARIO Y DEMANDA (archivo separado para ingesta)
# ============================================================

def generate_inventory_demand(catalog: pd.DataFrame) -> pd.DataFrame:
    """
    Extrae y formatea las columnas de stock y demanda del catálogo
    en un archivo separado para simular ingesta desde sistema de inventario.
    """
    print("📊 Generando archivo de inventario y demanda...")

    df = catalog[[
        "product_id", "stock", "sales_7d", "sales_30d",
        "visits_7d", "velocity_score"
    ]].copy()
    df["updated_at"] = datetime.now().isoformat()

    print(f"  ✅ Inventario: {len(df)} registros")
    return df


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Generador de datasets para Dynamic Pricing")
    parser.add_argument("--output-dir", default="data/raw", help="Directorio de salida")
    parser.add_argument("--seed", type=int, default=42, help="Semilla aleatoria")
    parser.add_argument("--n-products", type=int, default=1000, help="Número de productos")
    args = parser.parse_args()

    # Semilla para reproducibilidad
    random.seed(args.seed)
    rng = np.random.default_rng(args.seed)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n🚀 Iniciando generación de datasets (seed={args.seed}, n={args.n_products})\n")

    # Generar catálogo
    catalog = generate_catalog(args.n_products, rng)
    catalog_path = output_dir / "catalog.csv"
    catalog.to_csv(catalog_path, index=False)
    print(f"  💾 Guardado: {catalog_path}")

    # Generar competencia
    competitors = generate_competitors(catalog, rng)
    competitors_path = output_dir / "competitors.csv"
    competitors.to_csv(competitors_path, index=False)
    print(f"  💾 Guardado: {competitors_path}")

    # Generar inventario/demanda
    inventory = generate_inventory_demand(catalog)
    inventory_path = output_dir / "inventory_demand.csv"
    inventory.to_csv(inventory_path, index=False)
    print(f"  💾 Guardado: {inventory_path}")

    # Resumen estadístico
    print("\n" + "="*50)
    print("📈 RESUMEN DE DATOS GENERADOS")
    print("="*50)
    print(f"Catálogo: {len(catalog)} productos")
    print(f"  - Categorías: {catalog['category'].value_counts().to_dict()}")
    print(f"  - Precio promedio: ${catalog['current_price'].mean():.2f}")
    print(f"  - Margen promedio: {((catalog['current_price'] - catalog['cost_price']) / catalog['current_price']).mean():.1%}")
    print(f"\nCompetencia: {len(competitors)} registros")
    print(f"  - Competidores únicos: {competitors['competitor_id'].nunique()}")
    print(f"  - Productos con competencia: {competitors['product_id_own'].nunique()}")
    print(f"\nInventario/Demanda: {len(inventory)} registros")
    print(f"  - Productos con stock bajo (<20): {(inventory['stock'] < 20).sum()}")
    print(f"  - Productos sin stock: {(inventory['stock'] == 0).sum()}")
    print("\n✅ Generación completada exitosamente\n")


if __name__ == "__main__":
    main()
