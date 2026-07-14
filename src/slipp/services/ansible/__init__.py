"""Ansible subprocess wrapper services.

This package provides services for running Ansible commands.
"""

from slipp.services.ansible.ansible import (
    AnsibleResult,
    ensure_requirements_installed,
    get_host_group,
    maybe_become_password_file,
    run_inventory,
    run_list_tasks,
    run_playbook,
    spinner_progress_callback,
    syntax_check,
)

__all__ = [
    "AnsibleResult",
    "ensure_requirements_installed",
    "get_host_group",
    "maybe_become_password_file",
    "run_inventory",
    "run_list_tasks",
    "run_playbook",
    "spinner_progress_callback",
    "syntax_check",
]
