"""
twin_engine.py — motor de similaridade climática para o módulo Gêmeos Climáticos.

Toda a matemática fica aqui; a página 2_Gemeos_Climaticos.py fica magra.
Vetorização numpy completa: sem loops Python por município no cálculo dos scores.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import streamlit as st

from utils.data_loader import load_base
from utils.simulation import DEC_LABEL

_HERE    = os.path.dirname(os.path.abspath(__file__))
_DATA    = os.path.join(_HERE, "..", "data")
STD_PATH = os.path.join(_DATA, "Base_Clima_std_2010_2025.parquet")

VARS = ["Prec", "Tmax", "Tmed", "Tmin"]


# ── Loaders ────────────────────────────────────────────────────────────────

@st.cache_data(show_spinner="Carregando base de médias…")
def load_means() -> pd.DataFrame:
    """Wide-format com médias históricas. Reutiliza o parquet de media_geral."""
    return load_base("media_geral")


@st.cache_data(show_spinner="Carregando base de desvios padrão…")
def load_stds() -> pd.DataFrame:
    if not os.path.exists(STD_PATH):
        st.error(
            "Base de desvios padrão não encontrada em `data/Base_Clima_std_2010_2025.parquet`. "
            "Execute `scripts/gerar_base_std.py` primeiro."
        )
        st.stop()
    return pd.read_parquet(STD_PATH)


# ── Utilitários de período ─────────────────────────────────────────────────

def dec_period_indices(dec_ini: int, dec_fim: int) -> list[int]:
    """
    Retorna lista de índices 0-based dos decêndios que compõem o período.

    Suporta wraparound: dec_ini=28, dec_fim=9 → [27,28,...,35,0,...,8].
    """
    if dec_ini <= dec_fim:
        return list(range(dec_ini - 1, dec_fim))
    return list(range(dec_ini - 1, 36)) + list(range(0, dec_fim))


# ── Régua climática ────────────────────────────────────────────────────────

def build_ruler(
    means_row: pd.Series,
    stds_row: pd.Series,
    period_idx: list[int],
    k: float,
) -> dict:
    """
    Constrói a régua [lower, upper] para cada (posição no período, variável).

    Retorna dict com:
        "lower": np.ndarray (P, 4)  — limites inferiores
        "upper": np.ndarray (P, 4)  — limites superiores
        "means": np.ndarray (P, 4)  — médias do município de referência
        "stds":  np.ndarray (P, 4)  — desvios do município de referência
    """
    P = len(period_idx)
    means_arr = np.zeros((P, 4), dtype=np.float64)
    stds_arr  = np.zeros((P, 4), dtype=np.float64)

    for j, dec_0 in enumerate(period_idx):
        d = dec_0 + 1  # converte índice 0-based → rótulo 1-based
        for v, var in enumerate(VARS):
            m = means_row.get(f"{var}_D{d}", np.nan)
            s = stds_row.get(f"{var}_D{d}_std", np.nan)
            means_arr[j, v] = float(m) if pd.notna(m) else 0.0
            # NaN std → 0: régua pontual (match exato), conservador mas não quebra
            stds_arr[j, v]  = float(s) if pd.notna(s) else 0.0

    lower = means_arr - k * stds_arr
    upper = means_arr + k * stds_arr

    # Precipitação nunca negativa
    lower[:, 0] = np.maximum(0.0, lower[:, 0])

    return {"lower": lower, "upper": upper, "means": means_arr, "stds": stds_arr}


# ── Motor principal (totalmente vetorizado) ────────────────────────────────

def compute_twins(
    df_candidates: pd.DataFrame,
    period_idx: list[int],
    ruler: dict,
) -> pd.DataFrame:
    """
    Calcula score de similaridade para todos os candidatos × 36 janelas.

    Sem loops Python por município — opera em tensores numpy.
    Complexidade de memória: N × 36 × P × 4 × float32 (~116 MB no pior caso).

    Retorna DataFrame com N_candidatos × 36 linhas.
    """
    N = len(df_candidates)
    P = len(period_idx)

    if N == 0 or P == 0:
        return pd.DataFrame()

    # ── Tensor (N, 36, 4): candidato × decêndio × variável ────────────────
    def _col(prefix: str) -> np.ndarray:
        return (
            df_candidates[[f"{prefix}_D{d}" for d in range(1, 37)]]
            .values.astype(np.float32)
        )  # (N, 36)

    means_arr = np.stack(
        [_col("Prec"), _col("Tmax"), _col("Tmed"), _col("Tmin")], axis=2
    )  # (N, 36, 4)

    # ── dec_idx[s, j] = (s + j) % 36 ─────────────────────────────────────
    # Para cada janela s (0..35) e posição j (0..P-1), o índice 0-based do decêndio
    dec_idx = np.array(
        [[(s + j) % 36 for j in range(P)] for s in range(36)],
        dtype=np.int32,
    )  # (36, P)

    # ── candidate_window[i, s, j, v] = means_arr[i, dec_idx[s,j], v] ─────
    # Indexação avançada numpy: axis 1 substituído por (36, P) → (N, 36, P, 4)
    candidate_window = means_arr[:, dec_idx, :]  # (N, 36, P, 4)

    # ── Comparação com a régua ─────────────────────────────────────────────
    lower = ruler["lower"].astype(np.float32)[None, None, :, :]  # (1, 1, P, 4)
    upper = ruler["upper"].astype(np.float32)[None, None, :, :]  # (1, 1, P, 4)

    within = (candidate_window >= lower) & (candidate_window <= upper)  # (N, 36, P, 4)

    scores          = within.mean(axis=2) * 100.0   # (N, 36, 4) — % por variável
    score_combinado = scores.mean(axis=-1)           # (N, 36)    — média das 4 vars

    # ── Monta DataFrame flat (N × 36 linhas) ──────────────────────────────
    mun_idx = np.repeat(np.arange(N), 36)   # (N*36,)
    win_idx = np.tile(np.arange(36), N)     # (N*36,)

    def _win_labels(s0: int) -> tuple[str, str]:
        ini = s0 + 1
        fim = (s0 + P - 1) % 36 + 1
        return DEC_LABEL[ini], DEC_LABEL[fim]

    labels  = [_win_labels(s) for s in range(36)]
    ini_arr = np.array([lbl[0] for lbl in labels])  # (36,)
    fim_arr = np.array([lbl[1] for lbl in labels])  # (36,)

    # solo_1_ordem pode ser Categorical — converte para string
    solo_vals = df_candidates["solo_1_ordem"].astype(str).values
    solo_vals[solo_vals == "nan"] = "Não identificado"

    result = pd.DataFrame({
        "codigo_ibge":     df_candidates["codigo_ibge"].values[mun_idx],
        "nome":            df_candidates["nome"].values[mun_idx],
        "estado":          df_candidates["estado"].values[mun_idx],
        "lat":             df_candidates["lat"].values[mun_idx],
        "lon":             df_candidates["lon"].values[mun_idx],
        "altitude_media":  df_candidates["altitude_media"].values[mun_idx],
        "solo_1_ordem":    solo_vals[mun_idx],
        "decendio_inicio": win_idx + 1,
        "data_inicio_str": ini_arr[win_idx],
        "data_fim_str":    fim_arr[win_idx],
        "score_prec":      scores[:, :, 0].ravel().astype(np.float32),
        "score_tmax":      scores[:, :, 1].ravel().astype(np.float32),
        "score_tmed":      scores[:, :, 2].ravel().astype(np.float32),
        "score_tmin":      scores[:, :, 3].ravel().astype(np.float32),
        "score_combinado": score_combinado.ravel().astype(np.float32),
    })

    return result


# ── Identificação de janelas ótimas ───────────────────────────────────────

def extract_best_windows(gemeos_df: pd.DataFrame) -> pd.DataFrame:
    """
    Para cada município, identifica 1–2 janelas ótimas via análise de picos.

    Usa scipy.signal.find_peaks com distance=3. Se nenhum pico encontrado,
    retorna o argmax. Retorna DataFrame com 1 ou 2 linhas por município.

    Implementação vetorizada: evita groupby + append de Series (lento).
    Substitui por np.unique + slicing direto e fancy indexing no final.
    """
    from scipy.signal import find_peaks

    # Ordena garantindo que cada município tem seus 36 decêndios contíguos
    df_s = gemeos_df.sort_values(["codigo_ibge", "decendio_inicio"]).reset_index(drop=True)

    ibge_arr  = df_s["codigo_ibge"].values
    scores_all = df_s["score_combinado"].values

    # Índice de início de cada grupo de município
    _, first_idx = np.unique(ibge_arr, return_index=True)
    starts = np.append(first_idx, len(df_s))  # sentinela no final

    best_pos: list[int] = []  # posições em df_s das linhas escolhidas

    for i in range(len(first_idx)):
        s, e = int(starts[i]), int(starts[i + 1])
        scores = scores_all[s:e]

        peaks, _ = find_peaks(scores, distance=3)

        if len(peaks) == 0:
            peaks = np.array([int(np.argmax(scores))])

        top = peaks[np.argsort(scores[peaks])[::-1]][:2]

        for pk in top:
            best_pos.append(s + int(pk))

    if not best_pos:
        return pd.DataFrame()

    return df_s.iloc[best_pos].reset_index(drop=True)


# ── Dados para comparação detalhada ───────────────────────────────────────

@st.cache_data(show_spinner=False)
def build_comparison_data(
    ibge_ref: str,
    ibge_cand: str,
    dec_ini: int,
    dec_fim: int,
    k: float,
    dec_ini_cand: int,
) -> dict:
    """
    Prepara os dados brutos para o gráfico de comparação de assinaturas
    climáticas entre referência e candidato.

    Retorna dict com arrays numpy prontos para plotagem — sem objetos
    Plotly (permite @st.cache_data via pickle).

    Chave de cache: (ibge_ref, ibge_cand, dec_ini, dec_fim, k, dec_ini_cand).
    """
    # Normalise to plain Python str so @st.cache_data hashes consistently
    ibge_ref  = str(ibge_ref)
    ibge_cand = str(ibge_cand)

    df_means = load_means()
    df_stds  = load_stds()

    period_idx = dec_period_indices(dec_ini, dec_fim)
    P = len(period_idx)

    ref_means_row  = df_means[df_means["codigo_ibge"] == ibge_ref].iloc[0]
    ref_stds_row   = df_stds[df_stds["codigo_ibge"] == ibge_ref].iloc[0]
    cand_means_row = df_means[df_means["codigo_ibge"] == ibge_cand].iloc[0]

    ruler = build_ruler(ref_means_row, ref_stds_row, period_idx, k)

    # Valores do candidato nos decêndios da sua janela (posição j → decêndio absoluto)
    cand_vals = np.zeros((P, 4), dtype=np.float64)
    for j in range(P):
        cand_dec = (dec_ini_cand - 1 + j) % 36 + 1  # 1-indexed
        for v, var in enumerate(VARS):
            raw = cand_means_row.get(f"{var}_D{cand_dec}", np.nan)
            cand_vals[j, v] = float(raw) if pd.notna(raw) else 0.0

    # Within: candidato dentro da faixa da referência?
    within = (cand_vals >= ruler["lower"]) & (cand_vals <= ruler["upper"])  # (P, 4)

    # Rótulos de data para os decêndios de cada série (usados nos eixos X)
    ref_date_labels  = [DEC_LABEL[period_idx[j] + 1] for j in range(P)]
    cand_date_labels = [DEC_LABEL[(dec_ini_cand - 1 + j) % 36 + 1] for j in range(P)]

    return {
        "P":               P,
        "ref_means":       ruler["means"],   # (P, 4)
        "ref_lower":       ruler["lower"],   # (P, 4)
        "ref_upper":       ruler["upper"],   # (P, 4)
        "cand_vals":       cand_vals,        # (P, 4)
        "within":          within,           # (P, 4) bool
        "ref_date_labels": ref_date_labels,  # list[str] comprimento P
        "cand_date_labels": cand_date_labels,
    }
