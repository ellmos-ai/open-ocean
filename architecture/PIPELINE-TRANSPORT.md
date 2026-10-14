# Shared host transport

*[Deutsch](PIPELINE-TRANSPORT.de.md)*

`ocean_resources.service.HostService` exposes one already configured
`HostController` to separate native client processes. It is an optional explicit
loopback HTTP transport, not a durable queue, executor registry or replacement
for a pipeline's job state. Compute, services, media and builds use the same
socket/slot/grant contracts. Native workload and publication gates remain intact.

## Ownership and startup

The integrating host application creates the existing writer, native capacity
sensor, reviewed workload profiles, fixed executor adapters and controller. It
then explicitly constructs `HostService(controller, configured_operator, port=0)`
and runs `serve_forever()` in its own foreground service lifecycle. That loop
accepts HTTP independently of one explicitly managed poll worker, so a native
callback can read the same service without blocking its own HTTP acceptance.
Construction
binds only `127.0.0.1`; port 0 requests an OS-assigned port. Nothing installs a
daemon, changes launchd/tasks, discovers jobs, scans configuration or opens BACH
databases. The service polls the existing controller at an explicit .05–1 second
interval; native lifecycle latency can be longer.

`stop()` ends new acceptance/polling. `close()` waits for its accept loop, poll
worker and bounded request workers within one shared five-second drain budget.
Unexpected poll failure makes status HOLD and prevents new work, retaining the
original torch. Neither method frees an active torch, unloads a model, stops an
executor or clears its durable reservation. The caller must retain the writer
and executors until native completion or explicit reconciliation. An unfinished
loop/request causes HOLD; it must not be interpreted as released RAM. A crashed
host still meets the existing unresolved-journal restart gate.
Stop is an admission fence: no new request or tick is admitted after it. An
operation already admitted before the fence may finish while close drains it;
transport shutdown does not roll back a native operation already in progress.

## Authentication and session fencing

Each request carries an existing scoped controller client ID and private token
in headers; no token enters the URL, repr, audit or HTTP access log. Native
`ocean_resources.client.HostClient` uses direct loopback connections without
proxy discovery or redirects. Private delivery of tokens and the endpoint is
the host application's responsibility. Configuration is privileged, never a work
request. A browser Origin, foreign Host, duplicate framing/authentication header,
chunked request, invalid JSON, duplicate key or nonfinite value is rejected.
There are at most eight request workers and one-MiB message limits. A two-second
absolute header/body input deadline closes slow incomplete requests even when
bytes keep arriving; it is rechecked before admitting the parsed request. Stop
also closes incomplete, not yet admitted sockets. Already parsed/authenticated
operations may drain beyond the read deadline. No CORS or unauthenticated status
endpoint is exposed.

Every message binds the configured host and current writer authority ID.
Replacing the writer requires explicit client reconfiguration; an old client
cannot submit or control the new session. The controller continues to enforce
socket scopes, priority floors, interactive permissions, request ownership,
override expiry and replay protection. Only an operator can request an explicit
tick or override; the host's configured operator performs automatic polling.

POST `/v1/focus/{operation}` accepts exact message fields:
`schema=ocean-host-transport.v1`, `host_id`, `authority_id`, `payload`.
Operations are status, submit, begin_turn, end_turn, finish, override and tick.
Contract payloads contain the exact dataclass fields, including null optional
fields. The response is JSON OK/result or sanitized HOLD. A timed-out mutating
request is not proof of failure: reread the same native request identity before
retrying; immutable submit/override identities retain their existing semantics.
A visible torch during TRANSITION is a reservation, not executor readiness.
Consumers wait for one status snapshot with RUNNING and the intended request
identity before starting a turn; a writer session or return transition still
requires revalidation at the operation itself.
Automatic polling and explicit finish/tick operations share one transport
lifecycle mutex. A native request waits at most two seconds to enter that mutex,
then returns HOLD without starting an operation if still busy. The accept loop
skips a busy poll rather than blocking other requests. Status, submissions and
turn completion remain available while an admitted lifecycle operation drains.
This does not bypass the controller lock if an application independently calls
the controller; integrating applications must use one polling owner.

```python
from ocean_resources.client import HostClient

client = HostClient(configured_port, configured_host, current_writer_authority,
                    configured_client_id, privately_delivered_token)
state = client.status()
# client.submit(native_request), begin_turn/end_turn, finish and override
# reuse existing contracts, not arbitrary commands or caller-supplied grants.
```

This transport does not provide CLI configuration, a GUI panel, product daemon
installation, native model/queue cutover or production family certification.
Those consumers must use this same authority rather than instantiate a second
arbiter. Tests use actual HTTP and a separate Python client with injected fixture
executors; that is not evidence of live Buddha or production resource admission.
