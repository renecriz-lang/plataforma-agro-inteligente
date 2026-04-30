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
try:
    ADMIN_PASSWORD = st.secrets.get("ADMIN_PASSWORD", "")
except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
    ADMIN_PASSWORD = ""

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
        <div style="background:#fff;border:1px solid #d0e4d8;border-radius:16px;
                    padding:1.5rem;box-shadow:0 2px 12px rgba(27,67,50,0.10)">
          <div style="font-size:2.5rem;margin-bottom:0.5rem">🌍</div>
          <h3 style="color:#1b4332;margin:0 0 0.4rem 0;font-family:'Lora',serif">
            Gêmeos Climáticos
          </h3>
          <p style="color:#4a6352;margin:0 0 1rem 0;font-size:0.95rem">
            Identifique municípios brasileiros com <strong>clima análogo</strong>
            ao de uma referência. Descubra novas regiões e janelas de plantio
            por similaridade climática — abre fronteiras de diversificação.
          </p>
          <span style="background:#2d6a4f;color:#fff;padding:3px 12px;
                       border-radius:99px;font-size:0.8rem;font-weight:600">
            ✅ Disponível
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.page_link(
        "pages/2_🌍_Gemeos_Climaticos.py",
        label="Abrir módulo →",
        icon="🌍",
    )

st.markdown("---")
st.subheader("Análise Climática Avançada")

col3, col4 = st.columns([3, 2])

with col3:
    st.markdown(
        """
        <div style="background:#fff;border:1px solid #d0e4d8;border-radius:16px;
                    padding:1.5rem;box-shadow:0 2px 12px rgba(27,67,50,0.10)">
          <div style="font-size:2.5rem;margin-bottom:0.5rem">🌊</div>
          <h3 style="color:#1b4332;margin:0 0 0.4rem 0;font-family:'Lora',serif">
            Resiliência ENSO
          </h3>
          <p style="color:#4a6352;margin:0 0 1rem 0;font-size:0.95rem">
            Análise probabilística do impacto de <strong>El Niño, La Niña e Neutro</strong>
            sobre eventos climáticos críticos e rendimento produtivo real.
            Motor de análogos históricos para projetar o ano corrente.
          </p>
          <span style="background:#2d6a4f;color:#fff;padding:3px 12px;
                       border-radius:99px;font-size:0.8rem;font-weight:600">
            ✅ Disponível
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.page_link(
        "pages/3_🌍_Resiliencia_ENSO.py",
        label="Abrir módulo →",
        icon="🌊",
    )

with col4:
    st.markdown(
        """
        <div style="background:#fff;border:1px solid #d0e4d8;border-radius:16px;
                    padding:1.5rem;box-shadow:0 2px 12px rgba(27,67,50,0.10)">
          <div style="font-size:2.5rem;margin-bottom:0.5rem">📈</div>
          <h3 style="color:#1b4332;margin:0 0 0.4rem 0;font-family:'Lora',serif">
            Comparador de Cenários
          </h3>
          <p style="color:#4a6352;margin:0 0 1rem 0;font-size:0.95rem">
            Monte perfis climáticos históricos combinando <strong>intervalo de anos,
            fase e intensidade ENSO</strong> e compare num único gráfico decendial.
            Responda: "El Niño Forte chove diferente de La Niña Forte aqui?"
          </p>
          <span style="background:#2d6a4f;color:#fff;padding:3px 12px;
                       border-radius:99px;font-size:0.8rem;font-weight:600">
            ✅ Disponível
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.page_link(
        "pages/4_📈_Comparador_Cenarios.py",
        label="Abrir módulo →",
        icon="📈",
    )

st.markdown("---")
st.subheader("Simulação Multicultura")

col5, _ = st.columns([3, 2])

with col5:
    st.markdown(
        """
        <div style="background:#fff;border:1px solid #d0e4d8;border-radius:16px;
                    padding:1.5rem;box-shadow:0 2px 12px rgba(27,67,50,0.10)">
          <div style="font-size:2.5rem;margin-bottom:0.5rem">🌱</div>
          <h3 style="color:#1b4332;margin:0 0 0.4rem 0;font-family:'Lora',serif">
            Aptidão Multicultura
          </h3>
          <p style="color:#4a6352;margin:0 0 1rem 0;font-size:0.95rem">
            Generalize o motor de zoneamento para <strong>qualquer cultura</strong>.
            Escolha entre 5 templates pré-configurados (cevada, soja, milho, feijão, trigo)
            ou crie estádios personalizados. Simule com base climática média, filtrada por
            <strong>ENSO</strong> ou por <strong>safra única</strong>.
          </p>
          <span style="background:#2d6a4f;color:#fff;padding:3px 12px;
                       border-radius:99px;font-size:0.8rem;font-weight:600">
            ✅ Disponível
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.page_link(
        "pages/5_🌱_Aptidao_Multicultura.py",
        label="Abrir módulo →",
        icon="🌱",
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
