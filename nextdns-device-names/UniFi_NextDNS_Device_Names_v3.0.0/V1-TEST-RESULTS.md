# Validation results

## Version 1.0.2

The monitor update was tested locally on October 23, 2026. All 42 Python tests
passed, including five tests added for query-free scheduled checks, listener
failure reporting, query-free rollback, explicit diagnostic behavior, and an
update from version 1.0.1 that preserves commit/deadline and restarts no DNS
processes. The scheduled validation test fails if any DNS exchange or synthetic
header probe is attempted, and checks that listener connections send no payload.

The supplied proxy binary, Go source patch, WAN configuration and shell entry
points are unchanged. No repeat Go build is needed for this monitor-only update.
Live SSH is currently blocked by the execution environment, so version 1.0.2 has
not yet been deployed or tested on the gateway. The production checks below were
performed with version 1.0.1 and remain baseline evidence for the unchanged proxy.

Automatic checks validate processes, configuration, binary hashes, name refresh
and TCP listener readiness. They no longer test DNS responses, UDP forwarding or
per-device HTTP headers. Explicit `test.sh`/LAN diagnostics and fresh-install
preflight still send their one-time test queries.

## Version 1.0.1 baseline

Version 1.0.1, built and tested October 23, 2026 for the inspected ARM64 UniFi gateway.
The proxy source and binary are unchanged from version 1.0.0; this update changes
the deployment, collector, monitor, WAN-forwarder integration and recovery.

| Check | Result |
| --- | --- |
| Unmodified upstream proxy suite on Windows | Passed |
| Full patched proxy suite on Windows | Passed |
| Nine new proxy test groups on the gateway, including eight malformed/trust subcases | Passed |
| Sixty simultaneous HTTP requests, alternating DoH GET and POST, with separate device names | Passed |
| EDNS client extraction, IPv4/IPv6, UDP/TCP loopback peers and MAC/IP fallback | Passed |
| EDNS removal, preservation of DNSSEC/padding, expired/invalid registry and unsafe-name rejection | Passed |
| Refusal to follow cross-origin redirects carrying device headers | Passed |
| Thirty-seven Python tests on Windows, covering installer/recovery, WAN migration, commit preservation and source patch/reversal | Passed |
| Thirty-five collector/installer/recovery Python tests on the gateway | Passed |
| Native dnsmasq syntax checks for main and both WAN metadata configurations | Passed |
| Candidate using the existing SDNS stamp on an isolated loopback port, with UDP/TCP queries | Passed |
| Two different real client records mapped to separate per-request header proof records | Passed |
| Query from the LAN computer through a temporary native-config dnsmasq listener to the candidate and NextDNS | Passed |
| Actual busy bind-mount removal restoring a private target while its ELF executable is running | Passed |
| Actual systemd ExecStopPost recovery after SIGKILL of an isolated test process | Passed |
| Bounded handoff defers private ExecStopPost; independent timer forces private recovery | Passed |
| Live version 1.0.0 â†’ 1.0.1 migration preserves committed=true and deadline=null | Passed |
| Main DNS and encrypted-proxy PIDs unchanged across live update | Passed |
| Real LAN computer, no supplied EDNS identity, through ports 53, 20201 and 20202 over both UDP and TCP | All six proof hashes matched the expected device name |
| Live local refreshes after update, with both WAN processes and monitor active | Passed |
| Native encrypted DNS configuration and original connection-mark policy retained | Passed |
| User-requested production rollback after the update: stock binary, both original WAN config hashes, removed metadata include and stopped monitor | Passed |
| Both LAN interfaces, all three listener ports, UDP/TCP stock DNS checks after rollback | All twelve passed |
| Fresh pre-install native checks and isolated candidate tests after rollback | Passed |

The live LAN test sent no client metadata from the computer. The temporary
dnsmasq listener attached the original identity, and the proxy completed its
encrypted request with the expected known device name and stable ID. Its proof
hash matched the hash produced by the computer. The test listener used a private
copy of the native configuration because UniFi's socket/interface setup differs
from a generic dnsmasq invocation.

The original version named requests through main DNS but lost identity when a
WAN-specific forwarder sent them through main DNS as loopback requests. A live
LAN probe to the WAN listener reproduced the missing proof before migration.
After migration, all three listeners produced the expected device-header proof
for both LAN transports. A short passive sample also showed original identities
on WAN-policy client traffic, with no client identity replaced by loopback. One
observed client had neither a UniFi alias nor a DHCP hostname and remained unnamed;
this is a missing name record, rather than a device-count limit.

Failure tests cover watchdog startup, mount failure, dnsmasq syntax failure,
both service restart phases, initial validation, trial expiry, two consecutive
health failures, repeated/manual rollback, edited metadata includes, unmount
failure, failed main/WAN dnsmasq recovery, failed WAN migration and modified
managed blocks. They check that metadata is stopped in all forwarders before
returning to stock proxy code, that later native changes survive rollback, and
that a monitor update preserves commit/deadline and avoids a main DNS restart.

The installer tests use simulated DNS processes and mounts. The runtime drill
separately validates the real mount/recovery primitives using temporary files
and temporary services. Production was restored to stock during investigation of
the old busy-mount rollback bug, then the user's new committed installation was
migrated in place. The user subsequently requested a clean install and manually
rolled the new version back. Read-only checks verified the complete WAN-aware
rollback: stock proxy hash, no executable bind mount, original WAN config hashes,
no metadata include, monitor inactive, and working UDP/TCP DNS on every listener.
The gateway was left on stock DNS. A real ISP outage/failover and complete
dashboard coverage were not tested. Per-request
proof confirms completion of the encrypted request with the expected headers; it
is not a NextDNS dashboard API readback.

The nine new Go test groups are:

1. TestNextDNSExtractAndStrip
2. TestNextDNSTrustAndMalformedMetadata
3. TestNextDNSExpiredOrInvalidRegistry
4. TestNextDNSIPv6AndTCPClientMetadata
5. TestNextDNSIPOnlyFallback
6. TestNextDNSProviderAndHeaderValidation
7. TestNextDNSNoPluginFastPathStillStrips
8. TestNextDNSConcurrentHTTPHeaders
9. TestNextDNSRedirectDoesNotLeakHeaders

The package is pinned to dnscrypt-proxy 2.1.14 at upstream commit
e27f9b8128827cad5b5c7c6b47a4902daf6b4c26. The supplied production candidate was
cross-compiled with Go 1.26.10 for Linux ARM64, CGO disabled, with debug symbols
removed and source paths trimmed. The manifest includes candidate and stock
binary SHA-256 values. See SHA256SUMS for all packaged file hashes.
