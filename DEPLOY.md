# Deploy — Plataforma Agro Inteligente

## 1. Pré-requisitos

- GitHub Release `v1.0-data` criado com `Base_Clima_Compacta.parquet`
  anexado (33 MB). Sem este Release, os módulos Resiliência ENSO,
  Comparador de Cenários e Tendências Climáticas falham ao baixar a base
  climática.

## 2. Streamlit Community Cloud

1. Acesse https://share.streamlit.io/
2. Login com GitHub.
3. New app:
   - Repository: `renecriz-lang/plataforma-agro-inteligente`
   - Branch: `main`
   - Main file path: `app.py`
4. Deploy. Primeira execução: 3-5 min.

## 3. Comportamento esperado no primeiro acesso

- Páginas Aptidão Cevada e Aptidão Multicultura: carregam imediatamente
  (usam `Base_Clima_media_geral.parquet`, que já está no repo).
- Páginas Resiliência ENSO, Comparador, Tendências Climáticas, Gêmeos
  Climáticos: na primeira execução, mostram spinner "Baixando base
  climática histórica (33 MB)...". Demora ~30-60s; depois cacheia em
  memória via `@st.cache_resource`.

## 4. Limitações conhecidas no Streamlit Cloud

- O filesystem é volátil: configs personalizadas salvas em
  `data/configs_culturas/*.json` são perdidas em deploys novos. Para
  produção, exportar via botão "Exportar JSON" no módulo Multicultura.
- A base climática (33 MB) é re-baixada quando o servidor reinicia (após
  inatividade prolongada ou novo deploy).

## 5. Atualizando a base climática

Quando regenerar `Base_Clima_Compacta.parquet`:
1. Rodar `gerar_bases_resiliencia.py` no projeto bruto.
2. Criar novo Release no GitHub (ex.: `v1.1-data`) e anexar o parquet
   novo.
3. Atualizar `_URL_BASE_CLIMA_COMPACTA` em `utils/data_loader.py` apontando
   para a nova tag.
4. Commit + push em `main`. Streamlit Cloud redeploya automaticamente.

## 6. Variáveis de ambiente

Nenhuma necessária. Caso adicione integrações futuras (APIs, autenticação),
use **Secrets** no painel do Streamlit Cloud, nunca commite no
`.streamlit/secrets.toml`.
