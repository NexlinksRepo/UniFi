# NextDNS version history

**Latest available: v3.0.0 experimental. Stable: none published.**

## v2.0.0 — Beta

[GitHub beta pre-release](https://github.com/NexlinksRepo/UniFi/releases/tag/nextdns-device-names%2Fv2.0.0) — entry created October 26, 2026.

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

## v3.0.0 — Experimental

[GitHub experimental pre-release](https://github.com/NexlinksRepo/UniFi/releases/tag/nextdns-device-names%2Fv3.0.0) — entry created October 26, 2026.

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

## v3.0.1 — Planned stable

The next planned version is v3.0.1, intended to be labelled stable when
published. No download, tag, runtime changes, or validation record exists for
v3.0.1 as part of this reorganization.

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

[Project overview](../README.md) · [Project changelog](../CHANGELOG.md) · [Repository releases](../../RELEASES.md)
