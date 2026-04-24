"""
app.py — Dashboard de Dynamic Pricing en Streamlit
Visualiza: KPIs, comparación de precios, revenue at risk, productos sin match
"""
import os
import sys

sys.path.insert(0, '/app')

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.ingestion.db_utils import get_engine

st.set_page_config(
    page_title="Dynamic Pricing Dashboard",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# CARGA DE DATOS (cacheada 5 min)
# ============================================================

@st.cache_data(ttl=300)
def load_pricing_data() -> pd.DataFrame:
    engine = get_engine()
    try:
        df = pd.read_sql("""
            SELECT
                r.product_id, s.name_original AS name, s.category,
                r.current_price, r.suggested_price, r.action, r.confidence,
                r.reasoning, r.demand_adjustment, r.stock_adjustment,
                s.avg_comp_price, s.min_comp_price, s.stock, s.stock_status,
                s.velocity_score, s.sales_7d, s.margin_current,
                s.price_position, s.n_competitors
            FROM gold.pricing_recommendations r
            JOIN gold.fct_pricing_signals s ON r.product_id = s.product_id
        """, engine)
        df["price_change_pct"] = (
            (df["suggested_price"] - df["current_price"]) / df["current_price"] * 100
        ).round(2)
        df["price_delta"] = (df["suggested_price"] - df["current_price"]).round(2)
        df["revenue_at_risk"] = (
            (df["current_price"] - df["suggested_price"]) * df["sales_7d"]
        ).clip(lower=0).round(2)
        return df
    except Exception as e:
        st.error(f"❌ Error cargando datos: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300)
def load_pending_matches() -> pd.DataFrame:
    engine = get_engine()
    try:
        return pd.read_sql("""
            SELECT own_product_id, own_product_name, competitor_name,
                   competitor_id, similarity_score, category
            FROM silver.product_matches
            WHERE status = 'review'
            ORDER BY similarity_score DESC
            LIMIT 100
        """, engine)
    except Exception:
        return pd.DataFrame()


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.title("🔧 Filtros")
    st.divider()

    df_all = load_pricing_data()

    if df_all.empty:
        st.error("⚠️ Sin datos. Ejecuta el pipeline primero.")
        st.stop()

    categories = ["Todos"] + sorted(df_all["category"].unique().tolist())
    selected_category = st.selectbox("📦 Categoría", categories)

    selected_action = st.multiselect(
        "🎯 Acción recomendada",
        ["increase", "decrease", "maintain"],
        default=["increase", "decrease", "maintain"],
    )

    selected_confidence = st.multiselect(
        "🎲 Nivel de confianza",
        ["high", "medium", "low"],
        default=["high", "medium"],
    )

    selected_stock = st.multiselect(
        "📦 Estado de stock",
        ["normal", "critical_low", "overstock", "out_of_stock"],
        default=["normal", "critical_low", "overstock"],
    )

    st.divider()
    if st.button("🔄 Refrescar datos"):
        st.cache_data.clear()
        st.rerun()

# ============================================================
# APLICAR FILTROS
# ============================================================

df = df_all.copy()
if selected_category != "Todos":
    df = df[df["category"] == selected_category]
if selected_action:
    df = df[df["action"].isin(selected_action)]
if selected_confidence:
    df = df[df["confidence"].isin(selected_confidence)]
if selected_stock:
    df = df[df["stock_status"].isin(selected_stock)]

# ============================================================
# HEADER
# ============================================================

st.title("💰 Dynamic Pricing Dashboard")
st.caption(
    f"Sistema de pricing inteligente para e-commerce • "
    f"**{len(df):,} productos** filtrados de **{len(df_all):,}** totales"
)
st.divider()

# ============================================================
# KPIs ROW 1
# ============================================================

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    total_revenue_at_risk = df["revenue_at_risk"].sum()
    st.metric(
        "💸 Revenue at Risk (7d)",
        f"${total_revenue_at_risk:,.0f}",
        help="Ventas potencialmente perdidas si no se ajustan precios"
    )

with col2:
    avg_margin = df["margin_current"].mean()
    st.metric(
        "📊 Margen Promedio",
        f"{avg_margin:.1%}",
        help="Margen bruto promedio del catálogo filtrado"
    )

with col3:
    badly_positioned = df["price_position"].isin(
        ["much_more_expensive", "much_cheaper"]
    ).sum()
    pct_bad = badly_positioned / max(len(df), 1) * 100
    st.metric(
        "⚠️ Mal Posicionados",
        f"{badly_positioned:,}",
        f"{pct_bad:.1f}% del catálogo",
        delta_color="inverse",
    )

with col4:
    decrease_count = (df["action"] == "decrease").sum()
    st.metric(
        "📉 Bajar Precio",
        f"{decrease_count:,}",
        f"{decrease_count/max(len(df),1):.1%}",
    )

with col5:
    increase_count = (df["action"] == "increase").sum()
    st.metric(
        "📈 Subir Precio",
        f"{increase_count:,}",
        f"{increase_count/max(len(df),1):.1%}",
        delta_color="normal",
    )

st.divider()

# ============================================================
# GRÁFICOS
# ============================================================

col_left, col_right = st.columns(2)

with col_left:
    st.subheader("📌 Precio Propio vs Competencia")
    scatter_df = df.dropna(subset=["avg_comp_price"])

    if not scatter_df.empty:
        fig = px.scatter(
            scatter_df,
            x="avg_comp_price",
            y="current_price",
            color="category",
            size="sales_7d",
            size_max=20,
            hover_data=["name", "action", "price_change_pct", "confidence"],
            labels={
                "avg_comp_price": "Precio Promedio Competencia ($)",
                "current_price": "Precio Actual ($)",
            },
        )
        # Línea de paridad (precio = competencia)
        max_val = max(scatter_df["avg_comp_price"].max(), scatter_df["current_price"].max())
        fig.add_shape(
            type="line", x0=0, y0=0, x1=max_val, y1=max_val,
            line=dict(color="red", width=1, dash="dash"),
        )
        fig.add_annotation(
            x=max_val * 0.75, y=max_val * 0.85,
            text="Paridad de precio",
            showarrow=False, font=dict(color="red", size=10)
        )
        fig.update_layout(height=400, showlegend=True)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sin datos de competencia para los filtros seleccionados.")

with col_right:
    st.subheader("🎯 Acciones por Categoría")
    action_by_cat = (
        df.groupby(["category", "action"])
        .size().reset_index(name="count")
    )
    if not action_by_cat.empty:
        fig2 = px.bar(
            action_by_cat,
            x="category",
            y="count",
            color="action",
            barmode="stack",
            color_discrete_map={
                "increase": "#2ecc71",
                "decrease": "#e74c3c",
                "maintain": "#95a5a6",
            },
        )
        fig2.update_layout(
            height=400,
            xaxis_tickangle=-30,
            xaxis_title="Categoría",
            yaxis_title="Productos",
        )
        st.plotly_chart(fig2, use_container_width=True)

# Distribución de cambio % de precio
st.subheader("📊 Distribución de Cambios de Precio")
col_hist_left, col_hist_right = st.columns(2)

with col_hist_left:
    fig_hist = px.histogram(
        df,
        x="price_change_pct",
        nbins=50,
        color="action",
        color_discrete_map={
            "increase": "#2ecc71",
            "decrease": "#e74c3c",
            "maintain": "#95a5a6",
        },
        labels={"price_change_pct": "Cambio de Precio (%)"},
    )
    fig_hist.update_layout(height=300)
    st.plotly_chart(fig_hist, use_container_width=True)

with col_hist_right:
    # Treemap de revenue at risk por categoría
    risk_by_cat = df.groupby("category")["revenue_at_risk"].sum().reset_index()
    if not risk_by_cat.empty and risk_by_cat["revenue_at_risk"].sum() > 0:
        fig_tree = px.treemap(
            risk_by_cat,
            path=["category"],
            values="revenue_at_risk",
            title="Revenue at Risk por Categoría ($)",
        )
        fig_tree.update_layout(height=300)
        st.plotly_chart(fig_tree, use_container_width=True)

st.divider()

# ============================================================
# TABLA DE RECOMENDACIONES
# ============================================================

st.subheader("📋 Recomendaciones de Precio")

table_df = df[[
    "product_id", "name", "category", "current_price",
    "suggested_price", "price_delta", "price_change_pct", "action",
    "confidence", "stock_status", "revenue_at_risk"
]].copy().sort_values("revenue_at_risk", ascending=False)

table_df.columns = [
    "ID", "Producto", "Categoría", "Precio Actual",
    "Precio Sugerido", "Delta $", "Cambio %", "Acción",
    "Confianza", "Estado Stock", "Revenue at Risk ($)"
]

st.dataframe(
    table_df.head(300),
    use_container_width=True,
    height=400,
    column_config={
        "Precio Actual": st.column_config.NumberColumn(format="$%.2f"),
        "Precio Sugerido": st.column_config.NumberColumn(format="$%.2f"),
        "Delta $": st.column_config.NumberColumn(format="$%.2f"),
        "Cambio %": st.column_config.NumberColumn(format="%.1f%%"),
        "Revenue at Risk ($)": st.column_config.NumberColumn(format="$%.0f"),
    }
)

st.caption(f"Top 300 por Revenue at Risk. Total filtrado: {len(df):,} productos.")

st.divider()

# ============================================================
# MATCHES PENDIENTES
# ============================================================

st.subheader("🔍 Matches Pendientes de Revisión")
pending_df = load_pending_matches()

if pending_df.empty:
    st.success("✅ Sin matches pendientes de revisión.")
else:
    st.warning(f"⚠️ {len(pending_df)} matches requieren validación manual (score 0.70–0.85)")
    st.dataframe(
        pending_df,
        use_container_width=True,
        column_config={
            "similarity_score": st.column_config.ProgressColumn(
                "Similitud", min_value=0.0, max_value=1.0, format="%.2f"
            )
        }
    )
