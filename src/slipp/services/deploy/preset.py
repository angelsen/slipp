"""Tag-preset resolution for the deploy command."""

from slipp import output
from slipp.constants import DEFAULT_ENV
from slipp.services.config import PresetResolver, parse_preset_args
from slipp.utils.errors import PresetNotFoundError


def resolve_environment_and_tags(
    target: str,
    preset: str | None,
    tags: str | None,
    skip_tags: str | None,
) -> tuple[str, str | None, str | None]:
    """Resolve environment and tags/skip-tags from target, preset, and tag presets.

    `target` is either an environment name or (if it matches a configured
    preset) a preset name used with the default environment. `preset` is an
    explicit preset name passed as a second positional argument.

    Args:
        target: Environment name or tag preset name.
        preset: Explicit tag preset name, if given.
        tags: CLI --tags override.
        skip_tags: CLI --skip-tags override.

    Returns:
        Tuple of (environment, tags, skip_tags), with preset values merged
        in wherever the corresponding CLI flag wasn't explicitly set.

    Raises:
        PresetNotFoundError: If preset is given but not found.
    """
    presets = PresetResolver().list_presets()

    if preset:
        environment = target
        if preset not in presets:
            message = f"Preset '{preset}' not found"
            if presets:
                message += f"\nAvailable presets: {', '.join(presets.keys())}"
            raise PresetNotFoundError(message)
        preset_tags, preset_skip_tags = parse_preset_args(presets[preset])
        output.info(f"Using preset '{preset}': {presets[preset]}")
    elif target != DEFAULT_ENV and target in presets:
        environment = DEFAULT_ENV
        preset_tags, preset_skip_tags = parse_preset_args(presets[target])
        output.info(f"Using preset '{target}': {presets[target]}")
    else:
        environment = target
        preset_tags, preset_skip_tags = None, None

    if preset_tags and not tags:
        tags = preset_tags
    if preset_skip_tags and not skip_tags:
        skip_tags = preset_skip_tags

    return environment, tags, skip_tags
