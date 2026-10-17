from functools import lru_cache
from os import getenv
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.secrets_guard import database_password_problem, refusal_message, secret_key_problem

# Use the same environment variable that systemd uses: https://systemd.io/CREDENTIALS/
# If not defined, defaults to docker secrets defaults (https://docs.docker.com/compose/how-tos/use-secrets/)
CREDENTIALS_DIRECTORY: list[Path] = [
    Path(p) for p in getenv("CREDENTIALS_DIRECTORY", "/run/secrets").split(":") if p
]


class Settings(BaseSettings):
    # App
    app_name: str = "SyncroFin"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/syncrofin"

    # Auth
    secret_key: SecretStr = SecretStr("change-me-in-production")
    local_auth_enabled: bool = True
    algorithm: str = "HS256"
    # The access token is short on purpose: what keeps a person signed in is the refresh
    # token (an httpOnly cookie), which the server can revoke. See app/services/session_service.py.
    access_token_expire_minutes: int = 15
    # Second factor. `REQUIRE_MFA=true` makes it mandatory for everyone, at once, and the admin panel
    # cannot lift it. Without it, an administrator can require it from the panel, with a grace period
    # (this many days) before people who have not enrolled are held to enrolling.
    require_mfa: bool = False
    mfa_grace_days: int = 7
    # A session ends after this many days without being refreshed...
    session_idle_days: int = 7
    # ...and, however active it is, after this many days since sign-in.
    session_max_days: int = 30

    # What a password has to be (see app/core/password_policy.py). Never below 8.
    password_min_length: int = 10
    # After this many wrong passwords in a row the account is locked for `login_lock_minutes`,
    # and the lock doubles each time it is triggered again (up to a day) until a sign-in succeeds.
    login_max_attempts: int = 5
    login_lock_minutes: int = 15

    # How long access records (sign-ins, failures, locks, token use) are kept before they are anonymised.
    # The administrator can change it in the panel; this is what applies until they do. 183 to 3650 days.
    access_log_retention_days: int = 183

    # LGPD art. 18: how long a data-subject request stays open before it counts as overdue.
    data_request_deadline_days: int = 15

    # Pluggy
    pluggy_client_id: str = ""
    pluggy_client_secret: SecretStr = SecretStr("")
    # Empty means "derive from FRONTEND_URL" (see BankProvider.redirect_uri).
    # Set explicitly only when the URL registered in the provider dashboard
    # differs from where the app is served.
    pluggy_oauth_redirect_uri: str = ""

    # Enable Banking (European PSD2 banks)
    enable_banking_app_id: str = ""
    enable_banking_private_key: SecretStr = SecretStr("")  # raw PEM; supports \n-escaped envs
    enable_banking_private_key_file: str = ""  # path to PEM file; takes precedence
    enable_banking_api_url: str = "https://api.enablebanking.com"
    enable_banking_oauth_redirect_uri: str = ""  # empty derives from FRONTEND_URL

    # SimpleFIN Bridge (US/intl banks, paste-a-token flow). Off by default.
    # The bridge URL defaults to the beta/sandbox host so users can test with
    # the demo token; flip to https://bridge.simplefin.org for production.
    simplefin_enabled: bool = False
    simplefin_api_url: str = "https://beta-bridge.simplefin.org"

    # Frontend
    frontend_url: str = "http://localhost:5173"
    # Origens CORS separadas por vírgula; vazio = só FRONTEND_URL. "*" é ignorado porque
    # as chamadas usam credenciais (cookie).
    cors_origins: str = ""

    # WebAuthn / passkeys
    webauthn_rp_name: str = "SyncroFin"
    # Empty means the RP ID follows the domain the browser is on, which is what
    # most deployments want. Set it to pin passkeys to one domain (e.g.
    # syncrofin.example.com); requests from other origins are then rejected.
    webauthn_rp_id: str = ""
    # Empty means the expected origin follows the browser. Only set this when the
    # app is reached at exactly one origin and you want it enforced.
    webauthn_origin: str = ""
    webauthn_challenge_ttl_seconds: int = 300

    # Defaults for a new account (see app.core.defaults). Brazilian: this is a Brazilian product; set the
    # DEFAULT_* variables for another market. default_currency is also the fallback when a user has no preference.
    default_currency: str = "BRL"
    default_language: str = "pt-BR"  # en | pt-BR | es
    default_date_format: str = "DD/MM/YYYY"
    default_timezone: str = "America/Sao_Paulo"

    # FX Rates
    openexchangerates_app_id: str = ""
    supported_currencies: str = "USD,EUR,GBP,BRL,CAD,AUD,CHF,ARS,JPY,MXN,INR,SEK,DKK,NOK,PLN,CZK,HUF,RON,CRC,IDR,COP,CLP,DOP,RUB,GTQ,PHP,UAH,NZD,VND,SGD,AZN,TRY,PKR,MDL,AED,THB,EGP,MYR,CNY,SAR,QAR,JMD"  # comma-separated list
    fx_sync_mode: str = "on_demand"  # "on_demand" or "scheduled"

    # Storage
    storage_provider: str = "local"  # "local" or "s3"
    storage_local_path: str = "./data/attachments"
    storage_max_file_size_mb: int = 10
    storage_allowed_extensions: str = "jpg,jpeg,png,webp,gif,heic,pdf,xml"
    storage_max_attachments_per_transaction: int = 10
    # An invoice gathers more paper than a transaction does: the bill, the
    # fiscal document, a receipt, the contract behind it, and a correction
    # of any of them.
    storage_max_attachments_per_invoice: int = 20

    # Fiscal document retention: how many years fiscal documents (NF-e XML/PDF)
    # must be kept locked from deletion. Brazilian law requires 5 years.
    fiscal_retention_years: int = 5

    # S3 Storage (for future use)
    storage_s3_bucket: str = ""
    storage_s3_region: str = ""
    storage_s3_access_key: SecretStr = SecretStr("")
    storage_s3_secret_key: SecretStr = SecretStr("")
    storage_s3_endpoint_url: str = ""  # for S3-compatible services (MinIO, DigitalOcean Spaces)

    # Registration
    registration_enabled: bool = True

    # OIDC login (works with Authentik, Pocket ID, and other standard OIDC providers)
    oidc_enabled: bool = False
    oidc_provider_name: str = "OIDC"
    oidc_discovery_url: str = (
        ""  # e.g. https://auth.example.com/application/o/syncrofin/.well-known/openid-configuration
    )
    oidc_client_id: str = ""
    oidc_client_secret: SecretStr = SecretStr("")
    oidc_redirect_uri: str = ""  # defaults to {FRONTEND_URL}/api/auth/oidc/callback
    oidc_scopes: str = "openid email profile"
    oidc_auto_register: bool = True
    oidc_existing_user_link_mode: str = "disabled"  # disabled|verified_email|email
    oidc_require_verified_email: bool = True
    oidc_sync_roles: bool = False
    oidc_roles_claim: str = "groups"
    oidc_admin_roles: str = ""  # comma-separated provider roles/groups that grant SyncroFin admin
    oidc_workspace_role_map: str = ""  # JSON: {"provider-role": "owner|editor|viewer"}

    # SAML 2.0 SSO (C6) — for enterprise IdPs that speak SAML instead of OIDC.
    saml_enabled: bool = False
    saml_provider_name: str = "SAML"
    saml_idp_metadata_url: str = ""
    saml_sp_entity_id: str = ""
    saml_sp_cert: str = ""  # PEM certificate (base64 string or file path)
    saml_sp_key: SecretStr = SecretStr("")  # PEM private key
    saml_auto_register: bool = True
    saml_name_id_format: str = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
    saml_sync_roles: bool = False
    saml_roles_attribute: str = "Role"
    saml_admin_roles: str = ""  # comma-separated IdP roles that grant superuser
    saml_workspace_role_map: str = ""  # JSON: {"idp-role": "owner|editor|viewer"}

    # SCIM 2.0 provisioning (C6) — server-to-server user lifecycle.
    scim_enabled: bool = False
    scim_bearer_token: SecretStr = SecretStr("")
    scim_default_workspace_id: str = ""
    scim_auto_activate: bool = True

    # Outbound notification channels. Both are off until configured: the
    # in-app inbox always works, and e-mail / webhook are an addition for
    # instances that want alerts to reach people who are not logged in.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = ""  # e.g. "SyncroFin <alertas@empresa.com.br>"
    smtp_starttls: bool = True
    # Receives a JSON POST per new notification, signed with
    # `X-SyncroFin-Signature: sha256=<hmac of the body>` when a secret is set.
    notifications_webhook_url: str = ""
    notifications_webhook_secret: SecretStr = SecretStr("")

    # Celery
    redis_url: str = "redis://localhost:6379/0"

    # Reverse-proxy trust for client-IP-based rate limiting. 0 (default) means
    # request.client.host is used as-is, which is only correct when nothing
    # sits between the client and this service. In the shipped docker-compose
    # topology the backend is reached through the bundled nginx frontend, so
    # request.client.host is always nginx's container address. Set this to the
    # number of trusted reverse proxies in front of the backend (usually 1) to
    # derive the client IP from X-Forwarded-For instead, trusting only that
    # many hops from the right; a chain shorter than expected is not trusted.
    trusted_proxy_hops: int = 0

    # Logo size for market-priced asset icons. The logo URL is built from
    # the company website we get from the market-price provider; no API
    # key or third-party account is required. Defaults to 128×128 which
    # is what Google's favicon service caps at before upscaling.
    logo_size: int = 128

    # Brazilian Treasury bond prices (official Tesouro Transparente CSV).
    # On by default since most users are Brazilian; the official CSV is only
    # fetched when someone actually searches a bond, and the UI pre-warm is
    # gated to Brazilian users, so non-Brazilian installs pay ~zero cost.
    # Set TESOURO_DIRETO_ENABLED=false to fully disable (e.g. to avoid the
    # external dependency on the Brazilian government endpoint).
    tesouro_direto_enabled: bool = True

    # Observabilidade (E5)
    # LOG_FORMAT=json → linhas JSON em produção; "text" → formato legível para dev.
    log_format: str = "text"
    # LOG_LEVEL=DEBUG | INFO | WARNING | ERROR
    log_level: str = "INFO"
    # Tracing OpenTelemetry (E5): vazio = desligado (no-op). Aceita OTEL_EXPORTER_OTLP_ENDPOINT.
    otel_exporter_endpoint: str = Field(default="", validation_alias=AliasChoices("OTEL_EXPORTER_OTLP_ENDPOINT", "otel_exporter_endpoint"))
    otel_service_name: str = Field(default="syncrofin-backend", validation_alias=AliasChoices("OTEL_SERVICE_NAME", "otel_service_name"))
    # "grpc" (padrão, porta 4317) ou "http" (OTLP/HTTP protobuf, porta 4318).
    otel_exporter_protocol: str = Field(default="grpc", validation_alias=AliasChoices("OTEL_EXPORTER_OTLP_PROTOCOL", "otel_exporter_protocol"))
    # Structured logging (E5): emit JSON log lines when true.
    # Set STRUCTURED_LOGGING=true in production for log aggregators (Loki, CloudWatch, Datadog).
    structured_logging: bool = False

    @property
    def cors_allowed_origins(self) -> list[str]:
        origins = [o.strip().rstrip("/") for o in self.cors_origins.split(",")]
        origins = [o for o in origins if o and o != "*"]
        return origins or [self.frontend_url]

    @property
    def smtp_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)

    @property
    def oidc_login_available(self) -> bool:
        return bool(self.oidc_enabled and self.oidc_client_id and self.oidc_discovery_url)

    @property
    def saml_login_available(self) -> bool:
        return bool(self.saml_enabled and self.saml_sp_entity_id and self.saml_idp_metadata_url)

    @model_validator(mode="after")
    def validate_auth_settings(self) -> "Settings":
        if not self.local_auth_enabled and not self.oidc_login_available and not self.saml_login_available:
            missing = []
            if not self.oidc_enabled:
                missing.append("OIDC_ENABLED=true")
            if not self.oidc_client_id:
                missing.append("OIDC_CLIENT_ID")
            if not self.oidc_discovery_url:
                missing.append("OIDC_DISCOVERY_URL")
            raise ValueError(
                "LOCAL_AUTH_ENABLED=false requires a complete OIDC or SAML configuration; "
                f"missing: {', '.join(missing)}"
            )
        return self

    @model_validator(mode="after")
    def refuse_public_default_secrets(self) -> "Settings":
        """Production must not run on the secrets that are printed in the repository.

        See `app.core.secrets_guard`. `DEBUG=true` (the development compose) skips this.
        """
        if self.debug:
            return self
        problems = [
            problem
            for problem in (
                secret_key_problem(self.secret_key.get_secret_value()),
                database_password_problem(self.database_url),
            )
            if problem
        ]
        if problems:
            raise ValueError(refusal_message(problems))
        return self

    # The CWD-relative ".env" is kept for backward compatibility; the anchored
    # backend/.env guarantees the API and the Celery worker/beat resolve the
    # same file no matter which working directory each service is launched
    # from (a systemd unit without WorkingDirectory= used to leave the worker
    # with default settings, silently disabling every bank-sync provider).
    #
    # extra="ignore" because the same .env is shared with Docker Compose and with
    # the optional modules: it legitimately holds keys this model doesn't declare
    # (COMPOSE_PROFILES, FRONTEND_PORT, AGENTS_*, ...). Unknown keys coming from
    # the process environment are ignored by pydantic-settings anyway; without
    # this, the very same key written into the .env file aborted startup with
    # "Extra inputs are not permitted".
    model_config = SettingsConfigDict(
        env_file=(".env", Path(__file__).resolve().parents[2] / ".env"),
        secrets_dir=CREDENTIALS_DIRECTORY,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
