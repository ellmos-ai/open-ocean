# Native host capacity and system reserve

*[Deutsch](PIPELINE-CAPACITY.de.md)*

`ocean_resources.capacity.NativeCapacitySensor` implements the existing trusted
`CapacityReadback` port with real host observations. It does not grant a workload,
profile, task claim, model call or publication permission. The arbiter's default
profile gate remains closed.

Install the optional `resources` extra (`psutil>=5.9.6,<8`) for this path. Default
manifest, catalogue, host and fixture commands do not import psutil. The package
never installs dependencies or starts a service at runtime.

## CPU and reserve semantics

Two per-logical-CPU cumulative snapshots, separated by an explicit 0.1–1 second
interval, establish observed idle shares. Each individual counter must be finite,
nonnegative and nondecreasing, with unchanged topology and affinity. Linux guest
counters duplicate user/nice counters and are excluded from totals. I/O wait and
other non-idle counters count as busy. Overlapping optional interrupt counters can
understate capacity; they cannot add idle time.

Only eligible affinity CPUs count. Available CPU units are the floor of their
measured idle shares minus the positive configured CPU reserve. On Windows,
processor-group layouts above 64 logical CPUs stay HOLD until their effective
budget is verified. A process inside any Windows Job also stays HOLD: host-wide
RAM and affinity do not prove the effective limits of nested Jobs. Unknown Job
membership stays HOLD. macOS uses its exposed host CPU set. Linux counters remain
observable, but effective cgroup RAM/CPU budgets are not yet verified by this
adapter and therefore always keep reserve verification false.

RAM and disk observations bracket the CPU interval. Available RAM is the lower
observed value minus the explicit RAM reserve, never below zero. Both pressure
readings must be normal and both disk readings must preserve the disk reserve.
The oldest monotonic timestamp is retained: a slow follow-up probe does not make
old CPU/RAM input fresh. Failed, missing, regressing or stale probes yield HOLD.

This is an instantaneous conservative observation, not an OS-enforced CPU/memory
limit or a prediction of future unmanaged host activity. A logical CPU share does
not promise equal speed across heterogeneous cores. Application RAM/CPU profiles,
native ownership/claim checks, lifecycle adapters and host authority remain
separate gates. Memory held by a stopped process is not counted as released.

Counter and affinity semantics follow the [psutil API reference](https://psutil.io/api/).

## Explicit read-only CLI

```sh
python -m ocean_resources capacity \
  --reserve-ram-bytes 4294967296 \
  --reserve-cpu-units 1 \
  --reserve-disk-bytes 10737418240 \
  --capacity-directory /absolute/local/work
```

Use one shell line on Windows. All three reserves and the existing absolute
filesystem directory are required. The numbers above demonstrate explicit inputs;
they are not a measured policy for an arbitrary host. A valid observation command
returns JSON and exit 0 even when its result is HOLD; malformed policy/input exits
2. Consumers must inspect the state and full readback, not only the exit code.
`start_authorized` is always false. CANDIDATE means observed headroom only.

## Integration

```python
from ocean_resources.capacity import CapacityPolicy, NativeCapacitySensor

policy = CapacityPolicy(ram_reserve, cpu_reserve, disk_reserve, local_directory)
sensor = NativeCapacitySensor(policy)  # native host identity, bound to this process
# Pass sensor to the one existing HostLocalArbiter only after the other
# application/profile/authority gates are independently accepted.
reading = sensor()
```

The sensor serializes calls and emits a newer sequence even after failed probes.
It rejects a forked process before touching a potentially inherited locked mutex,
and rejects a foreign host. This increment adds native
measurement; it does not install the shared host service, qualify production
profiles, change existing queues or complete the live Buddha/compute acceptance.
