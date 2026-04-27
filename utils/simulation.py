"""
simulation.py — motor de zoneamento agroclimático da cevada.

Dois modos de simulação:
  • Dias  : duração fixa de cada estádio fenológico
  • GDD   : acumulação de grau-dias para cada estádio
"""

from __future__ import annotations
from collections import defaultdict
import numpy as np
import pandas as pd
import streamlit as st

# ── Estrutura dos Decêndios (ano não-bissexto = 365 dias) ──────────────────
DECENDIO_DAYS = [
    10, 10, 11,  # Jan D1–D3
    10, 10,  8,  # Fev D4–D6
    10, 10, 11,  # Mar D7–D9
    10, 10, 10,  # Abr D10–D12
    10, 10, 11,  # Mai D13–D15
    10, 10, 10,  # Jun D16–D18
    10, 10, 11,  # Jul D19–D21
    10, 10, 11,  # Ago D22–D24
    10, 10, 10,  # Set D25–D27
    10, 10, 11,  # Out D28–D30
    10, 10, 10,  # Nov D31–D33
    10, 10, 11,  # Dez D34–D36
]
assert sum(DECENDIO_DAYS) == 365

CUMUL = np.zeros(37, dtype=int)
for _i, _d in enumerate(DECENDIO_DAYS):
    CUMUL[_i + 1] = CUMUL[_i] + _d

DAY_TO_DEC = np.empty(365, dtype=int)
for _pos in range(365):
    for _di in range(36):
        if CUMUL[_di] <= _pos < CUMUL[_di + 1]:
            DAY_TO_DEC[_pos] = _di
            break

# DAY_TO_DEC estendido para 730 dias (ano circular × 2)
DAY_TO_DEC_EXT = np.tile(DAY_TO_DEC, 2)

MONTHS_PT    = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
                "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
DAYS_PER_MO  = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

DEC_LABEL: dict[int, str] = {}
for _m in range(12):
    _mn, _md, _b = MONTHS_PT[_m], DAYS_PER_MO[_m], _m * 3
    DEC_LABEL[_b + 1] = f"01-10 {_mn}"
    DEC_LABEL[_b + 2] = f"11-20 {_mn}"
    DEC_LABEL[_b + 3] = f"21-{_md:02d} {_mn}"

ESTAGIOS = [
    "Germinação e Emergência",
    "Perfilhamento",
    "Alongamento",
    "Emborrachamento",
    "Espigamento e Floração",
    "Enchimento de Grãos e Maturação",
    "Colheita",
]
STAGE_ICONS = ["🌱", "🌿", "📏", "🌾", "🌸", "🌰", "🚜"]


# ── Helpers de calendário ──────────────────────────────────────────────────

def _harvest_month(start_dec_1: int, cycle_days: int) -> str:
    annual_pos = (CUMUL[start_dec_1 - 1] + cycle_days - 1) % 365
    return DEC_LABEL[int(DAY_TO_DEC[annual_pos]) + 1].split()[-1]


def build_janelas_str(apt_decs: list[int], cycle_days: int | None,
                      gdd_mode: bool = False) -> str:
    parts = []
    for d in apt_decs:
        label = DEC_LABEL[d]
        if gdd_mode or cycle_days is None:
            parts.append(label)
        else:
            parts.append(f"{label} (Colheita: ~{_harvest_month(d, cycle_days)})")
    return " | ".join(parts)


def build_limitantes_str(failures: list[tuple]) -> str:
    if not failures:
        return ""
    reason_to_decs: dict[str, list[str]] = defaultdict(list)
    for dec_label, reason in failures:
        reason_to_decs[reason].append(dec_label)
    sorted_r = sorted(reason_to_decs.items(), key=lambda x: -len(x[1]))[:3]
    parts = []
    for reason, decs in sorted_r:
        decs_str = (
            ", ".join(decs) if len(decs) <= 4
            else f"{decs[0]}-{decs[-1]} ({len(decs)} dec.)"
        )
        parts.append(f"{decs_str}: {reason}")
    return " | ".join(parts)


# ── Pesos para modo Dias ───────────────────────────────────────────────────

def _phase_weights(start_dec_0: int, day_start: int, day_end: int) -> dict:
    """Pesos vetorizados para precipitação e temperatura média numa fase (modo Dias)."""
    phase_dur = day_end - day_start + 1
    dec_day_count = np.zeros(36, dtype=int)
    for sim_day in range(day_start, day_end + 1):
        annual_pos = (CUMUL[start_dec_0] + sim_day - 1) % 365
        dec_day_count[DAY_TO_DEC[annual_pos]] += 1
    touched = np.where(dec_day_count > 0)[0]
    prec_w = np.zeros(36)
    tmed_w = np.zeros(36)
    for di in touched:
        prec_w[di] = dec_day_count[di] / DECENDIO_DAYS[di]
        tmed_w[di] = dec_day_count[di] / phase_dur
    return {"prec_w": prec_w, "tmed_w": tmed_w, "t_idx": touched.tolist()}


def _check_phase(N, apt, first_failure, ph, s_idx,
                 phase_prec, phase_tmed, phase_tmin, phase_tmax):
    """Aplica filtros climáticos de uma fase e retorna máscara atualizada."""
    var_results: dict[str, tuple] = {}
    if ph["prec_en"]:
        cond = (phase_prec >= ph["prec_min"]) & (phase_prec <= ph["prec_max"])
        var_results["Prec. Acum."] = (phase_prec, cond, ph["prec_min"], ph["prec_max"], "mm")
    if ph["tmed_en"]:
        cond = (phase_tmed >= ph["tmed_min"]) & (phase_tmed <= ph["tmed_max"])
        var_results["Tmed"] = (phase_tmed, cond, ph["tmed_min"], ph["tmed_max"], "°C")
    if ph["tmin_en"] and phase_tmin is not None:
        cond = (phase_tmin >= ph["tmin_min"]) & (phase_tmin <= ph["tmin_max"])
        var_results["Tmin"] = (phase_tmin, cond, ph["tmin_min"], ph["tmin_max"], "°C")
    if ph["tmax_en"] and phase_tmax is not None:
        cond = (phase_tmax >= ph["tmax_min"]) & (phase_tmax <= ph["tmax_max"])
        var_results["Tmax"] = (phase_tmax, cond, ph["tmax_min"], ph["tmax_max"], "°C")

    phase_pass = np.ones(N, dtype=bool)
    for _, (_, cond, _, _, _) in var_results.items():
        phase_pass &= cond

    new_fail = apt & ~phase_pass
    for idx in np.where(new_fail)[0]:
        if not first_failure[idx]:
            parts = []
            for var, (vals, cond_a, vmin, vmax, unit) in var_results.items():
                if not cond_a[idx]:
                    v = float(vals[idx])
                    direction = (f"{v:.1f}{unit} < {vmin:.1f}{unit}" if v < vmin
                                 else f"{v:.1f}{unit} > {vmax:.1f}{unit}")
                    parts.append(f"{var}: {direction}")
            stage_name = ESTAGIOS[s_idx]
            first_failure[idx] = (
                f"{stage_name} ({'; '.join(parts)})" if parts else stage_name
            )
    return apt & phase_pass


# ── MODO DIAS ──────────────────────────────────────────────────────────────

def run_zoneamento_days(df_filtered: pd.DataFrame, phases: list[dict],
                        cycle_total_days: int) -> pd.DataFrame:
    """Varredura D1–D36 por município — modo duração em dias."""
    N = len(df_filtered)
    if N == 0:
        return pd.DataFrame()

    prec_mat = df_filtered[[f"Prec_D{i}" for i in range(1, 37)]].values.astype(float)
    tmed_mat = df_filtered[[f"Tmed_D{i}" for i in range(1, 37)]].values.astype(float)
    tmax_mat = df_filtered[[f"Tmax_D{i}" for i in range(1, 37)]].values.astype(float)
    tmin_mat = df_filtered[[f"Tmin_D{i}" for i in range(1, 37)]].values.astype(float)

    phase_ranges: list[tuple[int, int]] = []
    cursor = 1
    for ph in phases:
        phase_ranges.append((cursor, cursor + ph["dur"] - 1))
        cursor += ph["dur"]

    apt_dec_raw:  list[list[int]]   = [[] for _ in range(N)]
    all_failures: list[list[tuple]] = [[] for _ in range(N)]
    progress = st.progress(0, text="Iniciando…")

    for s0 in range(36):
        progress.progress((s0 + 1) / 36,
                          text=f"Varrendo decêndio D{s0 + 1} / 36…")
        weights = [_phase_weights(s0, ds, de) for ds, de in phase_ranges]

        apt          = np.ones(N, dtype=bool)
        first_failure = np.full(N, "", dtype=object)

        for s_idx, ph in enumerate(phases):
            if not apt.any():
                break
            w = weights[s_idx]

            phase_prec = prec_mat @ w["prec_w"]
            phase_tmed = tmed_mat @ w["tmed_w"]
            phase_tmin = tmin_mat[:, w["t_idx"]].min(axis=1) if w["t_idx"] else None
            phase_tmax = tmax_mat[:, w["t_idx"]].max(axis=1) if w["t_idx"] else None

            apt = _check_phase(N, apt, first_failure, ph, s_idx,
                               phase_prec, phase_tmed, phase_tmin, phase_tmax)

        dec_lbl = f"D{s0 + 1}"
        for idx in range(N):
            if apt[idx]:
                apt_dec_raw[idx].append(s0 + 1)
            else:
                motivo = first_failure[idx] or "Critérios climáticos não atendidos"
                all_failures[idx].append((dec_lbl, motivo))

    progress.empty()
    return _build_result(df_filtered, apt_dec_raw, all_failures,
                         cycle_total_days, gdd_mode=False)


# ── MODO GDD ───────────────────────────────────────────────────────────────

def run_zoneamento_gdd(df_filtered: pd.DataFrame, phases: list[dict],
                       tbase: float) -> pd.DataFrame:
    """Varredura D1–D36 por município — modo grau-dia acumulado."""
    N = len(df_filtered)
    if N == 0:
        return pd.DataFrame()

    prec_mat = df_filtered[[f"Prec_D{i}" for i in range(1, 37)]].values.astype(float)
    tmax_mat = df_filtered[[f"Tmax_D{i}" for i in range(1, 37)]].values.astype(float)
    tmed_mat = df_filtered[[f"Tmed_D{i}" for i in range(1, 37)]].values.astype(float)
    tmin_mat = df_filtered[[f"Tmin_D{i}" for i in range(1, 37)]].values.astype(float)

    # GD diário por decêndio: max(0, (Tmax+Tmin)/2 - Tbase)   shape [N,36]
    gd_per_dec = np.maximum(0.0, (tmax_mat + tmin_mat) / 2.0 - tbase)

    # Arrays diários (365 dias): cada dia herda o valor do decêndio ao qual pertence
    gd_daily   = np.empty((N, 365))
    prec_daily = np.empty((N, 365))
    tmed_daily = np.empty((N, 365))
    tmin_daily = np.empty((N, 365))
    tmax_daily = np.empty((N, 365))

    for d in range(365):
        dec = int(DAY_TO_DEC[d])
        n   = DECENDIO_DAYS[dec]
        gd_daily[:, d]   = gd_per_dec[:, dec]
        prec_daily[:, d] = prec_mat[:, dec] / n   # precipitação diária média
        tmed_daily[:, d] = tmed_mat[:, dec]
        tmin_daily[:, d] = tmin_mat[:, dec]
        tmax_daily[:, d] = tmax_mat[:, dec]

    # Extensão circular 730 dias para suportar ciclos que cruzam virada de ano
    gd_ext   = np.concatenate([gd_daily,   gd_daily],   axis=1)  # [N,730]
    prec_ext = np.concatenate([prec_daily, prec_daily], axis=1)
    tmed_ext = np.concatenate([tmed_daily, tmed_daily], axis=1)
    tmin_ext = np.concatenate([tmin_daily, tmin_daily], axis=1)
    tmax_ext = np.concatenate([tmax_daily, tmax_daily], axis=1)

    # Cumsums para precipitação e temperatura média
    gd_cumsum   = np.cumsum(gd_ext,   axis=1)  # [N,730]
    prec_cumsum = np.cumsum(prec_ext, axis=1)
    tmed_cumsum = np.cumsum(tmed_ext, axis=1)

    MAX_EXT = 730
    days_idx = np.arange(MAX_EXT)  # usado em masks

    apt_dec_raw:  list[list[int]]   = [[] for _ in range(N)]
    all_failures: list[list[tuple]] = [[] for _ in range(N)]
    progress = st.progress(0, text="Iniciando (GDD)…")

    for s0 in range(36):
        progress.progress((s0 + 1) / 36,
                          text=f"Varrendo decêndio D{s0 + 1} / 36 (GDD)…")

        day_off = int(CUMUL[s0])       # início desta simulação no array circular
        limit   = min(MAX_EXT, day_off + 365)  # não simular mais de 1 ano

        # GDD relativo ao início da simulação
        base_gdd  = gd_cumsum[:, day_off - 1]  if day_off > 0 else np.zeros(N)
        base_prec = prec_cumsum[:, day_off - 1] if day_off > 0 else np.zeros(N)
        base_tmed = tmed_cumsum[:, day_off - 1] if day_off > 0 else np.zeros(N)

        # fatia [N, limit-day_off] — índices absolutos no ext array: day_off .. limit-1
        ext_len = limit - day_off
        gdd_rel  = gd_cumsum[:,   day_off:limit] - base_gdd[:,  None]   # [N, ext_len]
        prec_rel = prec_cumsum[:, day_off:limit] - base_prec[:, None]
        tmed_rel = tmed_cumsum[:, day_off:limit] - base_tmed[:, None]

        local_days = np.arange(ext_len)  # 0..ext_len-1 (relativo ao início)

        # Estado da simulação
        stage_starts = np.zeros(N, dtype=int)   # dia rel onde esta fase começa
        gdd_at_stage_start = np.zeros(N)        # GDD acum. no início desta fase
        feasible     = np.ones(N, dtype=bool)
        first_failure = np.full(N, "", dtype=object)

        all_s_starts: list[np.ndarray] = []
        all_s_ends:   list[np.ndarray] = []

        # ── 1ª passagem: determinar janelas de dias por estádio ────────────
        for s_idx, ph in enumerate(phases):
            threshold = ph["gdd_threshold"]
            target    = gdd_at_stage_start + threshold  # [N]

            # Primeiro dia >= stage_starts onde gdd_rel >= target
            valid   = (local_days[None, :] >= stage_starts[:, None])     # [N, ext_len]
            exceeded = (gdd_rel >= target[:, None]) & valid               # [N, ext_len]

            has_exc  = exceeded.any(axis=1)                               # [N]
            end_days = np.where(has_exc, np.argmax(exceeded, axis=1),
                                ext_len)                                   # [N]

            # Registra falha por GDD insuficiente
            new_fail_gdd = feasible & (~has_exc | (end_days >= ext_len))
            for idx in np.where(new_fail_gdd)[0]:
                if not first_failure[idx]:
                    first_failure[idx] = f"{ESTAGIOS[s_idx]} (GDD insuficiente)"
            feasible &= ~new_fail_gdd

            all_s_starts.append(stage_starts.copy())
            all_s_ends.append(end_days.copy())

            gdd_at_stage_start = gdd_rel[np.arange(N),
                                         np.minimum(end_days, ext_len - 1)]
            stage_starts = np.minimum(end_days + 1, ext_len - 1)

        # ── 2ª passagem: checar restrições climáticas por estádio ──────────
        for s_idx, ph in enumerate(phases):
            if not feasible.any():
                break

            d_starts = all_s_starts[s_idx]             # [N] dias rel
            d_ends   = all_s_ends[s_idx]               # [N] dias rel
            dur      = np.maximum(1, d_ends - d_starts + 1)  # [N]

            # Precipitação acumulada na fase
            ep = prec_rel[np.arange(N), np.minimum(d_ends,   ext_len - 1)]
            sp = np.where(d_starts > 0,
                          prec_rel[np.arange(N), np.minimum(d_starts - 1, ext_len - 1)],
                          0.0)
            phase_prec = ep - sp

            # Temperatura média na fase
            et = tmed_rel[np.arange(N), np.minimum(d_ends,   ext_len - 1)]
            st_ = np.where(d_starts > 0,
                           tmed_rel[np.arange(N), np.minimum(d_starts - 1, ext_len - 1)],
                           0.0)
            phase_tmed = (et - st_) / dur

            # Tmin / Tmax — slab vetorizado para municípios feasible
            phase_tmin = np.full(N, 0.0)
            phase_tmax = np.full(N, 0.0)
            f_idx = np.where(feasible)[0]

            if len(f_idx) > 0 and (ph["tmin_en"] or ph["tmax_en"]):
                ds_f = d_starts[f_idx]
                de_f = d_ends[f_idx]
                L    = int((de_f - ds_f + 1).max())

                d_off_mat  = ds_f[:, None] + np.arange(L)[None, :]  # [Nf, L]
                abs_idx    = np.clip(day_off + d_off_mat, 0, MAX_EXT - 1)  # [Nf, L]
                valid_mask = d_off_mat <= (de_f - ds_f)[:, None]

                if ph["tmin_en"]:
                    slab = tmin_ext[f_idx[:, None], abs_idx]
                    slab = np.where(valid_mask, slab,  np.inf)
                    phase_tmin[f_idx] = slab.min(axis=1)

                if ph["tmax_en"]:
                    slab = tmax_ext[f_idx[:, None], abs_idx]
                    slab = np.where(valid_mask, slab, -np.inf)
                    phase_tmax[f_idx] = slab.max(axis=1)

            feasible = _check_phase(N, feasible, first_failure, ph, s_idx,
                                    phase_prec, phase_tmed,
                                    phase_tmin if ph["tmin_en"] else None,
                                    phase_tmax if ph["tmax_en"] else None)

        dec_lbl = f"D{s0 + 1}"
        for idx in range(N):
            if feasible[idx]:
                apt_dec_raw[idx].append(s0 + 1)
            else:
                motivo = first_failure[idx] or "Critérios não atendidos"
                all_failures[idx].append((dec_lbl, motivo))

    progress.empty()
    return _build_result(df_filtered, apt_dec_raw, all_failures,
                         cycle_total_days=None, gdd_mode=True)


# ── Monta DataFrame de resultados ──────────────────────────────────────────

def _build_result(df_filtered: pd.DataFrame,
                  apt_dec_raw:  list[list[int]],
                  all_failures: list[list[tuple]],
                  cycle_total_days: int | None,
                  gdd_mode: bool) -> pd.DataFrame:
    rows = []
    for i, row in enumerate(df_filtered.itertuples(index=False)):
        if not apt_dec_raw[i]:
            continue
        rows.append({
            "Codigo_IBGE":         row.codigo_ibge,
            "Municipio":           row.nome,
            "UF":                  row.estado,
            "Altitude_m":          round(float(row.altitude_media), 0)
                                   if pd.notna(row.altitude_media) else None,
            "Solo_Dominante":      str(row.solo_1_ordem)
                                   if str(row.solo_1_ordem) not in ("nan", "None", "")
                                   else "Não identificado",
            "Decendios_Aptos":     ", ".join(f"D{d}" for d in apt_dec_raw[i]),
            "Janelas_Plantio":     build_janelas_str(apt_dec_raw[i],
                                                     cycle_total_days, gdd_mode),
            "Num_Decendios_Aptos": len(apt_dec_raw[i]),
            "Fatores_Limitantes":  build_limitantes_str(all_failures[i]),
            "lat":                 float(row.lat) if pd.notna(row.lat) else None,
            "lon":                 float(row.lon) if pd.notna(row.lon) else None,
        })
    return pd.DataFrame(rows)
