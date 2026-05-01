"""
Resiliência ENSO — análise climática descritiva e probabilística por fase ENSO.

4 painéis:
  A — Probabilidade dos eventos críticos por fase ENSO (Nível 1)
  B — Distribuição empírica condicional (Nível 2)
  C — Motor de análogos para o ano corrente (Nível 3)
  D — Validação produtiva — impacto no rendimento real (Nível 4)
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

from utils.design import inject_css, hero_banner, badge
from utils.data_loader import (
    load_base,
    carregar_base_clima_compacta,
    carregar_base_producao,
    carregar_resiliencia_precomp,
)
from utils.resiliencia_enso import (
    EVENTOS_PADRAO,
    CORES_ENSO,
    FASES_ENSO,
    filtrar_validos,
    probabilidades_por_enso,
    cdf_empirica,
    motor_analogos,
    projecao_dos_analogos,
    historico_climatologico,
    rendimento_por_enso,
    projecao_rendimento_analogos,
)

# ── Configuração ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Resiliência ENSO",
    page_icon="🌍",
    layout="wide",
)
inject_css()
hero_banner(
    title="Resiliência ENSO",
    subtitle="Probabilidades climáticas históricas e impacto produtivo por fase ENSO",
    icon="🌍",
)

CULTURAS = ["Soja", "Milho", "Feijão", "Trigo", "Cevada"]
ANO_CORRENTE = 2025

# ── Carga das bases leves (sempre disponíveis) ────────────────────────────────
df_ref   = load_base("media_geral")
df_prod  = carregar_base_producao()
df_precomp = carregar_resiliencia_precomp()

# ── Sidebar — seleções ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🌍 Resiliência ENSO")
    st.markdown("---")

    estados = sorted(df_ref["estado"].dropna().unique())
    estado_sel = st.selectbox("Estado (UF)", estados, index=estados.index("PR") if "PR" in estados else 0)

    muns_disp = (
        df_ref[df_ref["estado"] == estado_sel]
        .sort_values("nome")["nome"]
        .tolist()
    )
    municipio_sel = st.selectbox("Município", muns_disp)

    cultura_sel = st.selectbox("Cultura", CULTURAS, index=0)

    st.markdown("---")
    with st.expander("⚙️ Personalizar limites dos eventos", expanded=False):
        limites_custom: dict[str, float] = {}
        for ev_key, ev_cfg in EVENTOS_PADRAO.items():
            st.markdown(f"**{ev_cfg['rotulo']}**")
            st.caption(f"Referência: {ev_cfg['percentil_ref']}")
            step = 0.5 if ev_cfg["unidade"] == "°C" else 5.0
            lim_min = 0.0 if ev_cfg["unidade"] == "mm" else -5.0
            lim_max = 500.0 if ev_cfg["unidade"] == "mm" else 45.0
            limites_custom[ev_key] = st.slider(
                f"Limite ({ev_cfg['unidade']})",
                min_value=lim_min,
                max_value=lim_max,
                value=float(ev_cfg["limite_default"]),
                step=step,
                key=f"lim_{ev_key}",
            )

# ── Código IBGE do município selecionado ─────────────────────────────────────
row_mun = df_ref[df_ref["nome"] == municipio_sel]
if row_mun.empty:
    st.warning(f"Município '{municipio_sel}' não encontrado na base.")
    st.stop()

codigo_ibge = str(row_mun["codigo_ibge"].iloc[0])
alt_media   = row_mun["altitude_media"].iloc[0] if "altitude_media" in row_mun.columns else "—"
solo_dom    = row_mun["solo_1_ordem"].iloc[0] if "solo_1_ordem" in row_mun.columns else "—"

# ── Cartão de identidade do município ────────────────────────────────────────
st.markdown("### 📍 Município selecionado")
ci1, ci2, ci3, ci4 = st.columns(4)

# Anos de série climática (pré-comp base)
mun_precomp = df_precomp[df_precomp["codigo_ibge"] == codigo_ibge]
n_anos_clima = int(mun_precomp["n_anos"].max()) if len(mun_precomp) > 0 else "—"

# Anos de série produtiva
mun_prod = df_prod[
    (df_prod["codigo_ibge"] == codigo_ibge) &
    (df_prod["cultura"] == cultura_sel)
]
n_anos_prod = int(mun_prod["ano"].nunique()) if len(mun_prod) > 0 else 0

ci1.metric("Altitude média", f"{alt_media:.0f} m" if isinstance(alt_media, float) else str(alt_media))
ci2.metric("Solo dominante", str(solo_dom))
ci3.metric("Série climática", f"{n_anos_clima} anos")
ci4.metric(f"Série produtiva ({cultura_sel})", f"{n_anos_prod} anos")

st.markdown("---")

# ── Carrega base climática completa (33 MB, cached após 1ª vez) ───────────────
with st.spinner("Carregando base climática histórica…"):
    df_clima = carregar_base_clima_compacta()

df_clima_mun = df_clima[df_clima["codigo_ibge"].astype(str) == codigo_ibge].copy()

if len(df_clima_mun) == 0:
    st.warning(f"Sem dados climáticos para '{municipio_sel}' na base histórica.")
    st.stop()


# ────────────────────────────────────────────────────────────────────────────
# PAINEL A — Nível 1: Probabilidade dos eventos críticos por fase ENSO
# ────────────────────────────────────────────────────────────────────────────
st.markdown("## 📊 Painel A — Probabilidade de eventos críticos por fase ENSO")
st.caption(
    "Probabilidade histórica de cada evento climático ocorrer, "
    "condicionada à fase ENSO predominante do ano."
)

# Monta dict de eventos com limites customizados
eventos_ui: dict[str, dict] = {
    k: {**v, "limite": limites_custom.get(k, v["limite_default"])}
    for k, v in EVENTOS_PADRAO.items()
}

with st.spinner("Calculando probabilidades…"):
    df_prob = probabilidades_por_enso(df_clima_mun, eventos=eventos_ui)

if df_prob.empty:
    st.info("Dados insuficientes para calcular probabilidades neste município.")
else:
    ev_keys   = df_prob["evento_key"].unique().tolist()
    ev_rotulos = [EVENTOS_PADRAO[k]["rotulo"] for k in ev_keys]
    n_ev = len(ev_keys)

    fig_a = make_subplots(
        rows=1, cols=n_ev,
        subplot_titles=ev_rotulos,
        shared_yaxes=True,
    )

    for col_idx, ev_key in enumerate(ev_keys, start=1):
        ev_df = df_prob[df_prob["evento_key"] == ev_key]
        for _, row in ev_df.iterrows():
            fase = row["fase_enso"]
            if fase == "TODOS":
                continue
            cor = CORES_ENSO.get(fase, "#888")
            prob = row["probabilidade"]
            n    = int(row["n_anos"])
            lo   = row["ic95_inf"]
            hi   = row["ic95_sup"]
            aviso = " ⚠️" if n < 5 else ""

            fig_a.add_trace(
                go.Bar(
                    x=[fase],
                    y=[prob],
                    name=fase,
                    marker_color=cor,
                    error_y=dict(
                        type="data",
                        symmetric=False,
                        array=[hi - prob],
                        arrayminus=[prob - lo],
                        visible=True,
                        color="#333",
                        thickness=1.5,
                        width=4,
                    ),
                    text=[f"n={n}{aviso}"],
                    textposition="outside",
                    hovertemplate=(
                        f"<b>{fase}</b><br>"
                        f"Probabilidade: {prob:.1%}<br>"
                        f"IC 95%: [{lo:.1%}, {hi:.1%}]<br>"
                        f"Anos: {n}<br>"
                        + ("⚠️ Amostra pequena — intervalos largos" if n < 5 else "")
                        + "<extra></extra>"
                    ),
                    showlegend=(col_idx == 1),
                    legendgroup=fase,
                ),
                row=1, col=col_idx,
            )

    fig_a.update_layout(
        height=420,
        barmode="group",
        yaxis=dict(tickformat=".0%", range=[0, 1.15], title="Probabilidade"),
        plot_bgcolor="white",
        paper_bgcolor="white",
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="center", x=0.5),
        margin=dict(t=60, b=40),
        font=dict(family="DM Sans"),
    )
    for i in range(1, n_ev + 1):
        fig_a.update_xaxes(showticklabels=False, row=1, col=i)
    st.plotly_chart(fig_a, use_container_width=True)

    # Legenda de amostras pequenas
    if (df_prob["n_anos"] < 5).any():
        st.caption("⚠️ Barras marcadas com ⚠️ têm menos de 5 anos de amostra — intervalos de confiança largos, use com cautela.")

st.markdown("---")


# ────────────────────────────────────────────────────────────────────────────
# PAINEL B — Nível 2: Distribuição empírica condicional
# ────────────────────────────────────────────────────────────────────────────
st.markdown("## 📈 Painel B — Distribuição histórica por fase ENSO")
st.caption(
    "Função de distribuição acumulada (CDF) empírica da variável selecionada, "
    "condicionada à fase ENSO. O marcador vertical mostra a probabilidade acumulada no ponto escolhido."
)

VARIAVEIS_B = {
    "Chuva acumulada em janeiro (mm)": {
        "variavel": "prec_media", "decendios": [1, 2, 3],
        "xlabel": "Chuva acumulada jan (mm)"
    },
    "Tmin média mai-jun (°C)": {
        "variavel": "tmin_media", "decendios": list(range(13, 19)),
        "xlabel": "Tmin média mai-jun (°C)"
    },
    "Tmax média em janeiro (°C)": {
        "variavel": "tmax_media", "decendios": [1, 2, 3],
        "xlabel": "Tmax média jan (°C)"
    },
    "Chuva acumulada em outubro (mm)": {
        "variavel": "prec_media", "decendios": [28, 29, 30],
        "xlabel": "Chuva acumulada out (mm)"
    },
}

b1, b2 = st.columns([2, 1])
with b1:
    var_b_sel = st.selectbox("Variável", list(VARIAVEIS_B.keys()), key="var_b")
with b2:
    st.markdown(" ")

cfg_b = VARIAVEIS_B[var_b_sel]
df_cdf = cdf_empirica(df_clima_mun, cfg_b["variavel"], cfg_b["decendios"])

if df_cdf.empty:
    st.info("Dados insuficientes para gerar a CDF.")
else:
    valor_min = float(df_cdf["valor"].min())
    valor_max = float(df_cdf["valor"].max())
    valor_ref = st.slider(
        "Ponto de referência (eixo X):",
        min_value=round(valor_min, 1),
        max_value=round(valor_max, 1),
        value=round((valor_min + valor_max) / 2, 1),
        step=round((valor_max - valor_min) / 100, 1) or 0.1,
        key="slider_b",
    )

    fig_b = go.Figure()
    for fase in ["El Niño", "La Niña", "Neutro"]:
        sub = df_cdf[df_cdf["categoria"] == fase]
        if sub.empty:
            continue
        fig_b.add_trace(go.Scatter(
            x=sub["valor"], y=sub["prob_acumulada"],
            mode="lines",
            name=f"{fase} (n={int(sub['n'].iloc[0])})",
            line=dict(color=CORES_ENSO[fase], width=2.5, shape="hv"),
            hovertemplate=f"<b>{fase}</b><br>Valor: %{{x:.1f}}<br>P(X≤x): %{{y:.1%}}<extra></extra>",
        ))

    # Linha vertical no ponto de referência
    fig_b.add_vline(
        x=valor_ref, line_dash="dot", line_color="#888", line_width=1.5,
        annotation_text=f"{valor_ref:.1f}", annotation_position="top right",
    )

    fig_b.update_layout(
        height=380,
        xaxis_title=cfg_b["xlabel"],
        yaxis=dict(title="Probabilidade acumulada", tickformat=".0%", range=[0, 1.05]),
        plot_bgcolor="white",
        paper_bgcolor="white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        margin=dict(t=40, b=40),
        font=dict(family="DM Sans"),
    )
    st.plotly_chart(fig_b, use_container_width=True)

    # Resumo dinâmico no ponto do slider
    resumo_cols = st.columns(3)
    for i, fase in enumerate(["El Niño", "La Niña", "Neutro"]):
        sub = df_cdf[df_cdf["categoria"] == fase]
        if sub.empty:
            continue
        prob_acum = float((sub["valor"] <= valor_ref).mean())
        resumo_cols[i].metric(
            label=f"{fase}",
            value=f"{prob_acum:.0%}",
            help=f"Em anos {fase}: {prob_acum:.0%} dos anos tiveram valor ≤ {valor_ref:.1f}",
        )

st.markdown("---")


# ────────────────────────────────────────────────────────────────────────────
# PAINEL C — Nível 3: Motor de análogos
# ────────────────────────────────────────────────────────────────────────────

# Ano corrente = maior ano disponível na base desse município
ANO_ATUAL = int(df_clima_mun["ano"].max())

# Detecta o último decêndio com flag_cobertura == 'OK' para o ano corrente
mask_atual = (df_clima_mun["ano"] == ANO_ATUAL) & (df_clima_mun["flag_cobertura"] == "OK")
_tem_dados_atuais = mask_atual.any()
ultimo_dec_obs = int(df_clima_mun.loc[mask_atual, "decendio"].max()) if _tem_dados_atuais else 0
decendios_obs_reais = list(range(1, ultimo_dec_obs + 1))
decendios_fut_reais = list(range(ultimo_dec_obs + 1, 37))

st.markdown(f"## 🔍 Painel C — Anos análogos a {ANO_ATUAL}")
st.caption(
    f"Os 5 anos da história mais parecidos com {ANO_ATUAL} "
    f"(com base nos decêndios 1–{ultimo_dec_obs} já observados em {ANO_ATUAL}), "
    "identificados por distância euclidiana Z-score sobre prec, tmax e tmin."
)

df_analogos = pd.DataFrame()
if not _tem_dados_atuais:
    st.info(f"Sem dados de {ANO_ATUAL} disponíveis para calcular análogos neste município.")
elif len(decendios_obs_reais) < 3:
    st.info(
        f"Apenas {len(decendios_obs_reais)} decêndio(s) observado(s) em {ANO_ATUAL} "
        "— mínimo recomendado: 3."
    )
else:
    with st.spinner("Calculando análogos…"):
        try:
            df_analogos = motor_analogos(
                df_clima_mun, ano_alvo=ANO_ATUAL,
                decendios_observados=decendios_obs_reais, k=5,
            )
        except Exception as e:
            st.warning(f"Não foi possível calcular análogos: {e}")

if df_analogos.empty and _tem_dados_atuais and len(decendios_obs_reais) >= 3:
    st.info(f"Dados insuficientes para calcular análogos de {ANO_ATUAL}.")
else:
    c1_c, c2_c = st.columns([1, 2])

    with c1_c:
        st.markdown("**Análogos identificados:**")
        df_exib = df_analogos.copy()
        df_exib.columns = ["#", "Ano", "Distância", "Fase ENSO"]
        df_exib["Distância"] = df_exib["Distância"].round(3)
        st.dataframe(df_exib, hide_index=True, use_container_width=True)

    with c2_c:
        anos_analogos = df_analogos["ano"].tolist()

        # Trajetória de precipitação — acumulada por decêndio
        fig_c = make_subplots(
            rows=2, cols=1,
            subplot_titles=["Precipitação observada e projeção (mm/decêndio)",
                            "Temperatura mínima (°C/decêndio)"],
            shared_xaxes=True,
            vertical_spacing=0.12,
        )

        hist_ok = filtrar_validos(df_clima_mun)
        hist_all = hist_ok[hist_ok["decendio"].isin(list(range(1, 37)))]

        # Faixa histórica p10-p90
        hist_band = (
            hist_all.groupby("decendio", observed=True)
            .agg(p10=("prec_media", lambda x: x.quantile(0.1)),
                 p50=("prec_media", "median"),
                 p90=("prec_media", lambda x: x.quantile(0.9)))
            .reset_index()
        )
        fig_c.add_trace(go.Scatter(
            x=list(hist_band["decendio"]) + list(hist_band["decendio"])[::-1],
            y=list(hist_band["p90"])     + list(hist_band["p10"])[::-1],
            fill="toself", fillcolor="rgba(141,153,174,0.15)",
            line=dict(color="rgba(0,0,0,0)"),
            name="Faixa histórica p10–p90", showlegend=True,
        ), row=1, col=1)
        fig_c.add_trace(go.Scatter(
            x=hist_band["decendio"], y=hist_band["p50"],
            mode="lines", name="Mediana histórica",
            line=dict(color="#8d99ae", width=1.5, dash="dot"),
        ), row=1, col=1)

        # Trajetória de cada análogo
        for ano_a in anos_analogos:
            s = hist_ok[hist_ok["ano"] == ano_a].sort_values("decendio")
            fig_c.add_trace(go.Scatter(
                x=s["decendio"], y=s["prec_media"],
                mode="lines", name=f"{ano_a}",
                line=dict(color=CORES_ENSO.get(
                    str(df_analogos.loc[df_analogos["ano"] == ano_a, "fase_enso"].iloc[0]), "#2e86ab"
                ), width=1, dash="dot"),
                opacity=0.55, showlegend=True,
            ), row=1, col=1)

        # Trajetória do ano atual (observada)
        s26 = hist_ok[hist_ok["ano"] == ANO_ATUAL].sort_values("decendio")
        if not s26.empty:
            fig_c.add_trace(go.Scatter(
                x=s26["decendio"], y=s26["prec_media"],
                mode="lines+markers", name=f"{ANO_ATUAL} (atual)",
                line=dict(color="#d1495b", width=3),
            ), row=1, col=1)

        # Linha vertical "agora"
        fig_c.add_vline(
            x=ultimo_dec_obs, line_dash="dash",
            line_color="#d1495b", line_width=1.5,
            annotation_text="Agora", annotation_position="top",
            row=1, col=1,
        )

        # Projeção análogos — Tmin
        if decendios_fut_reais:
            proj = projecao_dos_analogos(df_clima_mun, anos_analogos, decendios_fut_reais)
            hist_tmin = historico_climatologico(df_clima_mun, decendios_fut_reais)
            if not proj.empty:
                fig_c.add_trace(go.Scatter(
                    x=list(proj["decendio"]) + list(proj["decendio"])[::-1],
                    y=list(proj["tmin_p50"] + proj.get("tmin_p10", proj["tmin_p50"]) * 0)
                      + list(proj["tmin_p10"])[::-1],
                    fill="toself", fillcolor="rgba(46,134,171,0.12)",
                    line=dict(color="rgba(0,0,0,0)"),
                    name="Proj. análogos (faixa)", showlegend=True,
                ), row=2, col=1)
                fig_c.add_trace(go.Scatter(
                    x=proj["decendio"], y=proj["tmin_p50"],
                    mode="lines", name="Proj. análogos (mediana)",
                    line=dict(color="#2e86ab", width=2),
                ), row=2, col=1)
            if not hist_tmin.empty:
                fig_c.add_trace(go.Scatter(
                    x=hist_tmin["decendio"], y=hist_tmin["tmin_p50"],
                    mode="lines", name="Mediana hist. Tmin",
                    line=dict(color="#8d99ae", width=1.5, dash="dot"),
                ), row=2, col=1)

        fig_c.update_layout(
            height=480,
            plot_bgcolor="white", paper_bgcolor="white",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=10)),
            margin=dict(t=60, b=20),
            font=dict(family="DM Sans"),
        )
        fig_c.update_xaxes(title_text="Decêndio do ano", row=2, col=1)
        fig_c.update_yaxes(title_text="Prec (mm)", row=1, col=1)
        fig_c.update_yaxes(title_text="Tmin (°C)", row=2, col=1)
        st.plotly_chart(fig_c, use_container_width=True)

st.markdown("---")


# ────────────────────────────────────────────────────────────────────────────
# PAINEL D — Nível 4: Validação produtiva
# ────────────────────────────────────────────────────────────────────────────
st.markdown(f"## 🌾 Painel D — Impacto produtivo em {cultura_sel} ({ANO_ATUAL})")
st.caption(
    "Cruzamento entre as fases ENSO históricas e o rendimento real registrado. "
    "Dados: IBGE/PAM (Produção Agrícola Municipal)."
)

mun_prod_cult = df_prod[
    (df_prod["codigo_ibge"].astype(str) == codigo_ibge) &
    (df_prod["cultura"] == cultura_sel)
]

if mun_prod_cult.empty:
    st.info(f"Sem dados de **{cultura_sel}** para **{municipio_sel}** no histórico produtivo.")
else:
    # ── D.1 Strip plot + boxplot por fase ENSO ───────────────────────────────
    st.markdown(f"### D.1 Rendimento histórico de {cultura_sel} por fase ENSO")

    df_rend = rendimento_por_enso(mun_prod_cult, df_clima_mun, cultura_sel)

    if df_rend.empty:
        st.info("Dados insuficientes para comparar rendimento × fase ENSO.")
    else:
        d1_left, d1_right = st.columns([3, 2])

        with d1_left:
            fig_d1 = go.Figure()

            # Pontos individuais (strip plot)
            df_clima_ok = filtrar_validos(df_clima_mun)
            fase_ano = (
                df_clima_ok.groupby("ano", observed=True)["enso_fenomeno"]
                .agg(lambda x: x.mode().iloc[0] if len(x) > 0 else np.nan)
            )
            mun_prod_ann = mun_prod_cult.copy()
            mun_prod_ann["fase_enso"] = mun_prod_ann["ano"].map(fase_ano).astype(str).replace("nan", "—")

            for fase in ["El Niño", "La Niña", "Neutro"]:
                sub = mun_prod_ann[mun_prod_ann["fase_enso"] == fase]
                if sub.empty:
                    continue
                n = len(sub)
                aviso = " ⚠️" if n < 5 else ""

                fig_d1.add_trace(go.Box(
                    y=sub["rendimento_kg_ha"],
                    name=f"{fase} (n={n}){aviso}",
                    marker_color=CORES_ENSO[fase],
                    boxpoints="all",
                    jitter=0.3,
                    pointpos=0,
                    line_width=2,
                    marker=dict(size=6, opacity=0.7),
                    hovertemplate=(
                        f"<b>{fase}</b><br>"
                        "Ano: %{text}<br>"
                        "Rendimento: %{y:,.0f} kg/ha<extra></extra>"
                    ),
                    text=sub["ano"].astype(str).tolist(),
                ))

            fig_d1.add_hline(
                y=mun_prod_cult["rendimento_kg_ha"].mean(),
                line_dash="dash", line_color="#1b4332", line_width=1.5,
                annotation_text=f"Média geral: {mun_prod_cult['rendimento_kg_ha'].mean():,.0f} kg/ha",
                annotation_position="right",
            )

            fig_d1.update_layout(
                height=420,
                yaxis_title="Rendimento (kg/ha)",
                plot_bgcolor="white", paper_bgcolor="white",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
                margin=dict(t=20, b=20),
                font=dict(family="DM Sans"),
            )
            st.plotly_chart(fig_d1, use_container_width=True)

        with d1_right:
            st.markdown("**Resumo por fase ENSO:**")
            for _, row_r in df_rend[df_rend["fase_enso"] != "TODOS"].iterrows():
                fase   = row_r["fase_enso"]
                media  = row_r["rend_medio"]
                n      = int(row_r["n_anos"])
                media_geral = float(
                    df_rend.loc[df_rend["fase_enso"] == "TODOS", "rend_medio"].iloc[0]
                ) if "TODOS" in df_rend["fase_enso"].values else mun_prod_cult["rendimento_kg_ha"].mean()
                delta  = (media / media_geral - 1) * 100 if media_geral else 0
                sinal  = "+" if delta >= 0 else ""
                cor    = CORES_ENSO.get(fase, "#888")
                aviso  = " ⚠️" if n < 5 else ""

                st.markdown(
                    f"<div style='border-left:4px solid {cor};padding:8px 12px;"
                    f"margin-bottom:10px;border-radius:0 8px 8px 0;background:#f9f9f9'>"
                    f"<b style='color:{cor}'>{fase}</b>{aviso}<br>"
                    f"<span style='font-size:1.3rem;font-weight:700'>{media:,.0f} kg/ha</span><br>"
                    f"<span style='font-size:0.85rem;color:#555'>"
                    f"n={n} anos &nbsp;·&nbsp; {sinal}{delta:.1f}% vs média geral"
                    f"</span></div>",
                    unsafe_allow_html=True,
                )

            # Texto-conclusão automatizado
            melhor = df_rend[df_rend["fase_enso"] != "TODOS"].sort_values("rend_medio", ascending=False)
            if not melhor.empty:
                top_fase = melhor.iloc[0]["fase_enso"]
                top_media = melhor.iloc[0]["rend_medio"]
                media_geral = float(
                    df_rend.loc[df_rend["fase_enso"] == "TODOS", "rend_medio"].iloc[0]
                ) if "TODOS" in df_rend["fase_enso"].values else mun_prod_cult["rendimento_kg_ha"].mean()
                delta_top = (top_media / media_geral - 1) * 100 if media_geral else 0
                st.info(
                    f"Para **{cultura_sel}** em **{municipio_sel}**, anos de "
                    f"**{top_fase}** tiveram o maior rendimento médio: "
                    f"**{top_media:,.0f} kg/ha** — "
                    f"{'+' if delta_top >= 0 else ''}{delta_top:.1f}% vs média histórica geral."
                )

    # ── D.2 Projeção pelos análogos ──────────────────────────────────────────
    st.markdown(f"### D.2 Projeção de {cultura_sel} em {ANO_ATUAL} pelos análogos")

    if not df_analogos.empty:
        anos_ana = df_analogos["ano"].tolist()
        proj_prod = projecao_rendimento_analogos(mun_prod_cult, df_clima_mun, anos_ana, cultura_sel)

        if not proj_prod or proj_prod.get("n_analogos_com_dados", 0) == 0:
            st.info(f"Sem dados de {cultura_sel} em {municipio_sel} para os anos análogos.")
        else:
            media_ana  = proj_prod["rend_medio_analogos"]
            media_hist = proj_prod["rend_medio_historico"]
            rend_min   = proj_prod["rend_min_analogos"]
            rend_max   = proj_prod["rend_max_analogos"]
            delta_pct  = proj_prod["delta_pct"]
            n_anos_c   = proj_prod["n_analogos_com_dados"]
            sinal      = "+" if delta_pct >= 0 else ""
            cor_delta  = "#2d6a4f" if delta_pct >= 0 else "#d1495b"

            st.markdown(
                f"""
                <div style="background:linear-gradient(135deg,#1b4332,#2d6a4f);
                    border-radius:16px;padding:1.5rem 2rem;margin-bottom:1rem;color:#fff">
                  <div style="font-size:0.9rem;opacity:0.8;margin-bottom:0.3rem">
                    Projeção baseada em {n_anos_c} ano(s) análogo(s) com dados de {cultura_sel}
                  </div>
                  <div style="font-size:1.5rem;font-weight:700;font-family:'Lora',serif;margin-bottom:0.4rem">
                    Nos anos análogos a {ANO_ATUAL}, <b>{cultura_sel}</b> em <b>{municipio_sel}</b>
                    rendeu em média <b>{media_ana:,.0f} kg/ha</b>
                  </div>
                  <div style="font-size:1rem;opacity:0.9">
                    Variação: de <b>{rend_min:,.0f}</b> a <b>{rend_max:,.0f} kg/ha</b>
                    &nbsp;·&nbsp; Média histórica: <b>{media_hist:,.0f} kg/ha</b>
                    &nbsp;·&nbsp; <b style="color:{'#95e5b5' if delta_pct >= 0 else '#ffaaaa'}">{sinal}{delta_pct:.1f}%</b>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Tabela detalhada ano a ano
            st.markdown("**Detalhamento por ano análogo:**")
            detalhe = pd.DataFrame(proj_prod["detalhe_por_ano"])
            if not detalhe.empty:
                rename_map = {
                    "ano": "Ano",
                    "rendimento_kg_ha": "Rendimento (kg/ha)",
                    "area_plantada_ha": "Área plantada (ha)",
                    "producao_ton": "Produção (t)",
                    "fase_enso": "Fase ENSO",
                }
                detalhe = detalhe.rename(columns=rename_map)
                for col in ["Rendimento (kg/ha)", "Área plantada (ha)", "Produção (t)"]:
                    if col in detalhe.columns:
                        detalhe[col] = detalhe[col].apply(
                            lambda x: f"{x:,.0f}" if pd.notna(x) else "—"
                        )
                st.dataframe(detalhe, hide_index=True, use_container_width=True)
    else:
        st.info("Calcule os análogos no Painel C para ver a projeção produtiva.")

st.markdown("---")


# ── Rodapé técnico ────────────────────────────────────────────────────────────
with st.expander("ℹ️ Notas técnicas", expanded=False):
    st.markdown(f"""
**Metodologia e filtros aplicados:**

- **Filtro de cobertura:** somente registros com `flag_cobertura == 'OK'` são usados em análises probabilísticas.
- **Normalização ENSO:** intensidades 'Fraco' → 'Fraca', 'Moderado' → 'Moderada' (corrige inconsistência de gênero na base original).
- **Bootstrap (IC 95%):** 2.000 reamostras com reposição; quantis 2,5% e 97,5%. Quando n < 5, os intervalos podem ser muito largos — indicados com ⚠️.
- **Motor de análogos (Nível 3):** distância euclidiana sobre vetores Z-score-normalizados por dimensão (prec, tmax, tmin por decêndio + índice ENSO médio). A normalização garante que precipitação (mm) não domine sobre temperatura (°C) por diferença de magnitude.
- **Validação produtiva (Nível 4):** dados IBGE/PAM (Produção Agrícola Municipal). A fase ENSO de cada ano é a moda dos decêndios com `flag_cobertura == 'OK'` naquele ano.
- **Base climática:** longo formato (município × ano × decêndio), cobrindo {ANO_CORRENTE - 2000 + 1} anos (2000–{ANO_CORRENTE}), com dados interpolados por IDW a partir de estações INMET.
- **Este módulo é puramente descritivo e empírico** — não há modelagem fisiológica, estimativa de evapotranspiração ou simulação de balanço hídrico.
    """)

st.markdown(
    "<div style='text-align:center;color:#8a9e8f;font-size:0.82rem;padding:0.5rem 0'>"
    "Dados: INMET · IBGE/PAM · EMBRAPA &nbsp;·&nbsp; "
    "Projeto Integrador — Big Data &nbsp;·&nbsp; 2025"
    "</div>",
    unsafe_allow_html=True,
)
