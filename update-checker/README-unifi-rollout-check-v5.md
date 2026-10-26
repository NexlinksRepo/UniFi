# UniFi Gradual Rollout Check v5

`unifi-rollout-check-v5.sh` is a helper script for discovering and optionally installing UniFi application updates and UniFi OS firmware that may be available through Ubiquiti's update service before they are offered normally in the UniFi UI.

It was built for UniFi OS consoles such as the UDM Pro Max and uses the console's own authenticated firmware API token.

## What it does

### UniFi applications

For application packages such as UniFi Network, the script:

1. Detects the console architecture.
2. Reads the current UniFi release channel and platform information.
3. Queries Ubiquiti's authenticated firmware API for the exact requested version.
4. Selects the package matching the console architecture.
5. Downloads the application `.deb` package.
6. Verifies package checksums when Ubiquiti provides them.
7. Reads the package dependencies.
8. Recursively discovers and downloads exact-version `unifi-*` dependencies.
9. Verifies dependency checksums.
10. Runs an APT dry run against the complete local package set.
11. Prompts:

   ```text
   Do you want to proceed to install? [y/N]
   ```

12. If you answer `Y`, APT installs the full local package set as one transaction so dependency ordering is handled automatically.

### UniFi OS

For UniFi OS firmware, the script:

1. Detects the console's firmware product and platform.
2. Queries Ubiquiti's authenticated firmware API for the exact requested version.
3. Displays the matching firmware metadata and direct firmware URL.
4. Prompts:

   ```text
   Do you want to proceed to install? [y/N]
   ```

5. If you answer `Y`, the script runs:

   ```bash
   ubnt-systool fwupdate <exact-firmware-url>
   ```

The console may reboot as part of a UniFi OS update.

## Requirements

Run the script directly on the UniFi console as `root`.

The script expects these tools to be present:

```text
curl
jq
awk
grep
sed
dpkg
dpkg-query
dpkg-deb
sha256sum
md5sum
apt-get
```

For UniFi OS installation, the console must also provide:

```text
ubnt-systool
```

The script reads the firmware API token from:

```text
/data/unifi-core/config/firmware.yaml
```

The token is used only for requests to Ubiquiti's firmware update service and is not printed by the script.

## Installation

Upload the script to the console, for example to `/root/`, then make it executable:

```bash
chmod +x /root/unifi-rollout-check-v5.sh
```

## Usage

Syntax:

```bash
./unifi-rollout-check-v5.sh <target> <version>
```

### Check and optionally install UniFi Network

Example:

```bash
./unifi-rollout-check-v5.sh unifi 11.0.83
```

The script will download the Network package and any required exact-version UniFi dependencies, perform checksum validation and an APT dry run, then ask whether you want to install.

For example, if Network `11.0.83` requires:

```text
unifi-matter-controller = 0.0.10
```

and the console currently has `0.0.9`, the script will attempt to locate and download the matching `0.0.10` package before running the APT dry run.

### Check and optionally install UniFi OS

Example:

```bash
./unifi-rollout-check-v5.sh unifi-os 6.0.12
```

Aliases also accepted by the script are:

```text
uos
os
```

For example:

```bash
./unifi-rollout-check-v5.sh uos 6.0.12
```

The script automatically uses the console's actual firmware product and platform, such as:

```text
Product:  unifi-dream
Platform: UDMPROMAX
```

If the requested firmware is found, the script displays the firmware metadata and asks whether to install it.

## Application download location

Application packages and downloaded dependencies are stored under:

```text
/tmp/unifi-rollout-check
```

Example:

```text
/tmp/unifi-rollout-check/unifi_11.0.83_arm64.deb
/tmp/unifi-rollout-check/unifi-matter-controller_0.0.10_arm64.deb
```

Because `/tmp` is temporary storage, these files may disappear after a reboot.

## Safety behavior

The script is designed to stop before installation unless the user explicitly answers `Y` or `yes`.

Pressing Enter at the prompt defaults to **No**.

For application updates, installation will not be offered if the APT dry run fails.

Example:

```text
APT dry run succeeded.

Do you want to proceed to install? [y/N]
```

If the dry run detects an unresolved dependency, the script exits without installing anything.

For UniFi OS, there is no equivalent APT dry run because the firmware update is handled by `ubnt-systool`, not Debian package management.

## Gradual rollout information

The firmware API may return fields such as:

```text
channel
probability
probability_computed
release_date
file_size
md5
sha256
```

An exact build can sometimes be returned by the authenticated API even when the normal UniFi UI does not yet offer it to the console.

The presence of a build in the API does not necessarily mean Ubiquiti has enabled that build for normal automatic rollout to the console.

## Example workflow

To check a staged Network release:

```bash
./unifi-rollout-check-v5.sh unifi 11.0.83
```

Typical flow:

```text
QUERYING UNIFI UPDATE SERVICE
        |
        v
SELECTED BUILD
        |
        v
DOWNLOAD APPLICATION PACKAGE
        |
        v
VERIFY CHECKSUMS
        |
        v
DISCOVER EXACT UNIFI DEPENDENCIES
        |
        v
DOWNLOAD + VERIFY DEPENDENCIES
        |
        v
APT DRY RUN
        |
        v
Do you want to proceed to install? [y/N]
```

If you answer `Y`, APT receives the application package and all locally downloaded dependency packages in the same command. APT determines the required installation order.

## Troubleshooting

### No matching build returned

If you see:

```text
No matching build was returned for this authenticated console.
```

check that the requested version is correct and that the build exists in Ubiquiti's firmware service.

### No package matching architecture

If you see:

```text
ERROR: No package matching architecture 'arm64' was returned.
```

the requested application version may not contain a build for the console architecture.

### APT dry run fails

If APT reports an unmet dependency, review the `EXACT UNIFI DEPENDENCIES` section above it.

The script attempts to resolve exact-version dependencies whose package names begin with:

```text
unifi-
```

Other Debian dependencies are left for APT and the console's configured package sources to resolve.

### Checksum mismatch

If a downloaded package does not match the checksum returned by Ubiquiti, the script stops rather than installing that package.

### UniFi OS update

A UniFi OS update can reboot the console. Do not start an OS update unless you are prepared for a temporary interruption in console availability.

## Notes

This script uses advanced update mechanisms and direct firmware metadata from Ubiquiti's update service. It is intended for controlled use when investigating staged or gradual rollouts.

For normal production operation, the standard UniFi update interface remains the simplest update path when the desired release is already offered there.
