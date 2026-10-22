# Provisionamento do cluster

Scripts de criação de databases e roles no `postgres_11gb`. Rodam uma vez
por ambiente. Não são migrações de schema — o schema do `11gb` é
gerenciado pelos ETLs, e o do `n8n_bia` pelo próprio n8n.

Senhas entram por variável do `psql` (`-v`), nunca literais no arquivo.

## Estado do cluster (levantado em 2026-08-31)

`postgres:16`, container `postgres_11gb`, porta 5432 do host, na rede
`rede_11gb` com os aliases `postgres_11gb` e **`postgres`**.

| Database | Owner | Conteúdo |
|---|---|---|
| `11gb` | `admin` | webapp, ETLs, consultas da B.I.A. |
| `evolution_api` | `admin` | instâncias, mensagens e contatos da Evolution |
| `n8n_bia` | `n8n_bia_user` | workflows, credenciais e execuções do n8n *(criado pelo 001)* |

Antes do `001` o cluster tinha **uma única role**: `admin`, superuser,
usada por todos os sistemas. `n8n_bia_user` é a primeira role de
privilégio mínimo aqui.

## Como aplicar

Ambiente é Windows/PowerShell. Heredoc (`<< 'EOF'`) não existe no
PowerShell: o SQL vai por arquivo, não por stdin inline.

```powershell
docker cp db\provisioning\001_n8n_database.sql postgres_11gb:/tmp/001_n8n_database.sql
```

Carregue o `.env` da raiz e passe os valores como variáveis do `psql`:

```powershell
$e = @{}
Get-Content .env | Where-Object { $_ -match '^\s*[A-Za-z]' } | ForEach-Object { $p = $_ -split '=',2; if ($p.Count -eq 2) { $e[$p[0].Trim()] = $p[1].Trim() } }
docker exec postgres_11gb psql -U admin -d postgres -v n8n_user=$($e['N8N_PG_USER']) -v n8n_password=$($e['N8N_PG_PASS']) -v n8n_db=$($e['N8N_PG_DB']) -f /tmp/001_n8n_database.sql
```

Executar contra `-d postgres`, não contra o `11gb`.

Para SQL avulso multi-linha, o padrão no PowerShell é arquivo + pipe:

```powershell
Get-Content .\tmp.sql -Raw | docker exec -i postgres_11gb psql -U admin -d postgres
```

## Verificação

```powershell
docker exec postgres_11gb psql -U admin -d postgres -c "\l" -c "\du"
```

Esperado: `n8n_bia` com owner `n8n_bia_user`, e a role **sem** atributo
de superusuário.

Conexão da role — **deve passar**:

```powershell
docker exec postgres_11gb psql "postgresql://n8n_bia_user:SENHA@localhost:5432/n8n_bia" -c "SELECT current_user, current_database()"
```

Isolamento, depois do `002` — **deve falhar** com
`FATAL: permission denied for database "11gb"`:

```powershell
docker exec postgres_11gb psql "postgresql://n8n_bia_user:SENHA@localhost:5432/11gb" -c "SELECT 1"
```

## Rollback

`001` — seguro enquanto o database estiver vazio, ou seja, antes do
primeiro start do n8n:

```powershell
docker exec postgres_11gb psql -U admin -d postgres -c "DROP DATABASE n8n_bia" -c "DROP ROLE n8n_bia_user"
```

Depois que o n8n criou o schema e gravou workflows, `DROP DATABASE`
apaga tudo — a partir daí o rollback é o do runbook, não este.

`002` — `GRANT CONNECT ON DATABASE <db> TO PUBLIC` devolve o padrão.

## Nota de segurança

As senhas passam como argumento de processo e ficam visíveis na lista de
processos da máquina. Aceitável na estação de trabalho; num host
compartilhado, usar `PGPASSWORD` via arquivo de ambiente.
