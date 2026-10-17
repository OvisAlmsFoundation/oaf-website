"""Contact-only SMTP configuration and transport; no provider or credential setup."""

from dataclasses import dataclass, field
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
import os
from pathlib import Path
import re
import smtplib
import ssl
import stat
import tomllib

from .database_config import _validate_environment, _windows_password
from .notifications import normalize_email

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config/local/contact.toml"
RECIPIENT = "contact@ovisalmsfoundation.org"
SUBJECT = "OAF General Contact Inquiry"
SMTP_TIMEOUT = 5


class DeliveryUnavailable(Exception):
    """No acceptance occurred; exposes no transport/configuration details."""


class DeliveryUncertain(Exception):
    """The transport may have accepted DATA; do not automatically resend."""


@dataclass(frozen=True)
class SMTPConfig:
    host: str
    port: int
    tls_mode: str
    username: str = field(repr=False)
    from_email: str
    password: str = field(repr=False)

    def __post_init__(self):
        try:
            if (type(self.host) is not str or len(self.host) > 253
                    or re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", self.host) is None
                    or type(self.port) is not int or not 1 <= self.port <= 65535
                    or self.tls_mode not in {"ssl", "starttls"}
                    or type(self.username) is not str or not 1 <= len(self.username) <= 254
                    or not self.username.isascii() or any(ord(c) < 33 or ord(c) == 127 for c in self.username)
                    or type(self.password) is not str or not 1 <= len(self.password) <= 4096
                    or any(c in self.password for c in "\r\n\x00")
                    or type(self.from_email) is not str or len(self.from_email) > 254
                    or normalize_email(self.from_email) != self.from_email):
                raise ValueError
        except (ValueError, TypeError):
            pass
        else:
            return
        raise DeliveryUnavailable() from None


def load_contact_config(expected_profile, *, local_config_path=CONFIG_PATH,
                        environ=None, credential_loader=None):
    """Follow the existing explicit OAF_ENV, local TOML and pinned WinVault rules.

    Called only on Contact submission. No startup reads, fallback credentials,
    environment overrides, recipient setting or changes to shared services.
    Injection arguments are for offline tests.
    """
    try:
        environment = dict(os.environ if environ is None else environ)
        _validate_environment(environment, expected_profile)
        if expected_profile not in {"development", "testing"}:
            raise ValueError
        for path in (ROOT, ROOT / "config", local_config_path.parent, local_config_path):
            if path.is_symlink() or (path.exists() and getattr(path.lstat(), "st_file_attributes", 0)
                                     & stat.FILE_ATTRIBUTE_REPARSE_POINT):
                raise ValueError
        with local_config_path.open("rb") as source:
            contents = source.read(8193)
        if len(contents) > 8192:
            raise ValueError
        document = tomllib.loads(contents.decode("utf-8"))
        if (not document or not set(document) <= {"development", "testing"}
                or expected_profile not in document):
            raise ValueError
        for settings in document.values():
            if type(settings) is not dict or set(settings) != {"host", "port", "tls_mode", "username", "from_email"}:
                raise ValueError
            SMTPConfig(**settings, password="validation-only")
        settings = document[expected_profile]
        provider = _windows_password if credential_loader is None else credential_loader
        password = provider(f"OAF Website/{expected_profile}/Contact/SMTP",
                            settings["username"], environment, exact_target=True)
        return SMTPConfig(**settings, password=password)
    except Exception:
        # IO, TOML and provider exceptions can contain secrets; discard them.
        pass
    raise DeliveryUnavailable() from None


def construct_message(config, visitor_email, message):
    email = normalize_email(visitor_email)
    mail = EmailMessage()
    mail["From"] = Address("Ovis Alms Foundation", addr_spec=config.from_email)
    mail["To"] = Address(addr_spec=RECIPIENT)
    mail["Reply-To"] = Address(addr_spec=email)
    mail["Subject"] = SUBJECT
    mail["Date"] = formatdate(localtime=False, usegmt=True)
    mail["Message-ID"] = make_msgid(domain=config.from_email.split("@")[1])
    mail.set_content(f"OAF General Contact inquiry\n\nVisitor email: {email}\n\n{message}\n",
                     cte="quoted-printable")
    return mail


class ConfiguredSMTP:
    def __init__(self, expected_profile):
        self.expected_profile = expected_profile

    def __call__(self, visitor_email, message):
        config = load_contact_config(self.expected_profile)
        mail = construct_message(config, visitor_email, message)
        smtp = None
        submitting = False
        try:
            context = ssl.create_default_context()
            if config.tls_mode == "ssl":
                smtp = smtplib.SMTP_SSL(config.host, config.port, timeout=SMTP_TIMEOUT, context=context)
            else:
                smtp = smtplib.SMTP(config.host, config.port, timeout=SMTP_TIMEOUT)
            smtp.ehlo()
            if config.tls_mode == "starttls":
                smtp.starttls(context=context)
                smtp.ehlo()
            smtp.login(config.username, config.password)
            submitting = True
            refused = smtp.send_message(mail, from_addr=config.from_email, to_addrs=[RECIPIENT])
            if refused:
                raise DeliveryUnavailable()
            # Acknowledged DATA acceptance is success, not inbox delivery.
            # Close locally: a failed QUIT must not turn accepted mail into a retry.
            return
        except (smtplib.SMTPRecipientsRefused, smtplib.SMTPDataError, DeliveryUnavailable):
            raise DeliveryUnavailable() from None
        except Exception:
            if submitting:
                raise DeliveryUncertain() from None
            raise DeliveryUnavailable() from None
        finally:
            if smtp is not None:
                try:
                    smtp.close()
                except Exception:
                    pass
