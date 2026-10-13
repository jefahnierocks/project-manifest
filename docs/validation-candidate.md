# C2 candidate declaration validation

This unreleased extension adds executable semantic and exact-tree checks to
the [byte and shape reader](specification-candidate.md). It does not acquire
Git objects, verify a release or establish complete Specification 1 validity.

## Pure interface and evidence

Import `TreeEntry`, `TreeSnapshot` and `check_declaration` from
`project_manifest` with the local src directory on Python's import path:

```python
tree = TreeSnapshot((
    TreeEntry("docs", "directory"),
    TreeEntry("docs/status.example", "file"),
    TreeEntry("tools", "directory"),
    TreeEntry("tools/check.example", "file", executable=True),
))
result = check_declaration(document_bytes, tree=tree, reference_date="2026-01-01")
```

Tree records and document vectors are in memory; no fixture repository or
manifest file is created. The snapshot is caller-supplied and unverified.
It must declare completeness and contain a tuple of immutable TreeEntry
records. Every directory component is explicit; the root is implicit.
Records may be in any order. Duplicate paths, missing/non-directory parents,
unknown kinds, malformed paths or flags, and incomplete snapshots return
not checked. Kinds are file, directory, symlink and submodule. Only files
can carry a Boolean executable flag. No symlink target or submodule content
is represented or followed.

Unrelated tree names may be Unicode, but document references remain ASCII.
Tree paths cannot be empty, absolute, drive-prefixed, contain control bytes
or have empty/dot/dot-dot segments. Snapshot structure is validated without
filesystem access. Its completeness assertion is caller testimony, not proof
that records match a repository, revision or index.

The reference day is required: either an exact stdlib date or a valid
YYYY-MM-DD string. Datetime, missing values and malformed/impossible dates
return not checked. The API never reads a clock. Successful and semantic/tree
failure diagnostics record the normalized supplied reference day.

## Implemented semantics

The stated as_of must be a real Gregorian calendar date no later than the
reference day. Old dates never expire solely through age.

Canonical is uniformly required. It is null exactly when role is canonical;
otherwise it names an ID different from the project's own ID. Peers exclude
the own ID. C2 checks all five owner-adopted manifest enum sets described in the
[snapshot](enum-provenance.md). Cross-project ID/entity membership and
uniqueness remain producer responsibilities.

Peer, platform and requirement lists reject duplicates as an explicit C2
candidate default. Order is preserved. Empty platforms means no platform
claim; acceptance never supplies a portability receipt. C3 adds candidate
membership in macos-arm64, macos-x86_64, linux-arm64, linux-x86_64,
windows-arm64 and windows-x86_64. Unknown-axis tokens are excluded by
candidate policy; the generic axes themselves provide no pair restriction.
Activation-owner membership remains pending.

The producer runtime floor is Python 3.11+, so the declaration API uses that
candidate floor and returns not checked below it when import is possible.
The contract gate uses the project's pinned Python 3.13.16; supported-floor
qualification runs the same pure corpus separately on installed Python 3.11.
The version-guard test alone simulates branches and is not a live floor receipt.
The source CLI bootstrap enforces the floor before importing candidate
annotations on unsupported runtimes; branch simulation is not a live receipt.

## Candidate development policy

These closed sets implement candidate policy from the design; they are not
approved release enum snapshots:

| Field | Candidate policy |
| --- | --- |
| Activation owner | none, direnv, mise or project |
| Command runner | script or mise |
| Stack scope | host or checkout |
| Stack port_policy | unpublished or loopback_only |
| Host requirement | container_engine or android_sdk |

Activation owner selects project activation and non-secret configuration loading:

- none: no project activation/loading; a documentation-only template may exist.
- direnv: `.envrc` coordinates activation, including use-mise when appropriate;
  mise still owns runtime selection.
- mise: direct mise-native activation/non-secret configuration loading.
- project: tracked command-scoped native loading; there is no per-tool owner enum.

The exact set is closed; native is not an alias. Owner, template and secret_launcher
are independent declarations. No template/launcher is implied by an owner, and
their presence does not force a different owner. A null launcher declares that
no role uses secrets. Loader/task existence, activation effects and secretless
check behavior are separate conformance; no environment is loaded here.

Nonempty stacks require container_engine. Each non-null script role references
a supplied-tree regular executable file; all seven command roles use the same
rule. Optional environment templates reference regular files. Non-null secret
launchers reference regular executable files. Stack Compose declarations
reference regular files without parsing/interpolation. Null launcher means no
role may use secrets; that behavioral assertion remains conformance work.

Script and launcher paths use a candidate portable alphabet:
ASCII letters/digits, dot, underscore, hyphen and slash only. Segments must also
satisfy the path rules; spaces and shell/argv characters are rejected. The path
limit is 255 bytes. Paths are literal references, never executable authorization.

Mise targets are native task names, not file paths or argv. Their candidate
spelling is one or more lowercase token-shaped segments separated by single
colons, at most 64 bytes total. Single hyphen/underscore separators are allowed
within a segment; leading/trailing/adjacent separators fail. Examples such as
check and format:check describe task syntax, not approved project tasks.
Quoted task names need not exclude YAML reserved words. Task existence and role
effects require separate native-file conformance; mise is never evaluated.

Candidate policy defaults, duplicate rejection, platform-empty meaning, task
spelling and portable executable paths need freeze review. The kebab/underscore
enum-style conflict remains unresolved; no aliases or normalization are added.
No proposed vocabulary is silently promoted to release authority.

## Exact-tree references

All declared paths are relative, nonempty slash-separated ASCII segments.
Dot/dot-dot, absolute/drive-prefixed paths and .git in any letter case fail.
C2's case-insensitive reservation is an explicit candidate default; actual
tree lookup is always byte-exact and case-sensitive.

Each component must be present in the complete supplied tree. Intermediate
components must be directories; final components must be regular files.
Symlink, submodule or directory at a final file path is invalid. Executable
references additionally require the executable flag. A wrong-case or absent
path in a known complete snapshot is invalid. Unavailable, incomplete or
internally inconsistent evidence is not checked, never an empty healthy tree.

The pure API reads no referenced content and performs no Git, filesystem,
network, process or runtime operation. Its caller records remain unverified.
The separate [C3 adapter](acquisition-candidate.md) acquires bounded evidence
and exposes the exact TreeSnapshot used by C2 beside accepted Python records.
A staged or working observation is never mislabeled as a committed verdict.

## Results and remaining gates

DeclarationResult provides exit_code, candidate_declaration_accepted, findings
and a normalized record only on success. Exit 0 covers C2 candidate declaration
checks; exit 1 rejects the document; exit 2 means required evidence is unreliable.
The syntax phase uses the C1 reader, including the three source-confirmed legacy
rejections, and retains its safe findings.
Then reference-day evidence is checked, followed by enum/semantic rules, snapshot
structure and references in fixed order. Semantic/tree findings have zero
line/column; predefined fields and wildcard stack classes never echo values.

`diagnostics()` excludes the record, labels caller-supplied-unverified tree
evidence, owner-adopted manifest domains and separate candidate-unapproved
development policy, and always returns
`complete_v1_validity: not_checked`. Input-derived records remain data,
not safe diagnostic output.

New provisional codes are DATE_RULE, ROLE_RELATION, LIST_DUPLICATE,
FIELD_RELATION, ENUM_UNSUPPORTED, TARGET_RULE, REFERENCE_MISSING and
REFERENCE_MODE; FIELD_BOUND, REFERENCE_PATH and NOT_CHECKED retain their
candidate meanings. These are not published compatibility identifiers.

Remaining work is concrete: complete-release provenance/binding; development
vocabulary approval; producer legacy dispatch;
fresh minimum-runtime and cross-loader evidence; broader acquisition qualification;
immutable release binding/offline vendoring; native task/role/declaration
conformance; producer admission/identity invariance and runtime acceptance.
No release/publication/adoption or discoverable v1 root manifest follows from C2.
