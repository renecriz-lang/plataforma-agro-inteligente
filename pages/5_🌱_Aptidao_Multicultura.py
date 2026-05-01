"""Aptidão Multicultura — zoneamento fenológico para qualquer cultura."""

import os
import sys

import numpy as np
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))

from utils.data_loader import load_base
from utils.simulation import run_zoneamento_days, run_zoneamento_gdd, DEC_LABEL
from utils.design import inject_css, hero_banner
from utils.culturas_templates import TEMPLATES, construir_cultura_generica
from utils.configs_culturas import listar_configs, salvar_config, carregar_config, remover_config
from utils.base_climatica_dinamica import base_climatica_filtrada, n_anos_na_base

# ── Constantes ──────────────────────────────────────────────────────────────
_GRUPO_ICON = {"vegetativo": "🌿", "reprodutivo": "🌸", "outro": "🚜"}
_ANOS_MIN, _ANOS_MAX = 2010, 2025
_MAX_FASES = 20  # máximo de estádios suportados (para limpeza de widget state)
TEMP_FILE = os.path.join(_HERE, "..", "resultado_multicultura_temp.parquet")


def _v(fase: dict, key: str, default):
    """Retorna fase[key] ou default quando ausente/None."""
    val = fase.get(key)
    return default if val is None else val


# ── Configuração da página ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Aptidão Multicultura",
    page_icon="🌱",
    layout="wide",
)

inject_css()
hero_banner(
    title="Aptidão Multicultura",
    subtitle=(
        "Simule o zoneamento agroclimático para qualquer cultura. "
        "Escolha um template, configure os estádios fenológicos e obtenha "
        "o mapa interativo de janelas de plantio aptas por município."
    ),
    icon="🌱",
)

with st.expander("ℹ️ Como usar este módulo", expanded=False):
    st.markdown("""
**Siga os passos abaixo para simular o zoneamento:**

**1. Configure o painel lateral**
Escolha o modo de simulação (**Dias** ou **GDD**), a base climática (**Média Geral**,
**Filtrada por ENSO** ou **Safra única**) e aplique os filtros de altitude e solo.

**2. Selecione uma cultura (aba 📋 Templates)**
Escolha um dos templates pré-configurados ou crie uma cultura genérica com N estádios.
Clique em **"Usar este template"** para ativá-lo na aba 🎯 Cultura ativa.

**3. Configure os estádios (aba 🎯 Cultura ativa)**
Para cada estádio, informe a duração em dias (ou GDD) e ative os limites climáticos
opcionais — precipitação, temperatura média, máxima e mínima.
Salve a configuração para reutilização futura.

**4. Processe e visualize**
Clique em **"1. Processar Zoneamento"** e depois **"2. Gerar Mapa e Tabela"**
para ver os resultados no mapa interativo com os municípios aptos.

---
**Sobre os decêndios:** o ano é dividido em 36 períodos de ~10 dias.
Cada decêndio representa uma possível data de semeadura e o ciclo completo é simulado a partir dele.
""")

# ── Painel lateral ─────────────────────────────────────────────────────────
st.sidebar.header("⚙️ Configuração Geral")

sim_mode = st.sidebar.radio(
    "Modo de simulação",
    options=["Duração (Dias)", "Grau-Dia (GDD)"],
    key="mc_sim_mode",
    help=(
        "**Dias**: cada estádio tem duração fixa em dias.\n\n"
        "**GDD**: a duração de cada estádio é determinada pela acumulação "
        "de grau-dia térmico (GD = max(0, (Tmax+Tmin)/2 − Tbase))."
    ),
)

tbase = None
if sim_mode == "Grau-Dia (GDD)":
    tbase = st.sidebar.number_input(
        "Tbase (°C)",
        min_value=-5.0, max_value=20.0, value=0.0, step=0.5,
        key="mc_tbase",
        help="Temperatura base para cálculo de GDD.",
    )

st.sidebar.markdown("---")
st.sidebar.subheader("🌡️ Base Climática")

modo_base = st.sidebar.radio(
    "Fonte dos dados",
    options=["Média Geral (2010–2025)", "Filtrada por ENSO", "Safra única"],
    key="mc_modo_base",
    help="Define qual base climática usar na simulação.",
)

# ── Controles condicionais da base climática ────────────────────────────────
if modo_base == "Filtrada por ENSO":
    st.sidebar.markdown("---")
    st.sidebar.subheader("🌊 Parâmetros ENSO")

    intervalo_anos = st.sidebar.slider(
        "Período",
        _ANOS_MIN, _ANOS_MAX, (_ANOS_MIN, _ANOS_MAX),
        key="mc_intervalo_anos",
    )
    fases_enso = st.sidebar.multiselect(
        "Fase ENSO",
        ["El Niño", "La Niña", "Neutro"],
        default=["El Niño", "La Niña", "Neutro"],
        key="mc_fases_enso",
    )
    intensidades_enso = st.sidebar.multiselect(
        "Intensidade (El Niño / La Niña)",
        ["Fraca", "Moderada", "Forte", "Muito Forte"],
        default=["Fraca", "Moderada", "Forte", "Muito Forte"],
        key="mc_intensidades_enso",
    )

    n_anos = n_anos_na_base(
        tuple(intervalo_anos),
        fases_enso or None,
        intensidades_enso or None,
    )
    if n_anos < 3:
        st.sidebar.warning(f"⚠️ Apenas {n_anos} ano(s) na seleção — resultados podem ser instáveis.")
    else:
        st.sidebar.info(f"✓ {n_anos} anos na seleção.")

    df_base = base_climatica_filtrada(
        intervalo_anos=tuple(intervalo_anos),
        fases_enso=fases_enso or None,
        intensidades_enso=intensidades_enso or None,
    )

elif modo_base == "Safra única":
    st.sidebar.markdown("---")
    st.sidebar.subheader("🗓️ Safra")
    safra_ano = st.sidebar.number_input(
        "Ano",
        min_value=_ANOS_MIN, max_value=_ANOS_MAX, value=2023, step=1,
        key="mc_safra_ano",
    )
    df_base = base_climatica_filtrada(safra_unica_ano=int(safra_ano))

else:  # Média Geral
    df_base = load_base("media_geral")

if df_base is None or df_base.empty:
    st.error(
        "Nenhum dado disponível com os parâmetros selecionados. "
        "Ajuste os filtros ENSO ou escolha outro modo de base climática."
    )
    st.stop()

# ── Filtros Guilhotina ──────────────────────────────────────────────────────
st.sidebar.markdown("---")
st.sidebar.subheader("🔪 Filtros Guilhotina")

alt_min_val = int(df_base["altitude_media"].dropna().min())
alt_max_val = int(df_base["altitude_media"].dropna().max())
alt_range = st.sidebar.slider(
    "Altitude (m)",
    alt_min_val, alt_max_val, (alt_min_val, alt_max_val),
    step=10, key="mc_alt_range",
)

solo_col = df_base["solo_1_ordem"].astype(str).replace("nan", "Não identificado")
solos_disp = sorted([v for v in solo_col.unique().tolist() if isinstance(v, str)])
solos_sel = st.sidebar.multiselect(
    "Solo Dominante",
    options=solos_disp,
    default=solos_disp,
    key="mc_solos_sel",
)

df_filtered = df_base[
    (df_base["altitude_media"].fillna(-1) >= alt_range[0])
    & (df_base["altitude_media"].fillna(-1) <= alt_range[1])
    & (solo_col.isin(solos_sel))
].reset_index(drop=True)

st.sidebar.metric("Municípios após filtros", f"{len(df_filtered):,}")

# ── Pending load handler — executa ANTES de qualquer widget mc_ ─────────────
_pending = st.session_state.pop("_mc_pending", None)
if _pending is not None:
    # Apaga todas as chaves de widget de fase para forçar re-render com novos defaults
    for _i in range(_MAX_FASES):
        for _suf in [
            "dur", "gdd",
            "prec_en", "prec_min", "prec_max",
            "tmed_en", "tmed_min", "tmed_max",
            "tmax_en", "tmax_min", "tmax_max",
            "tmin_en", "tmin_min", "tmin_max",
        ]:
            _k = f"mc_{_suf}_{_i}"
            if _k in st.session_state:
                del st.session_state[_k]

    # Define defaults a partir do config/template carregado
    for _i, _fase in enumerate(_pending["fases"]):
        if _fase.get("dur") is not None:
            st.session_state[f"mc_dur_{_i}"] = int(_fase["dur"])
        if _fase.get("gdd_threshold") is not None:
            st.session_state[f"mc_gdd_{_i}"] = float(_fase["gdd_threshold"])
        for _suf2 in ["prec_en", "tmed_en", "tmax_en", "tmin_en"]:
            if _fase.get(_suf2):
                st.session_state[f"mc_{_suf2}_{_i}"] = True
        for _suf3 in ["prec_min", "prec_max", "tmed_min", "tmed_max",
                      "tmax_min", "tmax_max", "tmin_min", "tmin_max"]:
            if _fase.get(_suf3) is not None:
                st.session_state[f"mc_{_suf3}_{_i}"] = float(_fase[_suf3])

    st.session_state["mc_fases"] = _pending["fases"]
    st.session_state["mc_cultura_nome"] = _pending.get("nome", "")
    st.session_state["mc_template_key"] = _pending.get("template_key", "generico")

# ── Tabs ────────────────────────────────────────────────────────────────────
aba_tmpl, aba_cfgs, aba_ativa = st.tabs([
    "📋 Templates",
    "💾 Minhas configurações",
    "🎯 Cultura ativa",
])

# ── Tab 1: Templates ────────────────────────────────────────────────────────
with aba_tmpl:
    template_keys = list(TEMPLATES.keys())
    template_labels = [TEMPLATES[k]["nome"] for k in template_keys]

    tmpl_sel_label = st.selectbox(
        "Selecione uma cultura",
        template_labels,
        key="mc_tmpl_sel",
    )
    tmpl_key = template_keys[template_labels.index(tmpl_sel_label)]
    tmpl = TEMPLATES[tmpl_key]

    st.caption(tmpl["descricao"])

    if tmpl_key == "generico":
        gc1, gc2, gc3 = st.columns(3)
        n_veg = gc1.number_input(
            "Estádios vegetativos", min_value=1, max_value=10, value=3, step=1,
            key="mc_n_veg",
        )
        n_rep = gc2.number_input(
            "Estádios reprodutivos", min_value=1, max_value=10, value=3, step=1,
            key="mc_n_rep",
        )
        inclui_colheita = gc3.checkbox(
            "Incluir Colheita", value=True, key="mc_inclui_colheita",
        )
        fases_tmpl = construir_cultura_generica(int(n_veg), int(n_rep), inclui_colheita)
    else:
        fases_tmpl = tmpl["fases"]

    if fases_tmpl:
        st.markdown("**Estádios do template:**")
        cols_prev = st.columns(min(len(fases_tmpl), 3))
        for idx, (nome_f, grupo_f) in enumerate(fases_tmpl):
            icon = _GRUPO_ICON.get(grupo_f, "🔹")
            cols_prev[idx % 3].markdown(f"{icon} {nome_f}")
    else:
        st.info("Defina o número de estádios acima.")

    st.markdown("")
    if st.button("✅ Usar este template", key="mc_btn_usar_tmpl", type="primary",
                 disabled=not fases_tmpl):
        fases_list = [{"nome": n, "grupo": g} for n, g in fases_tmpl]
        st.session_state["_mc_pending"] = {
            "nome": tmpl["nome"],
            "template_key": tmpl_key,
            "fases": fases_list,
        }
        st.rerun()

# ── Tab 2: Minhas configurações ─────────────────────────────────────────────
with aba_cfgs:
    configs_salvas = listar_configs()
    if not configs_salvas:
        st.info(
            "Nenhuma configuração salva ainda. "
            "Use a aba **📋 Templates** para escolher uma cultura, "
            "configure os estádios em **🎯 Cultura ativa** e clique em **💾 Salvar configuração**."
        )
    else:
        st.caption(f"{len(configs_salvas)} configuração(ões) salva(s).")
        for cfg in configs_salvas:
            cc1, cc2, cc3 = st.columns([4, 1, 1])
            cc1.markdown(f"**{cfg['nome']}** — modificado em {cfg['modificado_em']}")

            if cc2.button("📂 Carregar", key=f"mc_load_{cfg['slug']}"):
                data = carregar_config(cfg["slug"])
                st.session_state["_mc_pending"] = {
                    "nome": data.get("nome", cfg["nome"]),
                    "template_key": data.get("template_key", "generico"),
                    "fases": data.get("fases", []),
                }
                st.rerun()

            if cc3.button("🗑️ Excluir", key=f"mc_del_{cfg['slug']}"):
                remover_config(cfg["slug"])
                st.rerun()

# ── Tab 3: Cultura ativa ────────────────────────────────────────────────────
phase_inputs: list[dict] = []
durations_ok = False

with aba_ativa:
    mc_fases = st.session_state.get("mc_fases", [])

    if not mc_fases:
        st.info("⬆️ Selecione um template na aba **📋 Templates** para começar.")
    else:
        mc_cultura_nome = st.text_input(
            "Nome da configuração",
            value=st.session_state.get("mc_cultura_nome", ""),
            key="mc_cultura_nome_input",
            placeholder="Ex.: Cevada — Safra Sul, Soja Precoce…",
        )

        st.markdown(f"**{len(mc_fases)} estádio(s) configurados** — preencha as durações e limites:")

        for i, fase in enumerate(mc_fases):
            icon = _GRUPO_ICON.get(fase.get("grupo", ""), "🔹")
            with st.expander(f"{icon} {fase['nome']}", expanded=(i == 0)):
                col_dur, col_info = st.columns([1, 3])

                with col_dur:
                    if sim_mode == "Duração (Dias)":
                        dur = st.number_input(
                            "Duração (dias) *",
                            min_value=1, max_value=365,
                            value=fase.get("dur"),
                            step=1,
                            key=f"mc_dur_{i}",
                            placeholder="Obrigatório",
                        )
                        gdd_thresh = None
                    else:
                        gdd_thresh = st.number_input(
                            "GDD acumulado *",
                            min_value=1.0,
                            value=fase.get("gdd_threshold"),
                            step=10.0,
                            key=f"mc_gdd_{i}",
                            placeholder="Obrigatório",
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

                # Limites climáticos opcionais
                prec_en = st.checkbox(
                    "Limitar Precipitação Acumulada (mm)",
                    key=f"mc_prec_en_{i}",
                    value=_v(fase, "prec_en", False),
                )
                if prec_en:
                    c1, c2 = st.columns(2)
                    prec_min = c1.number_input(
                        "Prec. Mín (mm)", value=_v(fase, "prec_min", 0.0),
                        step=1.0, key=f"mc_prec_min_{i}",
                    )
                    prec_max = c2.number_input(
                        "Prec. Máx (mm)", value=_v(fase, "prec_max", 500.0),
                        step=1.0, key=f"mc_prec_max_{i}",
                    )
                else:
                    prec_min = prec_max = None

                tmed_en = st.checkbox(
                    "Limitar Temperatura Média (°C)",
                    key=f"mc_tmed_en_{i}",
                    value=_v(fase, "tmed_en", False),
                )
                if tmed_en:
                    c1, c2 = st.columns(2)
                    tmed_min = c1.number_input(
                        "Tmed Mín (°C)", value=_v(fase, "tmed_min", 5.0),
                        step=0.5, key=f"mc_tmed_min_{i}",
                    )
                    tmed_max = c2.number_input(
                        "Tmed Máx (°C)", value=_v(fase, "tmed_max", 30.0),
                        step=0.5, key=f"mc_tmed_max_{i}",
                    )
                else:
                    tmed_min = tmed_max = None

                tmax_en = st.checkbox(
                    "Limitar Temperatura Máxima (°C)",
                    key=f"mc_tmax_en_{i}",
                    value=_v(fase, "tmax_en", False),
                )
                if tmax_en:
                    c1, c2 = st.columns(2)
                    tmax_min = c1.number_input(
                        "Tmax Mín (°C)", value=_v(fase, "tmax_min", 0.0),
                        step=0.5, key=f"mc_tmax_min_{i}",
                    )
                    tmax_max = c2.number_input(
                        "Tmax Máx (°C)", value=_v(fase, "tmax_max", 40.0),
                        step=0.5, key=f"mc_tmax_max_{i}",
                    )
                else:
                    tmax_min = tmax_max = None

                tmin_en = st.checkbox(
                    "Limitar Temperatura Mínima (°C)",
                    key=f"mc_tmin_en_{i}",
                    value=_v(fase, "tmin_en", False),
                )
                if tmin_en:
                    c1, c2 = st.columns(2)
                    tmin_min = c1.number_input(
                        "Tmin Mín (°C)", value=_v(fase, "tmin_min", -5.0),
                        step=0.5, key=f"mc_tmin_min_{i}",
                    )
                    tmin_max = c2.number_input(
                        "Tmin Máx (°C)", value=_v(fase, "tmin_max", 20.0),
                        step=0.5, key=f"mc_tmin_max_{i}",
                    )
                else:
                    tmin_min = tmin_max = None

                phase_inputs.append(dict(
                    dur=dur, gdd_threshold=gdd_thresh,
                    prec_en=prec_en, prec_min=prec_min, prec_max=prec_max,
                    tmed_en=tmed_en, tmed_min=tmed_min, tmed_max=tmed_max,
                    tmax_en=tmax_en, tmax_min=tmax_min, tmax_max=tmax_max,
                    tmin_en=tmin_en, tmin_min=tmin_min, tmin_max=tmin_max,
                ))

        # Validação das durações
        if sim_mode == "Duração (Dias)":
            durations_ok = all(
                ph["dur"] is not None and ph["dur"] > 0 for ph in phase_inputs
            )
        else:
            durations_ok = (
                tbase is not None
                and all(
                    ph["gdd_threshold"] is not None and ph["gdd_threshold"] > 0
                    for ph in phase_inputs
                )
            )

        # Régua de dias
        if sim_mode == "Duração (Dias)" and durations_ok:
            total_days = sum(ph["dur"] for ph in phase_inputs)
            cursor, rows_ruler = 1, []
            for idx_r, (ph, fase) in enumerate(zip(phase_inputs, mc_fases)):
                icon_r = _GRUPO_ICON.get(fase.get("grupo", ""), "🔹")
                rows_ruler.append({
                    "Estádio":        f"{icon_r} {fase['nome']}",
                    "Dia Início":     cursor,
                    "Dia Fim":        cursor + ph["dur"] - 1,
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

        # Salvar configuração
        st.markdown("---")
        if st.button("💾 Salvar configuração", key="mc_btn_salvar"):
            nome_salvar = st.session_state.get("mc_cultura_nome_input", "").strip()
            if not nome_salvar:
                st.warning("Informe um nome para a configuração antes de salvar.")
            else:
                fases_salvar = []
                for i, fase in enumerate(mc_fases):
                    fases_salvar.append({
                        "nome":          fase["nome"],
                        "grupo":         fase["grupo"],
                        "dur":           st.session_state.get(f"mc_dur_{i}"),
                        "gdd_threshold": st.session_state.get(f"mc_gdd_{i}"),
                        "prec_en":       st.session_state.get(f"mc_prec_en_{i}", False),
                        "prec_min":      st.session_state.get(f"mc_prec_min_{i}"),
                        "prec_max":      st.session_state.get(f"mc_prec_max_{i}"),
                        "tmed_en":       st.session_state.get(f"mc_tmed_en_{i}", False),
                        "tmed_min":      st.session_state.get(f"mc_tmed_min_{i}"),
                        "tmed_max":      st.session_state.get(f"mc_tmed_max_{i}"),
                        "tmax_en":       st.session_state.get(f"mc_tmax_en_{i}", False),
                        "tmax_min":      st.session_state.get(f"mc_tmax_min_{i}"),
                        "tmax_max":      st.session_state.get(f"mc_tmax_max_{i}"),
                        "tmin_en":       st.session_state.get(f"mc_tmin_en_{i}", False),
                        "tmin_min":      st.session_state.get(f"mc_tmin_min_{i}"),
                        "tmin_max":      st.session_state.get(f"mc_tmin_max_{i}"),
                    })
                arq = salvar_config({
                    "nome":         nome_salvar,
                    "template_key": st.session_state.get("mc_template_key", "generico"),
                    "fases":        fases_salvar,
                })
                st.success(f"Configuração salva em `{arq.name}`.")
                st.session_state["mc_cultura_nome"] = nome_salvar

# ── Processamento ─────────────────────────────────────────────────────────
def _norm_fase(ph: dict) -> dict:
    """Normaliza phase_inputs para o formato esperado pelo motor de simulação."""
    def _s(v, default):
        return v if v is not None else default
    return dict(
        dur=ph["dur"],
        gdd_threshold=ph["gdd_threshold"],
        prec_en=ph["prec_en"],
        prec_min=_s(ph["prec_min"], 0.0),
        prec_max=_s(ph["prec_max"], 1e9),
        tmed_en=ph["tmed_en"],
        tmed_min=_s(ph["tmed_min"], -99.0),
        tmed_max=_s(ph["tmed_max"],  99.0),
        tmax_en=ph["tmax_en"],
        tmax_min=_s(ph["tmax_min"], -99.0),
        tmax_max=_s(ph["tmax_max"],  99.0),
        tmin_en=ph["tmin_en"],
        tmin_min=_s(ph["tmin_min"], -99.0),
        tmin_max=_s(ph["tmin_max"],  99.0),
    )


st.markdown("---")
col_b1, col_b2 = st.columns([1, 1])

with col_b1:
    btn_processar = st.button(
        "1. Processar Zoneamento",
        type="primary",
        disabled=not durations_ok or len(df_filtered) == 0,
        key="mc_btn_processar",
        help="Varre os 36 decêndios possíveis de plantio para cada município.",
    )

if btn_processar:
    phases_norm = [_norm_fase(ph) for ph in phase_inputs]
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
        st.session_state.pop("mc_result_df", None)
    else:
        df_result.to_parquet(TEMP_FILE, index=False)
        st.session_state["mc_result_df"] = df_result
        st.success(
            f"Processamento concluído. **{len(df_result):,} municípios aptos** encontrados."
        )

has_result = "mc_result_df" in st.session_state or os.path.exists(TEMP_FILE)

with col_b2:
    btn_mapa = st.button(
        "2. Gerar Mapa e Tabela",
        disabled=not has_result,
        key="mc_btn_mapa",
        help="Exibe o mapa interativo e a tabela de municípios aptos.",
    )

if btn_mapa:
    st.session_state["mc_show_results"] = True

if st.session_state.get("mc_show_results") and has_result:
    if "mc_result_df" in st.session_state:
        df_res = st.session_state["mc_result_df"]
    else:
        df_res = pd.read_parquet(TEMP_FILE)

    df_map = df_res.dropna(subset=["lat", "lon"])

    st.markdown("---")
    st.subheader("📊 Resultados do Zoneamento")

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
            f"<b style='color:#27ae60'>🌱 Janelas ({n}):</b>"
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
    uf_sel   = cf1.selectbox("Filtrar por UF:", ufs, key="mc_uf_sel")
    _max_jan = max(2, int(df_res["Num_Decendios_Aptos"].max()))
    min_jan  = cf2.slider("Mínimo de janelas:", 1, _max_jan, 1, key="mc_min_jan")

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

    # Detalhes do município
    if not df_show.empty:
        st.markdown("---")
        st.subheader("🔍 Detalhes do Município")

        mun_sel = st.selectbox(
            "Selecione um município para ver as janelas de plantio:",
            df_show["Municipio"].tolist(),
            key="mc_mun_detail_sel",
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
                f"🌿 Janelas aptas: **{int(row_d['Num_Decendios_Aptos'])}**"
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

    # CSV download
    csv_bytes = df_show.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇️  Baixar CSV",
        data=csv_bytes,
        file_name="zoneamento_multicultura.csv",
        mime="text/csv",
        key="mc_download_csv",
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
