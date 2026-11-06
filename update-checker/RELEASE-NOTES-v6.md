# UniFi Update Checker v6 stable

Release date: November 6, 2026. Status: **latest stable**, designated by the project owner. Supersedes v5; prior versioned files are preserved.

## Changes from v5

- No-version discovery and numbered selection for Network and UniFi OS, plus target-specific menus and explicit-version arguments.
- Installed Network and OS detection, installed-entry labels, and an early exit for an already installed selection.
- Authenticated firmware enumeration with HAL pagination handling, architecture filtering for Network, and exact console product/platform filtering for OS.
- Recursive exact `unifi-*` dependencies from both Depends and Pre-Depends; full parent-platform matching, conflict/cycle tracking, and fail-closed handling of missing or ambiguous packages.
- Identical dependency artifacts repeated under multiple channels are consolidated by product, platform, version, URL and checksum metadata. Genuinely distinct artifacts remain ambiguous.
- Required API checksum verification, actual Debian package identity/version/architecture verification, and no arbitrary fallback build.
- One complete local package set for APT simulation and installation; removals forbidden, and post-install version checks required.
- Exact selected OS URL passed to the firmware updater after the same default-No confirmation.
- Unique restricted working directories, temporary token header cleanup and a concurrent-v6 lock.

## APT notice correction — November 6, 2026

After verification, v6 removes the token header and makes only the downloaded packages readable to APT through a root-owned traversable directory. This addresses the `_apt` permission notice without disabling the APT sandbox or hiding output. Other working files retain private permissions.

## Validation on November 6, 2026

- Bash syntax passed locally and on a Dream Machine Pro Max; staged script checksums matched.
- Simulated checks passed for exact recursive dependencies, duplicate channels, conflicting artifacts, platform mismatch, checksum failures, unavailable dependencies, wrong Debian versions, failed APT dry runs and declined installation.
- Owner-provided console output showed authenticated Network discovery and successful checksum/metadata verification of Network 11.1.47-37925-1 (`uos-deb13-arm64`, beta). The original script then stopped on duplicated Matter 1.0.0 records before APT installation.
- A read-only authenticated query confirmed that Matter Controller 1.0.0 appeared under beta, release-candidate and release with the same download URL and SHA256. This established the cause of the refusal and informed the correction.
- Read-only package status confirmed Matter Controller 1.0.0 installed. The correction was staged and syntax checked without running an updater or installing packages.

The owner subsequently supplied APT output showing successful Network 11.1.47-37925-1 installation and installed Matter Controller 1.0.0, then confirmed the application looks healthy. This is owner-reported evidence rather than independently observed end-to-end execution. The later APT readability correction has not been exercised during a live installation. UniFi OS installation, reboot, rollback and broad hardware compatibility remain unverified. An API record is not evidence of normal rollout eligibility. All returned channels, including beta and older versions, may be shown.

## Use and limitations

See the [complete guide](README-unifi-rollout-check-v6.md). Back up configuration, review release notes and required intermediate upgrades, and use a maintenance window. APT simulation does not test runtime health or application data migration. Firmware handling is delegated to `ubnt-systool`; OS mode has no APT simulation or local firmware checksum pass.
