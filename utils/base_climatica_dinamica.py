"""Geração on-demand de bases climáticas wide-format alinhadas com o motor.

O motor de simulação (utils/simulation.py) espera um DataFrame wide com colunas:
  codigo_ibge, nome, estado, altitude_media, solo_1_ordem, lat, lon,
  Prec_D1..D36, Tmax_D1..D36, Tmed_D1..D36, Tmin_D1..D36

Esta função constrói esse DataFrame a partir da Base_Clima_Compacta.parquet
aplicando filtros de intervalo de anos, fase ENSO, intensidade ou safra única.
"""

import numpy as np
import pandas as pd
import streamlit as st

from utils.data_loader import carregar_base_clima_compacta

_META_COLS = ["codigo_ibge", "nome", "estado", "altitude_media", "solo_1_ordem", "lat", "lon"]
_VARIAVEIS = [("prec_media", "Prec"), ("tmax_media", "Tmax"),
              ("tmed_media", "Tmed"), ("tmin_media", "Tmin")]


def _piv_long_para_wide(df_long: pd.DataFrame, agg: str = "mean") -> pd.DataFrame:
    """Converte long-format em wide-format com 144 colunas climáticas.

    agg='mean'  → média sobre os anos filtrados (modo padrão)
    agg='first' → primeiro valor por município (safra única)
    """
    bases: list[pd.DataFrame] = []
    for var, prefixo in _VARIAVEIS:
        aggfunc = "mean" if agg == "mean" else "first"
        piv = df_long.pivot_table(
            index="codigo_ibge", columns="decendio",
            values=var, aggfunc=aggfunc, observed=True,
        )
        piv.columns = [f"{prefixo}_D{int(c)}" for c in piv.columns]
        bases.append(piv)
    return pd.concat(bases, axis=1).reset_index()


@st.cache_data(show_spinner="Calculando base climática personalizada…")
def base_climatica_filtrada(
    intervalo_anos: tuple[int, int] | None = None,
    fases_enso: list[str] | None = None,
    intensidades_enso: list[str] | None = None,
    safra_unica_ano: int | None = None,
) -> pd.DataFrame:
    """Retorna DataFrame wide compatível com o motor de simulação.

    Se safra_unica_ano for fornecido, usa apenas aquele ano (sem média).
    Caso contrário aplica intervalo + filtros ENSO e calcula a média.

    Retorna DataFrame vazio se não houver dados após os filtros.
    """
    df = carregar_base_clima_compacta()
    df = df[df["flag_cobertura"] == "OK"].copy()

    if safra_unica_ano is not None:
        df = df[df["ano"] == safra_unica_ano]
        agg = "first"
    else:
        if intervalo_anos:
            df = df[df["ano"].between(intervalo_anos[0], intervalo_anos[1])]
        if fases_enso:
            df = df[df["enso_fenomeno"].isin(fases_enso)]
        if intensidades_enso:
            mask_neutro = df["enso_fenomeno"] == "Neutro"
            mask_match  = df["enso_intensidade"].isin(intensidades_enso)
            df = df[mask_neutro | mask_match]
        agg = "mean"

    if df.empty:
        return pd.DataFrame()

    df_wide = _piv_long_para_wide(df, agg=agg)

    # Metadados estáticos da base wide (altitude, solo, coordenadas, nome, estado)
    base_meta = pd.read_parquet(
        "data/Base_Clima_media_geral.parquet",
        columns=_META_COLS,
    )
    df_wide = df_wide.merge(base_meta, on="codigo_ibge", how="left")

    # Garante que todas as 144 colunas existem (decêndios sem dados ficam NaN)
    for prefixo in ["Prec", "Tmax", "Tmed", "Tmin"]:
        for d in range(1, 37):
            col = f"{prefixo}_D{d}"
            if col not in df_wide.columns:
                df_wide[col] = np.nan

    return df_wide


def n_anos_na_base(
    intervalo_anos: tuple[int, int] | None = None,
    fases_enso: list[str] | None = None,
    intensidades_enso: list[str] | None = None,
) -> int:
    """Conta quantos anos distintos restam após os filtros (para aviso de n<3)."""
    df = carregar_base_clima_compacta()
    df = df[df["flag_cobertura"] == "OK"]
    if intervalo_anos:
        df = df[df["ano"].between(intervalo_anos[0], intervalo_anos[1])]
    if fases_enso:
        df = df[df["enso_fenomeno"].isin(fases_enso)]
    if intensidades_enso:
        mask_neutro = df["enso_fenomeno"] == "Neutro"
        df = df[mask_neutro | df["enso_intensidade"].isin(intensidades_enso)]
    return int(df["ano"].nunique())
