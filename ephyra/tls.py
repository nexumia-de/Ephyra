"""Client certificates for servers behind mutual TLS (docs/connection.md).
No GTK."""
from gi.repository import Gio, GLib


class CertificateError(Exception):
    pass


class PasswordNeeded(CertificateError):
    """The PKCS #12 file is encrypted and the password is missing or
    wrong."""


def is_pem(data):
    return data.lstrip().startswith(b"-----BEGIN")


def load(data, password=None):
    """A Gio.TlsCertificate with private key from PKCS #12 (.p12, .pfx) or
    PEM data (certificate, chain and unencrypted key in one file)."""
    try:
        if is_pem(data):
            cert = Gio.TlsCertificate.new_from_pem(data.decode("ascii"), -1)
        else:
            cert = Gio.TlsCertificate.new_from_pkcs12(data, password or None)
    except GLib.Error as e:
        if e.matches(Gio.tls_error_quark(),
                     Gio.TlsError.BAD_CERTIFICATE_PASSWORD):
            raise PasswordNeeded("Wrong password" if password
                                 else "The certificate needs its password") from None
        raise CertificateError(_reason(e)) from None
    except UnicodeDecodeError:
        raise CertificateError("Not a certificate file") from None
    if not cert.props.private_key and not cert.props.private_key_pkcs11_uri:
        raise CertificateError("The file has no private key")
    return cert


def _reason(error):
    text = error.message or ""
    if "no private key" in text.lower() or "private key" in text.lower():
        return "The file has no private key"
    return "Not a certificate file"


def describe(cert):
    """(subject, expiry as GLib.DateTime or None) for the preferences."""
    subject = cert.props.subject_name or "Client certificate"
    for part in subject.split(","):
        part = part.strip()
        if part.upper().startswith("CN="):
            subject = part[3:]
            break
    return subject, cert.props.not_valid_after
