# v3.0.0 validation - October 25, 2026

v3 fixes registry publication during routine name refresh. No v3 production
installation or commit was performed during these checks.

## Local validation

- 85 Python tests passed, including 14 new registry-refresh regressions.
- The tests check old-registry readability before atomic publication, source and
  rename failures, unchanged expiry on failure, expired/malformed/wrong-profile
  data, changed attribution scope, startup observation, failed listener health,
  and explicit disable.
- Full Go proxy suite passed on Windows using Go 1.27.3.
- Linux ARM64 candidate and native test executable rebuilt for v3 runtime paths.
- No new Go dependencies or DNS wire-format changes were introduced. The
  profile-scoped registry format remains version 2; package version is 3.0.0.

## Field boundaries

The new publication behavior has regression coverage. A real production v3
cutover, v3 reboot, native DNS Shield server-list refresh, ISP failover, and
long-duration field stability have not been established by local tests.

V2-TEST-RESULTS.md and V1-TEST-RESULTS.md are historical records. The successful
v2 reboot and Network restart are not evidence that those scenarios have passed
on v3. The five-minute trial and explicit commit remain.

Some negative unit tests deliberately print errors about expired trials. Mocked
lifecycle tests can print a successful commit message; that is not a gateway
installation.
