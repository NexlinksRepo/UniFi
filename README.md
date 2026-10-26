# UniFi projects

## NextDNS Device Names v2.0.0

Experimental external integration that adds UniFi client names and profile-scoped
device IDs to NextDNS DNS-over-HTTPS requests. This is not a native UniFi feature
or an official Ubiquiti/NextDNS package.

- [Download the v2.0.0 package](packages/UniFi_NextDNS_Device_Names_v2.0.0.zip)
- [Usage instructions](nextdns-device-names/UniFi_NextDNS_Device_Names_v2.0.0/README.md)
- [Source and tests](nextdns-device-names/UniFi_NextDNS_Device_Names_v2.0.0/)
- [Requirements and limitations](nextdns-device-names/UniFi_NextDNS_Device_Names_v2.0.0/V2-REQUIREMENTS.md)
- [Package validation](nextdns-device-names/UniFi_NextDNS_Device_Names_v2.0.0/TEST-RESULTS.md)
- [Subsequent field validation](docs/v2-field-validation.md)

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

**Reboot behavior:** a committed v2 installation was verified to start
automatically after an actual gateway reboot on October 25, 2026. An uncommitted
five-minute trial is not enabled for startup. The ZIP's original TEST-RESULTS.md
is a build-time validation snapshot that predates this field test; use the
[subsequent field-validation note](docs/v2-field-validation.md) for current results.

The default name lookup uses read-only access to UniFi's private PostgreSQL
schema, not a supported public interface. The optional official API adapter has
fixture validation only. Native UniFi configuration generation remains outside
the package's control.

Read the usage and validation limits before installation. Expect a brief DNS
interruption during activation or rollback. Confirm real client names and UniFi
cloud access during the trial before committing.

### Package integrity

The uploaded ZIP is the existing v2.0.0 artifact, without modifications:

```text
SHA-256: 75bb5e13e2805c93db04c109138eb4ef6ce5c56a3e8928f360d983d34854e70f
```

The package also contains SHA256SUMS and a manifest with candidate/stock binary
hashes. The source tree mirrors that archive. Later field observations are
documented separately so the original artifact and its validation history remain
clear.

### Licensing

The repository's existing [LICENSE](LICENSE) is retained. The bundled upstream
code retains its [ISC license notice](nextdns-device-names/UniFi_NextDNS_Device_Names_v2.0.0/LICENSE)
and [third-party notices](nextdns-device-names/UniFi_NextDNS_Device_Names_v2.0.0/THIRD_PARTY_LICENSES.txt).
Preserve the applicable notices when redistributing the source or archive.

Private gateway logs, operational credentials, actual NextDNS profile configuration, and
diagnostic archives are not included in this repository.
