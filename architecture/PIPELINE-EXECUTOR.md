# Owned process executor

*[Deutsch](PIPELINE-EXECUTOR.de.md)*

The general Hybrid-C pipeline port can wrap a **new explicitly configured child process** with
`ocean_resources.process.OwnedProcessExecutor`. It reuses Ocean's process-group supervisor on
POSIX and suspended-start, kill-on-close job objects on Windows. It never adopts a PID from a
queue file or stops an existing service. The original pipeline remains the owner of its job,
business rules, input/output and checkpoint semantics.

## Boundaries

- The existing arbiter must already own the grant and bind this execution identity. The adapter
  is not an authorization, resource-profile, budget or native task-claim authority.
- `ProcessCommand` declares immutable argv, an absolute local cwd, exact source pins including
  the executable and an explicit environment. Source hashes are checked before launch. This is
  cooperative provenance, not a sandbox against another process of the same user changing files.
- Commands must implement the protocol below; existing jobs without checkpoint support remain
  ineligible. A caller-supplied application validator must approve the actual checkpoint payload.
- Production resource admission remains closed in the current arbiter. An owned small-process
  test with fixture capacity does not certify model-sized memory, free CPU or system reserve.
- Child output is not copied to the terminal; the application owns its normal logs/results.
  Parent lifecycle state is confined to the explicit local state directory.
- The process/job boundary covers cooperating descendants. External daemons, model servers,
  escaped process sessions and remote workers require their own lifecycle/residency adapter.

## Worker protocol v1

The environment variable `OCEAN_RESOURCE_RUN_DIR` points to a new private per-execution directory.
The parent writes `start.json` with schema `ocean-owned-process.v1`, grant, execution_identity
and resume (null or the previous verified application payload). The worker acknowledges
`ready.json` with the same schema, grant and execution_identity.

On `checkpoint.request.json`, the worker reaches an application-safe point, durably stores its
own state, and atomically writes `checkpoint.json` with the same identifiers, payload (JSON
object) and `quiescent: true`. It must stay quiescent until stopped. Another execution's answer,
unknown quiescence, missing/invalid JSON, duplicate keys, NaN and oversized messages fail closed.
The parent bounds acknowledgement waiting and validates the application payload. It then seals
and fsyncs `accepted.checkpoint.json`; the accepted file must still match before any stop.

Only then is the owned process group/job terminated. Windows separately queries ActiveProcesses
until zero; POSIX requires an empty owned group. `ExitReadback` with zero residency refers to that
ended owned tree, not a claim about global free RAM. The arbiter still requires a newer independent
capacity readback before release. A matching next execution receives the exact checkpoint payload.

An invalid or absent checkpoint leaves the running worker and resource reservation in place.
`close()` is explicit own-process emergency cleanup; it neither publishes a result nor releases
the arbiter or invents a checkpoint. Failed Windows job assignment reaps the explicit suspended
child rather than attempting to terminate an empty job only. Failed starts retain the arbiter's
reservation pending verified reconciliation.

On POSIX an isolated Python bootstrap (`-I -S`) waits on an inherited pipe before
executing the application. Only a captured process-group fence and stored execution
can open that gate; EOF or timeout exits without starting application code. This also
covers hosts that automatically reap exited children (`SIGCHLD=SIG_IGN`). Both pipe
ends are closed on parent failure. After a verified exit, checkpoint/stop retries
revalidate the persisted checkpoint and do not signal the old process identity again;
a temporary capacity-probe failure therefore remains recoverable.

## Python integration

```python
from ocean_resources import BACHFacade
from ocean_resources.process import OwnedProcessExecutor, ProcessCommand

# command = ProcessCommand(immutable_argv, local_cwd, exact_source_pins, explicit_environment)
# arbiter and its resource profiles must be independently accepted for the actual workload.
with OwnedProcessExecutor(arbiter, command, local_state, application_checkpoint_validator) as executor:
    facade = BACHFacade(arbiter, {socket_id: executor.adapter()})
    # Existing pipeline pointer -> arbiter.submit(...), facade.start_next(), safe yield/resume.
```

No service installation, queue migration, publication, model start or new schedule happens on
import. Controlled production integration is a separate step after native adapters/profiles,
restart reconciliation, user override and application-specific acceptance.

## Acceptance

`tests/test_pipeline_process.py` uses its own 1 MiB Python worker and temporary state. It checks
checkpoint 7, confirmed process end, a separate interactive worker and exact resume 14; owned
helpers must end too. Negative cases cover changed source, wrong execution identity, invalid
checkpoint, timeout, corrupted accepted state and Windows assignment failure. These are real
process-lifecycle checks with synthetic admission budgets, not a live Buddha/model demonstration.
