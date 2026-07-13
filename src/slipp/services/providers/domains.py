"""Domain registration orchestration."""

from typing import Any


from slipp import output
from slipp.services.providers.gigahost import GigahostClient
from slipp.utils.errors import DomainRegistrationError, ProviderError


def register_domain_interactive(client: GigahostClient, domain: str) -> dict[str, Any]:
    """Prompt for registrant info and register a .no domain.

    Raises:
        DomainRegistrationError: If the registration API call fails.
    """
    registrant_type = output.prompt(
        "Registrant type (organization/person)", default="organization"
    )
    email = output.prompt("Contact email")
    zip_code = output.prompt("Zip code")
    city = output.prompt("City")

    extra: dict[str, Any] = {}
    if registrant_type == "organization":
        org_number = output.prompt("Organization number (9 digits)")
        try:
            org = client.lookup_organization(org_number)
        except ProviderError as e:
            raise DomainRegistrationError(f"Organization lookup failed: {e}") from e

        company_name = org.get("company_name", "")
        if company_name:
            output.info(f"Found: {company_name}")
        applicant_name = output.prompt("Applicant name", default=company_name or "")
        zip_code = org.get("zip_code") or zip_code
        city = org.get("city") or city
        extra = {"org_number": org_number, "company_name": company_name}
    else:
        first_name = output.prompt("First name")
        last_name = output.prompt("Last name")
        pid = output.prompt("Personal ID (format: N.PRI.12345678)")
        applicant_name = f"{first_name} {last_name}"
        extra = {"pid": pid, "first_name": first_name, "last_name": last_name}

    try:
        return client.register_domain(
            domain_name=domain,
            registrant_type=registrant_type,
            email=email,
            applicant_name=applicant_name,
            zip_code=zip_code,
            city=city,
            **extra,
        )
    except ProviderError as e:
        raise DomainRegistrationError(f"Failed to register {domain}: {e}") from e


def ensure_domain_registered(client: GigahostClient, domain: str) -> None:
    """Register `domain` if available; no-op if it's already registered.

    Raises:
        DomainRegistrationError: If the domain is taken by someone else, or
            registration fails.
    """
    available, reason = client.check_domain(domain)

    if available:
        register_domain_interactive(client, domain)
        output.success(f"Registered {domain}")
    elif client.find_zone(domain):
        output.info(f"{domain} already registered")
    else:
        raise DomainRegistrationError(
            f"{domain} is not available" + (f": {reason}" if reason else "")
        )
