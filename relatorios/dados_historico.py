"""
Série histórica 2022-2025 dos indicadores do 11º GB.

Na produção, os valores vêm do relatório anual oficial, slide por slide. NESTA
CÓPIA PÚBLICA os números são fictícios (mesma ordem de grandeza), só para os
geradores rodarem. Cada KPI tem uma chave estável usada pelo gerador visual.

Para acrescentar 2026: preenche via dados_atuais() ou passa direto pro gerador.
"""

# Anos históricos (fixo — o relatório anual registra 2022-2025)
ANOS_HIST = [2022, 2023, 2024, 2025]

# ================================================================
# HISTÓRICO (fictício nesta cópia; em produção, extraído do relatório anual)
# Formato: {chave: {ano: valor, ...}}
# Todos os %s são armazenados como fração (0.84 = 84%)
# ================================================================
HISTORICO = {
    # --- B/1 — Pessoal ---
    "absenteismo_lts_pct":       {2022: 0.0268, 2023: 0.0209, 2024: 0.0265, 2025: 0.0103},
    "efetivo_operacional_pct":   {2022: 0.8142, 2023: 0.7490, 2024: 0.6184, 2025: 0.8437},

    # --- B/3 — Territorial & Operacional ---
    "cobertura_territorial_pct": {2022: 0.3685, 2023: 0.4897, 2024: 0.3995, 2025: 0.4063},
    "especializacao_pct":        {2022: 0.0818, 2023: 0.0928, 2024: 0.0521, 2025: 0.0831},
    "atendimento_20min_pct":     {2022: 0.3993, 2023: 0.4795, 2024: 0.4028, 2025: 0.3652},
    "fatais_incendio":           {2022: 5,      2023: 4,      2024: 5,      2025: 7},
    "fatais_transito":           {2022: 53,     2023: 55,     2024: 57,     2025: 71},

    # --- B/5 — Reconhecimento & Educação ---
    "elogios_por_bombeiro":      {2022: 0.57,   2023: 1.62,   2024: 1.35,   2025: 1.9163},
    "lmp_outorgadas":            {2022: 82,     2023: 63,     2024: 57,     2025: 114},
    "turmas_bombeiro_escola":    {2022: 381,    2023: 944,    2024: 1135,   2025: 1897},

    # --- UGE ---
    "uge_processos":             {2022: 37,     2023: 18,     2024: 20,     2025: 29},
    "uge_valor_custeio":         {2022: 813722.46, 2023: 645303.84, 2024: 492947.83, 2025: 220470.97},
    "uge_valor_investimento":    {2022: 146134.36, 2023: 401470.82, 2024: 1406584.80, 2025: 2555354.90},

    # --- PJMD ---
    "reclamacoes_denuncias":     {2022: 6,      2023: 10,      2024: 9,     2025: 6},
    "pms_punidos_pd":            {2022: 14,     2023: 31,     2024: 29,     2025: 15},
    "acidentes_folga_bombeiro":  {2022: 6,      2023: 4,      2024: 6,      2025: 3},
    "acidentes_viatura_vitima":  {2022: 0,      2023: 0,      2024: 0,      2025: 0},

    # --- MOTOMEC ---
    "idade_media_veicular":      {2022: 11.24,  2023: 10.41,  2024: 11.86,   2025: 12.98},
    "viaturas_baixadas_pct":     {2022: 0.1877, 2023: 0.3060, 2024: 0.2386, 2025: 0.3228},

    # --- SAT ---
    "dias_analise":              {2022: 2,      2023: 3,      2024: 2,      2025: 2},
    "dias_vistoria":             {2022: 10,     2023: 12,     2024: 8,     2025: 5},
    "dias_analise_fat":          {2022: 3,      2023: 2,      2024: 1,      2025: 2},
    "fiscalizacoes":             {2022: 760,    2023: 825,    2024: 834,    2025: 889},
}


# ================================================================
# CATÁLOGO — metadados usados pelo gerador
# ================================================================
CATALOGO = {
    "absenteismo_lts_pct":       {"titulo": "Taxa de absenteísmo (LTS)", "fmt": "pct",   "secao": "B/1", "menor_melhor": True},
    "efetivo_operacional_pct":   {"titulo": "Efetivo empregado na atividade operacional", "fmt": "pct", "secao": "B/1", "menor_melhor": False},
    "cobertura_territorial_pct": {"titulo": "Ocupação da Unidade na área territorial",   "fmt": "pct", "secao": "B/3", "menor_melhor": False},
    "especializacao_pct":        {"titulo": "Especialização de Bombeiros",               "fmt": "pct", "secao": "B/3", "menor_melhor": False},
    "atendimento_20min_pct":     {"titulo": "Atendimento de incêndio em até 20 min",     "fmt": "pct", "secao": "B/3", "menor_melhor": False},
    "fatais_incendio":           {"titulo": "Vítimas fatais em incêndio",                "fmt": "int", "secao": "B/3", "menor_melhor": True},
    "fatais_transito":           {"titulo": "Vítimas fatais em acidente de trânsito",    "fmt": "int", "secao": "B/3", "menor_melhor": True},
    "elogios_por_bombeiro":      {"titulo": "Elogios por bombeiro",                       "fmt": "dec", "secao": "B/5", "menor_melhor": False},
    "lmp_outorgadas":            {"titulo": "Láureas de Mérito Pessoal (LMP)",           "fmt": "int", "secao": "B/5", "menor_melhor": False},
    "turmas_bombeiro_escola":    {"titulo": "Bombeiro na Escola — alunos formados",      "fmt": "int", "secao": "B/5", "menor_melhor": False},
    "uge_processos":             {"titulo": "UGE — quantidade de processos",             "fmt": "int", "secao": "UGE", "menor_melhor": False},
    "uge_valor_custeio":         {"titulo": "UGE — recursos de custeio (R$)",            "fmt": "brl", "secao": "UGE", "menor_melhor": False},
    "uge_valor_investimento":    {"titulo": "UGE — recursos de investimento (R$)",       "fmt": "brl", "secao": "UGE", "menor_melhor": False},
    "reclamacoes_denuncias":     {"titulo": "Reclamações e denúncias recebidas",         "fmt": "int", "secao": "PJMD", "menor_melhor": True},
    "pms_punidos_pd":            {"titulo": "PMs punidos por Procedimento Disciplinar",  "fmt": "int", "secao": "PJMD", "menor_melhor": True},
    "acidentes_folga_bombeiro":  {"titulo": "Acidentes de trânsito com bombeiros na folga", "fmt": "int", "secao": "PJMD", "menor_melhor": True},
    "acidentes_viatura_vitima":  {"titulo": "Acidentes com viatura e vítima bombeiro",   "fmt": "int", "secao": "PJMD", "menor_melhor": True},
    "idade_media_veicular":      {"titulo": "Idade média veicular (anos)",               "fmt": "dec", "secao": "MOTOMEC", "menor_melhor": True},
    "viaturas_baixadas_pct":     {"titulo": "Taxa de viaturas baixadas",                 "fmt": "pct", "secao": "MOTOMEC", "menor_melhor": True},
    "dias_analise":              {"titulo": "SAT — dias para análise",                   "fmt": "int", "secao": "SAT", "menor_melhor": True},
    "dias_vistoria":             {"titulo": "SAT — dias para vistoria",                  "fmt": "int", "secao": "SAT", "menor_melhor": True},
    "dias_analise_fat":          {"titulo": "SAT — dias para análise de FAT",            "fmt": "int", "secao": "SAT", "menor_melhor": True},
    "fiscalizacoes":             {"titulo": "SAT — fiscalizações realizadas",            "fmt": "int", "secao": "SAT", "menor_melhor": False},
}


def serie_completa(chave, valor_novo, ano_novo):
    """Retorna dict {ano: valor} incluindo o histórico + o ano novo."""
    s = dict(HISTORICO.get(chave, {}))
    if valor_novo is not None:
        s[ano_novo] = valor_novo
    return s


def valores_por_secao(secao):
    """Lista de chaves de KPI daquela seção."""
    return [k for k, meta in CATALOGO.items() if meta["secao"] == secao]


if __name__ == "__main__":
    print(f"{len(HISTORICO)} KPIs históricos carregados.")
    for chave, meta in CATALOGO.items():
        anos = HISTORICO.get(chave, {})
        print(f"  [{meta['secao']}] {chave:32s} → {anos}")
