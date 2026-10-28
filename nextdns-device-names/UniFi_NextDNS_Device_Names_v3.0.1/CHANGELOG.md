# Changelog

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


## 3.0.0 - 2026-10-25 (experimental)

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

## 2.0.0 - 2026-10-25

- Added local resolver/forwarder discovery, profile-scoped registries, an external
  configuration reconciler, five-minute trials, explicit commit and boot startup.
- Added an installer summary of interfaces, listener ports, and NextDNS paths.
- Read-only PostgreSQL remains private-schema compatibility access; the optional
  official API adapter is fixture-tested. This is external software, not native
  UniFi support.
- Subsequent field checks verified one committed gateway reboot and a Network
  application restart. Those v2 observations are not v3 field validation.
