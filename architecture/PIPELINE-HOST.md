# General pipelines and host resources

*[Deutsch](PIPELINE-HOST.de.md)*

Hybrid C keeps planning and visibility in Ocean/BACH and execution state in the existing
pipeline executor. Compute, repository care, outreach, editorial work, publication, stores,
translation, game design, video and software builds use the same reference contract.
The packaged catalogue is an example mapping of the original groups, not a second job store,
an installed publisher or approval to create accounts. Group 4 has multiple build targets;
the earlier 15-group/16-row presentation question does not create another pipeline.

## Existing core and new observation layer

The [resource arbiter](RESOURCE-ARBITER.md) owns one socket and one slot per configured host.
It still admits only explicit fixture profiles: publication gates, budget, real CPU profiles,
model lifecycle and native task claims cannot be obtained from a catalogue or JSON assertion.

`BACHFacade.request_from_pipeline` and `slot_request` preserve the original planner task,
executor job and source hash for any pipeline, without requiring a local model binding.
They never claim a task or copy a queue entry. Existing `request_from_task`, model target fields
and inference-gate interfaces remain compatible.

`host` observes the local machine without writing state or starting services. Windows uses
GlobalMemoryStatusEx, macOS uses vm_stat and the native memory-pressure level, Linux uses
MemAvailable. macOS free+inactive+speculative pages are a reclaimable estimate, not a guarantee;
compressed pages are not counted again. Windows/Linux pressure is explicitly a conservative
available-memory ratio, not a native pressure certification. CPU count and load average are
not an authoritative free-CPU measurement. Disk space is measured separately.

Observations carry UTC Unix seconds; monotonic uptimes from different hosts must not be compared.
Unknown, stale, future or incomplete readings remain HOLD. Headroom is an explicit caller choice,
not a measured model profile. The core's native admission clock remains monotonic and separate.

`shadow_plan` checks explicit pipeline job projections, platform, resource estimates, RAM/disk
headroom and reported gates. Even a matching candidate has `start_authorized: false`.
The current torch is unknown until connected to the actual arbiter; an observer never claims idle.
`route_job` prefers the central host for heavy or recurring work and local execution for small
one-off work. Capability and headroom precede that preference. Any fallback is a proposal for
the planner; it does not retarget an existing claimed execution.

## API and CLI

```text
python -m ocean_resources                 # unchanged read-only manifest
python -m ocean_resources catalog         # packaged example catalogue
python -m ocean_resources host            # native read-only observation
python -m ocean_resources shadow --jobs explicit-projection.json \
  --reserve-ram-bytes 4294967296 --reserve-disk-bytes 8589934592
```

The example reserve values are illustrative operator choices, not certified defaults.
Use `--catalog custom-catalog.json` only with the shadow command. Job projections are bounded
JSON arrays with exact fields: job_id, pipeline_id, host_id, priority, interactive, size_class,
ram_bytes, cpu_units, disk_bytes, gates, planner, task_id, executor_job_id, source_sha256.
Resource demand can be null (HOLD); size_class is small, large or unknown. Reported gates do
not prove authorization. Malformed/duplicate JSON keys, unknown pipelines, duplicate job IDs
and invalid values are rejected. The CLI never scans production queues or writes a task.

## Integration order

1. Observe each actual host and keep existing queue/claim/publication ownership intact.
2. Profile one real executor, its CPU/RAM/disk need and checkpoint/verified-exit contract.
3. Bind the existing planner and executor via the pointer and the single host arbiter.
4. Verify compute → checkpoint/exit → interactive request → return → resume without data loss.
5. Add media, builds and services through the same port. Model-backed translation is one user.

Schedules and ongoing jobs are not migrated by this change. Authenticated user override,
production restart reconciliation, accepted real adapters and native BACH service wiring remain
explicit deployment work. No model, publication, store submission or service start is implied.

The POSIX writer regression is covered by a real fork: closing an inherited child descriptor
must not unlock the parent's file description. A third writer remains excluded until the
parent releases normally.
