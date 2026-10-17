from datetime import date

from pydantic import BaseModel, Field, SecretStr


class BackupRequest(BaseModel):
    """Options for a workspace backup.

    `password` is optional: omitted (or null) produces the plain zip. A
    SecretStr so the value never reaches a log line or a validation error
    through a repr. The floor is a length, not a character-class rule, since
    those push people towards shorter passwords they can satisfy.
    """

    password: SecretStr | None = Field(default=None, min_length=8, max_length=256)


class AccountantExportRequest(BaseModel):
    """The package for the accountant: a period, and optionally a password.

    Same rule as the backup: the password is a SecretStr with a length floor,
    and rides in a body rather than a query string.
    """

    start: date
    end: date
    password: SecretStr | None = Field(default=None, min_length=8, max_length=256)
