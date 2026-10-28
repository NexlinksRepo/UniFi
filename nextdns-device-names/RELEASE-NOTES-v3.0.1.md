## v3.0.1 stable — October 28, 2026

This is the stable release of the v3 runtime, scoped to the known-good Dream
Machine Pro Max running **UniFi OS 6.0.16** and **UniFi Network 11.0.97**
(Network package 11.0.97-37231-1; UniFi Core 6.0.130; dnscrypt-proxy 2.1.14).
These versions were checked through SSH on October 28, 2026. The package
enforces the expected stock binary hash before activation; while active, the
proxy path contains the patched candidate, whose SHA-256 matched its manifest.
It remains an independent external integration alongside UniFi OS and Network.
Stable is the project release classification, not official vendor support.

### Verified behavior

- Committed v3 survives a gateway reboot: owner-confirmed and subsequently
  checked through SSH with the service active, desired state committed, registry
  enabled, and no health failures.
- Survives native DNS Shield server-list regeneration/restart. Captured October
  26 at 21:23:25 Eastern with reconciliation at 21:23:29, and October 27 at
  21:23:56 with reconciliation at 21:23:59. Surrounding 20-second samples
  retained enabled registries with zero failures or alerts.
- v3.0.1 retains the v3.0.0 runtime and proxy binaries; this patch updates release
  metadata and documentation. It does not introduce a runtime behavior change.

### Known limitations and untested scenarios

- DNS resolution or device-name enrichment may be interrupted while native
  regeneration and external reconciliation occur. Allow for a possible brief
  gap on the order of the 20-second monitoring interval; **20 seconds is not a
  measured outage or a guaranteed maximum**. Reconciliation completed in about
  3–4 seconds in the captured events, but passive samples cannot prove continuous
  client DNS service between samples. This limitation follows from operating
  outside and alongside UniFi OS and the Network application.
- **Network application upgrades and other OS upgrade paths remain untested.**
  The 6.0.15 → 6.0.16 observation is recorded below. Changes
  to the native binary or private PostgreSQL schema may disable enrichment.
- Other gateway/firmware combinations, actual ISP failover, IPv6 frontend
  coverage, and the optional official API adapter against a live gateway remain
  unvalidated. The default PostgreSQL interface is private and unsupported.
- The extended passive monitoring window is still in progress; its final report
  is not claimed as completed validation.

The five-minute installation trial, explicit commit, health rollback, and
option to disable enrichment remain. v3.0.1 uses the existing v3 service and
runtime paths. No in-place upgrade: disable the existing installation before
starting a new trial. Publishing this package does not upgrade the gateway.

### UniFi OS upgrade observation — October 28, 2026

The owner upgraded the Dream Machine Pro Max from UniFi OS 6.0.15 to **6.0.16**
(build `UDMPROMAX.al324.v6.0.16.8ea8e65.261028.1047`). Network remained
**11.0.97**, package `11.0.97-37231-1`.

Read-only SSH checks confirmed the gateway booted at 16:22:41 Eastern and the
committed NextDNS v3 service started automatically at 16:23:25. At 17:41,
the service and registry were active, desired state was enabled/committed,
health and registry-refresh failures were zero, and no service warnings appeared
in the preceding 30 minutes. The registry contained 98 IP and 81 MAC mappings.

This is a successful **6.0.15 → 6.0.16 upgrade observation on one gateway**,
using the installed v3.0.0 runtime that v3.0.1 preserves unchanged. It is not
proof of uninterrupted DNS during the upgrade or general future-upgrade support;
no synthetic client DNS probes were sent. Network application upgrades remain
untested. Known-good observed OS versions are 6.0.15 and 6.0.16 with Network
11.0.97. The published v3.0.1 ZIP remains its original build-time snapshot.
