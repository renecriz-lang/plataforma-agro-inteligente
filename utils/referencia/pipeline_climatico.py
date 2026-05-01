"""
Pipeline Climático Probabilístico — 3 camadas:
  Nivel 1: Probabilidades condicionais (ENSO × evento) com IC bootstrap
  Nivel 2: CDF empírica condicional
  Nivel 3: Motor de análogos históricos

Filosofia: tudo é descritivo/empírico sobre a história real.
Não há modelagem fisiológica. Cada resposta vem com tamanho de amostra
e intervalo de confiança para que o usuário saiba o quanto confiar.
"""

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# 1. Limpeza e preparação
# ---------------------------------------------------------------------------

def normalizar_enso_intensidade(s: pd.Series) -> pd.Series:
    """Resolve inconsistências de gênero: 'Fraco'->'Fraca', 'Moderado'->'Moderada'."""
    mapa = {
        'Fraco': 'Fraca',
        'Moderado': 'Moderada',
        # Forte e Muito Forte já são consistentes
    }
    s = s.astype('object').replace(mapa)
    # Reconverte para category com ordem natural
    ordem = ['Neutro', 'Fraca', 'Moderada', 'Forte', 'Muito Forte']
    return pd.Categorical(s, categories=ordem, ordered=True)


def carregar_dataset(caminho: str, codigo_ibge: str | None = None) -> pd.DataFrame:
    """Carrega o parquet e aplica limpezas. Se codigo_ibge for fornecido,
    filtra apenas aquele município (muito mais rápido)."""
    df = pd.read_parquet(caminho)
    if codigo_ibge is not None:
        df = df[df['codigo_ibge'] == codigo_ibge].copy()
    df['enso_intensidade'] = normalizar_enso_intensidade(df['enso_intensidade'])
    return df


def filtrar_validos(df: pd.DataFrame) -> pd.DataFrame:
    """Mantém só linhas com cobertura OK (para análises probabilísticas)."""
    return df[df['flag_cobertura'] == 'OK'].copy()


# ---------------------------------------------------------------------------
# 2. Definição de eventos críticos
# ---------------------------------------------------------------------------
# Cada evento é uma função que recebe um DataFrame de UM ano-município
# e retorna True/False. O agrupamento por ano é feito antes.

def evento_janeiro_seco(df_ano: pd.DataFrame, lim_mm: float = 150.0) -> bool:
    """Janeiro seco: chuva acumulada nos decêndios 1-3 (janeiro inteiro)
    abaixo de `lim_mm`. Para Santa Maria do Oeste/PR, 150 mm é ~percentil 10
    da história — define o 'pior 1 em cada 10 anos'."""
    jan = df_ano[df_ano['decendio'].between(1, 3)]
    if len(jan) < 3:
        return np.nan
    return jan['prec_media'].sum() < lim_mm


def evento_frio_intenso_outono(df_ano: pd.DataFrame, lim_c: float = 8.0) -> bool:
    """Frio intenso outonal: tmin_min ≤ lim_c em qualquer decêndio entre
    13 e 18 (mai-jun). Aviso: tmin_min é média decendial, não Tmin absoluta;
    8°C aqui ≈ ondas de frio/geada possíveis na semana correspondente."""
    win = df_ano[df_ano['decendio'].between(13, 18)]
    if len(win) < 6:
        return np.nan
    return (win['tmin_min'] <= lim_c).any()


def evento_excesso_chuva_plantio(df_ano: pd.DataFrame, lim_mm: float = 100.0) -> bool:
    """Excesso na janela de plantio: algum decêndio de outubro (28-30)
    com chuva ≥ lim_mm — risco de inviabilidade de plantio."""
    win = df_ano[df_ano['decendio'].between(28, 30)]
    if len(win) < 3:
        return np.nan
    return (win['prec_media'] >= lim_mm).any()


def evento_calor_janeiro(df_ano: pd.DataFrame, lim_c: float = 30.5) -> bool:
    """Calor em janeiro: tmax_media > lim_c em algum decêndio 1-3
    (~percentil 75 da história, situação claramente acima do normal)."""
    jan = df_ano[df_ano['decendio'].between(1, 3)]
    if len(jan) < 3:
        return np.nan
    return (jan['tmax_media'] > lim_c).any()


EVENTOS_PADRAO = {
    'Janeiro seco (chuva total < 150 mm)':                    evento_janeiro_seco,
    'Frio intenso no outono (Tmin ≤ 8°C, mai-jun)':           evento_frio_intenso_outono,
    'Excesso de chuva no plantio (≥100 mm/decêndio em out)':  evento_excesso_chuva_plantio,
    'Calor em janeiro (Tmax > 30,5°C)':                       evento_calor_janeiro,
}


# ---------------------------------------------------------------------------
# 3. NÍVEL 1 — Probabilidades condicionais com bootstrap
# ---------------------------------------------------------------------------

def _bootstrap_ic(amostra: np.ndarray, n_boot: int = 2000,
                  alpha: float = 0.05, seed: int = 42) -> tuple[float, float]:
    """IC percentil para a média (proporção, no caso de bool)."""
    if len(amostra) == 0:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    boot = rng.choice(amostra, size=(n_boot, len(amostra)), replace=True).mean(axis=1)
    lo, hi = np.quantile(boot, [alpha/2, 1 - alpha/2])
    return float(lo), float(hi)


def probabilidades_por_enso(df_mun: pd.DataFrame,
                            eventos: dict | None = None,
                            n_boot: int = 2000) -> pd.DataFrame:
    """Para cada evento e cada fase ENSO, calcula:
       - probabilidade empírica
       - tamanho da amostra (anos)
       - IC 95% por bootstrap
    """
    if eventos is None:
        eventos = EVENTOS_PADRAO

    df = filtrar_validos(df_mun)
    # Para cada ano, qual foi a fase ENSO predominante?
    fase_por_ano = (df.groupby('ano')['enso_fenomeno']
                      .agg(lambda x: x.mode().iloc[0] if len(x) > 0 else np.nan))

    linhas = []
    for nome_ev, fn in eventos.items():
        # Avalia o evento ano a ano
        ocorrencias = df.groupby('ano').apply(fn, include_groups=False)
        ocorrencias = ocorrencias.dropna().astype(bool)
        # Junta com a fase ENSO
        tab = pd.DataFrame({'ocorreu': ocorrencias, 'fase': fase_por_ano})
        tab = tab.dropna()

        for fase in ['El Niño', 'La Niña', 'Neutro', 'TODOS']:
            if fase == 'TODOS':
                sub = tab['ocorreu'].values
            else:
                sub = tab.loc[tab['fase'] == fase, 'ocorreu'].values
            if len(sub) == 0:
                continue
            p = float(np.mean(sub))
            lo, hi = _bootstrap_ic(sub.astype(float), n_boot=n_boot)
            linhas.append({
                'evento': nome_ev,
                'fase_enso': fase,
                'n_anos': int(len(sub)),
                'n_ocorrencias': int(np.sum(sub)),
                'probabilidade': p,
                'ic95_inf': lo,
                'ic95_sup': hi,
            })
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------
# 4. NÍVEL 2 — CDF empírica condicional
# ---------------------------------------------------------------------------

def cdf_empirica(df_mun: pd.DataFrame, variavel: str, decendios: list[int],
                 condicionar_por: str = 'enso_fenomeno') -> pd.DataFrame:
    """Para uma janela de decêndios, calcula a CDF empírica da variável
    (somando se for chuva, mediando se for temperatura) por categoria de
    `condicionar_por`. Retorna DataFrame longo: {categoria, valor, prob_acumulada}."""

    df = filtrar_validos(df_mun)
    win = df[df['decendio'].isin(decendios)]

    # Agregação por ano: chuva soma, temperatura média
    if 'prec' in variavel:
        ag = win.groupby(['ano', condicionar_por], observed=True)[variavel].sum()
    else:
        ag = win.groupby(['ano', condicionar_por], observed=True)[variavel].mean()
    ag = ag.reset_index()

    out = []
    for cat, sub in ag.groupby(condicionar_por, observed=True):
        valores = np.sort(sub[variavel].dropna().values)
        if len(valores) == 0:
            continue
        prob = np.arange(1, len(valores) + 1) / len(valores)
        out.append(pd.DataFrame({
            'categoria': cat, 'valor': valores, 'prob_acumulada': prob
        }))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


# ---------------------------------------------------------------------------
# 5. NÍVEL 3 — Motor de análogos históricos
# ---------------------------------------------------------------------------

def construir_assinatura(df_mun: pd.DataFrame, ano: int,
                         decendios: list[int]) -> np.ndarray | None:
    """Vetor de assinatura climática de um ano até a data atual:
       [prec_dec1, ..., prec_decN, tmax_dec1, ..., tmin_decN, indice_enso]
       Normaliza dimensões depois.
    """
    sub = df_mun[(df_mun['ano'] == ano) &
                 (df_mun['decendio'].isin(decendios)) &
                 (df_mun['flag_cobertura'] == 'OK')]
    sub = sub.sort_values('decendio')
    if len(sub) < len(decendios):
        return None
    vec = np.concatenate([
        sub['prec_media'].values,
        sub['tmax_media'].values,
        sub['tmin_media'].values,
        [sub['enso_indice'].mean()],
    ])
    if np.any(np.isnan(vec)):
        return None
    return vec


def motor_analogos(df_mun: pd.DataFrame, ano_alvo: int,
                   decendios_observados: list[int],
                   k: int = 5) -> pd.DataFrame:
    """Para o `ano_alvo`, encontra os `k` anos históricos com trajetória
    climática mais semelhante na janela `decendios_observados`.
    Distância: euclidiana sobre vetores Z-score-normalizados (cada dimensão
    é padronizada usando a média/dp histórica para garantir que prec não
    domine só por ter magnitude maior)."""

    anos_disp = sorted(df_mun['ano'].unique())
    anos_disp = [a for a in anos_disp if a != ano_alvo]

    # Constrói matriz de assinaturas
    assinaturas = {}
    alvo = construir_assinatura(df_mun, ano_alvo, decendios_observados)
    if alvo is None:
        raise ValueError(f"Ano alvo {ano_alvo} não tem dados completos para {decendios_observados}")
    assinaturas[ano_alvo] = alvo
    for a in anos_disp:
        v = construir_assinatura(df_mun, a, decendios_observados)
        if v is not None:
            assinaturas[a] = v

    M = np.vstack([assinaturas[a] for a in assinaturas])
    # Z-score por coluna (dimensão)
    mu = M.mean(axis=0)
    sd = M.std(axis=0)
    sd[sd == 0] = 1.0
    Mn = (M - mu) / sd

    idx_alvo = list(assinaturas.keys()).index(ano_alvo)
    dist = np.linalg.norm(Mn - Mn[idx_alvo], axis=1)
    anos = list(assinaturas.keys())

    res = pd.DataFrame({'ano': anos, 'distancia': dist})
    res = res[res['ano'] != ano_alvo].sort_values('distancia').head(k)
    # Anexa o fenômeno ENSO predominante daquele ano
    fase = (df_mun.groupby('ano')['enso_fenomeno']
                  .agg(lambda x: x.mode().iloc[0] if len(x) > 0 else 'NA'))
    res['fase_enso'] = res['ano'].map(fase).astype(str)
    return res.reset_index(drop=True)


def projecao_dos_analogos(df_mun: pd.DataFrame, anos_analogos: list[int],
                          decendios_futuros: list[int]) -> pd.DataFrame:
    """Para cada decêndio futuro, retorna estatísticas (mediana, p10, p90)
    da prec, tmax e tmin observadas naqueles anos análogos."""
    df = filtrar_validos(df_mun)
    sub = df[(df['ano'].isin(anos_analogos)) &
             (df['decendio'].isin(decendios_futuros))]
    out = (sub.groupby('decendio')
              .agg(prec_p10=('prec_media', lambda x: x.quantile(0.1)),
                   prec_p50=('prec_media', 'median'),
                   prec_p90=('prec_media', lambda x: x.quantile(0.9)),
                   tmax_p50=('tmax_media', 'median'),
                   tmin_p10=('tmin_media', lambda x: x.quantile(0.1)),
                   tmin_p50=('tmin_media', 'median'))
              .reset_index())
    return out
