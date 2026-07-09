"""Ansible subprocess wrapper services.

This package provides services for running Ansible commands.
"""

from slipp.services.ansible.ansible import (
    AnsibleResult,
    become_password_file,
    ensure_requirements_installed,
    get_host_group,
    parse_playbook_progress,
    run_inventory,
    run_list_tasks,
    run_playbook,
    syntax_check,
)

__all__ = [
    "AnsibleResult",
    "become_password_file",
    "ensure_requirements_installed",
    "get_host_group",
    "parse_playbook_progress",
    "run_inventory",
    "run_list_tasks",
    "run_playbook",
    "syntax_check",
]
