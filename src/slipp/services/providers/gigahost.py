"""Gigahost API client -- httpx wrapper for the endpoints slipp uses.

Single class covering account/SSH-key, DNS, domain, server, and deploy
operations. Everything else in the ~110-endpoint Gigahost API (webhosting,
BGP, sub-clients, ...) is out of scope for slipp.
"""

from typing import Any

import httpx

from slipp.services.providers.dns import DNSRecord, DNSZone
from slipp.services.providers.http import ApiClientMixin
from slipp.utils.errors import ProviderError


class GigahostClient(ApiClientMixin):
    """Synchronous Gigahost API client.

    Implements the DNSProvider protocol (list_zones, list_records,
    create_record, update_record, find_zone) so it can be used anywhere
    a DNSProvider is expected.
    """

    BASE_URL = "https://api.gigahost.no/api/v0"
    PROVIDER_NAME = "Gigahost"

    def __init__(self, api_key: str):
        """Initialize with a flux_live_* personal API key."""
        self._client = httpx.Client(
            base_url=self.BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )

    # --- Account ---

    def get_account(self) -> dict[str, Any]:
        """GET /account -- the authenticated account, including sshkeys[]."""
        return self._request_data("GET", "/account", default={})

    def add_ssh_key(self, name: str, public_key: str) -> dict[str, Any]:
        """POST /account/sshkey -- add an SSH public key to the account."""
        return self._request_data(
            "POST",
            "/account/sshkey",
            json={"name": name, "data": public_key},
            default={},
        )

    # --- DNS (implements DNSProvider protocol) ---

    def list_zones(self) -> list[DNSZone]:
        """GET /dns/zones."""
        data = self._request_data("GET", "/dns/zones", default=[])
        return [self._zone_from_dict(z) for z in data]

    def list_records(self, zone_id: str) -> list[DNSRecord]:
        """GET /dns/zones/{zone_id}/records."""
        data = self._request_data("GET", f"/dns/zones/{zone_id}/records", default=[])
        return [self._record_from_dict(r) for r in data]

    def create_record(self, zone_id: str, record: DNSRecord) -> DNSRecord:
        """POST /dns/zones/{zone_id}/records.

        Unlike create_zone(), the create response never echoes the created
        record back at all -- confirmed live: `data: []` on every call,
        regardless of success. The only way to get its record_id is a
        follow-up list_records() call matched by name/type/value.
        """
        self._request(
            "POST",
            f"/dns/zones/{zone_id}/records",
            json=self._record_payload(record),
        )
        for entry in self.list_records(zone_id):
            if (
                entry.name == record.name
                and entry.type == record.type
                and entry.value == record.value
            ):
                return entry

        raise ProviderError(
            f"{self.PROVIDER_NAME} did not return the created record for "
            f"{record.name} ({record.type})"
        )

    def update_record(self, zone_id: str, record: DNSRecord) -> DNSRecord:
        """PUT /dns/zones/{zone_id}/records/{record_id}."""
        self._request(
            "PUT",
            f"/dns/zones/{zone_id}/records/{record.record_id}",
            json=self._record_payload(record),
        )
        return record

    def find_zone(self, domain: str) -> DNSZone | None:
        """Match domain (case/trailing-dot insensitive) against the zone list."""
        domain_norm = domain.lower().rstrip(".")
        for zone in self.list_zones():
            if zone.name.lower().rstrip(".") == domain_norm:
                return zone
        return None

    def create_zone(self, domain: str) -> DNSZone:
        """POST /dns/zones -- create a new (unregistered) DNS zone.

        Like GET /dns/zones, this wraps its payload as `data: [...]` (a list)
        rather than a bare object, even though it creates a single zone -
        unwrap the same way list_zones() does instead of assuming a dict.
        """
        data = self._request_data(
            "POST",
            "/dns/zones",
            json={"zone_name": domain, "create_default_records": False},
            default=[],
        )
        entries = data if isinstance(data, list) else [data]
        for entry in entries:
            if entry.get("zone_name", "").lower().rstrip(".") == domain.lower().rstrip(
                "."
            ):
                return self._zone_from_dict(entry)

        raise ProviderError(
            f"{self.PROVIDER_NAME} did not return the created zone for {domain}"
        )

    @staticmethod
    def _zone_from_dict(data: dict[str, Any]) -> DNSZone:
        return DNSZone(
            zone_id=str(data["zone_id"]),
            name=data["zone_name"],
            record_count=data.get("record_count", 0),
        )

    @staticmethod
    def _record_from_dict(data: dict[str, Any]) -> DNSRecord:
        return DNSRecord(
            record_id=str(data["record_id"]),
            name=data["record_name"],
            type=data["record_type"],
            value=data["record_value"],
            ttl=data.get("record_ttl", 3600),
            priority=data.get("record_priority"),
        )

    @staticmethod
    def _record_payload(record: DNSRecord) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "record_value": record.value,
            "record_name": record.name,
            "record_type": record.type,
            "record_ttl": record.ttl,
        }
        if record.priority is not None:
            payload["record_priority"] = record.priority
        return payload

    # --- Domains ---

    def check_domain(self, domain: str) -> tuple[bool, str]:
        """GET /dns/domains/check/{domain} -- .no availability check."""
        data = self._request_data("GET", f"/dns/domains/check/{domain}", default={})
        return bool(data.get("available", False)), data.get("reason", "")

    def register_domain(
        self,
        domain_name: str,
        registrant_type: str,
        email: str,
        applicant_name: str,
        zip_code: str,
        city: str,
        *,
        org_number: str | None = None,
        company_name: str | None = None,
        pid: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> dict[str, Any]:
        """POST /dns/domains/register -- register a .no domain.

        Args:
            registrant_type: "organization" or "person"
            org_number, company_name: required when registrant_type is "organization"
            pid, first_name, last_name: required when registrant_type is "person"
        """
        payload: dict[str, Any] = {
            "domain_name": domain_name,
            "registrant_type": registrant_type,
            "email": email,
            "applicant_name": applicant_name,
            "zip_code": zip_code,
            "city": city,
            "use_gigahost_ns": True,
        }
        if registrant_type == "organization":
            payload["org_number"] = org_number
            payload["company_name"] = company_name
        else:
            payload["pid"] = pid
            payload["first_name"] = first_name
            payload["last_name"] = last_name

        return self._request_data(
            "POST", "/dns/domains/register", json=payload, default={}
        )

    def lookup_organization(self, org_number: str) -> dict[str, Any]:
        """GET /dns/lookup/organization/{org_number}."""
        return self._request_data(
            "GET", f"/dns/lookup/organization/{org_number}", default={}
        )

    # --- Servers ---

    def list_servers(self) -> list[dict[str, Any]]:
        """GET /servers."""
        return self._request_data("GET", "/servers", default=[])

    def get_powerstate(self, server_id: int) -> bool:
        """GET /servers/{id}/powerstate -- powerstate lives in `meta`, not `data`."""
        result = self._request("GET", f"/servers/{server_id}/powerstate")
        return bool(result.get("meta", {}).get("powerstate", False))

    def reboot(self, server_id: int) -> None:
        """GET /servers/{id}/reboot (API quirk: power ops use GET, not POST)."""
        self._request("GET", f"/servers/{server_id}/reboot")

    def reinstall_server(
        self,
        server_id: int,
        os_id: int,
        *,
        hostname: str = "",
        key_id: int | None = None,
    ) -> dict[str, Any]:
        """POST /servers/{id}/reinstall.

        Args:
            key_id: SSH key ID from account (param name discovered from web UI).

        Returns:
            The meta dict (contains root_passwd if no SSH key, sshkey bool).
        """
        payload: dict[str, Any] = {
            "os_id": str(os_id),
            "language": "en_US",
            "keyboard": "us",
            "timezone": "Europe/Oslo",
            "hostname": hostname or f"srv{server_id}",
        }
        if key_id is not None:
            payload["key_id"] = str(key_id)

        result = self._request("POST", f"/servers/{server_id}/reinstall", json=payload)
        return result.get("meta", {})

    # --- Deploy ---

    def get_catalog(self) -> dict[str, Any]:
        """GET /deploy/servers -- the deployable product/region catalog."""
        return self._request_data("GET", "/deploy/servers", default={})

    def deploy_server(
        self,
        product_id: int,
        price_id: int,
        region_id: int,
        *,
        os_id: int | None = None,
        billing_period: str = "hourly",
        hostnames: list[str] | None = None,
        ssh_keys: list[int] | None = None,
    ) -> list[int]:
        """POST /deploy/servers -- order a server.

        Returns:
            List of order IDs (poll with get_deploy_status). Always a single
            ID -- get_deploy_status/_poll_and_wait only handle one server.
        """
        payload: dict[str, Any] = {
            "pid": product_id,
            "price_id": price_id,
            "region_id": region_id,
            "billing_period": billing_period,
            "quantity": 1,
        }
        if os_id is not None:
            payload["os_id"] = os_id
        if hostnames:
            payload["hostnames"] = hostnames
        if ssh_keys:
            payload["ssh_keys"] = ssh_keys

        data = self._request_data("POST", "/deploy/servers", json=payload, default={})
        return data.get("order_ids", [])

    def get_deploy_status(self, order_ids: list[int]) -> dict[str, Any]:
        """GET /deploy/status?ids=1,2,3.

        Returns:
            Dict with `servers` (list) and `all_ready` (bool).
        """
        ids = ",".join(str(i) for i in order_ids)
        return self._request_data(
            "GET", "/deploy/status", params={"ids": ids}, default={}
        )

    def list_distros(self) -> list[dict[str, Any]]:
        """GET /reinstall/distro."""
        return self._request_data("GET", "/reinstall/distro", default=[])

    def list_os_versions(self, distro_id: int) -> list[dict[str, Any]]:
        """GET /reinstall/distro/{id}."""
        return self._request_data("GET", f"/reinstall/distro/{distro_id}", default=[])
