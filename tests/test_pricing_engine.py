"""
test_pricing_engine.py
======================
Tests unitarios para el motor de pricing.
Ejecutar con: pytest tests/test_pricing_engine.py -v
"""
import pytest
from src.pricing.engine import (
    calculate_price, ProductSignals, PricingRecommendation,
    map_velocity_to_demand_adjustment, map_stock_to_adjustment,
    determine_base_price,
)
from src.pricing.config import PricingConfig


@pytest.fixture
def default_config() -> PricingConfig:
    return PricingConfig(
        min_margin_pct=0.10,
        undercut_buffer=1.00,
        max_adjustment_demand=0.10,
        min_adjustment_demand=-0.05,
        max_adjustment_stock_over=-0.05,
        max_adjustment_stock_under=0.03,
        overstock_threshold=400,
        understock_threshold=20,
    )


@pytest.fixture
def normal_product() -> ProductSignals:
    return ProductSignals(
        product_id="SKU-001",
        name="Test Headphones",
        category="Audio",
        cost_price=100.0,
        current_price=150.0,
        avg_comp_price=140.0,
        min_comp_price=135.0,
        stock=100,
        stock_status="normal",
        velocity_score=0.08,
        sales_7d=50,
    )


# ---- TEST 1: Caso normal con competencia ----
def test_normal_product_with_competition(normal_product, default_config):
    rec = calculate_price(normal_product, default_config)
    assert isinstance(rec, PricingRecommendation)
    assert rec.suggested_price > 0
    assert rec.suggested_price >= rec.min_allowed_price
    assert rec.product_id == "SKU-001"


# ---- TEST 2: Precio nunca cae por debajo del margen mínimo ----
def test_price_never_below_minimum_margin(default_config):
    """Si competencia es muy agresiva, respetar margen mínimo."""
    signals = ProductSignals(
        product_id="SKU-002",
        name="Budget Item",
        category="Accessories",
        cost_price=100.0,
        current_price=120.0,
        avg_comp_price=50.0,   # Competencia muy barata
        min_comp_price=45.0,   # Muy por debajo del costo
        stock=100,
        stock_status="normal",
        velocity_score=0.05,
        sales_7d=10,
    )
    rec = calculate_price(signals, default_config)
    min_price = round(100.0 * (1 + 0.10), 2)  # 110.0
    assert round(rec.suggested_price, 2) >= min_price, (
        f"Precio {rec.suggested_price} está por debajo del mínimo {min_price}"
    )


# ---- TEST 3: Sin competencia ----
def test_no_competition_data(default_config):
    """Sin datos de competencia, usar margen mínimo como base."""
    signals = ProductSignals(
        product_id="SKU-003",
        name="Unique Product",
        category="Tablets",
        cost_price=200.0,
        current_price=280.0,
        avg_comp_price=None,
        min_comp_price=None,
        stock=50,
        stock_status="normal",
        velocity_score=0.05,
    )
    rec = calculate_price(signals, default_config)
    assert rec.suggested_price >= 200.0 * 1.10  # Al menos margen mínimo
    assert rec.competitive_price is None
    # velocity_score=0.05 no es 0, así que confianza es medium (tiene señal de demanda)
    assert rec.confidence in ("low", "medium")


# ---- TEST 4: Stock = 0 → mantener precio, no calcular ----
def test_zero_stock_maintains_price(default_config):
    signals = ProductSignals(
        product_id="SKU-004",
        name="Out of Stock Item",
        category="Laptops",
        cost_price=500.0,
        current_price=750.0,
        avg_comp_price=720.0,
        min_comp_price=700.0,
        stock=0,
        stock_status="out_of_stock",
        velocity_score=0.0,
    )
    rec = calculate_price(signals, default_config)
    assert rec.action == "maintain"
    assert rec.suggested_price == 750.0
    assert "sin stock" in rec.reasoning.lower()


# ---- TEST 5: Sobre-stock → precio baja ----
def test_overstock_reduces_price(normal_product, default_config):
    import dataclasses
    signals = dataclasses.replace(normal_product, stock=450, stock_status="overstock")
    rec_normal = calculate_price(normal_product, default_config)
    rec_overstock = calculate_price(signals, default_config)
    assert rec_overstock.suggested_price < rec_normal.suggested_price
    assert rec_overstock.stock_adjustment == default_config.max_adjustment_stock_over


# ---- TEST 6: Stock crítico → precio sube ----
def test_critical_stock_increases_price(normal_product, default_config):
    import dataclasses
    signals = dataclasses.replace(normal_product, stock=5, stock_status="critical_low")
    rec_normal = calculate_price(normal_product, default_config)
    rec_critical = calculate_price(signals, default_config)
    assert rec_critical.suggested_price > rec_normal.suggested_price
    assert rec_critical.stock_adjustment == default_config.max_adjustment_stock_under


# ---- TEST 7: Cost price None → raise ValueError ----
def test_none_cost_price_raises_error(default_config):
    signals = ProductSignals(
        product_id="SKU-007",
        name="Bad Data Product",
        category="Audio",
        cost_price=None,  # type: ignore
        current_price=100.0,
        stock=50,
        stock_status="normal",
        velocity_score=0.05,
    )
    with pytest.raises(ValueError, match="cost_price inválido"):
        calculate_price(signals, default_config)


# ---- TEST 8: Alta demanda → precio sube ----
def test_high_demand_increases_price(normal_product, default_config):
    import dataclasses
    signals_high = dataclasses.replace(normal_product, velocity_score=0.30)
    signals_low = dataclasses.replace(normal_product, velocity_score=0.01)
    rec_high = calculate_price(signals_high, default_config)
    rec_low = calculate_price(signals_low, default_config)
    assert rec_high.suggested_price > rec_low.suggested_price
    assert rec_high.demand_adjustment > 0
    assert rec_low.demand_adjustment < 0


# ---- TEST 9: Reasoning siempre está presente ----
def test_reasoning_is_always_present(normal_product, default_config):
    rec = calculate_price(normal_product, default_config)
    assert rec.reasoning is not None
    assert len(rec.reasoning) > 10
    assert "Costo" in rec.reasoning


# ---- TEST 10: Precio sugerido siempre es positivo ----
@pytest.mark.parametrize("velocity,stock,stock_status", [
    (0.0, 1, "critical_low"),
    (0.30, 500, "overstock"),
    (0.05, 50, "normal"),
    (0.20, 15, "critical_low"),
])
def test_suggested_price_always_positive(velocity, stock, stock_status, default_config):
    signals = ProductSignals(
        product_id="SKU-P",
        name="Test",
        category="Audio",
        cost_price=50.0,
        current_price=70.0,
        avg_comp_price=65.0,
        min_comp_price=60.0,
        stock=stock,
        stock_status=stock_status,
        velocity_score=velocity,
    )
    rec = calculate_price(signals, default_config)
    assert rec.suggested_price > 0


# ---- TEST 11: map_velocity_to_demand_adjustment ----
def test_velocity_adjustment_ranges(default_config):
    assert map_velocity_to_demand_adjustment(0.30, default_config) > 0
    assert map_velocity_to_demand_adjustment(0.10, default_config) == 0.0
    assert map_velocity_to_demand_adjustment(0.01, default_config) < 0


# ---- TEST 12: Confianza alta cuando hay competencia y demanda ----
def test_high_confidence_with_full_data(normal_product, default_config):
    rec = calculate_price(normal_product, default_config)
    # normal_product tiene avg_comp_price y velocity_score > 0
    assert rec.confidence == "high"
