---
title: Quick Start
description: Get up and running with slipp in 5 minutes
---

## Generate Your First Deployment

Navigate to your project directory and run:

```bash
slipp launch
```

This scans your codebase and generates:

```yaml
your-project/
├── inventory.yml        # Ansible inventory
├── playbook.yml         # Deployment playbook
├── group_vars/all.yml   # Service variables
├── roles/               # Ansible roles
└── Dockerfile           # Container image (if needed)
```

## Deploy to Your VPS

```bash
slipp deploy
```

This runs `ansible-playbook` with your generated configuration.

## Operations

Once deployed, use slipp for debugging:

```bash
# List running services
slipp ps

# View logs
slipp logs backend -f

# Execute commands
slipp exec "docker ps"

# Interactive SSH
slipp ssh
```

## Next Steps

- Learn about [Run Profiles](/guides/run-profiles/) for local development
- Configure [Vault Secrets](/guides/secrets/) for sensitive data
- Set up [Tunnels](/guides/tunnels/) to connect local dev to production
