#!/bin/bash
# UniFi rollout checker v6. Requires Bash 4+, jq and Debian console tools.
set -Eeuo pipefail
umask 077
FW_YAML=/data/unifi-core/config/firmware.yaml
API=https://fw-update.ubnt.com
die() { echo "ERROR: $*" >&2; exit 1; }
trap 'echo "ERROR: Operation failed at line $LINENO; installation was not confirmed complete." >&2' ERR
usage() {
    echo 'Usage: unifi-rollout-check-v6.sh [menu|unifi|unifi-os [version]]'
    echo 'No arguments: discover Network and UniFi OS builds, then choose a numbered entry.'
}
[[ ${1:-} != --help && ${1:-} != -h ]] || { usage; exit 0; }
[[ $# -le 2 ]] || { usage; exit 1; }
TARGET=${1:-menu}
REQUEST=${2:-}
case "$TARGET" in menu|unifi|unifi-os) ;; os|uos) TARGET=unifi-os ;; *) usage; exit 1 ;; esac
[[ $TARGET != menu || -z $REQUEST ]] || die 'menu does not accept a version'
[[ -z $REQUEST || $REQUEST =~ ^v?[0-9]+\.[0-9]+\.[0-9]+([-+][a-zA-Z0-9.+~-]+)?$ ]] || die 'Invalid version'
[[ $EUID -eq 0 ]] || die 'Run as root directly on the UniFi OS console.'
for cmd in curl jq awk sed sort tr dpkg dpkg-query mktemp flock; do
    command -v "$cmd" >/dev/null || die "Missing command: $cmd"
done
exec 9>/run/lock/unifi-rollout-check-v6.lock
flock -n 9 || die 'Another v6 checker is running.'
[[ -r $FW_YAML ]] || die "Cannot read $FW_YAML"
# Restricted scalar reader for the known firmware.yaml layout; never source YAML.
yaml_scalar() {
    awk -v key="$1" -v section="${2:-}" '
      section != "" && $0 ~ "^" section ":" { inside=1; next }
      section != "" && inside && /^[^[:space:]#]/ {exit}
      (section == "" || inside) && $0 ~ "^[[:space:]]*" key ":[[:space:]]*" {
        sub("^[[:space:]]*" key ":[[:space:]]*", "")
        sub(/[[:space:]]+#.*$/, ""); sub(/[[:space:]]+$/, "")
        gsub(/^[\047\042]|[\047\042]$/, ""); print; exit
      }' "$FW_YAML"
}
TOKEN=$(yaml_scalar token)
[[ -n $TOKEN && $TOKEN != *$'\n'* && $TOKEN != *$'\r'* ]] || die 'Invalid or missing firmware token'
ARCH=$(dpkg --print-architecture)
PLATFORM=$(yaml_scalar platform latest)
PRODUCT=$(yaml_scalar product latest)
CHANNEL=$(yaml_scalar releaseChannel)
installed() {
    local state
    state=$(dpkg-query -W -f='${Status}\t${Version}' "$1" 2>/dev/null) || return 0
    [[ $state != 'install ok installed'$'\t'* ]] || printf '%s' "${state#*$'\t'}"
}
NETWORK=$(installed unifi)
OS=$( { ubnt-device-info summary 2>/dev/null || true; } | awk -F':[[:space:]]*' '/^[[:space:]]*Firmware:/ {print $2; exit}')
OS=${OS#v}
echo "Current Network: ${NETWORK:-NOT INSTALLED / unknown}"
echo "Current UniFi OS: ${OS:-unknown}"
echo "Architecture: $ARCH; console: ${PRODUCT:-unknown}/${PLATFORM:-unknown}; configured channel: ${CHANNEL:-unknown}"
WORK=$(mktemp -d /tmp/unifi-rollout-check-v6.XXXXXXXX)
echo "Working files: $WORK (retained for review; remove when finished)."
# Keep credentials out of command arguments and downloaded firmware requests.
printf 'Authorization: Bearer token:%s\n' "$TOKEN" >"$WORK/auth"
unset TOKEN
trap 'rm -f "$WORK/auth"' EXIT

# Enumerate the full response (large limit), following HAL next links if supplied.
# No version/channel filter: expose all builds the authenticated API returns.
discover() {
    local product=$1 platform=${2:-} url response next count signature previous='' page=0
    local -a args=(--data-urlencode "filter=eq~~product~~$product" --data-urlencode 'limit=10000')
    [[ -z $platform ]] || args+=(--data-urlencode "filter=eq~~platform~~$platform")
    url="$API/api/firmware"
    : >"$WORK/rows"
    while :; do
        ((page+=1)); ((page <= 100)) || die 'API pagination exceeded safety limit'
        if ((page == 1)); then
            response=$(curl --proto '=https' --connect-timeout 20 --max-time 180 -fsS -G -H "@$WORK/auth" "${args[@]}" "$url")
        else
            response=$(curl --proto '=https' --connect-timeout 20 --max-time 180 -fsS -H "@$WORK/auth" "$url")
        fi
        jq -e '._embedded.firmware | type == "array"' <<<"$response" >/dev/null || die 'Unrecognized API response'
        count=$(jq '._embedded.firmware | length' <<<"$response")
        signature=$(jq -c '[._embedded.firmware[] | .id // ._links.data.href]' <<<"$response")
        [[ $signature != "$previous" ]] || die 'API repeated a page; discovery incomplete'
        previous=$signature
        jq -c '._embedded.firmware[]' <<<"$response" >>"$WORK/rows"
        next=$(jq -r '._links.next.href // empty' <<<"$response")
        if [[ -z $next ]]; then
            ((count < 10000)) || die 'API limit reached without pagination; cannot claim complete discovery'
            break
        fi
        case "$next" in
            /api/firmware*) url="$API$next" ;;
            https://fw-update.ubnt.com/api/firmware*|https://fw-update.ui.com/api/firmware*) url=$next ;;
            *) die 'Untrusted pagination URL' ;;
        esac
    done
    jq -s --arg p "$product" --arg platform "$platform" --arg arch "$ARCH" '
      map(select(.product == $p) | select(
        if $platform != "" then .platform == $platform
        else (.platform | type == "string" and endswith("-" + $arch)) end))
      | unique_by([.version,.platform,.channel,._links.data.href])' "$WORK/rows"
}
version_matches() {
    local want=${1#v} have=${2#v}
    [[ $have == "$want" ]] && return 0
    [[ $want =~ ^[0-9]+\.[0-9]+\.[0-9]+$ && $have == "$want-"* ]]
}
is_installed() {
    local current=$1 api=${2#v}
    [[ -n $current ]] || return 1
    # Debian epoch is not part of the API version. Preserve package build suffixes.
    current=${current#*:}; current=${current#v}
    version_matches "$current" "$api"
}
echo 'Discovering authenticated builds...'
echo 'Architecture/product matches are candidates; rollout and OS compatibility still matter.'
echo 'All returned channels are shown, including older and prerelease builds.'
echo '[]' >"$WORK/catalog"
if [[ $TARGET == menu || $TARGET == unifi ]]; then
    discover unifi >"$WORK/network"
    jq 'map(. + {checker_target:"unifi"})' "$WORK/network" >"$WORK/catalog"
fi
if [[ $TARGET == menu || $TARGET == unifi-os ]]; then
    if [[ -z $PRODUCT || -z $PLATFORM ]]; then
        [[ $TARGET == menu ]] || die 'Cannot determine console product/platform from latest in firmware.yaml'
        echo 'OS discovery unavailable: console product/platform missing.' >&2
    else
        discover "$PRODUCT" "$PLATFORM" >"$WORK/os"
        jq -s '.[0] + (.[1] | map(. + {checker_target:"unifi-os"}))' "$WORK/catalog" "$WORK/os" >"$WORK/merged"
        mv "$WORK/merged" "$WORK/catalog"
    fi
fi
mapfile -t ROWS < <(jq -c 'sort_by(.checker_target, .version_major // 0, .version_minor // 0, .version_patch // 0, .version) | reverse[]' "$WORK/catalog")
CHOICES=()
for row in "${ROWS[@]}"; do
    ver=$(jq -r '.version' <<<"$row")
    [[ -z $REQUEST ]] || version_matches "$REQUEST" "$ver" || continue
    CHOICES+=("$row")
done
((${#CHOICES[@]})) || die 'No matching builds returned for this console. No versions were guessed.'
for i in "${!CHOICES[@]}"; do
    row=${CHOICES[i]}
    kind=$(jq -r '.checker_target' <<<"$row")
    ver=$(jq -r '.version' <<<"$row")
    current=$NETWORK; [[ $kind != unifi-os ]] || current=$OS
    marker=''; if is_installed "$current" "$ver"; then marker=' [ALREADY INSTALLED]'; fi
    printf '%4d) %s %s | %s | channel=%s%s\n' "$((i+1))" "$kind" "$ver" "$(jq -r '.platform' <<<"$row")" "$(jq -r '.channel // "unknown"' <<<"$row")" "$marker"
done
if [[ -n $REQUEST && ${#CHOICES[@]} -eq 1 ]]; then
    MATCH=${CHOICES[0]}
else
    while :; do
        read -r -p 'Choose a build number (q to quit): ' answer || exit 0
        [[ $answer != q && $answer != Q ]] || exit 0
        if [[ $answer =~ ^[0-9]{1,6}$ ]]; then
            index=$((10#$answer))
            if ((index >= 1 && index <= ${#CHOICES[@]})); then MATCH=${CHOICES[index-1]}; break; fi
        fi
        echo 'Invalid selection.'
    done
fi
TARGET=$(jq -r '.checker_target' <<<"$MATCH")
VER=$(jq -r '.version' <<<"$MATCH")
jq '{product,version,platform,channel,probability,probability_computed,release_date,file_size,url:._links.data.href}' <<<"$MATCH"
current=$NETWORK; [[ $TARGET != unifi-os ]] || current=$OS
if is_installed "$current" "$VER"; then
    echo 'Selected version is already installed. No installation needed.'
    exit 0
fi
https_url() { [[ $1 == https://* && $1 != *$'\n'* && $1 != *$'\r'* ]] || die 'Missing or invalid HTTPS download URL'; }
ask_install() {
    local answer
    read -r -p 'Do you want to proceed to install? [y/N] ' answer || return 1
    [[ ${answer,,} == y || ${answer,,} == yes ]]
}
if [[ $TARGET == unifi-os ]]; then
    command -v ubnt-systool >/dev/null || die 'Missing ubnt-systool'
    URL=$(jq -r '._links.data.href // empty' <<<"$MATCH")
    https_url "$URL"
    echo 'UniFi OS uses ubnt-systool; there is no APT dry run. The console may reboot.'
    echo 'Review release notes, required upgrade paths and your backup before proceeding.'
    if ask_install; then
        ubnt-systool fwupdate "$URL"
        echo 'Firmware command returned successfully; completion/reboot is not verified.'
    else echo 'Install declined.'; fi
    exit 0
fi
for cmd in dpkg-deb sha256sum md5sum apt-get; do
    command -v "$cmd" >/dev/null || die "Missing command: $cmd"
done
declare -A SEEN=() REQUIRED=()
PACKAGES=()
download_package() {
    local record=$1 name=$2 required=${3:-} url file hash expected actual arch version package deps group spec child childver candidate candidates parent_platform
    parent_platform=$(jq -r '.platform // empty' <<<"$record")
    url=$(jq -r '._links.data.href // empty' <<<"$record"); https_url "$url"
    file="$WORK/package-${#PACKAGES[@]}.deb"
    curl --proto '=https' --proto-redir '=https' --connect-timeout 20 --max-time 1800 -fLsS -o "$file" "$url"
    hash=0
    for spec in sha256 md5; do
        expected=$(jq -r --arg h "$spec" 'if $h == "sha256" then .sha256_checksum // .sha256 // empty else .md5 // .md5_checksum // empty end' <<<"$record")
        [[ -n $expected ]] || continue
        expected=${expected,,}
        if [[ $spec == sha256 ]]; then
            [[ $expected =~ ^[0-9a-f]{64}$ ]] || die 'Malformed SHA256'
            actual=$(sha256sum "$file"); actual=${actual%% *}
        else
            [[ $expected =~ ^[0-9a-f]{32}$ ]] || die 'Malformed MD5'
            actual=$(md5sum "$file"); actual=${actual%% *}
        fi
        [[ $actual == "$expected" ]] || die "Checksum mismatch: $name"
        hash=1
    done
    ((hash)) || die "No API checksum supplied for $name; refusing unverified package"
    package=$(dpkg-deb -f "$file" Package)
    version=$(dpkg-deb -f "$file" Version)
    arch=$(dpkg-deb -f "$file" Architecture)
    [[ $package == "$name" ]] || die "Package identity mismatch: expected $name, got $package"
    [[ $arch == "$ARCH" || $arch == all ]] || die "Wrong Debian architecture: $arch"
    if [[ -n $required ]]; then
        dpkg --compare-versions "$version" eq "$required" || die "Exact version mismatch: $name needs $required, got $version"
    else
        version_matches "${version#*:}" "$(jq -r '.version' <<<"$record")" || die 'Selected API build differs from downloaded package version'
    fi
    if [[ -n ${REQUIRED[$name]:-} ]]; then
        dpkg --compare-versions "${REQUIRED[$name]}" eq "$version" || die "Conflicting versions required for $name"
    fi
    REQUIRED[$name]=$version
    [[ -z ${SEEN[$name=$version]:-} ]] || return 0
    SEEN[$name=$version]=1
    PACKAGES+=("$file")
    echo "Verified $name $version ($arch); installed: $(installed "$name")"
    deps="$(dpkg-deb -f "$file" Pre-Depends),$(dpkg-deb -f "$file" Depends)"
    # Parse comma-separated groups. Alternatives involving exact UniFi pins are
    # deliberately refused rather than forcing every arm of an OR dependency.
    while IFS= read -r group; do
        [[ $group =~ unifi-[a-z0-9.+-]+[[:space:]]*\(=[[:space:]]*[^\)]+\) ]] || continue
        [[ $group != *'|'* ]] || die "Exact UniFi dependency has alternatives; manual review required: $group"
        spec=$(sed -nE 's/^[[:space:]]*(unifi-[a-z0-9.+-]+)[[:space:]]*\(=[[:space:]]*([^ )]+)[[:space:]]*\)[[:space:]]*$/\1 \2/p' <<<"$group")
        [[ -n $spec ]] || die "Unsupported exact UniFi dependency syntax: $group"
        read -r child childver <<<"$spec"
        if [[ -n ${REQUIRED[$child]:-} ]]; then
            dpkg --compare-versions "${REQUIRED[$child]}" eq "$childver" || die "Conflicting requirements for $child"
        fi
        [[ -z ${SEEN[$child=$childver]:-} ]] || continue
        echo "Discovering exact dependency: $child = $childver"
        candidates=$(discover "$child")
        # A single binary may be published in several channels. Channel rows
        # are not different packages when URL and integrity metadata agree.
        # Keep the parent's full OS/Debian platform, not merely its CPU arch.
        candidates=$(jq --arg platform "$parent_platform" '
            map(select(.platform == $platform))
            | unique_by([.product, .platform, .version, ._links.data.href,
                (.sha256_checksum // .sha256 // ""),
                (.md5 // .md5_checksum // "")])' <<<"$candidates")
        # Metadata may add a build suffix; downloaded Debian Version MUST equal
        # the complete pin. Never accept an arbitrary first architecture match.
        candidate=''
        while IFS= read -r record; do
            if version_matches "${childver#*:}" "$(jq -r '.version' <<<"$record")"; then
                [[ -z $candidate ]] || die "Ambiguous API builds for $child=$childver; manual review required"
                candidate=$record
            fi
        done < <(jq -c '.[]' <<<"$candidates")
        [[ -n $candidate ]] || die "Exact dependency unavailable: $child=$childver on $parent_platform"
        download_package "$candidate" "$child" "$childver"
    done < <(tr ',' '\n' <<<"$deps")
}
download_package "$MATCH" unifi
# Discovery is finished. Remove the token header before allowing APT's _apt
# account to traverse this root-owned directory and read verified public debs.
# Keep directory listing, writes and all other working files restricted.
rm -f "$WORK/auth"
chmod 711 "$WORK"
chmod 644 "${PACKAGES[@]}"
echo 'APT dry run: complete verified local package set (removals forbidden).'
printf '  %s\n' "${PACKAGES[@]}"
if ! apt-get --simulate --no-remove install "${PACKAGES[@]}"; then
    die 'APT dry run failed. Nothing was installed.'
fi
echo 'APT dry run succeeded. APT may obtain other dependencies from configured repositories.'
if ask_install; then
    if ! apt-get --no-remove install -y "${PACKAGES[@]}"; then
        die 'APT installation failed; inspect package state before retrying.'
    fi
    echo 'APT transaction completed successfully. Installed versions:'
    for name in "${!REQUIRED[@]}"; do
        actual=$(installed "$name")
        [[ -n $actual ]] && dpkg --compare-versions "$actual" eq "${REQUIRED[$name]}" || die "Post-install version verification failed: $name"
        printf '%s %s\n' "$name" "$actual"
    done
else
    echo 'Install declined. Downloaded files remain; no installation was performed.'
fi
