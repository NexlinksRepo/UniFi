# Changelog

**Latest stable: v3.0.1. Beta: v2.0.0. Experimental: v3.0.0.**

[Downloads and status](README.md) Â· [Version history](docs/versions.md)

Current checked compatibility: UniFi OS **6.0.16**, Network **11.0.99**
(package 11.0.99-37236-1), UniFi Core **6.0.130**, dnscrypt-proxy **2.1.14**.

### Network application upgrade observation — October 30, 2026

Package logs confirm Network upgraded from **11.0.97-37231-1** to
**11.0.99-37236-1** at 10:15:33 Eastern and completed installation at 10:17:49.
The Network service was active/running with that same activation timestamp.
UniFi OS remained **6.0.16** and UniFi Core remained **6.0.130**; the gateway
boot time remained October 28 at 16:22:41 Eastern.

Read-only SSH checks at 10:21–10:22 Eastern found the committed v3 enrichment
service active, with its activation timestamp unchanged from October 28 at
16:23:25. Health and registry-refresh failure counters were zero, last_error
was null, and the name registry was enabled and unexpired (101 IP mappings,
83 MAC mappings). All three discovered forwarders remained managed. The active
dnscrypt-proxy reported **2.1.14** and its SHA-256 matched the existing patched
candidate manifest. No enrichment service warning/error journal entries were
returned for the preceding two hours.

This records successful immediate post-upgrade operation for **Network
11.0.97 → 11.0.99 on UniFi OS 6.0.16** on this Dream Machine Pro Max. It does
not establish uninterrupted client DNS during installation, correct attribution
of every live request, or long-duration stability on 11.0.99. No synthetic DNS
probes or restarts were performed. Other application/OS upgrade paths remain
untested. The installed runtime remains v3.0.0, unchanged in stable v3.0.1;
the release ZIP and original build-time records are preserved.

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

## v3.0.1 stable — October 28, 2026

This is the stable release of the v3 runtime, scoped to the known-good Dream
Machine Pro Max running **UniFi OS 6.0.15** and **UniFi Network 11.0.97**
(Network package 11.0.97-37231-1; stock dnscrypt-proxy 2.1.14 hash is enforced).
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
- **Network application upgrades and UniFi OS upgrades are untested.** Reboot
  and DNS Shield refresh results do not establish upgrade compatibility. Changes
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

## Repository organization â€” 2026-10-26

- Classified existing v2.0.0 as beta and v3.0.0 as experimental.
- Grouped current documentation and change history under this project folder.
- Preserved original source snapshots, archives, checksums, and package dates.
- Kept former documentation URLs as compatibility links.

The status labels do not add runtime changes or new validation to either package.

## 3.0.0 - 2026-10-25 (experimental)

### Field validation

- The user reports that committed v3 survived a gateway reboot, as v2 did.
  This result has not been independently verified through SSH.

### Fixed

- Routine client-name refreshes no longer write `enabled: false` before reading
  the client source. The current valid registry remains available while the new
  data is prepared, and the replacement is published with an atomic file rename.
- A transient name-source failure can retain the last valid registry only while
  its original expiry remains valid, attribution scope is unchanged, and native
  listener checks pass. Failed refreshes never extend the old data's expiry.
- First observation by the manager and native comment/cache changes no longer
  disable an already active registry when attribution boundaries are unchanged.

### Safety retained

- Profile, upstream target, listener, and interface changes invalidate the old
  attribution scope. Unsupported discovery and failed listener/binary checks
  still disable enrichment and use the existing recovery path.
- Expired, disabled, malformed, or incorrectly scoped registries are not reused.
- Explicit disable/rollback continues to disable names before restoring stock.
- The five-minute install trial and explicit commit remain.

### Packaging

- Versioned v3 service/runtime paths prevent a v3 trial from silently replacing
  a running v2 installation. Disable v2 before installing v3; no in-place upgrade
  or automatic commit is performed.
- Added regression coverage for atomic refresh, failed/expired replacement,
  attribution changes, manager startup, and explicit disable.

## 2.0.0 - 2026-10-25 (beta)

Beta classification documented October 26, 2026. The original package date and
build-time records remain unchanged.

- Added local resolver/forwarder discovery, profile-scoped registries, an external
  configuration reconciler, five-minute trials, explicit commit and boot startup.
- Added an installer summary of interfaces, listener ports, and NextDNS paths.
- Read-only PostgreSQL remains private-schema compatibility access; the optional
  official API adapter is fixture-tested. This is external software, not native
  UniFi support.
- Subsequent field checks verified one committed gateway reboot and a Network
  application restart. Those v2 observations are not v3 field validation.
