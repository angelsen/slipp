---
title: Run Profiles
description: Local development with remote infrastructure
---

## Overview

Run profiles let you develop locally while connected to remote infrastructure via tunnels and vault secrets.

```mermaid
sequenceDiagram
    participant Dev as Developer
    participant Slipp
    participant Vault
    participant SSH as SSH Tunnel
    participant Cmd as Dev Server
    Dev->>Slipp: slipp run dev
    Slipp->>Vault: Load secrets
    Vault-->>Slipp: Environment vars
    Slipp->>SSH: Establish tunnel
    SSH-->>Slipp: Connected
    Slipp->>Cmd: npm run dev
    Cmd-->>Dev: Server running
```

## Create a Profile

```bash
slipp run dev \
  --cmd "npm run dev" \
  --tunnel-out 5173:app.example.com@myserver \
  --vault myproject
```

This creates a profile named `dev` that:

1. Loads secrets from the `myproject` vault
2. Sets up a reverse tunnel (local to remote)
3. Runs `npm run dev`

## Execute a Profile

```bash
slipp run dev
```

## List Profiles

```bash
slipp runs list
```

## Remove a Profile

```bash
slipp runs remove dev
```

## Tunnel Types

### tunnel-out (Reverse Tunnel)

Expose your local dev server to the remote infrastructure:

```bash title="Format"
--tunnel-out 5173:app.example.com@myserver
```

```mermaid
sequenceDiagram
    participant Browser
    participant Remote as app.example.com
    participant Local as localhost:5173
    Browser->>Remote: HTTPS request
    Remote->>Local: SSH tunnel
    Local-->>Remote: Response
    Remote-->>Browser: Response
```

### tunnel-in (Forward Tunnel)

Pull a remote service to your local machine:

```bash title="Format"
--tunnel-in postgres:5432@myserver
```

```mermaid
sequenceDiagram
    participant App as Local App
    participant Local as localhost:5432
    participant Remote as Remote Postgres
    App->>Local: Query
    Local->>Remote: SSH tunnel
    Remote-->>Local: Result
    Local-->>App: Result
```
