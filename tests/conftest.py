"""Offline suite: deny real credential access and database/network connections."""

import socket
import sys
from types import ModuleType

import psycopg
import pytest
import sqlalchemy
import sqlalchemy.engine.create


@pytest.fixture(autouse=True)
def isolate_external_access(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Unit tests must not access credentials or connections.")

    # Even accidental imports cannot reach an installed keyring or its plugins.
    for name in ("keyring", "keyring.backends", "keyring.backends.Windows"):
        module = ModuleType(name)
        module.__path__ = []
        module.get_keyring = denied
        module.get_password = denied
        module.get_credential = denied
        module.set_password = denied
        module.delete_password = denied
        module.WinVaultKeyring = denied
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(psycopg, "connect", denied)
    monkeypatch.setattr(psycopg.Connection, "connect", denied)
    monkeypatch.setattr(sqlalchemy, "create_engine", denied)
    monkeypatch.setattr(sqlalchemy.engine.create, "create_engine", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setenv("OAF_ENV", "testing")
