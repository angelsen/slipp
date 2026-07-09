"""Playbook validation, requirements install, and execution for deploy."""

from contextlib import ExitStack
from pathlib import Path

from slipp import output
from slipp.constants import DEFAULT_GALAXY_PATH
from slipp.output import format_path
from slipp.services.ansible import (
    AnsibleResult,
    become_password_file,
    ensure_requirements_installed,
    parse_playbook_progress,
    run_playbook,
)
from slipp.services.config import ConfigResolver, InventoryService, ResolvedConfig
from slipp.services.vault import has_vault_content
from slipp.services.vault import vault_password_file as get_vault_password_file
from slipp.utils.errors import ConfigError, InventoryParseError


def validate_deploy_files(
    config: ResolvedConfig,
    resolver: ConfigResolver,
    cli_inventory: str | None,
    cli_playbook: str | None,
) -> tuple[bool, str | None]:
    """Validate that the resolved inventory/playbook exist, and check for a vault.

    Args:
        config: Resolved deploy configuration.
        resolver: Config resolver, for project_root and has_local_config.
        cli_inventory: CLI --inventory override (used only to decide info messages).
        cli_playbook: CLI --playbook override (used only to decide info messages).

    Returns:
        Tuple of (needs_vault_password, vault_file_path_or_None).

    Raises:
        ConfigError: If the inventory or playbook file doesn't exist.
    """
    inventory_file = str(config.inventory)
    playbook_file = str(config.playbook)
    project_root = resolver.project_root

    if not cli_inventory and config.inventory_source == "local":
        output.info(
            f"Using inventory from slipp.yaml: {format_path(inventory_file, project_root)}"
        )
    if not cli_playbook and config.playbook_source == "local":
        output.info(
            f"Using playbook from slipp.yaml: {format_path(playbook_file, project_root)}"
        )

    if not Path(inventory_file).exists():
        message = (
            f"Inventory file not found: {format_path(inventory_file, project_root)}"
        )
        if not resolver.has_local_config:
            message += (
                "\nRun 'slipp projects add <name> -i <inventory>' to configure project"
            )
        raise ConfigError(message)

    if not Path(playbook_file).exists():
        raise ConfigError(
            f"Playbook file not found: {format_path(playbook_file, project_root)}"
        )

    try:
        parsed_inventory = InventoryService.parse(Path(inventory_file))
    except InventoryParseError as e:
        # ansible-inventory can legitimately fail without a password on
        # whole-file-vault-encrypted host_vars/group_vars, so a parse
        # failure here is a warning, not a hard stop -- the real check is
        # the empty-hosts case below, which is what a malformed inventory
        # file actually produces (ansible-playbook silently no-ops on it).
        output.warning(f"Could not pre-validate inventory: {e}")
        parsed_inventory = None

    if parsed_inventory is not None and not parsed_inventory.hosts:
        raise ConfigError(
            f"Inventory contains no hosts: {format_path(inventory_file, project_root)}\n"
            f"The file may be malformed. Check: ansible-inventory -i {inventory_file} --list"
        )

    inventory_dir = Path(inventory_file).parent
    needs_vault_password = has_vault_content(inventory_dir)

    vault_file: str | None = None
    if config.vault:
        vault_path = config.vault
        if vault_path.exists():
            vault_file = str(vault_path)
            needs_vault_password = True
        else:
            output.warning(
                f"Vault file not found: {format_path(vault_path, project_root)}"
            )

    return needs_vault_password, vault_file


def install_galaxy_requirements(
    requirements: str | None,
    galaxy_path: str | None,
    force: bool,
    log_dir: Path,
) -> None:
    """Install ansible-galaxy role and collection requirements if requirements.yml exists.

    Args:
        requirements: Path to requirements.yml (defaults to "requirements.yml").
        galaxy_path: Install path for external roles (defaults to "roles/galaxy").
        force: Force reinstall even if roles/collections are already present.
        log_dir: Directory for install logs.

    Raises:
        AnsibleError: If install fails.
    """
    reqs_file = requirements or "requirements.yml"
    if not Path(reqs_file).exists():
        return

    ensure_requirements_installed(
        reqs_file, galaxy_path or DEFAULT_GALAXY_PATH, log_dir=log_dir, force=force
    )


def execute_playbook(
    playbook_file: str,
    inventory_file: str,
    *,
    dry_run: bool,
    vault_file: str | None,
    needs_vault_password: bool,
    tags: str | None,
    skip_tags: str | None,
    roles_paths: list[str] | None,
    log_dir: Path,
    ask_become_pass: bool = False,
) -> AnsibleResult:
    """Run ansible-playbook, prompting for the vault/become password first if needed.

    Both prompts run before the spinner starts, so the terminal is clean
    for interactive input.

    Args:
        playbook_file: Path to playbook.yml.
        inventory_file: Path to inventory file.
        dry_run: If True, run in --check mode.
        vault_file: Path to vault file to pass as extra-vars, if any.
        needs_vault_password: Whether to prompt for the vault password.
        tags: Ansible tags to run.
        skip_tags: Ansible tags to skip.
        roles_paths: Role search directories.
        log_dir: Directory for playbook run logs.
        ask_become_pass: Whether to prompt for the sudo/become password
            (needed when the target host's sudo isn't passwordless).

    Returns:
        AnsibleResult with exit_code and log_path.
    """
    with ExitStack() as stack:
        vault_pw_file = (
            stack.enter_context(get_vault_password_file(confirm=False))
            if needs_vault_password
            else None
        )
        become_pw_file = (
            stack.enter_context(become_password_file()) if ask_become_pass else None
        )

        with output.spinner("Running playbook", spinner_type="earth") as update:

            def on_progress(line: str) -> None:
                label = parse_playbook_progress(line)
                if label:
                    update(label[:60])

            result = run_playbook(
                playbook_file,
                inventory_file,
                check=dry_run,
                vault_file=vault_file,
                vault_password_file=vault_pw_file,
                become_pw_file=become_pw_file,
                tags=tags,
                skip_tags=skip_tags,
                roles_path=roles_paths if roles_paths else None,
                log_dir=log_dir,
                on_progress=on_progress,
            )

    if result.exit_code != 0:
        output.error("Running playbook failed")
        if result.log_path:
            output.hint(f"See log: {result.log_path}")

    return result
