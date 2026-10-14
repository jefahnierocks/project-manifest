"""Source safety and pure candidate corpus; never full v1 validation."""

import ast
import configparser
import os
from pathlib import Path, PurePosixPath
import platform
import re
import subprocess
import sys
import tempfile
import tomllib
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).absolute().parent.parent
PINS = {"python": "3.13.16", "gitleaks": "8.30.1"}
BACKENDS = {"python": "core:python", "gitleaks": "aqua:gitleaks/gitleaks"}
BASELINE_FILES = {
    "README.md", "AGENTS.md", "CLAUDE.md", "STATUS.md", "LICENSE",
    ".editorconfig", ".gitignore", "mise.toml", "mise.lock", "scripts/validate.py",
}
CANDIDATE_FILES = {
    "docs/specification-candidate.md", "docs/field-table.md",
    "docs/enum-provenance.md", "src/project_manifest/__init__.py",
    "src/project_manifest/candidate.py", "tests/test_candidate.py",
    "src/project_manifest/validation.py", "tests/test_validation.py",
    "docs/validation-candidate.md", "docs/acquisition-candidate.md",
    "src/project_manifest/acquire.py", "src/project_manifest/cli.py",
    "src/project_manifest/__main__.py", "tests/acquisition_fixtures.py",
    "tests/test_acquisition.py", "tests/test_cli.py",
    "bootstrap/release_verifier.py", "tests/test_binding.py",
    "docs/offline-binding-candidate.md", "tests/run_corpus.py",
    "tests/compare_loaders.py", "scripts/prepare-linux-tools.py",
    "tests/test_tool_preparation.py", ".github/workflows/linux-source.yml",
    "scripts/assemble-release.py",
}
FILES = BASELINE_FILES | CANDIDATE_FILES
PRIVATE_DATA = re.compile(
    r"/(?:Users|home)/|~[/\\]|[A-Za-z]:\\Users\\|"
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b|"
    r"\b\d{3}-\d{2}-\d{4}\b"
)


class GateError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise GateError(message)


def git(*args):
    env = os.environ.copy()
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1")
    result = subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-c", "submodule.recurse=false",
         "-C", str(ROOT), *args], env=env, capture_output=True, check=False
    )
    require(result.returncode == 0, "Git metadata read failed")
    return result.stdout


def parse_index(data):
    require(not data or data.endswith(b"\0"), "Unterminated index metadata")
    names = set()
    for record in data.split(b"\0")[:-1]:
        fields = record.split(b"\t", 1)
        require(len(fields) == 2 and fields[1], "Malformed index metadata")
        header = fields[0].split(b" ")
        require(len(header) == 3 and header[1], "Malformed index metadata")
        require(header[0] in {b"100644", b"100755"} and header[2] == b"0",
                "Nonregular or unmerged index entry")
        name = fields[1].decode("utf-8")
        require(name not in names, "Duplicate index entry")
        names.add(name)
    return names


def check_paths(names):
    for name in names:
        parts = PurePosixPath(name).parts
        require(not name.startswith("/") and ".." not in parts,
                "Unsafe source path")
        require(not any(p.casefold() == "private" for p in parts[:-1]),
                "Private-directory path in intended source/index")


def read_source(name):
    path = ROOT
    for part in PurePosixPath(name).parts:
        path = path / part
        require(not path.is_symlink(), "Source symlink is forbidden")
    require(path.is_file(), "Required source file missing")
    return path.read_bytes()


def check_text(name, data):
    text = data.decode("utf-8")
    require(not text.startswith("\ufeff") and "\r" not in text
            and "\t" not in text and text.endswith("\n"),
            "Text encoding/newline/space hygiene failed")
    if not name.endswith(".md"):
        require(all(line == line.rstrip() for line in text.splitlines()),
                "Trailing whitespace in non-Markdown source")
    require(not PRIVATE_DATA.search(text), "Private-data heuristic matched")
    return text


def check_links(texts):
    for name, text in texts.items():
        if not name.endswith(".md"):
            continue
        for target in re.findall(r"\[[^\]]*\]\(([^)\s]+)\)", text):
            parsed = urlsplit(target)
            if parsed.scheme:
                require(parsed.scheme in {"https", "http"},
                        "Unsupported Markdown link scheme")
                continue
            path = PurePosixPath(name).parent / unquote(parsed.path)
            linked = path.as_posix() if parsed.path else name
            require(linked in texts, "Local Markdown link leaves source set")
            if parsed.fragment:
                headings = {
                    re.sub(r"[^\w -]", "", h.strip().lower()).replace(" ", "-")
                    for h in re.findall(r"^#+ (.+)$", texts[linked], re.MULTILINE)
                }
                require(unquote(parsed.fragment) in headings,
                        "Local Markdown anchor missing")


def check_python_syntax(text):
    try:
        ast.parse(text)
    except SyntaxError:
        raise GateError("Invalid Python source syntax") from None


def check_bundle(bundle):
    require(set(bundle) == FILES, "Intended source layout is not complete/closed")
    texts = {name: check_text(name, data) for name, data in bundle.items()}
    agents = texts["AGENTS.md"]
    for declaration in (
        "Adopts the Jefahnierocks child-repo baseline 0.1.",
        "Tier: Governed.", "STATUS.md", "system-config",
        "docs/project-conventions.md", "Operating floor",
    ):
        require(declaration in agents, "Required baseline declaration missing")
    require(texts["CLAUDE.md"] == "@AGENTS.md\n", "Claude bridge is not canonical")
    require(texts["LICENSE"].startswith("MIT License\n"), "MIT license missing")
    require("private/" in texts[".gitignore"].splitlines(),
            "Unanchored private-directory ignore missing")
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read_string("[baseline]\n" + texts[".editorconfig"])
    for key, value in {
        "charset": "utf-8", "end_of_line": "lf", "insert_final_newline": "true",
        "indent_style": "space", "indent_size": "2",
        "trim_trailing_whitespace": "true",
    }.items():
        require(cfg["*"].get(key) == value, "EditorConfig baseline mismatch")
    require(cfg["baseline"].get("root") == "true"
            and cfg["*.md"].get("trim_trailing_whitespace") == "false"
            and cfg["*.py"].get("indent_size") == "4",
            "EditorConfig root/type settings mismatch")
    config = tomllib.loads(texts["mise.toml"])
    require(config.get("tools") == PINS
            and config.get("min_version") == "2026.10.8"
            and set(config) == {"min_version", "tools", "settings"},
            "Project declaration does not match bootstrap pins")
    require(config["settings"] == {
        "lockfile": True, "lockfile_platforms": ["macos-arm64", "linux-x64"],
    }, "Project lock settings mismatch")
    lock = tomllib.loads(texts["mise.lock"])
    require(lock.get("lockfile_version") == 3
            and set(lock.get("tools", {})) == set(PINS),
            "Generated lock format/tool set mismatch")
    for tool, version in PINS.items():
        entries = lock["tools"][tool]
        require(len(entries) == 1, "Ambiguous locked tool")
        entry = entries[0]
        require(entry.get("version") == version
                and entry.get("specifiers") == [version]
                and entry.get("backend") == BACKENDS[tool],
                "Pin/request/backend differs from generated lock")
        require({k for k in entry if k.startswith("platforms.")}
                == {"platforms.macos-arm64", "platforms.linux-x64"}, "Unexpected locked platforms")
        for platform_name in ("macos-arm64", "linux-x64"):
            artifact = entry["platforms." + platform_name]
            require(re.fullmatch(r"sha256:[0-9a-f]{64}", artifact.get("checksum", "")),
                    "Locked SHA-256 missing")
            url = urlsplit(artifact.get("url", ""))
            require(url.scheme == "https" and url.hostname == "github.com"
                    and not url.username and not url.password and not url.query
                    and not url.fragment and version in url.path,
                    "Locked artifact URL is not the expected public release")
    for name, text in texts.items():
        if name.endswith(".py"):
            check_python_syntax(text)
    check_links(texts)


def safety_probes():
    def record(mode, stage=b"0"):
        return mode + b" " + b"0" * 40 + b" " + stage + b"\tREADME.md\0"

    for mode in (b"100644", b"100755"):
        require(parse_index(record(mode)) == {"README.md"},
                "Regular index mode control rejected")
    for mode, stage in (
        (b"120000", b"0"), (b"160000", b"0"), (b"040000", b"0"),
        (b"100644", b"1"), (b"100644", b"2"), (b"100644", b"3"),
    ):
        try:
            parse_index(record(mode, stage))
        except GateError:
            continue
        raise GateError("Nonregular/unmerged index mode probe accepted")
    for probe in (
        lambda: check_paths(["docs/PrIvAtE/record.txt"]),
        lambda: check_text("probe.txt", ("/" + "Users/synthetic/\n").encode()),
        lambda: check_python_syntax("def synthetic(:\n"),
    ):
        try:
            probe()
        except GateError:
            continue
        raise GateError("Negative safety probe was accepted")


def secret_scan(worktree, index):
    env = os.environ.copy()
    with tempfile.TemporaryDirectory(prefix="project-manifest-bootstrap-") as tmp:
        temp = Path(tmp)
        config = temp / "defaults.toml"
        config.write_text("[extend]\nuseDefault = true\n", encoding="utf-8")
        ignores = temp / "empty-ignore"
        ignores.write_text("", encoding="utf-8")
        args = [
            "gitleaks", "dir", "--config", str(config), "--redact=100",
            "--no-banner", "--no-color", "--log-level", "error",
            "--ignore-gitleaks-allow", "--gitleaks-ignore-path", str(ignores),
        ]
        negative = temp / "negative"
        negative.mkdir()
        synthetic = "gh" + "p_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
        (negative / "probe.txt").write_text(synthetic + "\n", encoding="utf-8")
        result = subprocess.run(args + [str(negative)], env=env,
                                capture_output=True, text=True, check=False)
        require(result.returncode == 1, "Gitleaks negative probe not rejected")
        require(synthetic not in result.stdout + result.stderr,
                "Gitleaks full-redaction probe failed")
        source = temp / "source"
        for label, bundle in (("worktree", worktree), ("index", index)):
            for name, data in bundle.items():
                path = source / label / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        result = subprocess.run(args + [str(source)], env=env,
                                capture_output=True, text=True, check=False)
        if result.returncode:
            print(result.stdout + result.stderr, end="", file=sys.stderr)
            raise GateError("Pinned Gitleaks intended-source scan failed")


def run_corpus(bundle, label):
    # Test exact intended source copies; fixtures own only guarded temporary graphs.
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    with tempfile.TemporaryDirectory(prefix="project-manifest-candidate-") as tmp:
        temp = Path(tmp)
        for name in sorted(CANDIDATE_FILES | {"LICENSE", "mise.toml", "mise.lock"}):
            path = temp / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(bundle[name])
        result = subprocess.run(
            [sys.executable, "-B", "tests/run_corpus.py", "--scope", "all"],
            cwd=temp, env=env, capture_output=True, text=True, check=False,
        )
        print(f"Corpus observation: {label} intended source snapshot")
        print(result.stdout + result.stderr, end="")
        require(result.returncode == 0, "Candidate syntax/shape corpus failed")


def main():
    require(os.getenv("MISE_EXEC_AUTO_INSTALL") == "0",
            "Routine gate requires automatic installation disabled")
    require(platform.python_version() == PINS["python"]
            and sys.version_info.releaselevel == "final", "Python pin mismatch")
    require((platform.system(), platform.machine()) in {("Darwin", "arm64"), ("Linux", "x86_64")},
            "Source gate permits only selected macOS-arm64/Linux-x86_64 hosts")
    version = subprocess.run(["gitleaks", "--version"], capture_output=True,
                             text=True, check=False)
    match = re.search(r"\b\d+\.\d+\.\d+\b", version.stdout)
    require(version.returncode == 0 and match and match[0] == PINS["gitleaks"],
            "Gitleaks runtime pin mismatch")
    require(git("rev-parse", "--show-toplevel").decode().strip() == str(ROOT),
            "Run from the own child checkout")
    names = set(git("ls-files", "--cached", "--others",
                    "--exclude-standard", "-z").decode().split("\0")) - {""}
    index_metadata = git("ls-files", "--stage", "-z")
    indexed = parse_index(index_metadata)
    check_paths(names | indexed)
    require(names == FILES, "Candidate source layout is not complete/closed")
    require(indexed == FILES, "Index must contain the complete candidate source set")
    worktree = {name: read_source(name) for name in sorted(names)}
    index = {name: git("show", ":" + name) for name in sorted(indexed)}
    safety_probes()
    check_bundle(worktree)
    check_bundle(index)
    secret_scan(worktree, index)
    run_corpus(worktree, "worktree candidate")
    run_corpus(index, "full candidate index")
    require(git("ls-files", "--stage", "-z") == index_metadata,
            "Index shape changed during validation")
    observed_names = set(git("ls-files", "--cached", "--others",
                             "--exclude-standard", "-z").decode().split("\0")) - {""}
    require(observed_names == names, "Source names changed during validation")
    require(all(read_source(name) == data for name, data in worktree.items()),
            "Worktree bytes changed during validation")
    require(all(git("show", ":" + name) == data for name, data in index.items()),
            "Index bytes changed during validation")
    print("PASS: intended layout/governance/pins/lock/links/hygiene/privacy")
    print("PASS: regular index modes; symlink/gitlink/nonregular/unmerged rejection")
    print("PASS: synthetic safety probes and fully redacted Gitleaks source scan")
    print(f"Source: {len(worktree)} worktree files; {len(index)} index files")
    print(f"Tools: Python {PINS['python']}; Gitleaks {PINS['gitleaks']}")
    print("Index coverage: full candidate source and syntax/shape corpus")
    print("C4 activation/trusted candidate byte binding; complete v1 validity not checked")
    print("Development policy owner-frozen; broader acquisition/conformance and release remain unqualified")


if __name__ == "__main__":
    try:
        main()
    except (GateError, OSError, ValueError, KeyError, configparser.Error) as error:
        print("FAIL: " + (str(error) if isinstance(error, GateError)
                          else type(error).__name__), file=sys.stderr)
        raise SystemExit(1)
