"""What a password has to be, decided by the server.

Until now the only rule lived in the browser (eight characters) and in two request schemas, so a call to the
API could set any password at all. This is the one rule every way of setting a password goes through: sign-up,
the reset link, a change from the account menu, an administrator setting one, the invitation of a new person.

The rules are the ones that matter and that a person can understand:

- a minimum length (`PASSWORD_MIN_LENGTH`, ten by default; length does most of the work);
- not one of the passwords everybody tries first, in English or in Portuguese;
- not made of the e-mail address it protects;
- not a single repeated character or an obvious run (`aaaaaaaaaa`, `1234567890`, `abcdefghij`).

There is deliberately no "one capital, one digit, one symbol" rule: it makes people write `Senha@123`, which is
on every list, instead of a long phrase that is easy to remember and hard to guess.

Each failure is a stable **code**, not a sentence, so the interface can say it in the person's language.
"""
from __future__ import annotations

import re

from app.core.config import get_settings

MAX_LENGTH = 128

TOO_SHORT = "PASSWORD_TOO_SHORT"
TOO_LONG = "PASSWORD_TOO_LONG"
TOO_COMMON = "PASSWORD_TOO_COMMON"
HAS_EMAIL = "PASSWORD_HAS_EMAIL"
TOO_SIMPLE = "PASSWORD_TOO_SIMPLE"

# The ones everybody tries first: the well-known lists of leaked passwords, plus what Brazilian
# users reach for (a team, a city, "senha", "mudar", "brasil"). Compared lower-cased, and again
# with trailing digits and symbols taken off, so `Senha123!` is caught as `senha`.
_COMMON = frozenset(
    """
    123456 1234567 12345678 123456789 1234567890 0123456789 987654321 9876543210 111111 000000 121212 112233
    123123 123321 654321 666666 696969 7777777 555555 222222 333333 444444 888888 999999 102030 010203 147258369
    password passw0rd p@ssw0rd p@ssword pass qwerty qwertyuiop qwerty123 qwertyui asdfgh asdfghjkl asdfghjk zxcvbn
    zxcvbnm 1q2w3e4r 1q2w3e 1qaz2wsx qazwsx q1w2e3r4 abc123 abcd1234 abcdef abcdefg abcdefgh abcdefghi abcdefghij
    letmein welcome admin administrator root toor login master monkey dragon shadow sunshine princess football
    baseball superman batman iloveyou trustno1 whatever freedom hello hello123 secret changeme change-me default
    guest user test testing test123 teste teste123 testando demo temp temporary
    senha senha123 senha1234 senha12345 minhasenha minhasenha123 mudar mudar123 mude123 trocar trocar123
    brasil brasil123 brasileiro brasileira brazil brazil123 saopaulo riodejaneiro curitiba
    flamengo corinthians palmeiras santos gremio internacional cruzeiro vasco botafogo fluminense saopaulofc
    amor amor123 eusouofodao meuamor gostosa gostoso linda lindo deus deus123 jesus jesus123 fabiano gabriel
    empresa empresa123 financeiro financeiro123 contabil contabilidade dinheiro dinheiro123 syncrofin
    syncrofin123 financebr financebr123 securo
    """.split()
)

_RUNS = (
    "abcdefghijklmnopqrstuvwxyz",
    "0123456789012345",
    "9876543210987654",
    "qwertyuiopasdfghjklzxcvbnm",
    "1qaz2wsx3edc4rfv5tgb",
)


def minimum_length() -> int:
    return max(8, get_settings().password_min_length)


def _stripped(value: str) -> str:
    """Lower-cased, with trailing digits and symbols removed: `Senha123!` -> `senha`."""
    return re.sub(r"[\d\W_]+$", "", value.lower())


def _is_run(value: str) -> bool:
    lowered = value.lower()
    return any(lowered in run for run in _RUNS) and len(lowered) >= 6


def _local_part(email: str | None) -> str:
    return (email or "").split("@", 1)[0].lower()


def problems(password: str, *, email: str | None = None) -> list[str]:
    """Every rule the password breaks (empty means it is acceptable), as stable codes."""
    found: list[str] = []
    if len(password) < minimum_length():
        found.append(TOO_SHORT)
    if len(password) > MAX_LENGTH:
        found.append(TOO_LONG)
    lowered = password.lower()
    if lowered in _COMMON or _stripped(password) in _COMMON:
        found.append(TOO_COMMON)
    local = _local_part(email)
    squeezed = re.sub(r"[.\-_]", "", lowered)
    if len(local) >= 4 and (local in lowered or re.sub(r"[.\-_]", "", local) in squeezed):
        found.append(HAS_EMAIL)
    if len(set(password)) <= 2 or _is_run(password):
        found.append(TOO_SIMPLE)
    return found


class PasswordRejected(ValueError):
    """A password the policy refuses, with the code that says why."""

    def __init__(self, reason: str) -> None:
        super().__init__(describe(reason))
        self.reason = reason


def http_detail(reason: str) -> dict[str, str]:
    """The body of a 400 for a refused password: the same shape fastapi-users gives at sign-up."""
    return {"code": "INVALID_PASSWORD", "reason": reason}


def first_problem(password: str, *, email: str | None = None) -> str | None:
    found = problems(password, email=email)
    return found[0] if found else None


def describe(code: str) -> str:
    """A plain-English sentence for logs and API clients; the interface has its own translations."""
    return {
        TOO_SHORT: f"The password must have at least {minimum_length()} characters",
        TOO_LONG: f"The password must have at most {MAX_LENGTH} characters",
        TOO_COMMON: "That password is too common: pick something less guessable, such as a few words",
        HAS_EMAIL: "The password must not contain your e-mail address",
        TOO_SIMPLE: "The password is too simple: it repeats one character or is an obvious sequence",
    }.get(code, code)
