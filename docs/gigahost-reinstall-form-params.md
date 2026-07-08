# Gigahost Reinstall API — Undocumented Parameters

Discovered 2026-07-08 by capturing the Flux web panel's form POST to
`POST /servers/{id}/reinstall`. The API docs only list the required params.

## Source: Captured POST payload

```json
{
  "os_id": "108",
  "key_id": "2524",
  "hostname": "bulletins-dev",
  "language": "en_US",
  "keyboard": "us",
  "timezone": "Europe/Oslo",
  "firstboot": "echo%20%22slipp-provisioned%20%24(date)%22%20%3E%20%2Froot%2F.slipp-firstboot",
  "boot_mode": "efi",
  "part_mode": "custom",
  "part_layout": "{\"installer_type\":\"preseed\",\"boot_mode\":\"efi\",\"drive_groups\":[{\"drives\":[\"23029\"],\"raid_level\":null,\"use_lvm\":false,\"partitions\":[{\"mount\":\"/boot/efi\",\"fs\":\"fat32\",\"size_gb\":0.5},{\"mount\":\"/boot\",\"fs\":\"ext4\",\"size_gb\":1},{\"mount\":\"swap\",\"fs\":\"swap\",\"size_gb\":4},{\"mount\":\"/\",\"fs\":\"ext4\",\"size_gb\":34.5,\"fill\":true}]}]}",
  "part_config": "<base64 preseed config>",
  "part": ""
}
```

## Parameter reference

### Documented (required)

| Param | Type | Description |
|-------|------|-------------|
| `os_id` | string | OS version ID (from `GET /reinstall/distro/{id}`) |
| `hostname` | string | Server hostname |
| `language` | string | OS language, e.g. `en_US`, `nb_NO` |
| `keyboard` | string | Keyboard layout, e.g. `us`, `no` |
| `timezone` | string | Timezone, e.g. `Europe/Oslo` |

### Undocumented (optional, discovered from web UI)

| Param | Type | Description |
|-------|------|-------------|
| `key_id` | string | SSH key ID from `GET /account` → `sshkeys[].key_id`. Injects into root's `authorized_keys` during install. **This is the correct param name** — `ssh_key`, `ssh_keys`, `sshkey` are all silently ignored. |
| `firstboot` | string | Shell script executed on first boot. URL-encoded in the web form. Could inject bootstrap commands. |
| `boot_mode` | string | `"efi"` or `"bios"`. Defaults to EFI. |
| `part_mode` | string | `"custom"` or empty (automatic partitioning). |
| `part_layout` | JSON string | Custom partition layout: drives, RAID, LVM, mount points, filesystems, sizes. |
| `part_config` | base64 string | Preseed/kickstart partition config. |
| `part` | string | Empty when using custom partitioning. |

## Notes

- All values are **strings** in the web form, even numeric IDs (`"108"` not `108`).
- The response `meta.sshkey` field reflects whether a key was actually injected (`true`/`false`).
- The `key_id` corresponds to keys managed via `POST /account/sshkey` (upload) and visible in `GET /account` → `sshkeys[]`.
- The account's SSH key field names are `key_id`, `key_name`, `key_data`, `key_added` (not `id`, `name`, `data`).

## slipp uses

| Param | Used | Notes |
|-------|------|-------|
| `os_id` | Yes | User picks distro + version interactively |
| `key_id` | Yes | SSH key injection — eliminates password-based login |
| `hostname` | Yes | Project name |
| `language` | Yes | Default `en_US` |
| `keyboard` | Yes | Default `us` |
| `timezone` | Yes | Default `Europe/Oslo` |
| `firstboot` | Potential | Could inject bootstrap script to avoid post-install SSH setup |
| `boot_mode` | No | Default EFI is fine |
| `part_mode` | No | Automatic partitioning |
| `part_layout` | No | No custom disk layouts |
| `part_config` | No | No custom preseed/kickstart |

## Abort endpoint (undocumented)

```
POST /servers/{id}/reinstall/abort
```

Cancels an in-progress OS reinstall. No request body needed. Returns 200 on
success. Discovered by capturing the Flux panel's "Avbryt installasjon" button.

## Findings from live testing (2026-07-08)

- **`key_id` works** — reinstall with `key_id` (no `firstboot`) returned
  `sshkey: true` and empty `root_passwd`. SSH key auth confirmed working.
- **`firstboot` can hang the install** — a reinstall with a firstboot script
  (`echo "..." > /root/.slipp-firstboot`) never completed after 30+ minutes.
  Same reinstall without firstboot completed in under 3 minutes. The script
  may block the preseed late_command or cloud-init phase. Avoid until the
  execution context is better understood.
- **Install timing** — API-triggered reinstalls (no custom partitioning)
  complete in 2-5 minutes. Web-form reinstalls with custom partitioning can
  take much longer.
