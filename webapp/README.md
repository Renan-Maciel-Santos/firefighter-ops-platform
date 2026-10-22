# webapp — painel e API

FastAPI que serve o painel (HTML estático em `frontend/`) e a API que o painel e
a B.I.A. consomem. Para subir com dados fictícios, siga o README da raiz
(docker compose + seed); esta página descreve o webapp em si.

## Rodar fora do Docker

```bash
pip install -r ../requirements.txt
python modelos/gerar_modelo_padrao.py
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

As credenciais vêm do `.env` da raiz (`PG_*`, `JWT_SECRET_KEY`, `N8N_TOKEN`) via
`_env.py`; variável obrigatória ausente derruba o processo com a mensagem do que
falta. Documentação interativa em `/api/docs`.

Em produção o webapp roda como tarefa agendada do Windows
(`registrar_servico_admin.ps1` registra; `iniciar_webapp.ps1` escolhe o Python,
grava logs em `logs/` e reinicia se cair).

## Acesso

A regra mora só em `acesso.py`; o frontend a recebe em `/auth/me` e apenas
esconde o que o backend já nega.

| Perfil | Vê |
|---|---|
| `admin` | todas as abas e a gestão de usuários |
| `oficial` | todas as abas, menos usuários |
| `praca` | só as abas da seção do cadastro (`SECAO_ABAS`) |

Usuários são criados pela aba **Usuários** (o admin recebe uma senha provisória
e o usuário troca no primeiro login) ou por `gerenciar_usuarios.py`.

Os endpoints `/consulta/*` são da B.I.A.: não usam login, e sim o cabeçalho
`X-API-Token` com o `N8N_TOKEN`. Devolvem o campo `mensagem` já no formato do
WhatsApp, para o modelo só repassar.

## Estrutura

```
webapp/
├── main.py               app FastAPI e arquivos estáticos
├── database.py           conexão (SQLAlchemy)
├── models.py             app.usuarios
├── acesso.py             perfis, seções e abas — fonte única da permissão
├── efetivo_regras.py     classificação do efetivo (lotação, atividade-fim)
├── eap_documento.py      preenchimento da OS do EAP (.docx)
├── modelos/              gerador do modelo padrão da OS
├── routers/              uma rota por aba + consulta.py (B.I.A.)
└── frontend/             index.html (login), dashboard.html, eap.js, ...
```

`init_db.sql` e `migra_*.sql` são o histórico de como `app.usuarios` evoluiu; o
schema atual completo está em `db/demo/schema.sql`.
