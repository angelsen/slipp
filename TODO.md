# slipp TODO

## Next session: manual QA pass — try to break it

No automated tests yet (deliberate for now, project isn't in production),
but today's cleanup session found 4 real bugs just from manual hands-on testing:
`generate dockerfile` completely broken (hard assert on data its own
pipeline never populates), `caddy_generator.py` silently omitting
`project_name` from a rendered path, `pyyaml` missing as a direct
dependency (would've broken on a fresh install), and a generated Ansible
task using a `docker_image` module parameter (`force_rm`) that doesn't
actually exist on the installed collection. That hit rate suggests there
are more latent bugs than one session surfaced.

Before Bulletins becomes the first real deployment target, spend a session
just trying to break slipp against a handful of scratch projects under
`/tmp/`:

- Run the full `launch` → `deploy --dry-run` loop against project types the
  scanner doesn't explicitly support (plain static site, a Go binary, a
  Rails app) and see what happens — scanner currently only detects
  Flask/generic-Python/Node/SvelteKit, everything else silently produces
  zero services.
- Multi-host inventories — most of the generator code takes
  `list(inventory.hosts.values())[0]` and only ever uses the first host;
  poke at what a second host actually gets (nothing, probably worth
  confirming that's expected rather than silently wrong).
- Flag combinations nobody's tried: `--reconfigure` after switching
  `container_runtime` docker↔podman, `--force-requirements`, `--roles`
  combined with an auto-generated `requirements.yml`, running `deploy`
  twice in a row, running commands from a subdirectory instead of project
  root.
- Error paths specifically — pull the network cable / rename a binary off
  PATH / feed malformed YAML into `inventory.yml` and see whether the
  failure is a clean `SlippError` message or a raw traceback slipping
  through.
- Whatever `slipp generate scaffold` does end to end against a real
  existing (non-slipp) Ansible project — least-tested path today.

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

