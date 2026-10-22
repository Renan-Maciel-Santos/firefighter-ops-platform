# n8n/workflows

O compose monta esta pasta em `/workflows`, somente leitura, para o
`n8n import:workflow`. Fora de uma importação, ela fica vazia — de
propósito. A fonte do workflow é o banco do n8n; a cópia legível sai todo
dia junto com o backup (`backup_11gb.py`).

## Por que export daqui não vai para o git

`.gitignore` ignora `n8n/workflows/*.json`. Um export do n8n carrega os
parâmetros dos nós como estão, e um header de autenticação escrito à mão
num nó HTTP (por exemplo, a apikey da Evolution) sai em texto claro. Essa
chave dá controle total da instância do WhatsApp: ler conversas, enviar
mensagens e desparear o aparelho. Commitá-la seria publicar a credencial no
histórico do git, de onde não sai sem reescrever a história.

### Como tornar o workflow versionável

1. No n8n, crie uma credencial **Header Auth** com `apikey: <valor>`.
2. Troque os nós HTTP que chamam a Evolution para usar essa credencial em
   vez do header escrito à mão.
3. Exporte para esta pasta e confirme que a chave sumiu:
   `Select-String -Path .\n8n\workflows\*.json -SimpleMatch "<apikey>"`
   — não deve retornar nada.
4. Só então remova `n8n/workflows/*.json` do `.gitignore`.

## O que o workflow da B.I.A. espera do ambiente

- **Entrada:** nó `Webhook Evolution (WhatsApp)`, `POST`, path
  `bia-whatsapp`. URL final = `<WEBHOOK_URL>webhook/bia-whatsapp`.
- **Saída → Evolution API:**
  `http://host.docker.internal:8080/message/sendText/...`
- **Saída → webapp:** endpoints `http://host.docker.internal:8000/consulta/*`
  (dossiê, efetivo, TAF, IAS, motomec, restrições, guarnição, saúde, UGE),
  autenticados pelo cabeçalho `X-API-Token`.

Os dois destinos usam `host.docker.internal`; por isso o compose mantém o
`extra_hosts` mesmo com o container na `rede_11gb`.

## Exportar para cá

```powershell
docker exec n8n_11gb n8n export:workflow --all --separate --output=/tmp/wf
docker cp n8n_11gb:/tmp/wf/. .\n8n\workflows\
```
