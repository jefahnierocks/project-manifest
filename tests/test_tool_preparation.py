"""Synthetic preparation refusals; never download or build real tool artifacts."""

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import unittest
from unittest.mock import patch

from acquisition_fixtures import FixtureOwner

ROOT = Path(__file__).absolute().parent.parent
SPEC = importlib.util.spec_from_file_location("linux_tool_preparation", ROOT / "scripts/prepare-linux-tools.py")
PREP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREP)


class ToolPreparationTests(unittest.TestCase):
    def setUp(self):
        self.owner = FixtureOwner(self)

    def archive(self, member):
        container = self.owner.create_root()
        source = container / "synthetic.tar.gz"
        with tarfile.open(source, "w:gz") as stream:
            content = b"Synthetic bytes\n" if member.isfile() else b""
            member.size = len(content)
            stream.addfile(member, io.BytesIO(content) if content else None)
        return container, source

    def test_current_tools_have_one_generated_lock_authority(self):
        selected = PREP.load_artifacts(ROOT)
        import tomllib
        lock = tomllib.loads((ROOT / "mise.lock").read_text())
        for tool in ("python", "gitleaks"):
            item = selected["python_current" if tool == "python" else tool]
            entry = lock["tools"][tool][0]
            self.assertEqual(item["version"], entry["version"])
            self.assertEqual(item["url"], entry["platforms.linux-x64"]["url"])
            self.assertEqual(item["checksum"], entry["platforms.linux-x64"]["checksum"])
        self.assertEqual(set(PREP.QUALIFICATION_PINS), {"git", "python_floor"})

    def test_mismatched_backend_or_version_refuses_before_download(self):
        import tomllib
        config = (ROOT / "mise.toml").read_text()
        lock = (ROOT / "mise.lock").read_text()
        for old, new in (("aqua:gitleaks/gitleaks", "github:synthetic/tool"),
                         ('version = "8.30.1"', 'version = "8.30.0"')):
            with self.subTest(field=old):
                container = self.owner.create_root()
                (container / "mise.toml").write_text(config)
                self.assertIn(old, lock)
                (container / "mise.lock").write_text(lock.replace(old, new, 1))
                with patch.object(PREP, "download", side_effect=AssertionError("unexpected download")):
                    with self.assertRaises(PREP.PreparationError):
                        PREP.load_artifacts(container)

    def test_bad_digest_origin_or_architecture_is_not_a_fallback(self):
        info = {"url": "https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz",
                "checksum": "sha256:" + "0" * 64}
        for replacement in ({"checksum": "unbound"},
                            {"url": info["url"].replace("github.com", "example.invalid")},
                            {"url": info["url"].replace("linux_x64", "linux_arm64")}):
            with self.subTest(keys=list(replacement)):
                with self.assertRaises(PREP.PreparationError):
                    PREP.artifact("8.30.1", info | replacement, "gitleaks")

    def test_unqualified_host_refuses_before_input_or_tool_activity(self):
        with patch.object(PREP.platform, "system", return_value="Darwin"), \
             patch.object(PREP, "load_artifacts", side_effect=AssertionError("unexpected input")), \
             patch.object(PREP, "download", side_effect=AssertionError("unexpected download")), \
             patch.object(PREP, "run", side_effect=AssertionError("unexpected process")):
            with self.assertRaisesRegex(PREP.PreparationError, "UNQUALIFIED"):
                PREP.prepare()

    def test_checksum_failure_retains_bytes_and_stops_before_extraction(self):
        container = self.owner.create_root()
        destination = container / "download"
        response = io.BytesIO(b"Synthetic incorrect archive bytes")
        with patch.object(PREP, "urlopen", return_value=response):
            with self.assertRaisesRegex(PREP.PreparationError, "ARCHIVE_CHECKSUM"):
                PREP.download({"url": "https://example.invalid/synthetic", "checksum": "sha256:" + "0" * 64}, destination)
        self.assertTrue(destination.is_file())
        self.assertFalse((container / "extracted").exists())

    def test_download_bound_is_enforced_before_acceptance(self):
        container = self.owner.create_root()
        with patch.object(PREP, "MAX_DOWNLOAD", 4), \
             patch.object(PREP, "urlopen", return_value=io.BytesIO(b"Synthetic oversized bytes")):
            with self.assertRaisesRegex(PREP.PreparationError, "DOWNLOAD_BOUND"):
                PREP.download({"url": "https://example.invalid/synthetic", "checksum": "sha256:" + "0" * 64}, container / "download")

    def test_regular_archive_has_bounded_owned_destination(self):
        container, archive = self.archive(tarfile.TarInfo("nested/source.txt"))
        PREP.extract(archive, container / "extracted")
        self.assertEqual((container / "extracted/nested/source.txt").read_bytes(), b"Synthetic bytes\n")

    def test_traversal_absolute_and_special_entries_refuse_before_destination_creation(self):
        for name, kind in (("../outside", tarfile.REGTYPE), ("/absolute", tarfile.REGTYPE),
                           ("named-pipe", tarfile.FIFOTYPE), ("hardlink", tarfile.LNKTYPE)):
            with self.subTest(kind=kind):
                member = tarfile.TarInfo(name)
                member.type = kind
                member.linkname = "synthetic-target"
                container, archive = self.archive(member)
                with self.assertRaises(PREP.PreparationError):
                    PREP.extract(archive, container / "extracted")
                self.assertFalse((container / "extracted").exists())

    def test_external_symlink_and_existing_target_are_refused(self):
        member = tarfile.TarInfo("escape")
        member.type = tarfile.SYMTYPE
        member.linkname = "../../outside"
        container, archive = self.archive(member)
        with self.assertRaises((PREP.PreparationError, tarfile.FilterError)):
            PREP.extract(archive, container / "extracted")
        self.assertFalse((container / "extracted").exists())
        existing = container / "existing"
        existing.mkdir()
        with self.assertRaisesRegex(PREP.PreparationError, "TARGET_EXISTS"):
            PREP.extract(archive, existing)

    def test_owned_child_timeout_cancels_only_that_process_group(self):
        process = unittest.mock.Mock(pid=43210)
        process.communicate.side_effect = [subprocess.TimeoutExpired("synthetic", 1), (None, None)]
        with patch.object(PREP.subprocess, "Popen", return_value=process) as launch, \
             patch.object(PREP.os, "killpg") as cancel:
            with self.assertRaisesRegex(PREP.PreparationError, "TIMEOUT"):
                PREP.run(["synthetic-never-executed"], cwd=ROOT, seconds=1)
        self.assertTrue(launch.call_args.kwargs["start_new_session"])
        cancel.assert_called_once_with(43210, PREP.signal.SIGKILL)


if __name__ == "__main__":
    unittest.main()
