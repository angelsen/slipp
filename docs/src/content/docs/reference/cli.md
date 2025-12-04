---
title: CLI Reference
description: Complete command reference for slipp
---

## Global Options

```bash
slipp [OPTIONS] COMMAND [ARGS]
```

| Option          | Description                              |
| --------------- | ---------------------------------------- |
| `--verbose, -v` | Enable verbose logging                   |
| `--output, -o`  | Output format: `table` (default), `json` |
| `--help`        | Show help message                        |

## Commands

### Generation

| Command                     | Description                                     |
| --------------------------- | ----------------------------------------------- |
| `slipp launch`              | Generate complete Ansible project from codebase |
| `slipp generate dockerfile` | Generate only Dockerfiles                       |

### Deployment

| Command                       | Description           |
| ----------------------------- | --------------------- |
| `slipp deploy <env> <preset>` | Deploy to environment |
| `slipp deploy --dry-run`      | Dry-run deployment    |

### Run Profiles

| Command                    | Description                 |
| -------------------------- | --------------------------- |
| `slipp run <name>`         | Execute a saved run profile |
| `slipp runs list`          | List all profiles           |
| `slipp runs remove <name>` | Remove a profile            |

### Operations

| Command                     | Description               |
| --------------------------- | ------------------------- |
| `slipp ps`                  | List all running services |
| `slipp status <service>`    | Detailed service status   |
| `slipp logs <service> [-f]` | View/stream service logs  |
| `slipp exec "<command>"`    | Execute command on VPS    |
| `slipp ssh`                 | Interactive SSH session   |

### Projects

| Command                        | Description              |
| ------------------------------ | ------------------------ |
| `slipp projects list`          | List registered projects |
| `slipp projects add <name>`    | Register a project       |
| `slipp projects remove <name>` | Unregister a project     |

### Secrets

| Command                       | Description                               |
| ----------------------------- | ----------------------------------------- |
| `slipp secret`                | Generate a secure random secret           |
| `slipp secrets list`          | Show all vaults                           |
| `slipp secrets add <name>`    | Add secret to vault                       |
| `slipp secrets sync vars.yml` | Generate secrets for `{{ vault_* }}` refs |
