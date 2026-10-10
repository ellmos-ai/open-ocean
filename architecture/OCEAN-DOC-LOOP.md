# OCEAN documentation loop contract

`architecture/ocean-doc-loop.v1.json` fixes the states and mandatory evidence of an empirical
documentation loop. It is a contract and a fixture-checked schema. It starts no workflow, owns no
scheduler, task or worker, and does not claim that any host currently runs the loop.

## The loop

Capture statements and their readers or sources, check the real effect on host, instance, version,
CLI, API and GUI, evidence every difference, correct the descriptive documentation to match reality,
and read it back independently. The four variants are `help`, `root`, `requirements` and `freshness`.

## States

| State | Meaning | Mandatory evidence |
|---|---|---|
| `trigger_planned` | a trigger is due or planned (a plan, not a run) | routine, interval_days, marker_source, next_due_at |
| `task_created` | a bounded analysis task exists and was read back | task_id, title_sha256, worker_binding, readback_verified, created_at |
| `executed` | a real run ended, possibly failed | run_id, host, instance, product_version, exit_state, exit_code, started_at, finished_at, result_id, author_id, author_instance |
| `corrected` | descriptive documentation was changed | files (before/after SHA-256), differences, diff_ref |
| `reviewed` | an independent read-back judged each difference | reviewer_id, reviewer_instance, verdicts, accepted_at |
| `repaired` | a re-measurement shows documentation and reality agree | repair_success_at, remeasure, regression |

## Rules

- A chain holds each state at most once, in order, with non-decreasing `observed_at`. A later state
  never replaces the evidence of an earlier one.
- A state only appears if all earlier states appear. The chain field `unknown` lists exactly the
  states without evidence. Missing evidence is `unknown`, never success.
- A last-run or dispatch marker is only a trigger/dedup marker. A task status such as `done` is not
  evidence either. Execution needs `run_id`, `finished_at` and `result_id`.
- `exit_state` `failed` or `unknown` ends the chain at `executed`. Only `succeeded` with `exit_code`
  0 may be followed by `corrected`.
- `reviewer_id` and `reviewer_instance` must differ from `author_id` and `author_instance`.
- Every corrected file carries two different SHA-256 values. Every difference names statement,
  source, observed value, evidence reference and scope (host, instance, version, surface).
- `repaired` needs `reviewed`, `remeasure.equal` true and `regression` false.

Intervals, worker bindings, archive policy and source/reader roots are configuration of the
consuming system. The contract freezes no model, path, fan-out, time or archive percentage; the
checker rejects such values in the contract text.

## Checker

```
python tools/check_doc_loop_contract.py            # contract + all fixtures
python tools/check_doc_loop_contract.py --chain <chain.json>
```

Positive fixtures must be accepted; each negative fixture (marker without run, `done` without
report, failed run followed by correction, same-instance review, correction without hashes, and
others) must be rejected with the listed problem codes. Exit code 0 means contract and fixtures
conform; the status string says `not-live-evidence`.
