import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env(name: str, default: str) -> str:
    return os.getenv(f"HIS_{name}", default)


class Settings:
    isu_id: str = _env("ISU_ID", "367627")

    db_url: str = _env("DB_URL", f"sqlite:///{(BASE_DIR / 'data' / 'his.db').as_posix()}")

    api_host: str = _env("API_HOST", "127.0.0.1")
    api_port: int = int(_env("API_PORT", "8443"))
    client_port: int = int(_env("CLIENT_PORT", "8444"))
    client_origins: list[str] = _env(
        "CLIENT_ORIGINS", "https://localhost:8444,https://127.0.0.1:8444"
    ).split(",")

    certs_dir: Path = BASE_DIR / "certs"
    tls_cert: Path = certs_dir / "server-fullchain.crt"
    tls_key: Path = certs_dir / "server.key"
    ca_cert: Path = certs_dir / "ca.crt"

    jwt_private_key: Path = BASE_DIR / "keys" / "jwt_ed25519.pem"
    jwt_issuer: str = "medsoft-his"
    access_ttl: timedelta = timedelta(minutes=int(_env("ACCESS_TTL_MIN", "5")))
    refresh_ttl: timedelta = timedelta(hours=int(_env("REFRESH_TTL_H", "8")))

    totp_issuer: str = "MedSoft HIS"
    seed_diagnoses: Path = BASE_DIR / "server" / "seed" / "diagnoses.json"


settings = Settings()
