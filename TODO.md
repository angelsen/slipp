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

Scope note: routing now goes through the `expose:` block (seeded into
slipp.yaml at launch, consumed by both proxy stages and the sync pruner —
not yet live-verified either), so this run also covers: the seeded block
appearing in slipp.yaml, wg-manage entries/route-flags derived from it,
and a hand-edit + redeploy surviving the post-deploy sync.

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
- [ ] Port `scans/portal` (`~/Projects/work/ultraportalen/scans/`,
      SvelteKit/systemd) to slipp — best remaining porting candidate, VPS
      already uses wg-manage for Caddy, first real consumer of `--proxy
      wg-manage` after Bulletins. `scans/admin` (Bente's Mac, LaunchAgent)
      is out of scope — not a VPS target.
- [ ] `--proxy wg-manage --public` needs its domain to already resolve to
      the host's public IP before `wg-manage service add --public` runs.
      Neither slipp nor wg-manage manages DNS records today — has to be
      created by hand until the Cloudflare provider (above) lands.
- [ ] Document the `expose:` block on slipp.dev — routing config
      (service → domain/path), seeding-at-launch, deletion-as-opt-out,
      the every-domain-needs-a-root rule, and the marker-based escape
      hatch for full Caddyfile control. It's the first slipp.yaml section
      users are *expected* to edit; currently undocumented.
- [ ] `expose:` list-form entries — one service on multiple domains/paths
      (`api: [{domain: ..., path: /api}, {domain: api.example.com}]`).
      Deliberately deferred: the dict is keyed by service name, so one
      route per service. Both translators already iterate entries, so
      it's a contained change — do it when the limit actually bites, not
      before.
- [ ] Incremental wg-manage peer service growth — `ensure_peer()`/
      `is_bootstrapped()` (`services/wg_peer.py`) treat a peer's assigned
      ports as one all-or-nothing set: adding a *new* service to an
      already-bootstrapped peer hits wg-manage's "peer already exists"
      error instead of incrementally opening just the new port. Documented
      as a known gap in `ensure_peer()`'s own docstring since the
      multi-host-deploy spec shipped (2026-07-17); found live but not
      fixed, since it needs `is_bootstrapped()` to check per-port state
      instead of the full current set, and `ensure_peer()` to open only
      the missing rule(s) rather than assuming a from-scratch bootstrap.
- [ ] Host-identity collision detection — two independently-registered
      slipp projects can silently point at the same physical host (same
      `ansible_host`) under different `inventory_hostname` labels, with no
      warning. `discover_across_hosts()`'s IP-based dedup
      (`services/discovery/pipeline.py`) then arbitrarily picks one
      project's name for `slipp ps` display — surfaced live when
      `slipp provision`'s auto-registered project collided with a
      `slipp hosts add`-registered peer for the same VPS (2026-07-17,
      worked around by deregistering the redundant project, root cause
      not fixed). Fix would need either provision-time detection (does
      any registered project already claim this `ansible_host`?) or a
      display-layer disambiguation so `ps` doesn't have to guess.
- [ ] Same-language multi-service port collision — two services of the
      same language/framework family on one host (e.g. two Python/Flask
      services) both scanner-detect the same default port, with no
      auto-allocation; needs a manual `app_port` edit today. Cross-host
      isn't affected (confirmed live during multi-host-deploy testing —
      same port on two different physical hosts is fine), only same-host
      same-family collisions.

---

## Open design questions

### Deploy stamps → host ledger (multi-dev sync, multi-project hosts)

Fast-forward-only deploys, `git push` semantics for `slipp deploy`: two
devs deploying the same project to the same target can silently roll each
other back today — nothing detects that the server has moved past your
local checkout.

**Increment 1 — sync guard.** After a successful deploy, write a stamp on
the target (`/var/lib/slipp/<project>.json`): commit hash, branch,
deployer, timestamp, slipp.yaml hash. Pre-flight on the next deploy:
`git merge-base --is-ancestor <deployed> HEAD` — deployed commit not in
your history (or unknown object, i.e. you haven't fetched) → error with
who/when, `--force` to override. Single-dev never trips it (always your
own ancestor). First deploy plants the stamp; no stamp → skip check.
Key the stamp by project name + repo fingerprint (root-commit hash,
stable across clones) so two unrelated repos both named `myapp` get a
"different project already deployed here" error instead of a misleading
divergence error. Branch-mismatch and dirty-worktree warnings fall out
nearly free. The slipp.yaml hash catches config drift too (stale
`expose:` block re-routing another dev's change).

**Increment 2 — claims + conflict pre-flight.** The stamp grows a
`claims` field (domains + ports, both already known at deploy time from
`expose:` and the scan). Before deploying, read the *other* projects'
stamps on the host: another project claims your domain → error; your
port → warn. Covers the collision classes per-project scoping (labeled
wg-manage entries, `<project>.caddy` files) can't.

**Increment 3 — host-centric view.** The stamps directory doubles as a
"what's deployed on this box" ledger: `slipp host status` (or extend
`slipp ps`) reads it — projects, commits, deployers, claims. This is the
"deployment registry" the many-to-many section below calls the missing
piece, grown incrementally instead of designed up front.

**Hard boundary:** the ledger is a passive record, never a coordination
system. Each project writes only its own file, only after a successful
deploy; reads are advisory pre-flights. No locks, no consensus — git +
slipp.yaml stay authoritative, the ledger is derived state rebuildable by
redeploying. On shared hosts like `mym-dev` this stays within the
additive-only rule: slipp still never touches what it doesn't own, it
just *reads* sibling stamps.

### Many-to-many: projects × servers

Today slipp is 1:1 (one `slipp.yaml` → one inventory → one server). Real
deployments are N:M — multiple services share a server, one project
deploys to staging + prod, etc.

**Missing piece:** a deployment registry — "server X runs services A, B,
C." `wg-manage`'s service list already is this for the network layer;
slipp needs its own equivalent or should read from `wg-manage`. The
host-ledger increments above are the current answer: stamps grow into
exactly this registry without a separate design.

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
- **2026-07-12** — Health-assessment refactor pass (commit `1961d9f`):
  shared `scanner/routing.py` classifier ending Caddy/wg-manage routing
  drift, Pangolin sync orchestration moved to new `services/resources.py`
  (restoring commands = args → service → output), `wg_manage.make_hub()`
  and `write_minimal_inventory()` extracted from command layer, dead code
  deleted (`delete_ssh_key`/`delete_record`, `CaddyConfig.staging`,
  `CaddySite.upstream_host`, `force_refresh` chain, unread provision-state
  fields), inventory-loading and project-registration dedup.
- **2026-07-12/13** — `expose:` routing block: launch seeds the routing
  decision (service → domain/path) into slipp.yaml instead of hiding it in
  code; both proxy translators and the wg-manage sync pruner consume the
  same block, so hand-edited routing survives deploys. Corrected default:
  with no frontend the backend serves `/` (adding a worker never moves the
  app's URL); Caddy and wg-manage now route identically, including
  `handle {path}/*` semantics (`/api` no longer swallows `/apiary`).
  Shared `validate_expose` (unknown service / duplicate claim / rootless
  domain) fails identically under both proxies; path validator, stale-
  domain warning, unrouted-service hint, single-write persistence.
  Five external review rounds. Shell-robustness pass from a full audit of
  interpolation sites: ingestion validation on project/service names (they
  become systemd units/paths/YAML — quoting can't save those), POSIX check
  on bootstrap `--user`, `shlex.quote` on image filter, container exec
  identifiers, wg-manage fqdn/label/route-flags. Not yet live-verified
  (see Next). Deploy-stamps → host-ledger design added (see design
  questions).
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
