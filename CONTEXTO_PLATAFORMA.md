# Contexto da Plataforma Agro Inteligente

Cole este arquivo no início de qualquer nova conversa sobre este projeto.
Ele descreve o que foi construído, como funciona internamente e como estender.

---

## 1. Visão Geral

App Streamlit **multipage** de zoneamento agroclimático para a Cooperativa Agrária (Projeto Integrador — Big Data).  
Repositório GitHub dedicado: `plataforma-agro-inteligente` (separado do `zoneamento-cevada` antigo).

**Objetivo:** para cada município brasileiro, identificar quais dos 36 decêndios do ano são aptos para o plantio de cevada (e, futuramente, outras culturas), considerando requisitos climáticos de cada estádio fenológico.

---

## 2. Estrutura de Arquivos

```
plataforma-agro-inteligente/          ← raiz do repo GitHub
├── app.py                            ← Página inicial (home)
├── requirements.txt                  ← inclui plotly e requests
├── .streamlit/config.toml            ← Tema visual verde-campo
├── data/
│   ├── Base_Clima_media_geral.parquet      ← 4.6 MB, wide-format, 5573 mun × 151 col
│   ├── Base_Producao_Compacta.parquet      ← ~5 MB, produção real por mun × cultura × ano
│   ├── Base_Resiliencia_PreComp.parquet    ← ~2 MB, probabilidades pré-computadas por mun × evento × fase
│   └── Base_Clima_Compacta.parquet         ← ~33 MB, baixado do GitHub Release v1.0-data na 1ª execução
├── pages/
│   ├── 1_🌾_Aptidao_Cevada.py       ← Simulação fenológica (Dias + GDD)
│   ├── 2_🌍_Gemeos_Climaticos.py    ← Análise de gêmeos climáticos
│   └── 3_🌍_Resiliencia_ENSO.py     ← Análise de Resiliência ENSO (4 níveis)
└── utils/
    ├── __init__.py
    ├── data_loader.py                ← Carregamento + 3 funções para módulo ENSO
    ├── simulation.py                 ← Motor matemático (Dias + GDD)
    ├── design.py                     ← CSS global, hero_banner(), badge()
    ├── twin_engine.py                ← Motor de gêmeos climáticos
    └── resiliencia_enso.py           ← Motor ENSO (4 níveis, puramente descritivo)
```

**Arquivos de pré-processamento** (ficam em `NOVO APP/`):
- `gerar_base_preprocessada.py` — base wide para zoneamento (4.6 MB)
- `gerar_bases_resiliencia.py` — gera as 3 bases do módulo Resiliência ENSO

---

## 3. Dados

### 3.1 Parquet bruto (128 MB — nunca vai ao GitHub)
Localização local: `NOVO APP/DADOS_Clima_alt_solos_nino/DADOS_Clima_alt_solos_nino.parquet`  
Formato: **long-format**, uma linha por `(município × ano × decêndio)`.

| Coluna | Descrição |
|--------|-----------|
| `codigo_ibge` | Código IBGE do município |
| `nome`, `estado` | Nome e UF |
| `ano` | 2000–2025 (2026 parcial) |
| `decendio` | 1–36 |
| `prec_media` | Precipitação acumulada no decêndio (mm) — total ~10 dias |
| `tmax_media` | Temperatura máxima média dos pixels do município |
| `tmed_media` | Temperatura média |
| `tmin_media` | Temperatura mínima média |
| `altitude_media` | Altitude média dos pixels (m) |
| `solo_1_ordem` | Solo dominante (classificação EMBRAPA, 15 categorias) |
| `enso_fenomeno` | La Niña / El Niño / Neutro |
| `enso_indice` | Índice ENSO numérico |

### 3.2 Base precomputada (4.6 MB — está no repo)
Formato: **wide-format**, uma linha por município.

Colunas: `codigo_ibge, nome, estado, altitude_media, solo_1_ordem, Prec_D1…D36, Tmax_D1…D36, Tmed_D1…D36, Tmin_D1…D36, lat, lon`

- `Prec_D{i}` = média histórica da precipitação acumulada do decêndio i (mm por decêndio)
- `Tmax_D{i}` = média histórica da temperatura máxima no decêndio i (°C)
- `Tmed_D{i}` = média histórica da temperatura média no decêndio i (°C)
- `Tmin_D{i}` = média histórica da temperatura mínima no decêndio i (°C)

**Modo de agregação atual:** Média Geral 2010–2025.

### 3.3 Coordenadas
`municipios_coords.parquet` (raiz do `Projeto_Ceveda_Agraria`) — 5573 linhas: `CD_MUN, lat, lon`.  
Já está embutido na base precomputada (colunas `lat`, `lon`).

---

## 4. Estrutura dos Decêndios

```python
DECENDIO_DAYS = [10,10,11, 10,10,8, 10,10,11, 10,10,10, 10,10,11, 10,10,10,
                 10,10,11, 10,10,11, 10,10,10, 10,10,11, 10,10,10, 10,10,11]
# soma = 365 dias (ano não-bissexto)
# D1 = 01-10 Jan … D36 = 21-31 Dez
```

`CUMUL[i]` = primeiro dia (0-indexed) do decêndio i.  
`DAY_TO_DEC[d]` = decêndio (0-indexed) ao qual o dia d pertence.

---

## 5. Modos de Agregação Temporal

Selecionável na sidebar da página de simulação. Registrado em `utils/data_loader.py`:

```python
AGG_MODES: dict[str, str] = {
    "media_geral": "Média Geral (2010–2025)",
    # Adicionar novos modos aqui
}
```

Para **adicionar um novo modo**:
1. Registrar a chave e rótulo em `AGG_MODES`.
2. Gerar `data/Base_Clima_{chave}.parquet` rodando `gerar_base_preprocessada.py` com os parâmetros desejados (intervalo de anos, filtro ENSO, etc.).
3. Commitar o novo parquet (se < 50 MB) ou hospedar externamente.

---

## 6. Motor de Simulação

### 6.1 Estádios Fenológicos (cevada)
```
0  Germinação e Emergência
1  Perfilhamento
2  Alongamento
3  Emborrachamento
4  Espigamento e Floração
5  Enchimento de Grãos e Maturação
6  Colheita
```

### 6.2 Modo Dias (run_zoneamento_days)

**Entrada por estádio:** `dur` (dias, obrigatório) + checkboxes opcionais para Prec, Tmed, Tmax, Tmin com limites Mín/Máx.

**Matemática por fase (para cada decêndio de plantio D_start):**

```
prec_w[dec] = dias_da_fase_no_dec / DECENDIO_DAYS[dec]
→ prec_fase = prec_mat @ prec_w   (precipitação acumulada proporcional)

tmed_w[dec] = dias_da_fase_no_dec / dur_fase
→ tmed_fase = tmed_mat @ tmed_w   (temperatura média ponderada)

tmin_fase = min(tmin_mat[:, decêndios_tocados])   (pior caso)
tmax_fase = max(tmax_mat[:, decêndios_tocados])   (pior caso)
```

**Resultado:** para cada decêndio de plantio (D1..D36), cada município passa ou falha. Salva os que passam em todos os estádios.

### 6.3 Modo Grau-Dia/GDD (run_zoneamento_gdd)

**Parâmetros globais:** `Tbase` (°C) — temperatura abaixo da qual não há desenvolvimento.  
**Entrada por estádio:** `gdd_threshold` (GD acumulados para completar o estádio) + mesmos checkboxes de Prec/Tmed/Tmax/Tmin.

**Matemática:**

```
GD_diário = max(0, (Tmax_dec + Tmin_dec) / 2 - Tbase)
# Cada dia dentro de um decêndio tem o mesmo GD (constante no decêndio)

gd_per_dec[N, 36] = max(0, (tmax_mat + tmin_mat) / 2 - Tbase)

# Array circular de 730 dias para suportar ciclos que cruzam virada de ano
gd_ext[N, 730], prec_ext[N, 730], tmed_ext[N, 730], tmin_ext[N, 730], tmax_ext[N, 730]
gd_cumsum = cumsum(gd_ext, axis=1)
```

**Detecção do fim de cada estádio (vetorizada):**
```python
# Para cada estádio s com threshold T_s:
target[N] = gdd_acumulado_até_aqui + T_s
exceeded[N, ext_len] = (gdd_rel >= target[:,None]) & (local_days >= stage_starts[:,None])
end_day[N] = argmax(exceeded, axis=1)
```

**Cálculo de clima na fase (GDD mode):**
```
# Precipitação: cumsum com indexação avançada
phase_prec[i] = prec_cumsum[i, end_day] - prec_cumsum[i, start_day-1]

# Temperatura média: idem com tmed_cumsum
phase_tmed[i] = (tmed_cumsum[i, end] - tmed_cumsum[i, start-1]) / dur[i]

# Tmin / Tmax: slab technique (vetorizado sobre municípios feasible)
d_off_mat[Nf, L] = d_starts_f[:,None] + arange(L)[None,:]
abs_idx = clip(day_off + d_off_mat, 0, 729)
slab = tmin_ext[f_idx[:,None], abs_idx]
slab = where(valid_mask, slab, inf)
phase_tmin[f_idx] = slab.min(axis=1)
```

### 6.4 Resultado por município

```python
{
    "Codigo_IBGE", "Municipio", "UF", "Altitude_m", "Solo_Dominante",
    "Decendios_Aptos",      # "D12, D13, D14"
    "Janelas_Plantio",      # "11-20 Jun (Colheita: ~Nov) | 21-30 Jun ..."
    "Num_Decendios_Aptos",  # int
    "Fatores_Limitantes",   # resumo agrupado das falhas por motivo
    "lat", "lon"
}
```

Salvo em `resultado_zoneamento_temp.parquet` + `st.session_state["result_df"]`.

---

## 7. Filtros Guilhotina (sidebar)

- **Altitude (m):** range slider sobre `altitude_media`
- **Solo Dominante:** multiselect sobre `solo_1_ordem` (15 categorias EMBRAPA)
- Ambos reduzem o DataFrame antes de qualquer cálculo

---

## 8. Arquitetura de Dois Botões

```
Botão 1: "Processar Zoneamento"
  → run_zoneamento_days() ou run_zoneamento_gdd()
  → salva resultado_zoneamento_temp.parquet
  → st.session_state["result_df"] = df_result

Botão 2: "Gerar Mapa e Tabela"
  → lê result_df (session_state ou parquet)
  → Folium map (verde ≥3 janelas, laranja 1-2)
  → st.dataframe com filtros UF e mínimo de janelas
  → download CSV
  → distribuição por estado
```

---

## 9. Design System (utils/design.py)

Função obrigatória no início de cada página: `inject_css()`

```python
from utils.design import inject_css, hero_banner, badge
inject_css()
hero_banner(title="...", subtitle="...", icon="🌾")
```

**Paleta:**
- Verde escuro `#1b4332` — cabeçalhos
- Verde médio `#2d6a4f` — primary / botões
- Verde fundo `#d8f3dc` — hover
- Dourado `#c9963a` — download button
- Fundo quente `#f9f7f2`

**Fontes:** Lora (títulos, serif) + DM Sans (corpo, sans-serif) via Google Fonts.

**Tema Streamlit** (`.streamlit/config.toml`):
```toml
primaryColor = "#2d6a4f"
backgroundColor = "#f9f7f2"
secondaryBackgroundColor = "#edf2ee"
textColor = "#1b2d1e"
```

---

## 10. Como Adicionar Novos Módulos (páginas)

1. Criar `pages/2_🌱_NomeModulo.py`
2. Chamar `inject_css()` e `hero_banner()` no topo
3. Registrar em `app.py` no card de módulos disponíveis

---

## 11. Como Adicionar Novos Modos de Simulação

Os modos atuais são **Dias** e **GDD**. Para adicionar um novo:

1. Criar função `run_zoneamento_novomode(df_filtered, phases, ...)` em `utils/simulation.py`
   - Deve retornar o mesmo schema do `_build_result()`
2. Na página `1_🌾_Aptidao_Cevada.py`, adicionar a opção no `st.sidebar.radio("Modo de simulação", ...)`
3. No bloco do botão 1, despachar para a nova função

**Invariantes que todo modo deve respeitar:**
- Iterar sobre os 36 decêndios de plantio (D1..D36)
- Para cada município que passa, salvar em `apt_dec_raw[i]`
- Para cada município que falha, salvar `(dec_label, motivo)` em `all_failures[i]`
- Chamar `_build_result()` ao final

---

## 12. Módulos Implementados e Próximas Implementações

### Módulos implementados
- [x] **Aptidão da Cevada** — simulação fenológica (Dias + GDD), mapa interativo
- [x] **Gêmeos Climáticos** — similaridade climática entre municípios (euclidiana Z-score)
- [x] **Resiliência ENSO** — 4 níveis: probabilidades condicionais, CDF empírica, análogos históricos, validação produtiva real

### Módulo Resiliência ENSO — arquitetura

**Bases de dados:**
- `Base_Clima_Compacta.parquet` (~33 MB) — hospedada no GitHub Release `v1.0-data`, baixada na 1ª execução
- `Base_Producao_Compacta.parquet` (~5 MB) — no repo; produção IBGE/PAM 1987–2024
- `Base_Resiliencia_PreComp.parquet` (~2 MB) — no repo; probabilidades pré-computadas

**Motor (`utils/resiliencia_enso.py`):**
- `filtrar_validos()` — mantém apenas `flag_cobertura == 'OK'`
- `probabilidades_por_enso()` — Nível 1, IC bootstrap (2000 reamostras)
- `cdf_empirica()` — Nível 2, CDF empírica por fase ENSO
- `motor_analogos()` — Nível 3, distância euclidiana Z-score
- `rendimento_por_enso()` — Nível 4, rendimento real × fase ENSO
- `projecao_rendimento_analogos()` — Nível 4, rendimento real nos anos análogos

**Constantes visuais:** `CORES_ENSO = {"El Niño": "#d1495b", "La Niña": "#2e86ab", "Neutro": "#8d99ae", "TODOS": "#2d6a4f"}`

**Filosofia:** tudo descritivo/empírico — sem modelagem fisiológica, evapotranspiração ou balanço hídrico.

### Modos de agregação temporal a implementar
- [ ] Filtro por intervalo de anos customizável
- [ ] Filtro por fenômeno ENSO (La Niña / El Niño / Neutro)
- [ ] Percentil histórico (ex: pior 20% dos anos)

### Módulos de análise futuros
- [ ] Expansão e Yield Gap (MapBiomas)

---

## 13. Comandos Úteis

```bash
# Rodar localmente
streamlit run app.py

# Regenerar base precomputada (rodar no Projeto_Ceveda_Agraria/)
python gerar_base_preprocessada.py

# Push ao GitHub após alterações
git add -A && git commit -m "feat: ..." && git push origin main
```

**Streamlit Cloud:**
- Repo: `plataforma-agro-inteligente`
- Branch: `main`
- Main file: `app.py`
