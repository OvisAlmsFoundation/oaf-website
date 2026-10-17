# Windows PowerShell 5.1. Owner-only interactive provisioning; never sends mail.
[CmdletBinding()]
param()

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
$taskCode = @'
import getpass
import importlib.metadata
import os
from pathlib import Path
import stat
import sys
import tomllib
import warnings


def provision(root):
    if (sys.platform != 'win32'
            or Path(sys.prefix).resolve() != (root / '.venv').resolve()
            or not all(stream.isatty() for stream in (sys.stdin, sys.stdout, sys.stderr))):
        raise RuntimeError
    if os.environ.get('OAF_ENV', 'development') != 'development':
        raise RuntimeError
    for name in os.environ:
        if ((name.startswith('OAF_') and name != 'OAF_ENV')
                or name.startswith(('PG', 'DB_', 'DATABASE_'))
                or name == 'SQLALCHEMY_DATABASE_URI' or 'KEYRING_PROPERTY_' in name):
            raise RuntimeError
    if (os.environ.get('PYTHON_KEYRING_BACKEND', 'keyring.backends.Windows.WinVaultKeyring')
            != 'keyring.backends.Windows.WinVaultKeyring'
            or importlib.metadata.version('keyring') != '25.7.0'):
        raise RuntimeError

    path = root / 'config/local/contact.toml'
    lock_path = path.parent / 'contact.operator.lock'
    for candidate in (root, root / 'config', path.parent, path, lock_path):
        if (candidate.is_symlink() or (candidate.exists()
                and getattr(candidate.lstat(), 'st_file_attributes', 0)
                & stat.FILE_ATTRIBUTE_REPARSE_POINT)):
            raise RuntimeError
    contents = path.read_bytes()
    if len(contents) > 8192:
        raise RuntimeError
    document = tomllib.loads(contents.decode('utf-8'))
    account = 'contact@ovisalmsfoundation.org'
    expected = dict(host='mail.privateemail.com', port=465, tls_mode='ssl',
                    username=account, from_email=account)
    if (document != {'development': expected}
            or type(document['development']['port']) is not int):
        raise RuntimeError

    # Same pinned backend as Contact. No backend discovery or keyring CLI.
    import msvcrt
    from keyring.backends.Windows import WinVaultKeyring
    backend = WinVaultKeyring()
    if type(backend) is not WinVaultKeyring or backend.priority <= 0:
        raise RuntimeError
    backend.persist = 2
    target = 'OAF Website/development/Contact/SMTP'
    password = confirmation = record = None
    # Coordinate cooperating operators. Keep other Credential Manager writers idle:
    # Windows CredWrite has no atomic create-only operation.
    with lock_path.open('a+b') as operator_lock:
        if operator_lock.tell() == 0:
            operator_lock.write(b'0')
            operator_lock.flush()
        operator_lock.seek(0)
        msvcrt.locking(operator_lock.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            if backend._read_credential(target) is not None:
                print('Exact DEVELOPMENT Contact SMTP credential already exists; unchanged. No password requested.')
                return
            with warnings.catch_warnings():
                warnings.simplefilter('error', getpass.GetPassWarning)
                password = getpass.getpass('Namecheap mailbox password (hidden): ')
                confirmation = getpass.getpass('Confirm mailbox password (hidden): ')
            if (not 1 <= len(password) <= 4096 or password != confirmation
                    or any(c in password for c in '\r\n\x00')):
                raise RuntimeError
            confirmation = None
            if backend._read_credential(target) is not None:
                raise RuntimeError
            # set_password may move existing credentials into compound targets.
            # Use the same backend exact-target writer after the absence recheck.
            backend._set_password(target, account, password)
            record = backend._read_credential(target)
            if (record is None or record.get('TargetName') != target
                    or record.get('UserName') != account or record.get('Type') != 1
                    or record.get('Persist') != 2 or record.value != password):
                raise RuntimeError
            print('DEVELOPMENT Contact SMTP credential provisioned and verified locally. No email sent.')
        finally:
            password = confirmation = record = None


try:
    provision(Path(sys.argv[1]))
except BaseException:
    print('Provisioning blocked or write outcome unverified. Keep existing credentials unchanged; reconcile metadata before retrying.', file=sys.stderr)
    sys.exit(2)
'@

& $taskPython -I -B -c $taskCode $taskRoot
if ($LASTEXITCODE -ne 0) {
    throw [InvalidOperationException]::new('Contact SMTP provisioning did not verify success. No application or email test was started.')
}
