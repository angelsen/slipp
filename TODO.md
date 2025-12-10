# slipp TODO

## slipp run Progress Output

### Problem

After Phase 2 refactor, `slipp run` lost progress feedback:
```
ℹ Updated profile 'dev'
<command runs immediately, no pipeline visibility>
```

### Goal

Show pipeline steps:
```
ℹ Loading vault secrets...
✓ Loaded 5 env vars from mdad
ℹ Setting up tunnels...
✓ Tunnel: localhost:5173 → auth.metria.no
ℹ Adding Caddy routes...
✓ Route: auth.metria.no → :5173
```

### Approach

Executor already has separate methods returning results:
- `load_vault_secrets()` → `VaultLoadResult`
- `setup_tunnels()` → `TunnelSetupResult`
- `setup_caddy_routes()` → `CaddyRouteResult`

Options:
1. Command calls methods individually (quick, some duplication)
2. Add progress callback to `execute()` (cleaner)

---

---

## Tunnel Auth

### Goal

Add HTTP basic auth to tunnel-out routes for security.

```bash
slipp run dev --tunnel-out 5173:auth.metria.no@mdad --tunnel-auth user:pass
```

### Implementation

- Add `--tunnel-auth` flag to `slipp run`
- Pass credentials to `CaddyProxy.add_route()`
- Caddy hashes password and adds `basicauth` directive
- One auth applies to all tunnel-out routes

### Caddy Config

```caddyfile
@auth host auth.metria.no
handle @auth {
    basicauth {
        user $hashed_pass
    }
    reverse_proxy localhost:5173
}
```

---

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

## Config Refactor: Merge runs.yaml into slipp.yaml

### Problem

Run profiles currently live in `.slipp/runs.yaml` (hidden directory), but they're useful to share with team via git.

```
project/
├── slipp.yaml              # Project config (tracked)
├── .slipp/
│   ├── runs.yaml           # Run profiles (hidden, but useful to share!)
│   └── logs/               # Logs (untracked)
```

### Goal

Single config file, git trackable, secrets stay in vaults.

```yaml
# slipp.yaml - single source of truth
name: nor-auth
inventory: inventory/hosts
vault: inventory/vault.yml

runs:
  dev:
    cmd: npm run dev
    vaults: [mdad]              # Secrets from vault, not inline
    env:
      - VITE_DEV_HOST=auth.metria.no
      - NORAUTH_ISSUER_URL=https://auth.metria.no
    tunnels:
      out: [5173:auth.metria.no@mdad]

  46dev:
    extends: dev                # Inherit from dev profile
    vaults: [mdad, nor-auth]    # Multiple vaults support
```

### Directory Structure

```
project/
├── slipp.yaml              # Config + runs (tracked)
├── .slipp/                 # Local-only, .gitignore'd
│   ├── logs/               # Command logs
│   ├── cache/              # Temp files
│   └── runs.local.yaml     # Personal overrides (optional)
```

### Features

| Feature | Description |
|---------|-------------|
| `extends` | Inherit from another profile |
| Multiple vaults | `vaults: [mdad, nor-auth]` |
| `runs.local.yaml` | Personal overrides, not tracked |

### Migration

1. Move `runs:` section into `slipp.yaml`
2. `.slipp/` becomes untracked-only (logs, cache, local overrides)
3. Deprecate `.slipp/runs.yaml` with warning

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
- [ ] Config refactor: merge runs.yaml into slipp.yaml
- [ ] Run profile inheritance (`extends: dev`)
- [ ] slipp run progress output
- [ ] slipp deploy progress output (ansible buffering - use `stdbuf -o0`)
- [ ] JSON output (`-o json`) for all plural commands
- [ ] Tunnel auth (`--tunnel-auth user:pass`)
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

**Gigahost** (Server + DNS + Registrar):
```
GET  /servers                      # List VPS with IPs
GET  /servers/{id}                 # Server details
GET  /servers/{id}/powerstate      # Power status
GET  /servers/{id}/reboot          # Reboot
PUT  /servers/{id}/reverse         # Reverse DNS
GET  /dns/zones                    # List domains
POST /dns/zones/{id}/records       # Create DNS record
```

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

