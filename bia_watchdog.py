"""
Watchdog da B.I.A. — vigia os QUATRO elos da cadeia, não só o WhatsApp.

    WhatsApp -> Evolution -> n8n -> webapp(:8000) -> Postgres

Olhar só o gateway do WhatsApp não basta: com o webapp fora do ar a B.I.A.
continua conectada, recebe a mensagem e erra TODA consulta — falha sem
sintoma visível. Por isso cada elo é checado separadamente.

Detectar sem avisar é o mesmo que não detectar: um alerta que só vai para um
.log ou um toast na própria máquina não chega a ninguém. Por isso o alerta
sai da máquina por e-mail.

Ele também vigia o FRESCOR do que a B.I.A. responde, não só se ela responde: b1.etl_status por idade (não pela coluna `status`, que guarda
o último sucesso e por isso marcava 'success' em viaturas com 5 dias de
atraso) e o código de saída das tarefas de carga.

Roda a cada 5min (via Task Scheduler do Windows). O que ele corrige sozinho:
containers parados (docker start) e webapp fora do ar (dispara a tarefa
11GB_Webapp). O que ele só avisa: sessão do WhatsApp, que exige parear.

O aviso vai para ALERTA_EMAIL_PARA (.env), no máximo um por problema a cada
4h, mais um e-mail de normalização quando tudo volta. Sem SMTP configurado
ele segue vigiando e corrigindo, e registra no log que o alerta não saiu.

E quem vigia o vigia: a cada rodada sai um pulso para HEARTBEAT_URL (.env),
um dead man's switch no healthchecks.io. Se esta máquina desligar ou a
tarefa parar, o pulso some e o alarme é do serviço de fora — sem isso o
silêncio seria indistinguível de "está tudo bem".

Uso manual:
    python bia_watchdog.py                → checa os 4 elos, 1 vez
    python bia_watchdog.py --so-whatsapp  → só a sessão (comportamento antigo)
    python bia_watchdog.py --loop 300     → loop infinito a cada 300s (debug)
    python bia_watchdog.py --qr-agora     → QR novo agora, zerando o cooldown
                                            (use quando estiver com o celular)

Arquivos gerados:
    logs\\bia_watchdog.log            — histórico completo
    logs\\bia_watchdog_alertas.json   — alertas em aberto (dedup do e-mail)
    logs\\bia_watchdog_qr_rodadas.txt — degrau atual do cooldown do QR
    n8n\\qrcode_bia_fresh.png         — QR pronto pra escanear
"""

import os, sys, re, json, base64, time
from datetime import datetime, timedelta
from pathlib import Path

import requests

# ==== CONFIG ====
# Acima: Credenciais do .env da raiz. A chave da Evolution dá controle total da instância
# do WhatsApp (ler conversas, enviar, desparear) — não pode viver num arquivo versionado.
sys.path.append(str(Path(__file__).resolve().parent))
from _env import exigir, opcional

API_URL   = opcional("EVOLUTION_URL", "http://localhost:8080")
API_KEY   = exigir("EVOLUTION_API_KEY")
INSTANCE  = opcional("EVOLUTION_INSTANCE", "bia11gb")
# Acima: Raiz do projeto (pasta deste arquivo); logs e QR ficam relativos a ela
RAIZ = Path(__file__).resolve().parent
LOG_FILE  = RAIZ / "logs" / "bia_watchdog.log"
QR_FILE   = RAIZ / "n8n" / "qrcode_bia_fresh.png"
HB_FILE   = RAIZ / "logs" / "bia_watchdog_heartbeat.txt"  # último "ok" — evita spam no log
HB_QUIET_MIN = 60  # só loga "ok" a cada 60min pra não poluir

# ---- Alerta por e-mail (SMTP) ----
# O aviso tem que sair da máquina: .log e toast só alcançam quem está nela.
#
# O canal é e-mail, e não WhatsApp, de propósito. Avisar pelo WhatsApp da
# própria B.I.A. seria autorreferente — se o que caiu foi a sessão do
# WhatsApp, o aviso não sairia.
#
# SMTP_PASS é senha de app do Gmail (conta com 2FA), não a senha da conta.
# Gerada em https://myaccount.google.com/apppasswords e escrita no .env.
SMTP_HOST   = opcional("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT   = int(opcional("SMTP_PORT", "587"))
SMTP_USER   = opcional("SMTP_USER")
# Lido direto do ambiente, não por `exigir` nem `opcional`: `exigir` derruba o
# processo inteiro (SystemExit) e mataria o watchdog em quem ainda não
# configurou e-mail — justamente o que ele existe para evitar. E `opcional`
# diz, no próprio docstring, para nunca ser usado com segredo. Sem SMTP_PASS
# o watchdog segue vigiando e corrigindo; só perde o e-mail, e avisa no log.
SMTP_PASS   = (os.environ.get("SMTP_PASS") or "").strip()
ALERTA_PARA = opcional("ALERTA_EMAIL_PARA")

# Reenvio do MESMO alerta. Sem isto uma queda longa vira um e-mail a cada
# 5min e o filtro do Gmail aprende a escondê-los — o problema
# que estamos consertando, de novo, com outra roupa.
ALERTA_REENVIO_MIN = 240
ALERTA_ESTADO = RAIZ / "logs" / "bia_watchdog_alertas.json"

# ---- Heartbeat: quem vigia o vigia ----
# O alerta por e-mail fechou o buraco de 03-08/09/2026, mas quem dispara o
# alerta continua morando nesta máquina. Se o Windows desligar, o Task
# Scheduler parar ou a tarefa BIA_Watchdog for desabilitada, o silêncio fica
# indistinguível de "está tudo bem" — que é a forma mais cara de falhar,
# porque não tem sintoma nenhum.
#
# Dead man's switch: o watchdog faz um GET nesta URL a cada rodada e um
# serviço de fora (healthchecks.io) reclama quando o pulso PARA de chegar.
# A lógica se inverte — em vez de precisar que a máquina consiga falar para
# avisar do problema, o problema é justamente ela ficar calada.
#
# A URL contém um UUID e vale como segredo: quem a tiver silencia o alarme.
# Por isso mora no .env, não aqui.
#
# Sugestão de configuração no healthchecks.io: period 5min (o intervalo da
# tarefa) e grace 30min, que tolera reboot e manutenção sem alarme falso.
HEARTBEAT_URL = opcional("HEARTBEAT_URL")

# Flag de rodada: fica True se um e-mail de alerta falhou no envio. Nesse
# caso o pulso vira /fail, porque o canal que contaria o problema quebrou e
# alguém precisa saber por outro caminho.
_ALERTA_NAO_SAIU = False

# ---- Webapp (porta 8000) ----
# É ele que serve as 20 tools. Se cair, a B.I.A. conecta no WhatsApp,
# recebe a mensagem e erra TODA consulta — falha silenciosa, sem sintoma visível.
WEBAPP_URL   = "http://localhost:8000/consulta/saude-geral"
TASK_WEBAPP  = "11GB_Webapp"   # tarefa agendada que sobe o uvicorn

# ---- Frescor dos dados ----
# LIÇÃO DE 08/09/2026: responder rápido com dado velho é a mesma falha
# silenciosa do webapp fora do ar, com outra fantasia. O watchdog vigiava se
# o sistema RESPONDE; não vigiava se o que ele responde ainda vale. Quando
# esta checagem foi escrita, b4_viaturas estava com 127h (5 dias) e ninguém
# sabia: as três tools de frota vinham entregando dado de 03/09 como se
# fosse de hoje.
#
# Julgamos por IDADE, não pela coluna `status` de b1.etl_status. Ela guarda o
# último SUCESSO, não a saúde atual — uma carga pode aparecer como 'success'
# com dias de atraso, porque as execuções que falharam não sobrescrevem a
# linha do último sucesso. Status responde "funcionou da última vez"; a
# pergunta que importa é "quando foi essa última vez".
#
# Os limites saem da cadência real de cada tarefa agendada, com folga para
# uma janela de falha antes de incomodar alguém:
#   Captura_SGP    05:30, de hora em hora por 15h  -> vão até 20:30, e a
#                  noite abre um vão normal de ~9h. Limite 14h não dispara
#                  nessa noite e pega uma manhã que não capturou.
#   ETL_Arquivos   uma vez por dia, 06:00          -> limite 48h tolera um
#                  dia perdido; dois dias é problema.
#   MapaForca      a cada 30min, o dia todo        -> limite 8h já são 16
#                  execuções perdidas.
#
# None = domínio não vigiado. ocorrencias e tempo_resposta não têm tarefa
# agendada nenhuma: são importações manuais, e cobrar cadência de quem não
# tem cadência produziria alarme permanente. Ficam registrados aqui de
# propósito, para a ausência ser uma decisão visível e não um esquecimento.
LIMITE_FRESCOR_H = {
    "efetivo":        14,
    "ias":            14,
    "restricoes":     14,
    "afastamentos":   14,
    "mapa_forca":      8,
    "b4_viaturas":    48,
    "sjd":            48,
    # Backup diário às 20:45. 30h tolera um dia perdido — máquina desligada,
    # rede caída — e acusa dois. Backup que para de rodar em silêncio é igual
    # a não ter backup, e é a única falha do sistema sem conserto depois.
    "backup":         30,
    # Promoções do SGP, todo dia 1º às 06:15 (coletor não incluído). 34 dias
    # cobre o mês de 31 e a tarefa que roda atrasada com a máquina desligada.
    "promocoes":     34 * 24,
    "ocorrencias":    None,
    "tempo_resposta": None,
}

# ---- Tarefas de ETL ----
# A checagem de idade pega "parou de atualizar"; esta pega "rodou e falhou",
# que é diferente e pode acontecer com o dado ainda fresco. Em 08/09/2026 a
# 11GB_ETL_Arquivos terminava com código 2 toda madrugada — visível no Task
# Scheduler e no log, e indo para lugar nenhum.
TAREFAS_ETL = {
    "11GB_Captura_SGP":  "efetivo, IAS, restrições e afastamentos",
    "11GB_ETL_Arquivos": "viaturas, NBI, UGE e SJD",
    "11GB_MapaForca":    "mapa de força",
    "11GB_Backup":       "backup dos bancos, do .env e do workflow",
    "11GB_Promocoes":    "promoções do SGP (antiguidade do encarregado no SDO)",
}

# Códigos do Task Scheduler que NÃO são falha: 0 sucesso, 0x41301 ainda
# rodando, 0x41303 nunca executada desde que foi criada.
TAREFA_OK = {0, 267009, 267011}

# ---- Banco (b1.etl_status) ----
# Mesmas credenciais que o resto do projeto usa. PG_PASS lido direto do
# ambiente pelo mesmo motivo de SMTP_PASS: `exigir` derrubaria o watchdog
# inteiro por causa de uma checagem acessória.
PG_HOST = opcional("PG_HOST", "localhost")
PG_PORT = opcional("PG_PORT", "5432")
PG_DB   = opcional("PG_DB", "11gb")
PG_USER = opcional("PG_USER")
PG_PASS = (os.environ.get("PG_PASS") or "").strip()

# ---- Containers que a B.I.A. exige ----
# n8n próprio (n8n_11gb, porta 5679) com database próprio no postgres_11gb.
# Só estes três estão no caminho da B.I.A.; outros containers da máquina não.
CONTAINERS = ["evolution_11gb", "n8n_11gb", "postgres_11gb"]

# ---- Cooldown do QR ----
# Puxar QR novo a cada 5min é comportamento que o WhatsApp penaliza (soft-ban).
# Só geramos QR novo a cada QR_COOLDOWN_MIN, e nunca durante 'connecting'
# recente — 'connecting' logo após boot é transitório e resolve sozinho.
QR_STAMP        = RAIZ / "logs" / "bia_watchdog_qr.txt"

# Intervalo fixo de 60min basta quando há alguém por perto para escanear, mas
# não numa queda longa sem ninguém: cada rodada de QR cicla até QRCODE_LIMIT=30,
# e uma noite inteira somaria centenas de tentativas de pareamento — o bastante
# para o WhatsApp passar a recusar com "tente novamente mais tarde" por horas.
#
# Por isso a espera cresce sozinha a cada rodada sem pareamento. O raciocínio
# da escada: a chance de
# alguém aparecer para escanear é alta na primeira hora e vai caindo; insistir
# no mesmo ritmo depois disso não aumenta a chance de parear, só gasta
# tentativas contra o limite do WhatsApp. Uma queda noturna de 12h dá 4
# rodadas em vez de 12.
#
# Primeira rodada é imediata (alguém pode estar por perto); daí em diante a
# espera é o próximo degrau, e o último se repete até parear.
QR_COOLDOWNS_MIN = [60, 120, 240, 480, 960, 1440]

# Quantas rodadas já foram gastas nesta queda. Zerado quando a instância volta
# para 'open' — sem isso a próxima queda começaria no meio da escada, esperando
# 16h para o primeiro QR de um problema recém-nascido.
QR_RODADAS = RAIZ / "logs" / "bia_watchdog_qr_rodadas.txt"
CONNECTING_STAMP    = RAIZ / "logs" / "bia_watchdog_connecting.txt"
CONNECTING_GRACA_MIN = 15  # tempo que toleramos 'connecting' antes de tratar como queda


def log(nivel, msg):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linha = f"[{ts}] {nivel:5s} {msg}"
    print(linha)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(linha + "\n")


def _toast_windows(titulo, mensagem):
    """Windows toast (via plyer). Fallback pra PowerShell BurntToast se plyer não estiver.

    Canal LOCAL. Serve para quem está na máquina no momento da queda.
    Continua útil, mas não conta como aviso: quem não está ali não vê.
    """
    try:
        from plyer import notification
        notification.notify(
            title=titulo,
            message=mensagem,
            app_name="B.I.A. Watchdog",
            timeout=15,
        )
        return
    except Exception as e:
        log("WARN", f"plyer falhou ({e}), tentando PowerShell...")

    try:
        import subprocess
        ps = f'''
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
        $template = @"
<toast><visual><binding template="ToastText02"><text id="1">{titulo}</text><text id="2">{mensagem}</text></binding></visual></toast>
"@
        $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
        $xml.LoadXml($template)
        $toast = New-Object Windows.UI.Notifications.ToastNotification $xml
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("B.I.A. Watchdog").Show($toast)
        '''
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       timeout=10, capture_output=True)
    except Exception as e2:
        log("WARN", f"PowerShell também falhou: {e2}")


def _qr_legivel(png):
    """Passa o QR para preto puro, triplica o tamanho e põe margem branca.

    A Evolution desenha o QR em azul, denso e com 348 px. Em 06/10/2026 o
    celular mal conseguia ler, e o QR expirava antes. Se o Pillow faltar,
    devolve o PNG original.
    """
    try:
        import io
        from PIL import Image
        im = Image.open(io.BytesIO(png)).convert("L").point(lambda v: 0 if v < 200 else 255, "1")
        im = im.resize((im.width * 3, im.height * 3), Image.NEAREST)
        fundo = Image.new("1", (im.width + 160, im.height + 160), 1)
        fundo.paste(im, (80, 80))
        buf = io.BytesIO()
        fundo.save(buf, "PNG")
        return buf.getvalue()
    except Exception as e:
        log("WARN", f"QR salvo sem ajuste de contraste: {e}")
        return png


def puxar_qr_fresh():
    """Bate no endpoint /instance/connect e salva o QR base64 como PNG."""
    try:
        r = requests.get(f"{API_URL}/instance/connect/{INSTANCE}",
                         headers={"apikey": API_KEY}, timeout=15)
        d = r.json()
        b64 = d.get("base64") or (d.get("qrcode") or {}).get("base64")
        if not b64:
            log("ERROR", f"connect não retornou QR: {d}")
            return False
        raw = re.sub(r"^data:image/[^;]+;base64,", "", b64)
        QR_FILE.parent.mkdir(parents=True, exist_ok=True)
        QR_FILE.write_bytes(_qr_legivel(base64.b64decode(raw)))
        log("INFO", f"QR fresh salvo em {QR_FILE}")
        return True
    except Exception as e:
        log("ERROR", f"falha ao puxar QR: {e}")
        return False


def _agora_menos(arquivo):
    """Minutos desde o carimbo gravado em `arquivo`, ou None se não existir."""
    if not arquivo.exists():
        return None
    try:
        t = datetime.fromisoformat(arquivo.read_text().strip())
    except Exception:
        return None
    return (datetime.now() - t).total_seconds() / 60


def _carimbar(arquivo):
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(datetime.now().isoformat())


def _rodadas_qr():
    """Quantas rodadas de QR já foram gastas na queda em curso."""
    if not QR_RODADAS.exists():
        return 0
    try:
        return max(0, int(QR_RODADAS.read_text().strip()))
    except Exception:
        # Arquivo ilegível conta como queda nova: errar para o lado de tentar
        # cedo demais é recuperável (uma rodada a mais); errar para o lado de
        # esperar 24h à toa deixa a B.I.A. muda sem motivo.
        return 0


def _gravar_rodadas_qr(n):
    try:
        QR_RODADAS.parent.mkdir(parents=True, exist_ok=True)
        QR_RODADAS.write_text(str(n))
    except Exception as e:
        log("WARN", f"não consegui gravar {QR_RODADAS.name}: {e}")


def _cooldown_qr(rodadas):
    """Espera até a próxima rodada, em minutos, depois de `rodadas` gastas."""
    if rodadas <= 0:
        return 0
    return QR_COOLDOWNS_MIN[min(rodadas, len(QR_COOLDOWNS_MIN)) - 1]


def _zerar_escada_qr():
    """Queda encerrada: a próxima começa de novo na primeira rodada."""
    QR_STAMP.unlink(missing_ok=True)
    QR_RODADAS.unlink(missing_ok=True)


# ==========================================================================
# ALERTA QUE SAI DA MÁQUINA (e-mail)
# Diagnóstico certo não basta se o aviso não sai do .log e do toast. Todo
# `notificar` também vira e-mail, com dois cuidados — não repetir
# o mesmo alerta a cada 5min, e avisar quando normalizar.
# ==========================================================================

def _humano(td):
    """timedelta -> '2 dias e 3h', '4h20', '35min'."""
    total = int(td.total_seconds())
    dias, resto = divmod(total, 86400)
    horas, resto = divmod(resto, 3600)
    minutos = resto // 60
    if dias:
        return f"{dias} dia{'s' if dias > 1 else ''} e {horas}h"
    if horas:
        return f"{horas}h{minutos:02d}"
    return f"{minutos}min"


def _ler_alertas():
    """Alertas em aberto: {titulo: {primeiro, ultimo_envio}}."""
    if not ALERTA_ESTADO.exists():
        return {}
    try:
        return json.loads(ALERTA_ESTADO.read_text(encoding="utf-8"))
    except Exception:
        # Arquivo corrompido não pode calar o watchdog: perde-se o histórico
        # de dedup (no pior caso um e-mail repetido), não a vigilância.
        return {}


def _gravar_alertas(estado):
    try:
        ALERTA_ESTADO.parent.mkdir(parents=True, exist_ok=True)
        ALERTA_ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    except Exception as e:
        log("WARN", f"não consegui gravar {ALERTA_ESTADO.name}: {e}")


def email_configurado():
    return bool(SMTP_USER and SMTP_PASS and ALERTA_PARA)


def enviar_email(assunto, corpo):
    """Envia um e-mail. Nunca levanta: e-mail é o extra, vigiar é o trabalho."""
    if not email_configurado():
        return False

    import smtplib
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = SMTP_USER
    msg["To"] = ALERTA_PARA
    msg.set_content(corpo)

    try:
        # Timeout curto de propósito: o Task Scheduler chama isto a cada 5min
        # e um SMTP que aceita conexão e não responde deixaria o watchdog
        # pendurado, parando de vigiar justamente durante uma queda.
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(SMTP_USER, SMTP_PASS)
            smtp.send_message(msg)
        return True
    except Exception as e:
        # Marca a rodada: sem e-mail, nenhum alerta de saúde chega a ninguém.
        # O pulso vira /fail para o vigia externo cobrir essa cegueira.
        global _ALERTA_NAO_SAIU
        _ALERTA_NAO_SAIU = True
        log("ERROR", f"falha ao enviar e-mail: {e}")
        return False


def _alertar_por_email(titulo, mensagem):
    """Manda o alerta por e-mail, no máximo um a cada ALERTA_REENVIO_MIN."""
    agora = datetime.now()
    estado = _ler_alertas()
    registro = estado.get(titulo) or {}
    primeiro = registro.get("primeiro") or agora.isoformat()

    ultimo = None
    if registro.get("ultimo_envio"):
        try:
            ultimo = datetime.fromisoformat(registro["ultimo_envio"])
        except Exception:
            pass

    # O alerta fica registrado como ABERTO mesmo que o envio falhe ou o e-mail
    # não esteja configurado — é esse registro que permite ao e-mail de
    # normalização dizer depois o que caiu e por quanto tempo.
    estado[titulo] = {"primeiro": primeiro, "ultimo_envio": registro.get("ultimo_envio")}
    _gravar_alertas(estado)

    if ultimo and (agora - ultimo) < timedelta(minutes=ALERTA_REENVIO_MIN):
        return

    if not email_configurado():
        log("WARN", "e-mail não configurado no .env (SMTP_USER, SMTP_PASS, "
                    "ALERTA_EMAIL_PARA) — este alerta ficou só na máquina")
        # Carimba mesmo sem enviar, senão este aviso repete a cada 5min e o
        # log volta a ser o lugar onde as coisas se perdem.
        estado[titulo]["ultimo_envio"] = agora.isoformat()
        _gravar_alertas(estado)
        return

    try:
        faz = _humano(agora - datetime.fromisoformat(primeiro))
    except Exception:
        faz = "agora"

    maquina = os.environ.get("COMPUTERNAME", "?")
    corpo = (
        f"{mensagem}\n"
        f"\n"
        f"Aberto há: {faz} (desde {datetime.fromisoformat(primeiro):%d/%m/%Y %H:%M})\n"
        f"Máquina:   {maquina}\n"
        f"Detectado: {agora:%d/%m/%Y %H:%M}\n"
        f"\n"
        f"A cadeia da B.I.A. é WhatsApp -> Evolution -> n8n -> webapp(:8000) -> Postgres.\n"
        f"Log completo: {LOG_FILE}\n"
        f"\n"
        f"Enquanto o problema durar, este aviso se repete a cada "
        f"{ALERTA_REENVIO_MIN // 60}h. Você recebe um e-mail quando normalizar.\n"
    )

    if enviar_email(f"[B.I.A.] {titulo}", corpo):
        estado[titulo]["ultimo_envio"] = agora.isoformat()
        _gravar_alertas(estado)
        log("INFO", f"alerta enviado por e-mail para {ALERTA_PARA}")


def pulsar(sucesso=True):
    """Pulso para o vigia externo. Silencioso se HEARTBEAT_URL não estiver no .env."""
    if not HEARTBEAT_URL:
        return
    url = HEARTBEAT_URL if sucesso else HEARTBEAT_URL.rstrip("/") + "/fail"
    try:
        # Timeout curto: o pulso é o último passo da rodada e não pode
        # atrasar a próxima. Se ele não sai, o vigia reclama sozinho — que é
        # exatamente o comportamento desejado, não um erro a mascarar.
        requests.get(url, timeout=10)
    except Exception as e:
        log("WARN", f"não consegui pulsar o heartbeat: {e}")


def notificar(titulo, mensagem):
    """Alerta nos dois canais: toast na máquina e e-mail fora dela."""
    _toast_windows(titulo, mensagem)
    _alertar_por_email(titulo, mensagem)


def avisar_normalizado():
    """Fecha os alertas abertos quando os quatro elos voltam."""
    estado = _ler_alertas()
    if not estado:
        return

    agora = datetime.now()
    linhas = []
    for titulo, registro in estado.items():
        try:
            duracao = _humano(agora - datetime.fromisoformat(registro["primeiro"]))
        except Exception:
            duracao = "duração desconhecida"
        linhas.append(f"  - {titulo} (aberto por {duracao})")

    log("OK", "tudo normalizado — fechando alertas")
    enviar_email(
        "[B.I.A.] normalizado",
        "Os quatro elos da B.I.A. voltaram a responder.\n"
        "\n"
        "Estava em aberto:\n"
        + "\n".join(linhas)
        + f"\n\nNormalizado em {agora:%d/%m/%Y %H:%M}.\n"
    )
    # Limpa mesmo se o envio falhar: estado velho faria o próximo e-mail de
    # normalização mentir sobre o que estava caído.
    _gravar_alertas({})


# ==========================================================================
# WEBAPP (:8000) — as 20 tools
# Sem ele a B.I.A. conecta, recebe a mensagem e erra TODA consulta, sem
# sintoma visível no WhatsApp — e olhar só o gateway (8080) não pega isso.
# ==========================================================================

def checar_webapp():
    """True só se quem atende a :8000 for O NOSSO webapp.

    "Alguém respondeu" não é "o webapp está no ar". Aceitar qualquer status
    < 500 deixa passar outro serviço que ocupe a porta 8000: ele devolve 404
    em /consulta/*, 404 < 500 parece sinal de vida, e a B.I.A. fica pronta
    para responder com todas as tools em 404 — exatamente a falha sem
    sintoma que esta função existe para pegar. E `subir_webapp` também não
    notaria o fracasso, porque confirma a subida chamando esta função.

    Por isso a checagem agora exige a assinatura do nosso app, e não um
    número de status: 401 com {"detail": "Token inválido"} na rota
    protegida. Um estranho na porta dá 404/"Not Found" e reprova.
    """
    try:
        r = requests.get(WEBAPP_URL, timeout=10)
    except Exception:
        return False

    if r.status_code >= 500:
        return False

    # 200 é possível se um dia a rota deixar de exigir token; 401 é o caso
    # de hoje. Nos dois, o corpo precisa ser JSON do nosso app.
    if r.status_code not in (200, 401):
        log("ALERTA", f"webapp: :8000 respondeu {r.status_code} — não é o nosso app")
        return False

    try:
        detalhe = r.json().get("detail", "")
    except Exception:
        log("ALERTA", "webapp: :8000 respondeu algo que não é JSON — não é o nosso app")
        return False

    if r.status_code == 401 and detalhe != "Token inválido":
        log("ALERTA", f"webapp: 401 inesperado em :8000 ({detalhe!r}) — não é o nosso app")
        return False

    return True


def subir_webapp():
    """Dispara a tarefa agendada que sobe o uvicorn."""
    import subprocess
    try:
        subprocess.run(["schtasks", "/Run", "/TN", "11GB_Webapp"],
                       capture_output=True, timeout=30)
        time.sleep(12)
        return checar_webapp()
    except Exception as e:
        log("ERROR", f"falha ao disparar tarefa do webapp: {e}")
        return False


# ==========================================================================
# FRESCOR DOS DADOS E SAÚDE DO ETL
# A B.I.A. pode estar de pé, respondendo em segundos, e mesmo assim entregar
# o mapa de força da semana passada. Estas duas checagens cobrem esse caso.
# ==========================================================================

def checar_frescor():
    """Domínios fora do limite de idade.

    Retorna lista de (dominio, horas, limite) — vazia se tudo fresco — ou
    None se NÃO FOI POSSÍVEL checar. A distinção é a mesma regra que a
    própria B.I.A. segue no prompt: falha não é resposta. Lista vazia
    significa "conferi e está tudo fresco"; None significa "não sei", e
    "não sei" nunca pode virar "está tudo certo".
    """
    if not (PG_USER and PG_PASS):
        log("WARN", "PG_USER/PG_PASS ausentes no .env — frescor não verificado")
        return None

    try:
        import psycopg2
        conexao = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, dbname=PG_DB,
            user=PG_USER, password=PG_PASS, connect_timeout=8,
        )
    except Exception as e:
        log("ERROR", f"não consegui abrir o banco para checar frescor: {e}")
        return None

    try:
        with conexao, conexao.cursor() as cur:
            cur.execute("""
                SELECT dominio,
                       EXTRACT(EPOCH FROM (now() - COALESCE(finalizado_em,
                                                            iniciado_em))) / 3600
                  FROM b1.etl_status
            """)
            linhas = cur.fetchall()
    except Exception as e:
        log("ERROR", f"falha ao ler b1.etl_status: {e}")
        return None
    finally:
        conexao.close()

    velhos = []
    for dominio, horas in linhas:
        if dominio not in LIMITE_FRESCOR_H:
            # Domínio novo que ninguém pensou em vigiar é exatamente como os
            # buracos anteriores começaram. Fica no log para ser notado.
            log("INFO", f"domínio '{dominio}' sem limite de frescor definido")
            continue
        limite = LIMITE_FRESCOR_H[dominio]
        if limite is None or horas is None:
            continue
        if horas > limite:
            velhos.append((dominio, float(horas), limite))

    return sorted(velhos, key=lambda v: -v[1])


def checar_tarefas_etl():
    """Tarefas de ETL cujo último resultado foi falha.

    Retorna lista de (tarefa, codigo). Lê LastTaskResult pelo PowerShell, e
    não pelo `schtasks`, porque a saída do schtasks é traduzida — num Windows
    em português o parse quebraria calado.
    """
    import subprocess

    # Uma única invocação para todas as tarefas: subir o PowerShell custa
    # ~1s, e isto roda de 5 em 5 minutos. Três chamadas separadas seriam 3s
    # de processo novo a cada rodada para ler três inteiros.
    script = (
        "$nomes = @(" + ",".join(f"'{t}'" for t in TAREFAS_ETL) + ");"
        "foreach ($n in $nomes) {"
        "  try { $i = Get-ScheduledTaskInfo -TaskName $n -ErrorAction Stop;"
        "        Write-Output ($n + '=' + $i.LastTaskResult) }"
        "  catch { Write-Output ($n + '=?') } }"
    )

    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=60,
        )
    except Exception as e:
        log("WARN", f"não consegui consultar as tarefas de ETL: {e}")
        return []

    lidas, falhas = set(), []
    for linha in (out.stdout or "").splitlines():
        linha = linha.strip()
        if "=" not in linha:
            continue
        tarefa, _, bruto = linha.partition("=")
        if tarefa not in TAREFAS_ETL:
            continue
        lidas.add(tarefa)
        try:
            codigo = int(bruto)
        except ValueError:
            # Tarefa sumiu ou o Get-ScheduledTaskInfo recusou. Não sei o
            # estado dela, e "não sei" não vira "falhou" nem "está ok".
            log("WARN", f"tarefa {tarefa}: não consegui ler o último resultado")
            continue
        if codigo not in TAREFA_OK:
            falhas.append((tarefa, codigo))

    for tarefa in TAREFAS_ETL:
        if tarefa not in lidas:
            log("WARN", f"tarefa {tarefa}: sem resposta do Task Scheduler")

    return falhas


# ==========================================================================
# CONTAINERS
# ==========================================================================

def checar_containers():
    """Retorna lista de containers exigidos que NÃO estão de pé."""
    import subprocess
    try:
        out = subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                             capture_output=True, text=True, timeout=30)
        vivos = set(out.stdout.split())
        return [c for c in CONTAINERS if c not in vivos]
    except Exception as e:
        log("ERROR", f"não consegui listar containers: {e}")
        return []


def subir_containers(faltando):
    import subprocess
    for c in faltando:
        log("INFO", f"subindo container {c}")
        try:
            subprocess.run(["docker", "start", c], capture_output=True, timeout=60)
        except Exception as e:
            log("ERROR", f"falha ao subir {c}: {e}")


def checar_uma_vez():
    """Retorna True se instância está OK, False se caiu ou erro."""
    try:
        r = requests.get(f"{API_URL}/instance/connectionState/{INSTANCE}",
                         headers={"apikey": API_KEY}, timeout=8)
    except requests.exceptions.ConnectionError:
        log("ERROR", "Evolution API não responde (:8080). Docker parado?")
        notificar("⚠️ Evolution offline",
                  "Evolution API não responde em :8080. Verifique o container evolution_11gb.")
        return False
    except Exception as e:
        log("ERROR", f"erro ao consultar state: {e}")
        return False

    if r.status_code == 404:
        log("ERROR", f"Instância {INSTANCE} não existe.")
        notificar("⚠️ B.I.A. sumiu",
                  f"Instância {INSTANCE} não existe na Evolution. Recriar via docker/API.")
        return False

    if not r.ok:
        log("ERROR", f"HTTP {r.status_code}: {r.text[:200]}")
        return False

    state = r.json().get("instance", {}).get("state")
    if state == "open":
        # heartbeat silencioso — só loga OK a cada HB_QUIET_MIN minutos
        agora = datetime.now()
        ultimo_ok = None
        if HB_FILE.exists():
            try:
                ultimo_ok = datetime.fromisoformat(HB_FILE.read_text().strip())
            except Exception:
                pass
        if not ultimo_ok or (agora - ultimo_ok) >= timedelta(minutes=HB_QUIET_MIN):
            log("OK", "instância open (heartbeat)")
            HB_FILE.parent.mkdir(parents=True, exist_ok=True)
            HB_FILE.write_text(agora.isoformat())
        # saiu do 'connecting': zera o carimbo de tolerância
        if CONNECTING_STAMP.exists():
            CONNECTING_STAMP.unlink(missing_ok=True)
        # Pareou: a escada de cooldown do QR volta ao primeiro degrau.
        if QR_STAMP.exists() or QR_RODADAS.exists():
            _zerar_escada_qr()
            log("INFO", "instância pareada — escada de cooldown do QR zerada")
        return True

    # 'connecting' logo após boot/restart é transitório e costuma resolver
    # sozinho. Só tratamos como queda depois de CONNECTING_GRACA_MIN.
    if state == "connecting":
        faz = _agora_menos(CONNECTING_STAMP)
        if faz is None:
            _carimbar(CONNECTING_STAMP)
            log("INFO", "instância em 'connecting' — aguardando (transitório?)")
            return False
        if faz < CONNECTING_GRACA_MIN:
            log("INFO", f"'connecting' há {faz:.0f}min — dentro da tolerância")
            return False
        log("ALERTA", f"'connecting' há {faz:.0f}min — tratando como queda")
    else:
        log("ALERTA", f"instância state={state!r} — B.I.A. fora do ar")

    # Cooldown do QR: gerar QR a cada 5min durante uma queda é justamente o
    # comportamento que o WhatsApp penaliza (soft-ban). A espera cresce a cada
    # rodada sem pareamento (QR_COOLDOWNS_MIN).
    rodadas = _rodadas_qr()
    espera = _cooldown_qr(rodadas)
    desde_qr = _agora_menos(QR_STAMP)

    if desde_qr is not None and desde_qr < espera:
        falta = espera - desde_qr
        log("INFO", f"QR gerado há {desde_qr:.0f}min (rodada {rodadas}) — "
                    f"próxima em {falta:.0f}min")
        notificar("🚨 B.I.A. fora do ar",
                  f"State: {state}. Já foram {rodadas} rodada(s) de QR sem "
                  f"pareamento; a próxima automática sai em {falta:.0f}min.\n"
                  f"Se você está com o celular em mãos agora, não espere: rode\n"
                  f"    python {Path(__file__).name} --qr-agora\n"
                  f"que ele puxa um QR novo na hora. O PNG salvo em "
                  f"{QR_FILE.name} expira em segundos e a esta altura já morreu.")
        return False

    ok_qr = puxar_qr_fresh()
    if ok_qr:
        _carimbar(QR_STAMP)
        _gravar_rodadas_qr(rodadas + 1)
    proxima = _cooldown_qr(rodadas + 1)
    corpo = (
        f"State: {state}. "
        + (f"QR fresh em {QR_FILE.name} — abre pra parear (expira em segundos). "
           f"Próxima rodada automática só em {proxima}min." if ok_qr
           else "Não consegui puxar QR novo. Ver log.")
    )
    notificar("🚨 B.I.A. caiu", corpo)
    return False


def checar_tudo():
    """Verifica os QUATRO elos e corrige o que der pra corrigir sozinho.

    Ordem importa: containers primeiro (o resto depende deles), depois o
    webapp (as tools), por último a sessão do WhatsApp — que é a única que
    exige ação humana (parear).
    """
    problemas = []

    # 1) containers
    faltando = checar_containers()
    if faltando:
        log("ALERTA", f"containers fora do ar: {', '.join(faltando)}")
        subir_containers(faltando)
        ainda = checar_containers()
        if ainda:
            problemas.append(f"containers parados: {', '.join(ainda)}")
            notificar("🚨 Containers fora do ar", ", ".join(ainda))
        else:
            log("OK", "containers religados pelo watchdog")

    # 2) webapp — a falha silenciosa
    if not checar_webapp():
        log("ALERTA", "webapp :8000 fora do ar — as 20 tools estão mortas")
        if subir_webapp():
            log("OK", "webapp religado pelo watchdog")
            notificar("⚠️ Webapp caiu e foi religado",
                      "O webapp :8000 estava fora; subi de novo. Ver log.")
        else:
            problemas.append("webapp :8000 não sobe")
            notificar("🚨 Webapp fora do ar",
                      "A B.I.A. responde mas erra TODA consulta. Ver webapp_*_err.log.")

    # 3) frescor dos dados — o sistema responde, mas o que ele responde vale?
    velhos = checar_frescor()
    if velhos is None:
        problemas.append("não consegui verificar o frescor dos dados")
    elif velhos:
        resumo = ", ".join(f"{d} {h:.0f}h" for d, h, _ in velhos)
        log("ALERTA", f"dados desatualizados: {resumo}")
        problemas.append(f"dados desatualizados: {resumo}")
        detalhe = "\n".join(
            f"  - {d}: {h:.0f}h sem atualizar (limite {lim}h)"
            for d, h, lim in velhos
        )
        notificar("⚠️ Dados desatualizados",
                  "A B.I.A. está no ar e vai responder normalmente, mas com "
                  "dado velho nestes domínios:\n\n" + detalhe +
                  "\n\nEla informa o frescor na resposta; quem perguntar "
                  "pode não reparar.")

    # 4) tarefas de ETL que rodaram e falharam
    falhas_etl = checar_tarefas_etl()
    if falhas_etl:
        resumo = ", ".join(f"{t} (código {c})" for t, c in falhas_etl)
        log("ALERTA", f"ETL com falha: {resumo}")
        problemas.append(f"ETL com falha: {resumo}")
        detalhe = "\n".join(
            f"  - {t}: código {c} — alimenta {TAREFAS_ETL[t]}"
            for t, c in falhas_etl
        )
        notificar("⚠️ ETL falhando",
                  "Tarefa(s) de carga terminaram com erro:\n\n" + detalhe +
                  "\n\nCódigo 2 costuma ser falha parcial: parte dos "
                  "domínios carregou e parte não. Ver o log da tarefa em "
                  f"{LOG_FILE.parent}.")

    # 5) sessão WhatsApp
    if not checar_uma_vez():
        problemas.append("sessão WhatsApp indisponível")

    if not problemas:
        # Fecha por e-mail o que estava aberto. Sem isto quem recebeu o alerta
        # não tem como saber que acabou, a não ser vindo olhar a máquina.
        avisar_normalizado()
        return True
    log("ERROR", "pendências: " + " | ".join(problemas))
    return False


def rodada_completa():
    """Uma passagem pelos quatro elos, seguida do pulso para o vigia externo.

    O pulso diz "o watchdog rodou", não "a B.I.A. está bem": saúde é assunto
    do e-mail. Misturar os dois deixaria o check vermelho durante toda uma
    queda longa, sem dizer o quê, e duplicaria cada alerta.

    A exceção é o e-mail ter falhado: aí o canal que contaria o problema está
    quebrado, e o pulso vira /fail para o vigia externo cobrir o buraco.

    Se esta função levantar, nenhum pulso sai e o vigia reclama — que é o
    comportamento certo para um watchdog que quebrou.
    """
    ok = checar_tudo()
    pulsar(sucesso=not _ALERTA_NAO_SAIU)
    return ok


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--loop":
        intervalo = int(sys.argv[2]) if len(sys.argv) > 2 else 300
        log("INFO", f"modo loop, intervalo={intervalo}s")
        while True:
            rodada_completa()
            time.sleep(intervalo)
    elif len(sys.argv) > 1 and sys.argv[1] == "--qr-agora":
        # Escada longa e QR que expira em segundos se combinam mal: quando
        # alguém finalmente chega com o celular, o PNG salvo está morto e a
        # próxima rodada pode estar a horas. Este atalho é a saída — a
        # presença de alguém para escanear é justamente a condição que a
        # escada estava esperando, então ela também volta ao primeiro degrau.
        ok = puxar_qr_fresh()
        if ok:
            _carimbar(QR_STAMP)
            _gravar_rodadas_qr(0)
            log("INFO", f"QR forçado à mão — escada zerada, QR em {QR_FILE}")
        sys.exit(0 if ok else 1)
    elif len(sys.argv) > 1 and sys.argv[1] == "--so-whatsapp":
        # comportamento antigo, só a sessão
        sys.exit(0 if checar_uma_vez() else 1)
    else:
        sys.exit(0 if rodada_completa() else 1)


if __name__ == "__main__":
    main()
