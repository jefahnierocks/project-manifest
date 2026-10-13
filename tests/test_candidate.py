"""Synthetic public behavior vectors; no manifest or Git fixture files."""

import contextlib
import io
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).absolute().parent.parent / "src"))
from project_manifest import check_candidate

BASE = b'''spec_version: "1"
project:
  id: sample-project
  display_name: "Synthetic example"
  owner_entity: sample-owner
role: sample-role
canonical: null
peers: []
status:
  posture: sample-posture
  operational_state: sample-state
  local_phase: "Synthetic phase"
  as_of: "2026-01-01"
authority:
  status_of_record: "docs/status.example"
presentation:
  visibility: sample-visibility
  public_alias: null
  link_policy: sample-link
development:
  platforms: []
  commands:
    setup: null
    check:
      runner: sample-runner
      target: "check-example"
    test: null
    build: null
    dev: null
    format_check: null
    format_write: null
  environment:
    owner: sample-activation
    template: null
    secret_launcher: null
  stacks: {}
  host_requirements: []
'''
STACK = b'''  stacks:
    sample-stack:
      compose: "stacks/compose.example"
      instance_scope: sample-scope
      port_policy: sample-policy
'''
EXPANDED = BASE.replace(b"  stacks: {}\n", STACK)
OPTIONAL_ROLES = (b"setup", b"test", b"build", b"dev", b"format_check", b"format_write")


def changed(old, new, data=BASE):
    if data.count(old) != 1:
        raise AssertionError("Synthetic replacement is not unique")
    return data.replace(old, new)


def full_declaration_shape():
    data = EXPANDED
    for role in OPTIONAL_ROLES:
        data = changed(b"    " + role + b": null\n", b"    " + role + b":\n"
                       b"      runner: sample-runner\n" b'      target: "sample-task"\n', data)
    for old, new in (
        (b"canonical: null\n", b"canonical: sample-parent\n"),
        (b"  public_alias: null\n", b'  public_alias: "Synthetic alias"\n'),
        (b"    template: null\n", b'    template: "config/example.env"\n'),
        (b"    secret_launcher: null\n", b'    secret_launcher: "scripts/example-launcher"\n'),
    ):
        data = changed(old, new, data)
    return data


# Independent public contract positions, not imported from the reader's SHAPE.
REQUIRED_POSITIONS = (
    "project", "role", "canonical", "peers", "status", "authority",
    "presentation", "development",
) + tuple(parent + "." + key for parent, keys in (
    ("project", ("id", "display_name", "owner_entity")),
    ("status", ("posture", "operational_state", "local_phase", "as_of")),
    ("authority", ("status_of_record",)),
    ("presentation", ("visibility", "public_alias", "link_policy")),
    ("development", ("platforms", "commands", "environment", "stacks", "host_requirements")),
    ("development.environment", ("owner", "template", "secret_launcher")),
    ("development.stacks.sample-stack", ("compose", "instance_scope", "port_policy")),
) for key in keys) + tuple(
    "development.commands." + role.decode() + suffix
    for role in (b"check",) + OPTIONAL_ROLES for suffix in ("", ".runner", ".target")
)
NULLABLE_POSITIONS = frozenset((
    "canonical", "presentation.public_alias", "development.environment.template",
    "development.environment.secret_launcher",
)) | frozenset("development.commands." + role.decode() for role in OPTIONAL_ROLES)


def edit_fixture_field(data, field, *, omit=False):
    # Locate only this trusted fixture's line block; no validator/parser internals.
    lines, stack = data.splitlines(keepends=True), []
    for start, line in enumerate(lines):
        depth = (len(line) - len(line.lstrip(b" "))) // 2
        key = line.lstrip(b" ").split(b":", 1)[0].decode("ascii")
        stack = stack[:depth] + [key]
        if ".".join(stack) != field:
            continue
        end = start + 1
        while end < len(lines) and len(lines[end]) - len(lines[end].lstrip(b" ")) > depth * 2:
            end += 1
        replacement = b"" if omit else b" " * (depth * 2) + key.encode() + b": null\n"
        changed_data = b"".join(lines[:start]) + replacement + b"".join(lines[end:])
        # Keep a sole-child omission syntactically valid so shape requiredness,
        # rather than an orphan empty-header grammar error, determines rejection.
        if omit and field == "authority.status_of_record":
            changed_data = changed(b"authority:\n", b"authority: {}\n", changed_data)
        return changed_data
    raise AssertionError("Public fixture field was not found")


class CandidateTests(unittest.TestCase):
    def accepted(self, data):
        result = check_candidate(data)
        self.assertEqual(result.exit_code, 0, result.diagnostics())
        self.assertTrue(result.syntax_shape_accepted)
        self.assertEqual(result.findings, ())
        self.assertIsInstance(result.record, dict)
        self.assertEqual(result.diagnostics()["complete_v1_validity"], "not_checked")
        self.assertNotIn("record", result.diagnostics())
        return result.record

    def rejected(self, data, code):
        result = check_candidate(data)
        self.assertEqual(result.exit_code, 1, result.diagnostics())
        self.assertFalse(result.syntax_shape_accepted)
        self.assertIsNone(result.record)
        self.assertEqual(len(result.findings), 1)
        self.assertEqual(result.findings[0].code, code)
        self.assertEqual(result.diagnostics()["complete_v1_validity"], "not_checked")
        return result

    def test_normalized_record_and_determinism(self):
        record = self.accepted(BASE)
        self.assertEqual(record["spec_version"], "1")
        self.assertEqual(record["project"], {
            "id": "sample-project", "display_name": "Synthetic example",
            "owner_entity": "sample-owner",
        })
        self.assertIsNone(record["canonical"])
        self.assertEqual(record["peers"], [])
        self.assertEqual(record["development"]["stacks"], {})
        self.assertEqual(record["development"]["commands"]["check"], {
            "runner": "sample-runner", "target": "check-example",
        })
        self.assertEqual(check_candidate(BASE), check_candidate(BASE))

    def test_every_fixed_field_is_required_even_when_nullable(self):
        data = full_declaration_shape()
        self.accepted(data)
        self.assertEqual(len(REQUIRED_POSITIONS), 51)
        self.assertEqual(len(set(REQUIRED_POSITIONS)), 51)
        for field in REQUIRED_POSITIONS:
            with self.subTest(field=field):
                self.rejected(edit_fixture_field(data, field, omit=True), "KEY_REQUIRED")
        # Version removal belongs to first-content selection, not map requiredness.
        self.rejected(changed(b'spec_version: "1"\n', b"", data), "VERSION_LINE")

    def test_nullability_of_every_fixed_record_and_leaf(self):
        data = full_declaration_shape()
        for field in REQUIRED_POSITIONS:
            with self.subTest(field=field):
                candidate = edit_fixture_field(data, field)
                if field in NULLABLE_POSITIONS:
                    self.accepted(candidate)
                else:
                    self.rejected(candidate, "FIELD_TYPE")
        self.rejected(edit_fixture_field(data, "development.stacks.sample-stack"), "FIELD_TYPE")

    def test_full_development_shape(self):
        data = EXPANDED
        for role in OPTIONAL_ROLES:
            data = changed(b"    " + role + b": null\n",
                           b"    " + role + b":\n"
                           b"      runner: sample-runner\n"
                           b'      target: "sample-task"\n', data)
        data = changed(b"    template: null\n", b'    template: "config/example.env"\n', data)
        data = changed(b"    secret_launcher: null\n",
                       b'    secret_launcher: "scripts/example-launcher"\n', data)
        data = changed(b"canonical: null\n", b"canonical: sample-parent\n", data)
        data = changed(b"  public_alias: null\n", b'  public_alias: "Example alias"\n', data)
        data = changed(b"peers: []\n", b"peers: [sample-peer, other-peer]\n", data)
        data = changed(b"  platforms: []\n",
                       b"  platforms: [sample-platform, other-platform]\n", data)
        data = changed(b"  host_requirements: []\n",
                       b"  host_requirements: [sample-engine]\n", data)
        record = self.accepted(data)
        self.assertEqual(len(record["development"]["commands"]), 7)
        self.assertEqual(record["development"]["stacks"]["sample-stack"]["compose"],
                         "stacks/compose.example")
        self.assertEqual(record["peers"], ["sample-peer", "other-peer"])

    def test_comments_blanks_and_unordered_keys(self):
        self.accepted(b"# Before version\n\n   # Odd comment indentation\n" + BASE + b"\n# End\n")
        self.accepted(changed(b"role: sample-role\ncanonical: null\n",
                              b"canonical: null\nrole: sample-role\n"))
        self.accepted(changed(b"  id: sample-project\n", b"# Outside indentation\n  id: sample-project\n"))
        self.accepted(b" " * 2047 + b"#\n" + BASE)

    def test_quoted_punctuation_and_null_text(self):
        record = self.accepted(changed(b'  display_name: "Synthetic example"\n',
                                       b'  display_name: "# literal: punctuation [] {}"\n'))
        self.assertEqual(record["project"]["display_name"], "# literal: punctuation [] {}")
        record = self.accepted(changed(b"  public_alias: null\n", b'  public_alias: "null"\n'))
        self.assertEqual(record["presentation"]["public_alias"], "null")
        self.rejected(changed(b"canonical: null\n", b'canonical: "null"\n'), "FIELD_TYPE")

    def test_version_line(self):
        for first in (b'spec_version: "2"', b"spec_version: 1", b'spec_version: "0.10"',
                      b"spec_version: 0.10", b'spec_version: "0.1"',
                      b"spec_version: '0.1'", b"spec_version: 0.1",
                      b' spec_version: "1"', b'  spec_version: "1"',
                      b'spec_version:  "1"', b'spec_version:"1"',
                      b'spec_version: "1" # comment'):
            with self.subTest(first=first):
                code = "GRAMMAR" if first.startswith(b" ") and not first.startswith(b"  ") else "VERSION_LINE"
                if first in (b'spec_version: "0.1"', b"spec_version: '0.1'", b"spec_version: 0.1"):
                    code = "LEGACY_VERSION"
                self.rejected(changed(b'spec_version: "1"\n', first + b"\n"), code)
        self.rejected(b"# Nothing\n\n", "KEY_REQUIRED")
        self.rejected(changed(b'spec_version: "1"\n', b""), "VERSION_LINE")
        self.rejected(BASE + b'spec_version: "1"\n', "KEY_DUPLICATE")

    def test_bytes(self):
        self.rejected(b"", "BYTE_PROFILE")
        self.rejected(BASE[:-1], "BYTE_PROFILE")
        for prefix in (b"\xef\xbb\xbf", b"\x00", b"\t", b"\r", b"\x7f", b"\x85",
                       "\u2028".encode(), "\u2029".encode(), "\u200b".encode(),
                       "\u00e9".encode(), "e\u0301".encode(), "\u0441".encode()):
            with self.subTest(prefix=prefix):
                self.rejected(prefix + BASE, "BYTE_PROFILE")
        self.rejected(BASE.replace(b"\n", b"\r\n"), "BYTE_PROFILE")
        self.rejected(BASE + b" \n", "BYTE_PROFILE")
        self.rejected(changed(b"peers: []\n", b"peers: [] \n"), "BYTE_PROFILE")
        self.rejected(changed(b"project:\n", b"project:\t\n"), "BYTE_PROFILE")

    def test_prohibited_forms(self):
        for value in (b"&sample", b"*sample", b"!sample", b"!!str sample",
                      b"{sample: value}", b"|", b">", b"'sample'", b"~",
                      b"sample # comment", b'"sample" # comment',
                      b'["sample"]', b"[sample,\n  other]", b"[ ]"):
            with self.subTest(value=value):
                self.rejected(changed(b"role: sample-role\n", b"role: " + value + b"\n"), "GRAMMAR")
        for line in (b"---\n", b"...\n", b"<<: *sample\n", b"- sample\n", b"? sample\n"):
            with self.subTest(line=line):
                self.rejected(BASE + line, "GRAMMAR")
        self.rejected(changed(b"peers: []\n", b"peers:\n  - sample\n"), "GRAMMAR")
        self.rejected(changed(b'  local_phase: "Synthetic phase"\n',
                              b'  local_phase: "first\n    second"\n'), "GRAMMAR")

    def test_spacing_indentation_and_depth(self):
        for old, new in (
            (b"  id: sample-project\n", b" id: sample-project\n"),
            (b"  id: sample-project\n", b"    id: sample-project\n"),
            (b"  id: sample-project\n", b"  id:sample-project\n"),
            (b"  id: sample-project\n", b"  id:  sample-project\n"),
            (b"  id: sample-project\n", b"  id : sample-project\n"),
            (b"project:\n", b"project: {}\n"),
            (b"peers: []\n", b"peers:\n"),
            (b"  stacks: {}\n", b"  stacks:\n"),
            (b'      target: "check-example"\n', b"      target:\n        deep: sample\n"),
        ):
            with self.subTest(new=new):
                self.rejected(changed(old, new), "GRAMMAR")
        for value in (b"[sample,other]", b"[sample,  other]", b"[ sample, other]",
                      b"[sample, other ]", b"[sample,]", b"[sample , other]"):
            with self.subTest(value=value):
                self.rejected(changed(b"peers: []\n", b"peers: " + value + b"\n"), "GRAMMAR")
        self.accepted(changed(b"peers: []\n", b"peers: [sample, other]\n"))

    def test_duplicate_keys_at_all_mapping_levels(self):
        for line, data in (
            (b"role: sample-role\n", BASE),
            (b"  id: sample-project\n", BASE),
            (b"  posture: sample-posture\n", BASE),
            (b'  status_of_record: "docs/status.example"\n', BASE),
            (b"  visibility: sample-visibility\n", BASE),
            (b"  platforms: []\n", BASE),
            (b"    setup: null\n", BASE),
            (b"      runner: sample-runner\n", BASE),
            (b"    owner: sample-activation\n", BASE),
            (b"    sample-stack:\n", EXPANDED),
            (b"      port_policy: sample-policy\n", EXPANDED),
        ):
            with self.subTest(line=line):
                if line == b"    sample-stack:\n":
                    duplicate = STACK[STACK.index(line):]
                    candidate = EXPANDED.replace(STACK, STACK + duplicate)
                else:
                    candidate = changed(line, line + line, data)
                self.rejected(candidate, "KEY_DUPLICATE")

    def test_unknown_keys_at_all_mapping_levels(self):
        for line, data in (
            (b"role: sample-role\n", BASE),
            (b"  id: sample-project\n", BASE),
            (b"  posture: sample-posture\n", BASE),
            (b'  status_of_record: "docs/status.example"\n', BASE),
            (b"  visibility: sample-visibility\n", BASE),
            (b"  platforms: []\n", BASE),
            (b"    setup: null\n", BASE),
            (b"      runner: sample-runner\n", BASE),
            (b"    owner: sample-activation\n", BASE),
            (b"      port_policy: sample-policy\n", EXPANDED),
        ):
            with self.subTest(line=line):
                indent = len(line) - len(line.lstrip(b" "))
                self.rejected(changed(line, line + b" " * indent + b"extra: sample\n", data),
                              "KEY_UNKNOWN")
        self.accepted(EXPANDED.replace(b"sample-stack:", b"other_stack-name:"))

    def test_missing_keys_at_all_mapping_levels(self):
        for line, data in (
            (b"role: sample-role\n", BASE),
            (b"canonical: null\n", BASE),
            (b"  id: sample-project\n", BASE),
            (b"  posture: sample-posture\n", BASE),
            (b"  visibility: sample-visibility\n", BASE),
            (b"  platforms: []\n", BASE),
            (b"    setup: null\n", BASE),
            (b"      runner: sample-runner\n", BASE),
            (b"    owner: sample-activation\n", BASE),
            (b"      port_policy: sample-policy\n", EXPANDED),
        ):
            with self.subTest(line=line):
                self.rejected(changed(line, b"", data), "KEY_REQUIRED")
        self.rejected(changed(b'  status_of_record: "docs/status.example"\n', b"  extra: sample\n"),
                      "KEY_UNKNOWN")
        self.rejected(changed(b'authority:\n  status_of_record: "docs/status.example"\n',
                              b"authority: {}\n"), "KEY_REQUIRED")

    def test_nonnullable_records_and_leaf_types(self):
        for old, new in (
            (b"project:\n  id: sample-project\n  display_name: \"Synthetic example\"\n  owner_entity: sample-owner\n",
             b"project: null\n"),
            (b'authority:\n  status_of_record: "docs/status.example"\n', b"authority: null\n"),
            (b'    check:\n      runner: sample-runner\n      target: "check-example"\n', b"    check: null\n"),
            (b"  stacks: {}\n", b"  stacks: null\n"),
            (b"peers: []\n", b"peers: null\n"),
            (b"  platforms: []\n", b'  platforms: "sample-platform"\n'),
            (b"  host_requirements: []\n", b"  host_requirements: {}\n"),
            (b'  display_name: "Synthetic example"\n', b"  display_name: sample\n"),
            (b"  id: sample-project\n", b'  id: "sample"\n'),
            (b"    setup: null\n", b"    setup: sample\n"),
        ):
            with self.subTest(new=new):
                self.rejected(changed(old, new), "FIELD_TYPE")
        for key in (b"template", b"secret_launcher"):
            self.rejected(changed(b"    " + key + b": null\n", b"    " + key + b": sample\n"),
                          "FIELD_TYPE")
        self.rejected(changed(b"    setup: null\n", b"    setup: {}\n"), "KEY_REQUIRED")

    def test_token_boundaries_and_reserved_spellings(self):
        for value in (b"a", b"a" * 64, b"a-b_c2"):
            self.accepted(changed(b"  id: sample-project\n", b"  id: " + value + b"\n"))
        self.rejected(changed(b"  id: sample-project\n", b"  id: " + b"a" * 65 + b"\n"), "FIELD_BOUND")
        for value in (b"y", b"n", b"yes", b"no", b"on", b"off", b"true", b"false",
                      b"Null", b"NULL", b"Yes", b"TRUE", b"1", b"0x10", b".inf", b"1e3",
                      b"a--b", b"a__b", b"a-_b", b"a_-b", b"-a", b"a-", b"a_", b"A"):
            with self.subTest(value=value):
                self.rejected(changed(b"  id: sample-project\n", b"  id: " + value + b"\n"), "GRAMMAR")
        self.rejected(changed(b"  id: sample-project\n", b"  id: null\n"), "FIELD_TYPE")
        self.rejected(changed(b"peers: []\n", b"peers: [null]\n"), "GRAMMAR")
        for name, code in ((b"a" * 64, None), (b"a" * 65, "FIELD_BOUND"),
                           (b"yes", "GRAMMAR"), (b"a--b", "GRAMMAR")):
            data = EXPANDED.replace(b"sample-stack:", name + b":")
            if code:
                self.rejected(data, code)
            else:
                self.accepted(data)

    def test_text_boundaries(self):
        for old, maximum in (
            (b'  display_name: "Synthetic example"\n', 100),
            (b"  public_alias: null\n", 100),
            (b'  local_phase: "Synthetic phase"\n', 400),
            (b'      target: "check-example"\n', 255),
        ):
            key = old.split(b":", 1)[0]
            for length in (1, maximum):
                with self.subTest(key=key, length=length):
                    self.accepted(changed(old, key + b': "' + b"x" * length + b'"\n'))
            self.rejected(changed(old, key + b': "' + b"x" * (maximum + 1) + b'"\n'), "FIELD_BOUND")
            self.rejected(changed(old, key + b': ""\n'), "GRAMMAR")
        for value in (b'" leading"', b'"trailing "', b'"contains\\"quote"', b'"back\\slash"'):
            self.rejected(changed(b'  display_name: "Synthetic example"\n',
                                  b"  display_name: " + value + b"\n"), "GRAMMAR")

    def test_path_boundaries_and_lexical_rules(self):
        for old, data in (
            (b'  status_of_record: "docs/status.example"\n', BASE),
            (b"    template: null\n", BASE),
            (b"    secret_launcher: null\n", BASE),
            (b'      compose: "stacks/compose.example"\n', EXPANDED),
        ):
            key = old.split(b":", 1)[0]
            for length in (1, 255):
                self.accepted(changed(old, key + b': "' + b"x" * length + b'"\n', data))
            self.rejected(changed(old, key + b': "' + b"x" * 256 + b'"\n', data), "FIELD_BOUND")
            self.rejected(changed(old, key + b': ""\n', data), "GRAMMAR")
            for path in (b"/absolute", b"C:/absolute", b"a//b", b"a/", b".", b"..",
                         b"a/../b", b"a/./b", b".git/config", b"a/.git/b",
                         b"a/ b", b"a /b"):
                with self.subTest(key=key, path=path):
                    self.rejected(changed(old, key + b': "' + path + b'"\n', data), "REFERENCE_PATH")
        self.accepted(changed(b'  status_of_record: "docs/status.example"\n',
                              b'  status_of_record: ".GIT/Not-a-tree-proof"\n'))

    def test_date_format_and_semantic_deferrals(self):
        for value, code in ((b'"2026-1-01"', "DATE_FORMAT"),
                            (b'"2026-aa-01"', "DATE_FORMAT"),
                            (b'"20260-01-01"', "FIELD_BOUND"), (b"sample-date", "FIELD_TYPE")):
            self.rejected(changed(b'  as_of: "2026-01-01"\n', b"  as_of: " + value + b"\n"), code)
        for date in (b"0000-00-00", b"2026-02-31", b"9999-12-31"):
            self.accepted(changed(b'  as_of: "2026-01-01"\n', b'  as_of: "' + date + b'"\n'))
        self.accepted(changed(b"role: sample-role\n", b"role: canonical\n"))
        self.accepted(changed(b"canonical: null\n", b"canonical: sample-project\n"))
        self.accepted(changed(b"peers: []\n", b"peers: [sample-project, sample-project]\n"))
        self.accepted(changed(b"  platforms: []\n", b"  platforms: [sample, sample]\n"))
        self.accepted(changed(b"  host_requirements: []\n", b"  host_requirements: [sample, sample]\n"))
        self.accepted(changed(b"      runner: sample-runner\n", b"      runner: mise\n").replace(
            b'      target: "check-example"\n', b'      target: "' + b"x" * 255 + b'"\n'))

    def test_file_and_line_boundaries(self):
        self.accepted(BASE + b"\n" * (65_536 - len(BASE)))
        self.rejected(BASE + b"\n" * (65_537 - len(BASE)), "FIELD_BOUND")
        self.accepted(BASE + b"#" + b"x" * 2047 + b"\n")
        self.rejected(BASE + b"#" + b"x" * 2048 + b"\n", "FIELD_BOUND")

    def test_diagnostics_are_value_blind_and_silent(self):
        marker = b"synthetic-marker-abcdef"
        cases = (
            BASE + marker + b": sample\n",
            EXPANDED.replace(b"sample-stack:", marker + b":").replace(
                b"      port_policy: sample-policy\n", b"      " + marker + b": sample\n"),
            changed(b"  id: sample-project\n", b'  id: "' + marker + b'"\n'),
            changed(b'  status_of_record: "docs/status.example"\n',
                    b'  status_of_record: "../' + marker + b'"\n'),
        )
        for data in cases:
            with self.subTest(case=len(data)):
                stdout, stderr = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    result = check_candidate(data)
                self.assertEqual(result.exit_code, 1)
                self.assertNotIn(marker.decode(), json.dumps(result.diagnostics()))
                self.assertNotIn(marker.decode(), repr(result))
                self.assertNotIn(marker.decode(), stdout.getvalue() + stderr.getvalue())
                finding = result.findings[0]
                self.assertGreater(finding.line, 0)
                self.assertGreater(finding.column, 0)
                self.assertNotIn("sample-stack", finding.field)

    def test_wrong_input_type_not_checked(self):
        for data in (BASE.decode(), bytearray(BASE), None, 1, memoryview(BASE)):
            with self.subTest(kind=type(data).__name__):
                result = check_candidate(data)
                self.assertEqual(result.exit_code, 2)
                self.assertEqual(result.findings[0].code, "NOT_CHECKED")
                self.assertIsNone(result.record)
                self.assertFalse(result.syntax_shape_accepted)


if __name__ == "__main__":
    unittest.main()
