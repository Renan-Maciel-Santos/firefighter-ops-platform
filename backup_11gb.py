"""
Backup do 11GB — bancos, segredos e workflow da B.I.A.

Uso:
    python backup_11gb.py              → backup completo
    python backup_11gb.py --verificar  → só confere os backups que já existem

O QUE ENTRA, E POR QUE CADA COISA
    postgres/11gb.dump          efetivo, IAS, restrições, TAF, ocorrências,
                                viaturas, UGE, SJD, QPO e os usuários do painel
    postgres/evolution_api.dump instância do WhatsApp e a sessão pareada
    postgres/n8n_bia.dump       o workflow da B.I.A. e as credenciais dele
    env/.env                    SEM ISTO O RESTORE NÃO FUNCIONA. Guarda a
                                N8N_ENCRYPTION_KEY — sem ela as credenciais do
                                n8n não descriptografam, e o dump do n8n_bia
                                vira um arquivo bonito e inútil. Guarda também
                                a JWT_SECRET_KEY: trocá-la invalida todas as
                                sessões do painel.
    n8n/workflow_bia.json       export legível do workflow, para diff e leitura
                                sem subir um Postgres

POR QUE ESTE SCRIPT EXISTE
Até 09/09/2026 o backup era manual. O último completo era de 01/09 — oito dias
—, feito à mão, e morava no mesmo disco do banco. Um disco só, sem RAID: se ele
morresse, iam junto a chave de cifra do n8n, a sessão do WhatsApp e o histórico
de efetivo. É a única falha do sistema que não tem conserto depois.

VERIFICAÇÃO
Um backup que nunca foi lido não é backup, é esperança. Cada dump é conferido
com `pg_restore --list` logo depois de gerado: se o arquivo estiver truncado ou
corrompido, isso falha aqui, e não no dia em que alguém precisar restaurar.

ALERTA
Registra em b1.etl_status como domínio `backup`. O bia_watchdog.py vigia a
idade desse registro e manda e-mail se passar do limite — mesma máquina que já
avisa sobre viaturas e ETL. Backup que para de rodar em silêncio é igual a não
ter backup.

DESTINO
BACKUP_DIR no .env (padrão <raiz do projeto>/backups). BACKUP_DIR_2, se preenchido,
recebe uma cópia — é a cópia que sobrevive ao disco morrer. Vazia, o script
avisa em toda execução que o backup está num disco só.

ATENÇÃO ao escolher o segundo destino: este conteúdo tem dado pessoal de 501
militares, restrição de saúde, processo disciplinar e todas as chaves do
sistema. Nuvem pessoal não é lugar para isso.

CÓPIA CIFRADA (desde 06/10/2026)
O segundo destino é //servidor/compartilhado/11GB/BACKUP_SISTEMA. Todo o 11GB
lê aquele share (o grupo de acesso da unidade tem Modify em todas as pastas), então
a cópia vai num único arquivo <carimbo>.11gb.enc: tar.gz cifrado com
AES-256-GCM, com chave derivada por scrypt de BACKUP_SENHA_2. Depois de
gravado, o arquivo é relido, decifrado e conferido contra a pasta local.

A senha mora no .env, que está DENTRO do backup e no mesmo disco. Se o disco
morrer, só a cópia em papel/cofre abre o arquivo. Sem ela, a cópia do share
é inútil.

Restaurar numa máquina nova (pede a senha se o .env não existir):
    python backup_11gb.py --decifrar <arquivo.11gb.enc> <pasta_destino>
"""

import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))
from _env import exigir, opcional

CONTAINER = opcional("BACKUP_CONTAINER", "postgres_11gb")
PG_USER_DB = opcional("PG_USER", "admin")

DESTINO = Path(opcional("BACKUP_DIR", str(Path(__file__).resolve().parent / "backups")))
DESTINO_2 = opcional("BACKUP_DIR_2")
SENHA_2 = opcional("BACKUP_SENHA_2")

# Retenção. Diários cobrem "apaguei ontem"; semanais cobrem "corrompeu há um
# mês e ninguém viu". Guardar tudo para sempre enche o disco e ninguém percebe.
MANTER_DIARIOS = int(opcional("BACKUP_MANTER_DIARIOS", "14"))
MANTER_SEMANAIS = int(opcional("BACKUP_MANTER_SEMANAIS", "8"))

BANCOS = ("11gb", "evolution_api", "n8n_bia")
RAIZ = Path(__file__).resolve().parent


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def docker(*args, saida=None, texto=False):
    """Roda docker exec. Com `saida`, escreve o stdout no arquivo."""
    cmd = ["docker", "exec", CONTAINER, *args]
    if saida:
        with open(saida, "wb") as f:
            r = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, timeout=1800)
    else:
        r = subprocess.run(cmd, capture_output=True, timeout=1800)
    if r.returncode != 0:
        erro = (r.stderr or b"").decode("utf-8", "replace")[:400]
        raise RuntimeError(f"docker exec falhou ({r.returncode}): {erro}")
    return r.stdout if not saida else None


def dump_banco(banco: Path, destino: Path):
    """pg_dump em formato custom: comprimido e restaurável seletivamente."""
    arquivo = destino / f"{banco}.dump"
    log(f"  {banco} ...")
    docker("pg_dump", "-U", PG_USER_DB, "-d", banco, "-Fc", "--no-owner",
           saida=arquivo)
    mb = arquivo.stat().st_size / 1024 / 1024
    if arquivo.stat().st_size < 1024:
        raise RuntimeError(f"{banco}: dump com {arquivo.stat().st_size} bytes — "
                           f"pequeno demais para ser real")
    log(f"  {banco} ok ({mb:.1f} MB)")
    return arquivo


def verificar(arquivo: Path) -> int:
    """Lê o índice do dump. Prova que o arquivo é restaurável, não só que existe."""
    try:
        with open(arquivo, "rb") as f:
            r = subprocess.run(
                ["docker", "exec", "-i", CONTAINER, "pg_restore", "--list"],
                stdin=f, capture_output=True, timeout=600,
            )
        if r.returncode != 0:
            return -1
        return len([l for l in r.stdout.decode("utf-8", "replace").splitlines()
                    if l and not l.startswith(";")])
    except Exception:
        return -1


def exportar_workflow(destino: Path):
    """Workflow da B.I.A. em JSON legível, para diff sem levantar um Postgres."""
    arquivo = destino / "workflow_bia.json"
    saida = docker("psql", "-U", PG_USER_DB, "-d", "n8n_bia", "-tAc",
                   "select json_build_object('name',name,'active',active,"
                   "'nodes',nodes,'connections',connections)::text "
                   "from workflow_entity;")
    arquivo.write_bytes(saida)
    log(f"  workflow_bia.json ok ({arquivo.stat().st_size/1024:.0f} KB)")


# Formato do .11gb.enc: MAGICO + sal (16) + nonce (12) + tar.gz cifrado com a tag do GCM.
# scrypt n=2**15 gasta ~32 MB e uma fração de segundo: barato para quem tem a senha,
# caro para quem tenta adivinhar.
MAGICO = b"11GBBKP1"


def _chave(senha: str, sal: bytes) -> bytes:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    return Scrypt(salt=sal, length=32, n=2**15, r=8, p=1).derive(senha.encode("utf-8"))


def cifrar(pasta: Path, arquivo: Path, senha: str):
    """Empacota a pasta em tar.gz e grava cifrado. Grava em .tmp e renomeia, para
    que uma cópia interrompida no meio nunca pareça um backup completo."""
    import io
    import os as _os
    import tarfile
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(pasta, arcname=pasta.name)
    sal, nonce = _os.urandom(16), _os.urandom(12)
    cifrado = AESGCM(_chave(senha, sal)).encrypt(nonce, buf.getvalue(), MAGICO)
    tmp = arquivo.with_name(arquivo.name + ".tmp")
    tmp.write_bytes(MAGICO + sal + nonce + cifrado)
    tmp.replace(arquivo)


def decifrar(arquivo: Path, senha: str):
    """Devolve o tar.gz aberto. Senha errada ou arquivo adulterado falham aqui (tag do GCM)."""
    import io
    import tarfile
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    dados = arquivo.read_bytes()
    if not dados.startswith(MAGICO):
        raise RuntimeError(f"{arquivo.name} não é um backup cifrado do 11GB")
    sal, nonce, cifrado = dados[8:24], dados[24:36], dados[36:]
    try:
        claro = AESGCM(_chave(senha, sal)).decrypt(nonce, cifrado, MAGICO)
    except Exception:
        raise RuntimeError(f"{arquivo.name}: senha errada ou arquivo corrompido")
    return tarfile.open(fileobj=io.BytesIO(claro), mode="r:gz")


def conferir_cifrado(arquivo: Path, pasta: Path, senha: str):
    """Relê o que foi gravado e compara nome e tamanho de cada arquivo com a pasta local."""
    with decifrar(arquivo, senha) as tar:
        no_tar = {m.name: m.size for m in tar.getmembers() if m.isfile()}
    local = {f"{pasta.name}/{f.relative_to(pasta).as_posix()}": f.stat().st_size
             for f in pasta.rglob("*") if f.is_file()}
    if no_tar != local:
        raise RuntimeError(f"{arquivo.name} não confere com {pasta}: "
                           f"{sorted(set(no_tar.items()) ^ set(local.items()))[:5]}")
    return len(no_tar)


def limpar_antigos(base: Path):
    """Retenção: N diários, e um por semana além disso. Vale para as pastas locais e
    para os .11gb.enc do segundo destino."""
    pastas = sorted([p for p in base.glob("20*_*")
                     if p.is_dir() or p.name.endswith(".11gb.enc")], reverse=True)
    hoje = datetime.now()
    manter, semanas_vistas = set(), set()

    for i, p in enumerate(pastas):
        try:
            quando = datetime.strptime(p.name[:15], "%Y%m%d_%H%M%S")
        except ValueError:
            manter.add(p)      # nome fora do padrão: não é meu, não apago
            continue
        if i < MANTER_DIARIOS:
            manter.add(p)
            continue
        semana = quando.isocalendar()[:2]
        if semana not in semanas_vistas and quando > hoje - timedelta(weeks=MANTER_SEMANAIS):
            semanas_vistas.add(semana)
            manter.add(p)

    for p in pastas:
        if p not in manter:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)
            log(f"  removido (retenção): {p.name}")


def registrar(status: str, erro: str | None = None):
    """b1.etl_status — é daí que o bia_watchdog.py vê que o backup parou."""
    sql = """
        INSERT INTO b1.etl_status (dominio, status, iniciado_em, finalizado_em, erro)
        VALUES ('backup', :s, now(), now(), :e)
        ON CONFLICT (dominio) DO UPDATE
           SET status = EXCLUDED.status,
               iniciado_em = EXCLUDED.iniciado_em,
               finalizado_em = EXCLUDED.finalizado_em,
               erro = EXCLUDED.erro
    """.replace(":s", f"'{status}'").replace(
        ":e", "NULL" if not erro else "'" + erro.replace("'", "''")[:400] + "'")
    try:
        docker("psql", "-U", PG_USER_DB, "-d", "11gb", "-c", sql)
    except Exception as e:
        log(f"  AVISO: não consegui registrar em etl_status: {e}")


def main():
    if "--decifrar" in sys.argv:
        i = sys.argv.index("--decifrar")
        try:
            arquivo, saida = Path(sys.argv[i + 1]), Path(sys.argv[i + 2])
        except IndexError:
            raise SystemExit("uso: python backup_11gb.py --decifrar <arquivo.11gb.enc> <pasta_destino>")
        senha = SENHA_2
        if not senha:
            import getpass
            senha = getpass.getpass("senha do backup (BACKUP_SENHA_2): ")
        with decifrar(arquivo, senha) as tar:
            tar.extractall(saida, filter="data")
        log(f"extraído em {saida}")
        return

    if "--verificar" in sys.argv:
        pastas = sorted([p for p in DESTINO.glob("20*_*") if p.is_dir()], reverse=True)
        if not pastas:
            log("nenhum backup encontrado")
            raise SystemExit(1)
        for p in pastas[:5]:
            log(p.name)
            for d in sorted((p / "postgres").glob("*.dump")):
                n = verificar(d)
                mb = d.stat().st_size / 1024 / 1024
                log(f"  {d.name:22} {mb:7.1f} MB  "
                    + (f"{n} objetos — íntegro" if n > 0 else "ILEGÍVEL"))
        if DESTINO_2 and SENHA_2:
            cifrados = sorted(Path(DESTINO_2).glob("20*_*.11gb.enc"), reverse=True)
            log(f"segundo destino ({DESTINO_2}): {len(cifrados)} cópia(s)")
            if cifrados:
                with decifrar(cifrados[0], SENHA_2) as tar:
                    n = len([m for m in tar.getmembers() if m.isfile()])
                log(f"  {cifrados[0].name}  decifrado, {n} arquivos")
        return

    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    pasta = DESTINO / carimbo
    (pasta / "postgres").mkdir(parents=True, exist_ok=True)
    (pasta / "env").mkdir(exist_ok=True)
    (pasta / "n8n").mkdir(exist_ok=True)

    log(f"backup em {pasta}")
    try:
        log("bancos:")
        arquivos = [dump_banco(b, pasta / "postgres") for b in BANCOS]

        log("verificando:")
        for a in arquivos:
            n = verificar(a)
            if n <= 0:
                raise RuntimeError(f"{a.name} não é restaurável — pg_restore não leu o índice")
            log(f"  {a.name:22} {n} objetos")

        log("segredos e workflow:")
        env = RAIZ / ".env"
        if env.exists():
            shutil.copy2(env, pasta / "env" / ".env")
            log("  .env ok (contém N8N_ENCRYPTION_KEY — sem ele o restore do n8n é inútil)")
        else:
            log("  AVISO: .env não encontrado — o restore do n8n não vai funcionar")
        exportar_workflow(pasta / "n8n")

        if DESTINO_2:
            # Sem senha não copia: o segundo destino é lido pelo 11GB inteiro, e uma
            # cópia em claro lá expõe as chaves e os dados pessoais. Melhor falhar alto.
            if not SENHA_2:
                raise RuntimeError("BACKUP_DIR_2 definido sem BACKUP_SENHA_2 — "
                                   "a cópia do share só sai cifrada")
            alvo = Path(DESTINO_2) / f"{carimbo}.11gb.enc"
            log(f"cópia cifrada em {alvo}")
            alvo.parent.mkdir(parents=True, exist_ok=True)
            cifrar(pasta, alvo, SENHA_2)
            n = conferir_cifrado(alvo, pasta, SENHA_2)
            log(f"  ok — {alvo.stat().st_size/1024/1024:.1f} MB, relido e decifrado, {n} arquivos conferem")
            limpar_antigos(Path(DESTINO_2))
        else:
            log("  AVISO: BACKUP_DIR_2 vazio — o backup está num disco só, o mesmo")
            log("         do banco. Não protege contra o disco morrer.")

        limpar_antigos(DESTINO)

        total = sum(f.stat().st_size for f in pasta.rglob("*") if f.is_file())
        log(f"concluído — {total/1024/1024:.1f} MB")
        registrar("success")

    except Exception as e:
        log(f"FALHOU: {e}")
        registrar("error", str(e))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
