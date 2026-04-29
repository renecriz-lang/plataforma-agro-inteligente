"""
data_loader.py — carrega os dados precomputados para o app.

Os parquets em data/ foram gerados pelo script gerar_base_preprocessada.py
e contêm médias históricas por município × decêndio em formato wide.
"""

import os
import requests
import pandas as pd
import streamlit as st
from pathlib import Path

_HERE  = os.path.dirname(os.path.abspath(__file__))
_DATA  = os.path.join(_HERE, "..", "data")

# Modos de agregação disponíveis: chave → rótulo legível
AGG_MODES: dict[str, str] = {
    "media_geral": "Média Geral (2010–2025)",
    # Novos modos serão registrados aqui quando disponíveis
}

# URL do GitHub Release (atualizar após criar o release v1.0-data)
_URL_BASE_CLIMA_COMPACTA = (
    "https://github.com/renecriz-lang/plataforma-agro-inteligente/"
    "releases/download/v1.0-data/Base_Clima_Compacta.parquet"
)
_CAMINHO_LOCAL_CLIMA = Path(_DATA) / "Base_Clima_Compacta.parquet"


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


@st.cache_resource(
    show_spinner="Baixando base climática histórica (~33 MB) — apenas na primeira execução…"
)
def carregar_base_clima_compacta() -> pd.DataFrame:
    """Baixa Base_Clima_Compacta.parquet do GitHub Release se necessário.
    Cacheia em memória entre sessões via cache_resource.
    """
    if not _CAMINHO_LOCAL_CLIMA.exists():
        _CAMINHO_LOCAL_CLIMA.parent.mkdir(parents=True, exist_ok=True)
        try:
            r = requests.get(_URL_BASE_CLIMA_COMPACTA, stream=True, timeout=300)
            r.raise_for_status()
            with open(_CAMINHO_LOCAL_CLIMA, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
        except Exception as e:
            st.error(
                f"Falha ao baixar a base climática: {e}\n\n"
                "Verifique se o arquivo foi publicado no GitHub Release "
                "`v1.0-data` do repositório `plataforma-agro-inteligente`."
            )
            st.stop()
    return pd.read_parquet(_CAMINHO_LOCAL_CLIMA)


@st.cache_data(show_spinner=False)
def carregar_base_producao() -> pd.DataFrame:
    """Carrega Base_Producao_Compacta.parquet (produção real por município × cultura × ano)."""
    path = os.path.join(_DATA, "Base_Producao_Compacta.parquet")
    if not os.path.exists(path):
        st.error(
            "Base de produção não encontrada. "
            "Execute `gerar_bases_resiliencia.py` e commite os arquivos em `data/`."
        )
        st.stop()
    return pd.read_parquet(path)


@st.cache_data(show_spinner=False)
def carregar_resiliencia_precomp() -> pd.DataFrame:
    """Carrega Base_Resiliencia_PreComp.parquet (probabilidades pré-computadas por município × evento × fase)."""
    path = os.path.join(_DATA, "Base_Resiliencia_PreComp.parquet")
    if not os.path.exists(path):
        st.error(
            "Base pré-computada de resiliência não encontrada. "
            "Execute `gerar_bases_resiliencia.py` e commite os arquivos em `data/`."
        )
        st.stop()
    return pd.read_parquet(path)
