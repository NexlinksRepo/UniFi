# v2 field validation

Observed October 25, 2026, on the compatibility baseline identified in the README.
Times below are America/New_York (EDT). These observations occurred after the
v2.0.0 ZIP was built and do not modify that artifact.

## Gateway reboot

The owner installed and committed v2.0.0, then rebooted the gateway.

- The enabled persistent service started automatically at 8:03:57 PM.
- It restored runtime metadata settings by 8:04:40 PM.
- Saved intent remained enabled and committed, with no trial deadline.
- The active proxy hash matched the installed candidate manifest.
- The identity registry was fresh and continuing to update.
- Normal DNS resolution succeeded, and a certificate-verified request to the
  UniFi portal endpoint returned HTTP 302.
- Real LAN-client probes through the main listener and one WAN-policy listener
  produced matching proof hashes with the expected client name and stable ID.

A further native forwarder configuration change was observed at 8:06:13 PM. The
manager logged successful reconciliation at 8:06:17 PM. All three managed blocks
were present afterward, with active state, zero failures, and no last error.

## Network application restart

The Network application was explicitly restarted at 8:09:14 PM. It returned to
active state at 8:10:38 PM. The v2 manager remained active.

At 8:10:56 PM, the manager reconciled regenerated configuration. All three managed
blocks were present afterward. A fresh real LAN-client query through the main
listener produced a matching device-header proof record. The manager reported
zero failures and no last error.

## Limits

The inspected intervals did not contain the specific native message
`DNS Shield server list has been updated, restarting dnscrypt-proxy`. These are
live reboot/application-restart and regeneration results, not validation of that
exact server-list-update scenario.

The checks do not establish long-duration stability, every client/VLAN path, both
DNS transports on every listener, real WAN failover, firmware upgrade behavior,
or authenticated cloud continuity. An HTTP response proves endpoint reachability;
an internal device-header proof is not a NextDNS dashboard API readback.

Actual device identities, profile IDs, public addresses, and raw gateway logs are
omitted from this public note.
