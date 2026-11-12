"""
Classificação do efetivo por lotação e atividade-fim — fonte única do painel
e da B.I.A.

/pessoal/operacional, /pessoal/realocacao e /consulta/efetivo repetiam, cada
um, o CASE por prefixo de cod_opm e a sua cópia do override da SAT. Quando a
SAT passou a incluir os NATs (11/09/2026), as três cópias teriam de mudar
juntas e em sincronia; aqui mudam de uma vez, e o card, o simulador e a
resposta do WhatsApp não têm como divergir.

Os fragmentos são SQL puro, sem alias de tabela e sem parâmetro: servem em
qualquer SELECT sobre b1.efetivo. As constantes são inteiros fixos no código,
então interpolá-las não abre brecha de injeção.

NÃO vale para as views b1.vw_efetivo_operacional e b1.vw_efetivo_disponivel,
que seguem só a regra do código terminado em zero e põem os NATs nos SGBs. A
vw_efetivo_operacional alimenta o PPQG (relatorios/dados.py), e mexer nela
mudaria o relatório sem ninguém pedir — ver commit a646545.
"""

EM_SAT   = 990119200
EM_COBOM = 990119131

# NUCL ATIV TEC dos SGBs. Compõem a SAT e só estão alocados nos SGBs pela
# localidade (confirmado com a seção de pessoal). O QPO da SAT em
# b1.qpo_funcoes — 13 Subten/Sgt e 6 Cb/Sd — só fecha somando a sede com
# esses núcleos, e os SGBs não têm vaga de NAT. O 990111900 estava vazio em
# 11/09; fica na lista para quem for lotado lá cair na SAT sem nova correção.
#
# O SEC SDM ATIV TEC (990119100, 1 militar) NÃO entra: está no ramo 9901191xx
# junto com B/1, B/3, B/4 e AG AREA, e o QPO prevê ali 1 Cap como Chefe da
# Seção Adm — o posto de quem está lá.
SAT_NATS = (990111900, 990112900, 990113900, 990114900)
SAT_CODS = (EM_SAT,) + SAT_NATS

_EH_SAT = f"cod_opm_atual IN ({', '.join(str(c) for c in SAT_CODS)})"

# A SAT é testada ANTES dos prefixos: 99011x900 começa como código de SGB e
# cairia no SGB, que é exatamente o erro que isto corrige.
SQL_PARTE = f"""
    CASE WHEN {_EH_SAT}                                           THEN 'SAT'
         WHEN cod_opm_atual = {EM_COBOM}                          THEN 'COBOM'
         WHEN left(cod_opm_atual::text, 6) IN ('990110','990119') THEN 'ADM'
         WHEN left(cod_opm_atual::text, 6) = '990111'             THEN '1°Sgb'
         WHEN left(cod_opm_atual::text, 6) = '990112'             THEN '2°Sgb'
         WHEN left(cod_opm_atual::text, 6) = '990113'             THEN '3°Sgb'
         WHEN left(cod_opm_atual::text, 6) = '990114'             THEN '4°Sgb'
         ELSE 'Outros' END
"""

PARTES_EM = ("SAT", "COBOM", "ADM")

# Atividade-fim. Regra geral: OPM cujo código não termina em zero. Todos os
# códigos da SAT terminam em zero, mas os Subten/Sgt dela fazem fiscalização e
# contam como operacionais (decisão do comando); Cb/Sd e oficiais da SAT
# são administrativos.
SQL_OPERACIONAL = f"""
    CASE WHEN {_EH_SAT} THEN (posto_grad ILIKE '%sgt%' OR posto_grad ILIKE '%sub%')
         ELSE cod_opm_atual::text NOT LIKE '%0' END
"""


# Vagas de atividade-fim no QPO (b1.qpo_funcoes) — a contraparte de
# SQL_OPERACIONAL, para o card de força operacional contar vaga e militar pelo
# mesmo critério. O QPO não tem coluna "operacional" nem código de OPM que ligue
# a vaga ao efetivo, então a regra lê a estrutura do próprio documento:
#   - SGB: só linhas com subseção, que são as estações e os Bombeiros
#     Comunitários. Comando, Adm e a sede do Pelotão (a linha do Pelotão sem
#     subseção) ficam fora — no efetivo, são os códigos terminados em zero.
#   - EM: o COBOM inteiro e os Subten/Sgt da SAT, os mesmos que SQL_OPERACIONAL
#     conta. O resto do EM não tem vaga operacional.
# Posição "a designar" não é vaga. As lotações saem com os mesmos rótulos de
# SQL_PARTE ('1°Sgb', 'SAT', 'COBOM', 'ADM'), para os dois lados cruzarem.
# Conferido em 11/09/2026: 130, 112, 132 e 87 nos SGBs, 13 na SAT e 30 no
# COBOM. Uma estação nova entra sozinha quando o QPO for reimportado com ela.
SQL_PARTE_QPO = """
    CASE WHEN lotacao <> 'EM'          THEN lotacao
         WHEN subsecao ILIKE '%COBOM%' THEN 'COBOM'
         WHEN secao ILIKE '%Ativ T%'   THEN 'SAT'
         ELSE 'ADM' END
"""

SQL_VAGA_OPERACIONAL = """
    NOT a_designar AND CASE
        WHEN lotacao <> 'EM'          THEN COALESCE(subsecao, '') <> ''
                                           AND secao NOT IN ('Comando', 'Adm')
        WHEN subsecao ILIKE '%COBOM%' THEN true
        WHEN secao ILIKE '%Ativ T%'   THEN posto_grad = 'Subten/Sgt'
        ELSE false END
"""


# Seção do ADMINISTRATIVO, nos dois lados (pedido do Maj em 11/11/2026: onde o
# administrativo está acima do QPO e quem são). Só faz sentido para militar
# não operacional e vaga não operacional — o resto é atividade-fim.
#   - EM: cada OPM da sede tem a sua seção no QPO. Agência de Área tem vagas
#     "a designar" no QPO, que não contam como vaga; quem estiver lá aparece
#     acima. SEC SDM ATIV TEC (990119100) é a Chefia da Seção Adm (1 Cap).
#   - SGB: o código terminado em 000 (sede do SGB) e o 800 (ADM do SGB) somam
#     "Comando" e "Adm" do QPO; o terminado em N00 é a sede do Nº Pelotão.
# Os rótulos são os mesmos dos dois lados, para cruzar vaga e militar.
SQL_SECAO_ADM = f"""
    CASE WHEN {_EH_SAT}                                     THEN 'SAT'
         WHEN cod_opm_atual = 990110000                     THEN 'Comando'
         WHEN cod_opm_atual = 990119100                     THEN 'Chefia da Seção Adm'
         WHEN cod_opm_atual = 990119110                     THEN 'B/1 e B/5'
         WHEN cod_opm_atual = 990119120                     THEN 'Agência de Área'
         WHEN cod_opm_atual = 990119130                     THEN 'B/3, PJMD e Motomec'
         WHEN cod_opm_atual = 990119140                     THEN 'B/4'
         WHEN cod_opm_atual = 990119160                     THEN 'St UGE'
         WHEN right(cod_opm_atual::text, 3) IN ('000','800') THEN 'Sede do SGB (Cmdo e Adm)'
         WHEN right(cod_opm_atual::text, 2) = '00'
              THEN substr(cod_opm_atual::text, 7, 1) || 'º Pelotão (sede)'
         ELSE opm_atual END
"""

SQL_SECAO_ADM_QPO = """
    CASE WHEN lotacao = 'EM' AND secao = 'Comando'          THEN 'Comando'
         WHEN lotacao = 'EM' AND secao ILIKE '%Ativ T%'     THEN 'SAT'
         WHEN lotacao = 'EM' AND COALESCE(subsecao, '') = '' THEN 'Chefia da Seção Adm'
         WHEN lotacao = 'EM' AND subsecao ILIKE 'Agência%'  THEN 'Agência de Área'
         WHEN lotacao = 'EM'                                THEN subsecao
         WHEN secao IN ('Comando', 'Adm')                   THEN 'Sede do SGB (Cmdo e Adm)'
         ELSE left(secao, 2) || ' Pelotão (sede)' END
"""

# Círculo do posto, igual nos dois lados: o QPO já agrupa assim.
SQL_CIRCULO = """
    CASE WHEN posto_grad ~ '(TEN|CAP|MAJ|CEL)' AND posto_grad !~ 'SUBTEN' THEN 'Oficiais'
         WHEN posto_grad ~ '(SUBTEN|SGT)'                                 THEN 'Subten/Sgt'
         ELSE 'Cb/Sd' END
"""

SQL_CIRCULO_QPO = """
    CASE WHEN posto_grad = 'Subten/Sgt' THEN 'Subten/Sgt'
         WHEN posto_grad = 'Cb/Sd'      THEN 'Cb/Sd'
         ELSE 'Oficiais' END
"""
