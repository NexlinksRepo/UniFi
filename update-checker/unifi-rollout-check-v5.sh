#!/bin/bash

set -u

TARGET="${1:-}"
TARGET_VERSION="${2:-}"

FW_YAML="/data/unifi-core/config/firmware.yaml"
API="https://fw-update.ubnt.com"
TMPDIR="/tmp/unifi-rollout-check"

usage() {
    cat <<'EOF'

UniFi Gradual Rollout Discovery + Interactive Install

Usage:
  unifi-rollout-check.sh <target> <version>

Examples:
  unifi-rollout-check.sh unifi 11.0.83
  unifi-rollout-check.sh unifi-os 6.0.12

Targets:
  unifi       UniFi Network application
  unifi-os    UniFi OS firmware for this console
  <product>   Other UniFi application product names may also work

Behavior:
  Application mode:
    - Finds the exact build in Ubiquiti's authenticated firmware API.
    - Downloads the matching application package.
    - Recursively discovers/downloads exact-version unifi-* dependencies.
    - Verifies checksums when supplied by the API.
    - Runs an APT dry run against the complete local package set.
    - Prompts: "Do you want to proceed to install? [y/N]"
    - If yes, APT installs the complete local package set in dependency order.

  UniFi OS mode:
    - Finds the exact firmware for this console product/platform.
    - Shows rollout metadata and firmware URL.
    - Prompts: "Do you want to proceed to install? [y/N]"
    - If yes, invokes:
        ubnt-systool fwupdate <exact firmware URL>
    - The console may reboot as part of the firmware update.

EOF
}

ask_install() {
    local answer
    echo
    read -r -p "Do you want to proceed to install? [y/N] " answer
    case "$answer" in
        y|Y|yes|YES|Yes)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

if [[ -z "$TARGET" || -z "$TARGET_VERSION" ]]; then
    usage
    exit 1
fi

for CMD in curl jq awk grep sed dpkg dpkg-query dpkg-deb sha256sum md5sum apt-get; do
    command -v "$CMD" >/dev/null 2>&1 || {
        echo "ERROR: Missing command: $CMD"
        exit 1
    }
done

if [[ ! -r "$FW_YAML" ]]; then
    echo "ERROR: Cannot read $FW_YAML"
    echo "Run this script as root on the UniFi console."
    exit 1
fi

TOKEN=$(awk '/^token:/{print $2; exit}' "$FW_YAML")

if [[ -z "$TOKEN" ]]; then
    echo "ERROR: No UniFi firmware API token found."
    exit 1
fi

ARCH=$(dpkg --print-architecture)

CHANNEL=$(awk '
    /^releaseChannel:/ {
        gsub(/["'"'"']/, "", $2)
        print $2
        exit
    }
' "$FW_YAML")

CONSOLE_PLATFORM=$(awk '
    /^latest:/ { latest=1; next }
    latest && /^  platform:/ {
        print $2
        exit
    }
' "$FW_YAML")

CONSOLE_PRODUCT=$(awk '
    /^latest:/ { latest=1; next }
    latest && /^  product:/ {
        print $2
        exit
    }
' "$FW_YAML")

CURRENT_OS_VERSION=$(ubnt-device-info summary 2>/dev/null | awk -F': ' '/Firmware:/ {print $2; exit}')

VERSION="${TARGET_VERSION#v}"
BASE_VERSION=$(echo "$VERSION" | sed -E 's/[-+].*$//')
IFS='.' read -r MAJOR MINOR PATCH <<< "$BASE_VERSION"

if [[ -z "${MAJOR:-}" || -z "${MINOR:-}" || -z "${PATCH:-}" ]]; then
    echo "ERROR: Version must look like 11.0.83 or 6.0.12"
    exit 1
fi

mkdir -p "$TMPDIR"

case "$TARGET" in
    unifi-os|uos|os)
        MODE="os"
        PRODUCT="$CONSOLE_PRODUCT"
        ;;
    *)
        MODE="app"
        PRODUCT="$TARGET"
        ;;
esac

echo
echo "============================================================"
echo " UniFi Gradual Rollout Discovery"
echo "============================================================"
echo
echo "Mode              : $MODE"
echo "Requested target  : $TARGET"
echo "Requested version : $TARGET_VERSION"
echo "System arch       : $ARCH"
echo "Release channel   : ${CHANNEL:-unknown}"
echo "Console platform  : ${CONSOLE_PLATFORM:-unknown}"
echo "Console product   : ${CONSOLE_PRODUCT:-unknown}"
echo "Current UniFi OS  : ${CURRENT_OS_VERSION:-unknown}"
echo

echo "============================================================"
echo " DEVICE"
echo "============================================================"
echo

ubnt-device-info summary 2>/dev/null || true

if [[ "$MODE" == "app" ]]; then
    echo
    echo "============================================================"
    echo " INSTALLED APPLICATION PACKAGES"
    echo "============================================================"
    echo

    for PKG in \
        "$PRODUCT" \
        unifi-core \
        unifi-matter-controller \
        temurin-25-jre
    do
        VER=$(dpkg-query -W -f='${Version}' "$PKG" 2>/dev/null || true)

        if [[ -n "$VER" ]]; then
            printf "%-28s %s\n" "$PKG" "$VER"
        else
            printf "%-28s %s\n" "$PKG" "NOT INSTALLED"
        fi
    done
fi

echo
echo "============================================================"
echo " QUERYING UNIFI UPDATE SERVICE"
echo "============================================================"
echo

if [[ "$MODE" == "os" ]]; then
    if [[ -z "$CONSOLE_PRODUCT" || -z "$CONSOLE_PLATFORM" ]]; then
        echo "ERROR: Could not determine this console's firmware product/platform."
        exit 1
    fi

    QUERY="${API}/api/firmware?filter=eq~~product~~${CONSOLE_PRODUCT}&filter=eq~~platform~~${CONSOLE_PLATFORM}&filter=eq~~version_major~~${MAJOR}&filter=eq~~version_minor~~${MINOR}&filter=eq~~version_patch~~${PATCH}"
else
    QUERY="${API}/api/firmware?filter=eq~~product~~${PRODUCT}&filter=eq~~version_major~~${MAJOR}&filter=eq~~version_minor~~${MINOR}&filter=eq~~version_patch~~${PATCH}"
fi

RESPONSE=$(curl -fsS \
    -H "Authorization: Bearer token:${TOKEN}" \
    "$QUERY") || {
        echo "ERROR: UniFi Update service query failed."
        exit 1
    }

COUNT=$(echo "$RESPONSE" | jq '._embedded.firmware | length')

echo "Matching builds returned: $COUNT"
echo

if [[ "$COUNT" -eq 0 ]]; then
    echo "No matching build was returned for this authenticated console."
    exit 2
fi

echo "$RESPONSE" | jq '
    ._embedded.firmware[]? |
    {
        product,
        platform,
        version,
        channel,
        probability,
        probability_computed,
        release_date,
        file_size,
        md5: (.md5 // .md5_checksum),
        sha256: (.sha256_checksum // .sha256),
        url: ._links.data.href
    }
'

if [[ "$MODE" == "os" ]]; then
    MATCH=$(echo "$RESPONSE" | jq -c \
        --arg platform "$CONSOLE_PLATFORM" '
            ._embedded.firmware[]?
            | select(.platform == $platform)
        ' | head -1)
else
    MATCH=$(echo "$RESPONSE" | jq -c \
        --arg arch "$ARCH" '
            ._embedded.firmware[]?
            | select(.platform | endswith("-" + $arch))
        ' | head -1)
fi

if [[ -z "$MATCH" ]]; then
    if [[ "$MODE" == "os" ]]; then
        echo "ERROR: No build matching console platform '$CONSOLE_PLATFORM' was returned."
    else
        echo "ERROR: No package matching architecture '$ARCH' was returned."
    fi
    exit 1
fi

PACKAGE_URL=$(echo "$MATCH" | jq -r '._links.data.href')
API_VERSION=$(echo "$MATCH" | jq -r '.version')
API_PLATFORM=$(echo "$MATCH" | jq -r '.platform')
API_CHANNEL=$(echo "$MATCH" | jq -r '.channel')
PROBABILITY=$(echo "$MATCH" | jq -r '.probability // "null"')
PROBABILITY_COMPUTED=$(echo "$MATCH" | jq -r '.probability_computed // "null"')
FILE_SIZE=$(echo "$MATCH" | jq -r '.file_size // "unknown"')
MD5_EXPECTED=$(echo "$MATCH" | jq -r '.md5 // .md5_checksum // "unknown"')
SHA256_EXPECTED=$(echo "$MATCH" | jq -r '.sha256_checksum // .sha256 // "unknown"')
RELEASE_DATE=$(echo "$MATCH" | jq -r '.release_date // "unknown"')

echo
echo "============================================================"
echo " SELECTED BUILD"
echo "============================================================"
echo
echo "Product              : $(echo "$MATCH" | jq -r '.product')"
echo "Version              : $API_VERSION"
echo "Platform             : $API_PLATFORM"
echo "Channel              : $API_CHANNEL"
echo "Probability          : $PROBABILITY"
echo "Probability computed : $PROBABILITY_COMPUTED"
echo "Release date         : $RELEASE_DATE"
echo "File size            : $FILE_SIZE"
echo "MD5                  : $MD5_EXPECTED"
echo "SHA256               : $SHA256_EXPECTED"
echo "URL                  : $PACKAGE_URL"

if [[ "$MODE" == "os" ]]; then
    echo
    echo "============================================================"
    echo " UNIFI OS UPDATE"
    echo "============================================================"
    echo
    echo "Current OS : ${CURRENT_OS_VERSION:-unknown}"
    echo "Target OS  : $API_VERSION"
    echo "Platform   : $CONSOLE_PLATFORM"
    echo "Product    : $CONSOLE_PRODUCT"
    echo
    echo "Firmware URL:"
    echo "  $PACKAGE_URL"
    echo
    echo "WARNING:"
    echo "  Proceeding will invoke ubnt-systool fwupdate."
    echo "  The console may reboot and network management will be unavailable"
    echo "  while the firmware update completes."
    echo

    if ! command -v ubnt-systool >/dev/null 2>&1; then
        echo "ERROR: ubnt-systool is not available on this console."
        exit 1
    fi

    if ask_install; then
        echo
        echo "============================================================"
        echo " INSTALLING UNIFI OS"
        echo "============================================================"
        echo
        echo "Running:"
        echo "  ubnt-systool fwupdate <exact firmware URL>"
        echo

        ubnt-systool fwupdate "$PACKAGE_URL"
        RC=$?

        echo
        if [[ "$RC" -eq 0 ]]; then
            echo "UniFi OS firmware update command accepted."
            echo "The console may reboot automatically."
        else
            echo "ERROR: ubnt-systool fwupdate exited with code $RC."
            exit "$RC"
        fi
    else
        echo
        echo "Install declined. Nothing was changed."
    fi

    exit 0
fi

PACKAGE_FILE="${TMPDIR}/${PRODUCT}_${BASE_VERSION}_${ARCH}.deb"

echo
echo "============================================================"
echo " DOWNLOADING APPLICATION PACKAGE"
echo "============================================================"
echo

curl -fL -o "$PACKAGE_FILE" "$PACKAGE_URL"

echo
echo "Saved to:"
echo "  $PACKAGE_FILE"

echo
echo "============================================================"
echo " MAIN PACKAGE CHECKSUM VERIFICATION"
echo "============================================================"
echo

ACTUAL_MD5=$(md5sum "$PACKAGE_FILE" | awk '{print $1}')
ACTUAL_SHA256=$(sha256sum "$PACKAGE_FILE" | awk '{print $1}')

echo "MD5 expected    : $MD5_EXPECTED"
echo "MD5 actual      : $ACTUAL_MD5"
echo "SHA256 expected : $SHA256_EXPECTED"
echo "SHA256 actual   : $ACTUAL_SHA256"

if [[ "$MD5_EXPECTED" != "unknown" && "$MD5_EXPECTED" != "$ACTUAL_MD5" ]]; then
    echo "ERROR: Main package MD5 checksum mismatch."
    exit 1
fi

if [[ "$SHA256_EXPECTED" != "unknown" && "$SHA256_EXPECTED" != "$ACTUAL_SHA256" ]]; then
    echo "ERROR: Main package SHA256 checksum mismatch."
    exit 1
fi

echo "Checksum verification passed."

echo
echo "============================================================"
echo " PACKAGE METADATA"
echo "============================================================"
echo

dpkg-deb -f "$PACKAGE_FILE" \
    Package \
    Version \
    Architecture \
    Depends \
    Pre-Depends \
    Conflicts \
    Provides \
    Replaces 2>/dev/null

DEPENDS=$(dpkg-deb -f "$PACKAGE_FILE" Depends 2>/dev/null || true)

echo
echo "============================================================"
echo " EXACT UNIFI DEPENDENCIES"
echo "============================================================"
echo

FOUND_DEP=0
DOWNLOADED_DEPS=()
SEEN_DEPS=()

already_seen_dep() {
    local key="$1"
    local item
    for item in "${SEEN_DEPS[@]:-}"; do
        [[ "$item" == "$key" ]] && return 0
    done
    return 1
}

download_unifi_dependency() {
    local DEP_NAME="$1"
    local DEP_VERSION="$2"
    local KEY="${DEP_NAME}=${DEP_VERSION}"
    local API_DEP_VERSION API_DEP_BASE D_MAJOR D_MINOR D_PATCH
    local DEP_QUERY DEP_RESPONSE DEP_MATCH DEP_URL DEP_PLATFORM DEP_CHANNEL
    local DEP_MD5 DEP_SHA256 DEP_FILE ACTUAL_DEP_MD5 ACTUAL_DEP_SHA256
    local INSTALLED CHILD_DEPENDS CHILD_SPEC CHILD_NAME CHILD_VERSION

    already_seen_dep "$KEY" && return 0
    SEEN_DEPS+=("$KEY")
    FOUND_DEP=1

    INSTALLED=$(dpkg-query -W -f='${Version}' "$DEP_NAME" 2>/dev/null || true)

    echo "$DEP_NAME"
    echo "  Required : $DEP_VERSION"
    echo "  Installed: ${INSTALLED:-NOT INSTALLED}"

    API_DEP_VERSION="${DEP_VERSION#*:}"
    API_DEP_BASE=$(echo "$API_DEP_VERSION" | sed -E 's/[-+].*$//')
    IFS='.' read -r D_MAJOR D_MINOR D_PATCH <<< "$API_DEP_BASE"

    if [[ -z "${D_MAJOR:-}" || -z "${D_MINOR:-}" || -z "${D_PATCH:-}" ]]; then
        echo "  API      : Could not parse dependency version"
        echo
        return 0
    fi

    DEP_QUERY="${API}/api/firmware?filter=eq~~product~~${DEP_NAME}&filter=eq~~version_major~~${D_MAJOR}&filter=eq~~version_minor~~${D_MINOR}&filter=eq~~version_patch~~${D_PATCH}"

    DEP_RESPONSE=$(curl -fsS \
        -H "Authorization: Bearer token:${TOKEN}" \
        "$DEP_QUERY" 2>/dev/null || true)

    if [[ -z "$DEP_RESPONSE" ]]; then
        echo "  API      : Query failed or returned no data"
        echo
        return 0
    fi

    DEP_MATCH=$(echo "$DEP_RESPONSE" | jq -c \
        --arg arch "$ARCH" \
        --arg required "$API_DEP_VERSION" '
            [
                ._embedded.firmware[]?
                | select(.platform | endswith("-" + $arch))
            ]
            | (
                map(select(
                    (.version | sub("^v"; "")) == $required
                    or
                    (.version | sub("^v"; "") | startswith($required + "-"))
                ))[0]
                //
                .[0]
            )
        ')

    if [[ -z "$DEP_MATCH" || "$DEP_MATCH" == "null" ]]; then
        echo "  API      : No architecture-matching package returned"
        echo
        return 0
    fi

    DEP_URL=$(echo "$DEP_MATCH" | jq -r '._links.data.href')
    DEP_PLATFORM=$(echo "$DEP_MATCH" | jq -r '.platform')
    DEP_CHANNEL=$(echo "$DEP_MATCH" | jq -r '.channel')
    DEP_MD5=$(echo "$DEP_MATCH" | jq -r '.md5 // .md5_checksum // "unknown"')
    DEP_SHA256=$(echo "$DEP_MATCH" | jq -r '.sha256_checksum // .sha256 // "unknown"')
    DEP_FILE="${TMPDIR}/${DEP_NAME}_${API_DEP_VERSION}_${ARCH}.deb"

    echo "  Platform : $DEP_PLATFORM"
    echo "  Channel  : $DEP_CHANNEL"
    echo "  URL      : $DEP_URL"
    echo "  Download : $DEP_FILE"

    if ! curl -fL -o "$DEP_FILE" "$DEP_URL"; then
        echo "  ERROR    : Dependency download failed"
        echo
        return 0
    fi

    ACTUAL_DEP_MD5=$(md5sum "$DEP_FILE" | awk '{print $1}')
    ACTUAL_DEP_SHA256=$(sha256sum "$DEP_FILE" | awk '{print $1}')

    if [[ "$DEP_MD5" != "unknown" && "$DEP_MD5" != "$ACTUAL_DEP_MD5" ]]; then
        echo "  ERROR    : MD5 checksum mismatch"
        rm -f "$DEP_FILE"
        echo
        return 0
    fi

    if [[ "$DEP_SHA256" != "unknown" && "$DEP_SHA256" != "$ACTUAL_DEP_SHA256" ]]; then
        echo "  ERROR    : SHA256 checksum mismatch"
        rm -f "$DEP_FILE"
        echo
        return 0
    fi

    echo "  Verify   : Checksums passed"
    DOWNLOADED_DEPS+=("$DEP_FILE")

    CHILD_DEPENDS=$(dpkg-deb -f "$DEP_FILE" Depends 2>/dev/null || true)

    while IFS= read -r CHILD_SPEC; do
        [[ -z "$CHILD_SPEC" ]] && continue

        CHILD_NAME=$(echo "$CHILD_SPEC" | sed -E 's/ \(=.*$//')
        CHILD_VERSION=$(echo "$CHILD_SPEC" | sed -E 's/^.*\(= ([^)]+)\).*$/\1/')

        echo "  Child dependency discovered: $CHILD_NAME = $CHILD_VERSION"
        download_unifi_dependency "$CHILD_NAME" "$CHILD_VERSION"
    done < <(
        echo "$CHILD_DEPENDS" |
        grep -oE 'unifi-[a-zA-Z0-9-]+ \(= [^)]+\)' |
        sort -u
    )

    echo
}

while IFS= read -r SPEC; do
    [[ -z "$SPEC" ]] && continue

    DEP_NAME=$(echo "$SPEC" | sed -E 's/ \(=.*$//')
    DEP_VERSION=$(echo "$SPEC" | sed -E 's/^.*\(= ([^)]+)\).*$/\1/')

    download_unifi_dependency "$DEP_NAME" "$DEP_VERSION"

done < <(
    echo "$DEPENDS" |
    grep -oE 'unifi-[a-zA-Z0-9-]+ \(= [^)]+\)' |
    sort -u
)

if [[ "$FOUND_DEP" -eq 0 ]]; then
    echo "No exact-version UniFi dependencies found."
fi

echo
echo "============================================================"
echo " DOWNLOADED FILES"
echo "============================================================"
echo
echo "Main package:"
echo "  $PACKAGE_FILE"

if [[ ${#DOWNLOADED_DEPS[@]} -gt 0 ]]; then
    echo
    echo "Dependencies:"
    for DEP_FILE in "${DOWNLOADED_DEPS[@]}"; do
        echo "  $DEP_FILE"
    done
else
    echo
    echo "Dependencies:"
    echo "  None downloaded"
fi

echo
echo "============================================================"
echo " APT DRY RUN"
echo "============================================================"
echo

LOCAL_PACKAGES=("${DOWNLOADED_DEPS[@]}" "$PACKAGE_FILE")

echo "APT will evaluate this complete local package set:"
for LOCAL_PACKAGE in "${LOCAL_PACKAGES[@]}"; do
    echo "  $LOCAL_PACKAGE"
done
echo

DRYRUN_OUTPUT=$(mktemp)

if apt-get -s install "${LOCAL_PACKAGES[@]}" >"$DRYRUN_OUTPUT" 2>&1; then
    cat "$DRYRUN_OUTPUT"
    DRYRUN_OK=1
else
    cat "$DRYRUN_OUTPUT"
    DRYRUN_OK=0
fi

rm -f "$DRYRUN_OUTPUT"

if [[ "$DRYRUN_OK" -ne 1 ]]; then
    echo
    echo "ERROR: APT dry run failed."
    echo "Nothing was installed."
    exit 3
fi

echo
echo "APT dry run succeeded."

if ask_install; then
    echo
    echo "============================================================"
    echo " INSTALLING APPLICATION AND DEPENDENCIES"
    echo "============================================================"
    echo
    echo "APT will install the downloaded packages as one transaction"
    echo "and determine the correct dependency order."
    echo

    apt-get install -y "${LOCAL_PACKAGES[@]}"

    echo
    echo "============================================================"
    echo " INSTALLED VERSIONS"
    echo "============================================================"
    echo

    for LOCAL_PACKAGE in "${LOCAL_PACKAGES[@]}"; do
        INSTALLED_NAME=$(dpkg-deb -f "$LOCAL_PACKAGE" Package 2>/dev/null || true)
        if [[ -n "$INSTALLED_NAME" ]]; then
            dpkg-query -W -f='${Package} ${Version}\n' "$INSTALLED_NAME" 2>/dev/null || true
        fi
    done

    echo
    echo "============================================================"
    echo " COMPLETE"
    echo "============================================================"
    echo
    echo "Installation completed."
else
    echo
    echo "Install declined. Nothing was installed."
fi

echo
