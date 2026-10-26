# v3 requirement status

- Routine refresh preserves the current valid registry and publishes a complete
  replacement atomically. Failures never renew old data's expiry.
- Reuse after a failed lookup requires unchanged profile/forwarding scope,
  unexpired valid data, and healthy native listeners. Unsafe conditions and
  explicit disable still turn enrichment off.
- Inherited resolver discovery, request-specific profile-scoped headers,
  interface summary, regeneration reconciliation, and disable/rollback remain.
- Five-minute trial and explicit commit remain. v3 uses its own versioned service,
  install directory, and runtime registry. Disable v2 before starting v3.
- The default name source remains the private PostgreSQL compatibility backend;
  the optional official API adapter still requires live API validation.
- This is an external integration. It does not make UniFi generate settings
  natively. Reboot/provisioning/failover behavior must be validated for v3 rather
  than inferred from v2's field results.

See CHANGELOG.md, TEST-RESULTS.md, and README.md for details.
