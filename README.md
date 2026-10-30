# UniFi projects
**Latest stable: v3.0.1**, published October 28, 2026. [Release notes](nextdns-device-names/RELEASE-NOTES-v3.0.1.md) include reboot/DNS Shield results, known-good versions, and upgrade limitations.

Independent UniFi administration tools and integrations by Phil Kinsley.

## Project directory

| Project | Purpose | Stable | Beta | Experimental |
| --- | --- | --- | --- | --- |
| [Update Checker](update-checker/) | Discover and optionally install UniFi application and OS updates. | [v5 stable](update-checker/README.md) | — | — |
| [NextDNS Device Names](nextdns-device-names/) | Add UniFi client names and profile-scoped device IDs to NextDNS DNS-over-HTTPS requests. | [v3.0.1 stable](nextdns-device-names/) | [v2.0.0](nextdns-device-names/docs/versions.md#v200--beta) | [v3.0.0](nextdns-device-names/docs/versions.md#v300--experimental) |


- [Release directory and repository updates](RELEASES.md)
- [NextDNS downloads, status, and usage](nextdns-device-names/README.md)
- [NextDNS changelog](nextdns-device-names/CHANGELOG.md)
- [NextDNS validation and upgrade notes](nextdns-device-names/docs/README.md)
- [GitHub Releases](https://github.com/NexlinksRepo/UniFi/releases)

## Repository layout

```text
UniFi/
  README.md                  Project directory
  RELEASES.md                Version/status directory and repository updates
  CHANGELOG.md               Link to project change history
  LICENSE                    Repository license
  update-checker/            UniFi Update Checker v5 stable script and usage guide
  nextdns-device-names/
    README.md                Project overview and downloads
    CHANGELOG.md             NextDNS changes
    releases.json            Project version/status metadata
    docs/                    Validation, version history, and upgrade notes
    UniFi_NextDNS_Device_Names_v2.0.0/  Original v2 source and tests
    UniFi_NextDNS_Device_Names_v3.0.0/  Original v3 source and tests
  packages/                  Existing published ZIP download URLs
  docs/                      Compatibility links to project documentation
  latest.json                Compatibility metadata for the newest NextDNS package
```

Each project has a permanent folder. Experimental, beta, and stable are release
statuses rather than separate copies of a project's files. Existing versioned
source snapshots and ZIPs retain their published contents and paths. Future
projects should keep their documentation and tests inside their own project folder.

## NextDNS scope

NextDNS Device Names is an external integration, not a native UniFi feature or
an official Ubiquiti/NextDNS package. The inspected compatibility baseline is a
Dream Machine Pro Max running UniFi OS 6.0.16 and UniFi Network 11.0.99, with an
exact stock dnscrypt-proxy 2.1.14 binary hash check. It is not universal gateway
or firmware support.

Both available versions retain a five-minute trial and explicit commit step.
Read the version-specific requirements, validation limits, and upgrade
instructions before installation. Beta status does not remove the limitations
recorded for v2, and the v3 refresh fix does not establish long-duration stability.

## License and privacy

See [LICENSE](LICENSE). Bundled upstream code retains its own license and
third-party notices; preserve those notices when redistributing it.

Private gateway logs, credentials, actual NextDNS profile configuration, and
diagnostic archives are excluded from this repository.

Current upgrade evidence: Network **11.0.99** (11.0.99-37236-1), UniFi OS
**6.0.16**, Core **6.0.130**, dnscrypt-proxy **2.1.14**, checked October 30.
See the current v3.0.1 release notes for immediate post-upgrade findings and limits.
