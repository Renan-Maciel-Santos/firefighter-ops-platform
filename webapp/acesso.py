"""
Regra de acesso do painel — o único lugar onde ela existe.

Antes de 09/09/2026 cada router carregava a própria lista (`ALLOWED_PERFIS`) e
o frontend carregava outra (`PERFIL_ACCESS`, em JavaScript). Duas fontes para
a mesma decisão divergem em silêncio: alguém acrescenta uma aba, esconde o
menu, e esquece o endpoint — que segue respondendo a quem souber a URL.

Agora a regra mora aqui, o backend a aplica e o frontend a RECEBE em
/auth/me. Esconder o menu deixou de ser a proteção; virou consequência dela.

MODELO
    admin    tudo, mais a gestão de usuários. Só o RE 900003.
    oficial  todas as abas, menos a gestão de usuários.
    praca    as abas da seção escolhida no cadastro — ou, se o admin
             ajustou na aba Permissões, as que ele marcou.

SJD só aparece para oficial, admin e praça da seção SJD, em qualquer caso.

Praça de SGB não recebe login — 421 dos 501 militares. O canal deles é a
B.I.A. no WhatsApp.
"""

# Abas do painel. A chave é a mesma usada no `data-tab` do dashboard.html e no
# `showTab()`; se divergir, o menu aparece e o dado não vem.
ABAS = (
    "ppmq", "viaturas", "pessoal", "afastamentos", "consulta_militar", "saude", "taf", "mapa",
    "ocorrencias", "auditoria_cobom", "eap", "elogios", "realocacao", "uge", "fin_indicadores", "fin_lancamento", "sjd",
    "usuarios", "permissoes",
)

# Só o admin gerencia acesso. Oficial vê todo o resto.
ABAS_SO_ADMIN = ("usuarios", "permissoes")

# Abas que só o praça da própria seção pode receber — nem o admin consegue
# dá-las a praça de outra seção pela aba Permissões. Pedido do Cmt em
# 09/11/2026: processo disciplinar é só para oficiais e para o pessoal do SJD.
ABAS_RESTRITAS_A_SECAO = {"sjd": "SJD"}

# O que pode ser escolhido para um praça na aba Permissões.
ABAS_ATRIBUIVEIS = tuple(a for a in ABAS if a not in ABAS_SO_ADMIN)

# Seção -> abas que o praça daquela seção enxerga.
#
# Este mapa é a parte organizacional da regra, e é o que muda com mais
# frequência. Está isolado de propósito: acrescentar uma seção ou mover uma
# aba é editar uma linha aqui, sem tocar em router nem em frontend.
#
# SAT fica vazia porque a aba dela ainda não existe ("Em breve" no menu).
SECAO_ABAS = {
    "B/1 e B/5":           ("pessoal", "afastamentos", "consulta_militar", "realocacao", "saude", "taf", "elogios"),
    "B/3, PJMD e Motomec": ("mapa", "ocorrencias", "auditoria_cobom", "eap", "ppmq"),
    "B/4":                 ("viaturas",),
    "St UGE":              ("uge", "fin_indicadores", "fin_lancamento"),
    "COBOM":               ("mapa", "ocorrencias"),
    "SJD":                 ("sjd",),
    "SAT":                 (),
}

SECOES = tuple(SECAO_ABAS)
PERFIS = ("admin", "oficial", "praca")


def aba_permitida_ao_praca(aba: str, secao: str | None) -> bool:
    exige = ABAS_RESTRITAS_A_SECAO.get(aba)
    return aba in ABAS_ATRIBUIVEIS and (exige is None or exige == secao)


def abas_do_usuario(perfil: str, secao: str | None,
                    personalizadas=None) -> tuple[str, ...]:
    """Abas que este usuário pode ver. Fonte única, usada pelos dois lados.

    `personalizadas` é app.usuarios.abas_personalizadas: quando não é NULL,
    substitui o padrão da seção para o praça. Oficial e admin a ignoram.
    """
    if perfil == "admin":
        return ABAS
    if perfil == "oficial":
        return tuple(a for a in ABAS if a not in ABAS_SO_ADMIN)
    if perfil == "praca":
        # Praça sem seção não vê nada. É estado inválido — o cadastro exige
        # seção —, e o que ele NÃO pode virar é acesso amplo por omissão.
        if not secao:
            return ()
        escolhidas = SECAO_ABAS.get(secao, ()) if personalizadas is None else personalizadas
        # Filtra mesmo o padrão da seção: a restrição do SJD vale sempre, e
        # uma aba que deixou de existir não pode virar acesso.
        return tuple(a for a in ABAS if a in escolhidas and aba_permitida_ao_praca(a, secao))
    # Perfil desconhecido (os três antigos, de antes da migração) não vê nada.
    # Negar por omissão: um perfil que ninguém reconhece não pode ganhar acesso
    # só porque o `if` não previu o caso.
    return ()


def pode_ver(usuario, aba: str) -> bool:
    return aba in abas_do_usuario(usuario.perfil.value,
                                  getattr(usuario, "secao", None),
                                  getattr(usuario, "abas_personalizadas", None))
