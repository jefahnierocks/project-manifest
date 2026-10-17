# project-manifest

A project-manifest specification candidate and reference source with an
owner-approved [first private release](https://github.com/jefahnierocks/project-manifest/releases/tag/release-1).
The canonical repository is `jefahnierocks/project-manifest`. The repository
owner is the sole release approver.

The byte/closed-shape reader and declaration semantics/tree-reference checker
are pure stdlib APIs with synthetic in-memory tests. Bounded offline Git
acquisition returns one explicit source observation through an API and source
CLI. A separately trusted consumer bootstrap provides
[candidate offline byte binding](docs/offline-binding-candidate.md) before
payload import. Project declaration verdicts require reviewed consumer composition
of syntax/shape, declaration semantics and authenticated selected-tree evidence.
Read the [acquisition candidate](docs/acquisition-candidate.md),
[declaration candidate](docs/validation-candidate.md),
[specification candidate](docs/specification-candidate.md),
[field worksheet](docs/field-table.md), [enum worksheet](docs/enum-provenance.md)
and [STATUS.md](STATUS.md). [AGENTS.md](AGENTS.md) is the working contract.

## Layout

- `docs/`: candidate grammar, complete field inventory and authority decisions.
- `src/project_manifest/`: pure APIs, bounded acquisition and source CLI.
- `bootstrap/`: trusted consumer verifier, acquired separately from payload code.
- `tests/`: inline synthetic byte/semantic/tree positive, negative and boundary
  vectors and guarded temporary Git graphs outside harvested roots.
- `scripts/validate.py`: the sole source gate, including the candidate corpus.
- `mise.toml` and `mise.lock`: exact provisioned tools and generated lock.
- `AGENTS.md`: canonical contract; `CLAUDE.md` imports it.
- `STATUS.md`: status of record; `LICENSE`: MIT license.

## Setup and check

Use Git and mise 2026.10.8 or later from the repository root. The owner must
explicitly authorize host-managed setup after reviewing the local declaration:

```sh
# Owner-only setup
mise trust mise.toml
mise install --locked python@3.13.16 gitleaks@8.30.1
```

Routine validation uses already provisioned tools and disables automatic
installation for this process:

```sh
MISE_EXEC_AUTO_INSTALL=0 mise exec python@3.13.16 gitleaks@8.30.1 -- python -B scripts/validate.py
```

If a tool is missing, report it and leave setup to the owner. Retain and report
inherited host-tool warnings; do not broaden the lock or change host
configuration to silence them.

The exact tools are Python 3.13.16 and Gitleaks 8.30.1. The reader, verifier and
reference corpus use the standard library; no dependency is added. A separate
qualification harness compares installed optional YAML loaders without installing
them. The generated bootstrap lock covers macOS arm64 and Linux x64. The hosted
Linux-x86_64 job prepares exact tools in owned temporary storage, then checks the
source corpus and actual Python floor. Executed evidence for the released source
covers Darwin arm64/current Python 3.13.16 and Linux x86_64/current 3.13.16/floor
3.11.17; see [release status and limits](STATUS.md#private-release-1). Other hosts,
loaders and project runtime acceptance remain separate.

The gate checks a closed source set, governance, real tool/lock
agreement, all Python syntax, local Markdown links, text hygiene, private-path
exclusion and public-safe source heuristics. Staged entries must be regular
files at stage zero; symlink, gitlink, other modes and unmerged stages fail.
Worktree symlink components fail. Pinned Gitleaks scans intended worktree and
index bytes with full redaction and default rules. Temporary synthetic probes
exercise safety failures; acquisition uses owned disposable Git graphs.

The corpus runs from temporary copies of the exact candidate source bytes.
The index must contain the complete candidate source set. The gate checks
worktree and index bytes and runs the corpus separately for each snapshot.
Incomplete indexes are refused. The gate never stages files and rejects
changes to observed source/index bytes during validation.

## Candidate limits and next work

The pure APIs are `check_candidate(bytes)` for syntax/shape and
`check_declaration(bytes, tree=TreeSnapshot(...), reference_date="YYYY-MM-DD")`
for C2 semantics/references. Use `result.diagnostics()` for value-blind
findings. `result.record` is input-derived data, not diagnostic output.
The source CLI is `PYTHONPATH=src python -B -m project_manifest` with exactly
one of `--rev REV`, `--staged` or `--worktree` and an explicitly selected
`--repo`. Read its [bounds and source selection](docs/acquisition-candidate.md).
There is no installed command, dependency or repository discovery mode.

The declaration API checks real calendar/reference dates, canonical/self/peer
relationships, list uniqueness, candidate runner/task/path policy, and exact
regular/executable references with no symlink/submodule component. Its direct
tree evidence is caller-supplied. The separate acquirer obtains bounded
revision, index or tracked working evidence and returns that same TreeSnapshot
with accepted Python results. The five manifest enum sets are owner-adopted
and checked; the [development contract policy](docs/validation-candidate.md#proposed-development-policy-freeze)
was frozen by the owner on 2026-10-13. [Private Release 1](STATUS.md#private-release-1)
records the separate artifact acceptance. Activation owner uses none/direnv/mise/project
independently from template/launcher presence. The separately trusted bootstrap
checks a closed externally anchored byte binding before payload import. Fresh
installed-loader comparisons remain bounded evidence. Actual consumer binding,
declaration validation, native project conformance, pilots and runtime acceptance
have their own gates. Corpus success alone does not establish those outcomes.

Keep document vectors inline. No root v1 manifest is initialized in this origin.
The producer's lock-only discovery barrier has landed in source and invocation
wiring; released-validator adoption, version dispatch and operational acceptance
remain separate. Synthetic acquisition graphs are an owner-authorized exception
solely in guarded system temporary roots outside harvested roots. The private release does not
authorize producer discovery, enrollment, migration, runtime operation, vendoring
or public visibility.

## Tool maintenance and local output

After an authorized pin or platform change, regenerate and review the real lock:

```sh
mise lock --platform macos-arm64,linux-x64
```

Never hand-edit generated lock metadata. A platform addition requires its own
lock and execution evidence. The lock contains public download metadata.

Repository-owned caches use ignored `.cache/bootstrap/`; generated output uses
`build/` and `dist/`. The source gate uses system temporary directories removed
on exit, with no persistent report or bytecode. Mise owns its normal host
install, cache and trust state; agents do not inspect or clean those stores.
Local overrides must not weaken the canonical gate.

Source and examples are freshly authored and public-safe. Specific private
working material requires owner authorization and ignored `private/`
directories, which are not durable storage. Secrets and regulated records do
not belong here.
