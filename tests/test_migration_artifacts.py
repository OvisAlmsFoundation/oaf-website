"""Authoritative inventory and isolated synthetic artifact corruption."""

import migration_offline as isolation
isolation.require_early_registration()

import json
from pathlib import Path

import pytest

from migration_offline import ROOT, artifacts
from oaf_website import migration_validation as v
from oaf_website.migration_config import Failure, MigrationError


@pytest.fixture
def artifact_copy(tmp_path, monkeypatch):
    # Copy only public framework files, never config/local or any credentials.
    for name in sorted(v.FRAMEWORK_FILES | v.REVISION_FILES | {"migrations/manifest.json"}):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    monkeypatch.setattr(v, "ROOT", tmp_path)
    return tmp_path


def verify(root, *, revision_hash=None):
    payload = (root / "migrations/manifest.json").read_bytes()
    document = json.loads(payload)
    revisions = document.get("revisions", [])
    declared = revisions[0].get("sha256", "0"*64) if revisions else "0"*64
    return v.validate_artifacts(expected_start=v.BASE, target=v.BASELINE,
        manifest_hash=v.digest(payload), revision_hash=revision_hash or declared)


def write_manifest(root, document):
    (root / "migrations/manifest.json").write_text(json.dumps(document), encoding="utf-8")


def test_revision_docstrings_are_optional_without_changing_operations(artifact_copy):
    import ast
    document=json.loads((artifact_copy/'migrations/manifest.json').read_bytes())
    for revision in document['revisions']:
        path=artifact_copy/'migrations/versions'/(revision['id']+'.py')
        if revision['id'] not in {v.STATE_REQUESTS,v.NOTIFICATIONS,v.MANAGEMENT,v.RELEASE_APPROVALS}:
            continue
        source=path.read_text()
        first=ast.parse(source).body[0]
        assert isinstance(first,ast.Expr) and isinstance(first.value,ast.Constant)
        path.write_text('\n'.join(source.splitlines()[first.end_lineno:])+'\n')
        revision['sha256']=v.digest(path.read_bytes())
    write_manifest(artifact_copy,document)
    assert verify(artifact_copy).target==v.BASELINE


def test_authoritative_manifest_and_single_root():
    a = artifacts()
    assert (a.expected_start, a.target) == ("base", "0001_migration_baseline")
    document = json.loads((ROOT / "migrations/manifest.json").read_bytes())
    assert document["approval_status"] == "pending_independent_review"
    assert len(document["revisions"]) == 7
    assert document["revisions"][0]["parent"] is None
    assert document["revisions"][1]["parent"] == v.BASELINE
    assert set(document["framework"]) == v.FRAMEWORK_FILES
    # Literal J2 regression: changes to the registry cannot remove these files
    # from both sides of the equality and silently weaken dependency integrity.
    assert {"oaf_website/database_config.py", "oaf_website/__init__.py",
            "requirements.txt"} <= set(document["framework"])


def test_digest_utf8_lf_normalization():
    assert v.digest("Ã©\n".encode()) == v.digest("Ã©\r\n".encode())


@pytest.mark.parametrize("payload", [b"\xef\xbb\xbf{}", b"a\rb"])
def test_bom_and_lone_cr_rejected(payload):
    with pytest.raises(MigrationError, match=Failure.ARTIFACT_HASH):
        v.digest(payload)


@pytest.mark.parametrize("start,target", [("head", v.BASELINE), (v.BASELINE, "base"),
    (v.BASE, "head"), (v.BASE, "heads"), (v.BASE, "0002"), (v.BASE, "base")])
def test_no_multi_revision_stamp_downgrade_or_unknown_transition(start, target):
    with pytest.raises(MigrationError, match=Failure.STARTING_REVISION):
        v.validate_artifacts(expected_start=start, target=target, manifest_hash="0"*64, revision_hash="0"*64)


@pytest.mark.parametrize("hash_value", [None, "", "A"*64, "g"*64, "0"*63, "0"*64])
def test_incorrect_hashes_rejected(hash_value):
    with pytest.raises(MigrationError, match=Failure.ARTIFACT_HASH):
        v.validate_artifacts(expected_start=v.BASE, target=v.BASELINE,
                             manifest_hash=hash_value, revision_hash="0"*64)


@pytest.mark.parametrize("name", sorted(v.FRAMEWORK_FILES | v.REVISION_FILES))
@pytest.mark.parametrize("mode", ["missing", "tampered"])
def test_every_hashed_dependency_rejected_when_missing_or_modified(artifact_copy, name, mode):
    path = artifact_copy / name
    if mode == "missing":
        path.unlink()
    else:
        path.write_bytes(path.read_bytes() + b"\n# synthetic tamper\n")
    with pytest.raises(MigrationError, match=Failure.ARTIFACT_HASH):
        verify(artifact_copy)


@pytest.mark.parametrize("field,value", [
    ("format", True), ("hash_mode", "sha256"), ("approval_status", "approved"),
    ("states", {}), ("security", {}), ("revisions", []), ("revisions", [{}, {}]),
    ("framework", {"migrations/manifest.json": "0"*64}), ("framework", []),
])
def test_manifest_structure_and_self_reference(artifact_copy, field, value):
    d = json.loads((artifact_copy / "migrations/manifest.json").read_bytes())
    d[field] = value
    write_manifest(artifact_copy, d)
    with pytest.raises(MigrationError, match=Failure.ARTIFACT_HASH):
        verify(artifact_copy)


@pytest.mark.parametrize("field,value", [("id", "changed"), ("parent", "unknown"),
    ("parent", v.BASELINE), ("file", "../outside.py"), ("starting_state", "unknown"),
    ("target_state", "head"), ("grants", ["PUBLIC"]), ("branch_labels", ["branch"])])
def test_revision_manifest_rejects_unknown_ancestors_branches_and_mappings(artifact_copy, field, value):
    d = json.loads((artifact_copy / "migrations/manifest.json").read_bytes())
    d["revisions"][0][field] = value
    write_manifest(artifact_copy, d)
    with pytest.raises(MigrationError, match=Failure.ARTIFACT_HASH):
        verify(artifact_copy)


@pytest.mark.parametrize("payload", [b'{"format":1,"format":1}', b"[]", b"null", b"{", b"\xff"])
def test_duplicate_keys_invalid_json_redacted(artifact_copy, payload):
    path = artifact_copy / "migrations/manifest.json"
    path.write_bytes(payload)
    # Invalid UTF-8 digest is itself invalid; validator wraps all parser errors.
    mh = "0"*64 if payload == b"\xff" else v.digest(payload)
    with pytest.raises(MigrationError, match=Failure.ARTIFACT_HASH):
        v.validate_artifacts(expected_start=v.BASE, target=v.BASELINE, manifest_hash=mh, revision_hash="0"*64)


@pytest.mark.parametrize("name", ["migrations/versions/0002.py", "migrations/extra.txt", "migrations/versions/branch.py"])
def test_directory_disagreement_and_extra_revisions(artifact_copy, name):
    (artifact_copy / name).write_text("# synthetic only\n", encoding="utf-8")
    with pytest.raises(MigrationError, match=Failure.ARTIFACT_HASH):
        verify(artifact_copy)


@pytest.mark.parametrize("old,new", [
    ('revision = "0001_migration_baseline"', 'revision = "changed"'),
    ('down_revision = None', 'down_revision = "unknown"'),
    ('branch_labels = None', 'branch_labels = ("branch",)'),
    ('depends_on = None', 'depends_on = "unknown"'),
    ('    pass', '    return None'), ('def upgrade():', 'def upgrade(value):'),
    ('def upgrade():', '@unapproved\ndef upgrade():'),
    ('    pass', '    pass\n    pass'),
    ('    raise RuntimeError("Ordinary migration downgrade is prohibited.")', '    pass'),
    ('branch_labels = None', 'branch_labels = None\nbranch_labels = None'),
    ('def upgrade():', 'import os\ndef upgrade():'),
])
def test_rehashed_unapproved_revision_shape_still_rejected(artifact_copy, old, new):
    path = artifact_copy / v.REVISION_FILE
    path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
    d = json.loads((artifact_copy / "migrations/manifest.json").read_bytes())
    d["revisions"][0]["sha256"] = v.digest(path.read_bytes())
    write_manifest(artifact_copy, d)
    with pytest.raises(MigrationError, match=Failure.ARTIFACT_HASH):
        verify(artifact_copy)


def test_rehashed_dependency_declaration_does_not_prove_operational_approval(artifact_copy, monkeypatch):
    from oaf_website import migrate as m, migration_config as c
    path = artifact_copy / "requirements-migrations.txt"
    path.write_text("Alembic==0.0.0\n", encoding="utf-8")
    d = json.loads((artifact_copy / "migrations/manifest.json").read_bytes())
    # Integrity accepts a matching synthetic hash, never approval of new pins.
    d["framework"]["requirements-migrations.txt"] = v.digest(path.read_bytes())
    write_manifest(artifact_copy, d)
    a = verify(artifact_copy)
    monkeypatch.setattr(c.os, "environ", {"OAF_ENV": "testing"})
    with pytest.raises(MigrationError, match=Failure.OPERATIONAL_GATE):
        m.run(m.Request("upgrade", "testing", a.expected_start, a.target, a.manifest_hash, a.revision_hash))


@pytest.mark.parametrize("expected", ["A"*64, "../outside", None, 123])
def test_invalid_artifact_hash_mapping(artifact_copy, expected):
    d = json.loads((artifact_copy / "migrations/manifest.json").read_bytes())
    d["framework"]["requirements.txt"] = expected
    write_manifest(artifact_copy, d)
    with pytest.raises(MigrationError, match=Failure.ARTIFACT_HASH):
        verify(artifact_copy)


def test_symbolic_artifact_rejected_without_windows_symlink_creation(artifact_copy, monkeypatch):
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path.name == "requirements.txt" or original(path))
    with pytest.raises(MigrationError, match=Failure.ARTIFACT_HASH):
        verify(artifact_copy)


def test_missing_manifest_rejected(artifact_copy):
    a = artifacts()
    (artifact_copy / "migrations/manifest.json").unlink()
    with pytest.raises(MigrationError, match=Failure.ARTIFACT_HASH):
        v.validate_artifacts(expected_start=a.expected_start, target=a.target,
                             manifest_hash=a.manifest_hash, revision_hash=a.revision_hash)


def test_baseline_upgrade_no_operations_and_ordinary_downgrade_prohibited():
    namespace = {}
    exec(compile((ROOT / v.REVISION_FILE).read_bytes(), "synthetic-baseline", "exec"), namespace)
    assert namespace["upgrade"]() is None
    with pytest.raises(RuntimeError, match="Ordinary migration downgrade is prohibited"):
        namespace["downgrade"]()
