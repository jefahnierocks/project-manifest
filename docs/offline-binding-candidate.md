# Candidate offline byte binding

This unreleased C4 source candidate binds a closed set of bytes. It does not
create, export, install, vendor, sign or approve a release. Complete Specification
1 validity, native conformance, producer admission and runtime acceptance remain
separate. No release artifact or approved consumer lock exists here.

## Trusted consumer bootstrap

A consumer separately reviews and pins `bootstrap/release_verifier.py`, together
with its trusted interpreter and standard library. That bootstrap is outside
the unverified payload and is never imported from it. The consumer also obtains
the expected digest through an independently trusted lock or owner-approved
record. A digest supplied by the payload does not establish trust. The table
contains neither its own digest nor the verifier's digest.

The trusted bootstrap exposes `verify_release(root, expected_digest=...)`.
`root` must be an explicit absolute directory with no symlink component. Before
importing any payload module, the consumer requires exit 0 against its external
digest. The standalone inspection interface may run with Python's isolated
mode, from the trusted bootstrap location:

```sh
python -I -B release_verifier.py --root /absolute/closed-bundle --expected-digest EXPECTED_SHA256
```

This is byte inspection, not an install or release command. Exit 0 means the
candidate bytes match; exit 1 means malformed, changed or mismatched evidence;
exit 2 means the external trust input, root or runtime is unavailable. Findings
are fixed codes and omit payload values and paths. The result retains the
verified public descriptor only on success. Python 3.11 and POSIX directory
descriptors with no-follow opens are prerequisites; that check is not a platform
qualification receipt.

Verification does not lock the filesystem after return. The trusted consumer
must hold the verified snapshot immutable through import and use, or reacquire
and verify it immediately before use. Importing from a concurrently writable
directory after verification is not covered. The verifier neither executes
payload code nor enforces a consumer's isolation boundary.

## Closed table and byte identity

The root contains exactly `release.json` and the twenty sorted paths in the
trusted bootstrap's `PAYLOAD_FILES`, plus only their derived directories. The
set includes the MIT license, all six normative/usage candidate documents, the
six runtime modules, five declaration/acquisition test and fixture modules,
and the corpus and loader-comparison harnesses. The trusted bootstrap and its
own tamper tests are reviewed separately; neither is acquired as payload code.
Origin-only governance, setup pins/lock, source gate and working reports are
not payload. Extra files/directories, missing paths, alternate lexical spelling,
symlinks, hardlinks and special files fail. No root project manifest is part of
this set.

The descriptor has exactly these fields:

| Field | Candidate rule |
| --- | --- |
| format | `candidate-binding-1` |
| origin | `jefahnierocks/project-manifest` |
| spec_version | String `1`; grammar selection alone grants no verdict |
| release_id | `candidate-1`; explicitly unreleased |
| source_revision | Full lowercase 40- or 64-digit source object identity |
| python_minimum | `3.11`; subject to release qualification |
| git_minimum | `2.56.0`; bounded acquisition requirement |
| files | Complete sorted list of exact `path`, integer `bytes`, lowercase SHA-256 |

Canonical encoding is ASCII JSON with sorted keys, separators comma/colon,
`ensure_ascii=True`, no non-finite numbers, and one final LF. Duplicate keys
and any noncanonical encoding fail. Each row binds a path, exact byte length
and content digest. Paths are fixed by the trusted bootstrap, not interpolated
from arbitrary table input. Boolean sizes, duplicate/unsorted/missing/extra rows
and undeclared metadata fail.

The externally expected digest is SHA-256 of the literal ASCII domain
`project-manifest-release-table-v1`, one NUL byte, then the canonical table
bytes. The table thereby binds origin, candidate identity, specification/runtime
claims, source revision and every selected content hash together. Content
hashes establish byte identity, not truthful provenance or approval. POSIX
permissions are observed for safe regular-file reads, not a released executable
mode contract.

Inspection bounds are 65,536 table bytes, 1,048,576 bytes per payload file and
16,777,216 declared payload bytes total. No-follow descriptor-relative reads
check file identity and size before/after; namespace and root identity are
rechecked. Changes cause failure. There is no network, Git child, target command,
environment activation or payload import in verification.

## Corpus and fresh loader evidence

The stdlib harness `python -B tests/run_corpus.py --scope pure` exercises byte and
semantic controls without synthetic Git graphs. CLI tests belong to the full
acquisition lane because some create synthetic Git graphs. `--scope all` also runs
guarded acquisition and, in the trusted origin source, bootstrap tamper tests.
Those fixtures retain the existing approved macOS temporary-root contract.
Other full-acquisition hosts return exit 2 before fixtures are created; Linux
qualification remains open. Pure test portability is not full acquisition
portability. These are source test interfaces, not an installed command.

`python -B tests/compare_loaders.py` compares fresh inline synthetic vectors
with already-installed PyYAML SafeLoader/CSafeLoader and Ruby Psych safe loading.
It installs nothing and adds no validator dependency. Every accepted vector
must yield the exact stdlib-reader record; known broader YAML acceptance is
recorded while the strict reader still refuses those bytes. Missing engines
are reported, and other loaders remain not checked. Fresh receipts bind the
exact source snapshot and installed engine versions outside publication source.
Neither an earlier prototype comparison nor this bounded engine sample is
complete release qualification.

The closed normative/runtime/corpus inventory, bootstrap trust mechanism,
approved vocabulary, full platform/runtime corpus, private grammar diagnostic,
and consumer lock/admission must all receive their separate owner review before
a complete immutable release can be approved. C4 adds no exporter, installer,
vendoring command, CI change or runtime operation.
