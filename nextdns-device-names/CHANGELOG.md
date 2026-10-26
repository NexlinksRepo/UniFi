# Changelog

**Latest available: v3.0.0 (experimental). Beta: v2.0.0. Stable: none published.**

[Downloads and status](README.md) · [Version history](docs/versions.md)

## Planned — v3.0.1 (stable)

The next planned version is v3.0.1, intended to be labelled stable when published.
It has not been built, tagged, or released. No v3.0.1 changes or validation are
claimed by this documentation update.

## Repository organization — 2026-10-26

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
