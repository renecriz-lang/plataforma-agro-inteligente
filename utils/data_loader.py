"""
data_loader.py — carrega os dados precomputados para o app.

Os parquets em data/ foram gerados pelo script gerar_base_preprocessada.py
e contêm médias históricas por município × decêndio em formato wide.
"""

import os
import pandas as pd
import streamlit as st

_HERE  = os.path.dirname(os.path.abspath(__file__))
_DATA  = os.path.join(_HERE, "..", "data")

# Modos de agregação disponíveis: chave → rótulo legível
AGG_MODES: dict[str, str] = {
    "media_geral": "Média Geral (2010–2025)",
    # Novos modos serão registrados aqui quando disponíveis
}


@st.cache_data(show_spinner="Carregando base climática…")
def load_base(agg_mode: str = "media_geral") -> pd.DataFrame:
    """Retorna o DataFrame wide-format para o modo de agregação selecionado."""
    path = os.path.join(_DATA, f"Base_Clima_{agg_mode}.parquet")
    if not os.path.exists(path):
        st.error(
            f"Base de dados '{agg_mode}' não encontrada em `{path}`. "
            "Execute `gerar_base_preprocessada.py` primeiro."
        )
        st.stop()
    return pd.read_parquet(path)
