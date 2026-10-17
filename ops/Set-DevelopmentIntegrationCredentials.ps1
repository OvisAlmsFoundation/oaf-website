# Windows PowerShell 5.1. Operator-only; never launches an application.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Provision', 'ActivateReporting', 'ActivateSharedServices')][string]$Operation
)

function Initialize-OafDevelopmentCredentialApi {
    if ('OafDevelopmentCredentials.Native' -as [type]) { return }
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;

namespace OafDevelopmentCredentials {
    // Exact generic targets only. No discovery, compound names, deletion or fallback.
    public static class Native {
        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        private struct Credential {
            public UInt32 Flags, Type;
            public string TargetName, Comment;
            public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
            public UInt32 CredentialBlobSize;
            public IntPtr CredentialBlob;
            public UInt32 Persist, AttributeCount;
            public IntPtr Attributes;
            public string TargetAlias, UserName;
        }
        [DllImport("advapi32.dll", EntryPoint = "CredReadW", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool ReadCredential(string target, UInt32 type, UInt32 flags, out IntPtr result);
        [DllImport("advapi32.dll", EntryPoint = "CredWriteW", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool WriteCredential(ref Credential value, UInt32 flags);
        [DllImport("advapi32.dll", EntryPoint = "CredFree")]
        private static extern void FreeCredential(IntPtr value);

        public sealed class Record {
            public string TargetName, UserName;
            public UInt32 Type, Persist;
            public byte[] Blob;
            public override string ToString() { return "Protected DEVELOPMENT credential"; }
        }
        public static Record Read(string target) {
            IntPtr pointer;
            if (!ReadCredential(target, 1, 0, out pointer)) {
                if (Marshal.GetLastWin32Error() == 1168) return null;
                throw new InvalidOperationException("Protected credential read failed.");
            }
            try {
                Credential value = (Credential)Marshal.PtrToStructure(pointer, typeof(Credential));
                // Bound before copying, even for malformed records. Valid blobs are 128 bytes.
                if (value.CredentialBlobSize > 512) throw new InvalidOperationException("Invalid credential encoding.");
                byte[] blob = new byte[value.CredentialBlobSize];
                if (blob.Length != 0) Marshal.Copy(value.CredentialBlob, blob, 0, blob.Length);
                return new Record { TargetName = value.TargetName, UserName = value.UserName,
                    Type = value.Type, Persist = value.Persist, Blob = blob };
            } finally { FreeCredential(pointer); }
        }
        public static byte[] Encode(string secret) {
            // Same byte representation as the installed keyring Windows writer: no BOM/NUL.
            return new UnicodeEncoding(false, false, true).GetBytes(secret);
        }
        public static void Create(string target, string account, string secret) {
            // CredWrite has no create-only flag. Recheck immediately before writing;
            // the PowerShell caller also holds an exclusive cooperating-operator lock.
            if (Read(target) != null) throw new InvalidOperationException("Credential already exists.");
            byte[] blob = Encode(secret);
            IntPtr pointer = Marshal.AllocHGlobal(blob.Length);
            try {
                Marshal.Copy(blob, 0, pointer, blob.Length);
                Credential value = new Credential { Type = 1, TargetName = target, UserName = account,
                    Persist = 2, CredentialBlobSize = (UInt32)blob.Length, CredentialBlob = pointer };
                if (!WriteCredential(ref value, 0)) throw new InvalidOperationException("Protected credential write failed.");
            } finally {
                for (int i = 0; i < blob.Length; i++) Marshal.WriteByte(pointer, i, 0);
                Marshal.FreeHGlobal(pointer);
                Array.Clear(blob, 0, blob.Length);
            }
        }
        public static string NewSecret() {
            byte[] bytes = new byte[32];
            try {
                using (RandomNumberGenerator generator = RandomNumberGenerator.Create()) { generator.GetBytes(bytes); }
                return BitConverter.ToString(bytes).Replace("-", "").ToLowerInvariant();
            } finally { Array.Clear(bytes, 0, bytes.Length); }
        }
    }
}
'@ | Out-Null
}

function Read-OafDevelopmentClientId([string]$Path, [string]$Python) {
    # stdlib TOML parser only; -I -S excludes environment, site hooks and packages.
    # No configuration contents or parser exceptions are returned to PowerShell.
    $code = @'
import re, sys, tomllib
try:
    with open(sys.argv[1], 'rb') as source:
        doc = tomllib.load(source)
    section = doc.get('development')
    assert set(doc) == {'development'} and type(section) is dict
    assert set(section) == {'client_id'} and type(section['client_id']) is str
    assert re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', section['client_id'], re.ASCII)
except BaseException:
    sys.exit(2)
print(section['client_id'])
'@
    $client = @($code | & $Python -I -S -B - $Path 2>$null)
    if ($LASTEXITCODE -ne 0 -or $client.Count -ne 1 -or $client[0] -cnotmatch '\A[a-z][a-z0-9_-]{0,63}\z') {
        throw 'DEVELOPMENT integration metadata is missing or invalid; nothing replaced.'
    }
    return [string]$client[0]
}

function Get-OafDevelopmentSecret($Record, [string]$Target, [string]$Account) {
    if ($null -eq $Record -or $Record.TargetName -cne $Target -or $Record.UserName -cne $Account -or
        $Record.Type -ne 1 -or $Record.Persist -ne 2) {
        throw 'DEVELOPMENT credential is missing or its target/account/type/persistence conflicts.'
    }
    # Strict canonical UTF-16LE, exactly 64 ASCII hex characters; reject UTF-8,
    # BOMs, terminators, malformed UTF-16 and keyring's permissive UTF-8 fallback.
    if ($Record.Blob -isnot [byte[]] -or $Record.Blob.Length -ne 128) { throw 'Invalid DEVELOPMENT credential encoding.' }
    for ($i = 0; $i -lt 128; $i += 2) {
        $b = $Record.Blob[$i]
        if ($Record.Blob[$i + 1] -ne 0 -or -not (($b -ge 48 -and $b -le 57) -or ($b -ge 97 -and $b -le 102))) {
            throw 'Invalid DEVELOPMENT credential encoding.'
        }
    }
    return [Text.Encoding]::Unicode.GetString($Record.Blob)
}

function Invoke-OafDevelopmentCredentialHandoff {
    # Injection is internal and used only by the offline AST-based harness.
    param([string]$Operation, [string]$Root, [string]$Python, $Store, [scriptblock]$SecretFactory)
    Set-StrictMode -Version 2.0
    $ErrorActionPreference = 'Stop'
    $names = @('OAF_INTEGRATION_ENABLED', 'OAF_INTEGRATION_ENVIRONMENT',
        'OAF_DEVELOPMENT_ORIGIN', 'OAF_DEVELOPMENT_REPORTING_CREDENTIAL')
    if ($Operation -ceq 'ActivateSharedServices') { $names += 'OAF_DEVELOPMENT_SUBMISSION_CREDENTIAL' }
    $prior = @{}
    foreach ($name in $names) { $prior[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
    $changing = $false
    $provisioning = $false
    $lock = $null
    $submission = $reporting = $null
    try {
        if ($Operation -cnotin @('Provision', 'ActivateReporting', 'ActivateSharedServices')) { throw 'Invalid operation.' }
        foreach ($entry in Get-ChildItem Env:) {
            if ($entry.Name -like 'OAF_*' -and $entry.Name -cnotin (@('OAF_ENV') + $names)) {
                throw 'Unexpected OAF process settings; use a separate DEVELOPMENT terminal.'
            }
        }
        if (($env:OAF_ENV -and $env:OAF_ENV -cne 'development') -or
            ($prior[$names[1]] -and $prior[$names[1]] -cne 'development') -or
            ($prior[$names[2]] -and $prior[$names[2]] -cne 'http://127.0.0.1:5055')) {
            throw 'Process settings conflict with DEVELOPMENT; no override performed.'
        }
        if ($Operation -ceq 'Provision' -and @($names | Where-Object { $prior[$_] }).Count -ne 0) {
            throw 'Provision in a separate terminal without GraManna activation settings.'
        }
        $configDirectory = Join-Path $Root 'config'
        $localDirectory = Join-Path $configDirectory 'local'
        $path = Join-Path $localDirectory 'integrations.toml'
        $lockPath = Join-Path $localDirectory 'integrations.operator.lock'
        foreach ($location in @($Root, $configDirectory, $localDirectory, $path, $lockPath)) {
            if (Test-Path -LiteralPath $location) {
                if ((Get-Item -Force -LiteralPath $location).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                    throw 'Redirected integration configuration locations are prohibited.'
                }
            }
        }
        if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Existing website Python is required.' }
        if ($Operation -ceq 'Provision') {
            [IO.Directory]::CreateDirectory($localDirectory) | Out-Null
            # A non-secret ignored lock file persists; FileShare.None releases on failure/exit.
            $lock = [IO.File]::Open($lockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
        }
        $hasMetadata = Test-Path -LiteralPath $path -PathType Leaf
        if ($hasMetadata) { $account = Read-OafDevelopmentClientId $path $Python }
        elseif ($Operation -ceq 'Provision') { $account = 'gramanna' }
        else { throw 'DEVELOPMENT integration metadata is missing.' }

        $submissionTarget = 'OAF Website/development/Integrations/Submission'
        $reportingTarget = 'OAF Website/development/Integrations/Reporting'
        if ($Operation -cin @('ActivateReporting', 'ActivateSharedServices')) {
            # Reporting-only activation intentionally never reads submission.
            if ($Operation -ceq 'ActivateSharedServices') {
                $submission = Get-OafDevelopmentSecret (& $Store.Read $submissionTarget) $submissionTarget $account
            }
            $reporting = Get-OafDevelopmentSecret (& $Store.Read $reportingTarget) $reportingTarget $account
            if ($Operation -ceq 'ActivateSharedServices') {
                if ($submission -ceq $reporting) { throw 'DEVELOPMENT permission credentials must differ.' }
                if ($prior[$names[4]] -and $prior[$names[4]] -cne $submission) {
                    throw 'Existing submission process credential conflicts; no override performed.'
                }
            }
            if ($prior[$names[3]] -and $prior[$names[3]] -cne $reporting) {
                throw 'Existing reporting process credential conflicts; no override performed.'
            }
            # Validate the complete requested handoff before changing any setting.
            # The rollback snapshot includes submission only for shared activation.
            $changing = $true
            if ($Operation -ceq 'ActivateSharedServices') {
                [Environment]::SetEnvironmentVariable($names[4], $submission, 'Process')
            }
            [Environment]::SetEnvironmentVariable($names[0], '1', 'Process')
            [Environment]::SetEnvironmentVariable($names[1], 'development', 'Process')
            [Environment]::SetEnvironmentVariable($names[2], 'http://127.0.0.1:5055', 'Process')
            [Environment]::SetEnvironmentVariable($names[3], $reporting, 'Process')
            if ($Operation -ceq 'ActivateSharedServices') {
                Write-Output 'DEVELOPMENT shared services activated in this PowerShell process. Start GraManna with dev_app.py in this terminal.'
            } else {
                Write-Output 'DEVELOPMENT reporting activated in this PowerShell process. Start GraManna with dev_app.py in this terminal.'
            }
            return
        }

        $first = & $Store.Read $submissionTarget
        $second = & $Store.Read $reportingTarget
        if ($null -ne $first -or $null -ne $second) {
            if (-not $hasMetadata -or $null -eq $first -or $null -eq $second) {
                throw 'Incomplete DEVELOPMENT setup; reconcile existing records and metadata before retrying.'
            }
            $submission = Get-OafDevelopmentSecret $first $submissionTarget $account
            $reporting = Get-OafDevelopmentSecret $second $reportingTarget $account
            if ($submission -ceq $reporting) { throw 'DEVELOPMENT permission credentials must differ.' }
            Write-Output 'Existing DEVELOPMENT credential pair verified; credentials and owner metadata unchanged.'
            return
        }
        # All preflight checks completed before generation. Never accepts a supplied secret.
        $submission = & $SecretFactory
        $reporting = & $SecretFactory
        if ($submission -isnot [string] -or $submission -cnotmatch '\A[0-9a-f]{64}\z' -or
            $reporting -isnot [string] -or $reporting -cnotmatch '\A[0-9a-f]{64}\z' -or $submission -ceq $reporting) {
            throw 'Credential generation failed; nothing provisioned.'
        }
        $provisioning = $true
        if (-not $hasMetadata) {
            # CreateNew preserves any file created since preflight. Metadata contains no secrets.
            $file = [IO.File]::Open($path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
            try {
                $bytes = [Text.Encoding]::UTF8.GetBytes("[development]`nclient_id = `"gramanna`"`n")
                $file.Write($bytes, 0, $bytes.Length)
                $file.Flush($true)
            } finally { $file.Dispose() }
        }
        & $Store.Create $submissionTarget $account $submission | Out-Null
        & $Store.Create $reportingTarget $account $reporting | Out-Null
        # Read both back, including metadata/encoding, before claiming success.
        $verifiedSubmission = Get-OafDevelopmentSecret (& $Store.Read $submissionTarget) $submissionTarget $account
        $verifiedReporting = Get-OafDevelopmentSecret (& $Store.Read $reportingTarget) $reportingTarget $account
        if ($verifiedSubmission -cne $submission -or $verifiedReporting -cne $reporting -or
            (Read-OafDevelopmentClientId $path $Python) -cne $account) { throw 'Readback mismatch.' }
        Write-Output 'DEVELOPMENT credential pair provisioned and verified. No application started.'
    } catch {
        if ($changing) {
            foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $prior[$name], 'Process') }
        }
        # Discard native/parser/provider exceptions, which may contain private text.
        # Throw only literal diagnostics; no exception interpolation or InnerException.
        if ($provisioning) {
            throw 'DEVELOPMENT provisioning incomplete; records or metadata may exist. Stop and reconcile before retrying; nothing automatically replaced or deleted.'
        }
        throw 'DEVELOPMENT handoff blocked: check metadata, exact credential targets/accounts/type/persistence/UTF-16LE encoding, process environment and operator lock. No activation performed; existing setup not replaced.'
    } finally {
        if ($null -ne $lock) { $lock.Dispose() }
        $submission = $reporting = $verifiedSubmission = $verifiedReporting = $null
        $first = $second = $prior = $null
    }
}

# The normal script invocation has its own scope. Use & from either repository;
# process environment changes survive in the invoking PowerShell, locals do not.
try {
    if ($PSVersionTable.PSVersion -lt [Version]'5.1' -or [Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw 'Windows PowerShell 5.1 or later is required.'
    }
    Initialize-OafDevelopmentCredentialApi
    $root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
    $store = @{
        Read = { param($target) [OafDevelopmentCredentials.Native]::Read($target) }
        Create = { param($target, $account, $secret) [OafDevelopmentCredentials.Native]::Create($target, $account, $secret) }
    }
    Invoke-OafDevelopmentCredentialHandoff -Operation $Operation -Root $root -Python (Join-Path $root '.venv\Scripts\python.exe') `
        -Store $store -SecretFactory { [OafDevelopmentCredentials.Native]::NewSecret() }
} catch {
    # Prevent the original ErrorRecord/InvocationInfo from exposing injected values.
    throw [InvalidOperationException]::new('DEVELOPMENT credential handoff failed. Check setup/environment; if provisioning began, stop and reconcile possible partial records before retrying.')
}
