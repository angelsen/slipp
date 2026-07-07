# slipp TODO

## Manual QA pass — done (2026-07-07)

Ran the planned break-it session against scratch projects under `/tmp/`.
Found and fixed 3 real bugs (commit `fae298b`):

- **`slipp generate scaffold` never registered the project.** No `--name`
  flag existed, so `project_name` was always empty; pydantic validation
  failed, was swallowed as a warning, and the command still printed
  "Scaffold complete!" while never writing `slipp.yaml`. Fixed: `--name`
  (defaults to the playbook's parent dir name), registration failures now
  hard-fail instead of being silently swallowed, and re-running scaffold
  no longer overwrites an existing `vault.yml`.
- **`slipp deploy` reported false success on a malformed/empty inventory.**
  `ansible-playbook`/`ansible-inventory` exit 0 when inventory fails to
  parse (warn + no-op), and slipp only checked the exit code. Fixed: a
  preflight rejects empty-parsed inventories, plus a post-run backstop
  catches "playbook matched no hosts" even when ansible exits 0 clean.
- **Multi-host inventories silently used only the first host** in
  `host`/`exec`/`ssh`/`logs`/`status`/`ps --project`/`images` — confirmed
  this was in fact silently wrong, not expected behavior. Fixed: these
  commands now warn on stderr which host they picked and which were
  ignored (stdout stays clean for piping).

Also fixed a prerequisite model bug (`from_ansible_inventory_json` dropped
hosts with no host-specific vars) and, caught during verification, a
self-introduced nondeterminism bug (used a `set` for host ordering, whose
iteration order depends on Python's per-process hash seed — switched to
`dict.fromkeys()`).

**Confirmed correct, no bugs:** unsupported project types (clean
`LaunchError`, not silent zero-services as originally suspected),
`--reconfigure` docker↔podman, `--force-requirements`, `--roles` +
auto-generated `requirements.yml`, running `deploy` twice, missing-binary
error path.

**Left for later, not bugs but worth knowing:** none remaining from this pass
— subdirectory config discovery (below) was the last item.

## Subdirectory config discovery — done (2026-07-07)

Running slipp commands from a subdirectory of a project now walks up to find
`slipp.yaml`, like git/npm/cargo. Previously scoped out due to a footgun:
`LocalConfigService.get_config_path()` is the single choke point that
`exists`/`load`/**`save`** all funnel through, so a blind walk would have
silently redirected writes (e.g. `projects add`'s `create()`) into an
enclosing project's `slipp.yaml`.

**Design:** discovery-at-entry, explicit-root-downstream (the git model).
Added `LocalConfigService.find_root()`/`resolve_root()`
(`services/config/local.py`) — walk from cwd upward checking `slipp.yaml`
file presence only (never parsed, so a corrupt config in cwd binds to cwd,
not a grandparent). All existing `LocalConfigService` primitives keep strict
exact-dir semantics; the walk is opt-in at command/service entry. Governing
rule: **creation never walks** (`projects add`, scaffold/launch stages,
`ensure_local_config`'s create-vs-update gate stay bound to cwd/explicit
dir) — **updates to a discovered config are the feature** (`tags add`,
`run --cmd`, deploy flag persistence writing into the walked root is exactly
"operate on the enclosing project"; nearest-file-wins keeps it safe).

Adopters: `ConfigResolver`, `RuntimeDetector`, `RunProfileService`,
`HostResolver.current()`, `PresetResolver`, `resolve_project_name()`,
`commands/config.py`, `commands/common.py` (`get_project_root`/
`resolve_runtime`), `commands/tags.py` (resolve root once, pass to both
load+save), and deploy (`commands/deploy.py` +
`services/deploy/config.py`).

**Bug found and fixed during verification (not in the original scope):**
CLI-flag relative paths (`-i`, `--playbook`, `--roles`, `--vault`) were left
relative to the process's cwd, but `run_playbook()`
(`services/ansible/ansible.py`) runs the ansible subprocess with
`cwd=playbook.parent` — i.e. `project_root`. Before this feature,
`project_root` was always cwd, so the two never diverged and this was
invisible. Once project_root can be a discovered *ancestor* of cwd, a
relative CLI path resolves against the wrong directory (confirmed by hand:
`slipp deploy -i ../../inventory2/hosts` from a subdirectory tried to parse
`/tmp/inventory2/hosts` instead of the intended path). Fixed by anchoring
CLI-flag paths to the actual process cwd via `Path(value).resolve()`
(`services/config/resolver.py`, `_resolve_cli_path`) before they're used
downstream.

Also added: deploy's `persist_config_updates` now converts flag paths to
project-root-relative before writing them into `slipp.yaml` (so persisted
paths mean the same thing on the next run regardless of which directory
`deploy` was invoked from), with a warning + skip for paths that fall
outside the project root and can't be expressed that way.

Verified end-to-end in a termtap pane (nested `parent/sub/deeper` tree):
regression baseline from the project root unchanged; reads (`config`,
`host`, `deploy --dry-run`) and writes (`tags add`, `run --cmd`, deploy flag
persistence) from a subdirectory correctly resolve/target the parent's
`slipp.yaml`; `.slipp/logs/` lands under the project root, never the
subdirectory; `projects add`/`deploy --name` in a subdirectory of a managed
parent create their own nested config without touching the parent's
(byte-identical before/after); `deploy --name` with no local config in the
subdirectory registers the *discovered* root in the global registry, not the
subdirectory it was run from; a corrupt `slipp.yaml` in an intermediate
directory binds there (with a new visible warning) rather than silently
falling through to the parent; no-config-anywhere behaves exactly as
before.

## `slipp generate scaffold` + external roles — fixed (2026-07-07)

Was fully broken: tested the previously-untested `requirements.yml` +
`--roles-path` branch of `ScaffoldValidationStage` with a scratch project
(fake git-hosted role, `requirements.yml` referencing it, playbook using it).
Role install succeeded but the next step — playbook syntax validation —
always failed with "Playbook syntax check failed", blocking scaffold
entirely.

**Root cause:** `syntax_check()` (`services/ansible/ansible.py:95-109`) ran
`ansible-playbook --syntax-check` as a bare subprocess and never set
`ANSIBLE_ROLES_PATH` (unlike `run_playbook()`, which does), and had no
parameter to accept a roles path at all.

**Fixed:** `syntax_check()` and `get_host_group()` (`services/ansible/ansible.py`)
both now take a `roles_path: list[str] | None` param and set
`ANSIBLE_ROLES_PATH` in their subprocess env when given, mirroring
`run_playbook()`. `ScaffoldValidationStage` (`services/launch/stages/scaffold.py`)
passes `context.roles_path` through to both.

Caught two adjacent bugs in the same flow while fixing:

- **`get_host_group()` silently fell back to `"servers"`** whenever role
  resolution failed (which, before this fix, was every scaffold with
  external roles) — it never checked the subprocess exit code. A scaffold
  could silently write the wrong `[servers]` host group into `inventory/hosts`
  instead of the playbook's real group. Confirmed fixed: a test playbook
  targeting `webservers` now correctly detects and writes `[webservers]`.
- **`ScaffoldRegistrationStage` never persisted `galaxy_path`** into
  `slipp.yaml`, so a scaffolded external-roles project only deployed
  correctly by coincidence (matching `DEFAULT_GALAXY_PATH`). Now passes
  `galaxy_path` through to `LocalConfigService.create()` (not as
  `roles_path=`, to avoid polluting `managed_roles` with externally-installed
  Galaxy roles).

Verified end-to-end in a termtap pane: rebuilt the scratch project (fake
git-hosted role installed via local `git init` repo, `requirements.yml`,
`setup.yml` targeting `webservers`), ran
`slipp generate scaffold -p setup.yml --roles-path roles/galaxy` — syntax
check passed, host group detected as `webservers`, `slipp.yaml` got
`galaxy_path: roles/galaxy`. Followed with `slipp deploy --dry-run`: got past
inventory/vault parsing and role resolution (no "role not found" error),
reached the actual play and failed only on SSH connect timeout to the
RFC5737 test IP used — confirms the whole scaffold→deploy round-trip
resolves roles correctly.

## SSH Security

| Feature | slipp only | needs nor-auth |
|---------|------------|-----------------|
| Hardware key (FIDO2) | ✓ | |
| Key + passphrase | ✓ | |
| Short-lived certs | | ✓ |
| Phone approval | | ✓ |
| TOTP 2FA | | ✓ |

**slipp:** `ssh-keygen -t ed25519-sk` + `slipp bootstrap account`

**nor-auth:** Simple HTTP API for cert issuance, no SDK needed

---

## Bulletins/Prelo integration (first real consumer)

Bulletins (`~/Projects/work/bulletins/bulletins-chat`, SvelteKit) is about to
become slipp's first real deployment target — two apps (`bulletins-chat`
public, `bulletins-admin` WG-only) on VPS infra already managed by
[`wg-deploy`](~/Projects/private/wg-deploy) (WireGuard mesh, internal DNS,
Caddy). See that repo's own TODO for the matching asks — the two projects
are meant to interoperate: slipp deploys the app, wg-manage owns the
network/routing it's exposed through.

- **Native (non-container) app role — done (2026-07-07).** `slipp launch`
  now supports a `systemd` runtime alongside `docker`/`podman`. Reused the
  existing `Runtime` enum (`models/service.py`, previously only used for
  *discovered* services) as the single source of truth for the
  *generation-time* config too, renaming `container_runtime` → `runtime`
  throughout (models, CLI prompts, templates) to converge with `slipp.yaml`'s
  existing `runtime:` key and drop the old two-item lists scattered across
  ~20 call sites (`constants.py`, `RuntimeDetector`, the launch pipeline's
  `ValidationStage`, etc.).

  New template set `generator/templates/roles/app-systemd/` (selected by
  `RoleGenerator._template_dir()`, not conditionals inside the container
  templates — the build step is a genuinely different operation): installs
  Node.js, syncs source, `npm ci && npm run build`, writes a persistent
  `.env.production` placeholder (never overwritten, `EnvironmentFile=-` so a
  missing/empty file doesn't block startup), templates a systemd unit with
  `ExecStart=/usr/bin/node build` — directly matching the shape of
  Bulletins' own hand-written `deploy/bulletins-chat.service` and
  `admin/deploy/bulletins-admin.service`. Dockerfile/compose generation and
  the docker/podman Galaxy collection are skipped project-wide when
  `runtime: systemd`.

  Known gaps, deliberately out of scope for this pass: no per-project
  `After=`/`Requires=` systemd dependency declaration (ships as
  `After=network.target` only — Bulletins' real
  `Requires=postgresql.service livekit.service` needs a manual edit to the
  generated unit); Node.js install is a plain distro package, not
  version-pinned to `.nvmrc`/`engines.node` (that data isn't threaded into
  `RoleGenerator` yet); one runtime per project, not per-service.

  Verified end-to-end in a termtap pane: a scratch SvelteKit-shaped project
  with `runtime: systemd` in `inventory.yml` generates a syntax-valid
  playbook, the correct native role, no Dockerfile/compose/docker-podman
  collection; the same scan with `runtime: docker` still produces
  byte-equivalent container output (regression check). Along the way, found
  and fixed a real pre-existing gap: `slipp launch`'s `RegistrationStage`
  never persisted `runtime:` into the generated `slipp.yaml` at all — for
  docker/podman this was silently masked by `RuntimeDetector`'s fragile
  auto-detect heuristic accidentally matching the substring "docker" inside
  the task name "Copy **Docker**file", but a systemd project has no such
  lucky coincidence and hard-failed "Could not detect runtime" on any
  `slipp images`/`slipp image push` call. Now persisted explicitly at
  registration time.

  Source template dir renamed `roles/app` → `roles/app-container` (2026-07-07)
  for symmetry with `roles/app-systemd` — docker and podman share one
  template set because they're both containers, so naming it by that shared
  property reads better than leaving one runtime as an unmarked "default".
  Purely a source-template rename; generated role output is still always
  `roles/app-{service}/` regardless of runtime.

  **Monorepo sync-exclude bug — found and fixed (2026-07-07).** Discussed
  applying this to Bulletins' actual repo shape (root = `bulletins-chat`
  app, `admin/` = `bulletins-admin` app, both under one `slipp launch --dir .
  --dir admin`) and found the generated sync task had no idea other
  services or slipp's own generated files lived inside a service's own
  directory. Two concrete failure modes, both now fixed via
  `RoleGenerator._compute_sync_excludes()`: a "root is also an app" project
  would rsync sibling services' full source trees into the wrong deploy
  target, **and** — this one hits every single-app project too, not just
  monorepos — would rsync slipp's own generated `playbook.yml`/`roles/`/
  `inventory.yml`/etc. into `/opt/...` as if they were app source, since
  `slipp launch` is normally run from the project's own root. Fix computes,
  per service, which other detected services and which of slipp's own
  generated top-level paths are nested inside *that* service's own
  directory (siblings never overlap, so they're left alone) and adds
  `--exclude=` entries for exactly those. Verified in a termtap pane against
  both a real two-service monorepo layout and a plain single-service
  project.

  **`package.json` workspace auto-detection — done (2026-07-07).**
  `slipp launch` with no `--dir` flags now auto-detects a
  `"workspaces"` array in the cwd's `package.json` and scans root + every
  member, instead of requiring the user to enumerate each app directory by
  hand. Explicit `--dir` still bypasses detection entirely, unchanged.

  Root-as-candidate needed no special-casing: `scan()` (`scanner/scanner.py:56`)
  already returns `None` for a directory matching no known framework, and
  `ProjectScanStage` already silently skips a `None` result — so a
  Turborepo-style pure-coordinator root (no build script) is naturally
  excluded for free, no need to distinguish "root is an app" vs "root is a
  coordinator" as a case. Confirmed by research rather than assumed: `uv`'s
  own workspace docs are explicit that "every workspace needs a root, which
  is also a workspace member" — same convention, independent ecosystem.

  Resolution leverages native package-manager tooling instead of
  hand-rolling glob matching: `npm query .workspace --json` (npm 8+) or
  `yarn workspaces list --json` (Yarn Berry) resolve the `"workspaces"`
  glob patterns (including negation) into concrete member paths —
  `scanner/workspaces.py`'s `detect_workspace_members()`. Extracted the
  existing lockfile-based package-manager sniffing out of
  `NodeJSVariableExtractor._detect_package_manager()` into a shared
  `utils/nodejs.py` helper so both call sites use one implementation.
  **pnpm is out of scope** — it declares workspaces in a separate
  `pnpm-workspace.yaml`, not `package.json`, and slipp doesn't read that
  file (Bulletins uses plain npm, confirmed via its `package-lock.json`).

  **Bug found and fixed during verification, not anticipated in scoping:**
  `npm query .workspace --json` (and presumably `yarn workspaces list`)
  returns an empty array on a project where `npm install` hasn't actually
  run — `--package-lock-only` isn't enough, node_modules must exist.
  Confirmed by hand: same repo, same `"workspaces": ["admin"]` declaration,
  `npm query` returns `[]` before a real `npm install` and the correct
  `admin` entry after. Since the code originally only fell back to the next
  resolver (native → glob) on an outright subprocess/parse failure, a fresh
  clone (the exact state a monorepo is in right after `git clone`, before
  `npm install`) would have silently detected zero workspace members
  instead of falling back. Fixed: fall back to the naive glob resolver on
  an **empty** result too, not just a hard failure — safe because
  `detect_workspace_members()` already confirmed the raw `"workspaces"`
  array itself is non-empty before ever calling a resolver.

  Verified end-to-end in a termtap pane: auto-detection via the native npm
  path (with `node_modules` present), via the glob fallback (fresh clone,
  no `node_modules`), explicit `--dir` still bypassing detection, and a
  plain single-app project with no `"workspaces"` key behaving identically
  to before. Sync-excludes (previous fix, commit `a6b67ff`) apply correctly
  to auto-detected services with no additional wiring needed.

  **Left for later:** pnpm workspace support (`pnpm-workspace.yaml`
  parsing); a symmetric `uv` workspace auto-detector for the Python
  scanners (Flask/FastAPI/Django) — `uv` has no equivalent to
  `npm query`/`yarn workspaces list` (no machine-readable listing command),
  so that side would need to parse `[tool.uv.workspace]`'s `members`/
  `exclude` glob patterns from `pyproject.toml` directly rather than
  shelling out to a native command; name collisions between two workspace
  members sharing a directory basename (pre-existing risk, not introduced
  here); no flag to force-disable auto-detection when no `--dir` is given.
- **Delegate exposure to wg-manage instead of templating Caddy.** Where the
  target host already runs wg-deploy's `wg-manage` (source of truth for
  Caddy via `/etc/wg-services.json`), slipp's `caddy` role should stop
  generating its own Caddyfile and instead shell out over the existing SSH
  connection: `wg-manage service add <name> <target> --https|--public`
  (idempotent create-or-update — see the matching ask in wg-deploy's TODO).
  Keeps exactly one owner of Caddy state instead of two tools racing to
  regenerate the same file. Bulletins-admin needs *no* exposure step at all
  (binds directly to the WG IP, no Caddy route) — the smallest possible
  first test of the native app role, before attempting bulletins-chat
  (public, needs Caddy + DNS).
- **Provider integrations below are bigger than first scoped** — see
  updated Gigahost section.

---

## Backlog

- [x] Output primitives refactor (stdout/stderr separation)
- [x] slipp host - pipeable host info
- [x] slipp image push - push container images via SSH
- [x] slipp images list - list images on VPS
- [x] slipp bootstrap registry - setup registry auth on VPS
- [x] Multiple vaults support (`vaults: [mdad, nor-auth]`) - run config already supported, added to `secrets list`
- [x] Secret encoding options (`--encoding hex|base64|ulid`) for `secrets add` and `secrets sync`
- [x] Role management refactor: `roles` → `roles_path`, added `galaxy_path` for ansible-galaxy
- [x] Config refactor: merge runs.yaml into slipp.yaml
- [x] Run profile inheritance (`extends: dev`)
- [x] slipp run progress output
- [x] slipp deploy progress output
- [x] JSON output (`-o json`) for all plural commands
- [x] Tunnel auth (`--tunnel-auth user:pass`)
- [ ] `slipp bootstrap auth` - SSH CA + TOTP setup (requires nor-auth)
- [ ] Provider integrations (Gigahost, Cloudflare)

---

## Provider Integrations

### Goal

Auto-configure infrastructure during scaffold/deploy. No manual IP or DNS entry.

### Workflow

```bash
slipp servers list                    # List VPS with IPs (from provider)
slipp domains list                    # List domains

slipp scaffold -p setup.yml
? Select server: metria-vps        # Auto-fetches IP
? Select domain: metria.no         # From your domains
✓ Inventory created

slipp dns sync                        # Auto-create A records from inventory
✓ matrix.metria.no → 83.143.80.248

slipp deploy
✓ Deploy completed
```

### Minimal Clients

**Gigahost** (Server + DNS + Registrar) — confirmed against
https://gigahost.no/en/api-dokumentasjon (base `https://api.gigahost.no/api/v0`,
Bearer token via `/authenticate`). Full DNS zone/record CRUD exists (TTL,
priority, DNSSEC, PTR, redirects) — more than enough for `dns sync`. Server
API also goes further than originally scoped: full ordering/provisioning,
not just management of existing servers:
```
GET  /servers                      # List VPS with IPs
GET  /servers/{id}                 # Server details
GET  /servers/{id}/powerstate      # Power status
GET  /servers/{id}/reboot          # Reboot
PUT  /servers/{id}/reverse         # Reverse DNS
GET  /dns/zones                    # List domains
GET  /dns/zones/{id}/records       # List records (needed before create/update)
POST /dns/zones/{id}/records       # Create DNS record
PUT  /dns/zones/{id}/records/{rid} # Update DNS record
DELETE /dns/zones/{id}/records/{rid} # Delete DNS record

# Provisioning — not in original scope, unlocks a real `slipp provision`:
GET  /deploy/servers               # Orderable product catalog (region, price, stock)
POST /deploy/servers               # Order a new VPS
GET  /deploy/status?ids=           # Poll waitlist→deploying→installing→ready, returns IP (+ root pw)
```
Regions are Norway-only (e.g. Oslo) — no multi-region equivalent to Fly's
edge network, don't design for one.

A `slipp provision <name> --region osl` command becomes possible: order via
`/deploy/servers`, poll `/deploy/status` for the IP, hand it to
`wg-manage add` so it joins the mesh immediately, `dns sync` the A record,
then `slipp deploy` the app role. Bulletins' current plan doesn't actually
call for a second VPS yet (`livekit-dev` is planned as a second systemd
unit on the existing box) — but see the Bulletins-side TODO milestone
"Prod/dev split + deployment hardening" in
`~/Projects/work/bulletins/bulletins-chat/TODO` for the motivating
use case, and the open question of whether real machine-level prod/dev
separation is worth it once provisioning is this cheap.

**Cloudflare** (DNS + Registrar):
```
GET  /zones                        # List domains
POST /zones/{id}/dns_records       # Create record
DELETE /zones/{id}/dns_records/{id} # Delete record
```

### Commands

```bash
# Server ops (Gigahost)
slipp servers list
slipp server status <name>
slipp server reboot <name>

# DNS (both providers)
slipp domains list
slipp dns sync                        # Create records from inventory
slipp dns add <domain> A <ip>
slipp dns list <domain>

# Config
slipp config set provider gigahost
slipp config set gigahost.token <token>
slipp config set cloudflare.token <token>
```

### Implementation

```
services/providers/
├── base.py           # Abstract interfaces (DNSProvider, ServerProvider)
├── gigahost.py       # Gigahost client
└── cloudflare.py     # Cloudflare client
```

---

## nor-auth Integration (external)

Endpoints needed for `slipp bootstrap auth`:

```
POST /ssh/request     - trigger phone approval, return request_id
GET  /ssh/status/:id  - poll for cert (approved/pending/denied)
POST /verify/totp     - validate TOTP code
```

Flow:
1. `slipp ssh` calls `/ssh/request` with pubkey
2. User approves on phone
3. CLI polls `/ssh/status`, receives short-lived cert
4. Optional TOTP check before connection

No SDK - just HTTPS + JSON. Any tool can integrate.

