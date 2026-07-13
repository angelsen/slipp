"""Shared XDG config-store plumbing: path resolution, corruption recovery, atomic writes.

Backs the three ~/.config/slipp/ stores (RegistryIO, ProviderConfigService,
ProvisionStateService) so their load/save/corruption-recovery mechanics
can't drift apart.
"""

import json
import logging
import os
import shutil
from pathlib import Path
from typing import TypeVar, overload

import yaml
from pydantic import BaseModel

from slipp.utils.files import atomic_write_text

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)


def slipp_config_dir(subdir: str | None = None) -> Path:
    """~/.config/slipp (or $XDG_CONFIG_HOME/slipp), created with mode 0o700.

    With subdir, also creates <dir>/<subdir> (0o700) and returns it.
    """
    xdg_config = os.getenv("XDG_CONFIG_HOME")
    if xdg_config:
        config_dir = Path(xdg_config) / "slipp"
    else:
        config_dir = Path.home() / ".config" / "slipp"

    config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if subdir:
        config_dir = config_dir / subdir
        config_dir.mkdir(exist_ok=True, mode=0o700)
    return config_dir


@overload
def load_model(
    path: Path, model_cls: type[ModelT], *, default: ModelT, label: str
) -> ModelT: ...
@overload
def load_model(
    path: Path, model_cls: type[ModelT], *, default: None, label: str
) -> ModelT | None: ...
def load_model(
    path: Path, model_cls: type[ModelT], *, default: ModelT | None, label: str
) -> ModelT | None:
    """Load a pydantic model from a JSON (.json) or YAML config file.

    Missing file -> default. A parse error backs the file up to
    <path><suffix>.backup and warns; any other failure (including
    validation) warns -- both return default, so a broken store never
    takes the CLI down.
    """
    if not path.exists():
        return default

    try:
        text = path.read_text()
        if path.suffix == ".json":
            data = json.loads(text)
        else:
            data = yaml.safe_load(text) or {}
        return model_cls.model_validate(data)
    except (json.JSONDecodeError, yaml.YAMLError) as e:
        backup_path = path.with_suffix(path.suffix + ".backup")
        shutil.copy(path, backup_path)
        logger.warning(f"{label} corrupted: {e}. Backed up to: {backup_path}")
        return default
    except Exception as e:
        logger.warning(f"Failed to load {label}: {e}")
        return default


def save_model(path: Path, model: BaseModel, *, exclude_none: bool = False) -> None:
    """Serialize a pydantic model (format by path suffix) and write atomically.

    Files are written with mode 0o600 -- stores may hold API keys.
    """
    data = model.model_dump(exclude_none=exclude_none, mode="json")
    if path.suffix == ".json":
        content = json.dumps(data, indent=2)
    else:
        content = yaml.dump(data, default_flow_style=False, sort_keys=False)
    atomic_write_text(path, content, mode=0o600)
