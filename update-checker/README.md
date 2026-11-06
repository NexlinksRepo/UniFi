# UniFi Update Checker — v6 stable

**Latest stable: v6**, designated by the project owner on November 6, 2026.

Discover UniFi Network packages and UniFi OS firmware through the console's authenticated update service. Run without a version to choose from a numbered menu, or supply a target and version. Currently installed versions are displayed and matching entries are marked.

- [Download the v6 script](https://raw.githubusercontent.com/NexlinksRepo/UniFi/main/update-checker/unifi-rollout-check-v6.sh)
- [Complete v6 setup, usage, dependencies and safety guide](README-unifi-rollout-check-v6.md)
- [v6 release notes and validation scope](RELEASE-NOTES-v6.md)
- [Project changelog](CHANGELOG.md)
- [File checksums](SHA256SUMS)

```bash
chmod +x unifi-rollout-check-v6.sh
./unifi-rollout-check-v6.sh
# Or: ./unifi-rollout-check-v6.sh unifi 11.0.83
# Or: ./unifi-rollout-check-v6.sh unifi-os 6.0.12
```

Run as root directly on a UniFi OS console. Network mode recursively prepares exact UniFi dependencies, verifies package identity and checksums, and runs an APT dry run before asking for installation approval. Identical artifacts repeated across channels are treated as one dependency; distinct conflicting builds still stop the run. Dependencies retain the selected parent's full platform.

OS mode uses the console's product/platform and invokes `ubnt-systool fwupdate` with the selected exact firmware URL only after confirmation. The console may reboot. Both paths default to declining installation.

Stable is the owner's release classification. Syntax and simulated safety checks passed, and limited live-console discovery evidence is documented. The corrected full installation workflow has not been independently verified end to end. Read the complete guide before proceeding.

## Previous release

[v5 script](unifi-rollout-check-v5.sh) and [v5 guide](README-unifi-rollout-check-v5.md) remain unchanged for historical use. v6 is the current stable version.
