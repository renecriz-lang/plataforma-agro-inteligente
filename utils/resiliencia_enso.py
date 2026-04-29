"""
Motor de análise de Resiliência ENSO.

4 camadas:
  Nível 1 — Probabilidades condicionais (eventos × fase ENSO) com IC bootstrap
  Nível 2 — CDF empírica condicional por fase ENSO
  Nível 3 — Motor de análogos históricos (distância euclidiana Z-score)
  Nível 4 — Cruzamento com produtividade real (dados_consolidados)

Princípio: tudo descritivo/empírico. Sem modelagem fisiológica.
Cada resposta vem com n (tamanho da amostra) e IC 95% por bootstrap.
"""

import numpy as np
import pandas as pd

# ============================================================
# 0. Definição dos eventos críticos (parametrizável pela UI)
# ============================================================

EVENTOS_PADRAO: dict[str, dict] = {
    "janeiro_seco": {
        "rotulo": "Janeiro seco",
        "descricao": "Chuva acumulada em janeiro abaixo do limite",
        "unidade": "mm",
        "limite_default": 150.0,
        "janela_decendios": [1, 2, 3],
        "tipo": "soma_abaixo",
        "variavel": "prec_media",
        "percentil_ref": "~p10 histórico",
    },
    "frio_outono": {
        "rotulo": "Frio intenso no outono",
        "descricao": "Tmin média abaixo do limite em mai-jun",
        "unidade": "°C",
        "limite_default": 8.0,
        "janela_decendios": list(range(13, 19)),
        "tipo": "minimo_abaixo",
        "variavel": "tmin_media",
        "percentil_ref": "~p25 histórico",
    },
    "excesso_plantio_primavera": {
        "rotulo": "Excesso de chuva no plantio (out)",
        "descricao": "Algum decêndio de outubro com chuva acima do limite",
        "unidade": "mm",
        "limite_default": 100.0,
        "janela_decendios": [28, 29, 30],
        "tipo": "maximo_acima",
        "variavel": "prec_media",
        "percentil_ref": "~p70 histórico",
    },
    "calor_janeiro": {
        "rotulo": "Calor em janeiro",
        "descricao": "Tmax média acima do limite em algum decêndio de jan",
        "unidade": "°C",
        "limite_default": 30.5,
        "janela_decendios": [1, 2, 3],
        "tipo": "maximo_acima",
        "variavel": "tmax_media",
        "percentil_ref": "~p75 histórico",
    },
}

# Paleta de cores ENSO (consistente em toda a plataforma)
CORES_ENSO: dict[str, str] = {
    "El Niño": "#d1495b",
    "La Niña": "#2e86ab",
    "Neutro":  "#8d99ae",
    "TODOS":   "#2d6a4f",
}

FASES_ENSO = ["El Niño", "La Niña", "Neutro", "TODOS"]


# ============================================================
# 1. Helpers de filtragem e limpeza
# ============================================================

def filtrar_validos(df: pd.DataFrame) -> pd.DataFrame:
    """Mantém apenas linhas com flag_cobertura == 'OK'."""
    return df[df["flag_cobertura"] == "OK"].copy()


def fase_predominante_por_ano(df_mun: pd.DataFrame) -> pd.Series:
    """Retorna a fase ENSO predominante (moda) para cada ano."""
    return (
        df_mun.groupby("ano", observed=True)["enso_fenomeno"]
        .agg(lambda x: x.mode().iloc[0] if len(x) > 0 else np.nan)
    )


# ============================================================
# 2. Bootstrap
# ============================================================

def bootstrap_ic(amostra: np.ndarray, n_boot: int = 2000,
                 alpha: float = 0.05, seed: int = 42) -> tuple[float, float]:
    """IC percentil para a média via bootstrap."""
    if len(amostra) == 0:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    boot = rng.choice(amostra, size=(n_boot, len(amostra)), replace=True).mean(axis=1)
    lo, hi = np.quantile(boot, [alpha / 2, 1 - alpha / 2])
    return float(lo), float(hi)


# ============================================================
# 3. Avaliação de eventos individuais
# ============================================================

def avaliar_evento(df_ano: pd.DataFrame, ev_config: dict) -> float:
    """Avalia se UM ano-município satisfez o evento.
    Retorna 1.0 (ocorreu), 0.0 (não ocorreu) ou np.nan (dados insuficientes).
    Aceita override do limite via ev_config['limite'] (key opcional).
    """
    win = df_ano[df_ano["decendio"].isin(ev_config["janela_decendios"])]
    n_esperado = len(ev_config["janela_decendios"])
    if len(win) < n_esperado:
        return np.nan
    serie = win[ev_config["variavel"]]
    if serie.isna().any():
        return np.nan

    lim = ev_config.get("limite", ev_config["limite_default"])
    tp  = ev_config["tipo"]
    if tp == "soma_abaixo":
        return float(float(serie.sum()) < lim)
    if tp == "minimo_abaixo":
        return float(float(serie.min()) <= lim)
    if tp == "maximo_acima":
        return float(float(serie.max()) > lim)
    raise ValueError(f"Tipo desconhecido: {tp}")


# ============================================================
# 4. Nível 1 — Probabilidades condicionais
# ============================================================

def probabilidades_por_enso(df_mun: pd.DataFrame,
                             eventos: dict | None = None,
                             n_boot: int = 2000) -> pd.DataFrame:
    """Para cada evento e cada fase ENSO, calcula:
      probabilidade empírica | n_anos | IC 95% bootstrap.

    df_mun deve conter flag_cobertura para ser filtrado internamente.
    eventos: dict de dicts no formato EVENTOS_PADRAO (com chave 'limite' opcional).
    """
    if eventos is None:
        eventos = EVENTOS_PADRAO

    df = filtrar_validos(df_mun)
    if len(df) == 0:
        return pd.DataFrame()

    fase_ano = fase_predominante_por_ano(df)

    linhas = []
    for ev_key, ev_cfg in eventos.items():
        ocorrencias = (
            df.groupby("ano", observed=True)
            .apply(avaliar_evento, ev_cfg, include_groups=False)
        )
        ocorrencias = ocorrencias.dropna()
        tab = pd.DataFrame({"ocorreu": ocorrencias, "fase": fase_ano})
        tab = tab.dropna()

        for fase in FASES_ENSO:
            sub = tab["ocorreu"].values if fase == "TODOS" else \
                  tab.loc[tab["fase"] == fase, "ocorreu"].values
            if len(sub) == 0:
                continue
            p = float(np.mean(sub))
            lo, hi = bootstrap_ic(sub.astype(float), n_boot=n_boot)
            linhas.append({
                "evento_key":    ev_key,
                "evento_rotulo": ev_cfg["rotulo"],
                "fase_enso":     fase,
                "n_anos":        int(len(sub)),
                "n_ocorrencias": int(np.sum(sub)),
                "probabilidade": p,
                "ic95_inf":      lo,
                "ic95_sup":      hi,
            })
    return pd.DataFrame(linhas)


# ============================================================
# 5. Nível 2 — CDF empírica condicional
# ============================================================

def cdf_empirica(df_mun: pd.DataFrame, variavel: str,
                 decendios: list[int],
                 condicionar_por: str = "enso_fenomeno") -> pd.DataFrame:
    """CDF empírica da variável na janela de decêndios, por fase ENSO.

    Chuva → soma por ano; temperatura → média por ano.
    Retorna DataFrame longo: categoria | valor | prob_acumulada | n.
    """
    df = filtrar_validos(df_mun)
    win = df[df["decendio"].isin(decendios)]
    if len(win) == 0:
        return pd.DataFrame()

    if "prec" in variavel:
        ag = win.groupby(["ano", condicionar_por], observed=True)[variavel].sum()
    else:
        ag = win.groupby(["ano", condicionar_por], observed=True)[variavel].mean()
    ag = ag.reset_index()

    out = []
    for cat, sub in ag.groupby(condicionar_por, observed=True):
        valores = np.sort(sub[variavel].dropna().values)
        if len(valores) == 0:
            continue
        prob = np.arange(1, len(valores) + 1) / len(valores)
        out.append(pd.DataFrame({
            "categoria": str(cat),
            "valor": valores,
            "prob_acumulada": prob,
            "n": len(valores),
        }))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


# ============================================================
# 6. Nível 3 — Motor de análogos
# ============================================================

def construir_assinatura(df_mun: pd.DataFrame, ano: int,
                          decendios: list[int]) -> np.ndarray | None:
    """Vetor de assinatura climática para um ano na janela de decêndios.
    [prec_D1..prec_Dn, tmax_D1..tmax_Dn, tmin_D1..tmin_Dn, enso_indice_medio]
    Normalização Z-score é feita posteriormente em motor_analogos().
    """
    sub = df_mun[
        (df_mun["ano"] == ano) &
        (df_mun["decendio"].isin(decendios)) &
        (df_mun["flag_cobertura"] == "OK")
    ].sort_values("decendio")

    if len(sub) < len(decendios):
        return None

    vec_parts = [
        sub["prec_media"].values,
        sub["tmax_media"].values,
        sub["tmin_media"].values,
    ]
    if "enso_indice" in sub.columns:
        vec_parts.append([float(sub["enso_indice"].mean())])

    vec = np.concatenate([v.astype(float) for v in vec_parts])
    return None if np.any(np.isnan(vec)) else vec


def motor_analogos(df_mun: pd.DataFrame, ano_alvo: int,
                   decendios_observados: list[int],
                   k: int = 5) -> pd.DataFrame:
    """Encontra os k anos históricos com trajetória climática mais semelhante
    ao ano_alvo na janela de decendios_observados.

    Distância: euclidiana sobre vetores Z-score-normalizados por dimensão.
    Retorna DataFrame: posicao | ano | distancia | fase_enso.
    """
    anos_disp = [a for a in sorted(df_mun["ano"].unique()) if a != ano_alvo]

    assinaturas: dict[int, np.ndarray] = {}
    alvo_sig = construir_assinatura(df_mun, ano_alvo, decendios_observados)
    if alvo_sig is None:
        return pd.DataFrame(columns=["posicao", "ano", "distancia", "fase_enso"])
    assinaturas[ano_alvo] = alvo_sig

    for a in anos_disp:
        v = construir_assinatura(df_mun, a, decendios_observados)
        if v is not None:
            assinaturas[a] = v

    if len(assinaturas) < 2:
        return pd.DataFrame(columns=["posicao", "ano", "distancia", "fase_enso"])

    anos_ord = list(assinaturas.keys())
    M = np.vstack([assinaturas[a] for a in anos_ord])
    mu = M.mean(axis=0)
    sd = M.std(axis=0)
    sd[sd == 0] = 1.0
    Mn = (M - mu) / sd

    idx_alvo = anos_ord.index(ano_alvo)
    dist = np.linalg.norm(Mn - Mn[idx_alvo], axis=1)

    res = pd.DataFrame({"ano": anos_ord, "distancia": dist})
    res = res[res["ano"] != ano_alvo].sort_values("distancia").head(k).reset_index(drop=True)
    res["posicao"] = res.index + 1

    fase = fase_predominante_por_ano(df_mun)
    res["fase_enso"] = res["ano"].map(fase).astype(str).replace("nan", "—")
    return res[["posicao", "ano", "distancia", "fase_enso"]]


def projecao_dos_analogos(df_mun: pd.DataFrame, anos_analogos: list[int],
                           decendios_futuros: list[int]) -> pd.DataFrame:
    """Estatísticas (p10, mediana, p90) dos análogos para decêndios futuros.
    Retorna DataFrame: decendio | prec_p10 | prec_p50 | prec_p90 | tmax_p50 | tmin_p10 | tmin_p50.
    """
    df = filtrar_validos(df_mun)
    sub = df[(df["ano"].isin(anos_analogos)) & (df["decendio"].isin(decendios_futuros))]
    if len(sub) == 0:
        return pd.DataFrame()
    return (
        sub.groupby("decendio", observed=True)
        .agg(
            prec_p10=("prec_media", lambda x: x.quantile(0.1)),
            prec_p50=("prec_media", "median"),
            prec_p90=("prec_media", lambda x: x.quantile(0.9)),
            tmax_p50=("tmax_media", "median"),
            tmin_p10=("tmin_media", lambda x: x.quantile(0.1)),
            tmin_p50=("tmin_media", "median"),
        )
        .reset_index()
    )


def historico_climatologico(df_mun: pd.DataFrame,
                             decendios: list[int]) -> pd.DataFrame:
    """Faixa histórica geral (p10, mediana, p90) para os decêndios dados."""
    df = filtrar_validos(df_mun)
    sub = df[df["decendio"].isin(decendios)]
    if len(sub) == 0:
        return pd.DataFrame()
    return (
        sub.groupby("decendio", observed=True)
        .agg(
            prec_p10=("prec_media", lambda x: x.quantile(0.1)),
            prec_p50=("prec_media", "median"),
            prec_p90=("prec_media", lambda x: x.quantile(0.9)),
            tmax_p50=("tmax_media", "median"),
            tmin_p50=("tmin_media", "median"),
        )
        .reset_index()
    )


# ============================================================
# 7. Nível 4 — Validação produtiva (NOVO)
# ============================================================

def rendimento_por_enso(df_prod_mun: pd.DataFrame,
                         df_clima_mun: pd.DataFrame,
                         cultura: str) -> pd.DataFrame:
    """Agrupa o rendimento histórico da cultura por fase ENSO predominante.

    Lógica:
      1. Fase ENSO predominante por ano (moda dos decêndios com flag OK)
      2. Inner join com produção por ano
      3. Estatísticas: n | média | mediana | p10 | p90 | IC 95% bootstrap

    Retorna DataFrame com: fase_enso | n_anos | rend_medio | rend_mediano |
                            rend_p10 | rend_p90 | ic95_inf_media | ic95_sup_media.
    """
    sub = df_prod_mun[df_prod_mun["cultura"] == cultura].copy()
    if len(sub) == 0:
        return pd.DataFrame()

    df_clima_ok = filtrar_validos(df_clima_mun)
    fase_ano = fase_predominante_por_ano(df_clima_ok)

    sub = sub.merge(
        fase_ano.rename("fase_enso"),
        left_on="ano", right_index=True, how="inner"
    )
    sub = sub.dropna(subset=["rendimento_kg_ha", "fase_enso"])

    linhas = []
    for fase in FASES_ENSO:
        valores = (
            sub["rendimento_kg_ha"].values if fase == "TODOS" else
            sub.loc[sub["fase_enso"] == fase, "rendimento_kg_ha"].values
        )
        if len(valores) == 0:
            continue
        lo, hi = bootstrap_ic(valores.astype(float))
        linhas.append({
            "fase_enso":      fase,
            "n_anos":         int(len(valores)),
            "rend_medio":     float(np.mean(valores)),
            "rend_mediano":   float(np.median(valores)),
            "rend_p10":       float(np.quantile(valores, 0.1)),
            "rend_p90":       float(np.quantile(valores, 0.9)),
            "ic95_inf_media": lo,
            "ic95_sup_media": hi,
        })
    return pd.DataFrame(linhas)


def projecao_rendimento_analogos(df_prod_mun: pd.DataFrame,
                                  df_clima_mun: pd.DataFrame,
                                  anos_analogos: list[int],
                                  cultura: str) -> dict:
    """Estatísticas do rendimento da cultura nos anos análogos.

    Retorna dict com: rend_medio_analogos, rend_mediano_analogos,
    rend_min, rend_max, rend_medio_historico, delta_pct,
    n_analogos_com_dados, detalhe_por_ano (lista de dicts).
    """
    sub_base = df_prod_mun[df_prod_mun["cultura"] == cultura]
    if len(sub_base) == 0:
        return {}

    sub_ana = sub_base[sub_base["ano"].isin(anos_analogos)].copy()

    # Adiciona a fase ENSO de cada ano análogo
    df_clima_ok = filtrar_validos(df_clima_mun)
    fase_ano = fase_predominante_por_ano(df_clima_ok)
    sub_ana = sub_ana.copy()
    sub_ana["fase_enso"] = sub_ana["ano"].map(fase_ano).astype(str).replace("nan", "—")

    if len(sub_ana) == 0:
        return {
            "cultura": cultura,
            "n_analogos_com_dados": 0,
            "aviso": f"Sem dados de {cultura} para os anos análogos no histórico.",
        }

    return {
        "cultura": cultura,
        "n_analogos_com_dados":  int(len(sub_ana)),
        "rend_medio_analogos":   float(sub_ana["rendimento_kg_ha"].mean()),
        "rend_mediano_analogos": float(sub_ana["rendimento_kg_ha"].median()),
        "rend_min_analogos":     float(sub_ana["rendimento_kg_ha"].min()),
        "rend_max_analogos":     float(sub_ana["rendimento_kg_ha"].max()),
        "rend_medio_historico":  float(sub_base["rendimento_kg_ha"].mean()),
        "rend_mediano_historico":float(sub_base["rendimento_kg_ha"].median()),
        "delta_pct": (
            float(sub_ana["rendimento_kg_ha"].mean() /
                  sub_base["rendimento_kg_ha"].mean()) - 1
        ) * 100,
        "detalhe_por_ano": (
            sub_ana[["ano", "rendimento_kg_ha", "area_plantada_ha",
                      "producao_ton", "fase_enso"]]
            .sort_values("ano")
            .to_dict("records")
        ),
    }
