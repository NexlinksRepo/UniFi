# v2.0.0 validation, October 25, 2026

Status: experimental external package for controlled trial. No production v2
installation or commit was performed during this validation.

## Completed checks

- Full patched Go proxy suite passed on Windows using Go 1.27.3.
- Linux ARM64 candidate and native test executable cross-compiled successfully.
- Eleven NextDNS Go test groups passed on the actual ARM64 gateway, including
  concurrent per-request headers, redirect restrictions, metadata stripping,
  malformed/expired registries, multiple profile isolation, and profile parsing.
- Current local Python suite: 71 tests passed. It includes the inherited v1
  regressions and v2 graph discovery, unknown/conflicting identities, API adapter
  pagination/schema validation, repeated regeneration protection, recovery
  ordering, five-minute trial expiry, and commit-time expiry checks.
- The same current 71-test Python suite also passed on the ARM64 gateway.
- All files in the staged release passed SHA256SUMS verification on the gateway.
- Read-only gateway discovery found main, eth8, and eth9 forwarders on ports 53,
  20201, and 20202. Each configuration listed br0 and br2 as listening interfaces.
- The candidate's isolated loopback UDP/TCP and two-client HTTP-header proof
  diagnostic passed against the gateway's existing NextDNS configuration.
- TCP listener checks passed for all discovered native frontend addresses/ports.
- The visible native executable retained its original pinned stock SHA-256, and
  the v2 manager service was inactive after isolated diagnostics.

Some negative unit tests deliberately print an ERROR about committing an expired
trial. Fixture lifecycle tests may print a successful trial/commit message. These
messages come from mocked tests, not from installation on the gateway.

## Boundaries

Native regeneration is reproduced through a transaction fixture that removes the
managed block, then checks reapplication and preservation of native settings.
This is not evidence of a live UniFi DNS Shield refresh under an active v2 trial.

Real v2 production cutover, reboot persistence, service-crash recovery under
systemd, a full-duration field run, real WAN failover, IPv6 frontend DNS, every
client/VLAN's attribution, and cloud portal continuity during v2 activation have
not been verified. The five-minute trial and explicit commit are retained so
those operational checks can be performed deliberately.

The official Integration API adapter has fixture tests only; no API key was
provided. The PostgreSQL compatibility backend was exercised by the live
isolated diagnostic. It remains a private schema dependency.

V1-TEST-RESULTS.md contains earlier package history only. Its production checks
must not be represented as v2 production validation. See V2-REQUIREMENTS.md for
the distinction between implemented external behavior and requested native UniFi
functionality.
