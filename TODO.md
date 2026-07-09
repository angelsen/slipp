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
- **Delegate exposure to wg-manage instead of templating Caddy — scoped
  (2026-07-07), not yet implemented.** Where the target host already runs
  wg-deploy's `wg-manage` (source of truth for Caddy via
  `/etc/wg-services.json`), slipp's `caddy` role should stop generating its
  own Caddyfile and instead shell out over the existing SSH connection to
  `wg-manage service add`. Re-verified both sides directly (not from stale
  notes) before scoping:

  **wg-manage's side is fully done and the contract is exactly as
  hoped.** `service add <name> <target> [--https|--public] [--upstream-tls]
  [--streaming] [--caddy-file F]` (`wg-deploy/templates/wg-manage.py.j2:930-963`)
  is genuinely idempotent — its own docstring: "the same command can be
  re-run safely (e.g. by an automated deploy) and converges to the same
  result," printing "Service unchanged" as a no-op when flags match what's
  already stored (`wg-manage.py.j2:667-712`). So slipp needs **no
  pre-check** (no `service list` diffing) — just call `service add`
  unconditionally every deploy, exactly like `ansible.builtin.package` or
  any other converge-to-desired-state module. wg-deploy's own TODO confirms
  no blockers remain on its side and spells out the exact call Bulletins
  needs: `wg-manage service add bulletins.chat <host>:<port> --public`.

  **The gap this surfaces that isn't just "swap the Caddy role": slipp has
  no per-service exposure control today.** `CaddyGenerator.build_caddy_sites()`
  (`generator/caddy_generator.py:114-179`) builds a site for *every*
  detected service unconditionally — the only override is the project-wide
  `--proxy none` flag (`VALID_PROXIES`, `constants.py`), there's no way to
  say "expose this service, not that one" within one `slipp launch`. Not
  fixing that here — the existing workaround (separate `slipp launch`
  invocations per exposure tier, e.g. `--dir admin --proxy none` for
  bulletins-admin and a second run for bulletins-chat) already covers
  Bulletins' actual need and keeps this feature's scope to "how a single
  exposed service gets its route," not "mixed exposure in one launch."

  **Design:**
  1. New `--proxy wg-manage` mode alongside today's `caddy`/`none`
     (`commands/launch.py`, `constants.VALID_PROXIES`). Like `--proxy none`,
     skips `CaddyRoleStage`/`CaddyGenerator` entirely (no Caddyfile
     templated) — but unlike `none`, still needs *something* generated.
  2. New lightweight role `roles/wg-manage-exposure/tasks/main.yml.j2`
     (no handlers/templates needed — no config file to reload, `wg-manage`
     handles its own Caddy regen/reload internally per its own docs) with
     one `ansible.builtin.command` task per exposed service:
     `wg-manage service add {{ domain }} {{ ansible_host }}:{{ port }} --public`
     (or `--https` for internal-only-but-TLS — see decision below), using
     `changed_when: "'unchanged' not in result.stdout"` on the registered
     result for accurate Ansible change-reporting, matching wg-manage's own
     stdout convention.
  3. Domain-per-service naming reuses the existing convention already in
     `build_caddy_sites()`'s multi-service branch: bare `app_domain` for a
     single service, `{{ service.name }}.{{ app_domain }}` per service
     otherwise. wg-manage's model is one-FQDN-to-one-target (no path-prefix
     multiplexing like Caddy's `domain/api` vs `domain/` split), so the
     path-prefix branch of `build_caddy_sites()` doesn't carry over —
     every exposed service just gets its own subdomain.
  4. **Open decision, needs a call before implementing:** `--public`
     (Let's Encrypt, internet-facing) vs `--https` (internal CA) isn't a
     distinction slipp's config models at all today (`CaddyConfig.auto_https`
     is one blanket bool). Needs an explicit flag at `slipp launch` time
     (matching the "explicit over auto-detected" precedent set for
     `runtime: systemd`) — leaning toward defaulting to `--https` (safer,
     internal-only) and requiring an explicit `--public` opt-in, since
     "internet-facing by default" is the wrong failure mode for a mistake.
  5. No existence check for `wg-manage` itself on the target host — same
     "explicit config, trust it" principle as the runtime work; if it's not
     actually there, the Ansible task just fails with a clear "command not
     found," which is an acceptable error mode for a deliberately-opted-into
     mode.

  **Confirmed: no wg-manage changes needed** — its CLI surface already
  covers everything this design uses, and wg-deploy's own TODO says so
  explicitly ("all items from the original slipp-integration review are
  now done"). Two adjacent things this scope surfaced that aren't
  wg-manage gaps either, but do affect whether it works end-to-end:
  - **DNS is a separate, unbuilt prerequisite.** `--public` mode means
    Let's Encrypt issuing a real cert, which requires the domain to
    already resolve to the host's public IP *before* `wg-manage service
    add --public` runs. Neither slipp nor wg-manage manages DNS records —
    that's the still-unbuilt Gigahost provider integration below. Until
    then, the domain's DNS record has to be created by hand first.
  - **This design only ever calls `service add`, never `service rm`.** If
    a service is renamed or removed from a project between deploys, its
    old `wg-manage` entry (and the Caddy route/cert it holds) would linger
    forever — slipp has no cleanup step. `wg-manage service rm` already
    exists; slipp's design just doesn't call it. Not fixing this in v1
    (matches slipp's existing non-cleanup-on-rename behavior for other
    generated artifacts), but flagging it since a stale *exposure* entry
    has more real consequence than a stale local file.

  **Verification when this gets implemented:** real end-to-end run against
  an actual wg-deploy-managed host (this one isn't scratch-project-testable
  the way the systemd role work was, since it needs a live `wg-manage`
  binary) — deploy bulletins-admin with `--proxy none` first (already
  possible today, validates the native app role on real infra), then once
  this lands, bulletins-chat with `--proxy wg-manage --public`.
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
- [x] Provider integrations (Gigahost) — implemented: providers add/list/remove,
      servers list, server status/reboot, domains check/register/list, dns sync/list,
      provision, up. Verified against live Gigahost API (2026-07-08).
- [x] Full SSH test session against a real VPS — completed 2026-07-08 against
      Gigahost VPS (193.200.238.213, Debian 13). Verified: bootstrap account,
      slipp launch, slipp deploy (Flask app in Docker). Found and documented
      several Debian 13 minimal issues (see below).

### Post-e2e fixes (from live VPS testing 2026-07-08)

- [x] Bootstrap: install python3 + rsync on fresh Debian (Ansible requires both,
      Debian 13 minimal includes neither). Added `_install_prerequisites` step to
      `services/bootstrap/account.py`.
- [x] Playbook template: `{{ runtime }}` used as package name but Debian/Ubuntu
      package is `docker.io` not `docker`. Mapped runtime → correct packages in
      template (`generator/templates/playbook.yml.j2`). Docker gets `docker.io` +
      `python3-requests`.
- [x] Runtime prompt: podman above docker, podman as default.
- [x] Deploy: print app URL at the end (https for domains, http for IPs).
- [x] Caddy template: IP-only deploys serve on `:80` with `auto_https off`.
- [x] Provision: show "up to 60 minutes" warning, timeout raised to 3600s.
- [x] Provision: resume-able flow — state saved to `~/.config/slipp/provisions/<name>.yaml`
      after ordering, so `slipp provision <name>` resumes poll→bootstrap→register
      if interrupted. Phases: ordered → provisioned → (deleted on completion).
- [ ] Bootstrap/provision: log SSH command output to `.slipp/logs/` for post-mortem
      debugging (same pattern as deploy's ansible-playbook logs)
- [ ] `slipp server install --continue` — list/pick from in-progress installs across
      all servers (for multi-project, multi-VPS workflows)
- [ ] Cloudflare provider (DNS-only, uses official Python SDK)

---

## Sudo password support for ps/logs/exec/status — staged, with follow-ups (2026-07-09)

Implementation is **staged (uncommitted)**: `--ask-become-pass` on
`ps`/`logs`/`exec`/`status`, a `SudoPasswordRequired` error, sudo-failure
detection (`check_sudo_result`), and `SSHService` rewriting `sudo ...` →
`sudo -S ...` with the password piped via stdin. This fixes the deferred gap
from the lanpad port (discovery silently reporting "No services found" on
hosts without passwordless sudo).

All inline fixes and the v2 detection improvements have been applied:

- [x] Redundant `try/except SudoPasswordRequired` blocks deleted from
  `common.py` and `ps.py` — global `SlippError` handler covers it.
- [x] Why-comments restored in `pipeline.py`.
- [x] `check_sudo_result` folded into `SSHService.check_sudo()` method —
  no more `password_was_provided` boilerplate or separate export.
- [x] `AskBecomePassOption` + `resolve_sudo_password()` factored into
  `commands/common.py` — all four commands use the shared definitions.
- [x] `check_sudo` wired into `status.py` and `logs.py` command-level SSH
  calls (not just discovery).
- [x] **`sudo -n true` probe** — `SSHService.require_sudo()` runs once in
  discovery before any `sudo systemctl` commands. Detects the need for a
  password before running, not after.
- [x] **Exact error-string matching** — `check_sudo` matches specific sudo
  messages (`a password is required`, `a terminal is required`,
  `incorrect password attempt`) instead of generic `"sudo:"` substring.
  Custom prompt sentinel was added then removed (false-positive: sudo writes
  the sentinel to stderr on every successful `-S` invocation too).
- [x] **`LC_MESSAGES=C` on all sudo commands** — sudo's error messages are
  gettext-translated (confirmed in source: `_()` / `ngettext()` / `U_()`
  macros, 30+ `.po` translations in the repo). On a `LANG=de_DE` host,
  `"a password is required"` becomes `"Ein Passwort ist notwendig"` and
  `check_sudo` would never match. Prepending `LC_MESSAGES=C` to all sudo
  commands forces English error output without affecting the child command's
  locale. Same gap exists in Ansible's become plugin (they use `dgettext()`
  on the controller side, which only works if controller and remote locales
  match).
- [x] **`execute_stream` captures stderr + exit status** after the stdout loop
  ends — stored as `ssh.last_stream_result`. `logs -f` checks it via
  `ssh.check_sudo()`, replacing the `line_count` heuristic.
- [x] `execute_stream` docstring documents that stdin is closed after the
  optional sudo password.

**Remaining follow-ups (not blocking):**

- The endgame is auto-prompting — detect → prompt on demand (injected prompt
  callback on `SSHService`) → retry, which would make `--ask-become-pass`
  unnecessary. The probe (`require_sudo`) is the foundation; the auto-prompt
  is the next step.
- `require_sudo`'s hint ("Use --ask-become-pass") is misleading when the SSH
  user isn't in sudoers at all — a password won't help. Edge case on
  slipp-provisioned hosts (which always create a sudoer), but worth noting for
  adopted hosts.

**Structural lesson (why this touched 13 files):** ~6 files were the
per-command flag (inherent to that UX choice — a global Typer option would
shrink it to one file, since sudo access is a property of the host, not the
command). The other ~7 were tramp data: intermediate layers
(`find_service_or_exit` → `discover_and_enrich` → `DiscoveryService` →
`_query_systemctl_batch`) take an `AnsibleHost` and construct `SSHService`
internally, so anything touching connection/execution semantics must thread
through every signature. Fix options, in order of preference: (a) the
prompt-on-demand probe above, which deletes the surface area entirely; (b) pass
the session/`SSHService` (or a factory for multi-host) down instead of
`AnsibleHost`, making such options a constructor detail in one layer.

---

## Many-to-many: projects × servers

Today slipp is 1:1 (one `slipp.yaml` → one inventory → one server). Real
deployments are N:M — multiple services share a server, one project deploys
to staging + prod, etc.

**Missing piece:** a deployment registry — "server X runs services A, B, C."
`wg-manage`'s service list already is this for the network layer; slipp needs
its own equivalent or should read from `wg-manage`.

Open questions:
- Per-environment inventories (`slipp deploy staging` / `slipp deploy prod`)
  partially works via `--env` but the UX is rough
- Shared-server deploys don't know about each other (port conflicts, shared Caddy)
- No global view of what's deployed where (`slipp servers list` shows servers
  but not their services)

---

## Port existing projects to slipp (before bulletins-chat)

Test slipp against real workloads to find gaps before the first "real" deployment.

### Candidates

| Project | Stack | Current deploy | Target | Fit |
|---------|-------|---------------|--------|-----|
| **lanpad** (`~/Projects/work/MyMechanic/mym-verksted-pluss/lanpad/`) | Python/FastAPI, systemd | ~~git push → post-receive → uv sync → restart~~ **ported to `slipp deploy` (2026-07-09)** | Internal VM (`mym-dev`, 192.168.60.21) | Done |
| **partbridge** (`~/Projects/work/MyMechanic/mym-verksted-pluss/tools/partbridge/`) | Python/FastMCP, systemd | git push → post-receive → uv sync → health check → auto-rollback | Same VM | Good, but has rollback logic slipp lacks |
| **scans/portal** (`~/Projects/work/ultraportalen/scans/`) | SvelteKit, systemd | git push → post-receive → npm ci → build → rsync → restart | VPS (Gigahost, wg-manage Caddy) | Best fit — already uses wg-manage |
| **scans/admin** (`~/Projects/work/ultraportalen/scans/`) | SvelteKit, LaunchAgent | git push → deploy.sh → build → drizzle push → restart | Bente's Mac | No — macOS, not a VPS |

### lanpad — ported (2026-07-09)

Deployed via a new Python/uv systemd role (`roles/app-systemd-python/`),
replacing lanpad's git-push/post-receive-hook workflow entirely (approach 1
from the git-push-to-deploy options below). Verified live against `mym-dev`:
service active, serving real traffic, idempotent redeploy, `--packages` data
survives redeploy. Real gaps this surfaced, all fixed:

- **Python app role** — done. New `roles/app-systemd-python/` template set,
  `PythonVariableExtractor` gained entrypoint resolution
  (`[project.scripts]` → binary, or file fallback) and `uv.lock` detection.
  New `--python-extra`/`--exec-args` flags on `slipp launch`.
- **uv workspace member with no standalone lockfile** — lanpad lives inside
  the `mym-verksted-pluss` uv workspace; its own directory has no `uv.lock`
  (the workspace root does). `uv sync --frozen` fails hard in this case.
  Fixed: `hasUvLock` detection drops `--frozen` automatically and warns at
  `slipp launch` time instead of failing at deploy time. Also fixed a
  parallel silent-failure risk: a Python service with no `[project.scripts]`
  entry *and* no recognized entrypoint file would generate a bare
  `ExecStart=.../.venv/bin/python` that crash-loops — now warned at launch
  time too.
- **No passwordless sudo on an adopted host** — `mym-dev` was never
  bootstrapped by slipp, so `fredrik`'s sudo needs a password. Added
  `--ask-become-pass` to `slipp deploy` (mirrors the existing vault-password
  prompt pattern — prompts before the spinner, passes the password via a
  temp extra-vars file, never argv). Real Ansible limitation hit along the
  way: `ansible.posix.synchronize`'s rsync shells out its own
  `sudo -u root rsync` over a raw ssh call that never sees
  `ansible_become_pass` — no amount of become-password plumbing fixes that
  specific task.
- **Both systemd templates ran the deployed app as root** — pre-existing in
  the Node role too, not just the new Python one. No privileged port is
  ever needed, so root was pure unnecessary blast radius. Redesigned both
  to run as `ansible_user` (the SSH-connecting user) — `become: true` stays
  only on the genuinely root-requiring tasks (package/systemd management).
  This also sidesteps the synchronize/become limitation above for free.
- **Not leveraging uv's own Python management** — the role used to install
  Python via the OS package manager. Switched to `uv python install
  {{ pythonVersion }}` + `uv sync --managed-python`, so the app's venv uses
  a uv-managed interpreter pinned to `.python-version`, not whatever the
  target distro happens to have packaged. Also added `--no-dev` to `uv
  sync` (matches partbridge's own hardened production pattern, wasn't
  wired in before).
- **`--proxy none` deploys showed a wrong/incomplete URL** — two separate
  pre-existing bugs, not new: the launch summary unconditionally listed a
  Caddy role and hardcoded `https://` with no port; `slipp deploy`'s own
  post-deploy hint had the same missing-port gap. Fixed both; added
  `app_port` persistence to `inventory.yml` so the deploy-time hint can
  know the port without re-scanning.

**New gap found, not fixed (deliberately deferred):** `slipp ps`/`slipp
logs`/discovery is silently broken on any host without passwordless sudo.
`DiscoveryService._query_systemctl_batch()` runs `sudo systemctl
list-units ...` over a plain SSH exec (not Ansible — `--ask-become-pass`
doesn't reach this path) and deliberately ignores the exit code (legitimate
reason: some setups exit nonzero with valid stdout). But that means a sudo
auth failure and a genuinely-empty host both produce empty stdout, and
discovery reports "No services found" either way — no error surfaced.
Confirmed live: `lanpad-lanpad.service` was active and serving on
`mym-dev`, but `slipp ps --refresh`/`slipp logs lanpad` both reported
nothing found. Fix would mean either detecting the sudo-failure case
explicitly (cheap, just stops the silent lie) or a full become-password
prompt for `SSHService` itself (bigger, mirrors `--ask-become-pass` but for
the ps/logs/exec path instead of deploy). **Update 2026-07-09: implemented
(staged) — see "Sudo password support for ps/logs/exec/status" section
below.**

### Gaps these would surface

- **Rollback** — partbridge has health-check + auto-rollback on failed deploy.
  slipp has no rollback mechanism.
- **Database migrations** — scans runs `drizzle db:push` during deploy. slipp's
  playbook template has no migration hook.
- **Git-push-to-deploy** — all three use `git push deploy main`. Two approaches:
  1. Replace entirely: run `slipp deploy` from dev machine instead of pushing
     (lanpad did this, see above)
  2. Hybrid: keep push trigger but the post-receive hook runs `slipp deploy`
     instead of bespoke shell scripts
  3. `slipp deploy --mode push` generates bare repo + post-receive hook
- **Shared server** — lanpad and partbridge deploy to the same VM. Need to handle
  multiple projects targeting one host without conflicts. Confirmed this VM is
  genuinely multi-tenant (also runs a third, unrelated service — `dtc-mcp`,
  owned by a colleague, manually deployed under its own Unix user) — slipp
  must stay additive-only there, never enumerate/touch what it doesn't own.

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

