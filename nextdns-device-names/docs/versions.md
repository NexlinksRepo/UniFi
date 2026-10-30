# NextDNS version history
**Latest stable: v3.0.1**, published October 28, 2026. [Release notes](../RELEASE-NOTES-v3.0.1.md) include reboot/DNS Shield results, known-good versions, and upgrade limitations.


## v2.0.0 â€” Beta

[GitHub beta pre-release](https://github.com/NexlinksRepo/UniFi/releases/tag/nextdns-device-names%2Fv2.0.0) â€” entry created October 26, 2026.

- [Download original v2 ZIP](../../packages/UniFi_NextDNS_Device_Names_v2.0.0.zip)
- [Source and tests](../UniFi_NextDNS_Device_Names_v2.0.0/)
- [Installation](../UniFi_NextDNS_Device_Names_v2.0.0/README.md)
- [Build-time validation](../UniFi_NextDNS_Device_Names_v2.0.0/TEST-RESULTS.md)
- [Later field validation](v2-field-validation.md)

Beta classification documented October 26, 2026. Original package date:
October 25, 2026. v2 includes discovery, profile-scoped registries, a five-minute
trial, explicit commit, and an external boot/reconciliation service. Its ordinary
refresh can briefly disable enrichment; v3 addresses that interval. The beta
label does not remove the documented limitations.

## v3.0.0 â€” Experimental

[GitHub experimental pre-release](https://github.com/NexlinksRepo/UniFi/releases/tag/nextdns-device-names%2Fv3.0.0) â€” entry created October 26, 2026.

- [Download original v3 ZIP](../../packages/UniFi_NextDNS_Device_Names_v3.0.0.zip)
- [Source and tests](../UniFi_NextDNS_Device_Names_v3.0.0/)
- [Installation](../UniFi_NextDNS_Device_Names_v3.0.0/README.md)
- [Build-time validation](../UniFi_NextDNS_Device_Names_v3.0.0/TEST-RESULTS.md)
- [Later validation and upgrade notes](v3-validation.md)

Original package date: October 25, 2026. v3 fixes ordinary registry-refresh gaps
while retaining expiry, attribution, health, trial, and rollback safeguards.
It remains experimental. See the validation notes for completed checks and open limits.

Original ZIP SHA-256:

```text
89f8c203088137e8cdb36e6d6f9db6d428896352f02be8d47636112547a0ec34
```

## v3.0.1 — Stable

Published October 28, 2026. [Download](../../packages/UniFi_NextDNS_Device_Names_v3.0.1.zip),
[usage](../UniFi_NextDNS_Device_Names_v3.0.1/README.md), and
[validation/limitations](v3.0.1-validation.md).

Promotes the unchanged v3 runtime after reboot and DNS Shield regeneration
observations. Known-good UniFi OS 6.0.15 and Network 11.0.97; Network app upgrades and other OS upgrade paths
are untested; 6.0.15 → 6.0.16 recovery was observed on October 28. See release notes for the possible reconciliation interruption.

## History and naming

Experimental, beta, and stable are explicit statuses. Version numbers alone do
not establish maturity. Project-prefixed tags use
`nextdns-device-names/v<version>`; beta and experimental releases are pre-releases.

Each GitHub pre-release links to the original project ZIP. GitHub's automatic
source archives include the whole repository, so use the project download link.

The archives and their exact source snapshots retain their original contents,
checksums, and dated validation records. Historical READMEs retain their original
wording; this directory records the current release classifications.

v1.0.2 is an earlier prototype discussed in historical test notes. Its package
is not published in this repository.

[Project overview](../README.md) Â· [Project changelog](../CHANGELOG.md) Â· [Repository releases](../../RELEASES.md)

Current upgrade evidence: Network **11.0.99** (11.0.99-37236-1), UniFi OS
**6.0.16**, Core **6.0.130**, dnscrypt-proxy **2.1.14**, checked October 30.
See the current v3.0.1 release notes for immediate post-upgrade findings and limits.
