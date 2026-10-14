# Task result review policy contract

This module is a pure, versioned decision contract. It does not read a database,
authenticate a token, write an audit row, or accept a result. BACH remains the
only owner of service credentials, producer provenance, transaction boundaries,
revocation revisions, task/result snapshots, and audit.

## API

The function tools.task_result_review_policy.evaluate_service_review(scope, task,
producer_binding, reviewer_subject, action) returns exactly this DTO:

    {
      "schema": "task-result-service-review-decision.v1",
      "allowed": true,
      "reason_code": "allow"
    }

allowed is a strict boolean. The only reason codes are allow, scope_denied,
self_review, producer_binding_missing, service_revoked, and invalid_request.
Unknown fields, versions, actions, issuer identities, or malformed values fail
closed.

The inputs are server-derived projections:

- scope uses task-result-service-scope.v1 and binds a service ID, positive
  revision, and a list of entries. Each entry has one exact action and exactly
  one target: a positive task ID or a nonempty category.
- task uses bach.task-result-review-target.v1. Its task ID, category, current
  result ID, digest, generation, fence, and content version come from the
  canonical BACH snapshot.
- producer_binding uses bach.task-result-producer-binding.v1; BACH creates
  and stores it in the native submission transaction from the verified lease
  row. The policy never accepts producer metadata from a result body.
- reviewer_subject uses bach.task-result-service-principal.v1 and is derived
  from the separately stored service identity and current revision.

Task-ID and category entries are ORed. Each entry is one narrow grant; neither
a missing target nor a wildcard means global access. Actions are independent:
read does not imply history, accept, or correction, and those actions do not
imply one another. Category comparison trims surrounding whitespace and uses
Unicode case folding.

A result-bearing operation requires an exact producer binding for the result,
including its digest, generation, fence, version, and native lease issuer.
Missing or mismatched provenance is producer_binding_missing. A reviewer is
denied when its trusted principal equals the producer principal or its trusted
generation equals the result generation. A task with no result may be read or
paged when explicitly scoped; it cannot be accepted or corrected.

## Activation boundary

The policy package does not create service identities or credentials. BACH must
authenticate the service on the exact result routes, check scope revision and
revocation under the same transaction as a correction or acceptance, and write
an audit record without credential material. Missing or unverified installed
policy source is unavailable; it must not fall back to a second BACH policy.
