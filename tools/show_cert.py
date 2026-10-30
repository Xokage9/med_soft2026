import ssl
import socket
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from server.settings import settings  # noqa: E402


def main() -> None:
    host = sys.argv[1] if len(sys.argv) > 1 else "localhost"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else settings.api_port

    ctx = ssl.create_default_context(cafile=str(settings.ca_cert))
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3

    with socket.create_connection((host, port), timeout=5) as raw:
        with ctx.wrap_socket(raw, server_hostname=host) as tls:
            print(f"Соединение: {tls.version()}, шифр {tls.cipher()[0]}")
            chain = tls.get_unverified_chain() if hasattr(tls, "get_unverified_chain") else [
                tls.getpeercert(binary_form=True)]
            for i, der in enumerate(chain):
                if hasattr(der, "public_bytes"):
                    der = der.public_bytes(ssl._ssl.ENCODING_DER)
                cert = x509.load_der_x509_certificate(der)
                print(f"\n[{i}] Subject: {cert.subject.rfc4514_string()}")
                print(f"    Issuer:  {cert.issuer.rfc4514_string()}")
                print(f"    Serial:  {cert.serial_number:x}")
                print(f"    Valid:   {cert.not_valid_before_utc} .. {cert.not_valid_after_utc}")
                print(f"    SHA-256: {cert.fingerprint(hashes.SHA256()).hex(':')}")
                try:
                    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
                    print(f"    SAN:     {', '.join(str(v.value) for v in san.value)}")
                except x509.ExtensionNotFound:
                    pass
            print("\nСертификат сервера проверен и доверен (цепочка до учебного CA).")


if __name__ == "__main__":
    main()
