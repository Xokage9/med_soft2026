import ssl
import sys

import uvicorn

from .settings import settings


class TLS13Config(uvicorn.Config):
    def load(self) -> None:
        super().load()
        if self.ssl is not None:
            self.ssl.minimum_version = ssl.TLSVersion.TLSv1_3
            self.ssl.maximum_version = ssl.TLSVersion.TLSv1_3


def main() -> None:
    if not settings.tls_cert.exists():
        sys.exit("Нет сертификатов. Сначала выполните: python tools/make_certs.py")
    config = TLS13Config(
        "server.main:app",
        host=settings.api_host,
        port=settings.api_port,
        ssl_certfile=str(settings.tls_cert),
        ssl_keyfile=str(settings.tls_key),
        proxy_headers=False,
    )
    print(f"API: https://localhost:{settings.api_port}  (документация: /docs)")
    uvicorn.Server(config).run()


if __name__ == "__main__":
    main()
