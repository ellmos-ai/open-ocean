# Native pipeline restart evidence, v1

This contract covers the shared Ocean resource pipeline for compute, builds, media, services and model-backed work. It is not specific to translation jobs.

## Durable evidence written during an owned process run

The host writer journal remains the single bounded, checksummed reservation journal. While a grant is active, it now carries two optional references:

- `execution_evidence` binds the grant and execution identity to the pinned command fingerprint, host-local run directory, owner PID, child PID, optional process creation and boot times, and the containment mechanism.
- `checkpoint_evidence` binds the same execution to the hash of the accepted checkpoint file and its payload hash. The checkpoint payload remains in the application-owned run directory; the journal does not copy or expose it.

Before any application instruction can run, the assigned child and its closed application gate are recorded and fsynced. After the final source and capacity admission succeeds, the journal advances to `gate_state=may-open` and is fsynced before the gate byte is sent. If either journal write fails, the gated child is cleaned up and the reservation remains held.

After application validation, the accepted checkpoint file contents are fsynced and renamed into place, then its file and payload hashes are recorded before stop is requested. Stop re-reads the checksummed writer journal and requires that exact binding. A journal write/fsync failure prevents stop and retains the reservation. The writer journal refuses records larger than its 64 KiB bound.

## Restart behavior and limits

The durability claim here covers a worker/owner-process crash while the host and filesystem remain running. It does not claim survival of power loss, kernel failure, or storage rollback: the checkpoint file is fsynced before rename, but its parent directory is not fsynced after rename. These records are diagnostic and recovery inputs, not proof of current process absence. A process ID, process group, run directory, creation time, or closed-job policy cannot by itself release a grant. A new writer still holds an unresolved reservation. It does not adopt, signal, resume, or requeue the old process. Independent OS-level residency reconciliation and a fresh validation of the original task claim are still required.

`gate_state=closed` proves the application gate was not durably marked as potentially open. `gate_state=may-open` is intentionally conservative: the gate byte may or may not have been delivered. Neither state is a restart release decision.

The checkpoint reference is durable only while the unresolved grant remains in the journal. The separate crash window after a verified release clears that journal but before an in-memory queue/checkpoint handoff is fully recovered remains open. Durable task requeue, checkpoint retention across completed grants, and automatic resume are not implemented here.

External model and GPU residency remain outside the qualified CPU process path. This change does not activate any production pipeline, migrate queues, or alter task ownership.
