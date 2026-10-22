"""
Gestão de usuários do painel — cadastro, listagem, ativação e reset de senha.

Uso:
    python gerenciar_usuarios.py listar
    python gerenciar_usuarios.py criar <matricula> "<Nome>" <perfil> [--secao "B/4"] [--apelido "Cap Fulano"]
    python gerenciar_usuarios.py resetar <matricula>
    python gerenciar_usuarios.py desativar <matricula>
    python gerenciar_usuarios.py reativar <matricula>

Perfis: admin | oficial | praca (praça exige --secao; ver acesso.py)

POR QUE ESTE SCRIPT EXISTE
Até 09/09/2026 havia UM usuário no sistema ("Administrador") e nenhuma forma
de criar outro. Compartilhar o painel assim significaria todo mundo entrando
na mesma conta, sem rastro de quem consultou o quê — num sistema com dados de
pessoal, saúde e disciplina.

SOBRE SENHAS
Não existe, e não pode existir, lista de senhas. O banco guarda hash bcrypt,
que é irreversível: nem o administrador nem quem tiver o banco lê a senha de
alguém. O cadastro gera uma provisória, mostra UMA vez aqui no terminal, e o
usuário é obrigado a trocá-la no primeiro acesso (`deve_trocar_senha`).

Se alguém esquecer a senha, o caminho é `resetar` — que gera outra provisória
—, nunca "recuperar". Entregue a provisória pessoalmente ou por canal que não
fique registrado; ela vale para um acesso só.

DESATIVAR, NÃO APAGAR
`desativar` desliga o acesso mantendo o registro. Apagar o usuário perderia a
referência de quem fez o quê. O login já respeita a coluna `ativo`.
"""

import argparse
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from database import SessionLocal  # noqa: E402
from models import Usuario  # noqa: E402
from routers.auth import hash_password  # noqa: E402

from acesso import PERFIS, SECOES, abas_do_usuario  # noqa: E402

PERFIL_DESCRICAO = {
    "admin":   "tudo, mais a gestão de usuários",
    "oficial": "todas as abas, menos usuários",
    "praca":   "só as abas da seção",
}


def senha_provisoria():
    # token_urlsafe(9) dá ~12 caracteres: forte o bastante e ainda digitável
    # uma vez. Ela existe para ser trocada no primeiro acesso, não para durar.
    return secrets.token_urlsafe(9)


def cmd_listar(db, _):
    linhas = db.query(Usuario).order_by(Usuario.id).all()
    if not linhas:
        print("nenhum usuário cadastrado")
        return
    print(f"{'MATRÍCULA':<12}{'NOME':<32}{'PERFIL':<28}{'ATIVO':<7}{'TROCA SENHA'}")
    print("-" * 94)
    for u in linhas:
        rotulo = u.perfil.value + (f" ({u.secao})" if u.secao else "")
        print(f"{u.matricula:<12}{u.nome[:31]:<32}{rotulo:<28}"
              f"{('sim' if u.ativo else 'NÃO'):<7}"
              f"{'pendente' if u.deve_trocar_senha else ''}")
    print(f"\n{len(linhas)} usuário(s).")


def cmd_criar(db, args):
    if args.perfil not in PERFIS:
        print(f"[ERRO] perfil inválido: {args.perfil}. Use: {', '.join(PERFIS)}",
              file=sys.stderr)
        raise SystemExit(1)

    if db.query(Usuario).filter(Usuario.matricula == args.matricula).first():
        print(f"[ERRO] matrícula {args.matricula} já cadastrada. "
              f"Para trocar a senha dela, use `resetar`.", file=sys.stderr)
        raise SystemExit(1)

    # Praça sem seção não veria aba nenhuma. Barrar aqui, em vez de deixar
    # criar uma conta que entra e não mostra nada.
    secao = args.secao
    if args.perfil == "praca" and not secao:
        print(f"[ERRO] praça exige --secao. Opções: {', '.join(SECOES)}", file=sys.stderr)
        raise SystemExit(1)
    if args.perfil != "praca":
        secao = None

    senha = senha_provisoria()
    db.add(Usuario(
        nome=args.nome,
        matricula=args.matricula,
        senha_hash=hash_password(senha),
        perfil=args.perfil,
        secao=secao,
        ativo=True,
        apelido_assinatura=args.apelido,
        deve_trocar_senha=True,
    ))
    db.commit()

    print(f"\n[OK] {args.nome} cadastrado.")
    print(f"     matrícula : {args.matricula}")
    print(f"     perfil    : {args.perfil} ({PERFIL_DESCRICAO[args.perfil]})")
    if secao:
        print(f"     seção     : {secao}")
    print(f"     abas      : {', '.join(abas_do_usuario(args.perfil, secao)) or '(nenhuma)'}")
    print(f"\n     SENHA PROVISÓRIA: {senha}")
    print("\n     Esta senha aparece UMA vez. Ela não fica em lugar nenhum —")
    print("     o banco guarda só o hash. Entregue pessoalmente; o usuário é")
    print("     obrigado a trocá-la no primeiro acesso.")


def cmd_resetar(db, args):
    u = _achar(db, args.matricula)
    senha = senha_provisoria()
    u.senha_hash = hash_password(senha)
    u.deve_trocar_senha = True
    db.commit()
    print(f"\n[OK] senha de {u.nome} redefinida.")
    print(f"\n     SENHA PROVISÓRIA: {senha}")
    print("\n     Aparece UMA vez. Troca obrigatória no próximo acesso.")


def cmd_desativar(db, args):
    u = _achar(db, args.matricula)
    if not u.ativo:
        print(f"[=] {u.nome} já estava desativado.")
        return

    # Trava de lockout. Aqui ela importa mais que na API: pelo painel, quem
    # desativa é obrigatoriamente um `admin` ativo, então sempre sobra ele.
    # Pelo terminal não há esse piso — dá para desativar o último e deixar o
    # sistema sem ninguém que gerencie acessos nem entre no painel.
    if u.perfil.value == "admin":
        outros = (db.query(Usuario)
                    .filter(Usuario.perfil == "admin",
                            Usuario.ativo == True,  # noqa: E712
                            Usuario.id != u.id)
                    .count())
        if outros == 0:
            print(f"[ERRO] {u.nome} é o ÚLTIMO administrador ativo.",
                  file=sys.stderr)
            print("       Desativá-lo deixaria o sistema sem quem gerencia acessos.",
                  file=sys.stderr)
            print("       Cadastre outro `admin` antes.", file=sys.stderr)
            raise SystemExit(1)

    u.ativo = False
    db.commit()
    print(f"[OK] {u.nome} desativado. O registro fica, o acesso não.")


def cmd_reativar(db, args):
    u = _achar(db, args.matricula)
    u.ativo = True
    db.commit()
    print(f"[OK] {u.nome} reativado.")


def _achar(db, matricula):
    u = db.query(Usuario).filter(Usuario.matricula == matricula).first()
    if not u:
        print(f"[ERRO] matrícula {matricula} não encontrada.", file=sys.stderr)
        raise SystemExit(1)
    return u


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("listar")

    c = sub.add_parser("criar")
    c.add_argument("matricula")
    c.add_argument("nome")
    c.add_argument("perfil", choices=PERFIS)
    c.add_argument("--secao", default=None, choices=SECOES,
                   help="obrigatório para praça: qual seção ele enxerga")
    c.add_argument("--apelido", default=None,
                   help="forma de tratamento nas assinaturas, ex: 'Cap Silva'")

    for nome in ("resetar", "desativar", "reativar"):
        s = sub.add_parser(nome)
        s.add_argument("matricula")

    args = ap.parse_args()
    acoes = {
        "listar": cmd_listar, "criar": cmd_criar, "resetar": cmd_resetar,
        "desativar": cmd_desativar, "reativar": cmd_reativar,
    }

    db = SessionLocal()
    try:
        acoes[args.cmd](db, args)
    finally:
        db.close()


if __name__ == "__main__":
    main()
