# Update Checker changelog

## v6 stable — November 6, 2026

Follow-up: remove the firmware token header after package discovery and permit `_apt` to traverse the root-owned working directory and read verified packages, avoiding its permission/root-fallback notice without hiding diagnostics. Record owner-reported successful Network 11.1.47 installation and healthy application observation.

Latest stable, designated by the project owner. Adds version-free discovery menus, installed-version labels, stricter exact dependency resolution and verification, full-platform dependency matching, and consolidation of identical dependency artifacts repeated across channels. Preserves interactive approval and the complete local APT transaction; OS mode uses the selected exact URL.

See [v6 release notes](RELEASE-NOTES-v6.md) for changes, observed evidence and unverified installation paths.

## v5 stable — October 26, 2026

Previous stable release. Exact-version discovery, recursive UniFi dependencies, APT dry run and interactive installation, and console-specific OS firmware handling. Original script and guide are retained unchanged. The original publication recorded owner-reported testing; it did not establish independent live-console testing during import.
