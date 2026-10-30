# NextDNS Device Names
**Latest stable: v3.0.1**, published October 28, 2026. [Release notes](RELEASE-NOTES-v3.0.1.md) include reboot/DNS Shield results, known-good versions, and upgrade limitations.

Add UniFi client names and profile-scoped device IDs to NextDNS DNS-over-HTTPS
requests. This is an independent external integration, not an official
Ubiquiti/NextDNS package or native UniFi feature.

## Choose a version

| Channel | Version | Download | Instructions | Validation |
| --- | --- | --- | --- | --- |
| Stable | v3.0.1 | [ZIP](../packages/UniFi_NextDNS_Device_Names_v3.0.1.zip) | [Usage](UniFi_NextDNS_Device_Names_v3.0.1/README.md) | [Validation](docs/v3.0.1-validation.md) |
| Beta | [v2.0.0](https://github.com/NexlinksRepo/UniFi/releases/tag/nextdns-device-names%2Fv2.0.0) | [ZIP](../packages/UniFi_NextDNS_Device_Names_v2.0.0.zip) | [v2 usage](UniFi_NextDNS_Device_Names_v2.0.0/README.md) | [v2 field results](docs/v2-field-validation.md) |
| Experimental | [v3.0.0](https://github.com/NexlinksRepo/UniFi/releases/tag/nextdns-device-names%2Fv3.0.0) | [ZIP](../packages/UniFi_NextDNS_Device_Names_v3.0.0.zip) | [v3 usage](UniFi_NextDNS_Device_Names_v3.0.0/README.md) | [v3 validation and upgrade](docs/v3-validation.md) |


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

The inspected baseline is a Dream Machine Pro Max with UniFi OS 6.0.16, Network
11.0.99, Linux ARM64, and an exact dnscrypt-proxy 2.1.14 stock binary hash check.
Discovery rejects unsupported or ambiguous layouts. The default name source
uses read-only access to UniFi's private PostgreSQL schema; the optional
official API adapter has fixture validation only.

Both versions require a five-minute trial and an explicit commit. Read the
version-specific README and requirements before installation. Disable v2 before
installing v3; the two versions use separate service/runtime paths.

Committed v3 reboot and two DNS Shield regeneration events have been verified.
The owner also upgraded UniFi OS 6.0.15 → 6.0.16; SSH checks confirmed automatic
service recovery and healthy enrichment afterward. Network remained 11.0.97.
Network 11.0.97 → 11.0.99 immediate post-upgrade operation was verified October 30.
Other application and OS upgrade paths remain untested. See the
v3.0.1 release notes for evidence and limitations. The stable patch preserves
the v3 runtime.

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

Current upgrade evidence: Network **11.0.99** (11.0.99-37236-1), UniFi OS
**6.0.16**, Core **6.0.130**, dnscrypt-proxy **2.1.14**, checked October 30.
See the current v3.0.1 release notes for immediate post-upgrade findings and limits.
