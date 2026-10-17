# Status

Governed intake baseline 0.1 with an MIT license. The specification candidate and
reference source have an owner-approved first private release. The repository
owner remains the sole release approver.

## Private release 1

[Project manifest release1](https://github.com/jefahnierocks/project-manifest/releases/tag/release-1)
was published in the private repository on 2026-10-17 UTC. The signed annotated
tag releases source revision 56e3920089726e585eaa0fd7f4dc94e6938a1e0c.
Its closed payload contains 20 files / 342,946 bytes, plus release.json.
The externally accepted release-table domain digest is
f7ff9dd0972af5d3a6a3348c3e092de1a6acd97fa3975e13e522cf80ce5e7df2;
the separately trusted bootstrap SHA-256 is
2ccf58e0da97bbbd9dae173d1cca047d465c4a2d950ee6e56052309a9689cf4f.

The release includes its archive, separate bootstrap, provenance and checksums.
All four downloaded assets matched the retained exact bytes, sizes and hashes;
the downloaded closed bundle passed trusted-bootstrap verification. The scoped
pre-freeze diagnostic was accepted for this release; its wider field coverage
remains partial and whole-file Specification 1 validity was not established for
the observed producer inputs.
Consumer binding and adoption follow their separate gates, using the existing
[released descriptor profile](docs/offline-binding-candidate.md#released-source-descriptor-profile)
and [bootstrap trust and immutable-use requirements](docs/offline-binding-candidate.md#trusted-consumer-bootstrap).
Verification alone grants no project execution, admission or runtime authority.

## Source scope and remaining acceptance

Source provides a pure byte/closed-shape reader, declaration semantics and exact
tree-reference checks, bounded offline Git acquisition with a source CLI, and a
separately trusted consumer bootstrap for byte binding. Consumers compose these
checks with authenticated source/tree evidence for actual declaration verdicts;
validation executes no project code.

The source gate validates its closed source set and requires the complete
candidate index. It checks worktree and index bytes and runs the corpus
separately for both snapshots. Counts and earlier runs are not substitutes
for qualification of current bytes. Staging source does not invalidate this
status description.

The five generic manifest domains, uniform canonical relation and full
development shape are settled. The owner froze the reviewed development
semantics and literal spellings as [contract policy](docs/validation-candidate.md#proposed-development-policy-freeze)
on 2026-10-13. Private Release 1 records separate artifact acceptance; actual
consumer acceptance remains separate. Empty platforms declares no platform
claim; platform tokens are not host observation or portability proof.
[Declaration corpus coverage](docs/validation-candidate.md#declaration-corpus-coverage)
records inspected byte/semantic/tree fixtures and their acceptance boundaries.

Recorded source gates for the released revision cover Darwin arm64/current
Python 3.13.16 and hosted Linux x86_64/current 3.13.16/floor 3.11.17. The native
worktree/index snapshots and the [first main Linux run](https://github.com/jefahnierocks/project-manifest/actions/runs/38657300186)
worktree/index/floor snapshots each passed 194 tests, including guarded synthetic
acquisition. These are selected host/source-corpus observations, not universal
platform, loader or project-runtime qualification. Unsupported storage or
changed/unavailable evidence still returns not checked.

Byte binding requires an external trusted digest before payload import and
immutable use of verified bytes. Generic verifier results do not approve a
release or establish a consumer lock. Actual native task/role/secretless-check/
activation/Compose safety belongs to project/consumer acceptance; validation
executes no project code.

Private Release 1 supplies the released specification and reference validator.
Release/download byte verification alone establishes no project declaration
verdict; actual consumer binding, declaration validation, conformance and
admission remain separate. The producer's lock-only discovery barrier has landed
in source and invocation wiring; released-validator adoption, version dispatch
and operational acceptance remain separate. Consumer migration, pilots and runtime
acceptance have their own gates. No installed/vendor command or root manifest is
initialized in this origin. Document vectors remain inline; synthetic Git fixtures
use guarded owned temporary roots outside harvested roots. Public visibility
remains a later owner-reviewed decision.
