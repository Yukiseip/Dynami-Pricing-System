"""
engine.py
=========
Motor de pricing dinámico. Calcula el precio sugerido para cada producto
basado en: costo, competencia, nivel de stock y velocidad de demanda.

PRINCIPIO DE DISEÑO: Reglas explícitas > ML black-box
Cada ajuste es trazable y comprensible para el equipo comercial.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd
from loguru import logger

from .config import PricingConfig, load_config


# ============================================================
# DATA CLASSES (Input / Output tipados)
# ============================================================

@dataclass
class ProductSignals:
    """Señales de entrada para calcular el precio sugerido."""
    product_id: str
    name: str
    category: str
    cost_price: float
    current_price: float
    avg_comp_price: Optional[float] = None
    min_comp_price: Optional[float] = None
    stock: int = 0
    stock_status: str = "normal"
    velocity_score: float = 0.0
    sales_7d: int = 0


@dataclass
class PricingRecommendation:
    """Recomendación de precio con trazabilidad completa."""
    product_id: str
    current_price: float
    suggested_price: float
    min_allowed_price: float
    competitive_price: Optional[float]
    demand_adjustment: float
    stock_adjustment: float
    base_price_used: float
    action: str  # 'decrease', 'increase', 'maintain'
    reasoning: str
    confidence: str  # 'high', 'medium', 'low'


# ============================================================
# FUNCIONES DE AJUSTE
# ============================================================

def map_velocity_to_demand_adjustment(
    velocity_score: float, config: PricingConfig
) -> float:
    """
    Mapea velocity_score (ratio ventas/visitas) a ajuste de precio.

    Lógica:
        - velocity >= 0.15 (alta conversión) → subir precio hasta +10%
        - velocity 0.05-0.15 (normal) → sin ajuste
        - velocity < 0.05 (baja conversión) → bajar precio hasta -5%

    Args:
        velocity_score: Ratio de conversión (ventas / visitas).
        config: Configuración del motor.

    Returns:
        Ajuste de precio como decimal (ej: 0.05 = +5%).
    """
    if velocity_score >= 0.15:
        # Alta demanda: escalar de 0 a max_adjustment_demand
        normalized = min((velocity_score - 0.15) / 0.15, 1.0)
        return round(normalized * config.max_adjustment_demand, 4)
    elif velocity_score >= 0.05:
        return 0.0
    else:
        # Baja demanda: escalar de 0 a min_adjustment_demand (negativo)
        normalized = min((0.05 - velocity_score) / 0.05, 1.0)
        return round(normalized * config.min_adjustment_demand, 4)


def map_stock_to_adjustment(
    stock: int, stock_status: str, config: PricingConfig
) -> float:
    """
    Mapea nivel de stock a ajuste de precio.

    Lógica:
        - out_of_stock → no calcular precio (retorna 0, se maneja arriba)
        - critical_low → +3% (escasez)
        - normal → sin ajuste
        - overstock → -5% (liquidar)

    Args:
        stock: Unidades en stock.
        stock_status: Clasificación del nivel de stock.
        config: Configuración del motor.

    Returns:
        Ajuste de precio como decimal.
    """
    if stock_status == "overstock":
        return config.max_adjustment_stock_over  # Negativo: bajar precio
    elif stock_status == "critical_low":
        return config.max_adjustment_stock_under  # Positivo: subir precio
    else:
        return 0.0


def determine_base_price(
    cost_price: float,
    avg_comp_price: Optional[float],
    min_comp_price: Optional[float],
    config: PricingConfig,
) -> tuple[float, Optional[float]]:
    """
    Determina el precio base antes de ajustes.

    Estrategia:
        1. Si hay competencia: igualar precio mínimo menos buffer
        2. Si no hay competencia: usar costo + margen mínimo como base

    Args:
        cost_price: Costo del producto.
        avg_comp_price: Precio promedio de competencia.
        min_comp_price: Precio mínimo de competencia.
        config: Configuración del motor.

    Returns:
        (precio_base, precio_competitivo_calculado)
    """
    min_price = round(cost_price * (1 + config.min_margin_pct), 2)

    if min_comp_price is not None and min_comp_price > 0:
        competitive_price = round(min_comp_price - config.undercut_buffer, 2)
        base_price = max(min_price, competitive_price)
        return base_price, competitive_price
    else:
        # Sin datos de competencia: usar precio mínimo + 5% buffer
        return round(min_price * 1.05, 2), None


# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================

def calculate_price(
    signals: ProductSignals,
    config: Optional[PricingConfig] = None,
) -> PricingRecommendation:
    """
    Calcula el precio sugerido para un producto.

    Flujo:
        1. Validar inputs
        2. Calcular precio mínimo (floor de rentabilidad)
        3. Determinar precio base competitivo
        4. Aplicar ajuste de demanda
        5. Aplicar ajuste de stock
        6. Calcular precio final
        7. Generar reasoning legible

    Args:
        signals: Señales del producto.
        config: Configuración del motor (opcional, carga desde YAML si None).

    Returns:
        PricingRecommendation con precio sugerido y trazabilidad.

    Raises:
        ValueError: Si cost_price es None o <= 0
    """
    if config is None:
        config = load_config()

    # --- Validaciones ---
    if signals.cost_price is None or signals.cost_price <= 0:
        raise ValueError(f"cost_price inválido para {signals.product_id}: {signals.cost_price}")

    # --- Caso especial: sin stock ---
    if signals.stock == 0 or signals.stock_status == "out_of_stock":
        return PricingRecommendation(
            product_id=signals.product_id,
            current_price=signals.current_price,
            suggested_price=signals.current_price,  # Mantener precio
            min_allowed_price=round(signals.cost_price * (1 + config.min_margin_pct), 2),
            competitive_price=None,
            demand_adjustment=0.0,
            stock_adjustment=0.0,
            base_price_used=signals.current_price,
            action="maintain",
            reasoning="Producto sin stock. Precio mantenido sin cambios.",
            confidence="low",
        )

    # --- Paso 1: Precio mínimo (floor) ---
    min_allowed_price = round(signals.cost_price * (1 + config.min_margin_pct), 2)

    # --- Paso 2: Precio base competitivo ---
    base_price, competitive_price = determine_base_price(
        signals.cost_price,
        signals.avg_comp_price,
        signals.min_comp_price,
        config,
    )

    # --- Paso 3: Ajuste de demanda ---
    demand_adj = map_velocity_to_demand_adjustment(signals.velocity_score, config)

    # --- Paso 4: Ajuste de stock ---
    stock_adj = map_stock_to_adjustment(signals.stock, signals.stock_status, config)

    # --- Paso 5: Precio final ---
    raw_final = base_price * (1 + demand_adj + stock_adj)
    final_price = round(max(raw_final, min_allowed_price), 2)

    # --- Paso 6: Determinar acción ---
    price_delta = final_price - signals.current_price
    if price_delta < -0.50:
        action = "decrease"
    elif price_delta > 0.50:
        action = "increase"
    else:
        action = "maintain"

    # --- Paso 7: Confianza (basada en disponibilidad de datos) ---
    if signals.avg_comp_price is not None and signals.velocity_score > 0:
        confidence = "high"
    elif signals.avg_comp_price is not None or signals.velocity_score > 0:
        confidence = "medium"
    else:
        confidence = "low"

    # --- Paso 8: Reasoning legible ---
    reasoning_parts = [
        f"Costo: ${signals.cost_price:.2f}",
        f"Margen mínimo requerido: {config.min_margin_pct:.0%} → floor ${min_allowed_price:.2f}",
        f"Base competitiva: ${base_price:.2f}" + (
            f" (competidor mín: ${signals.min_comp_price:.2f})"
            if signals.min_comp_price else " (sin datos de competencia)"
        ),
        f"Ajuste demanda (velocity={signals.velocity_score:.3f}): {demand_adj:+.1%}",
        f"Ajuste stock ({signals.stock_status}): {stock_adj:+.1%}",
        f"Precio sugerido: ${final_price:.2f} vs actual ${signals.current_price:.2f} ({price_delta:+.2f})",
    ]
    reasoning = " | ".join(reasoning_parts)

    return PricingRecommendation(
        product_id=signals.product_id,
        current_price=signals.current_price,
        suggested_price=final_price,
        min_allowed_price=min_allowed_price,
        competitive_price=competitive_price,
        demand_adjustment=demand_adj,
        stock_adjustment=stock_adj,
        base_price_used=base_price,
        action=action,
        reasoning=reasoning,
        confidence=confidence,
    )


# ============================================================
# PIPELINE COMPLETO
# ============================================================

def run_pricing_pipeline(config: Optional[PricingConfig] = None) -> pd.DataFrame:
    """
    Ejecuta el motor de pricing para todos los productos en gold.fct_pricing_signals.

    Args:
        config: Configuración del motor (opcional).

    Returns:
        DataFrame con todas las recomendaciones de precio.
    """
    from ingestion.db_utils import get_engine

    if config is None:
        config = load_config()

    logger.info("Iniciando pipeline de pricing...")
    engine = get_engine()

    df = pd.read_sql("SELECT * FROM gold.fct_pricing_signals", engine)
    logger.info(f"  Productos a procesar: {len(df)}")

    recommendations = []
    errors = []

    for _, row in df.iterrows():
        try:
            signals = ProductSignals(
                product_id=row["product_id"],
                name=row["name_original"],
                category=row["category"],
                cost_price=float(row["cost_price"]),
                current_price=float(row["current_price"]),
                avg_comp_price=float(row["avg_comp_price"]) if pd.notna(row.get("avg_comp_price")) else None,
                min_comp_price=float(row["min_comp_price"]) if pd.notna(row.get("min_comp_price")) else None,
                stock=int(row["stock"]),
                stock_status=str(row["stock_status"]),
                velocity_score=float(row.get("velocity_score", 0.0)),
                sales_7d=int(row.get("sales_7d", 0)),
            )
            rec = calculate_price(signals, config)
            recommendations.append({
                "product_id": rec.product_id,
                "current_price": rec.current_price,
                "suggested_price": rec.suggested_price,
                "min_allowed_price": rec.min_allowed_price,
                "competitive_price": rec.competitive_price,
                "demand_adjustment": rec.demand_adjustment,
                "stock_adjustment": rec.stock_adjustment,
                "base_price_used": rec.base_price_used,
                "action": rec.action,
                "reasoning": rec.reasoning,
                "confidence": rec.confidence,
                "price_delta": rec.suggested_price - rec.current_price,
                "computed_at": pd.Timestamp.now(),
            })
        except Exception as e:
            errors.append({"product_id": row["product_id"], "error": str(e)})
            logger.warning(f"  Error en {row['product_id']}: {e}")

    if errors:
        logger.warning(f"  {len(errors)} errores al calcular precios")

    results_df = pd.DataFrame(recommendations)

    # Guardar en Gold
    results_df.to_sql(
        "pricing_recommendations",
        engine,
        schema="gold",
        if_exists="replace",
        index=False,
    )

    logger.success(
        f"  ✅ Pricing completado: {len(recommendations)} recomendaciones. "
        f"Acciones: {results_df['action'].value_counts().to_dict()}"
    )
    return results_df
