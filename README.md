# slipp

**Build locally, slipp to production.**

90% automation for self-hosted app deployments. Generate Ansible deployments from your codebase + ops tools (logs, status, exec) for debugging.

## Quick Start

```bash
# Install
uv sync

# Generate complete Ansible project
slipp launch

# Deploy to VPS
slipp deploy

# Operations
slipp ps
slipp logs backend -f
```

## What It Does

`slipp launch` scans your project and generates:

```
my-app/
├── inventory.yml              # Ansible inventory (standard format)
├── playbook.yml               # Role-based deployment playbook
├── group_vars/all.yml         # Service variables
├── roles/                     # Ansible roles
│   ├── caddy/                 # Reverse proxy (auto HTTPS)
│   ├── app-backend/           # Flask/FastAPI service
│   └── app-frontend/          # SvelteKit/Next.js service
├── docker-compose.yml         # Local development
└── packages/*/Dockerfile      # Container images
```

**Then:** `slipp deploy` runs `ansible-playbook` to deploy everything.

## Features

- **Smart Detection**: Auto-detects Flask, FastAPI, Django, SvelteKit, Express, Next.js
- **Ansible Generation**: Standard `inventory.yml` + `playbook.yml` (works with any Ansible tool)
- **Dockerfiles**: Fetched from Fly.io templates, cached locally
- **Operations**: `logs`, `status`, `exec` commands for debugging deployments
- **Run Profiles**: Local dev with remote infrastructure (tunnels + vault secrets)
- **Multi-Environment**: Support for dev/staging/production with separate inventories

## Commands

### Generation
```bash
slipp launch                   # Generate full Ansible project
slipp generate dockerfile      # Generate only Dockerfiles
```

### Deployment
```bash
slipp deploy [env] [preset]    # Deploy to environment
slipp deploy --dry-run         # Dry-run deployment
```

### Run Profiles (local dev with remote infrastructure)
```bash
# Create profile: dev server with tunnel
slipp run dev \
  --cmd "npm run dev" \
  --tunnel-out 5173:app.example.com@infra

# Execute saved profile
slipp run dev

# Manage profiles
slipp runs list
slipp runs remove dev
```

### Operations
```bash
slipp ps                       # List all services
slipp status <service>         # Detailed service status
slipp logs <service> -f        # Stream service logs
slipp exec "command"           # Execute command on VPS
slipp ssh                      # Interactive SSH session
```

### Projects
```bash
slipp projects list            # List registered projects
slipp projects add <name>      # Register project
slipp projects remove <name>   # Unregister project
```

### Secrets
```bash
slipp secret                   # Generate secure secret
slipp secrets list             # Show all vaults
slipp secrets add <name>       # Add secret to vault
slipp secrets sync vars.yml    # Generate secrets for {{ vault_* }} refs
```

## Requirements

**On your machine:**
- Python 3.12+
- uv (package manager)

**On target VPS:**
- Ubuntu 20.04+ or Debian 11+
- SSH access
- systemd

## Philosophy

**90% automation, not complete infrastructure management.**

- Generate Ansible deployments for custom apps
- Ops tools (logs/status/exec) for debugging
- Works alone or alongside existing Ansible projects
- No lock-in: Standard Ansible, runs anywhere

---

**Inspiration:** fly.io UX + kubectl ops + Ansible pragmatism
