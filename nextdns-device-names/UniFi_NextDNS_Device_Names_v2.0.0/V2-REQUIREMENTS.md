# v2 requirement status

| Requested behavior | Implementation and present evidence |
| --- | --- |
| Find every local NextDNS forwarding instance | Enumerates native runtime TOML/config files and matching processes, resolves their graph, rejects ambiguous or unsupported layouts. Gateway discovery found main/eth8/eth9 instances, each listening on br0/br2. Arbitrary DNS implementations and unsupported layouts are not covered. |
| Supported client-name interface | Optional official API adapter with HTTPS, no redirects, pagination, and schema checks. Fixture-tested only because no API key was provided. Default PostgreSQL access was retained at the user's direction and passed live isolated diagnostics, but it is private-schema compatibility access, not an officially supported interface. |
| Correct profile-scoped identity | Registry v2 is keyed by selected NextDNS profile. Go tests check isolation. IDs are profile-derived and stable across name/address changes. Historical database last_ip and stale neighbors are not accepted as current IP ownership. Conflicting ownership/names are omitted. |
| Native generation and persistence | Native generation cannot be implemented by this external package. A committed systemd service discovers/reconciles generated output and is enabled for boot. Native server-list regeneration is simulated in transaction tests. Real reboot/provisioning/firmware regeneration has not yet been validated with v2. |
| Routing, caching, DNS, cloud preservation | No route/firewall commands; native cache and connection-mark directives retained. WAN forwards use the same terminal proxy but bypass the extra local main hop for identity. Actual WAN-policy behavior and cloud connectivity must be checked during trial. No broad guarantee is claimed. |
| Five-minute install trial | Default is 300 seconds, not boot-enabled. Fixture tests cover expiry and refusal to commit an expired trial. |
| Commit when ready | Explicit commit.sh validates active configuration and listeners before enabling boot and persisting committed state. No production commit was performed during package validation. |
| Install shows interfaces and active naming paths | Inventory precedes mutation. Coverage rows identify instance, configured listening interfaces, port, upstream path, and profile. ENABLED is printed only after configuration and listener checks. Real client/VLAN attribution requires LAN probes; the installer does not claim it proved every client path. |

This is an experimental v2.0.0 external package ready for controlled trial, not a
claim that all native-product requirements have been fulfilled or that field
reliability is established. A future official UniFi implementation would remove
the private-schema and external configuration-reconciliation dependencies.
