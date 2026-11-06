# UniFi rollout checker v6 stable

Discover UniFi Network packages and UniFi OS firmware using the console's own authenticated update API, then select a build without knowing its version beforehand. Based on the [stable v5 design](https://github.com/NexlinksRepo/UniFi/blob/main/update-checker/unifi-rollout-check-v5.sh).

**Latest stable: v6**, designated by the project owner on November 6, 2026. Supersedes v5. [Release notes and validation scope](RELEASE-NOTES-v6.md).

## Run on the console

Copy `unifi-rollout-check-v6.sh` to your UniFi OS console and run it as root with Bash 4 or later:

```bash
chmod +x unifi-rollout-check-v6.sh
./unifi-rollout-check-v6.sh
```

The script displays the installed Network version, current OS version, console architecture, product/platform and configured release channel. It queries both catalogs and presents one numbered list. Each entry includes the target, API version, platform and channel. Choose a number, or enter `q` to exit. Invalid selections are rejected. Network and OS updates are separate runs; selecting one does not install the other.

Target-specific menus and explicit targets are also supported:

```bash
./unifi-rollout-check-v6.sh menu
./unifi-rollout-check-v6.sh unifi
./unifi-rollout-check-v6.sh unifi-os
./unifi-rollout-check-v6.sh unifi 11.0.83
./unifi-rollout-check-v6.sh unifi-os 6.0.12
./unifi-rollout-check-v6.sh --help
```

`os` and `uos` are aliases for `unifi-os`. A bare three-part version selects matching API builds, including build suffixes; a supplied suffix must match exactly. When multiple builds match, you choose from a numbered menu. A unique explicit match goes directly to preparation, with installation still requiring confirmation.

## Discovery and applicability

The token is read from `/data/unifi-core/config/firmware.yaml` and sent as `Authorization: Bearer token:...` to `https://fw-update.ubnt.com/api/firmware`. The token is not printed or sent to package download URLs. A temporary restricted header file is removed on normal exit or a handled error. Do not run with shell tracing (`bash -x`), which can expose credentials. A forced kill or power loss may leave the header file in the working directory; treat that directory as sensitive.

Network entries must have product `unifi` and an API platform ending in the console's Debian architecture, following v5. OS entries must match the exact product and platform in the YAML `latest` section. Missing OS identity stops OS-only mode; combined mode reports the omission and can still show Network results. These fields identify the console firmware family; the YAML's latest version is **not** used as the installed version.

The script requests up to 10,000 entries per query, follows same-service HAL next links, deduplicates builds, and stops if a page repeats, a pagination link is unexpected, or a full page has no next link. It does not invent versions or scan guessed version numbers. The API may limit results or change its undocumented schema; “all” means all applicable records returned by that authenticated service, not every historical or unpublished Ubiquiti release. Discovery does not prove upgrade compatibility, eligibility for normal rollout, or vendor support.

No channel filter is applied: returned release, candidate or early-access builds can all appear, with their channels shown. The configured channel is informational. Rollout probability, product, platform, version, release date and exact URL are displayed for the selected build. Review the channel and release notes before choosing. Architecture matching alone does not establish compatibility with the console's OS/Debian generation; multiple platform variants are kept as separate choices.

## Installed-version detection

Network uses `dpkg-query` and requires `install ok installed` status. UniFi OS uses the `Firmware:` line from `ubnt-device-info summary`. Missing detection is displayed as unknown, without guessing from available firmware metadata.

Menu entries matching the installed version are labeled `[ALREADY INSTALLED]`. Comparison ignores a leading `v` and Debian epoch. An installed three-part version can match an API version with an additional build suffix; when the installed version has a suffix, the full suffix must match. Selecting an already installed entry exits without downloading or installing. This is a version comparison, not a file-integrity or service-health check.

## Network package preparation

1. Download the selected `.deb` to a unique private directory under `/tmp/unifi-rollout-check-v6.*` using HTTPS.
2. Verify every checksum supplied by the API (SHA256 and/or MD5). Missing, malformed or mismatching checksums stop the run. MD5-only metadata provides weaker integrity assurance than SHA256.
3. Verify the actual Debian package name and architecture, and check its version against the selected API build.
4. Read both `Pre-Depends` and `Depends`. Recursively discover and download exact `unifi-* (= version)` pins, including already installed dependencies so the full pinned local set can be evaluated together. The downloaded Debian version must equal the complete pin according to `dpkg --compare-versions`; no arbitrary fallback build is accepted.
5. Keep the parent package's full platform, including Debian generation. Identical dependency artifacts repeated across channels are collapsed only when product, platform, version, URL and checksum metadata agree. Different URLs or checksums remain ambiguous. Stop on an unavailable or ambiguous dependency, conflicting version pins, or unsupported exact UniFi dependency syntax. Alternative groups containing exact UniFi pins require manual review. Cycles and repeated exact requirements are tracked to avoid repeated recursion.
6. Run `apt-get --simulate --no-remove install` with the complete local package set. A failed simulation stops the script before the installation prompt.
7. Prompt exactly:

   ```text
   Do you want to proceed to install? [y/N]
   ```

8. Only `y` or `yes` (case insensitive) proceeds. Enter, any other response, or end of input declines. On approval, one `apt-get --no-remove install -y` command receives every verified local package. APT determines dependency order. The script checks the resulting installed versions before reporting success.

Other dependencies, including non-exact UniFi constraints, are left to APT and the configured repositories. The script does not run `apt-get update`, change repository configuration, bypass signatures, force broken dependencies, or allow package removals. It does not automatically allow downgrades; APT can reject them. Review the full dry-run output. Preparation downloads files but does not install them. Downloaded packages remain for inspection after decline or failure.

## UniFi OS installation

The selected firmware URL must be HTTPS. After showing the selected metadata and warning that the console may reboot, the script asks the same confirmation question. Approval runs:

```bash
ubnt-systool fwupdate '<exact firmware URL returned for the selected build>'
```

The script does not replace the selected URL with a latest-release URL. There is no APT simulation, local firmware checksum pass, or recursive application dependency resolution for OS firmware; processing and validation are delegated to the console's firmware updater. A successful command return does not verify that the update or reboot has finished. Confirm the installed OS version after the console returns.

## Requirements and safety notes

Requires console root access, Bash 4+, `curl` with header-file support, `jq`, `awk`, `sed`, `sort`, `tr`, `dpkg`, `dpkg-query`, `mktemp`, `flock` and standard file tools. Network preparation additionally requires `dpkg-deb`, `sha256sum`, `md5sum` and `apt-get`; OS installation requires `ubnt-systool`. Do not run inside a separate application container or on a workstation.

Back up the console and Network configuration, review release notes and mandatory intermediate upgrades, provide enough temporary storage, and use a maintenance window with stable power. Network package scripts can restart services. OS updates can reboot the console and interrupt management or connectivity. Older releases and prerelease builds are visible; appearance in the menu is not a recommendation to install them.

The dry run checks package resolution, not runtime health, firmware upgrade paths or application data migration. APT is one transaction for dependency resolution, not an atomic rollback guarantee: an interrupted or failed install can leave partial changes. The final install may fail if repositories, locks or system state change after simulation. Do not run other updates concurrently. A v6 lock prevents two copies of this script from running together; it does not block the console UI updater.

Working directories are printed and retained. Remove the specific directory after reviewing it and finishing the update. `/tmp` contents may disappear on reboot. Do not share the token or firmware YAML when reporting problems.

## Validation status

Bash syntax passed locally and on a Dream Machine Pro Max. Local mocked checks cover version matching, installed-version comparison, recursive dependency collection, duplicate-channel artifact consolidation, wrong-platform rejection, checksum and exact-version rejection, failed APT simulation, and declined installation.

The owner supplied live-console output showing authenticated discovery, selection and verified download of Network 11.1.47-37925-1, followed by the original duplicate-channel dependency refusal. A subsequent authenticated read-only query confirmed identical Matter Controller 1.0.0 URLs and SHA256 checksums across beta, release-candidate and release channels. The correction was staged on that console and its checksum verified. Installed Matter Controller 1.0.0 was confirmed through package status. These checks did not perform an installation.

The corrected complete dependency/download/APT workflow and actual Network or OS installation have **not** been independently verified end to end on a live console. Stable is the owner's release designation; it does not assert universal compatibility or completed installation testing. See [release notes](RELEASE-NOTES-v6.md) for the evidence and limits.
