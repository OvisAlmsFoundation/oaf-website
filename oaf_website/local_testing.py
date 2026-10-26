"""Loopback-only TESTING host for the existing website and Flask API.

No schema setup or migrations. A Windows-user DPAPI-protected recognition key
is retained in ignored local configuration, and never printed or exported.
"""

from .notification_dispatch import diagnostic_error

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import secrets
import stat
import sys

from flask import send_file

from .state_requests import create_app

ROOT = Path(__file__).resolve().parents[1]
SECRET_PATH = ROOT / "config/local/state-request-recognition.dpapi"
PUBLIC_FILES = (
    "index.html", "about.html", "gramanna.html", "faq.html", "support.html", "contact.html", "styles.css",
    "assets/state-requests.js", "assets/notifications.js", "assets/contact.js", "assets/images/gramanna-logo.png",
    "assets/images/hero-gifts.webp",
    "confirm-email.html", "assets/email-confirmation.js",
    "manage-notifications.html", "assets/notification-management.js",
)


def recognition_secret(*, require_existing=False):
    """Reuse the protected key; hosts may create once, processors must not replace."""
    if type(require_existing) is not bool:
        raise diagnostic_error(ValueError("Recognition key policy requires an explicit boolean."), "recognition_secret", "key_policy_boolean", stage="startup")
    if require_existing:
        for path in (ROOT, ROOT / "config", SECRET_PATH.parent, SECRET_PATH):
            if (path.is_symlink() or (path.exists() and
                    getattr(path.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)):
                raise diagnostic_error(RuntimeError("Redirected recognition key locations are prohibited."), "recognition_secret", "key_location_not_redirected", stage="startup")
        if not SECRET_PATH.is_file():
            raise diagnostic_error(RuntimeError("Existing protected recognition key is required."), "recognition_secret", "key_existing", stage="startup")
    if sys.platform != "win32":
        raise diagnostic_error(RuntimeError("Windows DPAPI is required for the local recognition key."), "recognition_secret", "key_windows_required", stage="startup")
    if SECRET_PATH.parent.is_symlink() or SECRET_PATH.is_symlink():
        raise diagnostic_error(RuntimeError("Redirected recognition key locations are prohibited."), "recognition_secret", "key_location_not_redirected", stage="startup")
    if not SECRET_PATH.parent.is_dir():
        raise diagnostic_error(RuntimeError("Existing local configuration directory is required."), "recognition_secret", "key_parent_existing", stage="startup")

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    for name in ("CryptProtectData", "CryptUnprotectData"):
        function = getattr(crypt, name)
        function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p,
                            ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                            wintypes.DWORD, ctypes.POINTER(Blob)]
        function.restype = wintypes.BOOL

    def transform(value, protect):
        buffer = ctypes.create_string_buffer(value)
        source = Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
        output = Blob()
        function = crypt.CryptProtectData if protect else crypt.CryptUnprotectData
        # CRYPTPROTECT_UI_FORBIDDEN; no machine-wide protection flag.
        if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
            raise diagnostic_error(RuntimeError("Recognition key DPAPI operation failed."), "recognition_secret", "key_dpapi_transform", stage="startup")
        try:
            return ctypes.string_at(output.data, output.size)
        finally:
            kernel.LocalFree(output.data)

    if not require_existing and not SECRET_PATH.exists():
        encrypted = transform(secrets.token_bytes(32), True)
        try:
            with SECRET_PATH.open("xb") as stream:
                stream.write(encrypted)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            pass
    try:
        value = transform(SECRET_PATH.read_bytes(), False)
    except Exception as exc:
        raise diagnostic_error(exc, "protected_key", "key_read_or_decrypt", stage="startup")
    if len(value) != 32:
        raise diagnostic_error(RuntimeError("Recognition key has an invalid length."), "recognition_secret", "key_length", stage="startup")
    return value


def testing_app(port):
    if os.environ.get("OAF_ENV") != "testing":
        raise diagnostic_error(RuntimeError("This local host requires OAF_ENV=testing."), "testing_app", "environment_testing_required", stage="startup")
    app = create_app(expected_profile="testing", recognition_secret=recognition_secret(),
                     public_origin=f"http://127.0.0.1:{port}", allow_insecure_localhost=True)
    return public_files(app)


def public_files(app):
    # Explicit public files only: never expose config, Git, Python, or audit files.
    for number, name in enumerate(PUBLIC_FILES):
        app.add_url_rule("/" + name, f"public_{number}",
                         lambda filename=name: send_file(ROOT / filename))
    app.add_url_rule("/", "home", lambda: send_file(ROOT / "index.html"))
    return app


def validate_testing_https(*, public_origin, confirmation_page, confirmation_enabled=False):
    """Validate all nonsecret HTTPS choices before protected runtime access."""
    from .database_config import _validate_environment
    from .notification_messages import secure_confirmation_page
    _validate_environment(dict(os.environ), "testing")
    if type(confirmation_enabled) is not bool:
        raise diagnostic_error(ValueError("Email confirmation activation requires an explicit boolean."), "validate_testing_https", "confirmation_activation_boolean", stage="startup")
    # Keep the existing strict template contract, including standard HTTPS port.
    if (type(public_origin) is not str or public_origin.endswith("/")
            or secure_confirmation_page(confirmation_page) != public_origin + "/confirm-email.html"):
        raise diagnostic_error(ValueError("HTTPS origin and confirmation page must match."), "validate_testing_https", "https_origin_page_match", stage="startup")
    # secure_confirmation_page validates the origin/labels before exact matching.


def testing_https_app(*, public_origin, confirmation_page, confirmation_enabled=False,
                      management_enabled=False, brevo_webhook_config=None):
    """Explicit HTTPS preparation seam; never starts a server or a processor."""
    validate_testing_https(public_origin=public_origin, confirmation_page=confirmation_page,
                           confirmation_enabled=confirmation_enabled)
    if type(management_enabled) is not bool:
        raise diagnostic_error(ValueError("Notification management activation requires an explicit boolean."), "testing_https_app", "management_activation_boolean", stage="startup")
    options = {}
    if management_enabled:
        options["management_enabled"] = True
    if brevo_webhook_config is not None:
        from .brevo_unsubscribe import validate_webhook_config
        validate_webhook_config(brevo_webhook_config, "testing")
        if not management_enabled:
            raise diagnostic_error(ValueError("Webhook processing requires management activation."), "testing_https_app", "webhook_management_required", stage="startup")
        options["brevo_webhook_config"] = brevo_webhook_config
    app = create_app(expected_profile="testing", recognition_secret=recognition_secret(require_existing=True),
                     public_origin=public_origin, confirmation_enabled=confirmation_enabled, **options)
    return public_files(app)
