# Open OCEAN TODO

*[Deutsch](TODO_de.md)*

## Immediate reliability follow-ups

- [ ] Add a workspace-scoped interprocess start lock. Two direct lifecycle invocations can
  currently pass the empty-state preflight before either supervisor writes runtime state. The
  ASUS-GEI logon task avoids this by disabling `StartWhenAvailable` and using one trigger, but the
  lifecycle itself must fail closed under simultaneous starts.
- [ ] Serve an OCEAN favicon or remove the favicon request; current browser acceptance is healthy
  but records one non-functional `/favicon.ico` 404.
- [ ] Perform a real ASUS-GEI reboot and read back the unchanged `EllmosOceanFullUserStart` task,
  exact tagged checkout, process tuple, port ownership, HTTP identity and Full Ocean readiness.

## Release breadth

- [ ] Run a complete fresh Full Ocean installation on a non-development host.
- [ ] Derive and test the default-deny OPEN OCEAN public allowlist independently from FULL OCEAN.
- [ ] Continue BACH functional-parity work; treat newly discovered BACH-only extraction as an
  exceptional, value-gated module cycle.

These items do not authorize publication, a visibility change or removal of `PRIVATE.txt`.
