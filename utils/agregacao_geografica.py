"""Agregação geográfica para o módulo Tendências Climáticas.

Agrupa a base long-format por (escopo, ano, decendio) e converte
decendial → mensal → anual.

Placeholder para ponderação por área municipal:
  PESOS_AREA = None  (quando o parquet chegar, carregar aqui)
"""

from __future__ import annotations

import pandas as pd

# ── Placeholder — ponderação por área ────────────────────────────────────────
# Quando disponível, deve ser um DataFrame com colunas [codigo_ibge, area_km2].
# Exemplo de carregamento futuro:
#   from pathlib import Path
#   _arq = Path("data/area_municipios.parquet")
#   PESOS_AREA = pd.read_parquet(_arq) if _arq.exists() else None
PESOS_AREA: pd.DataFrame | None = None


def agregar_por_escopo(
    df_long: pd.DataFrame,
    escopo: str,
    estado: str | None = None,
    municipio: int | str | None = None,
    variavel: str = "prec_media",
) -> pd.DataFrame:
    """Filtra por escopo e agrega por (ano, decendio).

    Parâmetros
    ----------
    df_long   : Base_Clima_Compacta já filtrada por intervalo de anos.
    escopo    : "Município" | "Estado" | "Brasil"
    estado    : UF (sigla) — obrigatório para Município e Estado.
    municipio : codigo_ibge — obrigatório para Município.
    variavel  : coluna a agregar (prec_media, tmax_media, tmed_media, tmin_media).

    Retorna
    -------
    DataFrame com colunas: ano, decendio, valor, enso_fenomeno, enso_intensidade.
    Vazio se não houver dados após os filtros.
    """
    df = df_long[df_long["flag_cobertura"] == "OK"].copy()

    if escopo == "Município":
        df = df[df["codigo_ibge"] == municipio]
    elif escopo == "Estado":
        df = df[df["estado"] == estado]
    # "Brasil" → sem filtro adicional

    if df.empty:
        return pd.DataFrame()

    # ── Ponderação por área (futuro) ──────────────────────────────────────
    if PESOS_AREA is not None and escopo != "Município":
        df = df.merge(PESOS_AREA, on="codigo_ibge", how="left")
        df["peso"] = df["area_km2"].fillna(df["area_km2"].mean())
        df["produto"] = df[variavel] * df["peso"]
        agrupado = (
            df.groupby(["ano", "decendio"], observed=True)
            .agg(
                soma_prod=("produto", "sum"),
                soma_pesos=("peso", "sum"),
                enso_fenomeno=("enso_fenomeno", "first"),
                enso_intensidade=("enso_intensidade", "first"),
            )
            .reset_index()
        )
        agrupado["valor"] = agrupado["soma_prod"] / agrupado["soma_pesos"]
        return agrupado[["ano", "decendio", "valor", "enso_fenomeno", "enso_intensidade"]]

    # ── Default: média simples não-ponderada ──────────────────────────────
    return (
        df.groupby(["ano", "decendio"], observed=True)
        .agg(
            valor=(variavel, "mean"),
            enso_fenomeno=("enso_fenomeno", "first"),
            enso_intensidade=("enso_intensidade", "first"),
        )
        .reset_index()
    )


def agregar_para_mensal(df_dec: pd.DataFrame, modo: str) -> pd.DataFrame:
    """Converte decendial → mensal.

    Parâmetros
    ----------
    df_dec : saída de agregar_por_escopo.
    modo   : "soma" (precipitação) | "media" (temperatura).

    Retorna
    -------
    DataFrame com colunas: ano, mes, valor, enso_fenomeno.
    """
    df = df_dec.copy()
    df["mes"] = ((df["decendio"] - 1) // 3) + 1

    def _moda(x: pd.Series):
        m = x.mode()
        return m.iloc[0] if not m.empty else None

    if modo == "soma":
        out = df.groupby(["ano", "mes"], as_index=False).agg(
            valor=("valor", "sum"),
            enso_fenomeno=("enso_fenomeno", _moda),
        )
    else:
        out = df.groupby(["ano", "mes"], as_index=False).agg(
            valor=("valor", "mean"),
            enso_fenomeno=("enso_fenomeno", _moda),
        )
    return out


def agregar_para_anual(df_mes: pd.DataFrame, modo: str) -> pd.DataFrame:
    """Converte mensal → anual.

    Parâmetros
    ----------
    df_mes : saída de agregar_para_mensal.
    modo   : "soma" | "media".

    Retorna
    -------
    DataFrame com colunas: ano, valor.
    """
    if modo == "soma":
        return df_mes.groupby("ano", as_index=False)["valor"].sum()
    return df_mes.groupby("ano", as_index=False)["valor"].mean()
