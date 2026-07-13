"""DNS provider protocol, shared wire models, and sync logic.

The DNSProvider Protocol is the one capability every future provider
(Gigahost today, Cloudflare later) is expected to implement. Everything
else provider-specific stays out of this module.
"""

from typing import Protocol

from pydantic import BaseModel, Field

from slipp import output


class DNSZone(BaseModel):
    """A DNS zone (domain) managed by a provider.

    Attributes:
        zone_id: Provider-specific zone identifier
        name: Zone/domain name (e.g. "example.no")
        record_count: Number of records in the zone
    """

    zone_id: str
    name: str
    record_count: int = 0


class DNSRecord(BaseModel):
    """A single DNS record.

    Attributes:
        record_id: Provider-specific record identifier (empty until created)
        name: Record name ("@", "www", "app", etc.)
        type: Record type (A, AAAA, CNAME, MX, TXT, ...)
        value: Record value (IP address or target)
        ttl: Time-to-live in seconds
        priority: Priority (required for MX records)
    """

    record_id: str = ""
    name: str
    type: str
    value: str
    ttl: int = 3600
    priority: int | None = Field(default=None)


class DNSProvider(Protocol):
    """Capability shared by every DNS-capable provider."""

    def list_zones(self) -> list[DNSZone]:
        """List all zones managed by this provider account."""
        ...

    def list_records(self, zone_id: str) -> list[DNSRecord]:
        """List all records in a zone."""
        ...

    def create_record(self, zone_id: str, record: DNSRecord) -> DNSRecord:
        """Create a new record in a zone."""
        ...

    def update_record(self, zone_id: str, record: DNSRecord) -> DNSRecord:
        """Update an existing record (record.record_id must be set)."""
        ...

    def find_zone(self, domain: str) -> DNSZone | None:
        """Find the zone managing a domain, or None if not found."""
        ...

    def create_zone(self, domain: str) -> DNSZone:
        """Create a zone for a domain."""
        ...


def sync_dns(provider: DNSProvider, domain: str, target_ip: str) -> list[str]:
    """Converge zone + root A record for domain -> target_ip.

    Additive only: creates a missing zone, creates a missing "@" A record,
    updates a stale one, and never deletes or touches any other record.

    Args:
        provider: DNS-capable provider client
        domain: Domain whose root A record should point at target_ip
        target_ip: Desired IPv4 address

    Returns:
        Human-readable list of actions taken (empty if already correct)
    """
    zone = provider.find_zone(domain)
    if zone is None:
        output.info(f"Creating zone {domain}...")
        zone = provider.create_zone(domain)

    records = provider.list_records(zone.zone_id)
    existing_a = [r for r in records if r.type == "A" and r.name == "@"]

    if not existing_a:
        provider.create_record(
            zone.zone_id, DNSRecord(name="@", type="A", value=target_ip)
        )
        return [f"Created A record: {domain} -> {target_ip}"]

    current = existing_a[0]
    if current.value != target_ip:
        updated = current.model_copy(update={"value": target_ip})
        provider.update_record(zone.zone_id, updated)
        return [f"Updated A record: {domain} -> {target_ip} (was {current.value})"]

    return []
