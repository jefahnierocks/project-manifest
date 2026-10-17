"""Origin declaration checks using independently pinned Release 1 bytes only."""

import sys

if __name__ == "__main__" and not (
    sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
):
    sys.stdout.write('{"exit_code":2,"finding":"ISOLATED_RUNTIME_REQUIRED"}\n')
    raise SystemExit(2)

import argparse
from contextlib import contextmanager
import hashlib
import importlib.abc
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import tempfile

ROOT = Path(__file__).absolute().parent.parent
SOURCE_REVISION = "56e3920089726e585eaa0fd7f4dc94e6938a1e0c"
BOOTSTRAP_SHA256 = "2ccf58e0da97bbbd9dae173d1cca047d465c4a2d950ee6e56052309a9689cf4f"
TABLE_SHA256 = "f7ff9dd0972af5d3a6a3348c3e092de1a6acd97fa3975e13e522cf80ce5e7df2"
VENDOR = "vendor/project-manifest/"
BOOTSTRAP = VENDOR + "bootstrap/release_verifier.py"
BUNDLE = VENDOR + "release-1/"
MODULES = {
    "project_manifest": "src/project_manifest/__init__.py",
    **{"project_manifest." + name: "src/project_manifest/" + name + ".py"
       for name in ("__main__", "candidate", "validation", "acquire", "cli")},
}
PAYLOAD = tuple(sorted((
    "LICENSE", "docs/specification-candidate.md", "docs/field-table.md",
    "docs/enum-provenance.md", "docs/validation-candidate.md",
    "docs/acquisition-candidate.md", "docs/offline-binding-candidate.md",
    *MODULES.values(), "tests/acquisition_fixtures.py", "tests/test_candidate.py",
    "tests/test_validation.py", "tests/test_acquisition.py", "tests/test_cli.py",
    "tests/run_corpus.py", "tests/compare_loaders.py",
)))
MAX_BYTES = 1_048_576


class Refusal(Exception):
    def __init__(self, code, exit_code=1):
        self.code, self.exit_code = code, exit_code


def require(condition, code, exit_code=1):
    if not condition:
        raise Refusal(code, exit_code)


def capture(path):
    """No-follow bounded read; retained bytes, never the pathname, are executed."""
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parts = path.parts[1:]
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        leaf = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            before = os.fstat(leaf)
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, "VENDOR_FILE_TYPE")
            require(before.st_size <= MAX_BYTES, "VENDOR_BYTE_BOUND")
            chunks, size = [], 0
            while True:
                chunk = os.read(leaf, min(65536, MAX_BYTES + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                require(size <= MAX_BYTES, "VENDOR_BYTE_BOUND")
            key = lambda info: (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
                                info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            require(key(before) == key(os.fstat(leaf))
                    == key(os.stat(parts[-1], dir_fd=fd, follow_symlinks=False))
                    and size == before.st_size, "VENDOR_CHANGED")
            return b"".join(chunks)
        finally:
            os.close(leaf)
    finally:
        os.close(fd)


class CapturedModules(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Closed import namespace backed by already authenticated in-memory bytes."""

    def __init__(self, sources, package=None):
        self.sources, self.package = sources, package

    def find_spec(self, fullname, path=None, target=None):
        if fullname in self.sources:
            return importlib.util.spec_from_loader(fullname, self,
                                                   is_package=fullname == self.package)
        if self.package and fullname.startswith(self.package + "."):
            raise ImportError("Undeclared released module")
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        exec(compile(self.sources[module.__name__], "<released-module>", "exec"), module.__dict__)

    @contextmanager
    def installed(self):
        names = lambda: [name for name in sys.modules if name in self.sources
                         or (self.package and name.startswith(self.package + "."))]
        require(not names(), "IMPORT_NAMESPACE_OCCUPIED", 2)
        sys.meta_path.insert(0, self)
        try:
            yield
        finally:
            sys.meta_path.remove(self)
            for name in names():
                del sys.modules[name]


def verified_runtime(root):
    bootstrap = capture(root / BOOTSTRAP)
    require(hashlib.sha256(bootstrap).hexdigest() == BOOTSTRAP_SHA256, "BOOTSTRAP_DIGEST")
    with CapturedModules({"_origin_release_bootstrap": bootstrap}).installed():
        verifier = __import__("_origin_release_bootstrap")
        original = verifier.verify_release(str(root / BUNDLE), expected_digest=TABLE_SHA256,
                                           expected_format="project-manifest-release-1")
        require(original.exit_code == 0, "RELEASE_BINDING")
        captured = {name: capture(root / BUNDLE / name) for name in (*PAYLOAD, "release.json")}
        with tempfile.TemporaryDirectory(prefix="project-manifest-self-binding-") as temporary:
            bundle = Path(temporary).resolve() / "bundle"
            bundle.mkdir()
            for name, data in captured.items():
                target = bundle / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            result = verifier.verify_release(str(bundle), expected_digest=TABLE_SHA256,
                                             expected_format="project-manifest-release-1")
            require(result.exit_code == 0, "RELEASE_BINDING")
            descriptor = result.descriptor
            require(descriptor["source_revision"] == SOURCE_REVISION
                    and tuple(row["path"] for row in descriptor["files"]) == PAYLOAD,
                    "RELEASE_IDENTITY")
            rows = {row["path"]: row for row in descriptor["files"]}
            for name, data in captured.items():
                if name == "release.json":
                    continue
                require(len(data) == rows[name]["bytes"]
                        and hashlib.sha256(data).hexdigest() == rows[name]["sha256"],
                        "CAPTURE_DIGEST")
    return {module: captured[path] for module, path in MODULES.items()}


def native_declaration(record):
    """Project-owned conformance; grammar and semantics belong only to Release 1."""
    expected_commands = {role: None for role in
                         ("setup", "check", "test", "build", "dev", "format_check", "format_write")}
    expected_commands["check"] = {"runner": "mise", "target": "check"}
    development = record["development"]
    require(development == {
        "platforms": ["macos-arm64", "linux-x86_64"], "commands": expected_commands,
        "environment": {"owner": "none", "template": None, "secret_launcher": None},
        "stacks": {}, "host_requirements": [],
    }, "NATIVE_DECLARATION")
    require(record["project"] == {"id": "project-manifest", "display_name": "Project Manifest",
                                    "owner_entity": "jefahnierocks"}
            and record["role"] == "canonical" and record["canonical"] is None
            and record["peers"] == [] and record["authority"]["status_of_record"] == "STATUS.md",
            "ORIGIN_DECLARATION")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-date", required=True)
    parser.add_argument("--git-common-dir", required=True)
    parser.add_argument("--worktree-sha256", required=True)
    parser.add_argument("--staged-sha256", required=True)
    parser.add_argument("--rev")
    args = parser.parse_args(argv)
    report = {"scope": "origin-self-adoption-release-1", "exit_code": 2,
              "complete_v1_validity": "not_checked", "runtime_acceptance": "not_checked",
              "source_revision": SOURCE_REVISION, "table_sha256": TABLE_SHA256,
              "bootstrap_sha256": BOOTSTRAP_SHA256, "observations": []}
    try:
        require(all(re.fullmatch(r"[0-9a-f]{64}", digest) for digest in
                    (args.worktree_sha256, args.staged_sha256)), "SNAPSHOT_DIGEST", 2)
        require(args.rev is None or re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", args.rev),
                "REVISION_IDENTITY", 2)
        sources = verified_runtime(ROOT)
        with CapturedModules(sources, "project_manifest").installed():
            observer = __import__("project_manifest.acquire", fromlist=["*"])
            for mode, digest in (("worktree", args.worktree_sha256),
                                 ("staged", args.staged_sha256)) + (
                                     (("rev", args.staged_sha256),) if args.rev else ()):
                result = observer.observe_released_repository(
                    str(ROOT), mode=mode, reference_date=args.reference_date,
                    common_dir=args.git_common_dir, rev=args.rev if mode == "rev" else None)
                report["observations"].append(result.diagnostics)
                require(result.exit_code == 0, "RELEASED_OBSERVATION", result.exit_code)
                require(result.diagnostics["manifest_sha256"] == digest, "SNAPSHOT_CHANGED")
                native_declaration(result.record)
        # The outer source gate binds the native mise bytes and command effects.
        # This child establishes only released declaration checks and agreement
        # with the expected project declaration; it cannot approve the task.
        report.update(exit_code=0, declaration_checks="passed",
                      declared_native_contract="matched", native_conformance="not_checked")
    except Refusal as error:
        report.update(exit_code=error.exit_code, finding=error.code)
    except (OSError, ValueError, KeyError, TypeError, ImportError):
        report.update(exit_code=2, finding="SELF_ADOPTION_UNAVAILABLE")
    print(json.dumps(report, sort_keys=True))
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
