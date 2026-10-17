"""The words in transactional e-mail, in the three languages the product ships.

Kept apart from `email_service` so wording can change without touching how mail
is sent, and so each message can be tested as text. A language the product does
not ship falls back to English, as the interface does.
"""
from __future__ import annotations

from typing import Optional

from app.services.email_service import clean_header

SUPPORTED = ("en", "pt-BR", "es")


def resolve_lang(language: Optional[str]) -> str:
    tag = (language or "").lower()
    if tag.startswith("pt"):
        return "pt-BR"
    if tag.startswith("es"):
        return "es"
    return "en"


_RESET = {
    "en": (
        "Reset your SyncroFin password",
        "Someone asked to reset the password for this SyncroFin account.\n\n"
        "Choose a new password here (the link works once and expires in {minutes} minutes):\n\n"
        "{link}\n\n"
        "If it was not you, ignore this message: your password stays as it is.\n",
    ),
    "pt-BR": (
        "Redefinir sua senha do SyncroFin",
        "Alguém pediu para redefinir a senha desta conta do SyncroFin.\n\n"
        "Escolha uma nova senha aqui (o link funciona uma vez e expira em {minutes} minutos):\n\n"
        "{link}\n\n"
        "Se não foi você, ignore esta mensagem: sua senha continua a mesma.\n",
    ),
    "es": (
        "Restablecer tu contraseña de SyncroFin",
        "Alguien solicitó restablecer la contraseña de esta cuenta de SyncroFin.\n\n"
        "Elige una contraseña nueva aquí (el enlace funciona una sola vez y caduca en {minutes} minutos):\n\n"
        "{link}\n\n"
        "Si no fuiste tú, ignora este mensaje: tu contraseña no cambia.\n",
    ),
}

_INVITE_NEW = {
    "en": (
        "{inviter} invited you to {workspace} on SyncroFin",
        "{inviter} added you to the workspace \"{workspace}\" on SyncroFin as {role}.\n\n"
        "An account was created for this e-mail address. Set your password to sign in "
        "(the link works once and expires in {days} days):\n\n"
        "{link}\n",
    ),
    "pt-BR": (
        "{inviter} convidou você para {workspace} no SyncroFin",
        "{inviter} adicionou você ao workspace \"{workspace}\" no SyncroFin como {role}.\n\n"
        "Foi criada uma conta para este e-mail. Defina sua senha para entrar "
        "(o link funciona uma vez e expira em {days} dias):\n\n"
        "{link}\n",
    ),
    "es": (
        "{inviter} te invitó a {workspace} en SyncroFin",
        "{inviter} te añadió al workspace \"{workspace}\" en SyncroFin como {role}.\n\n"
        "Se creó una cuenta para este correo. Define tu contraseña para entrar "
        "(el enlace funciona una sola vez y caduca en {days} días):\n\n"
        "{link}\n",
    ),
}

_INVITE_EXISTING = {
    "en": (
        "{inviter} added you to {workspace} on SyncroFin",
        "{inviter} added you to the workspace \"{workspace}\" on SyncroFin as {role}.\n\n"
        "Sign in with your usual account and switch workspace from the menu:\n\n{link}\n",
    ),
    "pt-BR": (
        "{inviter} adicionou você a {workspace} no SyncroFin",
        "{inviter} adicionou você ao workspace \"{workspace}\" no SyncroFin como {role}.\n\n"
        "Entre com a sua conta de sempre e troque de workspace pelo menu:\n\n{link}\n",
    ),
    "es": (
        "{inviter} te añadió a {workspace} en SyncroFin",
        "{inviter} te añadió al workspace \"{workspace}\" en SyncroFin como {role}.\n\n"
        "Entra con tu cuenta de siempre y cambia de workspace desde el menú:\n\n{link}\n",
    ),
}

_ROLE = {
    "en": {"owner": "owner", "editor": "editor", "viewer": "viewer (read-only)"},
    "pt-BR": {"owner": "proprietário", "editor": "editor", "viewer": "leitor (somente leitura)"},
    "es": {"owner": "propietario", "editor": "editor", "viewer": "lector (solo lectura)"},
}


def password_reset(language: Optional[str], link: str, minutes: int) -> tuple[str, str]:
    subject, body = _RESET[resolve_lang(language)]
    return subject, body.format(link=link, minutes=minutes)


def workspace_invite(
    language: Optional[str],
    *,
    inviter: str,
    workspace: str,
    role: str,
    link: str,
    new_account: bool,
    days: int = 7,
) -> tuple[str, str]:
    lang = resolve_lang(language)
    subject, body = (_INVITE_NEW if new_account else _INVITE_EXISTING)[lang]
    values = {
        # Free text from users goes into a subject line: collapse it to one line.
        "inviter": clean_header(inviter, 80),
        "workspace": clean_header(workspace, 80),
        "role": _ROLE[lang].get(role, role),
        "link": link,
        "days": days,
    }
    return subject.format(**values), body.format(**values)


_LOCKED = {
    "en": (
        "Your SyncroFin account was locked for a while",
        "There were {attempts} failed sign-in attempts (wrong password or verification code) on this SyncroFin account, so sign-in is paused for "
        "{minutes} minutes.\n\n"
        "If it was you, wait and try again, or choose a new password (this also lifts the pause):\n\n{link}\n\n"
        "If it was not you, someone is guessing your password: choose a new one, and turn on two-step "
        "verification. Nobody got in with these attempts.\n",
    ),
    "pt-BR": (
        "Sua conta do SyncroFin foi bloqueada por um tempo",
        "Houve {attempts} tentativas de entrada malsucedidas (senha ou código de verificação errado) nesta conta do SyncroFin, por isso a entrada "
        "ficou suspensa por {minutes} minutos.\n\n"
        "Se foi você, aguarde e tente de novo, ou escolha uma nova senha (isso também encerra a suspensão):\n\n{link}\n\n"
        "Se não foi você, alguém está tentando adivinhar a sua senha: escolha uma nova e ative a verificação "
        "em duas etapas. Ninguém entrou com essas tentativas.\n",
    ),
    "es": (
        "Tu cuenta de SyncroFin fue bloqueada por un tiempo",
        "Hubo {attempts} intentos de entrada fallidos (contraseña o código de verificación incorrecto) en esta cuenta de SyncroFin, por eso el "
        "acceso quedó suspendido durante {minutes} minutos.\n\n"
        "Si fuiste tú, espera e inténtalo de nuevo, o elige una contraseña nueva (esto también levanta la "
        "suspensión):\n\n{link}\n\n"
        "Si no fuiste tú, alguien está intentando adivinar tu contraseña: elige una nueva y activa la "
        "verificación en dos pasos. Nadie entró con esos intentos.\n",
    ),
}

_NEW_DEVICE = {
    "en": (
        "New sign-in to your SyncroFin account",
        "Your SyncroFin account was just signed in to from a device we had not seen before.\n\n"
        "Device: {device}\nAddress: {ip}\nWhen: {when} (UTC)\n\n"
        "If it was you, nothing to do. If not, change your password now and end the session from "
        "Account > Sessions:\n\n{link}\n",
    ),
    "pt-BR": (
        "Novo acesso à sua conta do SyncroFin",
        "Sua conta do SyncroFin acabou de ser acessada por um dispositivo que ainda não tínhamos visto.\n\n"
        "Dispositivo: {device}\nEndereço: {ip}\nQuando: {when} (UTC)\n\n"
        "Se foi você, não precisa fazer nada. Se não foi, troque a senha agora e encerre a sessão em "
        "Conta > Sessões:\n\n{link}\n",
    ),
    "es": (
        "Nuevo acceso a tu cuenta de SyncroFin",
        "Acaban de acceder a tu cuenta de SyncroFin desde un dispositivo que no habíamos visto.\n\n"
        "Dispositivo: {device}\nDirección: {ip}\nCuándo: {when} (UTC)\n\n"
        "Si fuiste tú, no tienes que hacer nada. Si no, cambia la contraseña ahora y cierra la sesión en "
        "Cuenta > Sesiones:\n\n{link}\n",
    ),
}

_ERASURE_CONFIRMED = {
    "en": (
        "Your SyncroFin account has been deleted",
        "As requested (protocol {protocol}), your SyncroFin account and its data were deleted on "
        "{when} (UTC).\n\nIf you did not request this, it is too late to recover the account — "
        "contact support immediately so we can investigate.\n",
    ),
    "pt-BR": (
        "Sua conta do SyncroFin foi excluída",
        "Conforme solicitado (protocolo {protocol}), sua conta do SyncroFin e seus dados foram "
        "excluídos em {when} (UTC).\n\nSe você não pediu isso, já não é possível recuperar a conta — "
        "entre em contato com o suporte imediatamente para que possamos investigar.\n",
    ),
    "es": (
        "Tu cuenta de SyncroFin fue eliminada",
        "Según lo solicitado (protocolo {protocol}), tu cuenta de SyncroFin y sus datos fueron "
        "eliminados el {when} (UTC).\n\nSi no lo pediste, ya no es posible recuperar la cuenta — "
        "contacta al soporte de inmediato para que podamos investigar.\n",
    ),
}


def account_locked(language: Optional[str], *, attempts: int, minutes: int, link: str) -> tuple[str, str]:
    subject, body = _LOCKED[resolve_lang(language)]
    return subject, body.format(attempts=attempts, minutes=minutes, link=link)


def new_device_login(
    language: Optional[str], *, device: str, ip: Optional[str], when: str, link: str
) -> tuple[str, str]:
    subject, body = _NEW_DEVICE[resolve_lang(language)]
    return subject, body.format(
        device=clean_header(device, 80), ip=clean_header(ip or "?", 60), when=when, link=link
    )


def erasure_confirmed(language: Optional[str], *, protocol: str, when: str) -> tuple[str, str]:
    subject, body = _ERASURE_CONFIRMED[resolve_lang(language)]
    return subject, body.format(protocol=protocol, when=when)
