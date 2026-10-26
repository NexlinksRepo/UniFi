# NextDNS Device Names

Add UniFi client names and profile-scoped device IDs to NextDNS DNS-over-HTTPS
requests. This is an independent external integration, not an official
Ubiquiti/NextDNS package or native UniFi feature.

## Choose a version

| Channel | Version | Download | Instructions | Validation |
| --- | --- | --- | --- | --- |
| Stable | None published | — | — | — |
| Beta | v2.0.0 | [ZIP](../packages/UniFi_NextDNS_Device_Names_v2.0.0.zip) | [v2 usage](UniFi_NextDNS_Device_Names_v2.0.0/README.md) | [v2 field results](docs/v2-field-validation.md) |
| Experimental | v3.0.0 | [ZIP](../packages/UniFi_NextDNS_Device_Names_v3.0.0.zip) | [v3 usage](UniFi_NextDNS_Device_Names_v3.0.0/README.md) | [v3 validation and upgrade](docs/v3-validation.md) |
| Planned stable | v3.0.1 | Not published | Planned next version | No validation recorded |

**Newest available: v3.0.0 experimental. No stable release is published.**
v3.0.1 is the planned next stable version, not an available download.

v3 fixes the interval when ordinary v2 registry refreshes temporarily disabled
device-name enrichment. It prepares a replacement while the current valid
registry remains enabled, then publishes the file atomically. Failed lookups
do not extend old data's expiry. Attribution changes, expired data, and unsafe
health/discovery conditions still disable enrichment.

## Start here

- [Version history and release status](docs/versions.md)
- [Change history](CHANGELOG.md)
- [Validation and upgrade documentation](docs/README.md)
- [Repository release directory](../RELEASES.md)
- [GitHub Releases](https://github.com/NexlinksRepo/UniFi/releases)
- [Machine-readable version directory](releases.json)

## Requirements and validation limits

The inspected baseline is a Dream Machine Pro Max with UniFi OS 6.0.15, Network
11.0.97, Linux ARM64, and an exact dnscrypt-proxy 2.1.14 stock binary hash check.
Discovery rejects unsupported or ambiguous layouts. The default name source
uses read-only access to UniFi's private PostgreSQL schema; the optional
official API adapter has fixture validation only.

Both versions require a five-minute trial and an explicit commit. Read the
version-specific README and requirements before installation. Disable v2 before
installing v3; the two versions use separate service/runtime paths.

v2 has documented gateway reboot and Network application restart observations.
v3 has 85 recorded Python test passes, Go/native tests, and isolated DNS/header
checks. The owner reports that committed v3 survived a reboot; that report has
not been independently checked through SSH. Long-duration stability, the exact
DNS Shield server-list-refresh event, and other limits remain open.

## Files and historical packages

- `docs/` contains the current version directory, validation, and upgrade notes.
- `CHANGELOG.md` records changes for this project.
- `releases.json` records beta, experimental, stable, and planned versions.
- `UniFi_NextDNS_Device_Names_v2.0.0/` and
  `UniFi_NextDNS_Device_Names_v3.0.0/` preserve the original source and tests.
- Existing ZIPs stay at `../packages/` so published download URLs remain valid.

Experimental, beta, and stable are release statuses, not separate source
folders. Historical package READMEs and checksums describe their original
snapshots; this page and the version directory carry the current classification.

## License and privacy

The repository [LICENSE](../LICENSE) is retained. Each version includes its
upstream ISC license and third-party notices. Preserve the applicable notices
when redistributing code or archives.

Names and device IDs are sent to NextDNS by the integration. Actual profile
configuration, device identities, private gateway logs, and credentials are
excluded from this public repository.
