# Hybrid resource arbiter: first seam

*[Deutsch](STECKPLATZVERTEILER.md)*

Status: offline core and injected adapter contracts. This is not live BACH-IN, production resource admission, a new queue, task migration or a release. The hybrid architecture was chosen by the owner on 2026-10-13; configuration and rollout are separate steps.

## Contracts and ownership

A **ResourceSocket** is a large RAM/CPU consumer. A **SlotRequest** is a user/job attached to that socket. The **torch** is exactly one active socket and its active slot per host. Other small work and operating-system processes remain outside this first seam. No hard-coded large-resource threshold is inferred.

`ocean_resources.HostLocalArbiter` owns the admission state. Every cooperating client on a host must use the same configured host identity and local state directory. `HostWriterAuthority` requires an explicit existing absolute directory, refuses OneDrive/UNC and linked paths, and uses a nonblocking OS lock. This is a cooperative writer boundary, not a security sandbox against another process that can replace the directory or choose a different configuration. Its writer journal is separate from BACH's Polarstern task writer lease (`resource_lease.py` / migration 053); that lease and BACH databases are untouched.

Grant generation plus a fresh writer-session identity fence callbacks. An active reservation is recorded in a checksummed, fsynced journal on the locked inode. An unresolved or malformed journal refuses a new arbiter after restart. There is no automated recovery or TTL-based release. In-session requests, events and checkpoint references are held in memory; the application owns durable job/checkpoint storage. Production restart recovery remains a gate.

`CapacityReadback` must have the correct host, a fresh finite monotonic time, a strictly newer sequence, positive available RAM/CPU after a **verified system reserve**, and a positive pressure check. Unknown parameters fail closed. Admission is currently restricted to explicitly supplied **fixture** profile names. Real OS/model profile certificates and their authorization path are not implemented.

## Handoff and compatibility

1. Submit an immutable request; exact repeated idempotency keys return the original request. Divergent duplicates fail closed.
2. Admission reserves the single torch. The executor binds a stable execution identity before start; start failure retains the reservation.
3. A return request prevents new inference turns and heartbeat renewal. It does not terminate an existing inference call.
4. The application supplies a canonical, generation-bound checkpoint (maximum 1 MiB). Invalid checkpoints never authorize stop.
5. The injected executor stops its own work. A separate readback must confirm the matching execution ended and its process residency is zero.
6. A newer host capacity sample must follow that exit before the torch is released. Insufficient capacity can still hold the *next* request.
7. The old job may requeue and resume from the verified application checkpoint. SIGSTOP is not a RAM-release proof.

Fairness permits at most three consecutive interactive grants while background work waits, then serves a background slot; priority and FIFO apply within each class. This bounds grant order, **not wall-clock chat latency**, because an active executor must reach a safe checkpoint. Policy durations are configurable; the core installs no polling service. A user override selects a waiting request with a reason and bounded expiry, and is recorded. Production override authentication/UI and automatic idle-time scheduling remain separate gates.

`BACHFacade` is an immutable injected executor map, not a BACH runtime import. `request_from_task` preserves `required_model` and `assigned_slot`, checks an exact `HybridPlannerPointer` and never claims/edits a real task. `ComputeExecutorAdapter` exposes start/checkpoint/stop/readback callbacks without discovering queues. No existing jobs are copied.

`ModelSocketInferenceAdapter` preserves the existing `model_target` fields (`socket_id`, `binding_id`, `agent_id`, `backend`, `model`) and async `HostInferenceGate.turn` API. It checks the current resource grant before and within the native gate. It neither replaces the inference gate nor loads/unloads a model. Model residency, same-model reuse and native BACH wiring are unaccepted live adapters.

## API, manifest and CLI

```text
python -m ocean_resources                  # JSON manifest; read-only
python -m ocean_resources manifest         # same manifest
python -m ocean_resources fixture-demo     # synthetic compute → chat → resume; own temporary state only
python -m pytest tests/test_resource_arbiter.py tests/test_resource_cli.py -q
```

The packaged `ocean_resources/manifest.json` records API, compatibility, state ownership and remaining gates. No native GUI extension exists at this seam. The existing task-union contract remains `union-schema-specified-fixtures-green-no-live-cutover`; this change does not promote any parity claim. The pipeline count remains an open count question.

Tests include a real owned 1 MiB dummy child with durable checkpoint readback, confirmed exit and resumed progress. Capacity in that scenario is synthetic; it does **not** establish a model-sized RAM budget, host-wide free-memory delta or Buddha production-chat acceptance.

## Remaining gates

Independent review; profiled and authorized real adapters; measured capacity/system reserve; application-safe checkpoint and verified model unload/process-tree exit; BACH-IN and legacy routing fixtures; restart reconciliation; authenticated override and idle/deadline scheduling; native GUI integration if needed; pinned recipe/consumer projection; controlled live acceptance. No service installation, production queue write, model call, release or cutover is included.

Primary OS-lock contracts: [Python fcntl](https://docs.python.org/3/library/fcntl.html#fcntl.flock), [Python msvcrt](https://docs.python.org/3/library/msvcrt.html#msvcrt.locking). These document locking primitives, not an independent host security guarantee.
