"""Persistência de configurações personalizadas de culturas.

Cada config é um JSON em data/configs_culturas/<slug>.json.

Nota: em Streamlit Cloud o filesystem é volátil — reseta a cada novo deploy.
Para uso em produção recomenda-se baixar o JSON e versionar manualmente.
Para uso local a persistência funciona normalmente.
"""

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

DIR_CONFIGS = Path("data/configs_culturas")
DIR_CONFIGS.mkdir(parents=True, exist_ok=True)


def _slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "config"


def listar_configs() -> list[dict]:
    """Retorna lista de {slug, nome, modificado_em} para o seletor da UI."""
    out: list[dict] = []
    for arq in sorted(DIR_CONFIGS.glob("*.json")):
        try:
            with open(arq, encoding="utf-8") as f:
                data = json.load(f)
            out.append({
                "slug": arq.stem,
                "nome": data.get("nome", arq.stem),
                "modificado_em": datetime.fromtimestamp(arq.stat().st_mtime)
                                         .strftime("%d/%m/%Y %H:%M"),
            })
        except Exception:
            continue
    return out


def salvar_config(config: dict) -> Path:
    """Salva config como JSON. Exige ao menos 'nome' e 'fases'.
    Adiciona 'versao_schema' e 'salvo_em'."""
    slug = _slugify(config["nome"])
    arq = DIR_CONFIGS / f"{slug}.json"
    payload = {
        **config,
        "versao_schema": 1,
        "salvo_em": datetime.now().isoformat(timespec="seconds"),
    }
    with open(arq, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return arq


def carregar_config(slug: str) -> dict:
    arq = DIR_CONFIGS / f"{slug}.json"
    if not arq.exists():
        raise FileNotFoundError(f"Config '{slug}' não existe em {DIR_CONFIGS}")
    with open(arq, encoding="utf-8") as f:
        return json.load(f)


def remover_config(slug: str) -> bool:
    arq = DIR_CONFIGS / f"{slug}.json"
    if arq.exists():
        arq.unlink()
        return True
    return False
