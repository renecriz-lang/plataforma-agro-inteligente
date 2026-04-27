"""Plataforma Agro Inteligente — Página Inicial."""

import os, sys
import streamlit as st

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from utils.data_loader import load_base, AGG_MODES
from utils.design import inject_css, hero_banner, badge
from utils.counter import increment, get_count, reset

st.set_page_config(
    page_title="Plataforma Agro Inteligente",
    page_icon="🌱",
    layout="wide",
)

inject_css()

# ── Contador de acessos ────────────────────────────────────────────────────
# Incrementa uma vez por sessão do usuário
if "counted" not in st.session_state:
    st.session_state["counted"] = True
    total_acessos = increment()
else:
    total_acessos = get_count()

# ── Painel Admin (sidebar) ─────────────────────────────────────────────────
ADMIN_PASSWORD = st.secrets.get("ADMIN_PASSWORD", "agro2025")

with st.sidebar:
    st.markdown("---")
    with st.expander("🔐 Admin"):
        pwd = st.text_input("Senha:", type="password", key="admin_pwd")
        if pwd == ADMIN_PASSWORD:
            st.success(f"Total de acessos: **{get_count()}**")
            if st.button("Zerar contador", type="primary"):
                reset()
                st.rerun()
        elif pwd:
            st.error("Senha incorreta.")

# ── Hero ───────────────────────────────────────────────────────────────────
hero_banner(
    title="Plataforma Agro Inteligente",
    subtitle=(
        "Zoneamento agroclimático com dados públicos — INMET · IBGE · EMBRAPA. "
        "Identifique onde e quando cultivar com precisão científica."
    ),
    icon="🌱",
)

# ── Sumário da Base ────────────────────────────────────────────────────────
with st.spinner("Carregando base…"):
    df = load_base()

col_a, col_b, col_c, col_d, col_e = st.columns(5)
col_a.metric("Municípios",        f"{len(df):,}")
col_b.metric("Período base",      "2010–2025")
col_c.metric("Decêndios / Mun.",  "36")
col_d.metric("Estados cobertos",  df["estado"].nunique())
col_e.metric("Acessos",           f"{total_acessos:,}")

st.markdown("---")

# ── Módulos ────────────────────────────────────────────────────────────────
st.subheader("Módulos Disponíveis")

col1, col2 = st.columns([3, 2])

with col1:
    st.markdown(
        f"""
        <div style="background:#fff;border:1px solid #d0e4d8;border-radius:16px;
                    padding:1.5rem;box-shadow:0 2px 12px rgba(27,67,50,0.10)">
          <div style="font-size:2.5rem;margin-bottom:0.5rem">🌾</div>
          <h3 style="color:#1b4332;margin:0 0 0.4rem 0;font-family:'Lora',serif">
            Aptidão da Cevada
          </h3>
          <p style="color:#4a6352;margin:0 0 1rem 0;font-size:0.95rem">
            Simulação fenológica completa com dois modos: <strong>duração em dias</strong>
            ou <strong>acumulação de grau-dia (GDD)</strong>. Filtre por altitude e solo,
            defina os requisitos climáticos de cada estádio e obtenha o mapa
            interativo das janelas de plantio aptas.
          </p>
          <span style="background:#2d6a4f;color:#fff;padding:3px 12px;
                       border-radius:99px;font-size:0.8rem;font-weight:600">
            ✅ Disponível
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col2:
    st.markdown(
        """
        <div style="background:#f9f7f2;border:1px dashed #c0d4c8;border-radius:16px;
                    padding:1.5rem;opacity:0.7">
          <div style="font-size:2rem;margin-bottom:0.5rem">🔬</div>
          <h4 style="color:#4a6352;margin:0 0 0.3rem 0;font-family:'Lora',serif">
            Mais Módulos — Em Breve
          </h4>
          <ul style="color:#4a6352;font-size:0.9rem;padding-left:1.2rem;margin:0.5rem 0 0 0">
            <li>Gêmeos Climáticos (Machine Learning)</li>
            <li>Resiliência ENSO / El Niño</li>
            <li>Expansão e Yield Gap</li>
          </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ── Rodapé ────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<div style='text-align:center;color:#8a9e8f;font-size:0.82rem;padding:0.5rem 0'>"
    "Dados: INMET · IBGE · EMBRAPA &nbsp;·&nbsp; "
    "Projeto Integrador — Big Data &nbsp;·&nbsp; 2025"
    "</div>",
    unsafe_allow_html=True,
)
