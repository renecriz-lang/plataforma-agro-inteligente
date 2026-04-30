"""
Comparador de Cenários Climáticos — Modo Ano Civil + Modo Safra Customizada.

Permite criar até 6 perfis (faixa ou pontual) e compará-los em gráficos
decendiais e mensais. Suporta safras que cruzam a virada do ano.
"""

import os
import sys

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))

from utils.design import inject_css, hero_banner
from utils.data_loader import load_base, carregar_base_clima_compacta
from utils.resiliencia_enso import (
    agregar_perfil_decendial,
    decendios_da_safra,
    safras_disponiveis,
    agregar_perfil_safra_faixa,
    agregar_perfil_safra_unica,
    rotulos_eixo_safra,
    agregar_mensal_de_safra,
    MESES_NOMES_CURTOS,
)

# ── Configuração ──────────────────────────────────────────────────────────────
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
        "(intervalo de anos/safras × fase ENSO × intensidade) em gráficos decendiais e mensais"
    ),
    icon="📈",
)

# ── Constantes ────────────────────────────────────────────────────────────────
PALETA_PERFIS = ["#2d6a4f", "#d1495b", "#2e86ab", "#c9963a", "#7d4f9e", "#3a7d44"]

VARIAVEIS = {
    "prec_media": "🌧️ Chuva acumulada por decêndio (mm)",
    "tmax_media": "🌡️ Temperatura máxima média (°C)",
    "tmed_media": "🌡️ Temperatura média (°C)",
    "tmin_media": "🌡️ Temperatura mínima média (°C)",
}
ROTULO_VARIAVEIS = {
    "prec_media": "Precipitação (mm/decêndio)",
    "tmax_media": "Tmax média (°C)",
    "tmed_media": "Tméd média (°C)",
    "tmin_media": "Tmin média (°C)",
}

VARIAVEIS_FLUXO = {"prec_media"}


def eh_variavel_de_fluxo(v: str) -> bool:
    return v in VARIAVEIS_FLUXO


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


ANO_MIN, ANO_MAX = 2000, 2025

MESES = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]

PERFIS_DEFAULT_CIVIL: list[dict] = [
    {"nome": "Média geral 2010–2025", "tipo": "faixa",
     "anos": (2010, 2025), "fases": [], "intensidades": []},
    {"nome": "Anos La Niña", "tipo": "faixa",
     "anos": (2000, 2025), "fases": ["La Niña"], "intensidades": []},
    {"nome": "Anos El Niño", "tipo": "faixa",
     "anos": (2000, 2025), "fases": ["El Niño"], "intensidades": []},
]

PERFIS_DEFAULT_SAFRA: list[dict] = [
    {"nome": "Média geral", "tipo": "faixa_safra",
     "safras_range": None, "fases": [], "intensidades": []},
    {"nome": "Safras La Niña", "tipo": "faixa_safra",
     "safras_range": None, "fases": ["La Niña"], "intensidades": []},
    {"nome": "Safras El Niño", "tipo": "faixa_safra",
     "safras_range": None, "fases": ["El Niño"], "intensidades": []},
]

# ── Session state ─────────────────────────────────────────────────────────────
if "perfis" not in st.session_state:
    st.session_state["perfis"] = [p.copy() for p in PERFIS_DEFAULT_CIVIL]
if "ultimo_modo" not in st.session_state:
    st.session_state["ultimo_modo"] = "Ano civil (Jan → Dez)"

# ── Referência ────────────────────────────────────────────────────────────────
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
        current_mode = st.session_state.get("modo_temporal", "Ano civil (Jan → Dez)")
        st.session_state["perfis"] = (
            [p.copy() for p in PERFIS_DEFAULT_CIVIL]
            if current_mode == "Ano civil (Jan → Dez)"
            else [p.copy() for p in PERFIS_DEFAULT_SAFRA]
        )
        st.rerun()

# ── Município → código IBGE ───────────────────────────────────────────────────
row_mun = df_ref[df_ref["nome"] == municipio_sel]
if row_mun.empty:
    st.warning(f"Município '{municipio_sel}' não encontrado.")
    st.stop()
codigo_ibge = str(row_mun["codigo_ibge"].iloc[0])
nome_municipio = municipio_sel
uf = estado_sel

# ── Base climática ────────────────────────────────────────────────────────────
with st.spinner("Carregando base climática histórica…"):
    df_clima = carregar_base_clima_compacta()
df_clima_mun = df_clima[df_clima["codigo_ibge"].astype(str) == codigo_ibge].copy()
if len(df_clima_mun) == 0:
    st.warning(f"Sem dados climáticos para '{municipio_sel}'.")
    st.stop()

# ── Modo de análise temporal ──────────────────────────────────────────────────
st.markdown("### Modo de análise temporal")
col_modo, _ = st.columns([3, 1])
with col_modo:
    modo_temporal = st.radio(
        "Como apresentar os dados ao longo do tempo?",
        options=["Ano civil (Jan → Dez)", "Safra (customizada)"],
        horizontal=True,
        key="modo_temporal",
        help=(
            "Ano civil: cada bloco temporal vai de janeiro a dezembro. "
            "Safra: você define o mês de início e fim — pode atravessar a "
            "virada do ano (ex.: out → mar)."
        ),
    )

if modo_temporal == "Safra (customizada)":
    col_a, col_b, col_c = st.columns([2, 2, 3])
    with col_a:
        mes_ini_nome = st.selectbox(
            "Mês de início", MESES, index=9, key="mes_ini_safra",
        )
    with col_b:
        n_meses = st.number_input(
            "Duração (meses)",
            min_value=1, max_value=12, value=6, step=1,
            key="n_meses_safra",
            help="Quantos meses dura a safra a partir do mês de início.",
        )
    with col_c:
        mes_ini_idx = MESES.index(mes_ini_nome) + 1
        mes_fim_idx_bruto = mes_ini_idx + int(n_meses) - 1
        cruza_ano = mes_fim_idx_bruto > 12
        mes_fim_idx = mes_fim_idx_bruto if not cruza_ano else mes_fim_idx_bruto - 12
        mes_fim_nome = MESES[mes_fim_idx - 1]
        st.metric(
            "Janela da safra",
            f"{mes_ini_nome} → {mes_fim_nome}",
            help=f"{int(n_meses)} meses · {int(n_meses) * 3} decêndios",
        )
        if cruza_ano:
            st.caption(
                f"⚙️ A safra cruza a virada do ano. "
                f"Rótulo de exemplo: **2015/16** = {mes_ini_nome} de 2015 → "
                f"{mes_fim_nome} de 2016."
            )
else:
    mes_ini_idx, mes_fim_idx, cruza_ano, n_meses = 1, 12, False, 12

st.session_state["mes_ini_idx"] = mes_ini_idx
st.session_state["mes_fim_idx"] = mes_fim_idx
st.session_state["cruza_ano"]   = cruza_ano
st.session_state["n_meses"]     = int(n_meses)

# Reseta perfis ao trocar modo
if st.session_state["ultimo_modo"] != modo_temporal:
    st.session_state["perfis"] = (
        [p.copy() for p in PERFIS_DEFAULT_CIVIL]
        if modo_temporal == "Ano civil (Jan → Dez)"
        else [p.copy() for p in PERFIS_DEFAULT_SAFRA]
    )
    st.session_state["ultimo_modo"] = modo_temporal

st.divider()

# ── Editor de perfis ──────────────────────────────────────────────────────────
st.markdown("### 🎯 Perfis de comparação")
st.caption(
    "Cada perfil define um subconjunto do histórico climático para comparação. "
    "De 2 a 6 perfis ativos."
)

safras_all = safras_disponiveis(ANO_MIN, ANO_MAX, mes_ini_idx, mes_fim_idx, cruza_ano)
rotulos_safras = [s[0] for s in safras_all]

n_perfis = len(st.session_state["perfis"])
for i in range(n_perfis):
    perfil = st.session_state["perfis"][i]
    with st.expander(f"🎯 {perfil['nome']}", expanded=(i == n_perfis - 1)):
        col1, col2 = st.columns([4, 1])
        with col1:
            novo_nome = st.text_input(
                "Nome do perfil", perfil["nome"], key=f"nome_{i}"
            )

            if modo_temporal == "Ano civil (Jan → Dez)":
                tipo_label = st.radio(
                    "Tipo",
                    ["Faixa de anos (média + faixa de incerteza)", "Ano único"],
                    horizontal=True, key=f"tipo_{i}",
                    index=0 if perfil.get("tipo", "faixa") == "faixa" else 1,
                )
                if tipo_label.startswith("Faixa"):
                    anos = st.slider(
                        "Intervalo de anos", ANO_MIN, ANO_MAX,
                        value=tuple(perfil.get("anos", (2010, 2025))),
                        key=f"anos_{i}",
                    )
                    fases = st.multiselect(
                        "Fase(s) ENSO (vazio = todas)",
                        ["El Niño", "La Niña", "Neutro"],
                        default=perfil.get("fases", []),
                        key=f"fases_{i}",
                    )
                    intensidades = st.multiselect(
                        "Intensidade(s) (vazio = todas; ignorada para Neutro)",
                        ["Fraca", "Moderada", "Forte", "Muito Forte"],
                        default=perfil.get("intensidades", []),
                        key=f"int_{i}",
                        disabled=(fases == ["Neutro"]),
                    )
                    st.session_state["perfis"][i] = {
                        "nome": novo_nome, "tipo": "faixa",
                        "anos": tuple(anos), "fases": fases,
                        "intensidades": intensidades,
                    }
                else:
                    anos_lista = list(range(ANO_MIN, ANO_MAX + 1))
                    idx_default = (
                        anos_lista.index(perfil["ano"])
                        if "ano" in perfil and perfil["ano"] in anos_lista
                        else len(anos_lista) - 1
                    )
                    ano_unico = st.selectbox(
                        "Ano", anos_lista, index=idx_default, key=f"ano_unico_{i}",
                    )
                    st.session_state["perfis"][i] = {
                        "nome": novo_nome, "tipo": "unico_civil", "ano": ano_unico,
                    }

            else:  # Modo Safra
                tipo_label = st.radio(
                    "Tipo",
                    ["Faixa de safras (média + faixa de incerteza)", "Safra única"],
                    horizontal=True, key=f"tipo_{i}",
                    index=0 if perfil.get("tipo", "faixa_safra") == "faixa_safra" else 1,
                )

                if tipo_label.startswith("Faixa"):
                    sr = perfil.get("safras_range")
                    default_range = (
                        tuple(sr)
                        if sr and sr[0] in rotulos_safras and sr[1] in rotulos_safras
                        else (rotulos_safras[0], rotulos_safras[-1])
                    )
                    intervalo = st.select_slider(
                        "Intervalo de safras",
                        options=rotulos_safras,
                        value=default_range,
                        key=f"safras_range_{i}",
                    )
                    fases = st.multiselect(
                        "Fase(s) ENSO predominante na safra (vazio = todas)",
                        ["El Niño", "La Niña", "Neutro"],
                        default=perfil.get("fases", []),
                        key=f"fases_{i}",
                    )
                    intensidades = st.multiselect(
                        "Intensidade(s) ENSO (vazio = todas)",
                        ["Fraca", "Moderada", "Forte", "Muito Forte"],
                        default=perfil.get("intensidades", []),
                        key=f"int_{i}",
                        disabled=(fases == ["Neutro"]),
                    )
                    st.session_state["perfis"][i] = {
                        "nome": novo_nome, "tipo": "faixa_safra",
                        "safras_range": intervalo,
                        "fases": fases, "intensidades": intensidades,
                    }
                else:
                    default_safra = (
                        perfil["safra"]
                        if perfil.get("safra") in rotulos_safras
                        else rotulos_safras[-1]
                    )
                    safra_escolhida = st.selectbox(
                        "Safra", rotulos_safras,
                        index=rotulos_safras.index(default_safra),
                        key=f"safra_unica_{i}",
                    )
                    st.session_state["perfis"][i] = {
                        "nome": novo_nome, "tipo": "unica_safra",
                        "safra": safra_escolhida,
                    }

        with col2:
            st.markdown(" ")
            st.markdown(" ")
            if st.button(
                "🗑️ Remover", key=f"rm_{i}",
                disabled=len(st.session_state["perfis"]) <= 2,
                help="Remover perfil (mínimo: 2)",
            ):
                st.session_state["perfis"].pop(i)
                st.rerun()

# ── Botão adicionar perfil ────────────────────────────────────────────────────
col_btn, col_cap = st.columns([1, 4])
with col_btn:
    if st.button(
        "➕ Adicionar perfil",
        disabled=len(st.session_state["perfis"]) >= 6,
        help="Máximo de 6 perfis",
    ):
        if modo_temporal == "Ano civil (Jan → Dez)":
            novo: dict = {
                "nome": f"Perfil {len(st.session_state['perfis'])+1}",
                "tipo": "faixa", "anos": (2010, 2025),
                "fases": [], "intensidades": [],
            }
        else:
            novo = {
                "nome": f"Perfil {len(st.session_state['perfis'])+1}",
                "tipo": "faixa_safra", "safras_range": None,
                "fases": [], "intensidades": [],
            }
        st.session_state["perfis"].append(novo)
        st.rerun()
with col_cap:
    st.caption(f"{len(st.session_state['perfis'])} de 6 perfis ativos")

st.markdown("---")
st.info("📊 Gráficos em construção — próximo commit.")

st.markdown(
    "<div style='text-align:center;color:#8a9e8f;font-size:0.82rem;padding:0.5rem 0'>"
    "Dados: INMET · IBGE · EMBRAPA &nbsp;·&nbsp; "
    "Projeto Integrador — Big Data &nbsp;·&nbsp; 2025"
    "</div>",
    unsafe_allow_html=True,
)
