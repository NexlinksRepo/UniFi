# UniFi NextDNS Device Names v2.0.0

Experimental external integration for the inspected ARM64 UniFi gateway. This is
not a native UniFi feature, and PostgreSQL access is not a supported public API.
The package keeps the five-minute trial and requires an explicit commit.

## What changed

- Discovers every dnscrypt-proxy TOML file and dnsmasq forwarder configuration in
  the inspected native runtime locations, and checks matching supervised processes.
  No fixed WAN-interface names or WAN-listener ports are assumed.
- Resolves forwarding chains to their NextDNS destinations and prints each
  instance, configured listening interfaces, listener port, profile, and path.
- Uses a separate registry per NextDNS profile. Names and 80-bit stable IDs are
  attached per HTTP request, so concurrent requests and profiles do not share
  attribution state. Conflicting names/current address ownership are omitted.
- Reconciles missing managed blocks after native DNS configuration regeneration.
  Only the managed settings are added; native caching and connection-mark
  directives remain. Native routes and firewall rules are not changed.
- Commit enables an external systemd boot service. Discovery and binary checks
  run again on boot. Unsupported changes disable the integration and restore stock.

Native UniFi configuration generation is outside this package's control. The
reconciler reapplies its external settings after generation, with a possible
short gap in enrichment. Reboot, real ISP failover, and firmware-upgrade coverage
must not be inferred from fixture tests. See TEST-RESULTS.md for actual validation.

## Supported scope and refusal behavior

The stock binary must match the SHA-256 in manifest.json. The current compatibility
baseline is the inspected Dream Machine Pro Max, UniFi OS 6.0.15 and Network
11.0.97, using dnscrypt-proxy 2.1.14. The candidate is Linux ARM64.

Discovery presently supports IPv4 loopback encrypted-proxy listeners, explicit
single upstreams, and the native default system-resolver chain through
127.0.0.1:53. All selected upstream stamps must be NextDNS DoH. Multiple proxy
instances and profiles are supported by the discovery/registry model. Other DNS
providers, conditional DNS, ambiguous multiple upstreams, nested configuration
includes, privilege drops, unmatched processes, IPv6 loopback proxy listeners,
and unsupported layouts are rejected before installation. Do not bypass refusal.
This is comprehensive discovery within that supported layout, not universal
support for every possible resolver implementation.

WAN forwarders are pointed at the same terminal encrypted-proxy destination that
their original chain resolves to. This avoids losing client identity through the
extra main-forwarder hop. Their native listener, caching, and connection-mark
directives remain, but this is a change to the local forwarding hop. Validate
your WAN-policy behavior before commit.

## Install, verify, then commit

Extract the ZIP locally and copy the folder to the gateway:

```powershell
scp -r .\UniFi_NextDNS_Device_Names_v2.0.0 root@<gateway-ip>:/tmp/
ssh root@<gateway-ip>
```

On the gateway:

```sh
cd /tmp/UniFi_NextDNS_Device_Names_v2.0.0
sh discover.sh
sh test.sh
sh install.sh
```

The explicit test starts an isolated proxy and verifies UDP/TCP DNS plus header
proof for two named clients. Test queries may appear in NextDNS. Installation
briefly restarts DNS processes. It prints discovered paths first and prints
ENABLED only after configuration and listener validation. That output does not
prove a real client used each interface; validate the LAN path separately.

The trial expires after five minutes unless you commit. During the trial, check
NextDNS names, the UniFi portal, and WAN policies. Use two named devices where
possible. From a LAN computer:

```powershell
python .\probe-client.py --router <gateway-ip>
python .\probe-client.py --router <gateway-ip> --port <detected-WAN-port>
```

Add --tcp for TCP. Compare the printed query hash against the gateway's
/run/nextdns-device-names-v2/proof.json and verify its device name. This is a
proxy proof record, not a NextDNS dashboard API readback. Repeat from relevant
LAN/VLAN interfaces; the installer cannot generate a real client on every VLAN.

When ready, explicitly commit:

```sh
sh commit.sh
sh status.sh
```

Commit enables the external boot service. An expired or inactive trial cannot
be committed. Installation alone does not enable persistence across reboot.
Unknown/unsupported changes cause stock fallback rather than repeated restarts.

## Disable enrichment and restore stock

```sh
sh disable.sh
# rollback.sh is an alias
```

If the extracted package is unavailable:

```sh
python3 /data/nextdns-device-names-v2/v2.py disable
```

Disable stops and disables the boot service, removes only complete managed
blocks, restores the stock executable view, and restarts affected native DNS.
It preserves subsequent native configuration edits. If forwarder recovery fails,
the metadata-stripping proxy is retained and errors are reported. Resolve those
errors before deleting runtime files. Disable before firmware changes.

## Name sources

The default is the read-only PostgreSQL method evaluated with v1. It depends on
the inspected private config.user_client schema on port 5434 and is explicitly
not a documented UniFi public API. A schema/access failure disables the
integration rather than silently trusting stale identities. DHCP and live
neighbor information supplement address matching. Registry data expires after
90 seconds. Names and IDs are disclosed to NextDNS; raw MAC metadata is stripped
from local DNS options before upstream forwarding in the supported path.

An optional adapter targets UniFi's official Network Integration API. It has
fixture tests but requires your version's localized API documentation and a
live read-only key for validation. Create /data/nextdns-device-names-v2/settings.json:

```json
{
  "name_source": "api",
  "api_url": "https://your-trusted-console/proxy/network/integration",
  "api_key_file": "/data/nextdns-device-names-v2/api-key",
  "api_ca_file": "/data/nextdns-device-names-v2/console-ca.pem"
}
```

The key file must be owner-only (chmod 600). TLS certificates must validate;
redirects are refused. The adapter requires data/totalCount pagination and
usable macAddress/name/ipAddress records. It refuses unknown schemas. No key
is included in this package. The PostgreSQL backend remains the tested default.

Official API introduction:
https://help.ui.com/hc/en-us/articles/30076656117655-Getting-Started-with-the-Official-UniFi-API

## Diagnostics and rebuilding

```sh
journalctl -u nextdns-device-names-v2.service --no-pager -n 60
python3 -m unittest discover -s tests -v
chmod 755 bin/proxy-tests-linux-arm64
bin/proxy-tests-linux-arm64 -test.v -test.run '^TestNextDNS'
sh build-and-test.sh
```

The full source and source patch retain upstream license notices. controller.py
contains v1 helper functions and regression tests; operator entry points use
v2.py. Do not invoke the legacy controller as an installer.

Scheduled manager checks refresh identity, inspect/reconcile topology, and check
proxy TCP listeners. They do not send synthetic DNS questions or prove continuous
cloud connectivity. No separate 24-hour diagnostic collector is bundled.

Stable device enrichment follows the provider's documented header mechanism:
https://help.nextdns.io/t/x2h76ay/device-information-log-enrichment
