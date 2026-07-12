# slipp TODO

## Next: live-verify `--proxy auto` / wg-manage composition against Bulletins

The full wg-manage/slipp composition is implemented on both sides (see
Shipped) but never run against a real host — only unit-tested via direct
rendering, `ansible-playbook --syntax-check`, and mocked-SSH
reproductions. The primary acceptance flow per
[`wg-deploy`](~/Projects/private/wg-deploy)'s `slipp-composition` spec is
one command end-to-end:

```
slipp up <name> --hub --domain <domain>
```

— provisions a fresh VPS, hub-ifies it via `scripts/new-host.sh`
(`slipp providers add wg-deploy` first), then `--proxy auto` probes and
finds the hub, deploys through wg-manage-owned Caddy. For Bulletins
specifically: deploy bulletins-admin with `--proxy none` first (already
possible today), then bulletins-chat with `--proxy auto --public` (or
explicit `--proxy wg-manage --public`) against the real VPS.

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
      already uses wg-manage for Caddy, first real consumer of `--proxy
      wg-manage` after Bulletins. `scans/admin` (Bente's Mac, LaunchAgent)
      is out of scope — not a VPS target.
- [ ] `--proxy wg-manage --public` needs its domain to already resolve to
      the host's public IP before `wg-manage service add --public` runs.
      Neither slipp nor wg-manage manages DNS records today — has to be
      created by hand until the Cloudflare provider (above) lands.

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
  file since those roles existed. `--proxy wg-manage` service exposure:
  new `slipp launch` proxy mode that generates a `wg-manage-exposure` role
  (`wg-manage service add` per exposed service, idempotent) instead of a
  Caddyfile, for hosts where wg-manage already owns Caddy. Defaults to
  `--https` (internal CA); `--public` (Let's Encrypt) is an explicit
  opt-in, validated against proxy choice.
- **2026-07-11** — Full `slipp-composition` spec landed (spans this repo
  and `wg-deploy`): `--proxy` now defaults to `auto` and resolves via a
  new `ProxyResolutionStage` that SSH-probes `wg-manage --version`,
  caching a genuinely-connected result as `proxy_owner` in
  `inventory.yml` (explicit overrides and failed probes never poison the
  cache; an inconclusive probe fails the launch rather than guessing).
  `wg-manage-exposure` role gains `--route` path multiplexing (a detected
  backend folds into the frontend's bare-domain entry as `/api/*` instead
  of its own subdomain) and a `--label slipp:<project>` tag on every
  exposed service, plus a deploy-time hub version-guard task. New
  `services/wg_manage/` module holds the SSH orchestration/converge logic
  shared by `commands/resources.py` and `commands/deploy.py`'s
  post-deploy hook. `slipp resources sync/list/remove` grows a wg-manage
  backend alongside Pangolin: label-scoped stray removal closes the
  gap where slipp never called `wg-manage service rm` on its own
  (previously an open backlog item). `slipp up --hub`
  shells out to a configured `wg-deploy` checkout's `scripts/new-host.sh`
  to hub-ify a freshly provisioned host before launch (`slipp providers
  add wg-deploy`). `slipp.yaml` now records the `--dir` values a launch
  actually scanned (`LocalConfig.project_dirs`) so exposure sync
  reproduces the same declared set instead of a possibly-divergent
  auto-detection -- verified this would otherwise break Bulletins' own
  per-tier `--dir admin`/`--dir chat` launches. Hardening:
  `shlex.quote()` on service names interpolated into remote wg-manage
  commands, `WgManageError` so the post-deploy hook's "never raises"
  contract actually holds. Five rounds of external review, each verified
  against the code (reproductions, not trust) before fixing. Not yet
  live-verified (see Next).
