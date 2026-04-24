"""config.py — Parámetros configurables del motor de pricing."""
import os
import yaml
from pathlib import Path
from pydantic import BaseModel, Field


class PricingConfig(BaseModel):
    min_margin_pct: float = Field(default=0.10, ge=0.0, le=1.0)
    undercut_buffer: float = Field(default=1.00, ge=0.0)
    max_adjustment_demand: float = Field(default=0.10, ge=0.0, le=0.50)
    min_adjustment_demand: float = Field(default=-0.05, ge=-0.50, le=0.0)
    max_adjustment_stock_over: float = Field(default=-0.05, ge=-0.50, le=0.0)
    max_adjustment_stock_under: float = Field(default=0.03, ge=0.0, le=0.50)
    overstock_threshold: int = Field(default=400, ge=0)
    understock_threshold: int = Field(default=20, ge=0)


def load_config(config_path: str = None) -> PricingConfig:
    """
    Carga configuración desde YAML o usa defaults.

    Args:
        config_path: Ruta al archivo YAML de configuración.

    Returns:
        Instancia de PricingConfig con los parámetros cargados.
    """
    if config_path is None:
        config_path = os.getenv("PRICING_CONFIG_PATH", "config/pricing_config.yaml")

    path = Path(config_path)
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f)
            engine_config = data.get("pricing_engine", {})
            return PricingConfig(**engine_config)

    # Fallback a defaults
    return PricingConfig()
