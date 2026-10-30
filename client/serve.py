import functools
import http.server
import ssl
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from server.settings import settings  # noqa: E402

API = f"localhost:{settings.api_port} 127.0.0.1:{settings.api_port}"
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    f"connect-src 'self' {' '.join('https://' + a for a in API.split())} "
    f"{' '.join('wss://' + a for a in API.split())}; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml"}

    def end_headers(self):
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Strict-Transport-Security", "max-age=31536000")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def main() -> None:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.load_cert_chain(settings.tls_cert, settings.tls_key)

    handler = functools.partial(Handler, directory=str(ROOT / "web"))
    httpd = http.server.ThreadingHTTPServer((settings.api_host, settings.client_port), handler)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    print(f"Клиент: https://localhost:{settings.client_port}/")
    print(f"  администратор: https://localhost:{settings.client_port}/admin/")
    print(f"  медработник:   https://localhost:{settings.client_port}/staff/")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
