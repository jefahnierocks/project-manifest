"""Pinned qualification tools in an owned hosted-runner prefix; no global setup."""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).absolute().parent.parent
MAX_DOWNLOAD = 64 * 1024 * 1024
MAX_EXPANDED = 512 * 1024 * 1024
MAX_MEMBERS = 25_000
QUALIFICATION_PINS = {
    "python_floor": {
        "version": "3.11.17",
        "url": "https://github.com/astral-sh/python-build-standalone/releases/download/20261009/cpython-3.11.17+20261009-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz",
        "checksum": "sha256:89db7607ebadb77a64709d159b86555d995368ec385a2ab33b00477790c543b0",
    },
    "git": {
        "version": "2.56.0",
        "url": "https://www.kernel.org/pub/software/scm/git/git-2.56.0.tar.xz",
        "checksum": "sha256:26c56c296b38c0695b26fa95f475f1d01704d2d38e73465ca30b0b2f5dc789d3",
    },
}
# Git's archive checksum is taken from the official HTTPS-published checksum list.
# GitHub's verified tag describes another object; no tar-signature claim is made.
# https://www.kernel.org/pub/software/scm/git/sha256sums.asc


class PreparationError(Exception):
    pass


def require(condition, code):
    if not condition:
        raise PreparationError(code)


def artifact(version, entry, tool):
    checksum = entry.get("checksum", "")
    url = entry.get("url", "")
    parsed = urlsplit(url)
    path = unquote(parsed.path)
    require(re.fullmatch(r"sha256:[0-9a-f]{64}", checksum), "LOCK_CHECKSUM")
    require(parsed.scheme == "https" and parsed.hostname == "github.com"
            and not parsed.username and not parsed.password and not parsed.query
            and not parsed.fragment, "LOCK_ORIGIN")
    if tool == "python":
        require(path.startswith("/astral-sh/python-build-standalone/releases/download/")
                and re.fullmatch(r"cpython-" + re.escape(version)
                                 + r"\+[0-9]{8}-x86_64-unknown-linux-gnu-install_only_stripped\.tar\.gz",
                                 path.rsplit("/", 1)[-1])
                and entry.get("provenance") == "github-attestations", "LOCK_PYTHON_ARTIFACT")
    else:
        require(path == "/gitleaks/gitleaks/releases/download/v" + version
                + "/gitleaks_" + version + "_linux_x64.tar.gz", "LOCK_GITLEAKS_ARTIFACT")
    return {"version": version, "url": url, "checksum": checksum}


def load_artifacts(root):
    config = tomllib.loads((root / "mise.toml").read_text())
    lock = tomllib.loads((root / "mise.lock").read_text())
    require(set(config["tools"]) == {"python", "gitleaks"}
            and set(lock["tools"]) == set(config["tools"]), "LOCK_TOOL_SET")
    result = dict(QUALIFICATION_PINS)
    for tool, version in config["tools"].items():
        require(isinstance(version, str) and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version), "LOCK_VERSION")
        entries = lock["tools"][tool]
        require(len(entries) == 1 and entries[0].get("version") == version
                and entries[0].get("specifiers") == [version], "LOCK_PIN_MATCH")
        expected = "core:python" if tool == "python" else "aqua:gitleaks/gitleaks"
        require(entries[0].get("backend") == expected, "LOCK_BACKEND")
        linux = entries[0].get("platforms.linux-x64")
        require(isinstance(linux, dict), "LOCK_LINUX_MISSING")
        result["python_current" if tool == "python" else tool] = artifact(version, linux, tool)
    return result


def require_host():
    require(platform.system() == "Linux" and platform.machine() == "x86_64"
            and os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("RUNNER_OS") == "Linux"
            and os.environ.get("RUNNER_ARCH") == "X64", "UNQUALIFIED_PREPARATION_HOST")
    require(sys.version_info >= (3, 11) and hasattr(tarfile, "data_filter"), "BOOTSTRAP_RUNTIME")


def download(info, path):
    digest = hashlib.sha256()
    size = 0
    deadline = time.monotonic() + 60
    with urlopen(Request(info["url"], headers={"User-Agent": "project-manifest-source-qualification"}), timeout=30) as response:
        with path.open("xb") as output:
            while chunk := response.read(65_536):
                size += len(chunk)
                require(size <= MAX_DOWNLOAD and time.monotonic() <= deadline, "DOWNLOAD_BOUND")
                digest.update(chunk)
                output.write(chunk)
    require("sha256:" + digest.hexdigest() == info["checksum"], "ARCHIVE_CHECKSUM")


def extract(archive, destination):
    require(not destination.exists(), "EXTRACTION_TARGET_EXISTS")
    with tarfile.open(archive, "r:*") as source:
        members = source.getmembers()
        require(len(members) <= MAX_MEMBERS, "ARCHIVE_MEMBER_BOUND")
        require(sum(member.size for member in members) <= MAX_EXPANDED, "ARCHIVE_BYTE_BOUND")
        for member in members:
            parts = PurePosixPath(member.name).parts
            require(parts and not member.name.startswith("/") and ".." not in parts
                    and "\\" not in member.name and "\x00" not in member.name, "ARCHIVE_PATH")
            require(member.isfile() or member.isdir() or member.issym(), "ARCHIVE_ENTRY")
            if member.issym():
                require(not member.linkname.startswith("/") and "\\" not in member.linkname, "ARCHIVE_LINK")
            tarfile.data_filter(member, str(destination))
        destination.mkdir()
        source.extractall(destination, members=members, filter="data")


def run(argv, *, cwd, seconds=600):
    # No shell or inherited process group. Only this owned child group is cancelled.
    process = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        process.communicate(timeout=seconds)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise PreparationError("PREPARATION_TIMEOUT") from None
    require(process.returncode == 0, "PREPARATION_COMMAND")


def observed(argv):
    result = subprocess.run(argv, capture_output=True, check=False, timeout=10)
    require(result.returncode == 0 and len(result.stdout) + len(result.stderr) <= 16_384, "TOOL_OBSERVATION")
    return result.stdout.decode("utf-8").strip()


def prepare():
    require_host()
    selected = load_artifacts(ROOT)
    parent = Path(os.environ.get("RUNNER_TEMP", ""))
    require(parent.is_absolute() and parent.is_dir() and not parent.is_symlink(), "RUNNER_TEMP_REQUIRED")
    resolved = parent.resolve()
    checkout = ROOT.resolve()
    require(resolved != checkout and checkout not in resolved.parents, "TOOL_PREFIX_IN_CHECKOUT")
    container = Path(tempfile.mkdtemp(prefix="project-manifest-linux-tools-", dir=parent))
    require(not container.is_symlink() and container.resolve().parent == resolved
            and container.stat().st_uid == os.getuid(), "TOOL_PREFIX_OWNERSHIP")
    (container / "qualification-owner").write_text("Owned hosted source qualification tools\n")
    paths = {}
    for name, info in selected.items():
        archive = container / (name + ".archive")
        destination = container / name
        download(info, archive)
        extract(archive, destination)
        paths[name] = destination
    git_source = paths["git"] / ("git-" + selected["git"]["version"])
    git_prefix = container / "git-prefix"
    run(["make", "-j2", "prefix=" + str(git_prefix), "NO_OPENSSL=YesPlease",
         "NO_CURL=YesPlease", "NO_EXPAT=YesPlease", "NO_GETTEXT=YesPlease",
         "NO_TCLTK=YesPlease", "NO_PERL=YesPlease", "NO_PYTHON=YesPlease", "all", "install"], cwd=git_source)
    binaries = {"python_current": paths["python_current"] / "python/bin/python3",
                "python_floor": paths["python_floor"] / "python/bin/python3",
                "gitleaks": paths["gitleaks"] / "gitleaks", "git": git_prefix / "bin/git"}
    for binary in binaries.values():
        require(binary.is_file() and os.access(binary, os.X_OK)
                and container.resolve() in binary.resolve().parents, "PREPARED_BINARY")
    versions = {}
    for name in ("python_current", "python_floor"):
        versions[name] = observed([str(binaries[name]), "-I", "-B", "-c", "import platform; print(platform.python_version())"])
        require(versions[name] == selected[name]["version"], "PREPARED_PYTHON_VERSION")
    versions["git"] = observed([str(binaries["git"]), "--version"])
    require(versions["git"] == "git version " + selected["git"]["version"], "PREPARED_GIT_VERSION")
    versions["gitleaks"] = observed([str(binaries["gitleaks"]), "version"])
    require(versions["gitleaks"] == selected["gitleaks"]["version"], "PREPARED_GITLEAKS_VERSION")
    report = {"scope": "owned-linux-source-qualification-tool-preparation", "versions": versions,
              "binary_sha256": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in binaries.items()},
              "lock_sha256": hashlib.sha256((ROOT / "mise.lock").read_bytes()).hexdigest(),
              "git_source_checksum_trust": "official-HTTPS-published-SHA256; tar-signature-not-verified",
              "compiled_git": True, "release_or_admission": "not_checked"}
    (container / "tool-observation.json").write_text(json.dumps(report, sort_keys=True) + "\n")
    output = Path(os.environ["GITHUB_OUTPUT"])
    with output.open("a") as stream:
        for name, path in binaries.items():
            stream.write(name + "=" + str(path) + "\n")
    with Path(os.environ["GITHUB_PATH"]).open("a") as stream:
        stream.write(str(binaries["git"].parent) + "\n" + str(binaries["gitleaks"].parent) + "\n")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    try:
        prepare()
    except (PreparationError, OSError, ValueError, KeyError, tarfile.TarError) as error:
        print(json.dumps({"scope": "owned-linux-tool-preparation", "exit_code": 2,
                          "reason": str(error) if isinstance(error, PreparationError) else type(error).__name__}, sort_keys=True))
        raise SystemExit(2)
