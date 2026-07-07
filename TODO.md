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

**Left for later, not bugs but worth knowing:**

- **Subdirectory config discovery.** Running commands from a subdirectory
  (instead of project root) fails cleanly but doesn't walk up to find
  `slipp.yaml` like git/npm/cargo do. Scoped this out (2026-07-07) — it's a
  coordinated multi-file change, not a one-function fix:
  - Callers that already delegate to `LocalConfigService` with
    `project_root=None` (would auto-benefit from an upward walk added to
    `get_config_path`): `HostResolver.current()` (the cwd-fallback path for
    `slipp host`/`exec`/`ssh`/`logs`/`status` when invoked without `-p`/a
    service — the registry-backed paths already work fine), `slipp tags
    add/remove`, `PresetResolver`, `resolve_project_name()`.
  - Callers that hardcode `Path.cwd()` themselves before ever reaching
    `LocalConfigService` — need separate explicit changes:
    `ConfigResolver.__init__` (backs `slipp deploy` and `slipp config`),
    and `commands/config.py`'s `config_command()` (hardcodes
    `project_root = Path.cwd()` directly, no override at all).
  - **Footgun to resolve first:** `LocalConfigService.exists()`/`load()`
    also gate "is a project already configured here" checks (e.g. `slipp
    projects add`). A blind upward walk could make `projects add` in a
    subdirectory of an already-slipp-managed parent wrongly think a nested
    project is already configured, or write into the wrong project's
    `slipp.yaml`. Needs the walk scoped to read-only resolution paths, not
    create/write-gating checks — not yet traced whether `projects add`
    shares the same `exists()` call.

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

- **Native (non-container) app role.** `roles/app/templates/systemd.service.j2`
  currently only generates `ExecStart=/usr/bin/{{ container_runtime }} run ...`
  — there is no path for a plain built binary/process. Bulletins runs via
  `npm run build` + systemd directly, no Docker/Podman anywhere in its stack.
  Need a role variant where `ExecStart` runs the app directly (e.g. `node
  build/index.js` for a SvelteKit `adapter-node` output, with
  `WorkingDirectory`/`Environment` set from scanned config) — same shape as
  today's role, no container runtime required. This decides whether
  Bulletins gets Dockerized just to fit slipp, or slipp grows to fit
  Bulletins' actual (systemd-native) deploy shape — leaning toward the
  latter, since wg-deploy's own target host is bare Ubuntu with no
  container runtime installed at all.
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

