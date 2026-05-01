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

# ── Funções de cálculo e renderização ────────────────────────────────────────

def calcular_serie_perfil(
    perfil: dict, df_clima_mun: pd.DataFrame, variavel: str
) -> pd.DataFrame:
    """Despacha para a função de agregação correta e retorna DataFrame com
    colunas posicao, media e opcionalmente p10, p50, p90, n.
    Usa mes_ini_idx, mes_fim_idx, cruza_ano e safras_all do escopo da página."""
    tipo = perfil["tipo"]

    if tipo == "faixa":
        df_agg = agregar_perfil_decendial(
            df_clima_mun, perfil["anos"], perfil["fases"],
            perfil["intensidades"], variavel,
        )
        if df_agg.empty:
            return pd.DataFrame(columns=["posicao", "media", "p10", "p50", "p90", "n"])
        return (
            df_agg
            .rename(columns={"decendio": "posicao", "n_anos": "n"})
            [["posicao", "media", "p10", "p50", "p90", "n"]]
        )

    if tipo == "unico_civil":
        sub = df_clima_mun[
            (df_clima_mun["flag_cobertura"] == "OK")
            & (df_clima_mun["ano"] == perfil["ano"])
        ][["decendio", variavel]].copy()
        if sub.empty:
            return pd.DataFrame(columns=["posicao", "media", "n"])
        return (
            sub.rename(columns={"decendio": "posicao", variavel: "media"})
               .assign(n=1)
               .sort_values("posicao")
               .reset_index(drop=True)
        )

    if tipo == "faixa_safra":
        decs = decendios_da_safra(mes_ini_idx, mes_fim_idx)
        sr = perfil.get("safras_range")
        if sr:
            r_ini, r_fim = sr
            i_ini = next((i for i, s in enumerate(safras_all) if s[0] == r_ini), 0)
            i_fim = next(
                (i for i, s in enumerate(safras_all) if s[0] == r_fim),
                len(safras_all) - 1,
            )
            safras_subset = safras_all[i_ini: i_fim + 1]
        else:
            safras_subset = safras_all
        df_agg = agregar_perfil_safra_faixa(
            df_clima_mun, safras_subset, perfil["fases"],
            perfil["intensidades"], decs, cruza_ano, variavel,
        )
        if df_agg.empty:
            return pd.DataFrame(columns=["posicao", "media", "p10", "p50", "p90", "n"])
        return (
            df_agg
            .rename(columns={"posicao_safra": "posicao", "n_safras": "n"})
            [["posicao", "media", "p10", "p50", "p90", "n"]]
        )

    if tipo == "unica_safra":
        decs = decendios_da_safra(mes_ini_idx, mes_fim_idx)
        safra_obj = next((s for s in safras_all if s[0] == perfil["safra"]), None)
        if safra_obj is None:
            return pd.DataFrame(columns=["posicao", "media", "n"])
        df_agg = agregar_perfil_safra_unica(
            df_clima_mun, safra_obj, decs, cruza_ano, variavel,
        )
        if df_agg.empty:
            return pd.DataFrame(columns=["posicao", "media", "n"])
        return df_agg.rename(columns={"posicao_safra": "posicao"}).assign(n=1)

    return pd.DataFrame(columns=["posicao", "media"])


def construir_grafico_decendial(
    perfis, df_clima_mun, variavel,
    modo_temporal, mes_ini, mes_fim, cruza_ano,
    rotulos_dec, mostrar_faixa,
):
    n_pos = len(rotulos_dec)
    dividir = n_pos >= 18
    metade = n_pos // 2

    if dividir:
        pos_p1 = list(range(1, metade + 1))
        pos_p2 = list(range(metade + 1, n_pos + 1))
        rot_p1 = rotulos_dec[:metade]
        rot_p2 = rotulos_dec[metade:]
        fig = make_subplots(
            rows=2, cols=1,
            row_heights=[0.5, 0.5],
            vertical_spacing=0.18,
            subplot_titles=(
                f"1ª metade ({rot_p1[0]} → {rot_p1[-1]})",
                f"2ª metade ({rot_p2[0]} → {rot_p2[-1]})",
            ),
            shared_yaxes=True,
        )
    else:
        fig = make_subplots(rows=1, cols=1)
        pos_p1 = list(range(1, n_pos + 1))
        pos_p2 = []
        rot_p1 = rotulos_dec
        rot_p2 = []

    modo_barras = eh_variavel_de_fluxo(variavel)

    for i, perfil in enumerate(perfis):
        df_serie = calcular_serie_perfil(perfil, df_clima_mun, variavel)
        if df_serie.empty:
            st.warning(
                f"⚠️ Perfil **{perfil['nome']}**: sem dados para os filtros selecionados."
            )
            continue
        cor = PALETA_PERFIS[i % len(PALETA_PERFIS)]
        eh_unico = perfil["tipo"] in ("unico_civil", "unica_safra")
        nome = f"🎯 {perfil['nome']}" if eh_unico else perfil["nome"]
        if not eh_unico and "n" in df_serie.columns and int(df_serie["n"].min()) < 3:
            nome = f"{nome} ⚠️"

        # _plot_em usa defaults para capturar variáveis do loop sem closure-bug
        def _plot_em(
            rows_pos, row_idx,
            _df=df_serie, _cor=cor, _nome=nome, _eh_unico=eh_unico,
        ):
            sub = _df[_df["posicao"].isin(rows_pos)]
            if sub.empty:
                return
            tem_faixa = (
                mostrar_faixa and not _eh_unico
                and "p10" in sub.columns and "p90" in sub.columns
            )
            if modo_barras:
                error_y = None
                if tem_faixa:
                    error_y = dict(
                        type="data", symmetric=False,
                        array=(sub["p90"] - sub["media"]).values,
                        arrayminus=(sub["media"] - sub["p10"]).values,
                        color=_hex_to_rgba(_cor, 0.55),
                        thickness=1.2, width=3,
                    )
                fig.add_trace(
                    go.Bar(
                        x=sub["posicao"], y=sub["media"],
                        name=_nome, marker_color=_cor,
                        error_y=error_y,
                        legendgroup=_nome,
                        showlegend=(row_idx == 1),
                    ),
                    row=row_idx, col=1,
                )
            else:
                if tem_faixa:
                    fig.add_trace(
                        go.Scatter(
                            x=sub["posicao"], y=sub["p90"],
                            mode="lines", line=dict(width=0),
                            showlegend=False, hoverinfo="skip",
                            legendgroup=_nome,
                        ),
                        row=row_idx, col=1,
                    )
                    fig.add_trace(
                        go.Scatter(
                            x=sub["posicao"], y=sub["p10"],
                            mode="lines", line=dict(width=0),
                            fill="tonexty",
                            fillcolor=_hex_to_rgba(_cor, 0.15),
                            showlegend=False, hoverinfo="skip",
                            legendgroup=_nome,
                        ),
                        row=row_idx, col=1,
                    )
                fig.add_trace(
                    go.Scatter(
                        x=sub["posicao"], y=sub["media"],
                        mode="lines+markers",
                        name=_nome,
                        line=dict(
                            color=_cor, width=2.5,
                            dash="dot" if _eh_unico else "solid",
                        ),
                        marker=dict(size=6 if _eh_unico else 5),
                        legendgroup=_nome,
                        showlegend=(row_idx == 1),
                    ),
                    row=row_idx, col=1,
                )

        if dividir:
            _plot_em(pos_p1, 1)
            _plot_em(pos_p2, 2)
        else:
            _plot_em(pos_p1, 1)

    _grid = dict(showgrid=True, gridcolor="#eee")
    if dividir:
        fig.update_xaxes(
            tickmode="array", tickvals=pos_p1, ticktext=rot_p1,
            tickangle=-45, tickfont=dict(size=10),
            range=[0.4, metade + 0.6], **_grid,
            row=1, col=1,
        )
        fig.update_xaxes(
            tickmode="array", tickvals=pos_p2, ticktext=rot_p2,
            tickangle=-45, tickfont=dict(size=10),
            title_text="Decêndio",
            range=[metade + 0.4, n_pos + 0.6], **_grid,
            row=2, col=1,
        )
        for r in (1, 2):
            fig.update_yaxes(
                title_text=ROTULO_VARIAVEIS[variavel],
                zeroline=False, **_grid,
                row=r, col=1,
            )
    else:
        fig.update_xaxes(
            tickmode="array", tickvals=pos_p1, ticktext=rot_p1,
            tickangle=-45, tickfont=dict(size=10),
            title_text="Decêndio", **_grid,
        )
        fig.update_yaxes(
            title_text=ROTULO_VARIAVEIS[variavel],
            zeroline=False, **_grid,
        )

    fig.update_layout(
        barmode="group" if modo_barras else "overlay",
        bargap=0.20, bargroupgap=0.05,
        height=720 if dividir else 460,
        margin=dict(t=70, b=80, l=70, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="left", x=0),
        hovermode="x unified",
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="DM Sans"),
    )
    return fig


def construir_grafico_mensal(
    perfis, df_clima_mun, variavel,
    modo_temporal, mes_ini, mes_fim, cruza_ano,
):
    modo_agg = "soma" if eh_variavel_de_fluxo(variavel) else "media"

    if modo_temporal == "Ano civil (Jan → Dez)":
        decs_eixo = list(range(1, 37))
        n_meses_total = 12
        rotulos_meses = [MESES_NOMES_CURTOS[m] for m in range(1, 13)]
    else:
        decs_eixo = decendios_da_safra(mes_ini, mes_fim)
        n_meses_total = len(decs_eixo) // 3
        rotulos_meses = [
            MESES_NOMES_CURTOS[((decs_eixo[k * 3] - 1) // 3) + 1]
            for k in range(n_meses_total)
        ]

    fig = go.Figure()
    for i, perfil in enumerate(perfis):
        df_serie = calcular_serie_perfil(perfil, df_clima_mun, variavel)
        if df_serie.empty:
            continue
        cor = PALETA_PERFIS[i % len(PALETA_PERFIS)]
        eh_unico = perfil["tipo"] in ("unico_civil", "unica_safra")
        nome = f"🎯 {perfil['nome']}" if eh_unico else perfil["nome"]

        df_mensal = agregar_mensal_de_safra(
            df_serie.rename(columns={"posicao": "posicao_safra"}),
            decs_eixo, modo_agg,
        )
        if df_mensal.empty:
            continue

        fig.add_trace(
            go.Bar(
                x=df_mensal["posicao_mes"],
                y=df_mensal["valor"],
                name=nome,
                marker_color=cor,
                hovertemplate=(
                    f"<b>{nome}</b><br>"
                    "Mês %{x} (%{customdata})<br>"
                    + ("Acumulado: %{y:.0f} mm" if modo_agg == "soma"
                       else "Média: %{y:.1f}°C")
                    + "<extra></extra>"
                ),
                customdata=df_mensal["mes_rotulo"],
            )
        )

    rotulo_y = ROTULO_VARIAVEIS[variavel]
    unidade = rotulo_y.split("(")[-1].rstrip(")")
    fig.update_layout(
        barmode="group", bargap=0.18, bargroupgap=0.04,
        xaxis=dict(
            title="Mês",
            tickmode="array",
            tickvals=list(range(1, n_meses_total + 1)),
            ticktext=rotulos_meses,
        ),
        yaxis_title=(
            "Acumulado mensal (mm)" if modo_agg == "soma"
            else f"Média mensal ({unidade})"
        ),
        height=480,
        margin=dict(t=50, b=50, l=70, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="left", x=0),
        hovermode="x unified",
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="DM Sans"),
    )
    return fig


def construir_tabela_mensal(
    perfis, df_clima_mun, variavel,
    modo_temporal, mes_ini, mes_fim, cruza_ano,
):
    modo_agg = "soma" if eh_variavel_de_fluxo(variavel) else "media"

    if modo_temporal == "Ano civil (Jan → Dez)":
        decs_eixo = list(range(1, 37))
        n_meses_total = 12
        rotulos = [MESES_NOMES_CURTOS[m] for m in range(1, 13)]
    else:
        decs_eixo = decendios_da_safra(mes_ini, mes_fim)
        n_meses_total = len(decs_eixo) // 3
        rotulos = [
            MESES_NOMES_CURTOS[((decs_eixo[k * 3] - 1) // 3) + 1]
            for k in range(n_meses_total)
        ]

    dados: dict = {"Mês": rotulos}
    for perfil in perfis:
        df_serie = calcular_serie_perfil(perfil, df_clima_mun, variavel)
        nome_col = perfil["nome"]
        if df_serie.empty:
            dados[nome_col] = ["—"] * n_meses_total
            continue
        df_mensal = agregar_mensal_de_safra(
            df_serie.rename(columns={"posicao": "posicao_safra"}),
            decs_eixo, modo_agg,
        )
        if df_mensal.empty:
            dados[nome_col] = ["—"] * n_meses_total
            continue
        valores = df_mensal.set_index("posicao_mes")["valor"]
        dados[nome_col] = [
            f"{valores[m]:.1f}" if m in valores.index else "—"
            for m in range(1, n_meses_total + 1)
        ]

    df_tab = pd.DataFrame(dados)
    if modo_agg == "soma":
        total_row: dict = {"Mês": "TOTAL"}
        for col in df_tab.columns[1:]:
            try:
                total_row[col] = f"{pd.to_numeric(df_tab[col], errors='coerce').sum():.0f}"
            except Exception:
                total_row[col] = "—"
        df_tab = pd.concat([df_tab, pd.DataFrame([total_row])], ignore_index=True)
    return df_tab


# ── Eixo X (rótulos dependem do modo) ────────────────────────────────────────
if modo_temporal == "Ano civil (Jan → Dez)":
    n_pos = 36
    rotulos_dec = [
        f"{MESES_NOMES_CURTOS[((d-1)//3)+1]}-D{((d-1)%3)+1}"
        for d in range(1, 37)
    ]
else:
    _decs_eixo = decendios_da_safra(mes_ini_idx, mes_fim_idx)
    n_pos = len(_decs_eixo)
    rotulos_dec = rotulos_eixo_safra(_decs_eixo)

modo_barras = eh_variavel_de_fluxo(variavel_key)

if modo_barras and mostrar_faixa and len(st.session_state["perfis"]) > 3:
    st.info(
        "💡 Com mais de 3 perfis, sugerimos desativar **Mostrar faixa p10–p90** "
        "para o gráfico de barras ficar mais legível."
    )

# ── Abas ─────────────────────────────────────────────────────────────────────
aba_dec, aba_mes = st.tabs(["📅 Visão decendial", "📊 Visão mensal"])

with aba_dec:
    st.markdown(f"#### {ROTULO_VARIAVEIS[variavel_key]} — {nome_municipio}/{uf}")
    fig_dec = construir_grafico_decendial(
        st.session_state["perfis"], df_clima_mun, variavel_key,
        modo_temporal, mes_ini_idx, mes_fim_idx, cruza_ano,
        rotulos_dec, mostrar_faixa,
    )
    st.plotly_chart(fig_dec, use_container_width=True)
    st.caption(
        "📅 **D1, D2, D3** indicam o 1º, 2º e 3º decêndio do mês (~10 dias cada). "
        "Ex.: *Jan-D1* = 1 a 10 de janeiro."
    )

with aba_mes:
    st.markdown(f"#### Resumo mensal — {nome_municipio}/{uf}")
    fig_mes = construir_grafico_mensal(
        st.session_state["perfis"], df_clima_mun, variavel_key,
        modo_temporal, mes_ini_idx, mes_fim_idx, cruza_ano,
    )
    st.plotly_chart(fig_mes, use_container_width=True)
    df_tab = construir_tabela_mensal(
        st.session_state["perfis"], df_clima_mun, variavel_key,
        modo_temporal, mes_ini_idx, mes_fim_idx, cruza_ano,
    )
    st.dataframe(df_tab, hide_index=True, use_container_width=True)

# ── Rodapé ────────────────────────────────────────────────────────────────────
st.markdown("---")
with st.expander("ℹ️ Notas técnicas", expanded=False):
    st.markdown("""
**Metodologia:**

- **Filtro de cobertura:** apenas registros com `flag_cobertura == 'OK'` são incluídos.
- **Faixa p10–p90:** variabilidade interanual dentro dos filtros do perfil (não é incerteza da média).
- **n < 3 em algum decêndio:** perfil marcado com ⚠️ na legenda — interprete com cautela.
- **Perfil único (🎯):** refere-se a um único ano ou safra — sem faixa de incerteza, linha tracejada.
- **ENSO predominante (modo Safra):** determinado pela moda dos registros dentro da janela da safra.
- **Modo Safra cruzando ano:** safra 2015/16 = outubro de 2015 até março de 2016.
- **Aba Mensal / linha TOTAL:** soma dos acumulados mensais (apenas para precipitação).
    """)

st.markdown(
    "<div style='text-align:center;color:#8a9e8f;font-size:0.82rem;padding:0.5rem 0'>"
    "Dados: INMET · IBGE · EMBRAPA &nbsp;·&nbsp; "
    "Projeto Integrador — Big Data &nbsp;·&nbsp; 2025"
    "</div>",
    unsafe_allow_html=True,
)
