# slipp TODO

## Next: `--proxy wg-manage` service exposure (scoped, not implemented)

Where the target host already runs wg-deploy's `wg-manage` (source of truth
for Caddy via `/etc/wg-services.json`), slipp's `caddy` role should stop
generating its own Caddyfile and instead shell out over the existing SSH
connection to `wg-manage service add`. This is Bulletins' (`bulletins-chat`
public, `bulletins-admin` WG-only) actual exposure path — see
[`wg-deploy`](~/Projects/private/wg-deploy)'s own TODO for the matching
asks.

**wg-manage's side is fully done and the contract is exactly as hoped.**
`service add <name> <target> [--https|--public] [--upstream-tls]
[--streaming] [--caddy-file F]` (`wg-deploy/templates/wg-manage.py.j2:930-963`)
is genuinely idempotent — safe to call unconditionally every deploy, no
pre-check needed (like `ansible.builtin.package` or any other
converge-to-desired-state module). wg-deploy's own TODO confirms no
blockers remain on its side.

**The gap this surfaces that isn't just "swap the Caddy role": slipp has no
per-service exposure control today.** `CaddyGenerator.build_caddy_sites()`
(`generator/caddy_generator.py:114-179`) builds a site for *every* detected
service unconditionally — the only override is the project-wide `--proxy
none` flag. Not fixing that here — separate `slipp launch` invocations per
exposure tier (`--dir admin --proxy none` for bulletins-admin, a second run
for bulletins-chat) already covers Bulletins' actual need.

**Design:**
1. New `--proxy wg-manage` mode alongside today's `caddy`/`none`
   (`commands/launch.py`, `constants.VALID_PROXIES`). Skips
   `CaddyRoleStage`/`CaddyGenerator` entirely (no Caddyfile templated) but,
   unlike `none`, still needs *something* generated.
2. New lightweight role `roles/wg-manage-exposure/tasks/main.yml.j2` (no
   handlers/templates — `wg-manage` handles its own Caddy regen/reload
   internally) with one `ansible.builtin.command` task per exposed service:
   `wg-manage service add {{ domain }} {{ ansible_host }}:{{ port }} --public`
   (or `--https` — see open decision below), using
   `changed_when: "'unchanged' not in result.stdout"` to match wg-manage's
   own stdout convention.
3. Domain-per-service naming reuses `build_caddy_sites()`'s existing
   convention: bare `app_domain` for a single service,
   `{{ service.name }}.{{ app_domain }}` per service otherwise. wg-manage
   is one-FQDN-to-one-target (no path-prefix multiplexing), so Caddy's
   `domain/api` vs `domain/` split doesn't carry over.
4. **Open decision, needs a call before implementing:** `--public`
   (Let's Encrypt, internet-facing) vs `--https` (internal CA) isn't a
   distinction slipp's config models today (`CaddyConfig.auto_https` is one
   blanket bool). Needs an explicit flag at `slipp launch` time — leaning
   toward defaulting to `--https` (safer) and requiring explicit `--public`
   opt-in, since internet-facing-by-default is the wrong failure mode for a
   mistake.
5. No existence check for `wg-manage` on the target host — same
   "explicit config, trust it" principle as the `runtime:` work; if it's
   not there, the task fails with a clear "command not found."

**No wg-manage changes needed** — its CLI surface already covers this, and
wg-deploy's own TODO confirms it. Two adjacent gaps this surfaces, neither
a wg-manage gap:
- **DNS is a separate, unbuilt prerequisite.** `--public` needs the domain
  to already resolve to the host's public IP before `wg-manage service add
  --public` runs. Neither slipp nor wg-manage manages DNS records — the
  domain's DNS has to be created by hand until a Cloudflare/DNS provider
  integration exists (see below).
- **This design only ever calls `service add`, never `service rm`.** A
  renamed/removed service would leave a stale `wg-manage` entry (and its
  Caddy route/cert) forever. `wg-manage service rm` already exists; this
  design just doesn't call it. Not fixing in v1 (matches slipp's existing
  non-cleanup-on-rename behavior elsewhere), but a stale *exposure* entry
  has more real consequence than a stale local file.

**Verification when implemented:** needs a live `wg-manage` binary, not
scratch-project-testable. Deploy bulletins-admin with `--proxy none` first
(already possible today), then bulletins-chat with `--proxy wg-manage
--public` once this lands.

---

## Open backlog

- [ ] `slipp bootstrap auth` — SSH CA + TOTP setup, requires `nor-auth`
  (external service, not yet built). Flow: `slipp ssh` → `POST
  /ssh/request` (pubkey) → phone approval → poll `GET /ssh/status/:id` for
  a short-lived cert → optional `POST /verify/totp`. No SDK needed, just
  HTTPS + JSON.

  | Feature | slipp only | needs nor-auth |
  |---------|------------|-----------------|
  | Hardware key (FIDO2) | ✓ | |
  | Key + passphrase | ✓ | |
  | Short-lived certs | | ✓ |
  | Phone approval | | ✓ |
  | TOTP 2FA | | ✓ |

  slipp side today: `ssh-keygen -t ed25519-sk` + `slipp bootstrap account`.

- [ ] `slipp server install --continue` — list/pick from in-progress
      installs across all servers (for multi-project, multi-VPS workflows)
- [ ] Cloudflare provider (DNS-only, official Python SDK): `GET /zones`,
      `POST /zones/{id}/dns_records`, `DELETE /zones/{id}/dns_records/{id}`
- [ ] `services/image/transfer.py` and `services/run/caddy.py:is_installed`
      still run sudo over SSH without calling `SSHService.ensure_sudo()` —
      they pick up a cached password for free if one was already prompted
      elsewhere in the process, but fail with no prompt on a password host
      with no prior prompt.
- [ ] Port `scans/portal` (`~/Projects/work/ultraportalen/scans/`,
      SvelteKit/systemd) to slipp — best remaining porting candidate, VPS
      already uses wg-manage for Caddy, ties directly into the
      `--proxy wg-manage` work above. `scans/admin` (Bente's Mac,
      LaunchAgent) is out of scope — not a VPS target.

---

## Open design questions

### Many-to-many: projects × servers

Today slipp is 1:1 (one `slipp.yaml` → one inventory → one server). Real
deployments are N:M — multiple services share a server, one project
deploys to staging + prod, etc.

**Missing piece:** a deployment registry — "server X runs services A, B,
C." `wg-manage`'s service list already is this for the network layer;
slipp needs its own equivalent or should read from `wg-manage`.

Open questions:
- Per-environment inventories (`slipp deploy staging` / `slipp deploy
  prod`) partially works via `--env` but the UX is rough
- Shared-server deploys don't know about each other (port conflicts,
  shared Caddy)
- No global view of what's deployed where (`slipp servers list` shows
  servers but not their services)

### Deploy hardening

- **Database migrations** — `scans` runs `drizzle db:push` during deploy;
  slipp's playbook template has no migration hook.
- **Git-push-to-deploy** — `lanpad`/`partbridge`/`scans` all used
  `git push deploy main` before their slipp ports. Three options if this
  needs to come back for a future project: (1) replace entirely, run
  `slipp deploy` from the dev machine (what lanpad/klara did); (2) hybrid —
  keep the push trigger, but the post-receive hook runs `slipp deploy`
  instead of a bespoke shell script; (3) `slipp deploy --mode push`
  generates the bare repo + post-receive hook itself.
- **Shared server** — lanpad and partbridge (klara) both deploy to
  `mym-dev`, confirmed genuinely multi-tenant (also runs `dtc-mcp`, owned
  by a colleague, manually deployed under its own Unix user). slipp must
  stay additive-only there, never enumerate/touch what it doesn't own.
- **Blue-green deploys** — today's health-check/rollback restart (see
  Shipped) is in-place: a few seconds of real downtime around each
  restart, no spare port/unit to health-check before cutover. True
  zero-downtime needs a blue-green swap: deploy to a spare port/unit,
  health-check while the old one still serves traffic, then repoint
  whatever's in front. Cheap for a slipp-managed Caddy role (admin-API
  port rewrite); for an externally-proxied domain (e.g. klara's Pangolin
  setup) it means calling that proxy's own API to swap the Target's port,
  plus apps with local on-disk state (e.g. partbridge's SQLite files)
  would briefly have two live processes touching the same files. Bigger
  scope than the current fix — not pursuing until the in-place restart
  window actually causes a problem.

---

## Shipped

- **2026-07-05** — v0.2.0 release, ~900-line cleanup after a health
  assessment pass.
- **2026-07-06/07** — Config refactor (merged `runs.yaml` into
  `slipp.yaml`), run/deploy progress output, JSON output (`-o json`) for
  plural commands, tunnel auth (`--tunnel-auth`), subdirectory config
  discovery (walk up to find `slipp.yaml` like git/npm/cargo), `slipp
  generate scaffold` + external roles fix, manual QA pass (3 real bugs
  found and fixed).
- **2026-07-07** — Native (non-container) systemd app role for `slipp
  launch` (first real consumer: Bulletins), monorepo rsync sync-exclude
  fix, `package.json` workspace auto-detection.
- **2026-07-08** — Gigahost provider integration (servers, DNS,
  provisioning, full API client) — verified against live Gigahost API.
  Full SSH test session against a real VPS (Debian 13); found and fixed
  several Debian-13-minimal issues (missing python3/rsync, docker package
  name, provision resumability, IP-only Caddy config).
- **2026-07-09** — Python/uv systemd role, `lanpad` ported off
  git-push-to-deploy onto `slipp deploy`, live-verified against `mym-dev`.
  Sudo password support for `ps`/`logs`/`exec`/`status` (`--ask-become-pass`
  flag, then replaced by auto-detect/prompt/cache with no flag needed).
- **2026-07-10** — SSH command logging to `.slipp/logs/` (every SSH
  interaction across the CLI, opens lazily on first use). Pangolin public
  resource management: `PangolinClient`, `slipp resources sync/list/remove`
  (converges a project's public `{name}.mymechanic.no` Resource+Target to
  match its inventory), `slipp providers add pangolin`. Health-check +
  rollback for systemd deploys (`slipp launch --health-check /path`: Ansible
  block/rescue, restart verification, HTTP health poll, snapshot-based
  rollback of app dir + systemd unit, re-verified rollback health).
  `klara` (partbridge) ported off its own git-push/rollback hook onto
  `slipp deploy`, live cutover verified against `mym-dev`. Container-runtime
  port override extended from systemd-only to docker/podman (scoped to the
  primary service only, to avoid clobbering a secondary service's own
  port); fixed the `# Generated by slipp` marker being missing from every
  role template (app-container/app-systemd/app-systemd-python/caddy), which
  had silently disabled customization-protection on every generated role
  file since those roles existed.
