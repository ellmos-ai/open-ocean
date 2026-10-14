# Reviewed workload profiles

*[Deutsch](PIPELINE-PROFILES.de.md)*

Host capacity and workload demand are separate facts. `ReviewedProfileGate`
admits an explicitly configured CPU process envelope only when its pinned policy,
pinned measurement, native host/platform/architecture, validity window, command
fingerprint and exact socket allocation match. Default admission remains closed.
No directory is scanned, file approved, service installed or queue changed.

Windows architecture comes from the OS
[IsWow64Process2 native-machine result](https://learn.microsoft.com/en-us/windows/win32/api/wow64apiset/nf-wow64apiset-iswow64process2),
including emulated processes. A missing API, failed call or unknown machine stays
closed. There is no WMI or environment-variable fallback for this approval field.
Other platforms use their nonempty reported architecture. Two blank observations
never constitute a matching host architecture.

## Approval and evidence

The trusted host configuration selects `ProfileSource(profile_path,
profile_sha256, evidence_path)`. The full policy bytes must match its configured
SHA-256; the policy pins the full evidence bytes. Both paths must be existing,
unlinked host-local files outside OneDrive/UNC. Files are re-read on each check;
duplicate JSON keys, nonfinite/bool numbers, extra fields, changed bytes and
oversized documents are rejected. An embedded `reviewed=true` is not an approval.
The configuration is a privileged operator decision, not input from a work request
or model. The gate does not verify arbitrary Python code in its own process.

Policy fields use schema `ocean-reviewed-workload-profile.v1` and exact fields:
`kind=cpu-owned-process`, `profile_id`, `socket_id`, `host_id`, `platform`,
`architecture`, `workload_sha256`, positive integer `ram_bytes`, `cpu_units`,
`ram_margin_bytes`, `evidence_sha256`, `approved_by`, `approved_at`, `expires_at`.
The last two times are UTC epoch seconds, separate from monotonic grant timers.

Evidence schema `ocean-workload-measurement.v1` requires `scope=cpu-process-tree`,
`method=sampled-rss-and-cumulative-cpu-v1`, matching workload/host/platform/
architecture, `peak_rss_bytes`, `peak_cpu_units`, reviewed integer
`cpu_concurrency_units`, `sample_count`, `sample_interval_seconds`, UTC
`started_at`/`finished_at`, and independently verified checkpoint and exit.
`unmeasured_external_residency` must be false. Do not fabricate these attestations.
An operator must review the actual workload and measurement scope.

RAM allocation must cover observed RSS plus the explicit positive RAM margin.
CPU allocation must cover the reviewed command's maximum concurrency and observed
CPU values. **Sampled or averaged utilization does not establish a burst limit.**
The observation window must fit its sample count/interval, finish before approval,
remain within an explicitly configured maximum age, and precede profile expiry.

Discrete RSS samples can miss short-lived children, transient peaks, reparented
processes and GPU or external daemon allocations. RSS can also double-count shared
pages. A profile is a reviewed demand envelope, not an OS-enforced limit or a
mathematical worst-case bound. This adapter therefore refuses model/GPU/daemon
scopes; those need independently proved residency, input/context bounds and unload
adapters. A process-file size or a model-file size is not a RAM profile.

## Command and lifecycle binding

`ProcessCommand.fingerprint()` binds the immutable argv, cwd, declared source pins
and explicit environment. Review must include all material input/dependency pins
and workload concurrency bounds. The generated `OCEAN_RESOURCE_RUN_DIR` is a
separate protocol variable; callers cannot override it. A `ResourceSocket` uses
the matching `workload_sha256` and exact reviewed RAM/CPU allocation.

```python
from ocean_resources import ProfileSource, ReviewedProfileGate

source = ProfileSource(local_policy, operator_configured_policy_sha256, local_evidence)
gate = ReviewedProfileGate((source,), max_age_seconds=86400)
# Supply profile_gate=gate to the existing HostLocalArbiter, without fixture names.
```

The arbiter checks before acquisition. The facade checks adapter kind/fingerprint;
`OwnedProcessExecutor` checks again before application activation, after source
verification. Its optional `measure_usage(grant, execution_identity)` reads only
its existing owned live process tree, with bounded membership and process counters.
It does not adopt, stop or grant a process. psutil uses the existing optional
`resources` dependency. New inference/heartbeat checks fail when a profile expires
or changes. Checkpoint, stop, exit readback and verified release stay available.
The existing restart journal remains fail-closed; profile approval never clears it.

The first reviewed executor path explicitly requires
`ProcessCommand(..., source_mode="frozen-python")`: the current trusted Python
interpreter plus exactly one pinned application script (at most 8192 bytes),
with explicit application arguments. Its verified bytes are copied into an
isolated `-I -S -c` program before creating the child; the application path is
never reopened for execution. POSIX executes those bytes in the already fenced
isolated bootstrap; Windows passes them to the suspended interpreter. Actual
source pins are checked again before activation, followed by a new capacity
sample. A mutation even after that final check cannot replace the frozen code.
The fingerprint also binds `source_mode`. Legacy path-based commands are allowed
only under explicit fixture admission until a separate artifact adapter is proved.
This is not a general multi-file snapshot: isolated imports, runtime file reads,
all material inputs and concurrency require operator review. The installed Python
runtime, standard library and OS are trusted host infrastructure; same-privilege
malicious host modification is outside this consistency contract. `-I/-S` are
not a sandbox. No production pipeline family is certified by the reference test.
Evidence sample counts must be between 2 and 10,000,000, with finite interval
arithmetic; invalid numeric input returns HOLD instead of a traceback.

## Read-only CLI

```sh
python -m ocean_resources profiles --profile /absolute/local/profile.json \
  --profile-sha256 CONFIGURED_SHA256 --evidence /absolute/local/evidence.json \
  --profile-max-age-seconds 86400
```

Use one line on Windows. `VALIDATED` means the explicitly supplied policy and
evidence passed validation at that moment; `start_authorized` remains false.
Invalid input returns HOLD/exit 2. This command cannot approve or persist an
allowlist. The example age is an explicit configuration example, not a universal
policy. Native capacity/system reserves, claims, budgets, host writer ownership,
application checkpoints and publication rules must still pass separately.
