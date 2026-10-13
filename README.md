# project-manifest

A fresh source home for a project-manifest specification and its reference
validation material. The canonical repository is
`jefahnierocks/project-manifest`. The repository owner is the sole release
approver.

This checkout currently contains an intake baseline and its bootstrap check.
It has no specification, parser, reference corpus or release. See
[STATUS.md](STATUS.md) for current state and [AGENTS.md](AGENTS.md) for the
working contract.

## Layout

- `mise.toml` and `mise.lock`: exact bootstrap tools and generated tool lock.
- `scripts/validate.py`: the local bootstrap validation entrypoint.
- `AGENTS.md`: canonical agent contract; `CLAUDE.md` imports it.
- `STATUS.md`: status of record.
- `LICENSE`: MIT license.

## Setup and check

Use Git and mise 2026.10.8 or later. Run from the repository root. The owner
must explicitly authorize these host-managed setup actions after reviewing the
local declaration:

```sh
# Owner-only setup
mise trust mise.toml
mise install --locked python@3.13.16 gitleaks@8.30.1
```

Routine validation uses the already provisioned tools and disables automatic
installation for this process:

```sh
MISE_EXEC_AUTO_INSTALL=0 mise exec python@3.13.16 gitleaks@8.30.1 -- python -B scripts/validate.py
```

If a tool is missing, report it and leave setup to the owner. Retain and report
inherited host-tool warnings; do not broaden this project's lock or alter host
configuration to silence them.

The project pins Python 3.13.16 and Gitleaks 8.30.1. Python uses only its standard
library; there are no application package dependencies. The bootstrap lock
covers macOS arm64 only. Other platforms and CI portability have not been
qualified. These bootstrap pins do not define a future validator minimum.

The check verifies the closed bootstrap source layout, governance declarations,
tool and lock agreement, local Markdown links, text hygiene, private-path
exclusion and public-safe source heuristics. Pinned Gitleaks scans only the
intended worktree and index source, with full value redaction. Synthetic
negative probes check the safety rules without creating Git fixture repositories.

This proves intake source only. A reference corpus gate is required before
release 1. No manifest files, discovery, harvesting, projection, producer
operations or publication are part of the bootstrap.

## Tool maintenance and local output

Review pin changes and regenerate the real project lock with:

```sh
mise lock --platform macos-arm64
```

Run the bootstrap check after reviewing the lock diff. Never hand-edit generated
lock metadata. A future platform addition needs its own lock and execution
evidence. The lock contains public download metadata, not application
dependencies.

Repository-owned caches and generated output belong in ignored
`.cache/bootstrap/`, `build/` or `dist/`. The check uses system temporary
directories that it removes on exit and writes no persistent report or bytecode.
mise owns its normal host install, cache and trust state; agents do not inspect
or clean those stores. Local overrides are ignored and must not weaken the
canonical check.

Private material is not part of this baseline. If the owner later authorizes
specific private working material, use ignored `private/` directories; they
are not durable storage. Secrets and regulated records do not belong here.
