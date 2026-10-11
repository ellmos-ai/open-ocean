---
name: doc-reality-loop
version: 0.1.0
type: workflow
category: docs
status: draft
language: en
description: >
  Empirical documentation loop: capture what documentation claims, measure the real effect on host,
  instance, version, CLI, API and GUI, evidence every difference, correct descriptive text to match
  reality, read it back independently, and record the result in the states of ocean-doc-loop.v1.
contract: architecture/ocean-doc-loop.v1.json
variants: [help, root, requirements, freshness]
---

# Workflow: doc-reality-loop

German version: `SKILL.de.md` (same structure, same headings).

## Claim boundary

This is workflow text. It starts nothing, owns no scheduler, task or worker, and does not claim that
any host currently runs it. Every state and evidence field it mentions is defined by
`architecture/ocean-doc-loop.v1.json` and checked by `tools/check_doc_loop_contract.py`. Intervals,
worker bindings, archive policy and source and reader roots are configuration of the consuming system
(`interval_ref`, `worker_binding`, `archive_policy`, `source_roots`, `reader_roots`); this text names
no model, path, fan-out, time span or archive percentage, and the consuming system must not smuggle one in.

## Principles

1. **Descriptive documentation follows reality.** Text that says what a system does is corrected to
   what it measurably does. Text that says what a system should do is a requirement; it is never
   deleted for being unfulfilled (see step 5).
2. **Evidence rank, highest wins on contradiction:** a measured effect on the real host, instance and
   version; then code, schema and file system; then validated documentation; then older notes and
   summaries. A statement taken from a lower rank is only a hypothesis until a higher rank confirms it.
3. **Unknown is a result.** What cannot be measured is recorded as `unknown`. A last-run marker, a
   dispatch marker or a task status such as `done` is never evidence of execution or of success.
4. **Generated files are regenerated, not edited by hand.** If a statement is wrong because a template,
   export or generator is wrong, the finding goes to the owner of the generator; the generated output
   is regenerated afterwards.
5. **The author does not accept their own work.** The read-back is done by a different identity and a
   different instance, from the files, not from the author's report.

## Variants

One loop, four variants. They differ only in what is captured and what counts as reality.

| Variant | Statements come from | Reality is measured by | Typical readers |
|---|---|---|---|
| `help` | help topics and their language variants (one topic family, not one entry per language) | running the documented commands, reading the handler or API, checking referenced paths and tables | the help handler, links from other topics, tests |
| `root` | repository entry documents, templates and their generated outputs | the same measurements against the entry points, plus regenerating generated files and diffing | package metadata, links, boot files, humans |
| `requirements` | requirement and plan documents | checking each extracted requirement against code, schema, API and CLI | roadmaps, task lists, links |
| `freshness` | change logs and date or version claims | comparing claimed versions, dates and counts with the repository and the running instance | release tooling, links |

## Steps

Each step names the contract state it produces and the exact evidence fields of
`architecture/ocean-doc-loop.v1.json`. Every chain entry also carries its own `observed_at` (UTC),
and every event timestamp is no later than that `observed_at` and ordered along the chain. A step may
only start when the evidence of all earlier states exists. Stop at the first step that fails.

### 0. Trigger (`trigger_planned`)

Record `routine`, `interval_ref` (a reference of the form `config:`, `routine:` or `policy:` plus an
identifier, never a number of days), `marker_source` (`config`, `state_file` or `scheduler_receipt`)
and `next_due_at`, plus the entry's `observed_at`. This is a plan, not a run.

### 1. Task (`task_created`)

Create one bounded analysis task for one scope item (a help topic family, a root document, a
requirement document, a change log). Read the task back from its source and record `task_id`,
`title_sha256`, `worker_binding`, `readback_ref`, `readback_sha256` and `created_at`;
`readback_verified` is true only after that read-back. Add the entry's `observed_at`. The scope item
comes from configuration or from a user request.

### 2. Capture

Read the document completely. List every checkable statement: commands and flags, functions, file and
directory references, table and endpoint names, versions, counts, dates, cross-references. For each
statement note where it was found and who reads it. Readers come from the document register
(`document_id`, `readers[]`); a document without a register entry gets none from guesswork, its
readers are recorded as `unknown`. Mark statements that express a wish or a plan as requirements, not
as claims about the present.

### 3. Measure (`executed`)

For each claim, measure the real effect on the host and instance in question and record `host`,
`instance` and `product_version`. Use the surface that fits: CLI (run the command with a harmless
argument, record exit code and output), API (call the endpoint), GUI (open the page), file system
(does the path exist), schema (does the table or column exist), code (does the handler or option
exist). Keep command and output as the evidence reference. Do not measure destructive operations; mark
them `unknown` with the reason. When the run ends, record `run_id`, `started_at`, `finished_at`,
`result_id`, `exit_state` (`succeeded`, `failed` or `unknown`), `exit_code`, `author_id` and
`author_instance`, plus the entry's `observed_at`.

**Gate:** only `exit_state` `succeeded` together with `exit_code` 0 may lead on to `corrected`. A
`failed` or `unknown` state, or any other exit code, ends the chain at `executed`.

### 4. Differences

For every claim whose measurement differs, write one row with the contract fields `statement`,
`source` (document and location), `observed`, `evidence_ref` and `scope` (`host`, `instance`,
`version`, `surface` as `cli`, `api`, `gui` or `doc`). Classify the row in the report (the contract
does not freeze the classes):

- `better`: reality offers more than the text says. Adjust the text.
- `partial`: partly implemented. Adjust the text to the implemented part and keep the rest as a
  requirement with a task.
- `target-missing`: the documented feature does not exist. If it is wished, keep it as a requirement
  with a task and mark it as not yet implemented; if it was removed on purpose, remove it from the text.
- `wrong`: a path, flag, name, number or reference is simply incorrect. Correct it.
- `unknown`: not measurable here. Leave the text, note the reason.

Where the cause is unclear, look for context first: roadmap, task list, logs, change log, memory
notes. A feature that was planned and forgotten and a feature that was removed on purpose need
different actions.

### 5. Correct (`corrected`)

Change only descriptive text, and only the statements that have a confirmed difference. Record
`files` (each with `path`, `before_sha256` and `after_sha256`, which must differ), the `differences`,
`diff_ref`, `corrected_at`, `archival`, `open_requirements` and the entry's `observed_at`. Rules:

- Safe, small corrections (path, flag, number, version) can be applied directly.
- Larger or structural rewrites, and anything where the intent is unclear, become a task or a question
  to the owner instead of a guess.
- Wished-for requirements that are not yet fulfilled are kept as target state and listed in
  `open_requirements`, each with `statement`, `source` and `task_id`.
- **Archival only through the document register.** An item may be archived only if it has a register
  entry (`document_id`, recorded as the `item`), the `archive_policy` of the consuming system allows it
  (all requirements fulfilled or superseded), and the checks below are recorded. Without a verifiable
  register entry the action is `keep`. Record `action` (`keep` or `archive`) and, for `archive`,
  `archived_at` in UTC. Every entry in `reader_checks` has exactly `ref`, `kind` (`reader` or `link`),
  `active` and `checked_at`: the register's `readers[]` become `reader` checks (`ref`, `active`,
  `last_checked_at` as `checked_at`), and each link to the item is checked as a `link` check. At least
  one check of each kind is required, no check may be active, and every check must be recent enough
  for the register's `archive_policy.reader_audit_not_before`. Any active reader or link means `keep`.
- Generated files: do not edit; record the finding for the generator owner (principle 4).

### 6. Read back (`reviewed`)

A different identity and a different instance read the changed files and the difference table,
re-check each difference themselves, and record `reviewer_id`, `reviewer_instance`, `verdicts` and
`accepted_at` (plus the entry's `observed_at`). Each verdict has exactly `difference_index` (unique,
covering every difference once) and `verdict` (`confirmed` or `rejected`). A rejected difference
returns to step 5; the loop does not proceed on the author's word.

### 7. Re-measure (`repaired`)

Measure again what the corrected text now claims, on the same scope. Record `remeasure` (`equal`,
`measured_at`, `measurement_ref`, `measurement_sha256`, `scope`), `repair_success_at` and
`regression` (plus the entry's `observed_at`). `repaired` needs `reviewed`, `equal` true and
`regression` false. A re-measurement that shows a regression is reported as such and is not success.

## Report

One report per run, written next to the other run results of the consuming system, with these parts:

1. Scope item, variant, host, instance, product version, run id and the contract state reached.
2. Difference table (statement, source, observed, evidence reference, scope, classification).
3. Changed files with before and after hashes, and the diff reference.
4. Open requirements with task ids; kept items with the reader and link checks that kept them.
5. Read-back verdicts and the re-measurement.
6. `unknown` list: every state or statement without evidence, with the reason.

## What this loop never does

- Treat a last-run marker, a dispatch marker or a `done` status as proof.
- Change a requirement document so that an unfulfilled wish disappears.
- Archive without checking readers and links.
- Edit a generated file by hand.
- Fix what it cannot measure; it records `unknown` instead.
- Decide models, intervals, paths, fan-out, time spans or archive thresholds; those are configuration.
