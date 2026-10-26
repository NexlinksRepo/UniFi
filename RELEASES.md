# Release directory

## NextDNS Device Names

| Channel | Version | Download | Source and instructions | Validation |
| --- | --- | --- | --- | --- |
| Stable | None published | — | — | — |
| Beta | v2.0.0 | [Original ZIP](packages/UniFi_NextDNS_Device_Names_v2.0.0.zip) | [v2 README](nextdns-device-names/UniFi_NextDNS_Device_Names_v2.0.0/README.md) | [v2 field results](nextdns-device-names/docs/v2-field-validation.md) |
| Experimental | v3.0.0 | [Original ZIP](packages/UniFi_NextDNS_Device_Names_v3.0.0.zip) | [v3 README](nextdns-device-names/UniFi_NextDNS_Device_Names_v3.0.0/README.md) | [v3 validation and upgrade notes](nextdns-device-names/docs/v3-validation.md) |
| Planned stable | v3.0.1 | Not published | Planned next version | No v3.0.1 validation recorded |

**Latest available: v3.0.0 experimental.** "Latest" identifies the newest version,
not a stable recommendation. There is no stable NextDNS release at present.

v2.0.0 is classified as beta and v3.0.0 as experimental. These labels were
documented on October 26, 2026; the original October 25, 2026 package dates,
contents, checksums, and validation records are preserved. Historical READMEs
inside those snapshots retain their original wording.

## Release naming

Use a project prefix for Git tags because this repository can contain multiple projects:

- `nextdns-device-names/v2.0.0` — beta pre-release.
- `nextdns-device-names/v3.0.0` — experimental pre-release.
- `nextdns-device-names/v3.0.1` — reserved here as the planned next stable version; not yet published or tagged.

The version number and maturity status are recorded separately. Keep v2.0.0 and
v3.0.0 unchanged rather than renaming the existing packages with new suffixes.
Future patch versions increment from v3.0.1. A stable label describes the
release's documented support and validation scope, not universal compatibility.

See [GitHub Releases](https://github.com/NexlinksRepo/UniFi/releases),
[project change history](nextdns-device-names/CHANGELOG.md), and
[version history](nextdns-device-names/docs/versions.md).

## Repository update — October 26, 2026

- Established the top-level README as a directory for UniFi projects.
- Put current NextDNS documentation and change history in the project folder.
- Added explicit beta, experimental, stable, and planned-version navigation.
- Preserved existing source snapshots, ZIP paths, licenses, and validation history.
- Kept the former top-level documentation URLs as links to the project documentation.
- Recorded v3.0.1 as planned stable without creating a new software version.

This update reorganizes documentation and release metadata. It does not change
runtime code or add new gateway validation.
