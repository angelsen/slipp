---
title: Secrets
description: Generate and manage Ansible vault secrets for deployments
---

## Generate a Secret

```bash
slipp secret
```

### Options

```bash title="Custom length or encoding"
slipp secret --bytes 32      # Custom length
slipp secret --base64        # Base64 encoded
```

## List Vaults

```bash
slipp secrets list
```

## Add a Secret

```bash
slipp secrets add <name>
```

Prompts for value, encrypts, and stores in vault.

## Sync Secrets

Generate secrets for all `{{ vault_* }}` references in a vars file:

```bash
slipp secrets sync <path>
```

Finds undefined vault references and prompts you to create them.

## Use in Run Profiles

Load vault secrets as environment variables:

```bash
slipp run dev --vault <project> --cmd "npm run dev"
```

Secrets are injected into the command's environment.
