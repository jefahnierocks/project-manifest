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

    def released_fixture(self):
        fixture = self.fixture()
        fixture.table.update(format="project-manifest-release-1", release_id="1",
                             observation_protocol="project-manifest-git-observation-1")
        fixture.write_table()
        return fixture

    def verify_released(self, fixture, **kwargs):
        return verify_release(fixture.root, expected_digest=fixture.expected,
                              expected_format="project-manifest-release-1", **kwargs)

    def test_released_profile_binds_closed_nine_fields_without_approving_itself(self):
        fixture = self.released_fixture()
        result = self.accepted(self.verify_released(fixture))
        self.assertEqual(set(result.descriptor),
                         {"format", "origin", "spec_version", "release_id", "source_revision",
                          "python_minimum", "git_minimum", "observation_protocol", "files"})
        self.assertEqual(result.descriptor["format"], "project-manifest-release-1")
        self.assertEqual(result.descriptor["release_id"], "1")
        self.assertEqual(result.descriptor["observation_protocol"], "project-manifest-git-observation-1")
        self.assertEqual(result.diagnostics()["scope"], "project-manifest-release-byte-binding-1")
        self.assertEqual(result.diagnostics()["release_approval"], "not_checked")
        self.assertEqual(result.diagnostics()["complete_v1_validity"], "not_checked")
        self.assertEqual(tuple(row["path"] for row in result.descriptor["files"]), PAYLOAD_FILES)
        self.assertNotIn("runtime_allowlist", result.descriptor)

    def test_candidate_and_released_profiles_never_fall_back_to_each_other(self):
        candidate, released = self.fixture(), self.released_fixture()
        result = self.rejected(self.verify_released(candidate))
        self.assertEqual(result.findings, ("TABLE_IDENTITY",))
        result = self.rejected(self.verify(released))
        self.assertEqual(result.findings, ("TABLE_IDENTITY",))
        self.assertEqual(self.accepted(self.verify(candidate)).diagnostics()["scope"],
                         "candidate-offline-byte-binding")

    def test_unknown_expected_profile_is_unavailable_before_any_read(self):
        for value in ("other", "synthetic-raw-profile", None, False, [], {}):
            with self.subTest(value=type(value).__name__), \
                 patch("release_verifier.os.open", side_effect=AssertionError("Unqualified profile read")):
                result = verify_release("/synthetic/unread", expected_digest="a" * 64, expected_format=value)
                self.rejected(result, unavailable=True)
                self.assertEqual(result.findings, ("BINDING_PROTOCOL",))
                self.assertNotIn("synthetic-raw", json.dumps(result.diagnostics()))
                self.assertIsNone(result.binding_format)

    def test_released_headers_keys_and_every_payload_row_remain_closed(self):
        for key, value in (("format", "candidate-binding-1"), ("origin", "other/origin"),
                           ("spec_version", "2"), ("release_id", "candidate-1"),
                           ("python_minimum", "3.10"), ("git_minimum", "2.55.0"),
                           ("observation_protocol", "candidate-git-observation")):
            with self.subTest(header=key):
                fixture = self.released_fixture()
                fixture.table[key] = value
                fixture.write_table()
                self.assertEqual(self.rejected(self.verify_released(fixture)).findings, ("TABLE_IDENTITY",))
        for key in ("format", "origin", "spec_version", "release_id", "source_revision",
                    "python_minimum", "git_minimum", "observation_protocol", "files"):
            with self.subTest(missing=key):
                fixture = self.released_fixture()
                del fixture.table[key]
                fixture.write_table()
                self.assertEqual(self.rejected(self.verify_released(fixture)).findings, ("TABLE_FORMAT",))
        fixture = self.released_fixture()
        fixture.table["approved"] = True
        fixture.write_table()
        self.assertEqual(self.rejected(self.verify_released(fixture)).findings, ("TABLE_FORMAT",))
        for path in PAYLOAD_FILES:
            with self.subTest(payload=path):
                fixture = self.released_fixture()
                fixture.root.joinpath(*path.split("/")).unlink()
                self.rejected(self.verify_released(fixture))

    def test_released_profile_keeps_external_expectation_tamper_and_no_import_boundary(self):
        fixture = self.released_fixture()
        with patch("builtins.__import__", side_effect=AssertionError("Payload import attempted")):
            self.accepted(self.verify_released(fixture))
        result = verify_release(fixture.root, expected_digest="0" * 64,
                                expected_format="project-manifest-release-1")
        self.assertEqual(self.rejected(result).findings, ("EXPECTED_DIGEST",))
        fixture.replace_payload("src/project_manifest/acquire.py", b"Synthetic changed bytes\n")
        self.assertEqual(self.rejected(self.verify_released(fixture)).findings, ("PAYLOAD_DIGEST",))

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

class AssemblyTests(unittest.TestCase):
    """Owned synthetic origin graphs; no actual source bundle or release."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        name = "origin_assembly_test_subject"
        spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/assemble-release.py")
        cls.assembly = importlib.util.module_from_spec(spec)
        sys.modules[name] = cls.assembly
        spec.loader.exec_module(cls.assembly)

    def setUp(self):
        self.owner = FixtureOwner(self)

    def fixture(self, *, object_format="sha1", changed=None):
        from acquisition_fixtures import FileSpec, GitFixture
        entries = {name: FileSpec("100644", ("Synthetic fixed bytes for " + name + "\n").encode())
                   for name in PAYLOAD_FILES}
        entries[".gitignore"] = FileSpec("100644", b"/build/\n/dist/\nprivate/\n*.pyc\n")
        if changed:
            entries.update(changed)
        fixture = GitFixture(self.owner, object_format=object_format).seed(entries)
        (fixture.path / "build").mkdir()
        (fixture.path / "dist").mkdir()
        return fixture

    def assemble(self, fixture, *, parent="build", revision=None):
        return self.assembly.assemble_candidate(str(fixture.path),
            expected_revision=fixture.head if revision is None else revision,
            output_parent=str(fixture.path / parent))

    def bundle(self, fixture, result, parent="build"):
        self.assertEqual(result.exit_code, 0, result.diagnostics())
        self.assertEqual(result.code, "CANDIDATE_FINALIZED")
        self.assertEqual(result.source_revision, fixture.head)
        self.assertEqual(result.tree_oid, fixture.tree)
        self.assertEqual(result.diagnostics()["release_approval"], "not_checked")
        self.assertEqual(result.diagnostics()["complete_v1_validity"], "not_checked")
        self.assertNotIn("paths", result.diagnostics())
        return fixture.path / parent / result.bundle_name

    def test_precommit_capture_source_and_parent_cleanup_failures_never_finalize(self):
        for selection in ("capture", "source", "parent"):
            with self.subTest(selection=selection):
                fixture = self.fixture()
                temporary = self.assembly.tempfile.TemporaryDirectory
                close_owned = self.assembly._close_owned_fds
                real_close = self.assembly.os.close
                close_calls = 0
                attempted = []
                target = None
                class Capture:
                    def __init__(self, *args, **kwargs):
                        self.inner = temporary(*args, **kwargs)
                    def __enter__(self):
                        return self.inner.__enter__()
                    def __exit__(self, *args):
                        result = self.inner.__exit__(*args)
                        if selection == "capture":
                            raise OSError("synthetic-private-capture-cleanup")
                        return result
                def inspect_close(descriptors):
                    nonlocal close_calls, target
                    close_calls += 1
                    descriptors = list(descriptors)
                    inject = close_calls == (1 if selection == "source" else 2)
                    if selection == "capture" or not inject:
                        return close_owned(descriptors)
                    target = descriptors[0]
                    def close(fd):
                        attempted.append(fd)
                        real_close(fd)
                        if fd == target:
                            raise OSError("synthetic-private-descriptor-cleanup")
                    with patch.object(self.assembly.os, "close", side_effect=close):
                        outcome = close_owned(descriptors)
                    self.assertEqual(attempted, list(dict.fromkeys(descriptors)))
                    return outcome
                with (
                    patch.object(self.assembly.tempfile, "TemporaryDirectory", Capture),
                    patch.object(self.assembly, "_close_owned_fds", side_effect=inspect_close),
                ):
                    result = self.assemble(fixture)
                self.assertEqual((result.exit_code, result.code), (2, "ASSEMBLY_UNAVAILABLE"))
                self.assertNotIn("synthetic-private", json.dumps(result.diagnostics()))
                container = next((fixture.path / "build").iterdir())
                self.assertEqual({path.name for path in container.iterdir()}, {".owner", "staging"})
                if target is not None:
                    self.assertEqual(attempted.count(target), 1)

    def test_postrename_close_failure_preserves_verified_finalized_warning(self):
        fixture = self.fixture()
        close_owned = self.assembly._close_owned_fds
        real_close = self.assembly.os.close
        close_calls = 0
        attempted = []
        def inspect_close(descriptors):
            nonlocal close_calls
            close_calls += 1
            descriptors = list(descriptors)
            if close_calls != 3:
                return close_owned(descriptors)
            self.assertEqual(len(descriptors), 1)
            def close(fd):
                attempted.append(fd)
                real_close(fd)
                raise OSError("synthetic-private-postrename-cleanup")
            with patch.object(self.assembly.os, "close", side_effect=close):
                return close_owned(descriptors)
        with patch.object(self.assembly, "_close_owned_fds", side_effect=inspect_close):
            result = self.assemble(fixture)
        self.assertEqual(close_calls, 3)
        self.assertEqual(len(attempted), 1)
        self.assertEqual((result.exit_code, result.code), (0, "CANDIDATE_FINALIZED_CLEANUP_WARNING"))
        self.assertEqual(result.source_revision, fixture.head)
        self.assertEqual(result.tree_oid, fixture.tree)
        self.assertNotIn("synthetic-private", json.dumps(result.diagnostics()))
        bundle = fixture.path / "build" / result.bundle_name
        self.assertFalse((bundle.parent / "staging").exists())
        checked = verify_release(str(bundle), expected_digest=result.table_sha256,
                                  expected_format="project-manifest-release-1")
        self.assertEqual(checked.exit_code, 0)

    def test_ignore_projection_classifies_ignored_directories_and_unignored_control(self):
        fixture = self.fixture()
        process = self.assembly.acquisition.bounded_process
        queries = []
        def inspect(argv, **kwargs):
            observed = process(argv, **kwargs)
            if "check-ignore" in argv:
                queries.append((argv, kwargs["data"], observed))
            return observed
        with patch.object(self.assembly.acquisition, "bounded_process", side_effect=inspect):
            self.bundle(fixture, self.assemble(fixture))
            (fixture.path / "synthetic-unignored").write_bytes(b"Synthetic unignored control\n")
            rejected = self.assemble(fixture)
        self.assertEqual((rejected.exit_code, rejected.code), (1, "SOURCE_UNTRACKED"))
        for name in (b"build/\0", b"dist/\0"):
            matches = [observed for _, raw, observed in queries if raw == name]
            self.assertTrue(matches)
            self.assertTrue(all(observed == (0, name, b"") for observed in matches))
        negatives = [observed for _, raw, observed in queries if raw == b"synthetic-unignored\0"]
        self.assertEqual(negatives, [(1, b"", b"")])
        for argv, _, _ in queries:
            self.assertLess(argv.index("--literal-pathspecs"), argv.index("--no-literal-pathspecs"))
            projection = argv[argv.index("-C") + 1]
            self.assertIn("--work-tree=" + projection, argv)

    def test_output_directory_replacement_during_second_source_check_is_refused(self):
        for selection in ("parent", "container", "staging"):
            with self.subTest(selection=selection):
                fixture = self.fixture()
                literal = self.assembly._literal_clean
                calls = 0
                displaced = fixture.root / "synthetic-displaced-output"
                def inspect(*args):
                    nonlocal calls
                    literal(*args)
                    calls += 1
                    if calls == 2:
                        parent = fixture.path / "build"
                        container = next(parent.iterdir())
                        target = {"parent": parent, "container": container,
                                  "staging": container / "staging"}[selection]
                        mode = target.stat().st_mode & 0o777
                        target.rename(displaced)
                        target.mkdir(mode=mode)
                recheck = self.assembly.acquisition.FrozenStore.recheck
                refusals = []
                def inspect_recheck(store):
                    try:
                        return recheck(store)
                    except self.assembly.acquisition.AcquisitionFailure as error:
                        refusals.append(error.reason)
                        raise
                with (
                    patch.object(self.assembly, "_literal_clean", side_effect=inspect),
                    patch.object(self.assembly.acquisition.FrozenStore, "recheck", new=inspect_recheck),
                ):
                    result = self.assemble(fixture)
                expected = (2, "ASSEMBLY_UNAVAILABLE") if selection == "parent" else (1, "OUTPUT_CHANGED")
                self.assertEqual((result.exit_code, result.code), expected)
                self.assertEqual(refusals, ["observation_changed"] if selection == "parent" else [])
                self.assertTrue(displaced.is_dir())
                self.assertFalse(any(path.name == "bundle" for path in displaced.rglob("*")))

    def test_staged_payload_mutation_during_second_source_check_is_refused(self):
        fixture = self.fixture()
        literal = self.assembly._literal_clean
        calls = 0
        staged = None
        def inspect(*args):
            nonlocal calls, staged
            literal(*args)
            calls += 1
            if calls == 2:
                container = next((fixture.path / "build").iterdir())
                staged = container / "staging"
                (staged / PAYLOAD_FILES[0]).write_bytes(b"Synthetic staged bytes changed after verification\n")
        with patch.object(self.assembly, "_literal_clean", side_effect=inspect):
            result = self.assemble(fixture)
        self.assertEqual((result.exit_code, result.code), (1, "ASSEMBLY_VERIFY"))
        self.assertEqual(calls, 2)
        self.assertIsNotNone(staged)
        self.assertTrue(staged.is_dir())
        self.assertFalse((staged.parent / "bundle").exists())

    def test_literal_commit_reproducibility_both_oid_widths_and_shared_encoder(self):
        for algorithm in ("sha1", "sha256"):
            with self.subTest(algorithm=algorithm):
                fixture = self.fixture(object_format=algorithm)
                before = (fixture.git_dir / "index").read_bytes()
                first, second = self.assemble(fixture), self.assemble(fixture, parent="dist")
                a, b = self.bundle(fixture, first), self.bundle(fixture, second, "dist")
                self.assertEqual((a / "release.json").read_bytes(), (b / "release.json").read_bytes())
                self.assertEqual(first.table_sha256, second.table_sha256)
                table = json.loads((a / "release.json").read_bytes())
                self.assertEqual(table["source_revision"], fixture.head)
                self.assertEqual(tuple(row["path"] for row in table["files"]), PAYLOAD_FILES)
                self.assertEqual((a / "release.json").read_bytes(), canonical(table))
                self.assertEqual(self.assembly.binding.canonical_table_bytes(table), canonical(table))
                for name in PAYLOAD_FILES:
                    self.assertEqual((a / name).read_bytes(), fixture.files[name].data)
                checked = verify_release(str(a), expected_digest=first.table_sha256,
                                          expected_format="project-manifest-release-1")
                self.assertEqual(checked.exit_code, 0)
                self.assertEqual((fixture.git_dir / "index").read_bytes(), before)

    def test_dirty_index_worktree_untracked_and_revision_never_create_output(self):
        from acquisition_fixtures import FileSpec
        for condition in ("worktree", "index", "untracked", "revision"):
            with self.subTest(condition=condition):
                fixture = self.fixture()
                revision = fixture.head
                if condition == "worktree":
                    (fixture.path / PAYLOAD_FILES[0]).write_bytes(b"Synthetic dirty bytes\n")
                elif condition == "index":
                    entries = dict(fixture.files)
                    entries[PAYLOAD_FILES[0]] = FileSpec("100644", b"Synthetic staged bytes\n")
                    fixture.set_index(entries)
                elif condition == "untracked":
                    (fixture.path / "synthetic-extra").write_bytes(b"Synthetic extra\n")
                else:
                    revision = "0" * len(fixture.head)
                result = self.assemble(fixture, revision=revision)
                self.assertNotEqual(result.exit_code, 0)
                self.assertEqual(list((fixture.path / "build").iterdir()), [])

    def test_source_symlink_and_output_scope_are_refused_without_outside_reads(self):
        from acquisition_fixtures import FileSpec
        fixture = self.fixture(changed={PAYLOAD_FILES[0]: FileSpec("120000", b"synthetic-outside")})
        result = self.assemble(fixture)
        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual(list((fixture.path / "build").iterdir()), [])
        fixture = self.fixture()
        outside = self.owner.create_root()
        marker = outside / "untouched"
        marker.write_bytes(b"Synthetic outsider\n")
        result = self.assembly.assemble_candidate(str(fixture.path), expected_revision=fixture.head,
                                                  output_parent=str(outside))
        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual(marker.read_bytes(), b"Synthetic outsider\n")
        self.assertEqual(set(p.name for p in outside.iterdir()), {"fixture-owner", "untouched"})

    def test_failure_and_collision_preserve_private_partial_output_without_completed_bundle(self):
        fixture = self.fixture()
        original = self.assembly._write_new
        calls = []
        def fail_write(fd, parts, data):
            calls.append(parts)
            if parts[-1] == "release.json":
                raise OSError("synthetic-private-write-error")
            return original(fd, parts, data)
        with patch.object(self.assembly, "_write_new", side_effect=fail_write):
            result = self.assemble(fixture)
        self.assertNotEqual(result.exit_code, 0)
        self.assertNotIn("synthetic-private", json.dumps(result.diagnostics()))
        containers = list((fixture.path / "build").iterdir())
        self.assertEqual(len(containers), 1)
        self.assertFalse((containers[0] / "bundle").exists())
        self.assertTrue((containers[0] / ".owner").is_file())
        fixture = self.fixture()
        finalize = self.assembly._finalize_noreplace
        def collide(fd):
            os.mkdir("bundle", dir_fd=fd)
            file_fd = os.open("bundle/untouched", os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                              0o600, dir_fd=fd)
            with os.fdopen(file_fd, "wb") as stream:
                stream.write(b"Synthetic collision\n")
            return finalize(fd)
        with patch.object(self.assembly, "_finalize_noreplace", side_effect=collide):
            result = self.assemble(fixture)
        self.assertNotEqual(result.exit_code, 0)
        container = next((fixture.path / "build").iterdir())
        self.assertEqual((container / "bundle/untouched").read_bytes(), b"Synthetic collision\n")
        self.assertTrue((container / "staging").exists())

    def test_source_mutation_and_verification_failure_never_finalize(self):
        for condition in ("source", "verification"):
            with self.subTest(condition=condition):
                fixture = self.fixture()
                original = self.assembly.binding.verify_release
                def inspect(*args, **kwargs):
                    result = original(*args, **kwargs)
                    if condition == "source":
                        (fixture.path / PAYLOAD_FILES[0]).write_bytes(b"Synthetic changed after capture\n")
                    else:
                        return self.assembly.binding.VerificationResult(1, ("PAYLOAD_DIGEST",))
                    return result
                with patch.object(self.assembly.binding, "verify_release", side_effect=inspect):
                    result = self.assemble(fixture)
                self.assertNotEqual(result.exit_code, 0)
                container = next((fixture.path / "build").iterdir())
                self.assertFalse((container / "bundle").exists())

    def test_contained_git_has_no_source_filters_hooks_fsmonitor_or_export_subst(self):
        from acquisition_fixtures import FileSpec
        fixture = self.fixture(changed={
            ".gitattributes": FileSpec("100644", b"* filter=synthetic export-subst\n"),
            PAYLOAD_FILES[0]: FileSpec("100644", b"Synthetic $Format:%H$ literal\n"),
        })
        marker = fixture.root / "should-not-exist"
        self.assertRegex(str(marker), r"\A/[A-Za-z0-9_./-]+\Z")
        command = 'touch ' + str(marker)
        with (fixture.git_dir / "config").open("a") as stream:
            stream.write("\n[filter \"synthetic\"]\n clean = " + command
                         + "\n smudge = " + command + "\n[core]\n fsmonitor = " + command + "\n")
        (fixture.git_dir / "hooks").mkdir()
        (fixture.git_dir / "hooks/pre-commit").write_text("#!/bin/sh\n" + command + "\n")
        (fixture.git_dir / "hooks/pre-commit").chmod(0o755)
        result = self.assemble(fixture)
        bundle = self.bundle(fixture, result)
        self.assertEqual((bundle / PAYLOAD_FILES[0]).read_bytes(), b"Synthetic $Format:%H$ literal\n")
        self.assertFalse(marker.exists())

    def test_fixture_and_assembler_do_not_follow_inherited_git_context(self):
        from acquisition_fixtures import FileSpec, GitFixture
        other = self.fixture()
        before = (other.git_dir / "index").read_bytes(), (other.git_dir / "config").read_bytes()
        overrides = {"GIT_DIR": str(other.git_dir), "GIT_WORK_TREE": str(other.path),
                     "GIT_INDEX_FILE": str(other.git_dir / "index"), "GIT_CONFIG_COUNT": "1",
                     "GIT_CONFIG_KEY_0": "core.bare", "GIT_CONFIG_VALUE_0": "true"}
        with patch.dict(os.environ, overrides):
            fixture = self.fixture()
            result = self.assemble(fixture)
        self.assertEqual(result.exit_code, 2)
        self.assertEqual(result.code, "INHERITED_GIT_CONTEXT")
        self.assertEqual((other.git_dir / "index").read_bytes(), before[0])
        self.assertEqual((other.git_dir / "config").read_bytes(), before[1])
        self.assertEqual(list((fixture.path / "build").iterdir()), [])

    def test_completed_payload_tamper_is_rejected_by_existing_verifier(self):
        fixture = self.fixture()
        result = self.assemble(fixture)
        bundle = self.bundle(fixture, result)
        (bundle / PAYLOAD_FILES[0]).write_bytes(b"Synthetic payload tamper\n")
        checked = verify_release(str(bundle), expected_digest=result.table_sha256,
                                  expected_format="project-manifest-release-1")
        self.assertEqual(checked.exit_code, 1)




if __name__ == "__main__":
    unittest.main()
