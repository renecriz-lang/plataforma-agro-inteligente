"""Tendências Climáticas — evolução temporal das variáveis climáticas.

Pergunta-foco: "Como o mês de [janeiro] está evoluindo ao longo dos anos
em [Santa Maria do Oeste/PR]?"
"""

import os
import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy import stats

import streamlit as st

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))

from utils.data_loader import carregar_base_clima_compacta
from utils.design import inject_css, hero_banner
from utils.agregacao_geografica import (
    agregar_por_escopo,
    agregar_para_mensal,
    agregar_para_anual,
)

# ── Constantes ──────────────────────────────────────────────────────────────
ROTULOS_VARS = {
    "prec_media": "🌧️ Precipitação (mm)",
    "tmax_media": "🌡️ Temperatura máxima (°C)",
    "tmed_media": "🌡️ Temperatura média (°C)",
    "tmin_media": "🌡️ Temperatura mínima (°C)",
}

MESES_NOMES = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março",    4: "Abril",
    5: "Maio",    6: "Junho",     7: "Julho",     8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}

COR_ENSO = {"El Niño": "#d1495b", "La Niña": "#2e86ab", "Neutro": "#8d99ae"}


def eh_chuva(variavel: str) -> bool:
    return variavel == "prec_media"


# ── Configuração da página ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Tendências Climáticas",
    page_icon="📉",
    layout="wide",
)

inject_css()
hero_banner(
    title="Tendências Climáticas",
    subtitle=(
        "Como o clima está mudando ao longo dos anos — visualize a evolução "
        "de cada mês e detecte tendências de longo prazo com marcação ENSO."
    ),
    icon="📉",
)

with st.expander("ℹ️ Como usar este módulo", expanded=False):
    st.markdown("""
**Siga os passos abaixo para analisar tendências climáticas:**

**1. Configure o painel lateral**
Escolha a variável (precipitação ou temperatura), o escopo geográfico
(Município, Estado ou Brasil) e o intervalo de anos a analisar.

**2. Visualização principal — "Foco em um mês"**
Selecione um mês para ver como ele se comportou em cada ano do período.
Esta é a visualização que melhor revela tendências: se janeiro está
esquentando, você verá os pontos subindo da esquerda para a direita.

**3. Abas de análise complementar**
- **📅 Heatmap calendário**: visão completa (ano × mês) em mapa de calor.
- **📈 Tendência anual**: soma/média anual com regressão linear e faixa de confiança 95%.
- **🌡️ Climograma sobreposto**: todos os anos em uma única tela — anos atípicos saltam aos olhos.
- **🔥 Anomalias mensais**: desvio de cada célula em relação à média histórica daquele mês.

**4. Toggles ENSO e tendência**
Ative/desative a marcação ENSO e a linha de tendência em todos os gráficos
de uma vez usando os toggles na barra lateral.

---
**Interpretação rápida de tendência:** p < 0,05 indica tendência
estatisticamente significativa; p > 0,10 sugere ausência de tendência clara.
""")

# ── Painel lateral ─────────────────────────────────────────────────────────
st.sidebar.header("⚙️ Configuração")

variavel = st.sidebar.selectbox(
    "Variável a analisar",
    list(ROTULOS_VARS.keys()),
    format_func=lambda v: ROTULOS_VARS[v],
    key="tc_variavel",
)

escopo = st.sidebar.radio(
    "Escopo geográfico",
    ["Município", "Estado", "Brasil"],
    key="tc_escopo",
)

# Carrega metadados (leve — só código, nome, estado)
@st.cache_data(show_spinner=False)
def _meta() -> pd.DataFrame:
    return (
        carregar_base_clima_compacta()[["codigo_ibge", "nome", "estado"]]
        .drop_duplicates()
        .dropna(subset=["estado"])
    )

df_meta = _meta()
estados_disp = sorted(df_meta["estado"].dropna().unique())

estado_sel: str | None = None
municipio_sel: int | None = None

if escopo in ("Município", "Estado"):
    idx_pr = estados_disp.index("PR") if "PR" in estados_disp else 0
    estado_sel = st.sidebar.selectbox(
        "Estado", estados_disp, index=idx_pr, key="tc_estado",
    )

if escopo == "Município":
    muns_df = (
        df_meta[df_meta["estado"] == estado_sel]
        .sort_values("nome")
        .drop_duplicates(subset="codigo_ibge")
    )
    municipio_sel = st.sidebar.selectbox(
        "Município",
        muns_df["codigo_ibge"].tolist(),
        format_func=lambda cod: (
            muns_df.loc[muns_df["codigo_ibge"] == cod, "nome"]
            .iloc[0] if (muns_df["codigo_ibge"] == cod).any() else str(cod)
        ),
        key="tc_municipio",
    )

st.sidebar.divider()

mostrar_enso = st.sidebar.toggle(
    "Mostrar marcação ENSO", value=True, key="tc_enso",
)
mostrar_tendencia = st.sidebar.toggle(
    "Mostrar linha de tendência (regressão linear)", value=True, key="tc_trend",
)

intervalo_anos = st.sidebar.slider(
    "Intervalo de anos", 2000, 2025, (2000, 2025), key="tc_anos",
)

# ── Carregamento e agregação dos dados ─────────────────────────────────────
df_long = carregar_base_clima_compacta()
df_long = df_long[df_long["ano"].between(intervalo_anos[0], intervalo_anos[1])]

df_dec = agregar_por_escopo(
    df_long, escopo, estado_sel, municipio_sel, variavel,
)

if df_dec.empty:
    st.error(
        "Sem dados disponíveis para o escopo selecionado. "
        "Verifique se os filtros estão corretos."
    )
    st.stop()

modo_agg = "soma" if eh_chuva(variavel) else "media"
df_mensal = agregar_para_mensal(df_dec, modo_agg)
df_anual  = agregar_para_anual(df_mensal, modo_agg)

# ── Nome do escopo (para títulos) ──────────────────────────────────────────
if escopo == "Município":
    _nome_mun = (
        muns_df.loc[muns_df["codigo_ibge"] == municipio_sel, "nome"]
        .iloc[0] if municipio_sel is not None else "—"
    )
    nome_escopo = f"{_nome_mun}/{estado_sel}"
elif escopo == "Estado":
    nome_escopo = estado_sel
else:
    nome_escopo = "Brasil"

# ── Cabeçalho contextual ───────────────────────────────────────────────────
st.markdown(
    f"## {ROTULOS_VARS[variavel]} em **{nome_escopo}** "
    f"· {intervalo_anos[0]}–{intervalo_anos[1]}"
)

# ── Métricas executivas ────────────────────────────────────────────────────
unidade = "mm" if eh_chuva(variavel) else "°C"

if len(df_anual) >= 3:
    slope, intercept, r_value, p_value, std_err = stats.linregress(
        df_anual["ano"].values, df_anual["valor"].values,
    )
    n_anos = len(df_anual)
    delta_total = slope * (n_anos - 1)

    if p_value > 0.10:
        rot_tendencia = "Sem tendência clara"
        delta_str = f"{delta_total:+.1f} {unidade} no período"
    elif slope > 0:
        rot_tendencia = "Tendência de alta"
        delta_str = f"{delta_total:+.1f} {unidade} no período"
    else:
        rot_tendencia = "Tendência de baixa"
        delta_str = f"{delta_total:+.1f} {unidade} no período"
else:
    slope = p_value = float("nan")
    rot_tendencia = "Dados insuficientes"
    delta_str = "—"

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Média do período", f"{df_anual['valor'].mean():.1f} {unidade}")
with col2:
    slope_str = f"{slope:+.2f} {unidade}/ano" if not np.isnan(slope) else "—"
    st.metric("Slope (variação anual)", slope_str)
with col3:
    st.metric(rot_tendencia, delta_str)
with col4:
    pval_str = f"{p_value:.3f}" if not np.isnan(p_value) else "—"
    st.metric(
        "p-valor (significância)", pval_str,
        help="p < 0,05 = tendência estatisticamente significativa.",
    )

# ── Função: gráfico "Foco em um mês" ──────────────────────────────────────

def construir_grafico_foco_mensal(
    df_foco: pd.DataFrame,
    variavel: str,
    mes_foco: int,
    mostrar_enso: bool,
    mostrar_tendencia: bool,
    nome_escopo: str,
    intervalo_anos: tuple[int, int],
) -> go.Figure:
    """Barras (chuva) ou linha+pontos (temperatura) com tendência e cores ENSO."""
    fig = go.Figure()
    is_chuva = eh_chuva(variavel)
    unidade = "mm" if is_chuva else "°C"
    nome_mes = MESES_NOMES[mes_foco]

    cores = (
        df_foco["enso_fenomeno"].map(COR_ENSO).fillna("#8d99ae").tolist()
        if mostrar_enso
        else ["#2d6a4f"] * len(df_foco)
    )

    if is_chuva:
        fig.add_trace(go.Bar(
            x=df_foco["ano"],
            y=df_foco["valor"],
            marker_color=cores,
            name=nome_mes,
            customdata=df_foco["enso_fenomeno"].fillna("—"),
            hovertemplate=(
                "<b>%{x}</b><br>"
                f"Acumulado de {nome_mes}: %{{y:.0f}} mm<br>"
                "ENSO: %{customdata}<extra></extra>"
            ),
        ))
    else:
        fig.add_trace(go.Scatter(
            x=df_foco["ano"],
            y=df_foco["valor"],
            mode="lines+markers",
            line=dict(color="#8d99ae", width=2),
            marker=dict(size=10, color=cores, line=dict(color="white", width=1.5)),
            name=nome_mes,
            customdata=df_foco["enso_fenomeno"].fillna("—"),
            hovertemplate=(
                "<b>%{x}</b><br>"
                f"{nome_mes} (média): %{{y:.1f}}°C<br>"
                "ENSO: %{customdata}<extra></extra>"
            ),
        ))

    # Linha de tendência
    if mostrar_tendencia and len(df_foco) >= 5:
        x = df_foco["ano"].values
        y = df_foco["valor"].values
        slope_f, intercept_f, _, p_f, _ = stats.linregress(x, y)
        x_line = np.array([x.min(), x.max()])
        y_line = slope_f * x_line + intercept_f
        sig = "significativa" if p_f < 0.05 else "não significativa"
        fig.add_trace(go.Scatter(
            x=x_line,
            y=y_line,
            mode="lines",
            line=dict(color="#1b4332", width=2.5, dash="dash"),
            name=f"Tendência: {slope_f:+.2f} {unidade}/ano · p={p_f:.3f} ({sig})",
            hoverinfo="skip",
        ))

    # Linha de média horizontal
    media = df_foco["valor"].mean()
    fig.add_hline(
        y=media,
        line_dash="dot",
        line_color="#666",
        annotation_text=f"Média do período: {media:.1f} {unidade}",
        annotation_position="top right",
    )

    # Entradas de legenda ENSO
    if mostrar_enso:
        for fase in ["El Niño", "La Niña", "Neutro"]:
            fig.add_trace(go.Scatter(
                x=[None], y=[None],
                mode="markers",
                marker=dict(size=12, color=COR_ENSO[fase]),
                name=fase,
                showlegend=True,
            ))

    fig.update_layout(
        title=f"{nome_mes} em {nome_escopo}  ({intervalo_anos[0]}–{intervalo_anos[1]})",
        xaxis_title="Ano",
        yaxis_title=ROTULOS_VARS[variavel],
        height=460,
        margin=dict(t=60, b=50, l=70, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


# ── Visualização principal: Foco em um mês ─────────────────────────────────
st.markdown("---")
st.markdown("### 🎯 Foco em um mês — evolução ao longo dos anos")
st.caption(
    "Selecione um mês para ver como ele se comportou em cada ano. "
    "Esta é a visualização que melhor revela tendências: se janeiro está "
    "esquentando, você verá os pontos subindo da esquerda para a direita."
)

mes_foco = st.selectbox(
    "Mês",
    list(MESES_NOMES.keys()),
    format_func=lambda m: MESES_NOMES[m],
    index=0,
    key="tc_mes_foco",
)

df_foco = df_mensal[df_mensal["mes"] == mes_foco].sort_values("ano")

if df_foco.empty:
    st.info("Sem dados para este mês no escopo selecionado.")
else:
    fig_foco = construir_grafico_foco_mensal(
        df_foco, variavel, mes_foco,
        mostrar_enso, mostrar_tendencia,
        nome_escopo, intervalo_anos,
    )
    st.plotly_chart(fig_foco, use_container_width=True)

# ── Abas complementares (em construção) ────────────────────────────────────
st.markdown("---")
st.info("📊 Abas complementares em construção — próximo commit.")
