"""Two disjoint canonical offline pytest shards and strict coverage aggregation."""

import argparse
import ast
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".pytest_cache/ci"
SHARDS = 2


def require(condition, code):
    if not condition:
        raise RuntimeError(code)


def canonical_files():
    # Read the existing allowlist without importing (and prematurely arming)
    # the early isolation plugin. New canonical files require its review too.
    tree = ast.parse((ROOT / "tests/migration_offline.py").read_text(encoding="utf-8"))
    value = next(node.value.args[0] for node in tree.body
                 if isinstance(node, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == "APPROVED_TESTS" for t in node.targets))
    files = sorted(ast.literal_eval(value))
    require(set(files) == {p.relative_to(ROOT).as_posix() for p in (ROOT / "tests").glob("test_*.py")},
            "canonical_file_inventory_mismatch")
    return files


def partition(nodeids, shard):
    require(shard in range(SHARDS), "invalid_shard")
    require(bool(nodeids) and nodeids == sorted(set(nodeids)), "invalid_collection")
    return nodeids[shard::SHARDS]


class Shard:
    def __init__(self, index):
        self.index = index
        self.collected = []
        self.selected = []
        self.passed = {phase: [] for phase in ("setup", "call", "teardown")}
        self.unsuccessful = []

    def pytest_collection_modifyitems(self, config, items):
        ordered = sorted(items, key=lambda item: item.nodeid)
        self.collected = [item.nodeid for item in ordered]
        self.selected = partition(self.collected, self.index)
        keep = set(self.selected)
        config.hook.pytest_deselected(items=[item for item in ordered if item.nodeid not in keep])
        items[:] = [item for item in ordered if item.nodeid in keep]

    def pytest_runtest_logreport(self, report):
        if report.passed and not getattr(report, "wasxfail", False):
            self.passed[report.when].append(report.nodeid)
        else:
            self.unsuccessful.append(report.nodeid)


def write_json(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, sort_keys=True)
        stream.write("\n")


def unpack(arc):
    # coverage 7.13.2 C tracer packs arcs. Same decoding as accepted measurement.
    if not isinstance(arc, int):
        return list(arc)
    first, second = arc & 0xFFFFFFF, (arc >> 28) & 0xFFFFFFF
    return [-first if arc & (1 << 56) else first, -second if arc & (1 << 57) else second]


def run_shard(index, *, collect=False):
    import pytest
    shard = Shard(index)
    destination = OUTPUT / ("collect" if collect else "run") / f"shard-{index}"
    require(not destination.exists(), "output_already_exists")
    cov = None
    if not collect:
        import coverage
        require(coverage.__version__ == "7.13.2", "coverage_version_mismatch")
        cov = coverage.Coverage(branch=True, config_file=False, source=["oaf_website"])
        cov.start()
    try:
        code = int(pytest.main(["-p", "migration_offline", "-q", "-x", "--tb=short",
                              *(["--collect-only", "--quiet"] if collect else []), *canonical_files()],
                              plugins=[shard]))
    finally:
        if cov is not None:
            cov.stop()
    complete = (not shard.unsuccessful and all(
        Counter(shard.passed[phase]) == Counter(shard.selected) for phase in shard.passed))
    if code == 0 and (not shard.selected or (not collect and not complete)):
        code = 1
    write_json(destination / "manifest.json", dict(
        format=1, shard=index, shards=SHARDS, mode="collect" if collect else "run",
        collected=shard.collected, selected=shard.selected, passed=shard.passed,
        unsuccessful=shard.unsuccessful, exit_code=code))
    if cov is not None:
        # Do not call get_data/save in the guarded process: even SQLite coverage
        # metadata is denied there. Export arcs as in the accepted canonical run.
        arcs = {Path(name).resolve().relative_to(ROOT).as_posix(): sorted(
            [unpack(arc) for arc in values])
            for name, values in cov._collector.data.items()}
        write_json(destination / "arcs.json", dict(format=1, shard=index, arcs=arcs))
    print(f"Shard {index}: collected={len(shard.collected)} selected={len(shard.selected)} exit={code}",
          flush=True)
    return code


def verify_manifests(documents):
    require(len(documents) == SHARDS, "two_manifests_required")
    canonical = documents[0]["collected"]
    assigned = []
    for index, document in enumerate(documents):
        require(document["format"] == 1 and document["shards"] == SHARDS
                and document["shard"] == index and document["mode"] == "run"
                and document["exit_code"] == 0, "shard_not_successful")
        require(document["collected"] == canonical, "collections_differ")
        selected = partition(canonical, index)
        require(bool(selected) and document["selected"] == selected, "shard_partition_mismatch")
        require(not document["unsuccessful"] and set(document["passed"]) == {"setup", "call", "teardown"}
                and all(Counter(document["passed"][phase]) == Counter(selected)
                        for phase in ("setup", "call", "teardown")), "test_not_fully_passed")
        assigned.extend(selected)
    require(Counter(assigned) == Counter(canonical), "suite_not_exactly_once")
    return len(canonical)


def combine():
    import coverage
    require(coverage.__version__ == "7.13.2", "coverage_version_mismatch")
    directory = OUTPUT / "downloads"
    expected = {f"linux-shard-{index}" for index in range(SHARDS)}
    require({p.name for p in directory.iterdir()} == expected, "two_artifacts_required")
    documents, payloads = [], []
    for index in range(SHARDS):
        artifact = directory / f"linux-shard-{index}"
        require({p.name for p in artifact.iterdir()} == {"manifest.json", "arcs.json"},
                "artifact_files_mismatch")
        documents.append(json.loads((artifact / "manifest.json").read_text(encoding="utf-8")))
        payload = json.loads((artifact / "arcs.json").read_text(encoding="utf-8"))
        require(payload["format"] == 1 and payload["shard"] == index
                and any(payload["arcs"].values()),
                "invalid_coverage_artifact")
        payloads.append(payload)
    count = verify_manifests(documents)
    # Metadata-only process: no application imports, tests, credentials or DBs.
    cov = coverage.Coverage(branch=True, config_file=False, source=["oaf_website"],
                            data_file=str(OUTPUT / ".coverage"))
    data = cov.get_data()
    data.erase()
    for payload in payloads:
        normalized = {}
        for name, arcs in payload["arcs"].items():
            path = Path(name)
            require(not path.is_absolute() and ".." not in path.parts
                    and path.parts[0] == "oaf_website" and path.suffix == ".py"
                    and (ROOT / path).is_file(), "invalid_coverage_source")
            require(all(isinstance(arc, list) and len(arc) == 2
                        and all(type(line) is int for line in arc) for arc in arcs),
                    "invalid_coverage_arcs")
            normalized[str((ROOT / path).resolve())] = [tuple(arc) for arc in arcs]
        data.add_arcs(normalized)
    require(data.has_arcs(), "branch_coverage_required")
    cov.save()
    cov.report(show_missing=True)
    cov.json_report(outfile=str(OUTPUT / "coverage.json"))
    totals = json.loads((OUTPUT / "coverage.json").read_text(encoding="utf-8"))["totals"]
    require(totals["num_statements"] > 0 and totals["num_branches"] > 0
            and totals["covered_lines"] == totals["num_statements"]
            and totals["covered_branches"] == totals["num_branches"]
            and totals["missing_lines"] == totals["missing_branches"] == 0,
            "statement_and_branch_coverage_below_100")
    print(f"PASS: {count} tests exactly once; statement and branch coverage both 100%.", flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("collect", "shard", "combine"))
    parser.add_argument("--shard", type=int, choices=range(SHARDS))
    options = parser.parse_args()
    require(Path.cwd().resolve() == ROOT, "run_from_repository_root")
    if options.action == "combine":
        require(options.shard is None, "combine_has_no_shard")
        return combine()
    require(options.shard is not None, "shard_required")
    return run_shard(options.shard, collect=options.action == "collect")


if __name__ == "__main__":
    raise SystemExit(main())
