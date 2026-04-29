"""
Comparador de Cenários Climáticos — compare múltiplos perfis históricos
(intervalo de anos × fase ENSO × intensidade) em um único gráfico decendial.
"""

import os
import sys

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))

from utils.design import inject_css, hero_banner
from utils.data_loader import load_base, carregar_base_clima_compacta
from utils.resiliencia_enso import agregar_perfil_decendial

# ── Configuração ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Comparador de Cenários Climáticos",
    page_icon="📈",
    layout="wide",
)
inject_css()
hero_banner(
    title="Comparador de Cenários Climáticos",
    subtitle=(
        "Compare múltiplos perfis históricos "
        "(intervalo de anos × fase ENSO × intensidade) em um único gráfico decendial"
    ),
    icon="📈",
)

# ── Constantes ────────────────────────────────────────────────────────────────
PALETA_PERFIS = ["#2d6a4f", "#d1495b", "#2e86ab", "#c9963a", "#7d4f9e", "#3a7d44"]

VARIAVEIS = {
    "prec_media":  "🌧️ Chuva acumulada por decêndio (mm)",
    "tmax_media":  "🌡️ Temperatura máxima média (°C)",
    "tmed_media":  "🌡️ Temperatura média (°C)",
    "tmin_media":  "🌡️ Temperatura mínima média (°C)",
}
ROTULOS_VAR = {
    "prec_media": "Precipitação (mm/decêndio)",
    "tmax_media": "Tmax média (°C)",
    "tmed_media": "Tméd média (°C)",
    "tmin_media": "Tmin média (°C)",
}

MESES_DECENDIOS = {
    1: "Jan-1", 4: "Fev-1", 7: "Mar-1", 10: "Abr-1",
    13: "Mai-1", 16: "Jun-1", 19: "Jul-1", 22: "Ago-1",
    25: "Set-1", 28: "Out-1", 31: "Nov-1", 34: "Dez-1",
}

PERFIS_DEFAULT = [
    {"nome": "Média geral 2010–2025", "anos": (2010, 2025), "fases": [],        "intensidades": []},
    {"nome": "Anos La Niña",          "anos": (2000, 2025), "fases": ["La Niña"], "intensidades": []},
    {"nome": "Anos El Niño",          "anos": (2000, 2025), "fases": ["El Niño"], "intensidades": []},
]

ANO_MIN, ANO_MAX = 2000, 2025


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ── Inicializa session_state ──────────────────────────────────────────────────
if "perfis" not in st.session_state:
    st.session_state["perfis"] = [p.copy() for p in PERFIS_DEFAULT]

# ── Bases de dados ────────────────────────────────────────────────────────────
df_ref = load_base("media_geral")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📈 Comparador de Cenários")
    st.markdown("---")

    estados = sorted(df_ref["estado"].dropna().unique())
    estado_sel = st.selectbox(
        "Estado (UF)", estados,
        index=estados.index("PR") if "PR" in estados else 0,
    )

    muns = df_ref[df_ref["estado"] == estado_sel].sort_values("nome")["nome"].tolist()
    municipio_sel = st.selectbox("Município", muns)

    st.markdown("---")
    variavel_key = st.radio(
        "Variável a comparar",
        list(VARIAVEIS.keys()),
        format_func=lambda k: VARIAVEIS[k],
    )

    st.markdown("---")
    mostrar_faixa = st.toggle("Mostrar faixa p10–p90", value=True)

    if st.button("↺ Resetar perfis padrão"):
        st.session_state["perfis"] = [p.copy() for p in PERFIS_DEFAULT]
        st.rerun()

# ── Município → código IBGE ───────────────────────────────────────────────────
row_mun = df_ref[df_ref["nome"] == municipio_sel]
if row_mun.empty:
    st.warning(f"Município '{municipio_sel}' não encontrado.")
    st.stop()
codigo_ibge = str(row_mun["codigo_ibge"].iloc[0])

# ── Carrega base climática completa ──────────────────────────────────────────
with st.spinner("Carregando base climática histórica…"):
    df_clima = carregar_base_clima_compacta()

df_clima_mun = df_clima[df_clima["codigo_ibge"].astype(str) == codigo_ibge].copy()

if len(df_clima_mun) == 0:
    st.warning(f"Sem dados climáticos para '{municipio_sel}'.")
    st.stop()

# ── Bloco de gestão de perfis ─────────────────────────────────────────────────
st.markdown("### 🎯 Perfis de comparação")
st.caption(
    "Cada perfil filtra o histórico por intervalo de anos, fase e intensidade ENSO. "
    "De 2 a 6 perfis ativos. A faixa p10–p90 mostra a variabilidade interanual."
)

n_perfis = len(st.session_state["perfis"])
for i in range(n_perfis):
    perfil = st.session_state["perfis"][i]
    expanded = i == n_perfis - 1

    with st.expander(f"🎯 {perfil['nome']}", expanded=expanded):
        col_cfg, col_rm = st.columns([5, 1])

        with col_cfg:
            r1, r2 = st.columns(2)
            with r1:
                novo_nome = st.text_input("Nome do perfil", perfil["nome"], key=f"nome_{i}")
            with r2:
                anos = st.slider(
                    "Intervalo de anos", ANO_MIN, ANO_MAX,
                    value=tuple(perfil["anos"]), key=f"anos_{i}",
                )

            r3, r4 = st.columns(2)
            with r3:
                fases = st.multiselect(
                    "Fase(s) ENSO (vazio = todas)",
                    ["El Niño", "La Niña", "Neutro"],
                    default=perfil["fases"], key=f"fases_{i}",
                )
            with r4:
                apenas_neutro = fases == ["Neutro"]
                intensidades = st.multiselect(
                    "Intensidade(s) (vazio = todas)",
                    ["Fraca", "Moderada", "Forte", "Muito Forte"],
                    default=[] if apenas_neutro else perfil["intensidades"],
                    key=f"int_{i}",
                    disabled=apenas_neutro,
                    help="Ignorada quando apenas 'Neutro' está selecionado.",
                )

        with col_rm:
            st.markdown(" ")
            st.markdown(" ")
            if st.button("🗑️", key=f"rm_{i}",
                         disabled=len(st.session_state["perfis"]) <= 2,
                         help="Remover perfil (mínimo: 2)"):
                st.session_state["perfis"].pop(i)
                st.rerun()

        st.session_state["perfis"][i] = {
            "nome": novo_nome,
            "anos": tuple(anos),
            "fases": fases,
            "intensidades": intensidades,
        }

# ── Botão adicionar perfil ────────────────────────────────────────────────────
btn_col, cap_col = st.columns([1, 4])
with btn_col:
    if st.button(
        "➕ Adicionar perfil",
        disabled=len(st.session_state["perfis"]) >= 6,
        help="Máximo de 6 perfis",
    ):
        st.session_state["perfis"].append({
            "nome": f"Perfil {len(st.session_state['perfis']) + 1}",
            "anos": (2010, 2025),
            "fases": [],
            "intensidades": [],
        })
        st.rerun()
with cap_col:
    st.caption(f"{len(st.session_state['perfis'])} de 6 perfis ativos")

st.markdown("---")

# ── Gráfico de comparação ─────────────────────────────────────────────────────
st.markdown(f"### 📊 {VARIAVEIS[variavel_key]} — {municipio_sel}/{estado_sel}")

fig = go.Figure()
resumo_rows = []

for i, perfil in enumerate(st.session_state["perfis"]):
    df_agg = agregar_perfil_decendial(
        df_clima_mun,
        anos=perfil["anos"],
        fases=perfil["fases"],
        intensidades=perfil["intensidades"],
        variavel=variavel_key,
    )

    if df_agg.empty:
        st.warning(f"⚠️ Perfil **{perfil['nome']}**: sem dados para os filtros selecionados.")
        continue

    cor = PALETA_PERFIS[i % len(PALETA_PERFIS)]
    n_min = int(df_agg["n_anos"].min())
    nome_legenda = perfil["nome"] + (" ⚠️" if n_min < 3 else "")

    # Faixa p10-p90
    if mostrar_faixa:
        fill_rgba = _hex_to_rgba(cor, 0.12)
        fig.add_trace(go.Scatter(
            x=df_agg["decendio"].tolist(), y=df_agg["p90"].tolist(),
            mode="lines", line=dict(width=0),
            showlegend=False, hoverinfo="skip",
            legendgroup=f"perfil_{i}",
        ))
        fig.add_trace(go.Scatter(
            x=df_agg["decendio"].tolist(), y=df_agg["p10"].tolist(),
            mode="lines", line=dict(width=0),
            fill="tonexty", fillcolor=fill_rgba,
            showlegend=False, hoverinfo="skip",
            legendgroup=f"perfil_{i}",
        ))

    # Linha da média
    fig.add_trace(go.Scatter(
        x=df_agg["decendio"].tolist(),
        y=df_agg["media"].tolist(),
        mode="lines+markers",
        name=nome_legenda,
        line=dict(color=cor, width=2.5),
        marker=dict(size=4),
        legendgroup=f"perfil_{i}",
        customdata=df_agg[["n_anos", "p10", "p50", "p90"]].values,
        hovertemplate=(
            f"<b>{perfil['nome']}</b><br>"
            "Decêndio %{x}<br>"
            f"Média: %{{y:.1f}} {ROTULOS_VAR[variavel_key].split('(')[-1].rstrip(')')}<br>"
            "Mediana: %{customdata[2]:.1f}<br>"
            "p10–p90: %{customdata[1]:.1f} – %{customdata[3]:.1f}<br>"
            "n=%{customdata[0]} anos<extra></extra>"
        ),
    ))

    # Linha para tabela-resumo
    n_anos_unicos = int(
        df_clima_mun[
            df_clima_mun["flag_cobertura"] == "OK"
        ]["ano"].between(perfil["anos"][0], perfil["anos"][1]).sum() > 0
        and df_agg["n_anos"].max()
    )
    if variavel_key == "prec_media":
        val_resumo = f"{df_agg['media'].sum():.0f} mm/ano"
        dec_max = int(df_agg.loc[df_agg["media"].idxmax(), "decendio"])
        dec_min = int(df_agg.loc[df_agg["media"].idxmin(), "decendio"])
    else:
        val_resumo = f"{df_agg['media'].mean():.1f} °C (média anual)"
        dec_max = int(df_agg.loc[df_agg["media"].idxmax(), "decendio"])
        dec_min = int(df_agg.loc[df_agg["media"].idxmin(), "decendio"])

    resumo_rows.append({
        "Perfil":        perfil["nome"],
        "Anos":          f"{perfil['anos'][0]}–{perfil['anos'][1]}",
        "Fases":         ", ".join(perfil["fases"]) or "Todas",
        "Intens.":       ", ".join(perfil["intensidades"]) or "Todas",
        "n máx/dec":     int(df_agg["n_anos"].max()),
        "Resumo anual":  val_resumo,
        "Dec. + alto":   f"D{dec_max}",
        "Dec. + baixo":  f"D{dec_min}",
    })

fig.update_layout(
    xaxis=dict(
        title="Decêndio do ano",
        tickmode="array",
        tickvals=list(MESES_DECENDIOS.keys()),
        ticktext=list(MESES_DECENDIOS.values()),
        tickangle=0,
        showgrid=True, gridcolor="#eee",
    ),
    yaxis=dict(
        title=ROTULOS_VAR[variavel_key],
        showgrid=True, gridcolor="#eee",
        zeroline=False,
    ),
    hovermode="x unified",
    height=520,
    margin=dict(t=30, b=40, l=60, r=20),
    legend=dict(
        orientation="h", yanchor="bottom", y=1.02,
        xanchor="left", x=0, font=dict(size=11),
    ),
    plot_bgcolor="white",
    paper_bgcolor="white",
    font=dict(family="DM Sans"),
)

st.plotly_chart(fig, use_container_width=True)

# ── Tabela-resumo ─────────────────────────────────────────────────────────────
if resumo_rows:
    st.markdown("### 📋 Resumo dos perfis")
    st.dataframe(
        pd.DataFrame(resumo_rows),
        hide_index=True,
        use_container_width=True,
    )

# ── Rodapé técnico ────────────────────────────────────────────────────────────
st.markdown("---")
with st.expander("ℹ️ Notas técnicas", expanded=False):
    st.markdown("""
**Metodologia:**

- **Filtro de cobertura:** apenas registros com `flag_cobertura == 'OK'` são incluídos em cada perfil.
- **Faixa p10–p90:** representa a variabilidade interanual dentro dos filtros do perfil (não é incerteza da estimativa da média).
- **n < 3 em algum decêndio:** perfil marcado com ⚠️ na legenda — interprete com cautela.
- **"Intensidade" ignorada para Neutro:** registros com `enso_fenomeno == 'Neutro'` não têm intensidade ENSO definida e são incluídos sempre que "Neutro" está entre as fases selecionadas.
- **Variável "Chuva":** valor decendial = precipitação acumulada nos ~10 dias do decêndio (mm).
- **Escala temporal:** cada decêndio representa aproximadamente 10 dias; 36 decêndios = 1 ano.
    """)

st.markdown(
    "<div style='text-align:center;color:#8a9e8f;font-size:0.82rem;padding:0.5rem 0'>"
    "Dados: INMET · IBGE · EMBRAPA &nbsp;·&nbsp; "
    "Projeto Integrador — Big Data &nbsp;·&nbsp; 2025"
    "</div>",
    unsafe_allow_html=True,
)
