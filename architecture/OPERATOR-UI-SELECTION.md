# Operator UI selection

session: 01a0f189-21d6-7851-a075-0aab0e3ebe77 | codex-ticket-master@ASUS-GEI | 2026-10-01

## Contract

`tools.operator_ui_selection.select_operator_ui` consumes a recorded installer/composition
choice, immutable candidate contracts, and observations supplied by the existing source
and entrypoint verifiers. It performs no filesystem discovery, network request, database
access, provider import, process start, or mount.

The choice includes a decision reference, an actual UI-enabled boolean, an explicit
Full/partial boolean when UI is enabled, and zero or one selected module IDs.
Headless operation binds none. An enabled UI requires exactly one binding. The role's
global minimum remains zero; this helper does not change the composition catalogue.

Partial installation selects `ellmos-unified-gui`. Its real module manifest must retain
`requires=[]`, so selection does not require BACH or the optional neutral shell.
Full installation requires the independently accepted Full module ID supplied by the
caller. No Full ID is registered or invented here. Missing Full identity, an Activity-only
contract, or missing Full surfaces refuses the choice without switching to Lite.

## Inputs and evidence boundary

`ProviderContract` binds module ID, profile, repository, full immutable commit, exact
manifest SHA-256, entrypoint, and required accepted surfaces. `VerifiedProviderFacts`
contains observations for those fields, including actual manifest bytes. This helper
checks equality, byte hashing and minimal role/source semantics. It does not reproduce
the catalogue generator, Git checkout verifier, package verifier, or entrypoint verifier.

The caller must obtain facts from those existing verified boundaries. Copying expected
strings into an observation is no checkout or runtime evidence. The entrypoint contract
is source-bound; the current Lite module manifest has no entrypoint field. The manifest
pin and source/entry observation remain separate inputs.

Full surfaces have stable helper-local names: activity, agents-board, tasks-board,
skills-board, chat, settings, assets, navigation, authorization, and errors. These are
required source-acceptance observations; they are not new catalogue `provides` IDs or
permission grants. Every surface needs its real capabilities and authorization/error
contract before a production caller may report it.

The return value is immutable metadata for at most one entrypoint. No provider is
constructed. Refusals expose a stable `OperatorUISelectionError.code`: invalid_choice,
conflicting_choice, ambiguous_choice, required_role_unbound, unresolved_full_provider,
unknown_provider, selection_mismatch, ambiguous_binding, invalid_provider_contract,
source_binding_unavailable, source_binding_mismatch, manifest_mismatch,
invalid_manifest, or missing_capability.

## Remaining integration

The current runtime dispatch is unchanged. Full still needs its actual neutral source
surfaces, accepted module identity and entry contract, canonical manifest registration,
generated catalogue and recorded composition binding, followed by the real authenticated
runtime acceptance. This pure helper and synthetic Full fixtures do not prove those gates.
The test ID `fixture-neutral-full-ui` is deliberately synthetic and must never be installed
as a catalogue provider.

## Deutsche Kurzfassung

Die Auswahl benötigt eine ausdrücklich gespeicherte Installationsentscheidung und
geprüfte Quellenbindungen. Ohne angeforderte Oberfläche bleibt die Komposition ohne GUI.
Eine Teilinstallation wählt Lite ohne BACH-Pflicht. Eine Vollinstallation verweigert bei
fehlender echter Full-Identität oder fehlenden Fähigkeiten; ein stiller Wechsel zu Lite
ist ausgeschlossen. Die Funktion startet und importiert keinen Provider. Die tatsächliche
Full-Oberfläche, Katalogintegration und Laufzeitabnahme bleiben offen.
