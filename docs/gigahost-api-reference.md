Here is the comprehensive structured summary of the Gigahost API (v0).

---

## General Information

- **Base URL:** `https://api.gigahost.no/api/v0`
- **API Version:** 0
- **Content-Type:** All PUT/POST requests must be JSON-encoded
- **Authentication:** Bearer token via `/authenticate`, HTTP Basic Auth, or personal API key (`flux_live_<hex>`)
- **Auth header:** `Authorization: Bearer {token}` or `Authorization: Basic base64(username:password)`

---

## 1. AUTHENTICATION

### POST /authenticate

- **Description:** Authenticate and receive a Bearer token.
- **Parameters:**
  - `username` (string, required)
  - `password` (string, required)
  - `code` (numeric, optional) -- needed if 2FA is enabled
- **Response fields:** `data.token`, `data.token_expire` (unix timestamp), `data.customer_id`
- **Notes:** HTTP Basic Auth is also supported on all endpoints. For unattended integrations, use a personal API key (`flux_live_<hex>`) instead of a session token.

---

## 2. BGP

### GET /bgp

- **Description:** Get all BGP data (ASNs, prefix lists, sessions).
- **Parameters:** none
- **Response fields:** `data.asn[]` (with `id`, `asn`, `asn_name`, `asn_country`, `irr_v4`, `irr_v6`, `irr_updated`, `status`, `rejected_reason`), `data.prefix_lists[]` (with `id`, `asn_id`, `prefix`, `prefix_type`, `status`, `your_asn`, `asn_country`), `data.sessions[]` (with `id`, `asn_id`, `cust_id`, `router_id`, `srv_id`, `ip_id`, `ip_type`, `defaultroute`, `status`, `neighbor_ipv4`, `neighbor_ipv6`, `multihop`, `router_asn`, `your_asn`, `asn_country`, `ip_address`)

### POST /bgp/asn

- **Description:** Submit ASN for approval.
- **Parameters:**
  - `asn` (numeric or string, required) -- e.g. "212345" or "AS212345"
- **Notes:** Max 3 ASNs per customer. Requires verification. Email sent after submission.

### POST /bgp/{asn_id}/session

- **Description:** Create BGP session.
- **Parameters:**
  - `asn_id` (numeric, in URL, required) -- ASN database ID, not the ASN number
  - `redundant` (numeric, required) -- 0 or 1
  - `defaultroute` (numeric, required) -- 0 or 1
  - `ip_id_v4` (numeric, optional) -- IP ID for IPv4 session
  - `ip_id_v6` (numeric, optional) -- IP ID for IPv6 session
- **Notes:** At least one of `ip_id_v4` or `ip_id_v6` must be provided. ASN must be in 'active' status.

### DELETE /bgp/{session_id}/session

- **Description:** Delete BGP session.
- **Parameters:**
  - `session_id` (numeric, in URL, required)
- **Notes:** Session must be in 'active' status. Deletion is asynchronous.

---

## 3. DNS / DOMAINS

### GET /dns/lookup/organization/{org_number}

- **Description:** Lookup Norwegian organization information.
- **Parameters:**
  - `org_number` (numeric, 9 digits, in URL, required)
- **Response fields:** `data.company_name`, `data.address`, `data.zip_code`, `data.city`

### GET /dns/domains/check/{domain}

- **Description:** Check .no domain availability.
- **Parameters:**
  - `domain` (string, in URL, required) -- e.g. "example.no"
- **Response fields:** `data.domain`, `data.available` (boolean), `data.reason`

### GET /dns/zones

- **Description:** List all DNS zones.
- **Parameters:** none
- **Response fields:** `data[]` with `zone_id`, `cust_id`, `zone_name`, `zone_name_display`, `zone_type`, `zone_active`, `zone_protected`, `zone_is_registered`, `domain_registrar`, `domain_status`, `domain_expiry_date`, `domain_auto_renew`, `external_dns`, `record_count`, `zone_updated`

### GET /dns/zones/{zone_id}/records

- **Description:** Get DNS records for a zone.
- **Parameters:**
  - `zone_id` (numeric, in URL, required)
- **Response fields:** `data[]` with `record_id`, `record_name`, `record_type`, `record_value`, `record_ttl`, `record_priority`

### GET /dns/zones/{zone_id}/registrant

- **Description:** Get registrant information for registered domain.
- **Parameters:**
  - `zone_id` (numeric, in URL, required)
- **Response fields:** `data.contact_id`, `data.name`, `data.organization`, `data.email`, `data.address`, `data.city`, `data.postal_code`, `data.country_code`, `data.identity`, `data.identity_type`, `data.type`
- **Notes:** Only available for registered .no domains.

### POST /dns/domains/register

- **Description:** Register a new .no domain.
- **Parameters:**
  - `domain_name` (string, required)
  - `registrant_type` (string, required) -- "organization" or "person"
  - `email` (string, required)
  - `applicant_name` (string, required, max 255 chars)
  - `zip_code` (string, required)
  - `city` (string, required)
  - For organizations: `org_number` (string, 9 digits), `company_name` (string, max 255 chars)
  - For persons: `pid` (string, format: N.PRI.12345678), `first_name` (string), `last_name` (string)
  - `use_gigahost_ns` (boolean, optional, default: true)
  - `nameservers` (array, optional, required if `use_gigahost_ns` is false, min 2)
- **Response fields:** `data.zone_id`, `data.domain_name`, `data.expires_at`, `data.status`

### POST /dns/zones

- **Description:** Create a new DNS zone.
- **Parameters (JSON):**
  - `zone_name` (string, required)
  - `zone_type` (string, optional) -- "NATIVE", "MASTER", or "SLAVE", default: "NATIVE"
  - `create_default_records` (boolean, optional, default: false)
  - `transfer_domain` (boolean, optional, default: false) -- initiate .no domain transfer
  - `auth_code` (string, optional) -- required if `transfer_domain` is true
  - `use_existing_ns` (boolean, optional, default: false)
- **Parameters (multipart/form-data for zone file import):**
  - `zone_name` (string)
  - `zone_file` (file, max 2MB) -- BIND zone file
- **Response fields:** `data.zone_id`
- **Notes:** Supports both JSON and multipart/form-data.

### POST /dns/zones/{zone_id}/records

- **Description:** Create a new DNS record.
- **Parameters:**
  - `zone_id` (numeric, in URL, required)
  - `record_value` (string, required)
  - `record_name` (string, optional, default: "@")
  - `record_type` (string, optional, default: "A") -- A, AAAA, CNAME, MX, TXT, NS, TLSA, etc.
  - `record_ttl` (numeric, optional, default: 3600)
  - `record_priority` (numeric, optional) -- required for MX records

### PUT /dns/zones/{zone_id}/records/{record_id}

- **Description:** Update an existing DNS record.
- **Parameters:**
  - `zone_id` (numeric, in URL, required)
  - `record_id` (string, in URL, required)
  - `record_value` (string, required)
  - `record_name` (string, optional, default: "@")
  - `record_type` (string, optional, default: "A")
  - `record_ttl` (numeric, optional, default: 3600)
  - `record_priority` (numeric, optional) -- for MX records
- **Notes:** Validates IPv4 for A records, IPv6 for AAAA records, requires priority for MX.

### PUT /dns/zones/{zone_id}/registrant

- **Description:** Change domain registrant/owner.
- **Parameters:**
  - `zone_id` (numeric, in URL, required)
  - `registrant_type` (string, required) -- "organization" or "person"
  - `email` (string, required)
  - `applicant_name` (string, required, max 255 chars)
  - `zip_code` (string, required)
  - `city` (string, required)
  - `agree_to_terms` (boolean, required) -- must be true
  - For organizations: `org_number` (string, 9 digits), `company_name` (string, max 255 chars)
  - For persons: `pid` (string, format: N.PRI.XXXXXXXX)
- **Notes:** Creates new order and extends domain by 1 year.

### PUT /dns/zones/{zone_id}/auto-renew

- **Description:** Toggle automatic renewal for domain.
- **Parameters:**
  - `zone_id` (numeric, in URL, required)
  - `auto_renew` (numeric, required) -- 0 or 1
- **Notes:** Only for registered .no domains.

### PUT /dns/zones/{zone_id}/nameservers

- **Description:** Update nameservers for registered domain.
- **Parameters:**
  - `zone_id` (numeric, in URL, required)
  - `nameservers` (array, required) -- minimum 2
- **Notes:** Only for protected zones (registered domains). Verifies nameservers are authoritative. Automatically updates `external_dns` flag.

### DELETE /dns/zones/{zone_id}

- **Description:** Delete a DNS zone.
- **Parameters:**
  - `zone_id` (numeric, in URL, required)
- **Notes:** Protected zones (registered domains) cannot be deleted.

### DELETE /dns/zones/{zone_id}/records/{record_id}

- **Description:** Delete a DNS record.
- **Parameters:**
  - `zone_id` (numeric, in URL, required)
  - `record_id` (string, in URL, required)
  - `name` (string, query parameter, required)
  - `type` (string, query parameter, required)
- **Notes:** Example: `DELETE /dns/zones/123/records/abc123?name=www&type=A`

### GET /dns/zones/{zone_id}/ds-records

- **Description:** Get DS records for DNSSEC.
- **Parameters:**
  - `zone_id` (numeric, in URL, required)
- **Response fields:** `data.ds_records` (string)
- **Notes:** For Gigahost NS returns DS records directly. For external NS returns configuration instructions.

### GET /dns/zones/{zone_id}/ds-records/external

- **Description:** Get stored external DS records.
- **Parameters:**
  - `zone_id` (numeric, in URL, required)
- **Response fields:** `data.ds_records[]` with `keyTag`, `alg`, `digestType`, `digest`
- **Notes:** Only for domains using external nameservers.

### POST /dns/zones/ptr

- **Description:** Create a PTR (reverse DNS) zone.
- **Parameters:**
  - `prefix` (string, required) -- e.g. "185.181.63" or "2a03:94e0::"
  - `ip_version` (string, required) -- "ipv4" or "ipv6"
  - `zone_name` (string, required) -- PTR zone name, e.g. "63.181.185.in-addr.arpa"
- **Response fields:** `data.zone_id`

### POST /dns/zones/{zone_id}/ds-records/external

- **Description:** Submit external DS records to Norid.
- **Parameters:**
  - `zone_id` (numeric, in URL, required)
  - `ds_records` (array, required) -- array of objects with:
    - `keyTag` (numeric, 0-65535)
    - `alg` (numeric -- 5, 7, 8, 10, 13, 14, 15, or 16)
    - `digestType` (numeric -- 1=SHA-1, 2=SHA-256, 4=SHA-384)
    - `digest` (string, hex)
- **Notes:** Replaces any existing DS records. Only for externally hosted domains.

### PUT /dns/zones/{zone_id}/dnssec

- **Description:** Enable or disable DNSSEC for domain.
- **Parameters:**
  - `zone_id` (numeric, in URL, required)
  - `enable` (numeric, required) -- 0 or 1
- **Notes:** For Gigahost NS, auto-creates cryptokeys and submits DS to Norid. For external NS, enables flag only; DS records must be submitted separately.

### GET /dns/zones/{zone_id}/redirect

- **Description:** List redirects for a zone.
- **Parameters:**
  - `zone_id` (numeric, in URL, required)
- **Response fields:** `data[]` with `domain`, `source`, `target_url`, `enabled`, `created_at`
- **Notes:** Not available for externally hosted domains.

### POST /dns/zones/{zone_id}/redirect

- **Description:** Create a redirect for a zone.
- **Parameters:**
  - `zone_id` (numeric, in URL, required)
  - `target_url` (string, required) -- valid URL
  - `source` (string, optional, default: "@") -- subdomain or "@" for root
- **Notes:** Auto-creates A records pointing to the redirect server. Checks for conflicting DNS records. For root (@) redirects, a www redirect is also configured.

### PUT /dns/zones/{zone_id}/redirect

- **Description:** Update redirect target URL.
- **Parameters:**
  - `zone_id` (numeric, in URL, required)
  - `source` (string, required) -- subdomain or "@"
  - `target_url` (string, required)

### DELETE /dns/zones/{zone_id}/redirect

- **Description:** Delete a redirect.
- **Parameters:**
  - `zone_id` (numeric, in URL, required)
  - `source` (string, query parameter, required)
- **Notes:** Example: `DELETE /dns/zones/123/redirect?source=@`. For root redirects, the www A record is also removed.

### PUT /dns/zones/{zone_id}/registrant-email

- **Description:** Update registrant email for domain.
- **Parameters:**
  - `zone_id` (numeric, in URL, required)
  - `email` (string, required)
  - `enable_protection` (boolean, optional, default: false) -- WHOIS email protection via whoisbeskyttelse.no
- **Response fields:** `data.protected` (boolean), `data.email` (the actual or protected alias)

### GET /dns/dyndns

- **Description:** Update dynamic DNS record (DynDNS-compatible).
- **Parameters:**
  - `hostname` (string, query, required) -- FQDN to update; comma-separated for multiple
  - `myip` (string, query, optional) -- IPv4 address; uses client IP if omitted
  - `myipv6` (string, query, optional) -- IPv6 address
- **Authentication:** HTTP Basic Auth required (not Bearer).
- **Response:** Plain text, not JSON. Codes: `good <ip>`, `nochg <ip>`, `nohost`, `notfqdn`, `badauth`, `dnserr`, `badagent`
- **Notes:** Records set with 60s TTL. Compatible with ddclient, Synology, QNAP, OPNsense/pfSense, MikroTik.

---

## 4. ACCOUNT MANAGEMENT

### GET /account

- **Description:** Get the authenticated account.
- **Parameters:** none
- **Response fields:** `data.cust_id`, `data.cust_name`, `data.cust_address`, `data.cust_zipcode`, `data.cust_city`, `data.cust_country`, `data.cust_phone`, `data.cust_email`, `data.cust_company_no`, `data.cust_billing_email`, `data.cust_newsletter`, `data.cust_incident`, `data.cust_bandwidth_notification`, `data.cust_email_on_login`, `data.cust_notify_service_renewal`, `data.cust_partner`, `data.sshkeys[]`, `data.passkeys[]`, `data.contacts[]`, `data.orders[]`
- **Notes:** API keys never see `contact_2fa_secret` or legacy `api_key`.

### GET /account/activity

- **Description:** Recent account activity log (admin only).
- **Parameters:** none
- **Response fields:** `data[]` with `log_id`, `contact_id`, `contact_name`, `contact_username`, `log_timestamp`, `log_entry`

### PUT /account

- **Description:** Update billing/contact address fields (admin only).
- **Parameters (all optional, send any subset):**
  - `cust_address`, `cust_address2`, `cust_zipcode`, `cust_city`, `cust_province`, `cust_country` (string)
  - `cust_billing_email`, `cust_billing_email2` (string)
- **Notes:** HTML special characters are rejected.

### PUT /account/notifications

- **Description:** Update notification preferences (admin only).
- **Parameters (all required):**
  - `cust_newsletter` (0|1)
  - `cust_incident` (0|1)
  - `cust_bandwidth_notification` (0|1)
  - `cust_email_on_login` (0|1)
  - `cust_notify_service_renewal` (0|1)

### GET /account/user/{id}

- **Description:** Get a single user contact (admin only).
- **Parameters:**
  - `id` (numeric, in URL, required) -- contact_id
- **Response fields:** `data.contact_id`, `data.contact_name`, `data.contact_username`, `data.contact_access_level`, `data.contact_active`, `data.contact_2fa`, `data.servers[]` (with `id`, `srv_id`, `srv_name`, `ip_address`), `data.servers_unassigned[]`

### POST /account

- **Description:** Invite a new user contact (admin only).
- **Parameters:**
  - `name` (string, required)
  - `username` (string, required) -- email address
  - `accesslevel` (string, required) -- "admin", "user", or "server"
- **Notes:** Password setup link emailed, valid 24 hours. Contact inactive until password set.

### PUT /account/user/{id}

- **Description:** Update an existing user contact (admin only).
- **Parameters:**
  - `id` (numeric, in URL, required) -- contact_id
  - `contact_name` (string, required)
  - `contact_username` (string, required) -- email
  - `contact_access_level` (string, required) -- "admin", "user", or "server"
  - `contact_password` (string, optional) -- min 5 chars; weak/compromised passwords rejected
- **Notes:** Changing email sends re-verification. Last admin's level cannot be downgraded.

### DELETE /account/user/{id}

- **Description:** Remove a user contact (admin only).
- **Parameters:**
  - `id` (numeric, in URL, required) -- contact_id
- **Notes:** Cannot delete your own contact.

### PUT /account/user/{id}/server

- **Description:** Grant a user access to a server (admin only).
- **Parameters:**
  - `id` (numeric, in URL, required) -- contact_id
  - `srv_id` (numeric, in body, required)

### DELETE /account/user/{id}/server/{relation_id}

- **Description:** Revoke a user's access to a server (admin only).
- **Parameters:**
  - `id` (numeric, in URL, required) -- contact_id
  - `relation_id` (numeric, in URL, required) -- from `servers[].id` in GET /account/user/{id}

### POST /account/password

- **Description:** Change your own password.
- **Parameters:**
  - `current` (string, required)
  - `new` (string, required)
- **Notes:** Returns 201. Weak/compromised passwords rejected with 400.

### POST /account/email

- **Description:** Begin/complete account email address change (admin only).
- **Parameters (start):**
  - `email` (string, required)
- **Parameters (commit):**
  - `hash` (string, required) -- from verification link
- **Notes:** Returns 200 when verification sent, 201 when committed.

### POST /account/validate

- **Description:** Validate a contact's email address.
- **Parameters:**
  - `hash` (32-char hex, required)

### POST /account/2fa

- **Description:** Enable or disable two-factor authentication.
- **Parameters:**
  - `type` (string, required) -- "enable" or "disable"
  - `code` (numeric, required) -- current 6-digit TOTP code
- **Notes:** After disabling, re-enabling requires fresh authenticator setup.

### POST /account/sshkey

- **Description:** Add an SSH public key.
- **Parameters:**
  - `name` (string, required) -- label
  - `data` (string, required) -- OpenSSH public key

### DELETE /account/sshkey/{id}

- **Description:** Remove an SSH public key.
- **Parameters:**
  - `id` (numeric, in URL, required) -- key_id from GET /account

### POST /account/passkey

- **Description:** Register a passkey (WebAuthn).
- **Parameters (begin step):**
  - `step` (string, required) -- "begin"
- **Parameters (finish step):**
  - `step` (string, required) -- "finish"
  - `clientDataJSON` (base64url, required)
  - `attestationObject` (base64url, required)
  - `name` (string, optional, max 64 chars)
- **Notes:** Registration challenge expires quickly.

### DELETE /account/passkey/{id}

- **Description:** Remove a passkey.
- **Parameters:**
  - `id` (numeric, in URL, required) -- passkey_id

### PUT /account/language

- **Description:** Set the contact's preferred language.
- **Parameters:**
  - `contact_language` (string, required) -- "no" or "en"

### POST /account/reset

- **Description:** Begin/complete a password reset flow.
- **Parameters (stage 1):**
  - `username` (string, required) -- account email
- **Parameters (stage 2):**
  - `stage` (string, required) -- "2"
  - `hash` (string, required) -- from reset email
- **Notes:** Returns 200 in all non-error cases (does not reveal whether username exists).

### POST /account/topup

- **Description:** Generate a top-up invoice for account credit (admin only).
- **Parameters:**
  - `currency` (string, required) -- "nok", "eur", or "usd"
  - `amount` (numeric, required) -- integer amount
- **Notes:** Minimums: 100 NOK / 10 EUR / 10 USD. Max 5 unpaid top-up invoices. Norwegian amounts are VAT-inclusive.

### DELETE /account/delete

- **Description:** Permanently close the account (admin only).
- **Parameters:** none
- **Notes:** IRREVERSIBLE. Requires no active services, no active orders, and no unpaid invoices. Deletes cards, contacts, SSH keys, tokens, tickets, orders.

---

## 5. API KEYS

**Permissions model:** Each key has a `permissions` object with categories: `dns`, `servers`, `webhosting`, `racks`, `support`, `billing`, `account`. Each has `mode` ("r" or "rw"). For `dns`, `servers`, `webhosting`: optionally `all: false` with `ids: [...]` to restrict to specific resources. Token format: `flux_live_<64 hex chars>`.

### GET /account/apikeys

- **Description:** List active API keys (admin only).
- **Parameters:** none
- **Response fields:** `data[]` with `key_id`, `key_label`, `key_prefix`, `permissions`, `created_at`, `expires_at`, `last_used_at`, `last_used_ip`, `status`, `revoked_at`, `contact_id`

### GET /account/apikeys/{id}

- **Description:** Get a single API key (admin only).
- **Parameters:**
  - `id` (numeric, in URL, required) -- key_id

### GET /account/apikeys/{id}/log

- **Description:** Paginated usage log for an API key (admin only).
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `limit` (numeric, optional, default 50, max 200)
  - `offset` (numeric, optional, default 0)
- **Notes:** Request bodies truncated at 4 KB, response at 16 KB. Sensitive fields redacted. `truncated` flag indicates truncation.

### POST /account/apikeys

- **Description:** Create a new API key (admin only).
- **Parameters:**
  - `label` (string, required, 1-100 chars)
  - `permissions` (object, required)
  - `expires_at` (Unix timestamp, optional) -- must be in the future
- **Response fields:** `data.secret`, `data.prefix`, `data.label`, `data.expires_at`, `data.permissions`
- **Notes:** Secret shown only once at creation. Store immediately.

### POST /account/apikeys/{id}/rotate

- **Description:** Rotate an API key's secret (admin only).
- **Parameters:**
  - `id` (numeric, in URL, required) -- key_id
- **Response fields:** `data.secret`, `data.prefix`
- **Notes:** Previous secret invalidated immediately. New secret shown once.

### PUT /account/apikeys/{id}

- **Description:** Update an API key's label and/or permissions (admin only).
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `label` (string, optional, 1-100 chars)
  - `permissions` (object, optional) -- replaces entire permissions object
- **Notes:** At least one of `label` or `permissions` must be supplied. Only active keys can be edited.

### DELETE /account/apikeys/{id}

- **Description:** Revoke an API key (admin only).
- **Parameters:**
  - `id` (numeric, in URL, required) -- key_id
- **Notes:** Denied immediately on next request.

---

## 6. SUB-CLIENTS (Partner Accounts)

**Notes:** All require admin access and partner feature enabled. Otherwise 403.

### GET /account/clients

- **Description:** List all sub-clients.
- **Parameters:** none
- **Response fields:** `data[]` with `client_id`, `client_username` (auto-generated as `GH-<client_id+10000>`), `client_name`, `client_email`, `client_company_name`, `client_company_no`, `client_country`, `client_active`, `client_login_enabled`, `client_invoice_direct`, `client_billing_ehf`, `client_2fa`, `client_created`

### GET /account/clients/{id}

- **Description:** Get a sub-client with assigned and available resources.
- **Parameters:**
  - `id` (numeric, in URL, required) -- client_id
- **Response fields:** `data.client_id`, `data.client_username`, `data.client_name`, `data.client_email`, `data.servers[]`, `data.servers_unassigned[]`, `data.domains[]`, `data.domains_unassigned[]`, `data.webhosting[]`, `data.webhosting_unassigned[]`

### POST /account/clients

- **Description:** Create a new sub-client.
- **Parameters:**
  - `name` (string, required)
  - `password` (string, required, min 6 chars)
  - `email`, `phone`, `company_name`, `company_no`, `address`, `zip`, `city`, `country` (string, optional)
  - `login_enabled` (0|1, optional, default 1)
  - `invoice_direct` (0|1, optional, default 0)
  - `send_login` (boolean, optional, default false)
- **Response fields:** `data.client_id`, `data.client_username`
- **Notes:** If `invoice_direct` enabled, name/email/address and (for companies) `company_no` are required.

### PUT /account/clients/{id}

- **Description:** Update a sub-client.
- **Parameters:**
  - `id` (numeric, in URL, required) -- client_id
  - `client_name`, `client_email`, `client_phone`, `client_company_name`, `client_company_no`, `client_address`, `client_zip`, `client_city`, `client_country` (string, optional)
  - `client_active` (0|1, optional)
  - `client_login_enabled` (0|1, optional)
  - `client_invoice_direct` (0|1, optional)
  - `password` (string, optional, min 6 chars)

### POST /account/clients/{id}/sendlogin

- **Description:** Generate new password and email it to the sub-client.
- **Parameters:**
  - `id` (numeric, in URL, required)

### DELETE /account/clients/{id}

- **Description:** Delete a sub-client.
- **Parameters:**
  - `id` (numeric, in URL, required)
- **Notes:** All resource assignments removed; underlying resources revert to partner.

### PUT /account/clients/{id}/server

- **Description:** Assign a server to a sub-client.
- **Parameters:**
  - `id` (numeric, in URL, required) -- client_id
  - `srv_id` (numeric, in body, required)

### DELETE /account/clients/{id}/server/{relation_id}

- **Description:** Unassign a server from a sub-client.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `relation_id` (numeric, in URL, required)

### PUT /account/clients/{id}/domain

- **Description:** Assign a domain to a sub-client.
- **Parameters:**
  - `id` (numeric, in URL, required) -- client_id
  - `zone_id` (numeric, in body, required)

### DELETE /account/clients/{id}/domain/{relation_id}

- **Description:** Unassign a domain from a sub-client.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `relation_id` (numeric, in URL, required)

### PUT /account/clients/{id}/webhosting

- **Description:** Assign a webhosting account to a sub-client.
- **Parameters:**
  - `id` (numeric, in URL, required) -- client_id
  - `hosting_id` (numeric, in body, required)

### DELETE /account/clients/{id}/webhosting/{relation_id}

- **Description:** Unassign a webhosting account from a sub-client.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `relation_id` (numeric, in URL, required)

---

## 7. DATA PROCESSING AGREEMENTS (DPA)

### GET /account/dpa

- **Description:** List all DPAs for the account.
- **Parameters:** none
- **Response fields:** `data[]` with `dpa_id`, `dpa_signed_by`, `dpa_signed_ip`, `dpa_signed_at`, `dpa_data_types`, `dpa_affected_groups`, `dpa_revoked`

### GET /account/dpa/{id}

- **Description:** Download a signed DPA PDF.
- **Parameters:**
  - `id` (numeric, in URL, required) -- dpa_id
- **Response fields:** `data.filename`, `data.data` (base64-encoded PDF)

### POST /account/dpa

- **Description:** Create and sign a new DPA.
- **Parameters:**
  - `data_types` (array of strings, required) -- e.g. ["personal","financial"]
  - `affected_groups` (array of strings, required) -- e.g. ["employees","customers"]
- **Notes:** HTML special characters rejected. Returns 201.

### DELETE /account/dpa/{id}

- **Description:** Revoke a DPA.
- **Parameters:**
  - `id` (numeric, in URL, required)
- **Notes:** Record remains for audit purposes.

---

## 8. SERVERS

### GET /servers

- **Description:** Get a list of your servers.
- **Parameters:** none
- **Response fields:** `data[]` with extensive fields including `srv_id`, `srv_tag`, `product_id`, `cust_id`, `node_id`, `pmx_id`, `os_id`, `nic_id`, `iso_id`, `bwpool_id`, `srv_name`, `srv_status` (boolean), `srv_status_rescue`, `srv_status_install`, `srv_status_snapshot`, `srv_status_mount`, `srv_status_method`, `srv_status_reboot`, `srv_label`, `srv_date_created`, `srv_vps_type`, `srv_hostname`, `srv_bw`, `srv_feature_reinstall`, `srv_feature_mgmt`, `srv_mgmt_type`, `srv_cores`, `srv_ram`, `srv_vnc_port`, `srv_vnc_password`, `srv_vnc_token`, `srv_suspended`, `srv_custom_partition`, `srv_new`, `srv_location`, `srv_type`, `srv_primary_ip`, `os` (object with `os_id`, `os_name`, `os_release`), `ips[]` (with `ip_id`, `sub_id`, `ip_v4v6`, `ip_address`, `ip_reverse`, `ip_traffic_sum`, `ip_nullroute`, `ip_routed_to`, `ip_type`, `ip_netmask`, `ip_gateway`), `cancelled`

### GET /servers/{id}

- **Description:** Get data for a single server.
- **Parameters:**
  - `server_id` (numeric, in URL, required)
- **Response fields:** Same as list plus additional: `hdds[]` (with `hdd_id`, `hdd_manufacturer`, `hdd_type`, `hdd_size`, `hdd_space_used`), `subnets[]` (with `sub_id`, `sub_type`, `sub_network`, `sub_netmask`, `sub_gateway`, `sub_cidr`, `sub_vlan`), `order` (with `order_id`, `order_number`, `order_billing_type`, `order_billing_cycle`, `order_status`, `order_total`), `attacklogs[]`, `bw_used`, `bw_used_in`, `bw_used_out`, `ipmi_session` (with `kvm_id`, `kvm_ip_address`, `kvm_username`, `kvm_password`, `kvm_expires`, `kvm_in_use`)

### PUT /servers/{id}/name

- **Description:** Update server name.
- **Parameters:**
  - `server_id` (numeric, in URL, required)
  - `name` (string, required)

### POST /servers/{id}/ipmi

- **Description:** Establish KVM/IPMI session.
- **Parameters:**
  - `server_id` (numeric, in URL, required)
  - `acl` (string, required) -- semicolon-separated IPs/subnets
- **Response fields:** `data.kvm_ip_address`, `data.username`, `data.password`
- **Notes:** Sessions valid for 3 hours.

### GET /servers/{id}/powerstate

- **Description:** Get server powerstate.
- **Parameters:**
  - `server_id` (numeric, in URL, required)
- **Response fields:** `meta.powerstate` (boolean), `meta.timestamp`

### GET /servers/{id}/reboot

- **Description:** Reboot server.
- **Parameters:**
  - `server_id` (numeric, in URL, required)

### GET /servers/{id}/power/on

- **Description:** Power on server.
- **Parameters:**
  - `server_id` (numeric, in URL, required)

### GET /servers/{id}/power/off

- **Description:** Power off server.
- **Parameters:**
  - `server_id` (numeric, in URL, required)

### GET /servers/{id}/snapshots

- **Description:** Get server snapshots.
- **Parameters:**
  - `server_id` (numeric, in URL, required)
- **Response fields:** `data[]` with `snap_id`, `srv_id`, `snap_name`, `snap_display_name`, `snap_time`, `snap_state` ("pending" or "completed")

### POST /servers/{id}/snapshot

- **Description:** Create snapshot of server.
- **Parameters:**
  - `server_id` (numeric, in URL, required)
  - `name` (string, required)

### DELETE /servers/{id}/snapshot/{snap-id}

- **Description:** Delete snapshot of server.
- **Parameters:**
  - `server_id` (numeric, in URL, required)
  - `snap_id` (numeric, in URL, required)

### GET /servers/{id}/port_bits

- **Description:** Get server bandwidth graphs (base64 images).
- **Parameters:**
  - `server_id` (numeric, in URL, required)
- **Response fields:** `data.graph_day`, `data.graph_week`, `data.graph_month`, `data.graph_year` (all base64 image data)

### GET /servers/{id}/port_upkts

- **Description:** Get server packets graphs (base64 images).
- **Parameters:**
  - `server_id` (numeric, in URL, required)
- **Response fields:** `data.graph_day`, `data.graph_week`, `data.graph_month`, `data.graph_year` (all base64 image data)

### PUT /servers/{id}/reverse

- **Description:** Update reverse DNS.
- **Parameters:**
  - `server_id` (numeric, in URL, required)
  - For IPv4: `ip_id` (numeric), `dns` (string, e.g. "server.mydomain.com")
  - For IPv6 (NS delegation): `sub_id` (numeric), `dns` (string, e.g. "ns1.gigahost.no")

### GET /servers/{id}/isos

- **Description:** Get list of uploaded ISOs.
- **Parameters:**
  - `server_id` (numeric, in URL, required)
- **Response fields:** `data[]` with `iso_id`, `cust_id`, `iso_url`, `iso_name`, `iso_hash`, `iso_size`, `iso_state`, `iso_mounted`

### POST /servers/{id}/isos

- **Description:** Upload/mount ISO.
- **Parameters:**
  - `server_id` (numeric, in URL, required)
  - `iso_id` (string, required)

### GET /servers/{id}/upgrade

- **Description:** Get list of available packages to upgrade to.
- **Parameters:**
  - `server_id` (numeric, in URL, required)
- **Response fields:** `data[]` with `pkg_id`, `product_id`, `pkg_name`, `pkg_cores`, `pkg_ram`, `pkg_disk`, `product_name`, `product_price`

### POST /servers/{id}/upgrade

- **Description:** Upgrade server to another package.
- **Parameters:**
  - `server_id` (numeric, in URL, required)
  - `pkg_id` (numeric, required)

### POST /servers/{id}/ipv4

- **Description:** Order additional IP addresses.
- **Parameters:**
  - `server_id` (numeric, in URL, required)
  - `ip_type` (string, required) -- "l2" (layer 2, non-routed) or "l3" (routed layer 3)

### PUT /servers/{id}/ipv4/{ip_id}

- **Description:** Move a routed IP to another server.
- **Parameters:**
  - `id` (numeric, in URL, required) -- source server
  - `ip_id` (numeric, in URL, required) -- the IP to move
  - `target_srv_id` (numeric, in body, required) -- destination server
- **Notes:** Only L3 (routed) IPs can be moved. Both servers must be same account, same region. Destination must have primary IP and fewer than 5 additional IPs. Billing follows destination order.

---

## 9. REINSTALL / OS

### GET /reinstall/distro

- **Description:** Get list of available distributions.
- **Parameters:** none
- **Response fields:** `data[]` with `dist_id`, `type_id`, `dist_name`, `dist_value`, `dist_logo`, `dist_description`, `dist_active`

### GET /reinstall/distro/{id}

- **Description:** Get list of available operating systems for a distribution.
- **Parameters:**
  - `id` (numeric, in URL, required) -- dist_id
- **Response fields:** `data[]` with `os_id`, `dist_id`, `os_name`, `os_release`, `os_dist`, `os_arch`, `os_custom_partition`, `os_single_disk_only`, `os_support_raid`, `os_dedicated_only`, `os_minram`

### POST /servers/{id}/reinstall

- **Description:** Reinstall server.
- **Parameters:**
  - `server_id` (numeric, in URL, required)
  - `os_id` (numeric, required)
  - `language` (string, required) -- e.g. "en_US", "nb_NO"
  - `keyboard` (string, required) -- e.g. "no", "en"
  - `timezone` (string, required) -- e.g. "Europe/Oslo"
  - `hostname` (string, required)
- **Response fields:** `meta.message`, `meta.reboot` (boolean), `meta.root_passwd`

---

## 10. DEPLOY / PROVISIONING

### GET /deploy/servers

- **Description:** Get the deployable server catalog.
- **Parameters:** none
- **Response fields:** `data.tiers[]` (with `group_id`, `group_name`, `in_stock`, `products[]`), `data.regions[]` (with `region_id`, `region_name`, `region_name_short`, `region_country`), `data.eligibility` (with `verified`, `has_method`, `method_qualifies`, `has_paid_invoice`, `qualifies_arrears`, `credit_nok`), `data.currency`
- Product fields: `product_id`, `product_hash`, `product_name`, `type`, `in_stock`, `built_to_order`, `waitlist_eligible`, `allow_hourly`, `allow_recurring`, `discount_year`, `setup`, `contract`, `vm_cores`, `vm_memory`, `vm_storage`, `vm_bw`, `vm_bw_type`, `price_id`, `rate_hourly`, `rate_monthly`, `region_ids`

### POST /deploy/servers

- **Description:** Deploy one or more servers.
- **Parameters:**
  - `pid` (numeric, required) -- product ID; or use `hash`
  - `hash` (string, alternative to `pid`)
  - `price_id` (numeric, required)
  - `region_id` (numeric, required)
  - One of: `os_id` (numeric), `iso_id` (numeric), or `rescue` (numeric, 0 or 1)
  - `billing_period` (string, optional) -- "hourly" (default), "monthly", "quarterly", "annual"
  - `waitlist` (string, optional) -- "reserve" or "notify" for sold-out products
  - `quantity` (numeric, optional, default 1)
  - `backups` (numeric, optional) -- 0 or 1, adds 25%
  - `auction_id` (numeric, optional) -- forces quantity 1
  - `hostnames` (array of strings, optional)
  - `ssh_keys` (array of numeric, optional) -- SSH key IDs
  - `opts` (object, optional) -- selected product options
- **Response fields:** `data.success`, `data.message`, `data.order_ids[]`, `data.order_numbers[]`, `data.quantity`, `data.rate_hourly`, `data.monthly_cap`, `data.currency`
- **Notes:** Recurring terms create real invoices with setup fees and discounts. Waitlist "reserve" auto-deploys when capacity frees up; "notify" just emails. Server auctions cannot be reserved.

### GET /deploy/status

- **Description:** Get deployment status.
- **Parameters:**
  - `ids` (string, in URL, required) -- comma-separated order IDs
- **Response fields:** `data.servers[]` with `order_id`, `order_number`, `hostname`, `srv_id`, `ip`, `ipv6`, `status` (waitlist/waiting/deploying/installing/ready/rescue/iso), `password`; `data.all_ready` (boolean)
- **Notes:** Root password only returned during install (if no SSH key) or rescue mode.

### GET /deploy/isos

- **Description:** List your uploaded ISOs.
- **Parameters:** none
- **Response fields:** `data.isos[]` with `iso_id`, `iso_name`, `iso_size`

### GET /deploy/waitlist

- **Description:** List waitlist reservations and notify signups.
- **Parameters:** none
- **Response fields:** `data.reservations[]` (with `order_id`, `order_number`, `product_name`, `region_id`, `region_name`, `billing_type`, `total`, `currency`, `reserved_at`), `data.notifications[]` (with `notify_id`, `product_id`, `product_name`, `region_id`, `region_name`, `signed_up_at`)

### DELETE /deploy/waitlist

- **Description:** Cancel a reservation or remove a notify signup.
- **Parameters:**
  - `order_id` (numeric, optional) -- or `notify_id`
  - `notify_id` (numeric, optional) -- or `order_id`
- **Notes:** Pass exactly one. Reservations only cancellable while still waiting.

---

## 11. LEGACY ENDPOINTS

### GET /my/account

- **Description:** Get your account (legacy, read-only alias for /account).
- **Parameters:** none
- **Response fields:** `cust_id`, `cust_name`, `cust_company_no`, `cust_address`, `cust_contacts[]`, etc.

### GET /my/invoices

- **Description:** Get your invoices (legacy, read-only alias).
- **Parameters:** none
- **Response fields:** `invoices[]` with `inv_id`, `order_id`, `order_number`, `inv_md5`, `inv_filename`, `inv_number`, `inv_date`, `inv_duedate`, `inv_paid`, `inv_total`, `inv_vat`, `inv_total_vat`

---

## 12. WEBHOSTING

### GET /webhosting

- **Description:** List your web hosting accounts.
- **Parameters:** none
- **Response fields:** `data.hosting[]` with `hosting_id`, `domain`, `username`, `package`, `status`, `created_date`, `order_number`, `order_renewal`, `order_status`

### GET /webhosting/{id}

- **Description:** Get one hosting account.
- **Parameters:**
  - `id` (numeric, in URL, required) -- hosting account id

### POST /webhosting

- **Description:** Order a new hosting account.
- **Parameters:**
  - `zone_id` (numeric, required) -- DNS zone you own
  - `product_id` (numeric, required) -- hosting package
  - `billing_period` (numeric, required) -- months: 1, 3, 6, or 12
  - `update_dns` (numeric, optional) -- set 1 to auto-create web/mail DNS records
- **Response fields:** `data.hosting_id`, `data.domain`, `data.username`

### PUT /webhosting/{id}

- **Description:** Upgrade the hosting package.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `product_id` (numeric, required)
- **Notes:** Supplementary invoice created if >30 days remain in billing period.

### DELETE /webhosting/{id}/cancel

- **Description:** Cancel a hosting account.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `reason` (string, required)
  - `early_termination` (boolean, optional, default false) -- true = immediate termination, no refund

### GET /webhosting/{id}/stats

- **Description:** Account usage statistics.
- **Parameters:**
  - `id` (numeric, in URL, required)

### GET /webhosting/{id}/domains

- **Description:** List additional domains on the account.
- **Parameters:**
  - `id` (numeric, in URL, required)

---

## 13. WEBHOSTING - EMAIL

### GET /webhosting/{id}/emails

- **Description:** List email accounts.
- **Parameters:** `id` (numeric, in URL, required)

### POST /webhosting/{id}/emails

- **Description:** Create an email account.
- **Parameters:**
  - `email` (string, required) -- local part (before @)
  - `password` (string, required)
  - `quota` (numeric, optional) -- MB, 0 = unlimited

### PUT /webhosting/{id}/emails/{email}/password

- **Description:** Change an email password.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `email` (string, in URL, required) -- full email address
  - `password` (string, required)

### PUT /webhosting/{id}/emails/{email}/quota

- **Description:** Change an email quota.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `email` (string, in URL, required) -- full email address
  - `quota` (numeric, required) -- MB, 0 = unlimited

### DELETE /webhosting/{id}/emails/{email}

- **Description:** Delete an email account.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `email` (string, in URL, required) -- full email address

### GET /webhosting/{id}/email-forwarders

- **Description:** List email forwarders.
- **Parameters:** `id` (numeric, in URL, required)

### POST /webhosting/{id}/email-forwarders

- **Description:** Create an email forwarder.
- **Parameters:**
  - `user` (string, required) -- local part
  - `destinations` (array or comma-separated string, required)

### PUT /webhosting/{id}/email-forwarders/{user}

- **Description:** Update an email forwarder.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `user` (string, in URL, required)
  - `destinations` (array or comma-separated string, required)

### DELETE /webhosting/{id}/email-forwarders/{user}

- **Description:** Delete an email forwarder.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `user` (string, in URL, required)

### GET /webhosting/{id}/email-catch-all

- **Description:** Get the catch-all setting.
- **Parameters:** `id` (numeric, in URL, required)

### PUT /webhosting/{id}/email-catch-all

- **Description:** Update the catch-all setting.
- **Parameters:**
  - `catch` (string, required) -- action (e.g. reject or forward)
  - `value` (string, optional) -- email address when forwarding

### GET /webhosting/{id}/autoresponders

- **Description:** List autoresponders.
- **Parameters:** `id` (numeric, in URL, required)

### GET /webhosting/{id}/autoresponders/{email}

- **Description:** Get one autoresponder.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `email` (string, in URL, required)

### POST /webhosting/{id}/autoresponders

- **Description:** Create an autoresponder.
- **Parameters:**
  - `user` (string, required) -- local part
  - `subject` (string, optional)
  - `text` (string, optional) -- reply message
  - `cc` (string, optional) -- "ON" or "OFF"
  - `reply_once_time` (string, optional) -- e.g. "2d"

### PUT /webhosting/{id}/autoresponders/{email}

- **Description:** Update an autoresponder.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `email` (string, in URL, required)
  - Same fields as create

### DELETE /webhosting/{id}/autoresponders/{email}

- **Description:** Delete an autoresponder.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `email` (string, in URL, required)

### GET /webhosting/{id}/email-dkim

- **Description:** Get DKIM status.
- **Parameters:** `id` (numeric, in URL, required)

### PUT /webhosting/{id}/email-dkim

- **Description:** Enable or disable DKIM.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `enable` (boolean, required)
- **Notes:** When domain uses Gigahost DNS, the matching DNS record is updated automatically.

### GET /webhosting/{id}/spamfilter

- **Description:** Get spam filter settings.
- **Parameters:** `id` (numeric, in URL, required)

### PUT /webhosting/{id}/spamfilter

- **Description:** Update spam filter settings.
- **Parameters (all optional):**
  - `where` (string) -- where spam is delivered
  - `required_hits` (number) -- spam score threshold
  - `high_score_block` (string) -- "yes" or "no"
  - `high_score` (number) -- very high score threshold
  - `rewrite_subject` (boolean)
  - `subject_tag` (string)
  - `blacklist_from` (string) -- always spam
  - `whitelist_from` (string) -- never spam

---

## 14. WEBHOSTING - FTP

### GET /webhosting/{id}/ftp

- **Description:** List FTP accounts.
- **Parameters:** `id` (numeric, in URL, required)

### POST /webhosting/{id}/ftp

- **Description:** Create an FTP account.
- **Parameters:**
  - `username` (string, required)
  - `password` (string, required)
  - `path` (string, optional) -- relative folder to restrict to; empty = full access

### PUT /webhosting/{id}/ftp/{ftp_user}/password

- **Description:** Change an FTP password.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `ftp_user` (string, in URL, required)
  - `password` (string, required)

### DELETE /webhosting/{id}/ftp/{ftp_user}

- **Description:** Delete an FTP account.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `ftp_user` (string, in URL, required)

---

## 15. WEBHOSTING - DATABASES

### GET /webhosting/{id}/databases

- **Description:** List databases.
- **Parameters:** `id` (numeric, in URL, required)

### POST /webhosting/{id}/databases

- **Description:** Create a database.
- **Parameters:**
  - `name` (string, required)
  - `password` (string, required) -- for the database user

### PUT /webhosting/{id}/databases/{dbname}/password

- **Description:** Change a database password.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `dbname` (string, in URL, required)
  - `password` (string, required)

### DELETE /webhosting/{id}/databases/{dbname}

- **Description:** Delete a database.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `dbname` (string, in URL, required)

---

## 16. WEBHOSTING - SUBDOMAINS

### POST /webhosting/{id}/subdomain

- **Description:** Create a subdomain.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `subdomain` (string, required) -- without the main domain

### DELETE /webhosting/{id}/subdomain/{name}

- **Description:** Delete a subdomain.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `name` (string, in URL, required)

---

## 17. WEBHOSTING - FILE MANAGER

All paths are relative to the account home directory.

### GET /webhosting/{id}/files/tree

- **Description:** Get the folder tree.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `path` (string, query, optional, default "/")

### GET /webhosting/{id}/files/list

- **Description:** List files in a folder.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `path` (string, query, optional, default "/")
  - `page` (numeric, query, optional, default 1)
  - `ipp` (numeric, query, optional, default 50) -- items per page

### GET /webhosting/{id}/files/edit

- **Description:** Read a file's contents.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `path` (string, query, required)

### GET /webhosting/{id}/files/download

- **Description:** Download a file.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `path` (string, query, required)

### POST /webhosting/{id}/files/save

- **Description:** Save a file.
- **Parameters:**
  - `path` (string, required) -- the folder
  - `filename` (string, required)
  - `text` (string, optional) -- file contents

### POST /webhosting/{id}/files/rename

- **Description:** Rename a file or folder.
- **Parameters:**
  - `path` (string, required) -- the folder it is in
  - `old` (string, required) -- current name
  - `filename` (string, required) -- new name

### POST /webhosting/{id}/files/folder

- **Description:** Create a folder.
- **Parameters:**
  - `path` (string, required) -- parent folder
  - `name` (string, required) -- folder name

### POST /webhosting/{id}/files/create

- **Description:** Create an empty file.
- **Parameters:**
  - `path` (string, required)
  - `filename` (string, required)

### POST /webhosting/{id}/files/delete

- **Description:** Delete files or folders.
- **Parameters:**
  - `paths` (array, required) -- paths to delete

### POST /webhosting/{id}/files/upload

- **Description:** Upload files (multipart form data).
- **Parameters:**
  - `files` (file, one or more, required)
  - `path` (string, optional, default "/")

---

## 18. WEBHOSTING - APPLICATIONS (One-Click Install)

### GET /webhosting/{id}/installations

- **Description:** List installed applications.
- **Parameters:** `id` (numeric, in URL, required)

### GET /webhosting/{id}/apps/available

- **Description:** List available applications.
- **Parameters:** `id` (numeric, in URL, required)

### POST /webhosting/{id}/install

- **Description:** Install an application.
- **Parameters:**
  - `app` (string, required) -- application id from available list
  - `domain` (string, optional) -- default: main domain
  - `path` (string, optional, default "/")
  - `admin_username` (string, optional, default "admin")
  - `admin_password` (string, optional) -- generated if omitted
  - `admin_email` (string, optional) -- defaults to account email
  - `site_title` (string, optional)
- **Notes:** Admin login returned in response.

### POST /webhosting/{id}/install/{installId}/update

- **Description:** Update an installed application.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `installId` (string, in URL, required)

### GET /webhosting/{id}/install/{installId}/backups

- **Description:** List application backups.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `installId` (string, in URL, required)
- **Response fields:** Each backup includes id, date, size, version, type.

### GET /webhosting/{id}/install/{installId}/backuplocations

- **Description:** List backup destinations.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `installId` (string, in URL, required)

### POST /webhosting/{id}/install/{installId}/backups

- **Description:** Back up or restore an application.
- **Parameters:**
  - `action` (string, required) -- "backup" or "restore"
  - When "backup": `location` (string, optional), `ftp` (object with `type`, `host`, `port`, `user`, `pass`, `path` -- required when location is "new")
  - When "restore": `backup` (string, required) -- backup id

### GET /webhosting/{id}/install/{installId}/backups/{backupId}/download

- **Description:** Download an application backup.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `installId` (string, in URL, required)
  - `backupId` (string, in URL, required)

### DELETE /webhosting/{id}/install/{installId}/backups

- **Description:** Delete an application backup.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `installId` (string, in URL, required)
  - `backup` (string, required) -- backup id

### DELETE /webhosting/{id}/install/{installId}

- **Description:** Uninstall an application.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `installId` (string, in URL, required)

---

## 19. WEBHOSTING - SSL

### GET /webhosting/{id}/ssl

- **Description:** Get the SSL certificate.
- **Parameters:** `id` (numeric, in URL, required)
- **Notes:** Response includes enabled status, certificate details, and valid hostnames.

### POST /webhosting/{id}/ssl

- **Description:** Request a free SSL certificate.
- **Parameters:**
  - `hostnames` (array, required) -- hostnames to secure, all under the main domain
  - `keysize` (string, optional) -- "secp384r1" (default), "secp256r1", or "rsa_4096"
- **Notes:** Usually issued within a minute.

### DELETE /webhosting/{id}/ssl

- **Description:** Remove the SSL certificate.
- **Parameters:** `id` (numeric, in URL, required)

---

## 20. WEBHOSTING - SITE BACKUPS

These cover the whole hosting account, separate from per-application backups.

### GET /webhosting/{id}/backups

- **Description:** List site backups.
- **Parameters:** `id` (numeric, in URL, required)

### POST /webhosting/{id}/backups

- **Description:** Create or restore a site backup.
- **Parameters:**
  - `action` (string, required) -- "backup" or "restore"
  - When "restore": `filename` (string, required) -- backup file to restore

### DELETE /webhosting/{id}/backups

- **Description:** Delete a site backup.
- **Parameters:**
  - `id` (numeric, in URL, required)
  - `filename` (string, required) -- backup file to delete

---

## CERTBOT PLUGIN (not an API endpoint, but documented)

**certbot-dns-gigahost** -- Certbot DNS authenticator plugin for automated SSL via dns-01 challenge. Install via `pip install certbot-dns-gigahost`. Credentials file at e.g. `~/.secrets/certbot/gigahost.ini` containing `dns_gigahost_api_token=flux_live_xxxxxxxxxxxx`. Flags: `--dns-gigahost-credentials` (required), `--dns-gigahost-propagation-seconds` (optional, default 120).

---

**Total endpoint count: ~110 distinct endpoints across 20 functional domains.**
