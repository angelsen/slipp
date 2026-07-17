"""WireGuard peer bootstrap playbook.

Installs WireGuard and brings up a tunnel to an existing wg-manage hub on
a secondary deploy host, and opens a firewall exception scoped to just
the hub's WireGuard IP and the one service port being exposed through it.
Run by services/wg_peer.py's ensure_peer() -- see that module for how the
extra vars this playbook expects (peer_config_path, iface_name,
hub_wg_ip, service_port) are produced.
"""
