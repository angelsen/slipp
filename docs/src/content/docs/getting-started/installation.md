---
title: Installation
description: How to install slipp
---

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Install with uv (recommended)

```bash
# From PyPI
uv tool install slipp

# Or from GitHub (latest)
uv tool install git+https://github.com/angelsen/slipp
```

This installs `slipp` globally and makes it available in your PATH.

## Install with pip

```bash
pip install slipp
```

## For Development

```bash
git clone https://github.com/angelsen/slipp.git
cd slipp
uv sync
uv run slipp --help
```

## Shell Completion

Enable tab completion for your shell:

```bash
# Bash
slipp --install-completion bash

# Zsh
slipp --install-completion zsh

# Fish
slipp --install-completion fish
```
