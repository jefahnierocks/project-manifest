"""Fresh synthetic comparison using installed safe YAML loaders; no installation."""

import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).absolute().parent.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
from project_manifest import check_candidate
from test_candidate import BASE, STACK, changed

RUBY = """
require 'psych'
require 'json'
if ARGV == ['version']
  puts JSON.generate({ruby: RUBY_VERSION, psych: Psych::VERSION, libyaml: Psych.libyaml_version})
else
  text = STDIN.read
  value = if Psych::VERSION.split('.')[0].to_i < 4
    Psych.safe_load(text, [], [], false)
  else
    Psych.safe_load(text, permitted_classes: [], permitted_symbols: [], aliases: false)
  end
  puts JSON.generate(value)
end
"""


def vectors():
    accepted = {"base": BASE, "stack": changed(b"  stacks: {}\n", STACK),
                "comment": b"# Synthetic comparison\n\n" + BASE,
                "quoted_reserved": changed(b'  display_name: "Synthetic example"\n', b'  display_name: "yes"\n')}
    for owner in ("none", "direnv", "mise", "project"):
        accepted["activation_" + owner] = changed(
            b"    owner: sample-activation\n", b"    owner: " + owner.encode() + b"\n")
    refused = {
        "duplicate_key": BASE + b'authority:\n  status_of_record: "docs/status.example"\n',
        "reserved_token": changed(b"role: sample-role\n", b"role: yes\n"),
        "single_quote": changed(b'  display_name: "Synthetic example"\n', b"  display_name: 'Synthetic example'\n"),
        "flow_map": changed(b"project:\n", b"project: {}\n"),
        "unicode": changed(b'  display_name: "Synthetic example"\n', '  display_name: "Synthetic caf\u00e9"\n'.encode()),
        "legacy_version": changed(b'spec_version: "1"\n', b"spec_version: 0.1\n"),
        "crlf": BASE.replace(b"\n", b"\r\n"),
    }
    return accepted, refused


def ruby_loader(executable, data):
    result = subprocess.run([executable, "-e", RUBY], input=data, capture_output=True,
                            timeout=5, check=False)
    if result.returncode:
        raise ValueError("LOADER_REFUSED")
    return json.loads(result.stdout)


def main():
    accepted, refused = vectors()
    strict = {name: check_candidate(data) for name, data in accepted.items()}
    if any(result.exit_code for result in strict.values()) or any(
        check_candidate(data).exit_code != 1 for data in refused.values()
    ):
        print(json.dumps({"exit_code": 1, "reason": "STRICT_CONTROL_FAILED"}))
        return 1
    loaders, unavailable = [], []
    if importlib.util.find_spec("yaml") is not None:
        import yaml
        for name in ("SafeLoader", "CSafeLoader"):
            loader = getattr(yaml, name, None)
            if loader is None:
                unavailable.append("PyYAML." + name)
            else:
                loaders.append(("PyYAML." + name, {"pyyaml": yaml.__version__,
                    "libyaml_enabled": bool(getattr(yaml, "__with_libyaml__", False))},
                    lambda data, loader=loader: yaml.load(data, Loader=loader)))
    else:
        unavailable.extend(("PyYAML.SafeLoader", "PyYAML.CSafeLoader"))
    ruby_paths = sorted({str(Path(path).resolve()) for path in
                         ("/usr/bin/ruby", "/opt/homebrew/bin/ruby") if Path(path).is_file()})
    if not ruby_paths:
        unavailable.append("Ruby.Psych")
    for path in ruby_paths:
        version = subprocess.run([path, "-e", RUBY, "version"], capture_output=True,
                                 timeout=5, check=False)
        if version.returncode:
            unavailable.append("Ruby.Psych")
            continue
        metadata = json.loads(version.stdout)
        loaders.append(("Ruby.Psych." + metadata["psych"], metadata,
                        lambda data, path=path: ruby_loader(path, data)))
    reports, mismatch = [], False
    for name, version, load in loaders:
        agreements, differences, broad = [], [], []
        for label, data in accepted.items():
            try:
                value = load(data)
                agreed = value == strict[label].record
            except Exception:
                agreed = False
            (agreements if agreed else differences).append(label)
        for label, data in refused.items():
            try:
                load(data)
                broad.append(label)
            except Exception:
                pass
        mismatch = mismatch or bool(differences)
        reports.append({"loader": name, "version": version, "agreements": agreements,
                        "differences": differences, "broader_yaml_acceptance": broad})
    code = 1 if mismatch else (0 if loaders else 2)
    report = {
        "scope": "fresh-installed-loader-synthetic-comparison", "exit_code": code,
        "python": platform.python_version(), "host": platform.system(),
        "accepted_vectors": len(accepted), "strict_refusal_vectors": len(refused),
        "vectors": {name: hashlib.sha256(data).hexdigest() for name, data in
                    (accepted | refused).items()}, "loaders": reports,
        "unavailable": unavailable, "other_loaders": "not_checked",
        "release_qualification": "not_checked",
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
