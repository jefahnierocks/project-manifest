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
claim; acceptance never supplies a portability receipt. The declaration API
checks candidate membership in macos-arm64, macos-x86_64, linux-arm64, linux-x86_64,
windows-arm64 and windows-x86_64. Unknown-axis tokens are excluded by
candidate policy; the generic axes themselves provide no pair restriction.
Activation-owner membership is implemented for none/direnv/mise/project;
release-policy approval and actual activation behavior remain separate.

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

## Proposed development-policy freeze

This is one concrete freeze recommendation, not owner approval. Retain the exact
implemented literal sets and bounds rather than introducing incompatible aliases:

| Decision | Proposed frozen rule |
| --- | --- |
| Platform tokens | macos-arm64, macos-x86_64, linux-arm64, linux-x86_64, windows-arm64, windows-x86_64; empty means no platform claim |
| Runner tokens | script or mise; every non-null command role uses the same runner-specific rules |
| Activation owner tokens | none, direnv, mise or project, with the independent template/launcher semantics above |
| Stack keys and tokens | compose, instance_scope and literal port_policy; scope host/checkout; policy unpublished/loopback_only |
| Requirement tokens and implication | container_engine/android_sdk; any nonempty stacks require container_engine |
| List policy | Peer, platform and requirement duplicates are invalid; retain declared order; no deduplication or inferred values |
| Script/launcher targets | Literal relative portable paths, maximum 255 bytes, exact regular executable tree reference, no .git component in any letter case or argv |
| Mise targets | Quoted task names, maximum 64 bytes, lowercase token segments separated by single colons; no path/argv interpretation or task evaluation |
| Token spelling | Retain current literal underscore-bearing values, including container_engine, android_sdk and loopback_only; no blanket kebab-only restriction |

General bare tokens continue to allow single hyphen or underscore separators.
Closed sets require exact literal membership; no aliases, case folding or hidden
normalization are proposed. An alternative replacing existing underscores with
hyphens is a distinct owner decision requiring compatibility and release review,
not a style-only edit. The five generic manifest domains, uniform canonical
relation and full development shape are settled and are not reopened here.
These development defaults remain candidate-unapproved until the owner freezes
them. Native task/effect/activation and Compose safety acceptance are not implied.


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

## Declaration corpus coverage

The following map records inspected fixture bodies, not just test-method names.
Positions refer to the public [field inventory](field-table.md). Test names below
are in tests/test_candidate.py (CandidateTests) or tests/test_validation.py
(DeclarationTests). Inline vectors contain fresh synthetic values; no project
command, native tool, referenced content, clock or producer is evaluated.

| Candidate rule group | Positive / negative / boundary fixtures |
| --- | --- |
| Byte/line profile | test_bytes checks LF/ASCII, controls/BOM/Unicode/missing LF/trailing spaces; test_file_and_line_boundaries accepts 65,536 file bytes/2,048 line bytes and rejects the next byte |
| First content and legacy dispatch boundary | test_version_line covers exact quoted1, missing/duplicate/wrong spellings and the three legacy forms; test_legacy_forms_remain_invalid_and_dispatchable retains legacy rejection without producer dispatch |
| Grammar and closed mappings | test_comments_blanks_and_unordered_keys; test_prohibited_forms; test_spacing_indentation_and_depth; duplicate/unknown-key fixtures reach every mapping class, including dynamic stack records |
| Byte-reader fixed keys and nullability | test_every_fixed_field_is_required_even_when_nullable removes all 51 fixed positions beyond the version guard; sole-child removal uses an explicit empty map; test_nullability_of_every_fixed_record_and_leaf accepts only the ten nullable positions and rejects null elsewhere, including a present stack record |
| Scalar/token/path bounds | test_token_boundaries_and_reserved_spellings covers 1/64/65-byte IDs and dynamic names; test_text_boundaries covers 1/max/max+1 and empty strings; test_path_boundaries_and_lexical_rules applies 1/255/256 and unsafe spellings to every reference class |
| Gregorian date and explicit reference day | test_calendar_dates_and_future_boundary covers real leap/calendar limits, future refusal and old dates; test_reference_date_evidence_not_checked rejects missing, malformed, impossible and datetime evidence |
| Adopted domains and identity relations | test_all_five_owner_adopted_enum_sets_and_unknown_rejection tests every adopted value; test_selected_uniform_canonical_and_own_id_rules covers null/role/own-ID and peer relations; no cross-project lookup |
| Lists and platform claims | test_list_uniqueness_and_empty_platform_claim checks all three duplicate classes; test_candidate_platform_domain_is_closed_and_empty_remains_no_claim tests all six tokens and unknown-axis refusal |
| Runner-specific semantics in every role | test_closed_candidate_runner_vocabulary and test_task_spelling_and_bounds; test_mise_target_rules_in_every_role_do_not_check_native_existence reaches all seven roles at 64/65 bytes and invalid task paths while denying native I/O |
| Executable script references | test_each_command_role_requires_executable_script supplies/misses every optional role; test_optional_script_roles_require_their_own_executable_mode checks each optional role independently from the valid check role; test_script_target_literal_path_and_bounds covers 255/256 and argv refusal |
| Environment independence and references | test_activation_owner_domain_and_rejected_alias checks all four owners and unsupported alternatives; test_activation_template_and_secret_launcher_are_independent covers all 16 combinations; test_environment_optional_references_and_launcher_mode checks absent/file/mode/unsafe-path evidence |
| Stack policy and requirements | test_stack_requirement_scope_policy_and_compose tests both scopes/policies, unsupported values, Compose file presence and engine implication; byte fixtures reject unknown/missing fixed stack keys and retain empty-map shape |
| Exact complete-tree evidence | test_exact_case_lookup_and_directory_nodes covers literal case, order, unrelated Unicode and final directories; symlink/submodule and unavailable/malformed tree fixtures reject unsafe, incomplete, duplicate and inconsistent records; known-empty tree gives missing-reference rejection |
| Safe pure result/evidence boundary | diagnostic fixtures exclude records/values/dynamic keys from failure output; test_syntax_then_semantics_then_evidence_order fixes phase ordering; test_no_filesystem_process_network_or_clock_operations denies native I/O; runtime guard simulation is not a live runtime receipt |

This is finite candidate declaration coverage, not an exhaustive program-state
proof or complete-release receipt. Acquisition storage/host cases and bootstrap
byte-binding tamper cases belong to their separate existing corpora. Passing
them cannot prove native task existence, role effects, secretless check behavior,
activation correctness, actual Compose port/concurrency safety or host capability.
Those claims need project/consumer acceptance; validation executes no project code.

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

Remaining declaration authority is the explicit development-policy freeze;
any subsequently selected missing validity rule requires its own source/corpus
delta. Native task existence, role effects, secretless check, activation behavior
and Compose runtime safety belong to project/consumer acceptance, not execution
inside the validator. Producer legacy dispatch and cross-project identity/join
invariance remain producer-owned.

Complete-release provenance, approved artifact/consumer lock and bootstrap trust,
full runtime/platform/loader qualification, the private diagnostic, producer
admission and pilot/runtime acceptance remain separate. Existing source receipts
qualify only their exact bytes and execution envelopes. Bounded acquisition and
candidate byte binding are implemented source mechanisms, not complete release
or offline-vendor acceptance. No release/publication/adoption or discoverable v1
root manifest follows from declaration acceptance.
