# slipp TODO

## Next: deploy the real Bulletins project through the now-verified wg-manage composition

The wg-manage/slipp composition mechanism itself is now fully live-verified
(see Shipped: wg-manage single-node, multi-node, `--proxy auto` probe,
per-service internal-only exposure, the `expose:` block feeding all of
it) — all against the synthetic `wgtest-smoke` fixture, not yet the real
Bulletins project. What's left is the actual cutover:
[`wg-deploy`](~/Projects/private/wg-deploy)'s `slipp-composition` spec's
target flow is one command end-to-end (`slipp up <name> --hub --domain
<domain>`, provisioning + hub-ifying + `--proxy auto` composing through
wg-manage-owned Caddy in one shot); for Bulletins specifically: deploy
bulletins-admin with `--proxy none` (already possible today), then
bulletins-chat with `--proxy auto --public` (or explicit `--proxy
wg-manage --public`) against a real hub. Not urgent — bulletins-chat isn't
live/serving users yet.

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
- [ ] Generic Node Dockerfile template fails to build — the fetched
      flyctl template (`scanner/templates/node/Dockerfile`, same
      fetch-verbatim mechanism as the Python one) has `COPY --link
      package.json package-lock.json .`; Docker rejects a multi-source
      `COPY` whose destination doesn't end in `/`, so any real generic
      Node project fails at the image-build step on container runtime.
      Found live (2026-07-18) while building a throwaway two-file Node
      fixture for an unrelated test -- not investigated further, switched
      to a Flask fixture to keep that test isolated. Reproduced against
      real Docker on `bulletins-dev`'s `peer1`, not a local-only quirk.
      Fix is presumably a one-line template patch (destination `./` or
      splitting into two `COPY` lines) but needs verifying against
      flyctl's actual template intent before changing it.

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
  identifiers, wg-manage fqdn/label/route-flags. Live-verified 2026-07-16
  onward (see below). Deploy-stamps → host-ledger design added (see design
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
  against the code (reproductions, not trust) before fixing. Live-verified
  2026-07-17 onward (see below).
- **2026-07-15/16** — Live end-to-end smoke-testing established (new
  `smoke-test` skill, `bulletins-dev` standing throwaway Gigahost VPS),
  after a git history squash (113 → 48 commits, byte-identical tree,
  verified via `git diff`). Eight real bugs found and fixed by actually
  running the pipeline against real infrastructure, none of them visible
  from static review: missing `curl`/`jq` prerequisites causing silent
  pipe failures (`bootstrap/account.py`, `caddy_dev` playbook), a Gigahost
  `create_zone()` response-shape crash, Caddy route-push corruption via an
  unguarded `jq` pipe (`_push_route()`), a misplaced `containers.podman`
  `force_rm` parameter, a dev-proxy iptables `PREROUTING` rule hijacking
  *all* outbound `:443` traffic on the host (the real root cause behind a
  costly podman-MTU red herring), a missing post-deploy health check on
  the container role (ported the systemd role's block/rescue pattern,
  which also made the `notify`/handler machinery it replaced dead code —
  removed), and duplicate `slipp ps` rows when two projects share a host
  (`discover_across_hosts()` now dedupes by `ansible_host`). Also fixed a
  doubled-blank-line output bug. Commits `81ca7f7`, `fd5c096`, `6d698f8`,
  `656df84`, `bc1360a`.
- **2026-07-16** — Multi-service deploy path (N services per project,
  Caddy path routing) validated live via a new `multiservice-smoke`
  fixture. Found and fixed the Caddy config-reload `notify:`/handler bug
  (handlers only flush at the end of a *successful* play -- a later-role
  failure leaves a written-but-unapplied Caddyfile while `slipp deploy`
  still reports success) and a silent Caddyfile collision between
  `--proxy caddy` and the dev-proxy (both bind `:443`, no coordination
  between them). Asked "where else does this bug class live?" and turned
  that into an 8-fix audit: no collision detection on project
  registration, the same response-shape bug on Gigahost's
  `create_record()`, `sync_dns()` only checking the first duplicate `@`
  record, wg-manage's `sync()` silently pruning an undetectable-service
  directory as a stray, a Pangolin `has_target` type mismatch,
  `slipp.yaml` silently dropping hand-added unrecognized keys
  (`extra: "ignore"` → `"allow"`), and unguarded wg-manage JSON parsing.
  Established **"Fail Loud, Never Corrupt Silently"** as this project's
  standing precedent for identity/location conflicts (hard-fail, not
  warn-and-proceed) -- written into `CLAUDE.local.md`. Commit `78413e4`
  (all 8 fixes, one commit). Scoped (not yet built) `--proxy wg-manage`
  multi-node support as its own design-sized feature, after confirming
  the generator hardcoded `localhost` targeting with no per-host play
  generation anywhere at the time.
- **2026-07-17** — `--proxy wg-manage` single-node validated live for the
  first time (hub-ified `bulletins-dev` via `slipp providers add
  wg-deploy` + `slipp up --hub`), finding and fixing a dev-proxy/wg-manage
  Caddy `:443` collision (same bug class as 2026-07-16's Caddy-collision
  fix, extended to cover hub-ification too) and a missing `--public`
  passthrough on `slipp up`. Then **multi-host-deploy** shipped and
  live-verified end-to-end: a project can declare a secondary host
  (`slipp hosts add`), assign a service to it
  (`expose.<service>.host`), and `slipp deploy` generates one Ansible
  play per host, auto-bootstrapping secondary hosts as WireGuard peers of
  the hub (`services/wg_peer.py`). Provisioned a real second Gigahost VPS
  (`peer1`, kept running as a standing fixture, 49 kr/month) and
  live-verified the full two-host round trip, finding and fixing 6 more
  real bugs (`--reconfigure` dropping secondary hosts, `wg-quick` failing
  on a captured `DNS =` line, extra-vars list corruption, `ufw` never
  enabled breaking idempotency, undefined `ansible_port`, `slipp ps -p`
  omitting secondary-host services). Commits `2e43598`, `366bad8`,
  `657493c`. Reacted to wg-deploy's `--https` → `--internal-tls` rename
  (clean break, no alias): updated the generator with a version-gate,
  upgraded `bulletins-dev` itself to wg-manage 1.1 live with zero
  regression (`metria`/`ultraportalen` confirmed still on 1.0,
  deliberately left alone). Commit `5c0ab96`.
- **2026-07-18** — Per-service **internal-only exposure** shipped and
  live-verified: `expose.<service>.internal: true` forces that one
  service through `wg-manage --internal-tls` regardless of the project's
  `--public` flag, mixed freely with public services, no public DNS
  record needed. Rejected outside `--proxy wg-manage`. Verified against a
  real mixed public+internal deployment on `wgtest-smoke`/`bulletins-dev`
  (confirmed `[HTTPS]` vs `[PUBLIC]` exposure, internal-CA reachability
  with zero public DNS resolution, idempotent redeploy). Commit
  `6b30a70`. Also live-verified the `--proxy auto` SSH-probe path for the
  first time (previously only ever exercised via explicit `--proxy
  wg-manage`), finding and fixing a real bug: `add_secondary_host()`/
  `remove_secondary_host()`/`write_minimal_inventory()` wrote
  `inventory.yml` without the generation marker `InventoryFileStage`
  checks before regenerating, so any project that ever used `slipp hosts
  add` (every multi-host project) silently stopped receiving
  `inventory.yml` updates from `slipp launch` forever after -- including
  the `proxy_owner` cache, defeating `--proxy auto`'s offline-stable
  re-launch design. Fixed by routing all inventory writers through the
  same marked template, which now also round-trips `is_primary`/
  `key_file` (previously omitted -- would have silently reset multi-host
  inventories back to single-primary the first time one was actually
  regenerated through it). Commit `db2f664`. Fixed the same-language
  multi-service port collision backlog item too: `expose.<service>.port`
  (mirroring `expose.<service>.host`) lets a service's port be overridden,
  and `slipp launch` now fails loud -- naming both services and pointing
  at the field -- if two services on the same host still collide after
  overrides, instead of silently generating a config where the second one
  can't bind. Live testing (not just reading the template) caught a real
  correctness gap in the first version of this fix: a container's
  Dockerfile `CMD` is fetched verbatim from the upstream flyctl template
  and hardcodes its own listening port (Flask's `--port=8080` has no
  template variable slot at all), so overriding `DetectedService.port`
  directly would have mismatched the container's actual internal port
  against the host-side publish port. Fixed properly by introducing a
  distinct host-facing port (`context.host_ports`, new
  `PortResolutionStage`) that only the host-side `-p HOST:CONTAINER`
  mapping, Caddy's `reverse_proxy` target, and wg-manage's service target
  read -- the container's own internal port is never touched. For systemd
  (no container layer, no host/container split) the override applies
  directly to `service.port` as before, since `Environment=PORT={{
  service.port }}` already reads it. Verified live end to end against
  `wgtest-smoke`/`bulletins-dev`: a third same-host service correctly
  failed loud with no override, then deployed and was reachable through
  the resolved host port (`docker ps` confirmed `8082->8080/tcp`, `curl`
  through the actual wg-manage route succeeded) once
  `expose.admin.port: 8082` was set, idempotent on redeploy, zero
  regression on the two pre-existing services (byte-identical `-p
  8080:8080`). Fixed incremental wg-manage peer service growth too:
  `is_bootstrapped()`'s all-or-nothing port check couldn't tell "peer
  never bootstrapped" apart from "tunnel's fine, a newly assigned port
  just needs its own firewall rule," so `ensure_peer()` always retried
  the one-shot `wg-manage add` (which fails "already exists" on a peer
  that's already registered) instead of just opening the new port. Split
  the check into a new tunnel-only `_tunnel_active()` and a `firewall`-
  tagged subset of the bundled `wg_peer` playbook (idempotent per port);
  `ensure_peer()` now runs only that tag when the tunnel's already up,
  skipping `wg-manage add`/key work entirely. Needed a second fix to make
  that possible: the peer's hub-facing WireGuard IP (`hub_wg_ip`, scopes
  the firewall rule's source) was previously only ever captured as a
  side effect of `wg-manage add`'s one-time output -- no wg-manage CLI
  command exposes it afterward (confirmed live: `list --json`/`status
  --json` omit it) -- so it's now read directly off the hub's `wg0`
  interface instead (`ip -4 -o addr show wg0`; "wg0" is wg-manage's own
  fixed interface name, confirmed in wg-deploy's own template). Entirely
  a slipp-side fix -- wg-manage's own contract (peer `add` is one-shot,
  correctly non-reissuable key material) is unchanged. Verified live
  against the standing `peer1` fixture: added a second service to an
  already-bootstrapped peer, confirmed the deploy succeeded via the
  incremental path alone (peer's public key unchanged throughout -- a
  full re-bootstrap attempt would have failed loudly), `ufw status`
  showed both ports' rules, the new service was reachable over the
  tunnel, and a second deploy was idempotent (`Service unchanged` on all
  three wg-manage entries).
- **2026-07-18 (later same day)** — Fixed a real security exposure found
  while re-verifying the peer-growth fix above: every container-runtime
  service fronted by a proxy (Caddy or wg-manage, primary host or
  secondary) was reachable directly from the raw public internet,
  completely bypassing the reverse proxy *and* the `ufw` rule meant to
  scope a secondary host's traffic to just the hub. Confirmed live:
  `worker` (on `peer1`, a wg-manage secondary host) had been reachable
  on `193.200.238.188:8080` from a machine with zero VPN/mesh access at
  all since the original multi-host-deploy session two days earlier --
  nobody had tested reachability from outside the mesh until now. Root
  cause, confirmed against official docs (Red Hat's own solutions
  article, not guessed): Docker and rootful Podman both manage their own
  iptables NAT rules for a published container port (`-p PORT:PORT`,
  implicitly `0.0.0.0`) *ahead of* `ufw`'s INPUT filter chain -- this is
  documented, intended behavior in both runtimes (tracked as
  [RHEL-27842](https://issues.redhat.com/browse/RHEL-27842) for a
  possible future opt-in change), not a slipp bug or something a
  correctly-written `ufw` rule could ever have prevented. Fixed by
  binding every published port to a specific interface instead of
  `0.0.0.0` -- the established pattern (confirmed via research, not just
  reasoned about) for exactly this "only the reverse proxy should reach
  this" and "only the VPN tunnel should reach this" shape: `127.0.0.1`
  for a service on the primary host (Caddy/wg-manage's own Caddy is
  always the same machine), the peer's own WireGuard tunnel IP for a
  secondary host. The peer IP isn't knowable at `slipp launch` time (the
  peer may not even be bootstrapped yet, and baking a tunnel IP into a
  static file is fragile regardless) -- new `context.bind_ips`
  (`PortResolutionStage`) emits a live discovery task
  (`roles/app-container/tasks/main.yml.j2`, `ip -4 -o addr show
  <iface>`) for that case only, using the same slipp-renders-once/
  Ansible-renders-again two-pass template trick the `wg-manage`
  version-gate already established (a Python-side variable whose value
  is literal Ansible `{{ }}` expression text, left untouched by slipp's
  own Jinja pass since it doesn't recursively re-render a rendered
  variable's string content -- verified directly against Jinja2's actual
  behavior before relying on it). `docker-compose.yml` (local dev) now
  binds `127.0.0.1` unconditionally too, for free, no UX cost (`docker
  compose`'s own `localhost` access is unaffected). `--proxy none` stays
  on `0.0.0.0` -- public reachability is the actual intent there.
  Verified live against `wgtest-smoke`/`bulletins-dev`/`peer1`: `docker
  ps` confirmed the exact bind addresses (`127.0.0.1:8080->8080/tcp` on
  the hub, `10.1.0.2:8080->8080/tcp` on the peer, live-discovered
  correctly), every previously-exposed port now silently unreachable
  from a machine outside the mesh entirely, the real proxy paths
  (`https://wgtest.getrekt.no`, `https://worker.getrekt.no`) fully
  unaffected, second deploy idempotent. Not yet applied to the native
  systemd (non-container) runtime -- there, the app process's own bind
  address is up to its own code, which slipp doesn't control the way it
  controls a container's `-p` mapping; worth checking separately if it
  becomes a concern, not scoped into this fix.
