"""Release trust and source selection remain independent of editable validator code."""

import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shlex
import subprocess
import sys
import unittest

from acquisition_fixtures import FileSpec, FixtureOwner, GitFixture

ROOT = Path(__file__).absolute().parent.parent
HELPER = "scripts/check-self-adoption.py"
VENDOR = "vendor/project-manifest"


class SelfAdoptionTests(unittest.TestCase):
    def fixture(self):
        owner = FixtureOwner(self)
        paths = ["project.yaml", "STATUS.md", HELPER]
        paths += [path.relative_to(ROOT).as_posix() for path in (ROOT / VENDOR).rglob("*")
                  if path.is_file()]
        source = {name: FileSpec("100644", (ROOT / name).read_bytes()) for name in paths}
        # Fixture replay date stays stable when the real origin's status advances.
        manifest, count = re.subn(rb'(?m)^  as_of: "[0-9]{4}-[0-9]{2}-[0-9]{2}"$',
                                  b'  as_of: "2026-10-17"', source["project.yaml"].data)
        self.assertEqual(count, 1)
        source["project.yaml"] = FileSpec("100644", manifest)
        # This code must never execute when checking the origin declaration.
        poison = b"raise RuntimeError('SYNTHETIC_EDITABLE_SOURCE_EXECUTED')\n"
        source["src/project_manifest/__init__.py"] = FileSpec("100644", poison)
        source["bootstrap/release_verifier.py"] = FileSpec("100644", poison)
        return GitFixture(owner).seed(source)

    def invoke(self, fixture, *, root=None, common=None, revision=None,
               worktree=None, staged=None, extra_env=None):
        root = fixture.path if root is None else root
        manifest = fixture.files["project.yaml"].data
        worktree = manifest if worktree is None else worktree
        staged = manifest if staged is None else staged
        args = [sys.executable, "-I", "-S", "-B", str(root / HELPER),
                "--reference-date", "2026-10-17",
                "--git-common-dir", str(fixture.git_dir if common is None else common),
                "--worktree-sha256", hashlib.sha256(worktree).hexdigest(),
                "--staged-sha256", hashlib.sha256(staged).hexdigest()]
        if revision is not None:
            args += ["--rev", revision]
        env = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
        env.update(extra_env or {})
        result = subprocess.run(args, env=env, cwd=root, capture_output=True, text=True,
                                timeout=60, check=False)
        self.assertEqual(result.stderr, "")
        report = json.loads(result.stdout)
        self.assertEqual(result.returncode, report["exit_code"])
        self.assertNotIn("SYNTHETIC_EDITABLE_SOURCE_EXECUTED", result.stdout)
        return report

    def test_release_checks_all_three_sources_without_editable_source_import(self):
        fixture = self.fixture()
        report = self.invoke(fixture, revision=fixture.head)
        self.assertEqual(report["exit_code"], 0, report)
        self.assertEqual([entry["mode"] for entry in report["observations"]],
                         ["worktree", "staged", "rev"])
        self.assertEqual(report["observations"][-1]["commit_oid"], fixture.head)
        self.assertEqual(report["complete_v1_validity"], "not_checked")
        self.assertEqual(report["native_conformance"], "not_checked")
        self.assertEqual(report["declaration_checks"], "passed")
        self.assertEqual(report["runtime_acceptance"], "not_checked")

    def test_linked_checkout_and_shallow_revision(self):
        fixture = self.fixture()
        (fixture.git_dir / "shallow").write_text(fixture.head + "\n")
        linked, _ = fixture.linked()
        report = self.invoke(fixture, root=linked, revision=fixture.head)
        self.assertEqual(report["exit_code"], 0, report)

    def test_wrong_linked_scope_is_not_checked(self):
        fixture = self.fixture()
        linked, _ = fixture.linked()
        report = self.invoke(fixture, root=linked, common=fixture.root)
        self.assertEqual(report["exit_code"], 2)
        self.assertEqual(report["complete_v1_validity"], "not_checked")

    def test_inherited_git_context_is_not_normalized(self):
        fixture = self.fixture()
        report = self.invoke(fixture, extra_env={"GIT_INDEX_FILE": str(fixture.git_dir / "index")})
        self.assertEqual(report["exit_code"], 2)
        self.assertEqual(report["finding"], "RELEASED_OBSERVATION")

    def test_bootstrap_tamper_is_refused_before_execution(self):
        fixture = self.fixture()
        path = fixture.path / VENDOR / "bootstrap/release_verifier.py"
        path.write_bytes(b"raise RuntimeError('SYNTHETIC_BOOTSTRAP_EXECUTED')\n")
        report = self.invoke(fixture)
        self.assertEqual((report["exit_code"], report["finding"]), (1, "BOOTSTRAP_DIGEST"))

    def test_payload_tamper_is_refused_before_execution(self):
        fixture = self.fixture()
        path = fixture.path / VENDOR / "release-1/src/project_manifest/__init__.py"
        path.write_bytes(b"raise RuntimeError('SYNTHETIC_PAYLOAD_EXECUTED')\n")
        report = self.invoke(fixture)
        self.assertEqual((report["exit_code"], report["finding"]), (1, "RELEASE_BINDING"))

    def test_candidate_descriptor_is_not_a_release(self):
        fixture = self.fixture()
        path = fixture.path / VENDOR / "release-1/release.json"
        path.write_bytes(path.read_bytes().replace(b'"project-manifest-release-1"', b'"candidate-binding-1"'))
        report = self.invoke(fixture)
        self.assertEqual((report["exit_code"], report["finding"]), (1, "RELEASE_BINDING"))

    def test_extra_payload_file_is_not_hidden_by_projection(self):
        fixture = self.fixture()
        path = fixture.path / VENDOR / "release-1/extra-file"
        path.write_bytes(b"Synthetic extra payload\n")
        report = self.invoke(fixture)
        self.assertEqual((report["exit_code"], report["finding"]), (1, "RELEASE_BINDING"))

    def test_vendor_symlink_is_refused(self):
        fixture = self.fixture()
        path = fixture.path / VENDOR / "bootstrap/release_verifier.py"
        data = path.read_bytes()
        path.unlink()
        target = fixture.root / "bootstrap-target"
        target.write_bytes(data)
        path.symlink_to(target)
        report = self.invoke(fixture)
        self.assertEqual(report["exit_code"], 2)

    def test_staged_manifest_is_checked_independently(self):
        fixture = self.fixture()
        data = fixture.files["project.yaml"].data.replace(b"role: canonical", b"role: unsupported")
        staged = dict(fixture.files, **{"project.yaml": FileSpec("100644", data)})
        fixture.set_index(staged)
        report = self.invoke(fixture, staged=data)
        self.assertEqual(report["exit_code"], 1)
        self.assertEqual([entry["mode"] for entry in report["observations"]], ["worktree", "staged"])

    def test_changed_manifest_capture_is_refused(self):
        fixture = self.fixture()
        report = self.invoke(fixture, worktree=b"Synthetic stale source bytes\n")
        self.assertEqual((report["exit_code"], report["finding"]), (1, "SNAPSHOT_CHANGED"))

    def test_valid_declared_role_with_wrong_native_target_is_refused(self):
        fixture = self.fixture()
        data = fixture.files["project.yaml"].data.replace(b'target: "check"', b'target: "missing"')
        (fixture.path / "project.yaml").write_bytes(data)
        report = self.invoke(fixture, worktree=data)
        self.assertEqual((report["exit_code"], report["finding"]), (1, "NATIVE_DECLARATION"))

    def test_outer_gate_requires_exact_native_task_and_no_automatic_installation(self):
        gate = runpy.run_path(str(ROOT / "scripts/validate.py"))
        bundle = {name: (ROOT / name).read_bytes() for name in gate["FILES"]}
        gate["check_bundle"](bundle)
        original = bundle["mise.toml"]
        for before, after in (
            (b'run = "python -I -S -B scripts/validate.py"', b'run = "python other-script.py"'),
            (b"auto_install = false", b"auto_install = true"),
            (b"task.run_auto_install = false", b"task.run_auto_install = true"),
        ):
            with self.subTest(before=before):
                changed = dict(bundle, **{"mise.toml": original.replace(before, after)})
                with self.assertRaises(gate["GateError"]):
                    gate["check_bundle"](changed)

    def test_checkout_attributes_preserve_manifest_and_released_bytes(self):
        owner = FixtureOwner(self)
        paths = (".gitattributes", "project.yaml", VENDOR + "/bootstrap/release_verifier.py",
                 VENDOR + "/release-1/src/project_manifest/candidate.py")
        source = {name: FileSpec("100644", (ROOT / name).read_bytes()) for name in paths}
        fixture = GitFixture(owner).seed(source)
        inherited = fixture.root / "inherited-attributes"
        inherited.write_text(
            "/project.yaml text eol=crlf filter=synthetic ident working-tree-encoding=UTF-16LE\n"
            "/vendor/project-manifest/** text eol=crlf filter=synthetic ident working-tree-encoding=UTF-16LE\n")
        marker, command = fixture.sentinel()
        for key, value in (("core.attributesfile", str(inherited)), ("core.autocrlf", "true"),
                           ("core.eol", "crlf"), ("filter.synthetic.required", "true"),
                           ("filter.synthetic.smudge", shlex.quote(str(command)))):
            fixture._run(["config", key, value])
        for name in paths[1:]:
            (fixture.path / name).unlink()
        fixture._run(["checkout-index", "--force", "--", *paths[1:]])
        self.assertFalse(marker.exists(), "Guarded files must not execute inherited filters")
        for name in paths[1:]:
            self.assertEqual((fixture.path / name).read_bytes(), source[name].data)


if __name__ == "__main__":
    unittest.main()
