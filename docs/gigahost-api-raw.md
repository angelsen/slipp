# Gigahost API Documentation

Source: https://gigahost.no/en/api-dokumentasjon
Fetched: 2026-07-08

Gigahost API documentation for clients. Integrate servers and services directly into your own system or panel.

Current API version: 0

Base URL: https://api.gigahost.no/api/v0

To communicate with our API you need to authenticate. To do this, use the /authenticate endpoint.

Add the received token to your header: **Authorization: Bearer {token}
**

Its expected that all PUT/POST requests are json encoded.

POST

        /authenticate

        Authenticate with API and receive Authorization Token.

    Parameters**username (string)password (string)**

Optional parameters**code (numeric) - If you have 2FA enabled**

Example return data

```
{
   "success":true,
   "meta":
   {
      "status": 200,
      "status_message": "200 OK"
   },
   "data":
   {
      "token":"xxxxxxxx",
      "token_expire": "unixtimestamp",
      "customer_id": "xxxxxx"
   }
}

```

        As an alternative to Bearer tokens, you can authenticate using HTTP Basic Auth. This is required for the DynDNS endpoint and supported across all other endpoints.

Send your credentials in the Authorization header:

`Authorization: Basic base64(username:password)`
**Important:** The username is your email address. If it contains special characters (e.g. + or @), you must URL-encode it when passing it in a URL.

        Example: user+tag@example.com becomes user%2Btag%40example.com

Example with curl:

```
# Using --user (curl handles encoding):
curl --user "user@example.com:yourpassword" https://api.gigahost.no/api/v0/servers
# Using inline URL credentials (URL-encode the username):
curl "https://user%40example.com:yourpassword@api.gigahost.no/api/v0/servers"

```

        For unattended integrations you can authenticate with a personal API key instead of a username/password Bearer token. Each key has a permissions object that restricts what it can read or change, and (for DNS, servers, and webhosting) can be limited to a specific list of resource IDs.

Send the key in the Authorization header just like a session token:

`Authorization: Bearer flux_live_<hex>`
Example with curl:

```
curl -H "Authorization: Bearer flux_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" https://api.gigahost.no/api/v0/servers

```

        **Security model:** the full secret is shown only once, at creation time. After that the secret cannot be recovered, so rotate or delete the key if it is lost. List and read responses return only the **key_prefix** (the first part of the secret, safe to display). API keys cannot manage other API keys.

An optional **expires_at** (Unix timestamp) auto-revokes the key once reached. See `/account/apikeys` for management endpoints.

GET

        /bgp

        Get all BGP data

    Parameters

{none}

Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK"
   },
   "data":{
      "asn":[
         {
            "id":"1",
            "asn":"212345",
            "asn_name":"Example Network",
            "asn_country":"NO",
            "irr_v4":"AS-EXAMPLE",
            "irr_v6":"AS-EXAMPLE",
            "irr_updated":"1700000000",
            "status":"active",
            "rejected_reason":""
         }
      ],
      "prefix_lists":[
         {
            "id":"1",
            "asn_id":"1",
            "prefix":"192.0.2.0/24",
            "prefix_type":"ipv4",
            "status":"active",
            "your_asn":"212345",
            "asn_country":"NO"
         }
      ],
      "sessions":[
         {
            "id":"1",
            "asn_id":"1",
            "cust_id":"1111",
            "router_id":"1",
            "srv_id":"3523",
            "ip_id":"7795",
            "ip_type":"ipv4",
            "defaultroute":"1",
            "status":"active",
            "neighbor_ipv4":"185.125.168.1",
            "neighbor_ipv6":"2a03:94e0::1",
            "multihop":"0",
            "router_asn":"39029",
            "your_asn":"212345",
            "asn_country":"NO",
            "ip_address":"185.181.63.24"
         }
      ]
   }
}

```

    POST

        /bgp/asn

        Submit ASN for approval

    Maximum 3 ASNs per customer. Requires verification before activation. An email with verification instructions will be sent after submission.

Required parameters**
asn (numeric or string - ASN number, e.g. "212345" or "AS212345")
**

Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK",
      "message":"ASN and LOA has been submitted for review."
   }
}

```

        Error responses

```
// Invalid ASN
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "message":"ASN is not valid"
   }
}
// Maximum ASNs reached
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "message":"Only three ASNs can be configured at a time. Contact support to remove an ASN first."
   }
}
// ASN already exists
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "message":"The ASN already exists in the database."
   }
}

```

    POST

        /bgp/{asn_id}/session

        Create BGP session

    ASN must be in 'active' status. Sessions are created on available routers in the server's datacenter. Both IPv4 and IPv6 sessions can be created simultaneously.

Required parameters**
asn_id (numeric - inurl - ASN database ID, not the ASN number)
redundant (numeric - 0 or 1 for redundant sessions)
defaultroute (numeric - 0 or 1 to receive default route)
**

Optional parameters**
ip_id_v4 (numeric - IP ID for IPv4 session)
ip_id_v6 (numeric - IP ID for IPv6 session)
**

At least one of ip_id_v4 or ip_id_v6 must be provided

Example request body

```
{
   "redundant":1,
   "defaultroute":1,
   "ip_id_v4":"7795",
   "ip_id_v6":"7796"
}

```

        Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK",
      "message":"BGP sessions has been created."
   }
}

```

        Error responses

```
// Session already exists
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "message":"IPv4 session exists already."
   }
}
// No routers available
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "message":"Unable to find available BGP routers."
   }
}

```

    DELETE

        /bgp/{session_id}/session

        Delete BGP session

    Session must be in 'active' status and belong to the customer. Actual deletion is processed asynchronously.

Parameters**
session_id (numeric - inurl - BGP session ID)
**

Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK",
      "message":"BGP sessions have been marked for deletion."
   }
}

```

    GET

        /dns/lookup/organization/{org_number}

        Lookup Norwegian organization information

    Parameters**org_number (numeric - 9 digits - inurl)**

Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK",
      "message":"Company lookup successful"
   },
   "data":{
      "company_name":"Example AS",
      "address":"Exampleveien 1",
      "zip_code":"0123",
      "city":"Oslo"
   }
}

```

    GET

        /dns/domains/check/{domain}

        Check .no domain availability

    Parameters**domain (string - inurl, e.g. example.no)**

Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK",
      "message":"Domain availability checked"
   },
   "data":{
      "domain":"example.no",
      "available":true,
      "reason":""
   }
}

```

    GET

        /dns/zones

        List all DNS zones

    Parameters

{none}

Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK"
   },
   "data":[
      {
         "zone_id":"123",
         "cust_id":"1111",
         "zone_name":"example.no",
         "zone_name_display":"example.no",
         "zone_type":"NATIVE",
         "zone_active":"1",
         "zone_protected":"1",
         "zone_is_registered":"1",
         "domain_registrar":"norid",
         "domain_status":"active",
         "domain_expiry_date":"2025-12-31 23:59:59",
         "domain_auto_renew":"1",
         "external_dns":"0",
         "record_count":5,
         "zone_updated":1700000000
      }
   ]
}

```

    GET

        /dns/zones/{zone_id}/records

        Get DNS records for a zone

    Parameters**zone_id (numeric - inurl)**

Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK"
   },
   "data":[
      {
         "record_id":"abc123",
         "record_name":"@",
         "record_type":"A",
         "record_value":"185.125.168.166",
         "record_ttl":3600,
         "record_priority":null
      },
      {
         "record_id":"def456",
         "record_name":"www",
         "record_type":"A",
         "record_value":"185.125.168.166",
         "record_ttl":3600,
         "record_priority":null
      },
      {
         "record_id":"ghi789",
         "record_name":"@",
         "record_type":"MX",
         "record_value":"mail.example.no",
         "record_ttl":3600,
         "record_priority":10
      }
   ]
}

```

    GET

        /dns/zones/{zone_id}/registrant

        Get registrant information for registered domain

    Only available for registered .no domains

Parameters**zone_id (numeric - inurl)**

Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK"
   },
   "data":{
      "contact_id":"ABC123P",
      "name":"John Doe",
      "organization":"Example AS",
      "email":"post@example.no",
      "address":"Exampleveien 1",
      "city":"Oslo",
      "postal_code":"NO-0123",
      "country_code":"NO",
      "identity":null,
      "identity_type":null,
      "type":"organization"
   }
}

```

    POST

        /dns/domains/register

        Register a new .no domain

    Required parameters**
            domain_name (string - domain to register)
            registrant_type (string - "organization" or "person")
            email (string - valid email address)
            applicant_name (string - name of applicant, max 255 characters)
            zip_code (string - postal code)
            city (string - city name)
        **

For organization registrants:**
org_number (string - 9 digit organization number)
company_name (string - company name, max 255 characters)
**

For person registrants:**
pid (string - format: N.PRI.12345678)
first_name (string)
last_name (string)
**

Optional parameters**
use_gigahost_ns (boolean - default: true)
nameservers (array - required if use_gigahost_ns is false, minimum 2)
**

Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK",
      "message":"Domain registered successfully! You will receive a confirmation email shortly."
   },
   "data":{
      "zone_id":"123",
      "domain_name":"example.no",
      "expires_at":"2025-11-17",
      "status":"active"
   }
}

```

    POST

        /dns/zones

        Create a new DNS zone

    Supports both JSON and multipart/form-data (for zone file import)

Required parameters (JSON)**
zone_name (string - domain name)
**

Optional parameters (JSON)**
zone_type (string - "NATIVE", "MASTER", or "SLAVE", default: "NATIVE")
create_default_records (boolean - default: false)
transfer_domain (boolean - initiate .no domain transfer, default: false)
auth_code (string - required if transfer_domain is true)
use_existing_ns (boolean - keep existing nameservers, default: false)
**

For zone file import (multipart/form-data):**
zone_name (string)
zone_file (file - BIND zone file, max 2MB)
**

Example return data

```
{
   "meta":{
      "status":201,
      "status_message":"201 Created",
      "message":"Zone created successfully."
   },
   "data":{
      "zone_id":"123"
   }
}

```

    POST

        /dns/zones/{zone_id}/records

        Create a new DNS record

    Required parameters**
            zone_id (numeric - inurl)
            record_value (string - record content)
        **

Optional parameters**
record_name (string - default: "@")
record_type (string - A, AAAA, CNAME, MX, TXT, NS, TLSA, etc., default: "A")
record_ttl (numeric - default: 3600)
record_priority (numeric - required for MX records)
**

Example return data

```
{
   "meta":{
      "status":201,
      "status_message":"201 Created",
      "message":"Record created successfully."
   }
}

```

    PUT

        /dns/zones/{zone_id}/records/{record_id}

        Update an existing DNS record

    Validates IPv4 addresses for A records, IPv6 for AAAA records, and requires priority for MX records

Required parameters**
zone_id (numeric - inurl)
record_id (string - inurl)
record_value (string - record content)
**

Optional parameters**
record_name (string - default: "@")
record_type (string - default: "A")
record_ttl (numeric - default: 3600)
record_priority (numeric - for MX records)
**

Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK",
      "message":"Record updated successfully."
   }
}

```

    PUT

        /dns/zones/{zone_id}/registrant

        Change domain registrant/owner

    Requires Norid Applicant Declaration acceptance. Creates new order and extends domain by 1 year.

Required parameters**
zone_id (numeric - inurl)
registrant_type (string - "organization" or "person")
email (string - valid email address)
applicant_name (string - name of applicant, max 255 characters)
zip_code (string - postal code)
city (string - city name)
agree_to_terms (boolean - must be true)
**

For organization registrants:**
org_number (string - 9 digit organization number)
company_name (string - company name, max 255 characters)
**

For person registrants:**
pid (string - format: N.PRI.XXXXXXXX)
**

Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK",
      "message":"Registrant changed successfully."
   }
}

```

    PUT

        /dns/zones/{zone_id}/auto-renew

        Toggle automatic renewal for domain

    Only available for registered .no domains

Required parameters**
zone_id (numeric - inurl)
auto_renew (numeric - 0 or 1)
**

Example request body

```
{
   "auto_renew":1
}

```

        Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK",
      "message":"Auto-renewal updated successfully."
   }
}

```

    PUT

        /dns/zones/{zone_id}/nameservers

        Update nameservers for registered domain

    Only available for protected zones (registered domains). Verifies nameservers are authoritative before applying changes. Automatically updates external_dns flag.

Required parameters**
zone_id (numeric - inurl)
nameservers (array - minimum 2 nameservers)
**

Example request body

```
{
   "nameservers":[
      "ns1.example.com",
      "ns2.example.com"
   ]
}

```

        Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK",
      "message":"Nameservers updated successfully."
   }
}

```

    DELETE

        /dns/zones/{zone_id}

        Delete a DNS zone

    Protected zones (registered domains) cannot be deleted

Parameters**zone_id (numeric - inurl)**

Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK",
      "message":"Zone deleted successfully."
   }
}

```

    DELETE

        /dns/zones/{zone_id}/records/{record_id}

        Delete a DNS record

    Required parameters**
            zone_id (numeric - inurl)
            record_id (string - inurl)
            name (string - query parameter)
            type (string - query parameter)
        **

Example: DELETE /dns/zones/123/records/abc123?name=www&type=A

Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK",
      "message":"Record deleted successfully."
   }
}

```

    GET

        /dns/zones/{zone_id}/ds-records

        Get DS records for DNSSEC

    For domains using Gigahost nameservers, returns DS records from Gigahost DNS. For externally hosted domains, returns configuration instructions.

Parameters**zone_id (numeric - inurl)**

Example return data (Gigahost nameservers)

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK"
   },
   "data":{
      "ds_records":"12345 13 2 1234567890ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890AB"
   }
}

```

        Error responses

```
// DNSSEC not enabled
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "message":"DNSSEC is not enabled for this domain."
   }
}

```

    GET

        /dns/zones/{zone_id}/ds-records/external

        Get stored external DS records

    Only available for domains using external nameservers

Parameters**zone_id (numeric - inurl)**

Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK"
   },
   "data":{
      "ds_records":[
         {
            "keyTag":12345,
            "alg":13,
            "digestType":2,
            "digest":"1234567890ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890AB"
         }
      ]
   }
}

```

        Error responses

```
// Not externally hosted
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "message":"This endpoint is only for externally hosted domains."
   }
}

```

    POST

        /dns/zones/ptr

        Create a PTR (reverse DNS) zone

    Required parameters**
            prefix (string - IP prefix, e.g. "185.181.63" or "2a03:94e0::")
            ip_version (string - "ipv4" or "ipv6")
            zone_name (string - PTR zone name, e.g. "63.181.185.in-addr.arpa" or "0.e.4.9.3.0.a.2.ip6.arpa")
        **

Example request body (IPv4)

```
{
   "prefix":"185.181.63",
   "ip_version":"ipv4",
   "zone_name":"63.181.185.in-addr.arpa"
}

```

        Example request body (IPv6)

```
{
   "prefix":"2a03:94e0::",
   "ip_version":"ipv6",
   "zone_name":"0.e.4.9.3.0.a.2.ip6.arpa"
}

```

        Example return data

```
{
   "meta":{
      "status":201,
      "status_message":"201 Created",
      "message":"PTR zone created successfully."
   },
   "data":{
      "zone_id":"456"
   }
}

```

        Error responses

```
// Invalid zone name format
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "message":"Invalid IPv4 PTR zone name format."
   }
}
// Zone already exists
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "message":"PTR zone already exists."
   }
}

```

    POST

        /dns/zones/{zone_id}/ds-records/external

        Submit external DS records to Norid

    Only for domains using external nameservers. Replaces any existing DS records.

Required parameters**
zone_id (numeric - inurl)
ds_records (array - array of DS record objects)
**

DS record object fields:**
keyTag (numeric - 0-65535)
alg (numeric - algorithm: 5, 7, 8, 10, 13, 14, 15, or 16)
digestType (numeric - 1 for SHA-1, 2 for SHA-256, 4 for SHA-384)
digest (string - hexadecimal digest)
**

Example request body

```
{
   "ds_records":[
      {
         "keyTag":12345,
         "alg":13,
         "digestType":2,
         "digest":"1234567890ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890AB"
      }
   ]
}

```

        Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK",
      "message":"DS records submitted to Norid successfully"
   }
}

```

        Error responses

```
// Invalid key tag
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "message":"Invalid Key Tag: must be between 0-65535"
   }
}
// Invalid algorithm
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "message":"Invalid algorithm: 99"
   }
}
// Not externally hosted
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "message":"This endpoint is only for externally hosted domains."
   }
}

```

    PUT

        /dns/zones/{zone_id}/dnssec

        Enable or disable DNSSEC for domain

    For domains using Gigahost nameservers, automatically creates cryptokeys and submits DS records to Norid. For externally hosted domains, enables the DNSSEC flag (DS records must be submitted separately).

Required parameters**
zone_id (numeric - inurl)
enable (numeric - 0 to disable, 1 to enable)
**

Example request body

```
{
   "enable":1
}

```

        Example return data (Gigahost nameservers)

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK",
      "message":"DNSSEC enabled successfully and DS records submitted to registry"
   }
}

```

        Example return data (external nameservers)

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK",
      "message":"DNSSEC flag enabled. Please configure DNSSEC on your nameservers."
   }
}

```

        Example return data (disable)

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK",
      "message":"DNSSEC disabled successfully"
   }
}

```

        Error responses

```
// Not a registered domain
{
   "meta":{
      "status":403,
      "status_message":"403 Forbidden",
      "message":"DNSSEC can only be enabled for registered domains."
   }
}

```

    GET

        /dns/zones/{zone_id}/redirect

        List redirects for a zone

    Not available for externally hosted domains

Parameters**zone_id (numeric - inurl)**

Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK"
   },
   "data":[
      {
         "domain":"example.no",
         "source":"@",
         "target_url":"https://www.target-site.no",
         "enabled":1,
         "created_at":"2024-01-15 12:00:00"
      },
      {
         "domain":"blog.example.no",
         "source":"blog",
         "target_url":"https://blog.target-site.no",
         "enabled":1,
         "created_at":"2024-02-20 14:30:00"
      }
   ]
}

```

        Error responses

```
// Externally hosted domain
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "message":"Redirects are not available for externally hosted domains."
   }
}

```

    POST

        /dns/zones/{zone_id}/redirect

        Create a redirect for a zone

    Automatically creates the necessary A records pointing to the redirect server. Checks for conflicting DNS records before creating the redirect. For root (@) redirects, a www redirect is also configured.

Required parameters**
zone_id (numeric - inurl)
target_url (string - valid URL, e.g. "https://example.com")
**

Optional parameters**
source (string - subdomain or "@" for root, default: "@")
**

Example request body

```
{
   "source":"@",
   "target_url":"https://www.target-site.no"
}

```

        Example return data

```
{
   "meta":{
      "status":201,
      "status_message":"201 Created",
      "message":"Redirect created successfully."
   },
   "data":{
      "domain":"example.no",
      "source":"@",
      "target_url":"https://www.target-site.no"
   }
}

```

        Error responses

```
// DNS conflict
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "message":"DNS conflict: '@' has an existing A record (185.125.168.166). Please remove it before adding a redirect."
   }
}
// Redirect already exists
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "message":"A redirect already exists for example.no. Delete it first or update instead."
   }
}
// External DNS
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "message":"This domain uses external nameservers. Redirects cannot be configured."
   }
}
// Invalid URL
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "message":"Invalid target URL format. Must be a valid URL (e.g. https://example.com)."
   }
}

```

    PUT

        /dns/zones/{zone_id}/redirect

        Update redirect target URL

    Required parameters**
            zone_id (numeric - inurl)
            source (string - subdomain or "@" for root)
            target_url (string - valid URL)
        **

Example request body

```
{
   "source":"@",
   "target_url":"https://www.new-target.no"
}

```

        Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK",
      "message":"Redirect updated successfully."
   }
}

```

    DELETE

        /dns/zones/{zone_id}/redirect

        Delete a redirect

    For root (@) redirects, the www A record pointing to the redirect server is also removed.

Required parameters**
zone_id (numeric - inurl)
source (string - query parameter, subdomain or "@" for root)
**

Example: DELETE /dns/zones/123/redirect?source=@

Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK",
      "message":"Redirect deleted successfully."
   }
}

```

    PUT

        /dns/zones/{zone_id}/registrant-email

        Update registrant email for domain

    Supports optional WHOIS email protection via whoisbeskyttelse.no forwarding. When protection is enabled, a random alias is generated and forwarding is set up to the real email address.

Required parameters**
zone_id (numeric - inurl)
email (string - valid email address)
**

Optional parameters**
enable_protection (boolean - enable WHOIS email protection, default: false)
**

Example request body (without protection)

```
{
   "email":"post@example.no",
   "enable_protection":false
}

```

        Example request body (with protection)

```
{
   "email":"post@example.no",
   "enable_protection":true
}

```

        Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK",
      "message":"Email updated successfully"
   },
   "data":{
      "protected":true,
      "email":"a1b2c3d4e5f6@whoisbeskyttelse.no"
   }
}

```

        Error responses

```
// Not a registered domain
{
   "meta":{
      "status":403,
      "status_message":"403 Forbidden",
      "message":"Email can only be updated for registered domains."
   }
}

```

    GET

        /dns/dyndns?hostname={hostname}&myip={ip}

        Update dynamic DNS record

    The hostname must belong to a DNS zone on your account. The zone is resolved automatically from the hostname, so no zone ID is needed. Records are set with a 60-second TTL for fast propagation.

**Authentication:** HTTP Basic Auth (see /authenticate above).

Required parameters**
hostname (string - query parameter. FQDN to update, e.g. home.example.no. Comma-separated for multiple.)
**

Optional parameters**
myip (string - query parameter. IPv4 address to set. If omitted, the client's source IP is used.)
myipv6 (string - query parameter. IPv6 address to set.)
**

**Response codes (plain text, not JSON)**

```
good 1.2.3.4        # IP updated successfully
nochg 1.2.3.4       # No change, IP already correct
nohost              # Hostname not found on your account
notfqdn             # Invalid or missing hostname
badauth             # Authentication failed
dnserr              # DNS server error
badagent            # Invalid IP address provided

```

        When updating multiple hostnames, one response code is returned per line.

**Examples with curl**

```
# Update with a specific IP
curl --user "user@example.com:password" \
  "https://api.gigahost.no/api/v0/dns/dyndns?hostname=home.example.no&myip=1.2.3.4"
# Let the server detect your IP automatically
curl --user "user@example.com:password" \
  "https://api.gigahost.no/api/v0/dns/dyndns?hostname=home.example.no"
# Update with IPv6
curl --user "user@example.com:password" \
  "https://api.gigahost.no/api/v0/dns/dyndns?hostname=home.example.no&myipv6=2a03:94e0::1234"
# Update both IPv4 and IPv6
curl --user "user@example.com:password" \
  "https://api.gigahost.no/api/v0/dns/dyndns?hostname=home.example.no&myip=1.2.3.4&myipv6=2a03:94e0::1234"
# Update multiple hostnames at once
curl --user "user@example.com:password" \
  "https://api.gigahost.no/api/v0/dns/dyndns?hostname=home.example.no,vpn.example.no&myip=1.2.3.4"

```

        **ddclient** (/etc/ddclient.conf)

```
protocol=dyndns2
ssl=yes
server=api.gigahost.no/api/v0/dns
login=user@example.com
password='your-password'
home.example.no

```

        **Synology NAS**

        Go to Control Panel > External Access > DDNS. Select «Customized» provider and configure:

```
Query URL: https://api.gigahost.no/api/v0/dns/dyndns?hostname=__HOSTNAME__&myip=__MYIP__
Username:  your Gigahost email (e.g. user@example.com)
Password:  your Gigahost password
Hostname:  home.example.no

```

        **QNAP NAS**

        Go to Network & Virtual Switch > DDNS. Select «Customized» and configure:

```
URL: https://api.gigahost.no/api/v0/dns/dyndns?hostname=%HOST%&myip=%IP%
Username:  your Gigahost email
Password:  your Gigahost password
Hostname:  home.example.no

```

        **Generic router**

        Select «Custom» or «User-defined» as the Dynamic DNS provider and enter:

```
Server / Update URL: api.gigahost.no
Path:                /api/v0/dns/dyndns
Protocol:            dyndns2
Username:            your Gigahost email
Password:            your Gigahost password
Hostname:            home.example.no

```

        **OPNsense / pfSense**

        Go to Services > Dynamic DNS and add a new entry:

```
Service type:  Custom
Update URL:    https://api.gigahost.no/api/v0/dns/dyndns?hostname=%h&myip=%i
Username:      your Gigahost email
Password:      your Gigahost password
Hostname:      home.example.no

```

        **MikroTik RouterOS**

```
/ip cloud set ddns-enabled=no
/system script add name=dyndns source={
  /tool fetch url="https://api.gigahost.no/api/v0/dns/dyndns\
    ?hostname=home.example.no&myip=$ipaddr" \
    user="user@example.com" password="your-password" \
    mode=https dst-path=dyndns.txt
}
/system scheduler add name=dyndns-update interval=5m on-event=dyndns

```

    PLUGIN

        certbot-dns-gigahost

        Certbot DNS authenticator plugin for automated SSL certificates

    This plugin automates the process of completing a **dns-01** challenge by creating, and subsequently removing, TXT records using the Gigahost API. It supports single-domain, multi-domain, and wildcard certificates.

**Installation:** [pypi.org/project/certbot-dns-gigahost](https://pypi.org/project/certbot-dns-gigahost/)

`pip install certbot-dns-gigahost`
Create a credentials file (e.g. **~/.secrets/certbot/gigahost.ini**) containing your Gigahost API key:

```
dns_gigahost_api_token=flux_live_xxxxxxxxxxxx

```

        **Important:** Protect your credentials file with restricted permissions:

```
chmod 600 ~/.secrets/certbot/gigahost.ini

```

        **--dns-gigahost-credentials** (required): Path to the credentials INI file.

        **--dns-gigahost-propagation-seconds** (optional): Seconds to wait for DNS propagation. Default: 120.

```
certbot certonly \
  --authenticator dns-gigahost \
  --dns-gigahost-credentials ~/.secrets/certbot/gigahost.ini \
  -d example.com \
  -d www.example.com

```

        ```

certbot certonly \
 --authenticator dns-gigahost \
 --dns-gigahost-credentials ~/.secrets/certbot/gigahost.ini \
 -d example.com \
 -d "\*.example.com"

````
        ```
docker run --rm \
  -v /etc/letsencrypt:/etc/letsencrypt \
  -v /var/lib/letsencrypt:/var/lib/letsencrypt \
  certbot-dns-gigahost \
  certonly \
  --authenticator dns-gigahost \
  --dns-gigahost-credentials /etc/letsencrypt/gigahost.ini \
  --agree-tos \
  --email "email@example.com" \
  -d example.com

````

        1. The plugin authenticates with the Gigahost API using HTTP Basic Auth.

        2. It looks up the DNS zone for the domain being validated.

        3. It creates a **_acme-challenge** TXT record with the validation token.

        4. After verification, the plugin removes the TXT record automatically.

Renewal is automatic. No additional configuration is needed after the initial certificate issuance. Test with:

`certbot renew --dry-run`
Manage your account: company and contact details, users, security (password / 2FA / SSH / passkey), API keys, sub-clients (for partner accounts), data processing agreements, and account-level actions like top-up and closure. The legacy `/my/account` and `/my/invoices` endpoints remain available as read-only aliases, but new integrations should use `/account`.

GET

        /account

        Get the authenticated account

    Includes company/contact details, notification preferences, SSH keys, passkeys, and (for admin sessions) the list of users and order history.

Parameters

{none}

Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK"
   },
   "data":{
      "cust_id":"1111",
      "cust_name":"Example AS",
      "cust_address":"Example Road 1",
      "cust_zipcode":"0000",
      "cust_city":"Oslo",
      "cust_country":"Norway",
      "cust_phone":"+47 00000000",
      "cust_email":"billing@example.com",
      "cust_company_no":"999999999",
      "cust_billing_email":"billing@example.com",
      "cust_newsletter":false,
      "cust_incident":true,
      "cust_bandwidth_notification":true,
      "cust_email_on_login":false,
      "cust_notify_service_renewal":true,
      "cust_partner":"0",
      "sshkeys":[
         {
            "key_id":"1",
            "key_name":"laptop",
            "key_added":"1700000000",
            "key_data":"ssh-ed25519 AAAA... user@host"
         }
      ],
      "passkeys":[
         {
            "passkey_id":"1",
            "passkey_name":"YubiKey",
            "created_at":"1700000000",
            "last_used":"1712000000"
         }
      ],
      "contacts":[
         {
            "contact_id":"5",
            "contact_name":"Jane Doe",
            "contact_username":"jane@example.com",
            "contact_access_level":"admin",
            "contact_2fa":"1"
         }
      ],
      "orders":[
         {
            "order_id":"1",
            "order_number":"GH-100001",
            "order_status":"active",
            "order_billing_cycle":"monthly",
            "products":[
               {
                  "op_id":"1",
                  "srv_id":"3523",
                  "product_id":"42",
                  "product_name":"VPS-Linux-1",
                  "srv_name":"web01"
               }
            ]
         }
      ]
   }
}

```

        API keys never see the **contact_2fa_secret** or the legacy **api_key** field.

GET

        /account/activity

        Recent account activity log (admin only)

    Parameters

{none}

Example return data

```
{
   "meta":{ "status":200, "status_message":"200 OK" },
   "data":[
      {
         "log_id":"12345",
         "contact_id":"5",
         "contact_name":"Jane Doe",
         "contact_username":"jane@example.com",
         "log_timestamp":"1712000000",
         "log_entry":"User changed their password."
      }
   ]
}

```

    PUT

        /account

        Update billing/contact address fields (admin only)

    HTML special characters are rejected.

Optional parameters (send any subset)**
cust_address (string)
cust_address2 (string)
cust_zipcode (string)
cust_city (string)
cust_province (string)
cust_country (string)
cust_billing_email (string)
cust_billing_email2 (string)
**

Returns 200 on success.

PUT

        /account/notifications

        Update notification preferences (admin only)

    Required parameters**
            cust_newsletter (0|1) - product newsletter
            cust_incident (0|1) - service incident notifications
            cust_bandwidth_notification (0|1) - bandwidth threshold alerts
            cust_email_on_login (0|1) - email on every login
            cust_notify_service_renewal (0|1) - upcoming renewal reminders
        **

Returns 200 on success.

GET

        /account/user/{id}

        Get a single user contact (admin only)

    Includes the contact's profile and the lists of servers currently assigned and available for assignment.

Parameters**id (numeric, in URL) - contact_id**

Example return data

```
{
   "meta":{ "status":200, "status_message":"200 OK" },
   "data":{
      "contact_id":"5",
      "contact_name":"Jane Doe",
      "contact_username":"jane@example.com",
      "contact_access_level":"user",
      "contact_active":"1",
      "contact_2fa":"0",
      "servers":[
         { "id":"1", "srv_id":"3523", "srv_name":"web01", "ip_address":"192.0.2.10" }
      ],
      "servers_unassigned":[
         { "srv_id":"3524", "srv_name":"db01", "ip_address":"192.0.2.11" }
      ]
   }
}

```

    POST

        /account

        Invite a new user contact (admin only)

    A password setup link valid for 24 hours is emailed to the new contact.

Required parameters**
name (string) - display name, no HTML characters
username (string) - email address
accesslevel (string) - one of: admin, user, server
**

Returns 200 on success. The new contact is inactive until they complete the password setup flow.

Error responses

```
// Email already in use
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "message":"Email address is already in use."
   }
}
// Invalid access level
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "message":"Access level is not valid."
   }
}

```

    PUT

        /account/user/{id}

        Update an existing user contact (admin only)

    Editable fields: name, email address, access level, and password.

Required parameters**
id (numeric, in URL) - contact_id
contact_name (string)
contact_username (string) - email
contact_access_level (string) - admin, user, or server
**

Optional parameters**contact_password (string) - new password, minimum 5 characters; weak or compromised passwords are rejected**

Changing the email address sends a re-verification mail to the new address. The access level on the last remaining admin cannot be downgraded.

DELETE

        /account/user/{id}

        Remove a user contact (admin only)

    You cannot delete your own contact.

Parameters**id (numeric, in URL) - contact_id**

PUT

        /account/user/{id}/server

        Grant a user access to a server (admin only)

    Required parameters**
            id (numeric, in URL) - contact_id
            srv_id (numeric, in body) - server to assign
        **

DELETE

        /account/user/{id}/server/{relation_id}

        Revoke a user's access to a server (admin only)

    The relation_id comes from the contact's `servers[].id` field.

Parameters**
id (numeric, in URL) - contact_id
relation_id (numeric, in URL) - assignment id from GET /account/user/{id}
**

POST

        /account/password

        Change your own password

    Required parameters**
            current (string) - current password
            new (string) - new password
        **

Returns 201 on success. The new password must meet our password strength requirements; weak or compromised passwords are rejected with a 400.

POST

        /account/email

        Begin / complete an account email address change (admin only)

    Send an **email** to start the change. A verification link is emailed to the new address. Send the **hash** from that link to commit the change.

Required parameters (start)**email (string) - new email address**

Required parameters (commit)**hash (string) - hash from the verification link**

Returns 200 when the verification email is sent, 201 when the change is committed.

POST

        /account/validate

        Validate a contact's email address

    Submit the 32-character hash from the verification email to mark the contact as verified and activate it.

Required parameters**hash (32-char hex) - validation hash**

POST

        /account/2fa

        Enable or disable two-factor authentication

    Required parameters**
            type (string) - "enable" or "disable"
            code (numeric) - current 6-digit code from your authenticator app
        **

After disabling 2FA, re-enabling requires setting up a fresh authenticator. The previously-displayed QR code cannot be reused.

POST

        /account/sshkey

        Add an SSH public key

    Keys can be selected during server reinstall and are pushed to new servers at provisioning.

Required parameters**
name (string) - label for the key
data (string) - OpenSSH public key (e.g. "ssh-ed25519 AAAA...")
**

Returns 200 on success. Invalid keys return 400.

DELETE

        /account/sshkey/{id}

        Remove an SSH public key

    Parameters**id (numeric, in URL) - key_id from GET /account**

POST

        /account/passkey

        Register a passkey

    Call once with **step: "begin"** to receive the registration options, then again with **step: "finish"** sending back the authenticator response.

Required parameters (begin)**step (string) - "begin"**

Required parameters (finish)**
step (string) - "finish"
clientDataJSON (base64url) - returned by the authenticator
attestationObject (base64url) - returned by the authenticator
name (string, optional) - human-readable label, max 64 chars
**

Registration challenges expire after a short timeout, so complete the "finish" call promptly.

DELETE

        /account/passkey/{id}

        Remove a passkey

    Parameters**id (numeric, in URL) - passkey_id from GET /account**

PUT

        /account/language

        Set the contact's preferred language

    Required parameters**contact_language (string) - "no" or "en"**

POST

        /account/reset

        Begin / complete a password reset flow

    Stage 1 emails a reset link. Stage 2 consumes the hash from that link and emails the new password.

Required parameters (stage 1)**username (string) - account email**

Required parameters (stage 2)**
stage (string) - "2"
hash (string) - reset hash from the email
**

Returns 200 in all non-error cases (the response does not reveal whether the username exists).

Personal API keys authenticate unattended integrations without exposing your password. Each key is independent of your interactive session and can be revoked at any time.

**Granular permissions.** Every key has a permissions object covering seven categories. Each category has a mode of **"r"** (read-only: GET requests pass, everything else returns 403) or **"rw"** (read-write: all methods allowed). For the three resource categories (dns, servers, and webhosting), a key can additionally be limited to a specific list of resource IDs by setting `all: false` and listing the IDs in `ids`. When limited this way, list endpoints automatically filter their results, and any write that does not target one of the listed IDs returns 403. Categories not present in the permissions object are treated as no access. The remaining four categories (racks, support, billing, account) are global: no per-resource limit.

Example permissions object

```
{
   "dns":        { "mode":"rw", "all":false, "ids":[123, 456] },
   "servers":    { "mode":"r",  "all":true },
   "webhosting": { "mode":"rw", "all":true },
   "racks":      { "mode":"r" },
   "support":    { "mode":"rw" },
   "billing":    { "mode":"r" },
   "account":    { "mode":"r" }
}

```

    This key can read all servers, fully manage all webhosting accounts, manage only DNS zones 123 and 456, and read racks/support/billing/account data.

**Token format.** Authenticate the key by sending `Authorization: Bearer flux_live_<64 hex chars>` on every request. See the API Key Authentication section under `/authenticate` above.

**Security model.** The full secret is shown only at creation (and at rotation); after that the secret cannot be recovered. List and read responses only return the **key_prefix**. API keys cannot create, list, modify, rotate, or delete other API keys; those operations require a session token. An optional **expires_at** auto-revokes the key once reached, and every successful request updates **last_used_at** and **last_used_ip**.

GET

        /account/apikeys

        List active API keys (admin only)

    Secrets are never returned, only the prefix.

Parameters

{none}

Example return data

```
{
   "meta":{ "status":200, "status_message":"200 OK" },
   "data":[
      {
         "key_id":"1",
         "key_label":"CI deployment",
         "key_prefix":"flux_live_abc123def456",
         "permissions":{
            "dns":     { "mode":"rw", "all":true },
            "servers": { "mode":"r",  "all":true }
         },
         "created_at":"1712000000",
         "expires_at":"1740873600",
         "last_used_at":"1712256000",
         "last_used_ip":"192.0.2.1",
         "status":"active",
         "revoked_at":null,
         "contact_id":"5"
      }
   ]
}

```

    GET

        /account/apikeys/{id}

        Get a single API key (admin only)

    Parameters**id (numeric, in URL) - key_id**

Error responses

```
// Not found
{
   "meta":{
      "status":404,
      "status_message":"404 Not Found",
      "message":"API key not found."
   }
}

```

    GET

        /account/apikeys/{id}/log

        Paginated usage log for an API key (admin only)

    Each entry includes timestamp, source IP, method, path, query string, request body, response code, and response body. Useful for auditing and debugging integrations.

Optional parameters**
limit (numeric, default 50, max 200)
offset (numeric, default 0)
**

Request and response bodies are truncated for storage (request 4 KB, response 16 KB); a `truncated` flag indicates when this has happened. Sensitive fields in request bodies (password, secret, token, etc.) are redacted before storage. Only the most recent entries per key are retained.

POST

        /account/apikeys

        Create a new API key (admin only)

    **The secret is shown only this once. Store it immediately.**

Required parameters**
label (string, 1-100 chars) - human-readable name, no HTML special characters
permissions (object) - granular permissions, see the section above
**

Optional parameters**expires_at (Unix timestamp) - must be in the future; the key auto-revokes when reached**

Example request body

```
{
   "label":"CI deployment",
   "expires_at":1740873600,
   "permissions":{
      "dns":     { "mode":"rw", "all":false, "ids":[123, 456] },
      "servers": { "mode":"r",  "all":true }
   }
}

```

        Example return data

```
{
   "meta":{
      "status":201,
      "status_message":"201 Created",
      "message":"API key created."
   },
   "data":{
      "secret":"flux_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
      "prefix":"flux_live_xxxxxxxxxxxx",
      "label":"CI deployment",
      "expires_at":1740873600,
      "permissions":{
         "dns":     { "mode":"rw", "all":false, "ids":[123, 456] },
         "servers": { "mode":"r",  "all":true }
      }
   }
}

```

        Error responses

```
// Missing or oversized label
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "message":"Label is required (max 100 characters)."
   }
}
// expires_at in the past
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "message":"Expiry must be in the future."
   }
}
// Malformed permissions object
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "message":"Invalid permissions payload."
   }
}

```

    POST

        /account/apikeys/{id}/rotate

        Rotate an API key's secret (admin only)

    The previous secret stops working immediately. The new secret is returned **once**. Store it immediately. Only active keys can be rotated.

Parameters**id (numeric, in URL) - key_id**

Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK",
      "message":"API key rotated."
   },
   "data":{
      "secret":"flux_live_yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy",
      "prefix":"flux_live_yyyyyyyyyyyy"
   }
}

```

    PUT

        /account/apikeys/{id}

        Update an API key's label and/or permissions (admin only)

    The secret and id are unchanged. At least one of **label** or **permissions** must be supplied.

Parameters**id (numeric, in URL) - key_id**

Optional parameters (send at least one)**
label (string, 1-100 chars)
permissions (object) - replaces the entire permissions object
**

Returns 200 on success. Only active keys can be edited.

DELETE

        /account/apikeys/{id}

        Revoke an API key (admin only)

    The key is denied immediately on the next request.

Parameters**id (numeric, in URL) - key_id**

Partner accounts can manage _sub-clients_: separate end-customer entities under the partner umbrella, each with their own login, optional direct-billing relationship with Gigahost, and assigned servers / domains / webhosting accounts. All sub-client endpoints require admin access and require the account to have the partner feature enabled; otherwise the endpoint returns 403.

GET

        /account/clients

        List all sub-clients

    Parameters

{none}

Example return data

```
{
   "meta":{ "status":200, "status_message":"200 OK" },
   "data":[
      {
         "client_id":"10",
         "client_username":"GH-10010",
         "client_name":"Acme AS",
         "client_email":"billing@acme.example",
         "client_company_name":"Acme AS",
         "client_company_no":"999999999",
         "client_country":"Norway",
         "client_active":"1",
         "client_login_enabled":"1",
         "client_invoice_direct":"0",
         "client_billing_ehf":"0",
         "client_2fa":"0",
         "client_created":"1710000000"
      }
   ]
}

```

    GET

        /account/clients/{id}

        Get a sub-client with assigned and available resources

    The response includes the sub-client's profile, the servers/domains/webhosting accounts currently assigned, and lists of resources available to assign.

Parameters**id (numeric, in URL) - client_id**

Example return data

```
{
   "meta":{ "status":200, "status_message":"200 OK" },
   "data":{
      "client_id":"10",
      "client_username":"GH-10010",
      "client_name":"Acme AS",
      "client_email":"billing@acme.example",
      "servers":[
         { "id":"1", "srv_id":"3523", "srv_name":"web01", "ip_address":"192.0.2.10" }
      ],
      "servers_unassigned":[
         { "srv_id":"3524", "srv_name":"db01", "ip_address":"192.0.2.11" }
      ],
      "domains":[
         { "id":"1", "zone_id":"42", "zone_name":"example.no" }
      ],
      "domains_unassigned":[
         { "zone_id":"43", "zone_name":"example.com" }
      ],
      "webhosting":[
         { "id":"1", "hosting_id":"7", "domain":"acme.example", "package":"start" }
      ],
      "webhosting_unassigned":[]
   }
}

```

    POST

        /account/clients

        Create a new sub-client

    The username is auto-generated as `GH-<client_id + 10000>`. If `invoice_direct` is enabled, name, email, address, and (for company customers) a 9-digit org number are required up front.

Required parameters**
name (string)
password (string, min 6 chars)
**

Optional parameters**
email (string)
phone (string)
company_name (string)
company_no (string, 9 digits if billing direct and company is set)
address, zip, city, country (string)
login_enabled (0|1, default 1)
invoice_direct (0|1, default 0) - bill the sub-client directly
send_login (boolean, default false) - email the sub-client their credentials
**

Example return data

```
{
   "meta":{
      "status":201,
      "status_message":"201 Created",
      "message":"Sub-client created."
   },
   "data":{
      "client_id":10,
      "client_username":"GH-10010"
   }
}

```

    PUT

        /account/clients/{id}

        Update a sub-client

    Enabling `client_invoice_direct` for the first time validates the billing details. Disabling it clears the invoice-routing stamps on the sub-client's resources. Already issued invoices are not retroactively re-routed.

Parameters**id (numeric, in URL) - client_id**

Optional parameters (send any subset)**
client_name, client_email, client_phone (string)
client_company_name, client_company_no (string)
client_address, client_zip, client_city, client_country (string)
client_active (0|1)
client_login_enabled (0|1)
client_invoice_direct (0|1)
password (string, min 6 chars) - replaces the sub-client's password
**

POST

        /account/clients/{id}/sendlogin

        Generate a new password and email it to the sub-client

    The new credentials are emailed to `client_email`. Use this to onboard a sub-client who has lost their password.

Parameters**id (numeric, in URL) - client_id**

DELETE

        /account/clients/{id}

        Delete a sub-client

    All resource assignments are removed. The underlying resources themselves are not deleted; they revert to the partner.

Parameters**id (numeric, in URL) - client_id**

PUT

        /account/clients/{id}/server

        Assign a server to a sub-client

    Required parameters**
            id (numeric, in URL) - client_id
            srv_id (numeric, in body) - server to assign
        **

DELETE

        /account/clients/{id}/server/{relation_id}

        Unassign a server from a sub-client

    Parameters**
            id (numeric, in URL) - client_id
            relation_id (numeric, in URL) - servers[].id from GET /account/clients/{id}
        **

PUT

        /account/clients/{id}/domain

        Assign a domain to a sub-client

    Required parameters**
            id (numeric, in URL) - client_id
            zone_id (numeric, in body) - DNS zone to assign
        **

DELETE

        /account/clients/{id}/domain/{relation_id}

        Unassign a domain from a sub-client

    Parameters**
            id (numeric, in URL) - client_id
            relation_id (numeric, in URL) - domains[].id from GET /account/clients/{id}
        **

PUT

        /account/clients/{id}/webhosting

        Assign a webhosting account to a sub-client

    Required parameters**
            id (numeric, in URL) - client_id
            hosting_id (numeric, in body) - webhosting account to assign
        **

DELETE

        /account/clients/{id}/webhosting/{relation_id}

        Unassign a webhosting account from a sub-client

    Parameters**
            id (numeric, in URL) - client_id
            relation_id (numeric, in URL) - webhosting[].id from GET /account/clients/{id}
        **

GET

        /account/dpa

        List all DPAs for the account

    Each entry includes the signer, signed timestamp, source IP, and data types covered.

Parameters

{none}

Example return data

```
{
   "meta":{ "status":200, "status_message":"200 OK" },
   "data":[
      {
         "dpa_id":"1",
         "dpa_signed_by":"Jane Doe",
         "dpa_signed_ip":"192.0.2.1",
         "dpa_signed_at":"1700000000",
         "dpa_data_types":["personal","financial"],
         "dpa_affected_groups":["employees","customers"],
         "dpa_revoked":"0"
      }
   ]
}

```

    GET

        /account/dpa/{id}

        Download a signed DPA PDF

    Decode the `data` field to obtain the binary PDF.

Parameters**id (numeric, in URL) - dpa_id**

Example return data

```
{
   "meta":{ "status":200, "status_message":"200 OK" },
   "data":{
      "filename":"Databehandleravtale.pdf",
      "data":"JVBERi0xLjQKJ..."
   }
}

```

    POST

        /account/dpa

        Create and sign a new DPA

    The DPA is signed under the authenticated contact's identity; the source IP is recorded for audit.

Required parameters**
data_types (array of strings) - categories of personal data covered (e.g. ["personal","financial"])
affected_groups (array of strings) - groups whose data is processed (e.g. ["employees","customers"])
**

HTML special characters in any element are rejected. Returns 201 on success with the created DPA record.

DELETE

        /account/dpa/{id}

        Revoke a DPA

    The record remains on the account for audit purposes.

Parameters**id (numeric, in URL) - dpa_id**

POST

        /account/topup

        Generate a top-up invoice for account credit (admin only)

    The account must either be verified or have at least one active order. At most five unpaid top-up invoices may exist at once.

Required parameters**
currency (string) - "nok", "eur", or "usd"
amount (numeric) - integer amount in the chosen currency
**

Minimum amounts: 100 NOK, 10 EUR, 10 USD. The maximum credit balance is configured per-account; exceeding it returns 400. For Norwegian customers the supplied amount is treated as VAT-inclusive.

Returns 200 with a confirmation message. The invoice is created in the customer's open invoice list. Proceed with payment via the regular billing flow.

DELETE

        /account/delete

        Permanently close the account (admin only)

    **Irreversible.** Deletes all stored payment cards, removes user contacts, SSH keys, tokens, tickets, and orders, and marks the customer record as terminated. The account cannot be reopened. A new account must be created if access is needed again.

The request only succeeds if the account has no active services (servers, colocation, S3, DNS zones, webhosting), no active orders, and no unpaid invoices. Each precondition returns 400 with a specific message identifying the blocking service.

Parameters

{none}

Error responses

```
// Active services present
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "message":"Account has existing services (Servers)."
   }
}
// Unpaid invoices present
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "message":"Account has unpaid invoices."
   }
}

```

    GET

                            /servers

                            Get a list of your servers

                        Parameters

{none}

Example return data

```
        {
           "meta":{
              "status":200,
              "status_message":"200 OK"
           },
           "data":[
           {
              "srv_id":"111",
              "srv_tag":"0",
              "product_id":"0",
              "cust_id":"111",
              "node_id":"0",
              "pmx_id":"111",
              "os_id":"111",
              "nic_id":"111",
              "iso_id":"0",
              "bwpool_id":"0",
              "srv_name":"srv111.gigahost.no",
              "srv_status":true,
              "srv_status_rescue":false,
              "srv_status_install":false,
              "srv_status_snapshot":false,
              "srv_status_mount":false,
              "srv_status_method":"icmp",
              "srv_status_reboot":"0",
              "srv_label":"srv111.gigahost.no",
              "srv_manufacturer":"",
              "srv_model":"",
              "srv_motherboard":"",
              "srv_date_created":"1530609706",
              "srv_vps_type":"kvm",
              "srv_hostname":"srv111.gigahost.no",
              "srv_bw":"1000",
              "srv_feature_reinstall":true,
              "srv_feature_mgmt":true,
              "srv_feature_preconf":"0",
              "srv_mgmt_type":"kvm",
              "srv_formfactor":"",
              "srv_cores":"2",
              "srv_ram":"2",
              "srv_ram_type":"",
              "srv_ram_sticks":"0",
              "srv_ram_vendor":"",
              "srv_vnc_port":"0",
              "srv_vnc_password":"",
              "srv_vnc_token":"",
              "srv_suspended":false,
              "srv_custom_partition":"1",
              "srv_new":false,
              "srv_location":"DC2",
              "srv_type":"vps",
              "srv_primary_ip":"185.181.63.xx",
              "os":{
              "os_id":"72",
              "os_name":"Ubuntu 18.04 LTS 64-bit",
              "os_release":"ubuntu",
              "os_dedicated_only":"0",
              "os_minram":"0",
              "os_custom_partition":"1",
              "os_single_disk_only":"1"
              },
              "ips":[
              {
                 "ip_id":"7795",
                 "sub_id":"405",
                 "ip_v4v6":"ipv4",
                 "ip_address":"185.181.63.xx",
                 "ip_reverse":"static.185.181.63.xx.customers.gigahost.no",
                 "ip_traffic_sum":"0",
                 "ip_pkts_sum":"0",
                 "ip_nullroute":"0",
                 "ip_routed_to":"0",
                 "ip_type":"primary",
                 "ip_netmask":"255.255.255.0",
                 "ip_gateway":"185.181.63.1"
              },
              {
                 "ip_id":"7538",
                 "sub_id":"404",
                 "ip_v4v6":"ipv4",
                 "ip_address":"185.181.62.xx",
                 "ip_reverse":"static.185.181.62.xx.gigahost.no",
                 "ip_traffic_sum":"0",
                 "ip_pkts_sum":"0",
                 "ip_nullroute":"0",
                 "ip_routed_to":"7795",
                 "ip_type":"extra",
                 "ip_netmask":"255.255.255.0",
                 "ip_gateway":"185.181.62.1"
              }
              ]
              "cancelled":null
           }
        }

```

                        GET

                            /servers/{id}

                            Get data for server

                        Parameters**server_id (numeric - inurl)**

Example return data

```
        {
        "meta":{
        "status":200,
        "status_message":"200 OK"
        },
        "data":[
        {
        "srv_id":"3523",
        "srv_tag":"0",
        "product_id":"0",
        "cust_id":"19998",
        "node_id":"0",
        "pmx_id":"4",
        "os_id":"72",
        "nic_id":"1422",
        "iso_id":"0",
        "bwpool_id":"0",
        "srv_name":"srv3523.gigahost.no",
        "srv_status":true,
        "srv_status_rescue":false,
        "srv_status_install":false,
        "srv_status_snapshot":false,
        "srv_status_mount":false,
        "srv_label":"srv3523.gigahost.no",
        "srv_manufacturer":"",
        "srv_model":"",
        "srv_motherboard":"",
        "srv_date_created":"1530609706",
        "srv_vps_type":"kvm",
        "srv_hostname":"srv3523.gigahost.no",
        "srv_bw":"1000",
        "srv_feature_reinstall":true,
        "srv_feature_mgmt":true,
        "srv_feature_preconf":false,
        "srv_mgmt_type":"kvm",
        "srv_formfactor":"",
        "srv_cores":"2",
        "srv_ram":"2",
        "srv_ram_type":"",
        "srv_ram_sticks":"0",
        "srv_ram_vendor":"",
        "srv_vnc_port":"0",
        "srv_vnc_password":"",
        "srv_vnc_token":"",
        "srv_vmware_id":"0",
        "srv_suspended":false,
        "srv_deleted":"0",
        "srv_deleted_date":"0",
        "srv_bw_notice":"0",
        "srv_migration_state":"2",
        "srv_custom_partition":"1",
        "srv_new":false,
        "srv_location":"DC2",
        "srv_type":"vps",
        "ipmi_session":null,
        "os":{
        "os_id":"72",
        "os_name":"Ubuntu 18.04 LTS 64-bit",
        "os_release":"ubuntu",
        "os_dedicated_only":"0",
        "os_minram":"0",
        "os_custom_partition":"1",
        "os_single_disk_only":"1",
        "dist_logo":"/images/os/ubuntu.png"
        },
        "cpus":[
        ],
        "hdds":[
        {
        "hdd_id":"1622",
        "srv_id":"3523",
        "datastore_id":"0",
        "hdd_manufacturer":"Proxmox",
        "hdd_model":"",
        "hdd_type":"SSD",
        "hdd_size":"20",
        "hdd_space_used":"0",
        "hdd_serial_number":""
        }
        ],
        "ips":[
        {
        "ip_id":"7795",
        "sub_id":"405",
        "ip_v4v6":"ipv4",
        "ip_address":"185.181.63.24",
        "ip_reverse":"static.185.181.63.24.customers.gigahost.no",
        "ip_traffic_sum":"0",
        "ip_pkts_sum":"0",
        "ip_nullroute":"0",
        "ip_routed_to":"0",
        "ip_type":"primary",
        "ip_netmask":"255.255.255.0",
        "ip_gateway":"185.181.63.1"
        },
        {
        "ip_id":"7538",
        "sub_id":"404",
        "ip_v4v6":"ipv4",
        "ip_address":"185.181.62.21",
        "ip_reverse":"static.185.181.62.21.gigahost.no",
        "ip_traffic_sum":"0",
        "ip_pkts_sum":"0",
        "ip_nullroute":"0",
        "ip_routed_to":"7795",
        "ip_type":"extra",
        "ip_netmask":"255.255.255.0",
        "ip_gateway":"185.181.62.1"
        }
        ],
        "subnets":[
        {
        "sub_id":"2236",
        "sub_parent_id":"675",
        "srv_id":"3523",
        "device_id":"0",
        "sub_type":"ipv6",
        "sub_ipv6_type":"",
        "sub_network":"2a03:94e0:190e::",
        "sub_netmask":"48",
        "sub_broadcast":"",
        "sub_gateway":"2a03:94e0:19ff::1",
        "sub_cidr":"2a03:94e0:190e::/48",
        "sub_vlan":"1510",
        "sub_vrf":"1",
        "sub_description":"",
        "sub_location":"DC2",
        "sub_duid":"",
        "sub_ns":""
        },
        {
        "sub_id":"2237",
        "sub_parent_id":"675",
        "srv_id":"3523",
        "device_id":"0",
        "sub_type":"ipv6",
        "sub_ipv6_type":"",
        "sub_network":"2a03:94e0:190f::",
        "sub_netmask":"48",
        "sub_broadcast":"",
        "sub_gateway":"2a03:94e0:19ff::1",
        "sub_cidr":"2a03:94e0:190f::/48",
        "sub_vlan":"1510",
        "sub_vrf":"1",
        "sub_description":"",
        "sub_location":"DC2",
        "sub_duid":"",
        "sub_ns":""
        }
        ],
        "order":{
        "order_id":"3081",
        "payment_id":"4",
        "order_number":"3976",
        "order_date":"1528244467",
        "order_billing_type":"recurring",
        "order_billing_date":"06.07.2018",
        "order_billing_cycle":"1",
        "order_billing_days":"10",
        "order_status":"cancelled",
        "order_payment_status":"0",
        "order_total":"199.00",
        "order_cancel_reason":""
        },
        "attacklogs":[
        ],
        "cancelled":null,
        "node":"pmx4dc2",
        "bw_used":0,
        "bw_used_in":0,
        "bw_used_out":0,
        "location":[
        ],
        "ipmi_session":{
        "kvm_id":"12",
        "srv_id":"xxx",
        "kvm_ip_address":"185.125.168.xxx",
        "kvm_username":"xxx",
        "kvm_password":"xxx",
        "kvm_userid":"5",
        "kvm_expires":"1530717076",
        "kvm_in_use":"1"
        }
        }
        ]
        }

```

                        PUT

                            /servers/{id}/name

                            Update servers name

                        Parameters**server_id (numeric - inurl)name (string)**

POST

                            /servers/{id}/ipmi

                            Establish KVM/IPMI session

                        Sessions are valid for 3 hours at a time.

Parameters**server_id (numeric - inurl)acl (string - semi-colon separated list of ips and/or subnets)**

Example return data

```
        {
           "meta":{
              "status":200,
              "status_message":"200 OK"
           },
              "data":{
                 "kvm_ip_address":"185.125.168.xx",
                 "username":"xxxx",
                 "password":"xxxx"
           }
        }

```

                        GET

                            /servers/{id}/powerstate

                            Get servers powerstate

                        Parameters**server_id (numeric - inurl)**

Example return data

```
        {
           "meta":{
              "status":200,
              "status_message":"200 OK",
              "powerstate":true,
              "timestamp":1530706429
           }
        }

```

                        GET

                            /servers/{id}/reboot

                            Reboots server

                        Parameters**server_id (numeric - inurl)**

GET

                            /servers/{id}/power/on

                            Powers on server

                        Parameters**server_id (numeric - inurl)**

GET

                            /servers/{id}/power/off

                            Powers off server

                        Parameters**server_id (numeric - inurl)**

GET

                            /servers/{id}/snapshots

                            Get servers snapshots

                        Parameters**server_id (numeric - inurl)**

Example return data

```
        {
           "meta":{
              "status":200,
              "status_message":"200 OK"
           },
           "data":[{
              "snap_id": 123,
              "srv_id": 999,
              "snap_name":"Asdf1234",
              "snap_display_name":"my-snapshot",
              "snap_time": 1234567890,
              "snap_state": "pending" or "completed"
           }
        }

```

                        POST

                            /servers/{id}/snapshot

                            Create snapshot of server

                        Required parameters**
                                server_id (numeric - inurl)
                                name (string - descriptive name of snapshot)
                                **

Example return data

```
        {
           "meta":{
              "status":200,
              "status_message":"200 OK",
              "message":"Snapshot is currently being created.",
           }
        }

```

                        DELETE

                            /servers/{id}/snapshot/{snap-id}

                            Delete snapshot of server

                        Required parameters**
                                server_id (numeric - inurl)
                                snap_id (numeric - inurl)
                                **

Example return data

```
        {
           "meta":{
              "status":200,
              "status_message":"200 OK",
              "message":"Snapshot has been deleted.",
           }
        }

```

                        GET

                            /servers/{id}/port_bits

                            Get servers bandwidth graphs (base64 image)

                        Parameters**server_id (numeric - inurl)**

Format is base64 image data.

Example return data

```
        {
           "meta":{
              "status":200,
              "status_message":"200 OK"
           },
           "data":{
              "graph_day":"img-data (base64)",
              "graph_week":"img-data (base64)",
              "graph_month":"img-data (base64)",
              "graph_year":"img-data (base64)",
           }
        }

```

                        GET

                       /servers/{id}/port_upkts

                       Get servers packets graphs (base64 image)

                    Parameters**server_id (numeric - inurl)**

Format is base64 image data.

Example return data

```
        {
           "meta":{
              "status":200,
              "status_message":"200 OK"
           },
           "data":{
              "graph_day":"img-data (base64)",
              "graph_week":"img-data (base64)",
              "graph_month":"img-data (base64)",
              "graph_year":"img-data (base64)",
           }
        }

```

                    GET

                            /reinstall/distro

                            Get list of available distributions

                        Parameters**none**

Example return data

```
        {
           "meta":{
              "status":200,
              "status_message":"200 OK"
           },
           "data":[
           {
              "dist_id":"1",
              "type_id":"1",
              "dist_name":"CentOS",
              "dist_value":"centos",
              "dist_logo":"/images/os/centos.png",
              "dist_description":"",
              "dist_active":"1"
           }
        }

```

                        GET

                       /reinstall/distro/{id}

                       Get list of available operating systems

                    Parameters**none**

Example return data

```
        {
           "meta":{
              "status":200,
              "status_message":"200 OK"
           },
           "data":[
           {
              "os_id":"47",
              "dist_id":"1",
              "os_name":"CentOS 6 64-bit",
              "os_release":"centos",
              "os_dist":"6",
              "os_arch":"amd64",
              "os_custom_partition":"1",
              "os_single_disk_only":"0",
              "os_support_raid":"1",
              "os_dedicated_only":"0",
              "os_minram":"0"
           }
        }

```

                    POST

                            /servers/{id}/reinstall

                            Reinstall server

                        Required parameters**
                                server_id (numeric - inurl)
                                os_id (numeric - operating system id)
                                language (string - OS language, e.g. en_US, nb_NO)
                                keyboard (string - keyboard, e.g. no, en)
                                timezone (string - timezone, e.g. Europe/Oslo)
                          hostname (string - servers hostname)
                                **

Example return data

```
        {
           "meta":{
              "status":200,
              "status_message":"200 OK",
              "message":"Server install has been initiated.",
              "reboot":true,
              "root_passwd":"xxxxxx"
           }
        }

```

                        PUT

                            /servers/{id}/reverse

                            Update reverse DNS

                        Parameters**server_id (numeric - inurl)

                                For IPv4:
                                ip_id (numeric)
                                dns (string, e.g. server.mydomain.com)

                                For IPv6 (whole subnet, NS delegation):
                                sub_id (numeric - subnets id)
                                dns (string, e.g. ns1.gigahost.no)
                                **


GET

                       /servers/{id}/isos

                       Get list of uploaded ISOs

                    Parameters**none**

Example return data

```
        {
           "meta":{
              "status":200,
              "status_message":"200 OK"
           },
           "data":[
              {
                 "iso_id":"xxx",
                 "cust_id":"xxxx",
                 "iso_url":"http://xxxxx/debian-9.4.0-amd64-netinst.iso",
                 "iso_name":"debian-9.4.0-amd64-netinst.iso",
                 "iso_hash":"",
                 "iso_size":"0",
                 "iso_state":"uploading",
                 "iso_mounted":"0"
              }
           ]
        }

```

                    POST

                       /servers/{id}/isos

                       Upload ISO for mount

                    Parameters**server_id (numeric - inurl)
                          iso_id (string - iso_id)
                          **


GET

                       /servers/{id}/upgrade

                       Get list of available packages to upgrade to

                    Parameters**none**

Example return data

```
        {
           "meta":{
              "status":200,
              "status_message":"200 OK"
           },
           "data":[
              {
                 "pkg_id":"3",
                 "product_id":"2058",
                 "pkg_name":"kvm2048.2018.gigahost",
                 "pkg_cores":"2",
                 "pkg_ram":"2048",
                 "pkg_disk":"40",
                 "product_name":"KVM 2048",
                 "product_price":"199.00"
              },
              {
                 "pkg_id":"4",
                 "product_id":"2059",
                 "pkg_name":"kvm4096.2018.gigahost",
                 "pkg_cores":"4",
                 "pkg_ram":"4096",
                 "pkg_disk":"50",
                 "product_name":"KVM 4096",
                 "product_price":"299.00"
              }
           ]
        }

```

                    POST

                       /servers/{id}/upgrade

                       Upgrade server to another package

                    Parameters**server_id (numeric - inurl)
                          pkg_id (numeric - package id)
                          **


POST

                       /servers/{id}/ipv4

                       Order additional IP addresses

                    Parameters**server_id (numeric - inurl)
                          ip_type (string - "l2" or "l3")
                          **


Pass "l2" to receive a layer 2, non routed IP. Pass "l3" to receive a routed layer 3 IP.

PUT

                       /servers/{id}/ipv4/{ip_id}

                       Move a routed IP to another server

                    Moves an additional, routed (layer 3) IP from one of your servers to another. Only layer 3 IPs can be moved; layer 2 IPs cannot. Both servers must belong to your account and be in the same region. The destination server must already have a primary IP and fewer than 5 additional IPs. The IP's billing line moves to the destination server's order and follows that order's billing model and currency.

Required parameters**id (numeric - inurl - source server)
ip_id (numeric - inurl - the IP to move)
target_srv_id (numeric - destination server)
**

Example request body

```
{
   "target_srv_id":456
}

```

                       Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK",
      "message":"IP has been moved.",
      "ip_id":789,
      "target_srv_id":456
   },
   "data":{}
}

```

                       Error responses

```
// Invalid or same destination server
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "error":"Invalid destination server."
   }
}
// IP is not on the source server
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "error":"IP not found on this server."
   }
}
// IP is layer 2, not routed
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "error":"Only routed (L3) IPs can be moved."
   }
}
// Destination server is in a different region
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "error":"Destination server must be in the same region as the IP."
   }
}
// Destination server is at the additional IP limit
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "error":"Destination server has reached the maximum number of additional IPs. Contact support."
   }
}
// You do not own the destination server
{
   "meta":{
      "status":403,
      "status_message":"403 Forbidden",
      "error":"Access denied."
   }
}

```

                    GET

                            /my/account

                            Get your account

                        Parameters**None**

Example return data

```
        {
           "success":true,
           "cust_id":"1111",
           "cust_name":"name",
           "cust_company_no":"",
           "cust_address":"address",
           "cust_address2":"address2",
           "cust_province":"province",
           "cust_zipcode":"1111",
           "cust_city":"city",
           "cust_country":"country",
           "cust_phone":"number",
           "cust_email":"email",
           "cust_billing_email":"billing email",
           "cust_contacts":[
              {
                 "contact_id":"1",
                 "contact_name":"name",
                 "contact_email":"email",
                 "contact_phone":"number",
                 "contact_address":"address",
                 "contact_zip":"1111",
                 "contact_city":"city",
                 "contact_username":"username",
                 "contact_admin":"1"
              },
              {
                 "contact_id":"2",
                 "contact_name":"name",
                 "contact_email":"email",
                 "contact_phone":"number",
                 "contact_address":"address",
                 "contact_zip":"1111",
                 "contact_city":"city",
                 "contact_username":"username",
                 "contact_admin":"1"
              }
           ]
        }

```

                        GET

                            /my/invoices

                            Get your invoices

                        Parameters**None**

Example return data

```
        {
           "success":true,
           "invoices":[
              {
                 "inv_id":"xxxx",
                 "order_id":"xxxx",
                 "order_number":"xxxx",
                 "inv_md5":"xxx",
                 "inv_filename":"Invoice_xxxx.pdf",
                 "inv_number":"xxxx",
                 "inv_date":"1463004000",
                 "inv_duedate":"1463868000",
                 "inv_paid":"1",
                 "inv_total":"3240.00",
                 "inv_vat":810,
                 "inv_total_vat":4050
              }
           ]
        }

```

                        GET

        /deploy/servers

        Get the deployable server catalog

    Lists the server products available for deployment, grouped into tiers, together with the regions each product can be deployed in. Each product reports whether it can be ordered hourly (allow_hourly) and on a recurring term (allow_recurring), its current stock (in_stock), whether a sold-out product can still be built to order (built_to_order), and whether it can be reserved on the waitlist (waitlist_eligible). The eligibility object describes the account's payment standing so you can tell up front whether hourly deploys are allowed. Pricing is returned in NOK.

Parameters

{none}

Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK"
   },
   "data":{
      "tiers":[
         {
            "group_id":1,
            "group_name":"Cloud Servers",
            "in_stock":true,
            "products":[
               {
                  "product_id":101,
                  "product_hash":"a1b2c3d4",
                  "product_name":"Cloud 2",
                  "type":"vm",
                  "in_stock":true,
                  "built_to_order":false,
                  "waitlist_eligible":false,
                  "allow_hourly":true,
                  "allow_recurring":true,
                  "discount_year":15,
                  "setup":0,
                  "contract":0,
                  "vm_cores":"2",
                  "vm_memory":"4096",
                  "vm_storage":"80",
                  "vm_bw":"5",
                  "vm_bw_type":"TB",
                  "price_id":555,
                  "rate_hourly":0.123,
                  "rate_monthly":89,
                  "region_ids":[1,2]
               }
            ]
         }
      ],
      "regions":[
         {
            "region_id":1,
            "region_name":"Oslo",
            "region_name_short":"OSL",
            "region_country":"NO",
            "region_icon":"no",
            "region_active":"1"
         }
      ],
      "eligibility":{
         "verified":1,
         "has_method":true,
         "method_qualifies":true,
         "has_paid_invoice":true,
         "qualifies_arrears":true,
         "credit_nok":0
      },
      "currency":"NOK"
   }
}

```

    GET

        /deploy/status

        Get deployment status

    Poll this while servers are being provisioned. Works for both hourly and recurring orders. Status values are: waitlist, waiting, deploying, installing, ready, rescue and iso. A waitlist status means the order is reserved and deploys automatically once capacity frees up. The root password is only returned while a server is installing and no SSH key was supplied, or while it is in rescue mode.

Required parameters**
ids (string - inurl - comma-separated list of order IDs)
**

Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK"
   },
   "data":{
      "servers":[
         {
            "order_id":10001,
            "order_number":55001,
            "hostname":"web1.example.no",
            "srv_id":3500,
            "ip":"185.181.60.10",
            "ipv6":"2a03:94e0:ffff::10",
            "status":"ready",
            "password":""
         }
      ],
      "all_ready":true
   }
}

```

    GET

        /deploy/isos

        List your uploaded ISOs

    Only completed ISO uploads belonging to your account are returned. Use an iso_id from this list when deploying with a custom installation image.

Parameters

{none}

Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK"
   },
   "data":{
      "isos":[
         {
            "iso_id":"42",
            "iso_name":"debian-12.iso",
            "iso_size":"650000000"
         }
      ]
   }
}

```

    GET

        /deploy/waitlist

        List your waitlist reservations and notify signups

    Reservations are held orders that deploy automatically when capacity frees up, so they have no server yet and do not appear in the deployment status list. Notify-only signups record interest in a sold-out product and trigger an email when it is back in stock. Use the order_id of a reservation or the notify_id of a signup to cancel it.

Parameters

{none}

Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK"
   },
   "data":{
      "reservations":[
         {
            "order_id":10050,
            "order_number":55050,
            "product_name":"Cloud 2",
            "region_id":1,
            "region_name":"Oslo",
            "billing_type":"hourly",
            "total":89,
            "currency":"NOK",
            "reserved_at":1750000000
         }
      ],
      "notifications":[
         {
            "notify_id":7,
            "product_id":120,
            "product_name":"Dedicated AX41",
            "region_id":1,
            "region_name":"Oslo",
            "signed_up_at":1750000000
         }
      ]
   }
}

```

    DELETE

        /deploy/waitlist

        Cancel a reservation or remove a notify signup

    Pass exactly one of order_id (to cancel a held reservation) or notify_id (to remove a notify signup). Both are scoped to your account. A reservation can only be cancelled while it is still waiting; once it has been promoted and deployed it is no longer cancellable here.

Required parameters**
One of: order_id (numeric - reservation order ID) or notify_id (numeric - notify signup ID)
**

Example request body

```
{
   "order_id":10050
}

```

        Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK"
   },
   "data":{
      "success":true,
      "message":"Reservation cancelled."
   }
}

```

        Error responses

```
// Neither id supplied
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "error":"Provide order_id or notify_id."
   }
}
// Reservation already deployed or not found
{
   "meta":{
      "status":404,
      "status_message":"404 Not Found",
      "error":"Reservation was not found or is no longer cancellable."
   }
}
// Notify signup not found
{
   "meta":{
      "status":404,
      "status_message":"404 Not Found",
      "error":"Notification signup was not found."
   }
}

```

    POST

        /deploy/servers

        Deploy servers

    Queues one or more servers for provisioning. One order is created per server. Choose exactly one image option: an operating system (os_id), a custom ISO (iso_id), or rescue mode (rescue).

Use billing_period to pick how the server is billed. The default "hourly" is pay-as-you-go and requires either a qualifying card on file or a sufficient prepaid balance. The recurring terms "monthly", "quarterly" and "annual" create a real invoice per server, with any product setup fee and (annual only) the product's yearly discount; VAT is added for Norwegian customers.

For a sold-out product, use waitlist. "reserve" holds the order and deploys it automatically when capacity frees up (nothing is billed while it waits). "notify" creates no order and just emails you when the product is back in stock. If the product is actually in stock when the request arrives, the deploy proceeds normally and the waitlist value is ignored. Server auctions cannot be reserved.

Required parameters**
pid (numeric - product ID; or use hash)
hash (string - product hash; alternative to pid)
price_id (numeric - price ID for the product)
region_id (numeric - region to deploy in)
One of: os_id, iso_id or rescue
**

Optional parameters**
os_id (numeric - operating system to install)
iso_id (numeric - uploaded ISO to install from)
rescue (numeric - 0 or 1 to boot into rescue mode)
billing_period (string - "hourly" (default), "monthly", "quarterly" or "annual")
waitlist (string - "reserve" or "notify" for a sold-out product)
quantity (numeric - number of servers to deploy, default 1)
backups (numeric - 0 or 1 to enable backups, adds 25%)
auction_id (numeric - claim a specific server auction; forces quantity 1)
hostnames (array of strings - requested hostname per server)
ssh_keys (array of numeric - your SSH key IDs to authorize)
opts (object - selected product options)
**

Example request body

```
{
   "pid":101,
   "price_id":555,
   "region_id":1,
   "os_id":12,
   "quantity":2,
   "backups":1,
   "hostnames":["web1.example.no","web2.example.no"],
   "ssh_keys":[7,8]
}

```

        Example return data

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK"
   },
   "data":{
      "success":true,
      "message":"Servers queued for deployment.",
      "order_ids":[10001,10002],
      "order_numbers":[55001,55002],
      "quantity":2,
      "rate_hourly":0.123,
      "monthly_cap":89,
      "currency":"NOK"
   }
}

```

        Example return data (recurring term)

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK"
   },
   "data":{
      "success":true,
      "message":"Servers queued for deployment.",
      "order_ids":[10003],
      "order_numbers":[55003],
      "quantity":1,
      "billing_period":"annual",
      "term":12,
      "monthly":89,
      "setup":0,
      "discount":15,
      "vat":25,
      "currency":"NOK",
      "pending_payment":false,
      "under_review":false
   }
}

```

        Example return data (waitlist reserve)

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK"
   },
   "data":{
      "success":true,
      "mode":"reserve",
      "waitlisted":true,
      "message":"Reserved. Your server deploys automatically when capacity becomes available.",
      "order_ids":[10050],
      "order_numbers":[55050],
      "quantity":1,
      "rate_hourly":0.123,
      "monthly_cap":89,
      "currency":"NOK"
   }
}

```

        Example return data (waitlist notify)

```
{
   "meta":{
      "status":200,
      "status_message":"200 OK"
   },
   "data":{
      "success":true,
      "mode":"notify",
      "message":"We'll email you when this product is available again."
   }
}

```

        Error responses

```
// Missing or invalid required field
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "error":"Required field is invalid: region_id"
   }
}
// No image option selected
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "error":"Choose an operating system, an ISO, or rescue mode."
   }
}
// Profile incomplete
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "error":"Please complete your account profile before ordering."
   }
}
// Out of stock
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "error":"Not enough stock to deploy 2 server(s)."
   }
}
// Product cannot be ordered hourly
{
   "meta":{
      "status":403,
      "status_message":"403 Forbidden",
      "error":"This product cannot be ordered hourly."
   }
}
// Hourly not allowed without a qualifying method or prepaid balance
{
   "meta":{
      "status":403,
      "status_message":"403 Forbidden",
      "error":"Hourly servers require a non-prepaid card or PayPal on file plus at least one paid invoice on your account, or a prepaid balance covering one month of all your active hourly services.",
      "reason":"payment",
      "required":178,
      "balance":0,
      "currency":"NOK"
   }
}
// Recurring card charge declined (order and invoice are kept and retried)
{
   "meta":{
      "status":402,
      "status_message":"402 Payment Required",
      "error":"Your card was declined. The order is saved and we will retry payment; your server deploys once it is paid.",
      "reason":"payment_declined"
   }
}
// Server auction cannot be reserved
{
   "meta":{
      "status":400,
      "status_message":"400 Bad Request",
      "error":"Auctions cannot be reserved."
   }
}

```

    Manage web hosting accounts and everything inside them: email, databases, FTP, files, DNS, subdomains, SSL, one-click applications and backups.

Every account is identified by its **{id}** (the hosting account id from `GET /webhosting`). You can only access accounts that belong to you. Read operations need a token or API key with **read** access to webhosting; everything that creates, changes or deletes needs **read-write** access.

GET

        /webhosting

        List your web hosting accounts

    Example return data

```
{
   "meta": { "status": 200, "status_message": "200 OK" },
   "data": {
      "hosting": [
         {
            "hosting_id": 1234,
            "domain": "example.no",
            "username": "exampleno",
            "package": "Webhosting M",
            "status": "active",
            "created_date": "2026-01-15",
            "order_number": 55012,
            "order_renewal": "2026-07-15",
            "order_status": "active"
         }
      ]
   }
}

```

    GET

        /webhosting/{id}

        Get one hosting account

    Parameters**id (numeric, in URL) - hosting account id**

The response includes the domain, package, status, order information and current usage.

POST

        /webhosting

        Order a new hosting account

    Required parameters**
            zone_id (numeric) - the domain to host (a DNS zone you own)
            product_id (numeric) - the hosting package to order
            billing_period (numeric) - number of months: 1, 3, 6 or 12
        **

Optional parameters**
update_dns (numeric) - set to 1 to automatically create the standard web and mail DNS records for the domain
**

On success the account is created and a welcome email with the login details is sent. Returns status 201.

```
{
   "meta": { "status": 201, "status_message": "201 Created" },
   "data": {
      "message": "Webhosting account created successfully.",
      "hosting_id": 1234,
      "domain": "example.no",
      "username": "exampleno"
   }
}

```

    PUT

        /webhosting/{id}

        Upgrade the hosting package

    Required parameters**
            id (numeric, in URL) - hosting account id
            product_id (numeric) - the package to move to
        **

If there are more than 30 days left in the current billing period, a supplementary invoice is created for the price difference.

DELETE

        /webhosting/{id}/cancel

        Cancel a hosting account

    Required parameters**
            id (numeric, in URL) - hosting account id
            reason (string) - why the account is being cancelled
        **

Optional parameters**
early_termination (boolean) - set to true to terminate and delete the data immediately with no refund. When false (default) the account is scheduled to end on the next billing date and any unpaid, not-yet-due invoices are credited.
**

GET

        /webhosting/{id}/stats

        Account usage statistics

    Parameters**id (numeric, in URL) - hosting account id**

GET

        /webhosting/{id}/domains

        List additional domains on the account

    Parameters**id (numeric, in URL) - hosting account id**

GET

        /webhosting/{id}/emails

        List email accounts

    Parameters**id (numeric, in URL) - hosting account id**

POST

        /webhosting/{id}/emails

        Create an email account

    Required parameters**
            email (string) - the part before the @
            password (string)
        **

Optional parameters**
quota (numeric) - mailbox size in MB, 0 means unlimited
**

PUT

        /webhosting/{id}/emails/{email}/password

        Change an email password

    Required parameters**
            id (numeric, in URL) - hosting account id
            email (string, in URL) - the full email address
            password (string)
        **

PUT

        /webhosting/{id}/emails/{email}/quota

        Change an email quota

    Required parameters**
            id (numeric, in URL) - hosting account id
            email (string, in URL) - the full email address
            quota (numeric) - mailbox size in MB, 0 means unlimited
        **

DELETE

        /webhosting/{id}/emails/{email}

        Delete an email account

    Parameters**
            id (numeric, in URL) - hosting account id
            email (string, in URL) - the full email address
        **

GET

        /webhosting/{id}/email-forwarders

        List email forwarders

    Parameters**id (numeric, in URL) - hosting account id**

POST

        /webhosting/{id}/email-forwarders

        Create an email forwarder

    Required parameters**
            user (string) - the address to forward (part before the @)
            destinations (array or comma-separated string) - where to forward the mail
        **

PUT

        /webhosting/{id}/email-forwarders/{user}

        Update an email forwarder

    Required parameters**
            id (numeric, in URL) - hosting account id
            user (string, in URL) - the forwarding address
            destinations (array or comma-separated string)
        **

DELETE

        /webhosting/{id}/email-forwarders/{user}

        Delete an email forwarder

    Parameters**
            id (numeric, in URL) - hosting account id
            user (string, in URL) - the forwarding address
        **

GET

        /webhosting/{id}/email-catch-all

        Get the catch-all setting

    Parameters**id (numeric, in URL) - hosting account id**

PUT

        /webhosting/{id}/email-catch-all

        Update the catch-all setting

    Required parameters**
            catch (string) - the action, for example reject the mail or send it to one address
        **

Optional parameters**
value (string) - the email address to use when the action is to forward to a single address
**

GET

        /webhosting/{id}/autoresponders

        List autoresponders

    Parameters**id (numeric, in URL) - hosting account id**

GET

        /webhosting/{id}/autoresponders/{email}

        Get one autoresponder

    Parameters**
            id (numeric, in URL) - hosting account id
            email (string, in URL) - the email address
        **

POST

        /webhosting/{id}/autoresponders

        Create an autoresponder

    Required parameters**
            user (string) - the address (part before the @)
        **

Optional parameters**
subject (string) - reply subject
text (string) - reply message
cc (string) - ON or OFF, send a copy to the original sender
reply_once_time (string) - how often the same sender gets a reply, for example 2d
**

PUT

        /webhosting/{id}/autoresponders/{email}

        Update an autoresponder

    Parameters**
            id (numeric, in URL) - hosting account id
            email (string, in URL) - the email address
        **

Accepts the same fields as the create call.

DELETE

        /webhosting/{id}/autoresponders/{email}

        Delete an autoresponder

    Parameters**
            id (numeric, in URL) - hosting account id
            email (string, in URL) - the email address
        **

GET

        /webhosting/{id}/email-dkim

        Get DKIM status

    Parameters**id (numeric, in URL) - hosting account id**

PUT

        /webhosting/{id}/email-dkim

        Enable or disable DKIM

    Required parameters**
            id (numeric, in URL) - hosting account id
            enable (boolean) - true to enable, false to disable
        **

When the domain uses our DNS, the matching DNS record is updated automatically.

GET

        /webhosting/{id}/spamfilter

        Get spam filter settings

    Parameters**id (numeric, in URL) - hosting account id**

PUT

        /webhosting/{id}/spamfilter

        Update spam filter settings

    Optional parameters**
            where (string) - where spam is delivered
            required_hits (number) - score before a mail counts as spam
            high_score_block (string) - yes or no, block very high scoring mail
            high_score (number) - the score that counts as very high
            rewrite_subject (boolean) - add a tag to the subject of spam
            subject_tag (string) - the tag to add
            blacklist_from (string) - senders always treated as spam
            whitelist_from (string) - senders never treated as spam
        **

GET

        /webhosting/{id}/ftp

        List FTP accounts

    Parameters**id (numeric, in URL) - hosting account id**

POST

        /webhosting/{id}/ftp

        Create an FTP account

    Required parameters**
            username (string)
            password (string)
        **

Optional parameters**
path (string) - a folder to limit the account to, relative to the website root. Leave empty for full access.
**

PUT

        /webhosting/{id}/ftp/{ftp_user}/password

        Change an FTP password

    Required parameters**
            id (numeric, in URL) - hosting account id
            ftp_user (string, in URL) - the FTP username
            password (string)
        **

DELETE

        /webhosting/{id}/ftp/{ftp_user}

        Delete an FTP account

    Parameters**
            id (numeric, in URL) - hosting account id
            ftp_user (string, in URL) - the FTP username
        **

GET

        /webhosting/{id}/databases

        List databases

    Parameters**id (numeric, in URL) - hosting account id**

POST

        /webhosting/{id}/databases

        Create a database

    Required parameters**
            name (string) - database name
            password (string) - password for the database user
        **

PUT

        /webhosting/{id}/databases/{dbname}/password

        Change a database password

    Required parameters**
            id (numeric, in URL) - hosting account id
            dbname (string, in URL) - database name
            password (string)
        **

DELETE

        /webhosting/{id}/databases/{dbname}

        Delete a database

    Parameters**
            id (numeric, in URL) - hosting account id
            dbname (string, in URL) - database name
        **

POST

        /webhosting/{id}/subdomain

        Create a subdomain

    Required parameters**
            id (numeric, in URL) - hosting account id
            subdomain (string) - the subdomain name, without the main domain
        **

DELETE

        /webhosting/{id}/subdomain/{name}

        Delete a subdomain

    Parameters**
            id (numeric, in URL) - hosting account id
            name (string, in URL) - the subdomain name
        **

All paths are relative to the account home directory.

GET

        /webhosting/{id}/files/tree

        Get the folder tree

    Parameters**
            id (numeric, in URL) - hosting account id
            path (string, query) - folder to start from, default /
        **

GET

        /webhosting/{id}/files/list

        List files in a folder

    Parameters**
            id (numeric, in URL) - hosting account id
            path (string, query) - folder to list, default /
            page (numeric, query) - page number, default 1
            ipp (numeric, query) - items per page, default 50
        **

GET

        /webhosting/{id}/files/edit

        Read a file

    Parameters**
            id (numeric, in URL) - hosting account id
            path (string, query) - full path to the file
        **

GET

        /webhosting/{id}/files/download

        Download a file

    Parameters**
            id (numeric, in URL) - hosting account id
            path (string, query) - full path to the file
        **

The file is returned as a download.

POST

        /webhosting/{id}/files/save

        Save a file

    Required parameters**
            path (string) - the folder
            filename (string) - the file name
        **

Optional parameters**
text (string) - the file contents
**

POST

        /webhosting/{id}/files/rename

        Rename a file or folder

    Required parameters**
            path (string) - the folder it is in
            old (string) - current name
            filename (string) - new name
        **

POST

        /webhosting/{id}/files/folder

        Create a folder

    Required parameters**
            path (string) - the parent folder
            name (string) - folder name
        **

POST

        /webhosting/{id}/files/create

        Create an empty file

    Required parameters**
            path (string) - the folder
            filename (string) - the file name
        **

POST

        /webhosting/{id}/files/delete

        Delete files or folders

    Required parameters**
            paths (array) - the paths to delete
        **

POST

        /webhosting/{id}/files/upload

        Upload files

    Send the request as multipart form data.

Required parameters**
files (file, one or more) - the files to upload
**

Optional parameters**
path (string) - target folder, default /
**

Install and manage common web applications with one click, and back them up.

GET

        /webhosting/{id}/installations

        List installed applications

    Parameters**id (numeric, in URL) - hosting account id**

GET

        /webhosting/{id}/apps/available

        List available applications

    Parameters**id (numeric, in URL) - hosting account id**

POST

        /webhosting/{id}/install

        Install an application

    Required parameters**
            app (string) - the application id from the available list
        **

Optional parameters**
domain (string) - where to install it, default the main domain
path (string) - folder to install into, default /
admin_username (string) - default admin
admin_password (string) - generated for you if left out
admin_email (string) - default the account email
site_title (string)
**

The admin login is returned in the response.

POST

        /webhosting/{id}/install/{installId}/update

        Update an application

    Parameters**
            id (numeric, in URL) - hosting account id
            installId (string, in URL) - the installation id
        **

GET

        /webhosting/{id}/install/{installId}/backups

        List application backups

    Parameters**
            id (numeric, in URL) - hosting account id
            installId (string, in URL) - the installation id
        **

Each backup includes an id, date, size, version and type.

GET

        /webhosting/{id}/install/{installId}/backuplocations

        List backup destinations

    Parameters**
            id (numeric, in URL) - hosting account id
            installId (string, in URL) - the installation id
        **

POST

        /webhosting/{id}/install/{installId}/backups

        Back up or restore an application

    Required parameters**
            action (string) - backup or restore
        **

When action is backup**
location (string, optional) - where to store it: default is the account itself, or new for an external server
ftp (object, required when location is new):
  type (string) - ftp, ftps or sftp
  host (string)
  port (numeric, optional)
  user (string)
  pass (string, optional)
  path (string, optional)
**

When action is restore**
backup (string) - the backup id to restore
**

GET

        /webhosting/{id}/install/{installId}/backups/{backupId}/download

        Download an application backup

    Parameters**
            id (numeric, in URL) - hosting account id
            installId (string, in URL) - the installation id
            backupId (string, in URL) - the backup id
        **

The backup is returned as a download.

DELETE

        /webhosting/{id}/install/{installId}/backups

        Delete an application backup

    Required parameters**
            id (numeric, in URL) - hosting account id
            installId (string, in URL) - the installation id
            backup (string) - the backup id to delete
        **

DELETE

        /webhosting/{id}/install/{installId}

        Uninstall an application

    Parameters**
            id (numeric, in URL) - hosting account id
            installId (string, in URL) - the installation id
        **

GET

        /webhosting/{id}/ssl

        Get the SSL certificate

    Parameters**id (numeric, in URL) - hosting account id**

The response includes whether SSL is enabled, the certificate details if one is installed, and the list of valid hostnames.

POST

        /webhosting/{id}/ssl

        Request a free SSL certificate

    Required parameters**
            hostnames (array) - the hostnames to secure, all under the main domain
        **

Optional parameters**
keysize (string) - secp384r1 (default), secp256r1 or rsa_4096
**

The certificate is usually issued within a minute.

DELETE

        /webhosting/{id}/ssl

        Remove the SSL certificate

    Parameters**id (numeric, in URL) - hosting account id**

These cover the whole hosting account, separate from the per-application backups above.

GET

        /webhosting/{id}/backups

        List site backups

    Parameters**id (numeric, in URL) - hosting account id**

POST

        /webhosting/{id}/backups

        Create or restore a site backup

    Required parameters**
            action (string) - backup or restore
        **

When action is restore**
filename (string) - the backup file to restore
**

DELETE

        /webhosting/{id}/backups

        Delete a site backup

    Required parameters**
            id (numeric, in URL) - hosting account id
            filename (string) - the backup file to delete
        **
