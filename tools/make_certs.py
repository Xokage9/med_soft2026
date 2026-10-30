import argparse
import datetime as dt
import ipaddress
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from server.settings import settings  # noqa: E402

CERTS = settings.certs_dir


def _name(cn: str) -> x509.Name:
    return x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "RU"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ITMO"),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, f"MedSoft 2026/27 {settings.isu_id}"),
        x509.NameAttribute(NameOID.COMMON_NAME, cn),
    ])


def _write_key(path: Path, key) -> None:
    path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))


def make_ca(now):
    key = ec.generate_private_key(ec.SECP384R1())
    name = _name(f"MedSoft {settings.isu_id} Root CA")
    ski = x509.SubjectKeyIdentifier.from_public_key(key.public_key())
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=False, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
            encipher_only=False, decipher_only=False), critical=True)
        .add_extension(ski, critical=False)
        .sign(key, hashes.SHA384())
    )
    return key, cert


def make_server(now, ca_key, ca_cert):
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "RU"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ITMO"),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, f"MedSoft 2026/27 {settings.isu_id}"),
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False,
            encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectAlternativeName([
            x509.DNSName("localhost"),
            x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
            x509.IPAddress(ipaddress.ip_address("::1")),
        ]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
                       critical=False)
        .sign(ca_key, hashes.SHA384())
    )
    return key, cert


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="перевыпустить, даже если файлы есть")
    args = ap.parse_args()

    CERTS.mkdir(parents=True, exist_ok=True)
    if settings.tls_cert.exists() and not args.force:
        print(f"Сертификаты уже есть в {CERTS}. Для перевыпуска: --force")
        return

    now = dt.datetime.now(dt.timezone.utc)
    ca_key, ca_cert = make_ca(now)
    srv_key, srv_cert = make_server(now, ca_key, ca_cert)

    pem = serialization.Encoding.PEM
    _write_key(CERTS / "ca.key", ca_key)
    (CERTS / "ca.crt").write_bytes(ca_cert.public_bytes(pem))
    _write_key(settings.tls_key, srv_key)
    (CERTS / "server.crt").write_bytes(srv_cert.public_bytes(pem))
    settings.tls_cert.write_bytes(srv_cert.public_bytes(pem) + ca_cert.public_bytes(pem))

    print("Готово:")
    print("  CA      Subject:", ca_cert.subject.rfc4514_string())
    print("  CA      Issuer: ", ca_cert.issuer.rfc4514_string())
    print("  Server  Subject:", srv_cert.subject.rfc4514_string())
    print("  Server  Issuer: ", srv_cert.issuer.rfc4514_string())
    print(f"\nДобавьте {CERTS / 'ca.crt'} в доверенные корневые (см. README).")


if __name__ == "__main__":
    main()
