"""
scripts/gerar_base_std.py

Pré-processamento: lê o parquet bruto (128 MB), filtra 2010-2025 sem SEM_DADOS,
computa desvio padrão amostral (ddof=1) por (município × decêndio) para as 4
variáveis climáticas e gera wide parquet com uma linha por município.

Saída: data/Base_Clima_std_2010_2025.parquet
"""

import os
import numpy as np
import pandas as pd

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT   = os.path.join(_SCRIPTS_DIR, "..")
_NOVO_APP    = os.path.join(_REPO_ROOT, "..")

RAW_PATH = os.path.join(
    _NOVO_APP, "DADOS_Clima_alt_solos_nino",
    "DADOS_Clima_alt_solos_nino.parquet",
)
OUT_PATH = os.path.join(_REPO_ROOT, "data", "Base_Clima_std_2010_2025.parquet")

VAR_MAP = {
    "prec_media": "Prec",
    "tmax_media": "Tmax",
    "tmed_media": "Tmed",
    "tmin_media": "Tmin",
}
VARS_RAW = list(VAR_MAP.keys())


def main() -> None:
    print("Lendo parquet bruto…")
    df = pd.read_parquet(RAW_PATH)
    print(f"  Shape original: {df.shape}")

    # ── Filtros ────────────────────────────────────────────────────────────
    mask = (
        (df["ano"] >= 2010)
        & (df["ano"] <= 2025)
        & (df["flag_cobertura"] != "SEM_DADOS")
    )
    df = df[mask].copy()
    print(f"  Shape após filtros (2010-2025, sem SEM_DADOS): {df.shape}")
    print(f"  Municípios únicos: {df['codigo_ibge'].nunique()}")

    # ── n_anos_validos por município ────────────────────────────────────────
    n_anos = (
        df.groupby("codigo_ibge")["ano"]
        .nunique()
        .rename("n_anos_validos")
        .reset_index()
    )

    # ── Desvio padrão amostral por (município × decêndio) ──────────────────
    print("Calculando desvios padrão (ddof=1)…")
    df_std = (
        df.groupby(["codigo_ibge", "nome", "estado", "decendio"])[VARS_RAW]
        .std(ddof=1)
        .reset_index()
    )

    # ── Pivot para wide format ─────────────────────────────────────────────
    print("Pivotando para wide format…")
    df_wide = df_std.pivot_table(
        index=["codigo_ibge", "nome", "estado"],
        columns="decendio",
        values=VARS_RAW,
    )

    # Achata MultiIndex: ("prec_media", 1) → "Prec_D1_std"
    df_wide.columns = [
        f"{VAR_MAP[var]}_D{int(dec)}_std"
        for var, dec in df_wide.columns
    ]
    df_wide = df_wide.reset_index()

    # ── Ordem de colunas: ids + Prec_D1..36 + Tmax.. + Tmed.. + Tmin.. ───
    id_cols  = ["codigo_ibge", "nome", "estado"]
    var_cols: list[str] = []
    for prefix in ["Prec", "Tmax", "Tmed", "Tmin"]:
        var_cols += [f"{prefix}_D{d}_std" for d in range(1, 37)]

    # Garante que todas as colunas existem (decêndios sem dados → NaN)
    for col in var_cols:
        if col not in df_wide.columns:
            df_wide[col] = np.nan

    df_wide = df_wide[id_cols + var_cols]

    # ── Adiciona n_anos_validos ────────────────────────────────────────────
    df_wide = df_wide.merge(n_anos, on="codigo_ibge", how="left")

    # ── Diagnóstico ────────────────────────────────────────────────────────
    nan_rows = df_wide[var_cols].isna().any(axis=1).sum()
    print(f"\n  Municípios no output:         {len(df_wide):,}")
    print(f"  Linhas com algum NaN em std:  {nan_rows:,}")
    print(f"  n_anos_validos — min: {df_wide['n_anos_validos'].min()}, "
          f"max: {df_wide['n_anos_validos'].max()}, "
          f"mediana: {df_wide['n_anos_validos'].median():.0f}")
    print(f"  Municípios com >= 10 anos:    "
          f"{(df_wide['n_anos_validos'] >= 10).sum():,}")

    # ── Salva ──────────────────────────────────────────────────────────────
    df_wide.to_parquet(OUT_PATH, index=False)
    size_mb = os.path.getsize(OUT_PATH) / 1e6
    print(f"\n  Salvo em: {OUT_PATH}")
    print(f"  Tamanho:  {size_mb:.2f} MB")
    print(f"  Colunas:  {df_wide.columns.tolist()[:5]} … "
          f"{df_wide.columns.tolist()[-3:]}")


if __name__ == "__main__":
    main()
