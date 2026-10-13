"""Fresh public-safe consumer binding probes; no producer or payload execution."""

import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).absolute().parent.parent
sys.path.insert(0, str(ROOT / "bootstrap"))
from release_verifier import verify_release
from acquisition_fixtures import FixtureOwner


# Independent fixed protocol expectation, rather than the verifier's own constant.
PAYLOAD_FILES = (
    "LICENSE",
    "docs/acquisition-candidate.md",
    "docs/enum-provenance.md",
    "docs/field-table.md",
    "docs/offline-binding-candidate.md",
    "docs/specification-candidate.md",
    "docs/validation-candidate.md",
    "src/project_manifest/__init__.py",
    "src/project_manifest/__main__.py",
    "src/project_manifest/acquire.py",
    "src/project_manifest/candidate.py",
    "src/project_manifest/cli.py",
    "src/project_manifest/validation.py",
    "tests/acquisition_fixtures.py",
    "tests/compare_loaders.py",
    "tests/run_corpus.py",
    "tests/test_acquisition.py",
    "tests/test_candidate.py",
    "tests/test_cli.py",
    "tests/test_validation.py",
)
DOMAIN = b"project-manifest-release-table-v1\0"


def canonical(table):
    return (json.dumps(table, ensure_ascii=True, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("ascii")


def expectation(data):
    return hashlib.sha256(DOMAIN + data).hexdigest()


class BindingFixture:
    """The ownership marker stays outside the strictly closed bundle root."""

    def __init__(self, owner):
        self.container = owner.create_root()
        self.root = self.container / "binding"
        self.root.mkdir()
        self.payload = {}
        for path in PAYLOAD_FILES:
            data = ("Synthetic payload bytes for " + path + "\n").encode("ascii")
            self.payload[path] = data
            target = self.root.joinpath(*path.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        self.table = {
            "format": "candidate-binding-1",
            "origin": "jefahnierocks/project-manifest",
            "spec_version": "1",
            "release_id": "candidate-1",
            "source_revision": "a" * 40,
            "python_minimum": "3.11",
            "git_minimum": "2.56.0",
            "files": [{"path": path, "bytes": len(self.payload[path]),
                       "sha256": hashlib.sha256(self.payload[path]).hexdigest()}
                      for path in PAYLOAD_FILES],
        }
        self.write_table()

    def write_table(self, table=None, *, raw=None):
        if table is not None:
            self.table = copy.deepcopy(table)
        self.table_bytes = canonical(self.table) if raw is None else raw
        (self.root / "release.json").write_bytes(self.table_bytes)
        self.expected = expectation(self.table_bytes)

    def replace_payload(self, path, data, *, reseal=False):
        self.payload[path] = data
        self.root.joinpath(*path.split("/")).write_bytes(data)
        if reseal:
            for entry in self.table["files"]:
                if entry["path"] == path:
                    entry["bytes"] = len(data)
                    entry["sha256"] = hashlib.sha256(data).hexdigest()
                    break
            self.write_table()


class ReleaseBindingTests(unittest.TestCase):
    def setUp(self):
        self.owner = FixtureOwner(self)

    def fixture(self):
        self.assertTrue(PAYLOAD_FILES, "Reviewed payload list was not supplied")
        return BindingFixture(self.owner)

    def verify(self, fixture, *, digest=None, root=None):
        return verify_release(fixture.root if root is None else root,
                              expected_digest=fixture.expected if digest is None else digest)

    def accepted(self, result):
        self.assertEqual(result.exit_code, 0, result.diagnostics())
        self.assertEqual(result.findings, ())
        self.assertIsInstance(result.descriptor, dict)
        self.assertIsInstance(result.diagnostics(), dict)
        return result

    def rejected(self, result, *, unavailable=False):
        self.assertEqual(result.exit_code, 2 if unavailable else 1, result.diagnostics())
        self.assertIsInstance(result.findings, tuple)
        self.assertTrue(result.findings)
        self.assertIsNone(result.descriptor)
        self.assertIsInstance(result.diagnostics(), dict)
        return result

    def test_exact_canonical_binding_requires_independent_domain_separated_expectation(self):
        fixture = self.fixture()
        self.assertEqual(tuple(sorted(PAYLOAD_FILES)), PAYLOAD_FILES)
        result = self.accepted(self.verify(fixture))
        self.assertEqual(result.descriptor["source_revision"], "a" * 40)
        self.assertEqual(result.descriptor["files"], fixture.table["files"])
        replay = self.accepted(self.verify(fixture))
        self.assertEqual(replay.descriptor, result.descriptor)
        self.assertEqual(replay.diagnostics(), result.diagnostics())
        self.rejected(self.verify(fixture, digest=hashlib.sha256(fixture.table_bytes).hexdigest()))

    def test_external_digest_mismatch_refuses_self_consistent_candidate_bytes(self):
        fixture = self.fixture()
        self.rejected(self.verify(fixture, digest="0" * 64))
        old_expected = fixture.expected
        fixture.table["source_revision"] = "b" * 40
        fixture.write_table()
        self.rejected(self.verify(fixture, digest=old_expected))
        self.accepted(self.verify(fixture))

    def test_both_supported_full_source_revision_widths_are_bound(self):
        fixture = self.fixture()
        fixture.table["source_revision"] = "b" * 64
        fixture.write_table()
        self.assertEqual(self.accepted(self.verify(fixture)).descriptor["source_revision"], "b" * 64)

    def test_missing_and_malformed_external_expectations_are_unavailable_without_reads(self):
        fixture = self.fixture()
        for digest in (None, "", b"a" * 64, "a" * 63, "a" * 65, "A" * 64,
                       "g" * 64, "synthetic-expected-digest-marker", 1):
            with self.subTest(kind=type(digest).__name__):
                with patch("release_verifier.os.open", side_effect=AssertionError("Missing trust input caused a bundle read")):
                    result = self.rejected(verify_release(fixture.root, expected_digest=digest),
                                           unavailable=True)
                self.assertNotIn("synthetic-expected-digest-marker", json.dumps(result.diagnostics()))

    def test_absent_or_inaccessible_root_is_unavailable_with_value_blind_diagnostics(self):
        fixture = self.fixture()
        missing = fixture.container / "synthetic-missing-root-marker"
        result = self.rejected(self.verify(fixture, root=missing), unavailable=True)
        self.assertNotIn("synthetic-missing-root-marker", json.dumps(result.diagnostics()))
        with patch("release_verifier.os.open", side_effect=PermissionError("synthetic-permission-value-marker")):
            result = self.rejected(self.verify(fixture), unavailable=True)
        self.assertNotIn("synthetic-permission-value-marker", json.dumps(result.diagnostics()))

    def test_unsupported_runtime_is_unavailable_without_payload_access(self):
        fixture = self.fixture()
        with patch("release_verifier.sys.version_info", (3, 10, 99)):
            with patch("release_verifier.os.open", side_effect=AssertionError("Unsupported runtime read the bundle")):
                self.rejected(self.verify(fixture), unavailable=True)

    def test_missing_descriptor_and_each_listed_payload_file_are_tamper(self):
        fixture = self.fixture()
        (fixture.root / "release.json").unlink()
        self.rejected(self.verify(fixture))
        for path in PAYLOAD_FILES:
            with self.subTest(path=path):
                fixture = self.fixture()
                fixture.root.joinpath(*path.split("/")).unlink()
                self.rejected(self.verify(fixture))

    def test_each_normative_document_is_required_in_the_sealed_table(self):
        for path in (value for value in PAYLOAD_FILES if value.startswith("docs/")):
            with self.subTest(path=path):
                fixture = self.fixture()
                fixture.table["files"] = [entry for entry in fixture.table["files"]
                                          if entry["path"] != path]
                fixture.write_table()
                self.rejected(self.verify(fixture))

    def test_payload_byte_change_and_truncation_are_tamper(self):
        for mutation in ("changed", "truncated", "extended"):
            with self.subTest(mutation=mutation):
                fixture = self.fixture()
                path = PAYLOAD_FILES[0]
                original = fixture.payload[path]
                data = (b"x" + original[1:] if mutation == "changed" else
                        original[:-1] if mutation == "truncated" else original + b"x")
                fixture.replace_payload(path, data)
                self.rejected(self.verify(fixture))

    def test_metadata_byte_counts_and_payload_hashes_are_not_advisory(self):
        for key, value in (("bytes", 0), ("bytes", -1), ("bytes", True),
                           ("bytes", 1.0), ("bytes", "synthetic-byte-marker"),
                           ("sha256", "0" * 64), ("sha256", "g" * 64),
                           ("sha256", "a" * 63), ("sha256", "A" * 64)):
            with self.subTest(key=key, kind=type(value).__name__):
                fixture = self.fixture()
                fixture.table["files"][0][key] = value
                fixture.write_table()
                self.rejected(self.verify(fixture))

    def test_payload_list_must_be_sorted_unique_and_closed(self):
        for mutation in ("reversed", "duplicate", "omitted", "extra"):
            with self.subTest(mutation=mutation):
                fixture = self.fixture()
                entries = fixture.table["files"]
                if mutation == "reversed":
                    entries.reverse()
                elif mutation == "duplicate":
                    entries.append(copy.deepcopy(entries[0]))
                elif mutation == "omitted":
                    entries.pop()
                else:
                    entries.append({"path": "synthetic-extra-marker", "bytes": 0,
                                    "sha256": hashlib.sha256(b"").hexdigest()})
                    entries.sort(key=lambda entry: entry["path"])
                fixture.write_table()
                self.rejected(self.verify(fixture))

    def test_unknown_top_level_and_file_keys_are_refused_even_when_resealed(self):
        for where in ("table", "file", "self-digest"):
            with self.subTest(where=where):
                fixture = self.fixture()
                if where == "table":
                    fixture.table["synthetic-unknown-key"] = "synthetic-private-value-marker"
                elif where == "file":
                    fixture.table["files"][0]["synthetic-unknown-key"] = "synthetic-private-value-marker"
                else:
                    fixture.table["digest"] = fixture.expected
                fixture.write_table()
                result = self.rejected(self.verify(fixture))
                self.assertNotIn("synthetic-private-value-marker", json.dumps(result.diagnostics()))
                self.assertNotIn("synthetic-unknown-key", json.dumps(result.diagnostics()))

    def test_missing_required_table_fields_are_invalid(self):
        for field in ("format", "origin", "spec_version", "release_id", "source_revision",
                      "python_minimum", "git_minimum", "files"):
            with self.subTest(field=field):
                fixture = self.fixture()
                fixture.table.pop(field)
                fixture.write_table()
                self.rejected(self.verify(fixture))

    def test_candidate_protocol_values_and_revision_spelling_are_closed(self):
        cases = (("format", "synthetic-format-marker"),
                 ("origin", "synthetic-origin-marker"),
                 ("spec_version", "0.1"), ("spec_version", 1),
                 ("release_id", "synthetic-release-marker"),
                 ("source_revision", "a" * 39), ("source_revision", "a" * 65),
                 ("source_revision", "g" * 40), ("source_revision", "A" * 40),
                 ("source_revision", None),
                 ("python_minimum", "3.10"), ("git_minimum", "2.55.9"))
        for field, value in cases:
            with self.subTest(field=field, kind=type(value).__name__):
                fixture = self.fixture()
                fixture.table[field] = value
                fixture.write_table()
                self.rejected(self.verify(fixture))

    def test_noncanonical_json_and_duplicate_object_keys_are_refused(self):
        for mutation in ("spaces", "no-lf", "extra-lf", "duplicate-key"):
            with self.subTest(mutation=mutation):
                fixture = self.fixture()
                if mutation == "spaces":
                    raw = (json.dumps(fixture.table, sort_keys=True, indent=2) + "\n").encode()
                elif mutation == "no-lf":
                    raw = fixture.table_bytes[:-1]
                elif mutation == "extra-lf":
                    raw = fixture.table_bytes + b"\n"
                else:
                    raw = fixture.table_bytes.replace(b'"format":',
                        b'"format":"candidate-binding-1","format":', 1)
                fixture.write_table(raw=raw)
                self.rejected(self.verify(fixture))

    def test_malformed_and_nonobject_json_are_refused(self):
        for raw in (b"{\n", b"[]\n", b"null\n", b"true\n", b"\xff\n"):
            with self.subTest(kind=raw[:1]):
                fixture = self.fixture()
                fixture.write_table(raw=raw)
                self.rejected(self.verify(fixture))

    def test_traversal_and_absolute_table_paths_are_rejected_before_target_read(self):
        for spelling in ("parent", "absolute", "dot", "empty-component", "backslash",
                         "wrong-case", "trailing-separator"):
            with self.subTest(spelling=spelling):
                fixture = self.fixture()
                outside = fixture.container / "synthetic-never-read-marker"
                outside.write_bytes(b"synthetic-outside-value-marker")
                nested = PAYLOAD_FILES[1]
                paths = {"parent": "../" + outside.name, "absolute": str(outside),
                         "dot": "./" + PAYLOAD_FILES[0],
                         "empty-component": nested.replace("/", "//", 1),
                         "backslash": nested.replace("/", "\\", 1),
                         "wrong-case": PAYLOAD_FILES[0].lower(),
                         "trailing-separator": PAYLOAD_FILES[0] + "/"}
                fixture.table["files"][0]["path"] = paths[spelling]
                fixture.write_table()
                original = os.open
                def guarded_open(path, *args, **kwargs):
                    if not isinstance(path, int) and os.fspath(path) in {str(outside), outside.name}:
                        raise AssertionError("Verifier opened an outside table target")
                    return original(path, *args, **kwargs)
                with patch("release_verifier.os.open", side_effect=guarded_open):
                    result = self.rejected(self.verify(fixture))
                self.assertNotIn("synthetic-outside-value-marker", json.dumps(result.diagnostics()))

    def test_payload_symlink_is_refused_without_opening_target(self):
        fixture = self.fixture()
        leaf = fixture.root.joinpath(*PAYLOAD_FILES[0].split("/"))
        outside = fixture.container / "synthetic-symlink-value-marker"
        outside.write_bytes(fixture.payload[PAYLOAD_FILES[0]])
        leaf.unlink()
        leaf.symlink_to(outside)
        original = os.open
        def guarded_open(path, *args, **kwargs):
            if not isinstance(path, int) and os.fspath(path) in {str(outside), outside.name}:
                raise AssertionError("Verifier opened a payload symlink target")
            return original(path, *args, **kwargs)
        with patch("release_verifier.os.open", side_effect=guarded_open):
            self.rejected(self.verify(fixture))

    def test_root_and_derived_directory_symlinks_are_refused(self):
        fixture = self.fixture()
        root_link = fixture.container / "synthetic-root-link"
        root_link.symlink_to(fixture.root, target_is_directory=True)
        self.rejected(self.verify(fixture, root=root_link))
        fixture = self.fixture()
        directory = fixture.root / "docs"
        outside = fixture.container / "synthetic-docs-target"
        directory.rename(outside)
        directory.symlink_to(outside, target_is_directory=True)
        original = os.open
        def guarded_open(path, *args, **kwargs):
            if not isinstance(path, int) and os.fspath(path) in {str(outside), outside.name}:
                raise AssertionError("Verifier opened a redirected payload directory")
            return original(path, *args, **kwargs)
        with patch("release_verifier.os.open", side_effect=guarded_open):
            self.rejected(self.verify(fixture))

    def test_payload_and_descriptor_hardlinks_are_refused_even_with_matching_bytes(self):
        for path in (PAYLOAD_FILES[0], "release.json"):
            with self.subTest(path=path):
                fixture = self.fixture()
                leaf = fixture.root.joinpath(*path.split("/"))
                outside = fixture.container / "synthetic-hardlink-target"
                outside.write_bytes(leaf.read_bytes())
                leaf.unlink()
                os.link(outside, leaf)
                self.assertEqual(leaf.stat().st_nlink, 2)
                self.rejected(self.verify(fixture))

    def test_descriptor_symlink_is_refused_without_reading_target(self):
        fixture = self.fixture()
        table = fixture.root / "release.json"
        outside = fixture.container / "synthetic-descriptor-target"
        outside.write_bytes(table.read_bytes())
        table.unlink()
        table.symlink_to(outside)
        original = os.open
        def guarded_open(path, *args, **kwargs):
            if not isinstance(path, int) and os.fspath(path) in {str(outside), outside.name}:
                raise AssertionError("Verifier opened a descriptor symlink target")
            return original(path, *args, **kwargs)
        with patch("release_verifier.os.open", side_effect=guarded_open):
            self.rejected(self.verify(fixture))

    def test_payload_fifo_is_refused_before_blocking_open(self):
        fixture = self.fixture()
        leaf = fixture.root.joinpath(*PAYLOAD_FILES[0].split("/"))
        leaf.unlink()
        os.mkfifo(leaf)
        original_os = os.open
        original_builtin = open
        original_path = Path.read_bytes
        def target(path):
            return not isinstance(path, int) and os.fspath(path) in {str(leaf), leaf.name}
        def guarded_os(path, *args, **kwargs):
            if target(path):
                raise AssertionError("Verifier attempted a blocking FIFO open")
            return original_os(path, *args, **kwargs)
        def guarded_builtin(path, *args, **kwargs):
            if target(path):
                raise AssertionError("Verifier attempted a blocking FIFO open")
            return original_builtin(path, *args, **kwargs)
        def guarded_path(path):
            if target(path):
                raise AssertionError("Verifier attempted a blocking FIFO read")
            return original_path(path)
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch("release_verifier.os.open", side_effect=guarded_os))
            stack.enter_context(patch("builtins.open", side_effect=guarded_builtin))
            stack.enter_context(patch("pathlib.Path.read_bytes", new=guarded_path))
            self.rejected(self.verify(fixture))

    def test_unlisted_files_and_empty_directories_are_not_ignored(self):
        for kind, parent in (("file", ""), ("directory", ""),
                             ("file", "docs"), ("directory", "src/project_manifest")):
            with self.subTest(kind=kind, parent=parent):
                fixture = self.fixture()
                extra = fixture.root / parent / "synthetic-unlisted-marker"
                if kind == "file":
                    extra.write_bytes(b"synthetic-extra-value-marker")
                else:
                    extra.mkdir()
                self.rejected(self.verify(fixture))

    def test_source_checkout_markers_are_refused_without_reading_git_config(self):
        fixture = self.fixture()
        git = fixture.root / ".git"
        git.mkdir()
        source_config = git / "config"
        source_config.write_bytes(b"synthetic-source-config-value-marker\n")
        (fixture.root / "pyproject.toml").write_bytes(b"synthetic-source-project-marker\n")
        original = os.open
        def guarded_open(path, *args, **kwargs):
            if not isinstance(path, int) and os.fspath(path) in {str(source_config), "config"}:
                raise AssertionError("Verifier read a source checkout config")
            return original(path, *args, **kwargs)
        with patch("release_verifier.os.open", side_effect=guarded_open):
            result = self.rejected(self.verify(fixture))
        self.assertNotIn("synthetic-source-config-value-marker", json.dumps(result.diagnostics()))

    def test_byte_budgets_refuse_resealed_oversized_files_and_aggregate_payload(self):
        fixture = self.fixture()
        fixture.replace_payload(PAYLOAD_FILES[0], b"x" * (1024 * 1024), reseal=True)
        self.accepted(self.verify(fixture))
        fixture.replace_payload(PAYLOAD_FILES[0], b"x" * (1024 * 1024 + 1), reseal=True)
        self.rejected(self.verify(fixture))
        fixture = self.fixture()
        for path in PAYLOAD_FILES[:17]:
            fixture.replace_payload(path, b"x" * (1024 * 1024), reseal=True)
        self.assertGreater(sum(entry["bytes"] for entry in fixture.table["files"]),
                           16 * 1024 * 1024)
        self.rejected(self.verify(fixture))

    def test_table_budget_is_enforced_before_parsing_large_untrusted_json(self):
        fixture = self.fixture()
        raw = b'{"synthetic-table-marker":"' + b"x" * (64 * 1024) + b'"}\n'
        fixture.write_table(raw=raw)
        result = self.rejected(self.verify(fixture))
        self.assertNotIn("synthetic-table-marker", json.dumps(result.diagnostics()))

    def test_file_container_and_entry_shapes_are_closed(self):
        for value in (None, {}, "synthetic-file-list-marker", [None], [1], [[]]):
            with self.subTest(kind=type(value).__name__):
                fixture = self.fixture()
                fixture.table["files"] = value
                fixture.write_table()
                self.rejected(self.verify(fixture))
        for field in ("path", "bytes", "sha256"):
            with self.subTest(missing_file_field=field):
                fixture = self.fixture()
                fixture.table["files"][0].pop(field)
                fixture.write_table()
                self.rejected(self.verify(fixture))

    def test_verification_leaves_bundle_paths_bytes_and_file_identity_unchanged(self):
        fixture = self.fixture()
        def snapshot():
            result = {}
            for path in fixture.root.rglob("*"):
                info = path.lstat()
                identity = (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
                            info.st_size, info.st_mtime_ns, info.st_ctime_ns)
                digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
                result[path.relative_to(fixture.root).as_posix()] = (identity, digest)
            return result
        before = snapshot()
        self.accepted(self.verify(fixture))
        self.assertEqual(snapshot(), before)

    def test_payload_changed_during_read_cannot_return_verified_descriptor(self):
        fixture = self.fixture()
        leaf = fixture.root / PAYLOAD_FILES[0]
        initial = leaf.stat()
        identity = (initial.st_dev, initial.st_ino)
        original_read = os.read
        mutated = False
        marker = "synthetic-concurrent-read-marker"
        def concurrent_read(fd, maximum):
            nonlocal mutated
            info = os.fstat(fd)
            data = original_read(fd, maximum)
            if data and not mutated and (info.st_dev, info.st_ino) == identity:
                mutated = True
                replacement = marker.encode().ljust(len(fixture.payload[PAYLOAD_FILES[0]]), b"x")
                leaf.write_bytes(replacement[:len(fixture.payload[PAYLOAD_FILES[0]])])
            return data
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with patch("release_verifier.os.read", side_effect=concurrent_read):
                result = self.rejected(self.verify(fixture))
        self.assertTrue(mutated, "Named payload did not reach the controlled read")
        report = json.dumps(result.diagnostics())
        self.assertNotIn(marker, report)
        self.assertNotIn(str(fixture.root), report)
        self.assertEqual(stdout.getvalue() + stderr.getvalue(), "")

    def test_payload_path_replaced_after_open_cannot_redirect_bound_read(self):
        fixture = self.fixture()
        leaf = fixture.root / PAYLOAD_FILES[0]
        initial = leaf.stat()
        identity = (initial.st_dev, initial.st_ino)
        outside = fixture.container / "synthetic-concurrent-outside-target"
        marker = "synthetic-concurrent-outside-value-marker"
        outside.write_bytes(marker.encode())
        outside_info = outside.stat()
        outside_identity = (outside_info.st_dev, outside_info.st_ino)
        original_open, original_read = os.open, os.read
        replaced = False
        def concurrent_open(path, *args, **kwargs):
            nonlocal replaced
            if not isinstance(path, int) and os.fspath(path) in {str(outside), outside.name}:
                raise AssertionError("Verifier opened an outside replacement target")
            fd = original_open(path, *args, **kwargs)
            info = os.fstat(fd)
            opened = (info.st_dev, info.st_ino)
            if opened == outside_identity:
                os.close(fd)
                raise AssertionError("Verifier followed the replaced payload path")
            if not replaced and opened == identity:
                replaced = True
                leaf.unlink()
                leaf.symlink_to(outside)
            return fd
        def guarded_read(fd, maximum):
            info = os.fstat(fd)
            if (info.st_dev, info.st_ino) == outside_identity:
                raise AssertionError("Verifier read outside replacement bytes")
            return original_read(fd, maximum)
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with patch("release_verifier.os.open", side_effect=concurrent_open):
                with patch("release_verifier.os.read", side_effect=guarded_read):
                    result = self.rejected(self.verify(fixture))
        self.assertTrue(replaced, "Named payload did not reach the controlled open")
        report = json.dumps(result.diagnostics())
        self.assertNotIn(marker, report)
        self.assertNotIn(str(outside), report)
        self.assertEqual(stdout.getvalue() + stderr.getvalue(), "")

    def test_bundle_root_rebound_during_inspection_cannot_authorize_stale_namespace(self):
        fixture = self.fixture()
        leaf = fixture.root / PAYLOAD_FILES[0]
        initial = leaf.stat()
        identity = (initial.st_dev, initial.st_ino)
        saved_root = fixture.container / "synthetic-original-binding"
        outside = fixture.container / "synthetic-root-rebound-target"
        outside.mkdir()
        outside_directory_info = outside.stat()
        outside_directory_identity = (outside_directory_info.st_dev, outside_directory_info.st_ino)
        marker = "synthetic-root-rebound-value-marker"
        outside_leaf = outside / "synthetic-never-read"
        outside_leaf.write_bytes(marker.encode())
        outside_info = outside_leaf.stat()
        outside_identity = (outside_info.st_dev, outside_info.st_ino)
        original_open, original_read = os.open, os.read
        rebound = False
        def concurrent_open(path, *args, **kwargs):
            nonlocal rebound
            if not isinstance(path, int) and os.fspath(path) in {
                    str(outside), outside.name, str(outside_leaf), outside_leaf.name}:
                raise AssertionError("Verifier entered a rebound outside namespace")
            fd = original_open(path, *args, **kwargs)
            info = os.fstat(fd)
            if (info.st_dev, info.st_ino) in {outside_identity, outside_directory_identity}:
                os.close(fd)
                raise AssertionError("Verifier opened rebound outside bytes")
            if not rebound and (info.st_dev, info.st_ino) == identity:
                rebound = True
                fixture.root.rename(saved_root)
                fixture.root.symlink_to(outside, target_is_directory=True)
            return fd
        def guarded_read(fd, maximum):
            info = os.fstat(fd)
            if (info.st_dev, info.st_ino) == outside_identity:
                raise AssertionError("Verifier read rebound outside bytes")
            return original_read(fd, maximum)
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with patch("release_verifier.os.open", side_effect=concurrent_open):
                with patch("release_verifier.os.read", side_effect=guarded_read):
                    result = self.rejected(self.verify(fixture))
        self.assertTrue(rebound, "Named payload did not reach the controlled inspection")
        self.assertTrue(saved_root.is_dir())
        self.assertTrue(fixture.root.is_symlink())
        report = json.dumps(result.diagnostics())
        self.assertNotIn(marker, report)
        self.assertNotIn(str(outside), report)
        self.assertEqual(stdout.getvalue() + stderr.getvalue(), "")

    def test_payload_modules_are_verified_as_bytes_without_import_side_effects(self):
        fixture = self.fixture()
        sentinel = fixture.container / "synthetic-import-executed"
        poison = ("open(" + repr(str(sentinel)) + ", 'wb').write(b'synthetic-import-marker')\n"
                  "raise RuntimeError('synthetic-payload-execution-marker')\n").encode()
        python_paths = [path for path in PAYLOAD_FILES if path.endswith(".py")]
        self.assertTrue(python_paths)
        for path in python_paths:
            fixture.replace_payload(path, poison, reseal=True)
        original = __import__
        def guarded_import(name, *args, **kwargs):
            if name == "project_manifest" or name.startswith("project_manifest."):
                raise AssertionError("Verifier imported untrusted payload")
            return original(name, *args, **kwargs)
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with patch("builtins.__import__", side_effect=guarded_import):
                with patch("importlib.util.spec_from_file_location", side_effect=AssertionError("Verifier loaded payload code")):
                    self.accepted(self.verify(fixture))
        self.assertFalse(sentinel.exists())
        self.assertEqual(stdout.getvalue() + stderr.getvalue(), "")

    def test_diagnostics_and_repr_never_echo_untrusted_table_or_path_values(self):
        marker = "synthetic-binding-nondisclosure-marker"
        fixture = self.fixture()
        fixture.table["origin"] = marker
        fixture.write_table()
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = self.rejected(self.verify(fixture))
        self.assertNotIn(marker, json.dumps(result.diagnostics()))
        self.assertNotIn(marker, repr(result))
        self.assertEqual(stdout.getvalue() + stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
