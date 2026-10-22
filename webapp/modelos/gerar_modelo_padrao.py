"""
Gera webapp/modelos/eap_os_modelo.docx — o modelo PADRÃO da OS do EAP.

O modelo de produção é a OS oficial da unidade com os trechos variáveis
trocados por campos {{...}} (ver eap_documento.py). Ele não vai para o
repositório público; este script monta um equivalente com texto fictício e os
mesmos campos, para a aba EAP gerar a OS na demonstração. O Dockerfile roda
este script no build.
"""
import os

import docx
from docx.shared import Pt

SAIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eap_os_modelo.docx")

d = docx.Document()
d.styles["Normal"].font.name = "Arial"
d.styles["Normal"].font.size = Pt(11)
for linha in [
    "CORPO DE BOMBEIROS — GRUPAMENTO FICTÍCIO",
    "ORDEM DE SERVIÇO Nº EAP-{{numero}}/{{ano}}",
    "{{data_extenso}}",
    "Destinatários: {{destinatarios}}",
    "Assunto: {{assunto}}",
    "{{n}}. FINALIDADE",
    "Regular a participação do efetivo no Estágio de Atualização Profissional (EAP) de {{ano}}.",
    "{{se:pracas}}{{n}}. PÚBLICO: {{publico_pracas}}, no período de ensino a distância de {{periodo_ead}}.",
    "{{se:pracas}}{{n}}. FASE PRESENCIAL: {{presencial_pracas}}, em {{local_pracas}}.",
    "{{se:oficiais}}{{n}}. OFICIAIS: período de ensino a distância de {{periodo_ead}}.",
    "{{n}}. MILITARES ESCALADOS",
    "{{militares}}",
    "{{n}}. PRESCRIÇÕES DIVERSAS",
    "Os militares escalados ficam dispensados do serviço operacional nos dias da fase presencial.",
    "",
    "{{assinante_nome}}",
    "{{assinante_funcao}}",
]:
    d.add_paragraph(linha)
d.save(SAIDA)
print("modelo gerado:", SAIDA)
