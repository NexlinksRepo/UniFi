# v3.0.0 validation and upgrade notes

**Latest version: v3.0.0 (experimental).** Prepared October 25, 2026.

v3 fixes the disabled-registry interval observed during ordinary v2 refreshes.
It prepares the replacement while the existing unexpired registry remains
available and publishes the complete file atomically. A failed source lookup
cannot extend the old expiry. Attribution changes and unsafe health/discovery
conditions still disable enrichment.

## Completed

- 85 Python tests passed locally, from the extracted release archive, and on the
  ARM64 gateway. Fourteen new tests cover the refresh fix and its safety limits.
- The full Go proxy suite passed locally. Native ARM64 NextDNS test groups passed.
- The isolated candidate passed UDP/TCP DNS and two-client header diagnostics.
- The staged ZIP and all included file checksums were verified on the gateway.
- Stock DNS remained active during isolated validation; v3 was staged without a
  production install or commit by the investigator.

Some negative unit tests intentionally print errors about expired trials, and
mocked lifecycle tests print successful trial/commit messages. Those outputs are
not evidence that the package installed itself on the gateway.

## Upgrade

Disable the currently running version before installing v3. For v2:

```sh
python3 /data/nextdns-device-names-v2/v2.py disable
```

Then extract the v3 package and start its five-minute trial:

```sh
cd /tmp/UniFi_NextDNS_Device_Names_v3.0.0
sh test.sh
sh install.sh
```

Verify client names, DNS resolution, UniFi cloud access, and applicable WAN
policies. Only when ready:

```sh
sh commit.sh
```

The v3 install directory, runtime registry, and service are versioned separately
from v2. No in-place upgrade or automatic commit is performed. The code remains
an external integration using the private PostgreSQL compatibility backend by
default, with an optional official API adapter requiring live validation.

## Limits

Production v3 reboot recovery, the exact native DNS Shield server-list-refresh
event, actual ISP failover, IPv6 frontend coverage, and long-duration stability
remain unverified. [v2's field results](v2-field-validation.md) establish what was
observed on v2 only and should not be presented as v3 results.

The release ZIP's TEST-RESULTS.md is its build-time record. This page adds later
staging validation without changing the published archive bytes.
