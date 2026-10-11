"""Loopback-only TESTING host for the existing website and Flask API.

No schema setup or migrations. A Windows-user DPAPI-protected recognition key
is retained in ignored local configuration, and never printed or exported.
"""

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import secrets
import sys

from flask import send_file

from .state_requests import create_app

ROOT = Path(__file__).resolve().parents[1]
SECRET_PATH = ROOT / "config/local/state-request-recognition.dpapi"
PUBLIC_FILES = (
    "index.html", "about.html", "gramanna.html", "styles.css",
    "assets/state-requests.js", "assets/images/gramanna-logo.png",
    "assets/images/hero-gifts.webp",
)


def recognition_secret():
    """Create once with exclusive file creation; protect using current-user DPAPI."""
    if sys.platform != "win32":
        raise RuntimeError("Windows DPAPI is required for the local recognition key.")
    if SECRET_PATH.parent.is_symlink() or SECRET_PATH.is_symlink():
        raise RuntimeError("Redirected recognition key locations are prohibited.")
    if not SECRET_PATH.parent.is_dir():
        raise RuntimeError("Existing local configuration directory is required.")

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
            raise RuntimeError("Recognition key DPAPI operation failed.")
        try:
            return ctypes.string_at(output.data, output.size)
        finally:
            kernel.LocalFree(output.data)

    if not SECRET_PATH.exists():
        encrypted = transform(secrets.token_bytes(32), True)
        try:
            with SECRET_PATH.open("xb") as stream:
                stream.write(encrypted)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            pass
    value = transform(SECRET_PATH.read_bytes(), False)
    if len(value) != 32:
        raise RuntimeError("Recognition key has an invalid length.")
    return value


def testing_app(port):
    if os.environ.get("OAF_ENV") != "testing":
        raise RuntimeError("This local host requires OAF_ENV=testing.")
    app = create_app(expected_profile="testing", recognition_secret=recognition_secret(),
                     public_origin=f"http://127.0.0.1:{port}", allow_insecure_localhost=True)
    # Explicit public files only: never expose config, Git, Python, or audit files.
    for number, name in enumerate(PUBLIC_FILES):
        app.add_url_rule("/" + name, f"public_{number}",
                         lambda filename=name: send_file(ROOT / filename))
    app.add_url_rule("/", "home", lambda: send_file(ROOT / "index.html"))
    return app
