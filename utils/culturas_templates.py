"""Templates de culturas. Cada template define apenas os NOMES dos estádios.
O usuário preenche durações e requisitos climáticos na aba 'Cultura ativa'."""

TEMPLATES: dict[str, dict] = {
    "cevada": {
        "nome": "Cevada (template oficial Cooperativa Agrária)",
        "descricao": "7 estádios conforme o programa de melhoramento da Cooperativa Agrária.",
        "fases": [
            ("Germinação e Emergência",         "vegetativo"),
            ("Perfilhamento",                   "vegetativo"),
            ("Alongamento",                     "vegetativo"),
            ("Emborrachamento",                 "reprodutivo"),
            ("Espigamento e Floração",          "reprodutivo"),
            ("Enchimento de Grãos e Maturação", "reprodutivo"),
            ("Colheita",                        "outro"),
        ],
    },
    "soja": {
        "nome": "Soja (Fehr-Caviness)",
        "descricao": "Estádios vegetativos VE→V3 e reprodutivos R1→R8.",
        "fases": [
            ("VE - Emergência",              "vegetativo"),
            ("VC - Cotilédones",             "vegetativo"),
            ("V1 - 1ª folha",               "vegetativo"),
            ("V2 - 2ª folha",               "vegetativo"),
            ("V3 - 3ª folha",               "vegetativo"),
            ("R1 - Início floração",         "reprodutivo"),
            ("R2 - Floração plena",          "reprodutivo"),
            ("R3 - Início vagem",            "reprodutivo"),
            ("R4 - Vagem completa",          "reprodutivo"),
            ("R5 - Início enchimento",       "reprodutivo"),
            ("R6 - Enchimento completo",     "reprodutivo"),
            ("R7 - Maturação fisiológica",   "reprodutivo"),
            ("R8 - Maturação plena",         "reprodutivo"),
        ],
    },
    "milho": {
        "nome": "Milho (Ritchie & Hanway)",
        "descricao": "Estádios vegetativos VE→VT e reprodutivos R1→R6.",
        "fases": [
            ("VE - Emergência",                "vegetativo"),
            ("V1 - 1 folha",                  "vegetativo"),
            ("V2 - 2 folhas",                 "vegetativo"),
            ("V3 - 3 folhas",                 "vegetativo"),
            ("Vn - n folhas",                 "vegetativo"),
            ("VT - Pendoamento",              "vegetativo"),
            ("R1 - Florescimento",            "reprodutivo"),
            ("R2 - Grão leitoso",             "reprodutivo"),
            ("R3 - Grão pastoso",             "reprodutivo"),
            ("R4 - Grão farináceo",           "reprodutivo"),
            ("R5 - Grão farináceo duro",      "reprodutivo"),
            ("R6 - Maturidade fisiológica",   "reprodutivo"),
        ],
    },
    "feijao": {
        "nome": "Feijão (Embrapa / CIAT)",
        "descricao": "Estádios V0→V4 e R5→R9 conforme escala Embrapa CIAT.",
        "fases": [
            ("V0 - Germinação",              "vegetativo"),
            ("V1 - Emergência",              "vegetativo"),
            ("V2 - Folhas primárias",        "vegetativo"),
            ("V3 - 1ª folha trifoliolada",  "vegetativo"),
            ("V4 - 3ª folha trifoliolada",  "vegetativo"),
            ("R5 - Pré-floração",            "reprodutivo"),
            ("R6 - Floração",                "reprodutivo"),
            ("R7 - Formação de vagens",      "reprodutivo"),
            ("R8 - Enchimento de vagens",    "reprodutivo"),
            ("R9 - Maturação",               "reprodutivo"),
        ],
    },
    "trigo": {
        "nome": "Trigo (escala Feekes adaptada)",
        "descricao": "10 estádios da escala Feekes adaptada para o Brasil.",
        "fases": [
            ("Plântula",                      "vegetativo"),
            ("Afilhamento",                   "vegetativo"),
            ("Alongamento",                   "vegetativo"),
            ("Emborrachamento",               "reprodutivo"),
            ("Espigamento",                   "reprodutivo"),
            ("Florescimento",                 "reprodutivo"),
            ("Grão estado leitoso",           "reprodutivo"),
            ("Grão estado massa",             "reprodutivo"),
            ("Grão maturação fisiológica",    "reprodutivo"),
            ("Grão maduro",                   "reprodutivo"),
        ],
    },
    "generico": {
        "nome": "Cultura genérica (você define)",
        "descricao": "Use quando sua cultura não tem template. Defina N estádios vegetativos e M reprodutivos.",
        "fases": [],  # gerada dinamicamente por construir_cultura_generica()
    },
}


def construir_cultura_generica(
    n_vegetativos: int,
    n_reprodutivos: int,
    inclui_colheita: bool = True,
) -> list[tuple[str, str]]:
    """Gera lista de fases (nome, grupo) para o template genérico."""
    fases: list[tuple[str, str]] = []
    for i in range(1, n_vegetativos + 1):
        fases.append((f"V{i} - Vegetativo {i}", "vegetativo"))
    for i in range(1, n_reprodutivos + 1):
        fases.append((f"R{i} - Reprodutivo {i}", "reprodutivo"))
    if inclui_colheita:
        fases.append(("Colheita", "outro"))
    return fases
