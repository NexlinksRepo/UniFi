# UniFi projects

## Latest version: NextDNS Device Names v3.0.0 (experimental)

Experimental external integration that adds UniFi client names and profile-scoped
device IDs to NextDNS DNS-over-HTTPS requests. This is not a native UniFi feature
or an official Ubiquiti/NextDNS package.

- [Download the v3.0.0 package](packages/UniFi_NextDNS_Device_Names_v3.0.0.zip)
- [Usage instructions](nextdns-device-names/UniFi_NextDNS_Device_Names_v3.0.0/README.md)
- [Source and tests](nextdns-device-names/UniFi_NextDNS_Device_Names_v3.0.0/)
- [Requirements and limitations](nextdns-device-names/UniFi_NextDNS_Device_Names_v3.0.0/V3-REQUIREMENTS.md)
- [Package validation](nextdns-device-names/UniFi_NextDNS_Device_Names_v3.0.0/TEST-RESULTS.md)
- [Current validation and upgrade notes](docs/v3-validation.md)
- [Changelog](CHANGELOG.md)
- [Version history](docs/versions.md)

### Scope

The compatibility baseline is an inspected Dream Machine Pro Max running UniFi OS
6.0.15 and UniFi Network 11.0.97, with an exact stock dnscrypt-proxy 2.1.14 binary
hash check. Discovery enumerates the supported local proxy/forwarder layout and
refuses ambiguous or unsupported paths. It is not universal support for all
gateways, firmware, or resolver arrangements.

The installer prints detected forwarder instances, configured listening
interfaces, ports, and NextDNS paths. It retains a five-minute trial and an
explicit commit step. Commit enables an external systemd service to restore the
integration after reboot and reconcile supported generated-configuration changes.

### What v3 fixes

Routine client-name refreshes now keep the current valid registry enabled while
the replacement is prepared, then publish it atomically. Failed source lookups
never extend the old expiry. Changed attribution scope, expired/invalid data,
and failed health checks retain the fail-closed behavior.

The five-minute trial and explicit commit remain. Disable v2 before installing
v3; v3 uses separate service/runtime paths and is not silently installed over v2.

**Validation:** 85 Python tests passed locally and on the ARM64 gateway. The native
NextDNS Go tests and isolated UDP/TCP/header diagnostics passed. The user reports
that committed v3 survived a gateway reboot, as v2 did. This v3 result has not
been independently checked through SSH. Long-duration validation remains open.
See the current validation notes above.

The default name lookup uses read-only access to UniFi's private PostgreSQL
schema, not a supported public interface. The optional official API adapter has
fixture validation only. Native UniFi configuration generation remains outside
the package's control.

Read the usage and validation limits before installation. Expect a brief DNS
interruption during activation or rollback. Confirm real client names and UniFi
cloud access during the trial before committing.

### Package integrity

The uploaded ZIP is the existing v3.0.0 artifact, without modifications:

```text
SHA-256: 89f8c203088137e8cdb36e6d6f9db6d428896352f02be8d47636112547a0ec34
```

The package also contains SHA256SUMS and a manifest with candidate/stock binary
hashes. The source tree mirrors that archive. Later field observations are
documented separately so the original artifact and its validation history remain
clear.

### Licensing

The repository's existing [LICENSE](LICENSE) is retained. The bundled upstream
code retains its [ISC license notice](nextdns-device-names/UniFi_NextDNS_Device_Names_v3.0.0/LICENSE)
and [third-party notices](nextdns-device-names/UniFi_NextDNS_Device_Names_v3.0.0/THIRD_PARTY_LICENSES.txt).
Preserve the applicable notices when redistributing the source or archive.

Private gateway logs, operational credentials, actual NextDNS profile configuration, and
diagnostic archives are not included in this repository.
