"""Playbook validation, requirements install, and execution for deploy."""

from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path

import yaml

from slipp import output
from slipp.models.deployment import DeploymentHostConfig
from slipp.models.local_config import resolve_service_host
from slipp.services import wg_peer
from slipp.services.ansible import (
    AnsibleResult,
    ensure_requirements_installed,
    run_playbook_with_spinner,
)
from slipp.services.config import (
    ConfigResolver,
    LocalConfigService,
    ResolvedConfig,
    is_wg_manage_host,
    load_full_inventory,
    load_primary_host,
    parse_inventory,
)
from slipp.services.config.detection import has_caddy_role
from slipp.services.deploy.config import (
    DeployOverrides,
    ensure_project_registered,
    persist_config_updates,
)
from slipp.services.deploy.dev_proxy_guard import guard_against_dev_proxy_collision
from slipp.services.vault import has_vault_content
from slipp.services.vault import vault_password_file as get_vault_password_file
from slipp.utils.errors import (
    ConfigError,
    DeployError,
    InventoryParseError,
    WgManageError,
)
from slipp.utils.files import get_log_dir
from slipp.utils.network import format_app_url


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
            f"Using inventory from slipp.yaml: {output.format_path(inventory_file, project_root)}"
        )
    if not cli_playbook and config.playbook_source == "local":
        output.info(
            f"Using playbook from slipp.yaml: {output.format_path(playbook_file, project_root)}"
        )

    if not Path(inventory_file).exists():
        message = f"Inventory file not found: {output.format_path(inventory_file, project_root)}"
        if not resolver.has_local_config:
            message += (
                "\nRun 'slipp projects add <name> -i <inventory>' to configure project"
            )
        raise ConfigError(message)

    if not Path(playbook_file).exists():
        raise ConfigError(
            f"Playbook file not found: {output.format_path(playbook_file, project_root)}"
        )

    try:
        parsed_inventory = parse_inventory(Path(inventory_file))
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
            f"Inventory contains no hosts: {output.format_path(inventory_file, project_root)}\n"
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
                f"Vault file not found: {output.format_path(vault_path, project_root)}"
            )

    return needs_vault_password, vault_file


def install_galaxy_requirements(
    requirements: str | None,
    galaxy_path: str,
    force: bool,
    log_dir: Path,
    project_root: Path,
) -> None:
    """Install ansible-galaxy role and collection requirements if requirements.yml exists.

    Args:
        requirements: Path to requirements.yml (defaults to "requirements.yml").
        galaxy_path: Install path for external roles.
        force: Force reinstall even if roles/collections are already present.
        log_dir: Directory for install logs.
        project_root: Root to resolve a relative requirements path against.

    Raises:
        AnsibleError: If install fails.
    """
    reqs_file = project_root / (requirements or "requirements.yml")
    if not reqs_file.exists():
        return

    ensure_requirements_installed(
        str(reqs_file), galaxy_path, log_dir=log_dir, force=force
    )


def _load_service_ports(inventory_file: str) -> dict[str, int]:
    """Best-effort read of each service's own port from generated group_vars/all.yml.

    group_vars/all.yml sits next to the inventory file (Ansible's own
    resolution convention -- see validate_deploy_files()'s inventory_dir)
    and is the only place a service's port survives past launch time;
    DetectedService itself isn't persisted anywhere deploy-time code reads
    from. Returns {} if the file is missing or unparseable (an external/
    non-slipp-launched project) -- callers treat that as "nothing to
    bootstrap" rather than failing the whole deploy over a best-effort read.
    """
    group_vars_path = Path(inventory_file).parent / "group_vars" / "all.yml"
    try:
        data = yaml.safe_load(group_vars_path.read_text()) or {}
    except Exception:
        return {}

    services = data.get("services")
    if not isinstance(services, list):
        return {}

    return {
        s["name"]: s["port"]
        for s in services
        if isinstance(s, dict)
        and isinstance(s.get("name"), str)
        and isinstance(s.get("port"), int)
    }


def bootstrap_wg_manage_peers(
    project_root: Path, inventory_file: str, host: DeploymentHostConfig | None
) -> None:
    """Bootstrap every secondary host with an assigned service as a WireGuard peer.

    No-op for anything but a `--proxy wg-manage` project (host.proxy_owner
    == "wg-manage") -- core multi-host under any other proxy mode has no
    wg-manage dependency at all. Must run before execute_playbook(): the
    generated playbook's `wg-manage service add <peer>:<port>` call
    resolves the peer name eagerly, at add-time, so every referenced peer
    must already exist on the hub by the time the playbook runs.

    Args:
        project_root: Project root (for slipp.yaml's expose: block).
        inventory_file: Resolved inventory.yml path (for both the full
            per-host inventory and, indirectly, group_vars/all.yml).
        host: The project's primary host, if already loaded by the
            caller (run_deploy() already loads one for the dev-proxy
            collision guard) -- avoids a second raw inventory read.

    Raises:
        WgManageError: If any peer's bootstrap fails (see
            wg_peer.ensure_peer()), or slipp.yaml's expose: block
            references a host absent from inventory.yml (should already
            have been caught at launch time -- this is a defensive
            fail-loud check against drift since then, not the primary
            enforcement point).
    """
    if not is_wg_manage_host(host):
        return
    assert host is not None  # is_wg_manage_host() already narrows this

    inventory = load_full_inventory(project_root)
    if inventory is None:
        return

    local_config = LocalConfigService.load(project_root)
    declared_expose = (
        local_config.expose if local_config and local_config.expose else {}
    )

    ports_by_host: dict[str, list[int]] = {}
    for service_name, port in _load_service_ports(inventory_file).items():
        host_name = resolve_service_host(
            service_name, declared_expose, host.inventory_hostname
        )
        if host_name != host.inventory_hostname:
            ports_by_host.setdefault(host_name, []).append(port)

    for host_name, ports in ports_by_host.items():
        peer = inventory.hosts.get(host_name)
        if peer is None:
            raise WgManageError(
                f"expose[*].host references unknown host '{host_name}' "
                f"(known hosts: {', '.join(sorted(inventory.hosts)) or 'none'}) "
                "-- run 'slipp launch --reconfigure' or fix slipp.yaml"
            )
        wg_peer.ensure_peer(hub=host, peer=peer, ports=ports)


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
        result = run_playbook_with_spinner(
            playbook_file,
            inventory_file,
            label="Running playbook",
            spinner_type="earth",
            ask_become_pass=ask_become_pass,
            check=dry_run,
            vault_file=vault_file,
            vault_password_file=vault_pw_file,
            tags=tags,
            skip_tags=skip_tags,
            roles_path=roles_paths if roles_paths else None,
            log_dir=log_dir,
        )

    if result.exit_code != 0:
        output.error("Running playbook failed")
        if result.log_path:
            output.hint(f"See log: {result.log_path}")

    return result


@dataclass
class DeployResult:
    """Outcome of a full run_deploy() call."""

    exit_code: int
    log_dir: Path
    app_url: str | None


def run_deploy(
    project_root: Path,
    project_name: str,
    environment: str,
    tags: str | None,
    skip_tags: str | None,
    *,
    overrides: DeployOverrides,
    cli_name: str | None = None,
    requirements: str | None = None,
    dry_run: bool = False,
    force_requirements: bool = False,
    ask_become_pass: bool = False,
) -> DeployResult:
    """Resolve config, run the playbook, and apply post-deploy bookkeeping.

    Shared orchestrator for `slipp deploy` and `slipp up`'s final deploy
    step, so the two commands can't drift on what a deploy actually does.

    On success (excluding a dry run), persists CLI flag overrides into
    slipp.yaml (unless --name already handled config creation), registers
    the project in the global registry, and ensures logs are gitignored. A
    dry run never persists these side effects.
    wg-manage exposure sync is intentionally NOT done here -- it depends on
    command-layer helpers (resolve_project_dirs/resolve_declared_dirs) that
    services must not import; callers should run it themselves after a
    successful, non-dry-run deploy.

    Args:
        project_root: Root the deploy resolves config against.
        project_name: Resolved project name (for registry + wg-manage sync).
        environment: Ansible inventory environment/group to target.
        tags: Ansible tags to run.
        skip_tags: Ansible tags to skip.
        cli_name: Raw --name flag, if given (suppresses config persistence,
            since --name already created/updated slipp.yaml separately).
        overrides: CLI flag overrides (inventory/playbook/roles/vault/
            galaxy_path/runtime).
        requirements: --requirements override.
        dry_run: Run ansible-playbook in --check mode.
        force_requirements: Force reinstall galaxy roles/collections.
        ask_become_pass: Prompt for the sudo/become password.

    Returns:
        DeployResult with the playbook's exit code (0 on success), the log
        directory, and the app URL hint (if the host declares app_domain).

    Raises:
        ConfigError: If the resolved inventory/playbook doesn't exist.
        DeployError: If the playbook matched no hosts (exit 0 is otherwise
            indistinguishable from a real, effective deploy), or if this is
            a Caddy-fronted project and the target host already runs the
            dev proxy (see guard_against_dev_proxy_collision).
    """
    resolver = ConfigResolver(project_root)
    config = resolver.resolve(
        cli_inventory=overrides.inventory,
        cli_playbook=overrides.playbook,
        cli_roles=overrides.roles,
        cli_vault=overrides.vault,
        cli_galaxy_path=overrides.galaxy_path,
        environment=environment,
    )

    inventory_file = str(config.inventory)
    playbook_file = str(config.playbook)
    roles_paths = [str(r) for r in config.roles_path]

    galaxy_path = str(config.galaxy_path)
    if galaxy_path not in roles_paths:
        roles_paths.append(galaxy_path)

    needs_vault_password, vault_file = validate_deploy_files(
        config, resolver, overrides.inventory, overrides.playbook
    )

    host = load_primary_host(project_root)
    guard_against_dev_proxy_collision(project_root, host)

    log_dir = get_log_dir(project_root)
    install_galaxy_requirements(
        requirements, galaxy_path, force_requirements, log_dir, project_root
    )

    # Must run before execute_playbook() -- the generated playbook's
    # `wg-manage service add <peer>:<port>` call resolves the peer name
    # eagerly, at add-time, so every secondary-host peer this project
    # references must already exist on the hub first. Skipped under
    # --dry-run: unlike execute_playbook()'s --check mode, ensure_peer()
    # has no dry-run of its own -- it's a real SSH mutation against the
    # hub (and the peer, on first bootstrap), not something ansible-playbook
    # --check can safely preview.
    if not dry_run:
        bootstrap_wg_manage_peers(project_root, inventory_file, host)
    elif is_wg_manage_host(host):
        output.info("Dry run: skipping WireGuard peer bootstrap")

    result = execute_playbook(
        playbook_file,
        inventory_file,
        dry_run=dry_run,
        vault_file=vault_file,
        needs_vault_password=needs_vault_password,
        tags=tags,
        skip_tags=skip_tags,
        roles_paths=roles_paths,
        log_dir=log_dir,
        ask_become_pass=ask_become_pass,
    )

    if result.exit_code == 0 and result.no_hosts_matched:
        raise DeployError(
            "Playbook matched no hosts "
            "(check the playbook's 'hosts:' pattern against your inventory groups)",
            log_dir=log_dir,
        )

    if result.exit_code != 0:
        return DeployResult(exit_code=result.exit_code, log_dir=log_dir, app_url=None)

    app_url = None
    if host and host.app_domain:
        # app_port only matters for --proxy none deploys; a Caddy-fronted
        # domain already implies :80/:443.
        app_url = format_app_url(
            host.app_domain,
            has_caddy=has_caddy_role(project_root),
            port=host.app_port,
        )

    if overrides.any_set() and not dry_run and not cli_name:
        persist_config_updates(overrides, project_root)

    if not dry_run:
        ensure_project_registered(project_name, project_root)
        LocalConfigService.ensure_logs_gitignore(project_root)

    return DeployResult(exit_code=0, log_dir=log_dir, app_url=app_url)
