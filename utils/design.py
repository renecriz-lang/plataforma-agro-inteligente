"""
design.py — injeção de CSS e componentes HTML para o visual da plataforma.

Paleta: verde-campo (profissional, agrícola) com acentos dourados.
  --verde-escuro  : #1b4332   (cabeçalhos, sidebar ativa)
  --verde-medio   : #2d6a4f   (primary)
  --verde-claro   : #52b788   (hover, sucesso)
  --dourado       : #c9963a   (destaque)
  --fundo         : #f9f7f2   (warmwhite)
  --fundo-card    : #ffffff
  --texto         : #1b2d1e
"""

import streamlit as st

_CSS = """
<style>
/* ── Importa fonte distintiva ── */
@import url('https://fonts.googleapis.com/css2?family=Lora:wght@400;600;700&family=DM+Sans:wght@300;400;500;600&display=swap');

/* ── Variáveis ── */
:root {
  --verde-escuro  : #1b4332;
  --verde-medio   : #2d6a4f;
  --verde-claro   : #52b788;
  --verde-fundo   : #d8f3dc;
  --dourado       : #c9963a;
  --dourado-claro : #f0c87a;
  --fundo         : #f9f7f2;
  --fundo-card    : #ffffff;
  --fundo-sidebar : #edf2ee;
  --texto         : #1b2d1e;
  --texto-leve    : #4a6352;
  --borda         : #d0e4d8;
  --sombra        : 0 2px 12px rgba(27,67,50,0.10);
  --raio          : 10px;
  --raio-grande   : 16px;
}

/* ── Base da app ── */
html, body, [data-testid="stApp"] {
  font-family: 'DM Sans', sans-serif;
  background-color: var(--fundo) !important;
  color: var(--texto);
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
  background-color: var(--fundo-sidebar) !important;
  border-right: 1px solid var(--borda);
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
  color: var(--verde-escuro) !important;
  font-family: 'Lora', serif;
  font-size: 1rem;
  letter-spacing: 0.02em;
}
[data-testid="stSidebarNav"] a {
  border-radius: var(--raio);
  transition: background 0.2s, padding-left 0.2s;
}
[data-testid="stSidebarNav"] a:hover {
  background: var(--verde-fundo);
  padding-left: 8px;
}

/* ── Títulos principais ── */
h1 {
  font-family: 'Lora', serif !important;
  font-weight: 700;
  color: var(--verde-escuro) !important;
  letter-spacing: -0.02em;
  line-height: 1.2;
}
h2, h3 {
  font-family: 'Lora', serif !important;
  color: var(--verde-escuro) !important;
}

/* ── Botão primário ── */
[data-testid="stButton"] > button[kind="primary"] {
  background: linear-gradient(135deg, var(--verde-medio), var(--verde-escuro)) !important;
  color: #fff !important;
  border: none !important;
  border-radius: var(--raio) !important;
  font-weight: 600;
  letter-spacing: 0.03em;
  padding: 0.5rem 1.4rem !important;
  box-shadow: 0 4px 14px rgba(45,106,79,0.35) !important;
  transition: transform 0.15s, box-shadow 0.15s !important;
}
[data-testid="stButton"] > button[kind="primary"]:hover {
  transform: translateY(-2px) !important;
  box-shadow: 0 6px 20px rgba(45,106,79,0.45) !important;
}

/* ── Botão secundário ── */
[data-testid="stButton"] > button:not([kind="primary"]) {
  border: 2px solid var(--verde-medio) !important;
  border-radius: var(--raio) !important;
  color: var(--verde-medio) !important;
  background: transparent !important;
  font-weight: 500;
  transition: background 0.2s, color 0.2s !important;
}
[data-testid="stButton"] > button:not([kind="primary"]):hover {
  background: var(--verde-fundo) !important;
}

/* ── Métricas ── */
[data-testid="stMetric"] {
  background: var(--fundo-card);
  border: 1px solid var(--borda);
  border-radius: var(--raio-grande);
  padding: 1rem 1.25rem;
  box-shadow: var(--sombra);
  transition: transform 0.2s;
}
[data-testid="stMetric"]:hover {
  transform: translateY(-3px);
  box-shadow: 0 6px 20px rgba(27,67,50,0.15);
}
[data-testid="stMetricLabel"] {
  color: var(--texto-leve) !important;
  font-size: 0.82rem !important;
  font-weight: 500 !important;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
[data-testid="stMetricValue"] {
  color: var(--verde-escuro) !important;
  font-family: 'Lora', serif !important;
  font-size: 1.9rem !important;
  font-weight: 700 !important;
}

/* ── Expanders (estádios fenológicos) ── */
[data-testid="stExpander"] {
  border: 1px solid var(--borda) !important;
  border-radius: var(--raio-grande) !important;
  background: var(--fundo-card) !important;
  box-shadow: var(--sombra);
  margin-bottom: 0.5rem;
}
[data-testid="stExpander"] summary {
  font-family: 'DM Sans', sans-serif;
  font-weight: 600;
  color: var(--verde-escuro) !important;
  padding: 0.75rem 1rem;
}

/* ── Inputs ── */
[data-testid="stNumberInput"] input,
[data-testid="stTextInput"]   input {
  border-radius: var(--raio) !important;
  border: 1.5px solid var(--borda) !important;
  background: var(--fundo) !important;
  transition: border-color 0.2s;
}
[data-testid="stNumberInput"] input:focus,
[data-testid="stTextInput"]   input:focus {
  border-color: var(--verde-claro) !important;
  box-shadow: 0 0 0 3px rgba(82,183,136,0.2) !important;
}

/* ── Selectbox / Multiselect ── */
[data-testid="stSelectbox"] div[data-baseweb="select"],
[data-testid="stMultiSelect"] div[data-baseweb="select"] {
  border-radius: var(--raio) !important;
  border: 1.5px solid var(--borda) !important;
  background: var(--fundo) !important;
}

/* ── Slider ── */
[data-testid="stSlider"] [role="slider"] {
  background: var(--verde-medio) !important;
}

/* ── Alertas e info boxes ── */
[data-testid="stAlert"] {
  border-radius: var(--raio) !important;
}

/* ── Divisores ── */
hr {
  border-color: var(--borda) !important;
  margin: 1.5rem 0;
}

/* ── Dataframe ── */
[data-testid="stDataFrame"] {
  border-radius: var(--raio) !important;
  overflow: hidden;
  border: 1px solid var(--borda) !important;
}

/* ── Progress bar ── */
[data-testid="stProgressBar"] > div > div {
  background: linear-gradient(90deg, var(--verde-claro), var(--verde-medio)) !important;
  border-radius: 99px !important;
}

/* ── Download button ── */
[data-testid="stDownloadButton"] button {
  border-radius: var(--raio) !important;
  border: 2px solid var(--dourado) !important;
  color: var(--dourado) !important;
  background: transparent !important;
  font-weight: 600 !important;
  transition: background 0.2s !important;
}
[data-testid="stDownloadButton"] button:hover {
  background: rgba(201,150,58,0.1) !important;
}
</style>
"""


def inject_css() -> None:
    """Injeta o CSS global da plataforma. Chame no início de cada página."""
    st.markdown(_CSS, unsafe_allow_html=True)


def hero_banner(title: str, subtitle: str, icon: str = "🌾") -> None:
    """Renderiza o banner de cabeçalho das páginas."""
    st.markdown(
        f"""
        <div style="
          background: linear-gradient(135deg, #1b4332 0%, #2d6a4f 60%, #40916c 100%);
          border-radius: 16px;
          padding: 2rem 2.5rem;
          margin-bottom: 1.5rem;
          position: relative;
          overflow: hidden;
        ">
          <div style="
            position: absolute; top: -30px; right: -30px;
            font-size: 8rem; opacity: 0.08; user-select: none;
          ">{icon}</div>
          <h1 style="
            color: #ffffff !important;
            font-family: 'Lora', serif;
            margin: 0 0 0.4rem 0;
            font-size: 2rem;
          ">{icon} {title}</h1>
          <p style="
            color: rgba(255,255,255,0.82);
            margin: 0;
            font-size: 1rem;
            font-family: 'DM Sans', sans-serif;
          ">{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def badge(text: str, color: str = "#2d6a4f") -> str:
    """Retorna HTML de uma badge colorida inline."""
    return (
        f"<span style='background:{color};color:#fff;"
        f"padding:2px 10px;border-radius:99px;"
        f"font-size:0.78rem;font-weight:600;letter-spacing:0.04em'>"
        f"{text}</span>"
    )


def section_card(content_fn, title: str = "", icon: str = "") -> None:
    """Envolve conteúdo Streamlit num card com borda e sombra."""
    header = f"<h3 style='margin:0 0 1rem 0;color:#1b4332'>{icon} {title}</h3>" if title else ""
    st.markdown(
        f"<div style='background:#fff;border:1px solid #d0e4d8;"
        f"border-radius:16px;padding:1.5rem;box-shadow:0 2px 12px rgba(27,67,50,0.10);"
        f"margin-bottom:1rem'>{header}",
        unsafe_allow_html=True,
    )
    content_fn()
    st.markdown("</div>", unsafe_allow_html=True)
