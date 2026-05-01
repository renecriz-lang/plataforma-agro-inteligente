"""
Gêmeos Climáticos — encontra municípios brasileiros climaticamente análogos
a um município de referência em um período do ano especificado.
"""

import os
import sys
import time

import numpy as np
import pandas as pd
import streamlit as st
import folium
import plotly.graph_objects as go
from streamlit_folium import st_folium

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))

from utils.data_loader import load_base
from utils.design import inject_css, hero_banner
from utils.simulation import DEC_LABEL
from utils.twin_engine import (
    load_stds,
    dec_period_indices,
    build_ruler,
    compute_twins,
    extract_best_windows,
    build_comparison_data,
)

TEMP_FILE = os.path.join(_HERE, "..", "gemeos_resultado_temp.parquet")

# ── Configuração ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Gêmeos Climáticos",
    page_icon="🌍",
    layout="wide",
)

inject_css()
hero_banner(
    title="Gêmeos Climáticos",
    subtitle="Encontre municípios brasileiros climaticamente análogos a uma referência",
    icon="🌍",
)

# ── Como usar ───────────────────────────────────────────────────────────────
with st.expander("ℹ️ Como usar este módulo", expanded=False):
    st.markdown("""
**Siga os passos abaixo para encontrar gêmeos climáticos:**

**1. Escolha o município de referência (barra lateral)**
Selecione a UF e o município cuja assinatura climática você deseja replicar.
Apenas municípios com ≥ 10 anos de dados válidos aparecem na lista.

**2. Defina o período do ano**
Escolha os decêndios inicial e final. O sistema compara a assinatura climática
do período nesse município contra todos os 5.573 municípios brasileiros
em todas as 36 janelas possíveis de início no ano.

**3. Ajuste a tolerância k**
Cada variável climática é aceita se estiver dentro de `mean ± k × desvio padrão`
da referência. Valores maiores de k aceitam mais variação.

**4. Aplique filtros guilhotina (opcional)**
Restrinja os candidatos por altitude e tipo de solo antes do cálculo.
O município de referência é sempre incluído como sanity check.

**5. Clique em "Calcular Gêmeos Climáticos"**
O cálculo é vetorizado em numpy — tipicamente < 5 s para 5.500+ municípios.

**6. Clique em "Apresentar Resultados"**
Ajuste o threshold de similaridade e explore o mapa interativo, a tabela
e o download CSV dos municípios gêmeos encontrados.
""")

# ── Carrega bases (com cache) ───────────────────────────────────────────────
df_means = load_base("media_geral")
df_stds  = load_stds()

# ── Sidebar — Parâmetros ────────────────────────────────────────────────────
st.sidebar.header("⚙️ Município de Referência")

ufs_sorted = sorted([v for v in df_means["estado"].unique() if isinstance(v, str)])
default_uf_idx = ufs_sorted.index("PR") if "PR" in ufs_sorted else 0
uf_ref = st.sidebar.selectbox(
    "UF do município de referência", ufs_sorted, index=default_uf_idx,
)

# Filtra municípios com dados suficientes na UF selecionada
munis_validos = (
    df_stds[(df_stds["estado"] == uf_ref) & (df_stds["n_anos_validos"] >= 10)]
    ["nome"].sort_values().tolist()
)

if not munis_validos:
    st.sidebar.error(f"Nenhum município em {uf_ref} com ≥ 10 anos de dados válidos.")
    st.stop()

default_mun_idx = (
    munis_validos.index("Guarapuava")
    if uf_ref == "PR" and "Guarapuava" in munis_validos
    else 0
)
mun_ref = st.sidebar.selectbox(
    "Município de referência", munis_validos, index=default_mun_idx,
)

st.sidebar.markdown("---")
st.sidebar.header("📅 Período de Análise")

dec_options = {d: f"D{d} — {DEC_LABEL[d]}" for d in range(1, 37)}

d_ini = st.sidebar.selectbox(
    "Decêndio inicial",
    options=list(dec_options.keys()),
    format_func=lambda d: dec_options[d],
    index=12,  # D13 — 01-10 Mai (padrão Guarapuava)
)
d_fim = st.sidebar.selectbox(
    "Decêndio final",
    options=list(dec_options.keys()),
    format_func=lambda d: dec_options[d],
    index=29,  # D30 — 21-31 Out (padrão Guarapuava)
)

k = st.sidebar.slider(
    "Tolerância (k × desvio padrão)",
    min_value=0.0, max_value=3.0, value=0.8, step=0.1,
    help=(
        "Define a amplitude da régua climática: mean ± k × std. "
        "Maior k → mais municípios aceitos como gêmeos."
    ),
)
st.sidebar.caption(
    "💡 k=0 exige match exato (apenas a própria referência bate 100%). "
    "Valores entre 0.5 e 1.5 dão calibração útil."
)

st.sidebar.markdown("---")
st.sidebar.header("🔪 Filtros Guilhotina (candidatos)")

alt_min_val = int(df_means["altitude_media"].dropna().min())
alt_max_val = int(df_means["altitude_media"].dropna().max())
alt_range = st.sidebar.slider(
    "Altitude (m)",
    min_value=alt_min_val, max_value=alt_max_val,
    value=(alt_min_val, alt_max_val), step=10,
)

solos_str  = df_means["solo_1_ordem"].astype(str).replace({"nan": "Não identificado"})
solos_disp = sorted([v for v in solos_str.unique().tolist() if isinstance(v, str)])
solos_sel  = st.sidebar.multiselect(
    "Solo Dominante", options=solos_disp, default=solos_disp,
)

# Aplica guilhotinas sobre df_means
df_candidates = df_means[
    (df_means["altitude_media"].fillna(-1) >= alt_range[0])
    & (df_means["altitude_media"].fillna(-1) <= alt_range[1])
    & (solos_str.isin(solos_sel))
].reset_index(drop=True)

st.sidebar.metric("Municípios candidatos", f"{len(df_candidates):,}")

# ── Lookup do município de referência ───────────────────────────────────────
ref_mask_means = (df_means["nome"] == mun_ref) & (df_means["estado"] == uf_ref)
if not ref_mask_means.any():
    st.error(f"Município '{mun_ref}/{uf_ref}' não encontrado na base de médias.")
    st.stop()
ref_row_means = df_means[ref_mask_means].iloc[0]
ref_ibge      = str(ref_row_means["codigo_ibge"])

ref_mask_stds = df_stds["codigo_ibge"] == ref_ibge
if not ref_mask_stds.any():
    st.error(f"Município '{mun_ref}/{uf_ref}' não encontrado na base de desvios.")
    st.stop()
ref_row_stds = df_stds[ref_mask_stds].iloc[0]

# Garante que a referência está entre os candidatos (mesmo que filtrada)
if ref_ibge not in df_candidates["codigo_ibge"].values:
    ref_df_row = df_means[df_means["codigo_ibge"] == ref_ibge]
    df_candidates = pd.concat([df_candidates, ref_df_row], ignore_index=True)

# ── Período e régua ─────────────────────────────────────────────────────────
period_idx = dec_period_indices(d_ini, d_fim)
P = len(period_idx)

if P == 0:
    st.sidebar.error("Período inválido. Ajuste os decêndios.")
    st.stop()

ruler = build_ruler(ref_row_means, ref_row_stds, period_idx, k)

# ── Expander: visualizar régua ──────────────────────────────────────────────
with st.sidebar.expander("📐 Visualizar régua calculada"):
    ruler_rows = []
    for j, dec_0 in enumerate(period_idx):
        d = dec_0 + 1
        ruler_rows.append({
            "Dec.":            f"D{d}",
            "Período":         DEC_LABEL[d],
            "Prec mean":       f"{ruler['means'][j, 0]:.1f}",
            "Prec range":      f"[{ruler['lower'][j, 0]:.1f}, {ruler['upper'][j, 0]:.1f}]",
            "Tmax mean":       f"{ruler['means'][j, 1]:.1f}",
            "Tmax range":      f"[{ruler['lower'][j, 1]:.1f}, {ruler['upper'][j, 1]:.1f}]",
            "Tmed mean":       f"{ruler['means'][j, 2]:.1f}",
            "Tmed range":      f"[{ruler['lower'][j, 2]:.1f}, {ruler['upper'][j, 2]:.1f}]",
            "Tmin mean":       f"{ruler['means'][j, 3]:.1f}",
            "Tmin range":      f"[{ruler['lower'][j, 3]:.1f}, {ruler['upper'][j, 3]:.1f}]",
        })
    st.dataframe(pd.DataFrame(ruler_rows), hide_index=True, use_container_width=True)

# ── Cabeçalho da análise ────────────────────────────────────────────────────
if d_ini <= d_fim:
    periodo_str = (
        f"D{d_ini} ({DEC_LABEL[d_ini]}) → D{d_fim} ({DEC_LABEL[d_fim]})"
    )
else:
    periodo_str = (
        f"D{d_ini} ({DEC_LABEL[d_ini]}) → D{d_fim} ({DEC_LABEL[d_fim]}) "
        f"[cruza virada de ano]"
    )
st.info(
    f"🔍 Referência: **{mun_ref} / {uf_ref}** &nbsp;·&nbsp; "
    f"Período: **{periodo_str}** ({P} decêndios) &nbsp;·&nbsp; k = **{k}**"
)

# ── Dois Botões ─────────────────────────────────────────────────────────────
col_b1, col_b2 = st.columns([1, 1])

with col_b1:
    btn_calcular = st.button(
        "🔍 Calcular Gêmeos Climáticos",
        type="primary",
        help="Computa scores de similaridade para todos os candidatos × 36 janelas.",
    )

has_result = "gemeos_df" in st.session_state or os.path.exists(TEMP_FILE)

with col_b2:
    btn_apresentar = st.button(
        "📊 Apresentar Resultados",
        disabled=not has_result,
        help="Gera mapa interativo, tabela e opção de download.",
    )

# ── Botão 1 — Calcular ──────────────────────────────────────────────────────
if btn_calcular:
    t0 = time.perf_counter()
    with st.spinner("Calculando gêmeos climáticos (vetorizado)…"):
        df_result = compute_twins(df_candidates, period_idx, ruler)
    elapsed = time.perf_counter() - t0

    df_result.to_parquet(TEMP_FILE, index=False)
    st.session_state["gemeos_df"]      = df_result
    st.session_state.pop("gemeos_best_df", None)  # invalida cache do botão 2

    n_comb = len(df_result)

    # Sanity check: referência deve ter 100% na janela correta
    ref_check = df_result[
        (df_result["codigo_ibge"] == ref_ibge)
        & (df_result["decendio_inicio"] == d_ini)
    ]
    if not ref_check.empty:
        sc_ref = float(ref_check["score_combinado"].iloc[0])
        if abs(sc_ref - 100.0) < 0.1:
            st.success(
                f"✅ {n_comb:,} combinações calculadas em **{elapsed:.1f}s**. "
                f"Sanity check OK — {mun_ref} = **100%** na janela D{d_ini}."
            )
        else:
            st.warning(
                f"⚠️ {n_comb:,} combinações em {elapsed:.1f}s. "
                f"Sanity check FALHOU: {mun_ref} = {sc_ref:.1f}% (esperado 100%). "
                "Verifique se o município está na base de médias."
            )
    else:
        st.success(
            f"✅ {n_comb:,} combinações calculadas em **{elapsed:.1f}s**. "
            "(Referência não encontrada no resultado — verifique filtros.)"
        )

# ── Botão 2 — Apresentar ────────────────────────────────────────────────────
if btn_apresentar:
    st.session_state["show_gemeos"] = True

if st.session_state.get("show_gemeos") and has_result:

    # Carrega resultado
    if "gemeos_df" in st.session_state:
        df_g = st.session_state["gemeos_df"]
    else:
        df_g = pd.read_parquet(TEMP_FILE)

    st.markdown("---")
    st.subheader("📊 Resultados — Gêmeos Climáticos")

    # Extrai melhores janelas (cacheado na sessão para não recomputar a cada slider)
    if "gemeos_best_df" not in st.session_state:
        with st.spinner("Identificando janelas ótimas por município…"):
            st.session_state["gemeos_best_df"] = extract_best_windows(df_g)
    df_best = st.session_state["gemeos_best_df"]

    # ── Controles de filtro e ranking ──────────────────────────────────────
    col_ctrl1, col_ctrl2 = st.columns([1, 1])

    with col_ctrl1:
        threshold = st.slider(
            "Threshold mínimo de similaridade (%)",
            min_value=0, max_value=100, value=80, step=1,
            key="threshold_slider",
        )

    with col_ctrl2:
        rank_var = st.selectbox(
            "Rankear por:",
            options=["Combinado", "Precipitação", "Tmax", "Tmed", "Tmin"],
            key="rank_var_sel",
        )

    rank_col = {
        "Combinado":    "score_combinado",
        "Precipitação": "score_prec",
        "Tmax":         "score_tmax",
        "Tmed":         "score_tmed",
        "Tmin":         "score_tmin",
    }[rank_var]

    # Filtra pelo threshold e ordena
    df_display = (
        df_best[df_best[rank_col] >= threshold]
        .sort_values(rank_col, ascending=False)
        .reset_index(drop=True)
    )

    # Para o mapa: melhor janela por município (evita marcadores duplicados)
    df_map = (
        df_display.sort_values("score_combinado", ascending=False)
        .drop_duplicates(subset="codigo_ibge")
        .dropna(subset=["lat", "lon"])
        .reset_index(drop=True)
    )

    n_munis = df_display["codigo_ibge"].nunique()

    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("Municípios gêmeos",  f"{n_munis:,}")
    col_m2.metric("Threshold aplicado", f"{threshold}%")
    col_m3.metric("Janelas no ranking", f"{len(df_display):,}")

    # ── Tabs: Mapa / Tabela / Comparação Detalhada ────────────────────────
    tab_map, tab_table, tab_detail = st.tabs(
        ["🗺️ Mapa Interativo", "📋 Tabela", "🔬 Comparação Detalhada"]
    )

    def _score_color(score: float, thr: float) -> str:
        """Gradiente verde claro (#d8f3dc) → verde escuro (#1b4332) por score."""
        span = 100.0 - thr
        t = max(0.0, min(1.0, (score - thr) / span)) if span > 0 else 1.0
        r = int(0xd8 + t * (0x1b - 0xd8))
        g = int(0xf3 + t * (0x43 - 0xf3))
        b = int(0xdc + t * (0x32 - 0xdc))
        return f"#{r:02x}{g:02x}{b:02x}"

    with tab_map:
        if df_map.empty:
            st.warning("Nenhum município atinge o threshold atual. Reduza o slider.")
        else:
            m = folium.Map(
                location=[df_map["lat"].mean(), df_map["lon"].mean()],
                zoom_start=5,
                tiles="CartoDB positron",
            )
            for _, row in df_map.iterrows():
                sc    = float(row["score_combinado"])
                color = _score_color(sc, threshold)
                folium.CircleMarker(
                    location=[float(row["lat"]), float(row["lon"])],
                    radius=7,
                    color=color, fill=True,
                    fill_color=color, fill_opacity=0.85, weight=1.5,
                    tooltip=(
                        f"<b>{row['nome']} — {row['estado']}</b><br>"
                        f"Score: {sc:.1f}% &nbsp;|&nbsp; "
                        f"Plantio: {row['data_inicio_str']}"
                    ),
                    popup=folium.Popup(
                        f"<div style='font-family:Arial,sans-serif;"
                        f"font-size:13px;min-width:230px;line-height:1.5'>"
                        f"<b style='font-size:14px'>📍 {row['nome']} / {row['estado']}</b><br>"
                        f"⛰️ {row['altitude_media']:.0f} m &nbsp;|&nbsp; "
                        f"🌱 {row['solo_1_ordem']}"
                        f"<hr style='margin:5px 0;border-color:#ddd'>"
                        f"🌍 Score Combinado: <b>{sc:.1f}%</b><br>"
                        f"🌧️ Prec: {float(row['score_prec']):.1f}%"
                        f" &nbsp; 🌡️ Tmax: {float(row['score_tmax']):.1f}%<br>"
                        f"🌡️ Tmed: {float(row['score_tmed']):.1f}%"
                        f" &nbsp; 🌡️ Tmin: {float(row['score_tmin']):.1f}%"
                        f"<hr style='margin:5px 0;border-color:#ddd'>"
                        f"📅 Janela: {row['data_inicio_str']} → {row['data_fim_str']}"
                        f"</div>",
                        max_width=340,
                    ),
                ).add_to(m)
            st_folium(m, width="100%", height=560, returned_objects=[])

    with tab_table:
        if df_display.empty:
            st.warning("Nenhum município atinge o threshold atual.")
        else:
            st.dataframe(
                df_display[[
                    "nome", "estado", "altitude_media", "solo_1_ordem",
                    "decendio_inicio", "data_inicio_str", "data_fim_str",
                    "score_combinado", "score_prec", "score_tmax",
                    "score_tmed", "score_tmin",
                ]].rename(columns={
                    "nome":            "Município",
                    "estado":          "UF",
                    "altitude_media":  "Altitude (m)",
                    "solo_1_ordem":    "Solo",
                    "decendio_inicio": "D_ini",
                    "data_inicio_str": "Plantio",
                    "data_fim_str":    "Fim Período",
                    "score_combinado": "Score (%)",
                    "score_prec":      "Prec (%)",
                    "score_tmax":      "Tmax (%)",
                    "score_tmed":      "Tmed (%)",
                    "score_tmin":      "Tmin (%)",
                }),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Altitude (m)": st.column_config.NumberColumn(format="%.0f m"),
                    "Score (%)":    st.column_config.NumberColumn(format="%.1f%%"),
                    "Prec (%)":     st.column_config.NumberColumn(format="%.1f%%"),
                    "Tmax (%)":     st.column_config.NumberColumn(format="%.1f%%"),
                    "Tmed (%)":     st.column_config.NumberColumn(format="%.1f%%"),
                    "Tmin (%)":     st.column_config.NumberColumn(format="%.1f%%"),
                },
            )
            st.caption(f"Exibindo {len(df_display):,} janela(s) de {n_munis:,} município(s).")

    with tab_detail:
        _VAR_LABELS = [
            "Precipitação Acumulada (mm)",
            "Temperatura Máxima (°C)",
            "Temperatura Média (°C)",
            "Temperatura Mínima (°C)",
        ]
        _REF_COLOR  = "#1b4332"
        _CAND_COLOR = "#c9963a"
        _BAND_FILL  = "rgba(45, 106, 79, 0.15)"
        _BAND_LINE  = "#2d6a4f"
        _FAIL_COLOR = "rgba(214, 40, 40, 0.7)"

        if df_display.empty:
            st.warning("Nenhum município acima do threshold para comparar.")
        else:
            # Selectbox com label informativo
            opt_labels = [
                f"{r['nome']} / {r['estado']} — "
                f"Score {float(r['score_combinado']):.0f}% — "
                f"Plantio {r['data_inicio_str']}"
                for _, r in df_display.iterrows()
            ]
            cand_idx = st.selectbox(
                "Selecione um município para comparar com a referência",
                options=range(len(df_display)),
                format_func=lambda i: opt_labels[i],
                key="cand_detail_sel",
            )
            cand_row     = df_display.iloc[cand_idx]
            cand_ibge    = str(cand_row["codigo_ibge"])
            dec_ini_cand = int(cand_row["decendio_inicio"])

            # Dados (cached por @st.cache_data em twin_engine)
            cdata = build_comparison_data(
                ref_ibge, cand_ibge, d_ini, d_fim, k, dec_ini_cand,
            )

            if ref_ibge == cand_ibge:
                st.warning(
                    "⚠️ Você selecionou a própria referência como candidato. "
                    "Os gráficos mostrarão duas linhas idênticas — isso confirma "
                    "que o sistema está funcionando corretamente para a própria referência."
                )

            P               = cdata["P"]
            ref_means       = cdata["ref_means"]       # (P, 4)
            ref_lower       = cdata["ref_lower"]       # (P, 4)
            ref_upper       = cdata["ref_upper"]       # (P, 4)
            cand_vals       = cdata["cand_vals"]       # (P, 4)
            within          = cdata["within"]          # (P, 4) bool
            ref_date_labels = cdata["ref_date_labels"]
            cand_date_labels = cdata["cand_date_labels"]

            x_vals = list(range(1, P + 1))  # posições 1..P

            # Ticks: ~6 pontos distribuídos no período
            step      = max(1, P // 6)
            tick_vals = list(range(1, P + 1, step))
            if tick_vals[-1] != P:
                tick_vals.append(P)
            ref_tick_text  = [ref_date_labels[t - 1]  for t in tick_vals]
            cand_tick_text = [cand_date_labels[t - 1] for t in tick_vals]

            # ── Gera 4 figuras Plotly ──────────────────────────────────────
            for v, var_label in enumerate(_VAR_LABELS):
                ref_m  = ref_means[:, v].tolist()
                lo_v   = ref_lower[:, v].tolist()
                hi_v   = ref_upper[:, v].tolist()
                cand_v = cand_vals[:, v].tolist()

                fig = go.Figure()

                # 1. Faixa sombreada — lower bound invisível
                fig.add_trace(go.Scatter(
                    x=x_vals, y=lo_v,
                    mode="lines",
                    line=dict(width=0),
                    showlegend=False,
                    hoverinfo="skip",
                    name="_lower",
                ))

                # 2. Faixa sombreada — upper bound com fill retroativo
                fig.add_trace(go.Scatter(
                    x=x_vals, y=hi_v,
                    mode="lines",
                    fill="tonexty",
                    fillcolor=_BAND_FILL,
                    line=dict(width=1.5, color=_BAND_LINE, dash="dash"),
                    name="Faixa de tolerância da referência",
                    hovertemplate="Faixa: [%{customdata[0]:.1f}, %{y:.1f}]<extra></extra>",
                    customdata=[[lo_v[i]] for i in range(P)],
                ))

                # 3. Linha da referência (média)
                fig.add_trace(go.Scatter(
                    x=x_vals, y=ref_m,
                    mode="lines+markers",
                    line=dict(color=_REF_COLOR, width=2.5),
                    marker=dict(size=5, color=_REF_COLOR),
                    name=f"Referência: {mun_ref}",
                    hovertemplate=f"{mun_ref}: %{{y:.1f}}<extra></extra>",
                ))

                # 4. Linha do candidato
                fig.add_trace(go.Scatter(
                    x=x_vals, y=cand_v,
                    mode="lines+markers",
                    line=dict(color=_CAND_COLOR, width=2.5, dash="dash"),
                    marker=dict(size=5, color=_CAND_COLOR),
                    name=f"Candidato: {cand_row['nome']} (janela: {cand_row['data_inicio_str']})",
                    hovertemplate=f"{cand_row['nome']}: %{{y:.1f}}<extra></extra>",
                ))

                # 5. Marcadores de falha (fora do range)
                fail_x, fail_y, fail_text = [], [], []
                for j in range(P):
                    if not within[j, v]:
                        val = cand_v[j]
                        lo  = lo_v[j]
                        hi  = hi_v[j]
                        dir_str = f"abaixo de {lo:.1f}" if val < lo else f"acima de {hi:.1f}"
                        fail_x.append(x_vals[j])
                        fail_y.append(val)
                        fail_text.append(f"Fora do range: {val:.1f} ({dir_str})")

                if fail_x:
                    fig.add_trace(go.Scatter(
                        x=fail_x, y=fail_y,
                        mode="markers",
                        marker=dict(
                            symbol="x",
                            size=8,
                            color=_FAIL_COLOR,
                            line=dict(width=1.5, color=_FAIL_COLOR),
                        ),
                        name="Fora da faixa",
                        text=fail_text,
                        hovertemplate="%{text}<extra></extra>",
                        showlegend=(v == 0),  # exibe legenda só no primeiro gráfico
                    ))

                # 6. Trace invisível para ativar xaxis2 (datas do candidato no topo)
                fig.add_trace(go.Scatter(
                    x=[tick_vals[0]],
                    y=[None],
                    xaxis="x2",
                    mode="markers",
                    marker=dict(opacity=0, size=1),
                    showlegend=False,
                    hoverinfo="skip",
                ))

                fig.update_layout(
                    title=dict(
                        text=var_label,
                        x=0.02, y=0.97,
                        xanchor="left", yanchor="top",
                        font=dict(size=14, color="#1b4332", family="Lora, serif"),
                    ),
                    height=360,
                    margin=dict(t=80, b=110, l=60, r=20),
                    hovermode="x unified",
                    legend=dict(
                        orientation="h",
                        yanchor="top",    y=-0.35,
                        xanchor="center", x=0.5,
                        font=dict(size=11),
                    ),
                    xaxis=dict(
                        tickmode="array",
                        tickvals=tick_vals,
                        ticktext=ref_tick_text,
                        tickfont=dict(size=10),
                        side="bottom",
                        showgrid=True,
                        gridcolor="#e8ede9",
                        title=dict(
                            text="Datas da referência",
                            font=dict(size=10, color="#4a6352"),
                            standoff=8,
                        ),
                    ),
                    xaxis2=dict(
                        overlaying="x",
                        side="top",
                        tickmode="array",
                        tickvals=tick_vals,
                        ticktext=cand_tick_text,
                        tickfont=dict(size=10),
                        showgrid=False,
                        matches="x",
                        title=dict(
                            text="Datas do candidato (janela deslocada)",
                            font=dict(size=10, color="#c9963a"),
                            standoff=8,
                        ),
                    ),
                    paper_bgcolor="white",
                    plot_bgcolor="#fafcfa",
                    yaxis=dict(showgrid=True, gridcolor="#e8ede9"),
                )

                st.plotly_chart(fig, use_container_width=True)
                if v < len(_VAR_LABELS) - 1:
                    st.markdown("<br>", unsafe_allow_html=True)

            # ── Anotação discreta do eixo X ──────────────────────────────────
            st.caption(
                "Eixo X: posição na janela de plantio (1 unidade = 1 decêndio ≈ 10 dias). "
                "Datas inferiores = referência · Datas superiores = candidato."
            )

            # ── Resumo textual ────────────────────────────────────────────────
            n_ok = within.sum(axis=0)  # (4,) — acertos por variável
            st.info(
                f"📊 **Resumo:** este candidato bate **{n_ok[0]}/{P}** decêndios em "
                f"precipitação, **{n_ok[1]}/{P}** em Tmax, **{n_ok[2]}/{P}** em Tmed, "
                f"**{n_ok[3]}/{P}** em Tmin."
            )

    # ── Download CSV ────────────────────────────────────────────────────────
    csv_bytes = df_display.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇️  Baixar CSV",
        data=csv_bytes,
        file_name=f"gemeos_climaticos_{mun_ref}_{uf_ref}_thr{threshold}.csv",
        mime="text/csv",
    )
