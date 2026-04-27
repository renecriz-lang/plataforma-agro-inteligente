"""
Aptidão da Cevada — simulação fenológica por município.

Dois modos:
  • Duração (Dias) — duração fixa por estádio
  • Grau-Dia (GDD) — acumulação térmica por estádio
"""

import os
import sys

import numpy as np
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

# garante importação do pacote utils/ irmão
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))

from utils.data_loader import load_base, AGG_MODES
from utils.simulation import (
    ESTAGIOS, STAGE_ICONS, DEC_LABEL, DECENDIO_DAYS,
    run_zoneamento_days, run_zoneamento_gdd,
)
from utils.design import inject_css, hero_banner

TEMP_FILE = os.path.join(_HERE, "..", "resultado_zoneamento_temp.parquet")

# ── Configuração da página ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Aptidão da Cevada",
    page_icon="🌾",
    layout="wide",
)

inject_css()
hero_banner(
    title="Aptidão Agroclimática da Cevada",
    subtitle=(
        "Simule as janelas de plantio aptas para cada município brasileiro. "
        "Filtre por altitude, solo e defina os requisitos de cada estádio fenológico."
    ),
    icon="🌾",
)

# ── Como usar ──────────────────────────────────────────────────────────────
with st.expander("ℹ️ Como usar este módulo", expanded=False):
    st.markdown("""
**Siga os passos abaixo para simular o zoneamento agroclimático:**

**1. Configure os filtros (barra lateral)**
Escolha a base de dados (agregação temporal), o modo de simulação (**Dias** ou **GDD**),
e aplique os filtros de altitude e tipo de solo para restringir a área de análise.

**2. Defina os estádios fenológicos**
Para cada um dos 7 estádios da cevada, informe a duração em dias (modo Dias) ou o
acúmulo de grau-dia necessário (modo GDD). Ative e configure os limites climáticos
opcionais — precipitação acumulada, temperatura média, máxima e mínima — que a cultura
exige em cada fase.

**3. Clique em "Processar Zoneamento"**
O sistema varre os 36 decêndios possíveis de plantio para todos os municípios filtrados
e identifica quais janelas de semeadura atendem a todos os requisitos definidos.

**4. Clique em "Gerar Mapa e Tabela"**
Visualize no mapa interativo os municípios aptos (🟢 verde = ≥ 3 janelas; 🟠 laranja = 1–2
janelas). Filtre a tabela por UF e número mínimo de janelas, e exporte o resultado em CSV.

**5. Consulte os detalhes de um município**
Selecione um município na lista abaixo da tabela para ver todas as janelas de plantio aptas
com as datas estimadas de colheita.

---
**Sobre os decêndios:** o ano é dividido em 36 períodos de ~10 dias
(D1 = 01–10 Jan · D2 = 11–20 Jan · … · D36 = 21–31 Dez).
Cada decêndio representa uma possível data de semeadura e o ciclo completo é simulado a partir dele.

**Fatores limitantes:** municípios sem nenhuma janela apta têm seus fatores restritivos
identificados por estádio e motivo (excesso/déficit de precipitação, calor excessivo, etc.).
""")

# ── Painel lateral ─────────────────────────────────────────────────────────
st.sidebar.header("⚙️ Configuração Geral")

# Modo de agregação temporal
agg_label = st.sidebar.selectbox(
    "Base de dados (agregação)",
    options=list(AGG_MODES.values()),
    help="Define como os dados históricos são condensados por decêndio.",
)
agg_key = {v: k for k, v in AGG_MODES.items()}[agg_label]

# Modo de simulação fenológica
sim_mode = st.sidebar.radio(
    "Modo de simulação",
    options=["Duração (Dias)", "Grau-Dia (GDD)"],
    help=(
        "**Dias**: cada estádio tem duração fixa em dias.\n\n"
        "**GDD**: a duração de cada estádio é determinada pela acumulação "
        "de grau-dia térmico (GD = max(0, (Tmax+Tmin)/2 − Tbase))."
    ),
)

# ── Carrega e filtra dados ──────────────────────────────────────────────────
df_base = load_base(agg_key)

st.sidebar.markdown("---")
st.sidebar.header("🔪 Filtros Guilhotina")

alt_min_val = int(df_base["altitude_media"].dropna().min())
alt_max_val = int(df_base["altitude_media"].dropna().max())

alt_range = st.sidebar.slider(
    "Altitude (m)",
    min_value=alt_min_val, max_value=alt_max_val,
    value=(alt_min_val, alt_max_val), step=10,
)

solo_col = df_base["solo_1_ordem"].astype(str).replace("nan", "Não identificado")
solos_disp = sorted([v for v in solo_col.unique().tolist() if isinstance(v, str)])
solos_sel = st.sidebar.multiselect(
    "Solo Dominante",
    options=solos_disp,
    default=solos_disp,
)

df_filtered = df_base[
    (df_base["altitude_media"].fillna(-1) >= alt_range[0])
    & (df_base["altitude_media"].fillna(-1) <= alt_range[1])
    & (solo_col.isin(solos_sel))
].reset_index(drop=True)

st.sidebar.metric("Municípios após filtros", f"{len(df_filtered):,}")

# ── Parâmetro Tbase (somente GDD) ──────────────────────────────────────────
tbase = None
if sim_mode == "Grau-Dia (GDD)":
    st.subheader("Temperatura Base (Tbase)")
    tbase = st.number_input(
        "Tbase (°C) *  — temperatura abaixo da qual não ocorre desenvolvimento",
        min_value=-5.0, max_value=20.0, value=0.0, step=0.5,
        key="tbase",
        help="Obrigatório para o modo GDD. "
             "Valores negativos de GD são tratados como zero.",
    )

# ── Estádios Fenológicos ────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Estádios Fenológicos da Cevada")
st.caption(
    "Informe a duração obrigatória e habilite os limites climáticos opcionais. "
    "O estádio seguinte começa imediatamente após o término do anterior."
)

phase_inputs: list[dict] = []

for s_idx, stage in enumerate(ESTAGIOS):
    with st.expander(f"{STAGE_ICONS[s_idx]} {stage}", expanded=(s_idx == 0)):
        col_dur, col_info = st.columns([1, 3])

        with col_dur:
            if sim_mode == "Duração (Dias)":
                dur = st.number_input(
                    "Duração (dias) *",
                    min_value=1, max_value=365, value=None, step=1,
                    key=f"dur_{s_idx}", placeholder="Obrigatório",
                )
                gdd_thresh = None
            else:
                gdd_thresh = st.number_input(
                    "GDD acumulado *",
                    min_value=1.0, value=None, step=10.0,
                    key=f"gdd_{s_idx}", placeholder="Obrigatório",
                    help="Grau-dias necessários para completar este estádio.",
                )
                dur = None

        with col_info:
            if sim_mode == "Duração (Dias)":
                if dur:
                    st.info(f"Estádio com **{dur} dia(s)**.")
                else:
                    st.warning("Preencha a duração para habilitar o processamento.")
            else:
                if gdd_thresh:
                    st.info(f"Acumular **{gdd_thresh:.0f} GD** para completar este estádio.")
                else:
                    st.warning("Informe o GDD necessário para habilitar o processamento.")

        prec_en = st.checkbox("Limitar Precipitação Acumulada (mm)", key=f"prec_en_{s_idx}")
        if prec_en:
            c1, c2 = st.columns(2)
            prec_min = c1.number_input("Prec. Mín (mm)", value=0.0, step=1.0, key=f"prec_min_{s_idx}")
            prec_max = c2.number_input("Prec. Máx (mm)", value=500.0, step=1.0, key=f"prec_max_{s_idx}")
        else:
            prec_min = prec_max = None

        tmed_en = st.checkbox("Limitar Temperatura Média (°C)", key=f"tmed_en_{s_idx}")
        if tmed_en:
            c1, c2 = st.columns(2)
            tmed_min = c1.number_input("Tmed Mín (°C)", value=5.0, step=0.5, key=f"tmed_min_{s_idx}")
            tmed_max = c2.number_input("Tmed Máx (°C)", value=30.0, step=0.5, key=f"tmed_max_{s_idx}")
        else:
            tmed_min = tmed_max = None

        tmax_en = st.checkbox("Limitar Temperatura Máxima (°C)", key=f"tmax_en_{s_idx}")
        if tmax_en:
            c1, c2 = st.columns(2)
            tmax_min = c1.number_input("Tmax Mín (°C)", value=0.0, step=0.5, key=f"tmax_min_{s_idx}")
            tmax_max = c2.number_input("Tmax Máx (°C)", value=40.0, step=0.5, key=f"tmax_max_{s_idx}")
        else:
            tmax_min = tmax_max = None

        tmin_en = st.checkbox("Limitar Temperatura Mínima (°C)", key=f"tmin_en_{s_idx}")
        if tmin_en:
            c1, c2 = st.columns(2)
            tmin_min = c1.number_input("Tmin Mín (°C)", value=-5.0, step=0.5, key=f"tmin_min_{s_idx}")
            tmin_max = c2.number_input("Tmin Máx (°C)", value=20.0, step=0.5, key=f"tmin_max_{s_idx}")
        else:
            tmin_min = tmin_max = None

        phase_inputs.append(dict(
            dur=dur, gdd_threshold=gdd_thresh,
            prec_en=prec_en, prec_min=prec_min, prec_max=prec_max,
            tmed_en=tmed_en, tmed_min=tmed_min, tmed_max=tmed_max,
            tmax_en=tmax_en, tmax_min=tmax_min, tmax_max=tmax_max,
            tmin_en=tmin_en, tmin_min=tmin_min, tmin_max=tmin_max,
        ))

# ── Régua de dias (modo Dias) ───────────────────────────────────────────────
def _safe(v, default):
    return v if v is not None else default


if sim_mode == "Duração (Dias)":
    durations_ok = all(ph["dur"] is not None and ph["dur"] > 0 for ph in phase_inputs)
else:
    durations_ok = (
        tbase is not None
        and all(ph["gdd_threshold"] is not None and ph["gdd_threshold"] > 0
                for ph in phase_inputs)
    )

if sim_mode == "Duração (Dias)" and durations_ok:
    total_days = sum(ph["dur"] for ph in phase_inputs)
    cursor, rows_ruler = 1, []
    for s_idx, ph in enumerate(phase_inputs):
        rows_ruler.append({
            "Estádio":       f"{STAGE_ICONS[s_idx]} {ESTAGIOS[s_idx]}",
            "Dia Início":    cursor,
            "Dia Fim":       cursor + ph["dur"] - 1,
            "Duração (dias)": ph["dur"],
        })
        cursor += ph["dur"]

    st.markdown("---")
    st.subheader("Régua de Dias da Simulação")
    st.dataframe(pd.DataFrame(rows_ruler), use_container_width=True, hide_index=True)
    c1, c2 = st.columns(2)
    c1.metric("Total de Dias do Ciclo", total_days)
    if total_days > 365:
        st.error("Ciclo ultrapassa 365 dias. Reduza as durações.")
        durations_ok = False
    else:
        c2.metric("Meses estimados", f"{total_days / 30:.1f}")

# ── Botão 1 — Processar ────────────────────────────────────────────────────
st.markdown("---")
col_b1, col_b2 = st.columns([1, 1])

with col_b1:
    btn_processar = st.button(
        "1. Processar Zoneamento",
        type="primary",
        disabled=not durations_ok or len(df_filtered) == 0,
        help="Varre os 36 decêndios possíveis de plantio para cada município.",
    )

if btn_processar:
    def _norm(ph):
        return dict(
            dur=ph["dur"],
            gdd_threshold=ph["gdd_threshold"],
            prec_en=ph["prec_en"],
            prec_min=_safe(ph["prec_min"], 0.0),
            prec_max=_safe(ph["prec_max"], 1e9),
            tmed_en=ph["tmed_en"],
            tmed_min=_safe(ph["tmed_min"], -99.0),
            tmed_max=_safe(ph["tmed_max"],  99.0),
            tmax_en=ph["tmax_en"],
            tmax_min=_safe(ph["tmax_min"], -99.0),
            tmax_max=_safe(ph["tmax_max"],  99.0),
            tmin_en=ph["tmin_en"],
            tmin_min=_safe(ph["tmin_min"], -99.0),
            tmin_max=_safe(ph["tmin_max"],  99.0),
        )

    phases_norm = [_norm(ph) for ph in phase_inputs]

    with st.spinner("Varrendo decêndios e municípios…"):
        if sim_mode == "Duração (Dias)":
            cycle_days = sum(ph["dur"] for ph in phase_inputs)
            df_result = run_zoneamento_days(df_filtered, phases_norm, cycle_days)
        else:
            df_result = run_zoneamento_gdd(df_filtered, phases_norm, float(tbase))

    if df_result.empty:
        st.warning(
            "Nenhum município apto encontrado. Considere relaxar os limites climáticos."
        )
        st.session_state.pop("result_df", None)
    else:
        df_result.to_parquet(TEMP_FILE, index=False)
        st.session_state["result_df"] = df_result
        st.success(
            f"Processamento concluído. **{len(df_result):,} municípios aptos** encontrados."
        )

# ── Botão 2 — Gerar Mapa e Tabela ─────────────────────────────────────────
has_result = "result_df" in st.session_state or os.path.exists(TEMP_FILE)

with col_b2:
    btn_mapa = st.button(
        "2. Gerar Mapa e Tabela",
        disabled=not has_result,
        help="Exibe o mapa interativo e a tabela de municípios aptos.",
    )

if btn_mapa:
    st.session_state["show_results"] = True

if st.session_state.get("show_results") and has_result:
    # Carrega resultado (prefere session_state; cai pro parquet se necessário)
    if "result_df" in st.session_state:
        df_res = st.session_state["result_df"]
    else:
        df_res = pd.read_parquet(TEMP_FILE)

    df_map = df_res.dropna(subset=["lat", "lon"])

    st.markdown("---")
    st.subheader("📊 Resultados do Zoneamento")

    # Métricas
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Municípios Aptos",      f"{len(df_res):,}")
    c2.metric("Estados Contempl.",     df_res["UF"].nunique())
    c3.metric("Máx. Janelas / Mun.",   int(df_res["Num_Decendios_Aptos"].max()))
    baixo_risco = (df_res["Num_Decendios_Aptos"] >= 3).mean() * 100
    c4.metric("Baixo Risco (≥3 jan.)", f"{baixo_risco:.0f}%")

    # Mapa Folium
    st.subheader("🗺️ Mapa Interativo dos Municípios Aptos")

    col_leg1, col_leg2, _ = st.columns([1, 1, 2])
    col_leg1.markdown(
        "<span style='background:#27ae60;color:#fff;padding:3px 10px;"
        "border-radius:4px;font-size:13px'>● Verde — ≥3 janelas</span>",
        unsafe_allow_html=True,
    )
    col_leg2.markdown(
        "<span style='background:#e67e22;color:#fff;padding:3px 10px;"
        "border-radius:4px;font-size:13px'>● Laranja — 1–2 janelas</span>",
        unsafe_allow_html=True,
    )

    m = folium.Map(
        location=[df_map["lat"].mean(), df_map["lon"].mean()],
        zoom_start=5,
        tiles="CartoDB positron",
    )

    for _, row in df_map.iterrows():
        n     = int(row["Num_Decendios_Aptos"])
        color = "#27ae60" if n >= 3 else "#e67e22"
        r     = 5 + min(n, 12)

        janelas_html = "".join(
            f"<li style='margin:2px 0'>🗓️ {j.strip()}</li>"
            for j in row["Janelas_Plantio"].split("|")
        )
        lims = row["Fatores_Limitantes"].split("|") if row["Fatores_Limitantes"] else []
        lim_block = ""
        if lims:
            lim_html = "".join(
                f"<li style='margin:2px 0;color:#c0392b'>⚠️ {p.strip()}</li>"
                for p in lims[:2]
            )
            lim_block = (
                "<hr style='margin:6px 0;border-color:#ddd'>"
                "<b style='color:#c0392b'>Fatores Restritivos:</b>"
                f"<ul style='margin:4px 0 0 0;padding-left:14px'>{lim_html}</ul>"
            )

        popup_html = (
            f"<div style='font-family:Arial,sans-serif;font-size:13px;"
            f"min-width:260px;max-width:380px;line-height:1.4'>"
            f"<b style='font-size:14px'>📍 {row['Municipio']} / {row['UF']}</b>"
            f"<span style='color:#555'> | ⛰️ {row['Altitude_m']} m</span><br>"
            f"<span style='color:#666;font-size:12px'>Solo: {row['Solo_Dominante']}</span>"
            f"<hr style='margin:6px 0;border-color:#ddd'>"
            f"<b style='color:#27ae60'>🌾 Janelas ({n}):</b>"
            f"<ul style='margin:4px 0 0 0;padding-left:14px'>{janelas_html}</ul>"
            f"{lim_block}</div>"
        )

        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=r, color=color, fill=True,
            fill_color=color, fill_opacity=0.80, weight=1.2,
            popup=folium.Popup(popup_html, max_width=400),
            tooltip=f"<b>{row['Municipio']} — {row['UF']}</b><br>{n} janela(s)",
        ).add_to(m)

    st_folium(m, width="100%", height=580, returned_objects=[])

    # Tabela
    st.subheader("📋 Tabela de Municípios Aptos")

    ufs   = ["Todos"] + sorted(df_res["UF"].unique().tolist())
    cf1, cf2 = st.columns([1, 2])
    uf_sel   = cf1.selectbox("Filtrar por UF:", ufs)
    _max_jan = max(2, int(df_res["Num_Decendios_Aptos"].max()))
    min_jan  = cf2.slider("Mínimo de janelas:", 1, _max_jan, 1)

    df_show = df_res.copy()
    if uf_sel != "Todos":
        df_show = df_show[df_show["UF"] == uf_sel]
    df_show = df_show[df_show["Num_Decendios_Aptos"] >= min_jan]
    df_show = df_show.sort_values(
        ["Num_Decendios_Aptos", "Municipio"], ascending=[False, True]
    ).reset_index(drop=True)

    st.dataframe(
        df_show[[
            "Municipio", "UF", "Altitude_m", "Solo_Dominante",
            "Num_Decendios_Aptos", "Janelas_Plantio", "Fatores_Limitantes",
        ]],
        use_container_width=True, hide_index=True,
        column_config={
            "Municipio":           st.column_config.TextColumn("Município"),
            "Altitude_m":          st.column_config.NumberColumn("Altitude (m)", format="%d m"),
            "Num_Decendios_Aptos": st.column_config.NumberColumn("Janelas Aptas", format="%d"),
            "Janelas_Plantio":     st.column_config.TextColumn("Janelas de Plantio", width="large"),
            "Fatores_Limitantes":  st.column_config.TextColumn("Fatores Limitantes",  width="large"),
        },
    )
    st.caption(f"Exibindo **{len(df_show):,}** município(s).")

    # ── Detalhes do município ──────────────────────────────────────────────
    if not df_show.empty:
        st.markdown("---")
        st.subheader("🔍 Detalhes do Município")

        nomes_lista = df_show["Municipio"].tolist()
        mun_sel = st.selectbox(
            "Selecione um município para ver as janelas de plantio:",
            nomes_lista,
            key="mun_detail_sel",
        )

        row_d = df_show[df_show["Municipio"] == mun_sel].iloc[0]
        janelas = [j.strip() for j in row_d["Janelas_Plantio"].split("|") if j.strip()]
        alt_str = f"{int(row_d['Altitude_m'])} m" if pd.notna(row_d["Altitude_m"]) else "N/D"

        col_info, col_jan = st.columns([1, 2])

        with col_info:
            st.markdown(
                f"**📍 {row_d['Municipio']} / {row_d['UF']}**  \n"
                f"⛰️ Altitude: **{alt_str}**  \n"
                f"🌱 Solo: **{row_d['Solo_Dominante']}**  \n"
                f"🌾 Janelas aptas: **{int(row_d['Num_Decendios_Aptos'])}**"
            )
            if row_d["Fatores_Limitantes"]:
                lims = [l.strip() for l in row_d["Fatores_Limitantes"].split("|") if l.strip()]
                if lims:
                    st.markdown("**⚠️ Fatores Restritivos:**")
                    for lim in lims:
                        st.markdown(f"- {lim}")

        with col_jan:
            st.markdown(f"**🗓️ Janelas de Plantio Aptas ({len(janelas)}):**")
            for j in janelas:
                st.markdown(f"&nbsp;&nbsp;&nbsp;🗓️ {j}", unsafe_allow_html=True)

    csv_bytes = df_show.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇️  Baixar CSV",
        data=csv_bytes,
        file_name="zoneamento_cevada.csv",
        mime="text/csv",
    )

    # Distribuição por estado
    st.subheader("📊 Distribuição por Estado")
    uf_agg = (
        df_res.groupby("UF")
        .agg(
            Municípios=("Municipio", "count"),
            Média_Janelas=("Num_Decendios_Aptos", "mean"),
            Máx_Janelas=("Num_Decendios_Aptos", "max"),
        )
        .sort_values("Municípios", ascending=False)
        .reset_index()
    )
    uf_agg["Média_Janelas"] = uf_agg["Média_Janelas"].round(1)
    st.dataframe(
        uf_agg, use_container_width=True, hide_index=True,
        column_config={
            "Média_Janelas": st.column_config.NumberColumn("Média Janelas", format="%.1f"),
            "Máx_Janelas":   st.column_config.NumberColumn("Máx. Janelas",  format="%d"),
        },
    )
