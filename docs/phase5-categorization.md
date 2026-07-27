# Phase 5 — personalized categorization and correction memory

## Acceptance contract

Categorization is owner-scoped and deterministic. It never changes amounts, posting
status, or financial totals other than their category grouping.

For a transaction without an explicit category, the classifier evaluates these
layers in order and stops at the first match:

1. an enabled user description rule (lowest numeric priority first);
2. the owner's verified merchant-to-category mapping;
3. the owner's latest exact-description correction;
4. non-vector token retrieval over verified corrections; and
5. a caller-supplied model category hint, if it resolves to a visible category.

No match leaves the transaction uncategorized. Token retrieval uses normalized word
sets, Jaccard similarity of at least `0.60`, and a unique best category. Ties remain
uncategorized. The version is `categorization-v1`.

An explicit category supplied during creation is a user selection, not a prediction.
Changing a transaction category:

- locks and owner-scopes the transaction;
- validates that the category is visible to the owner;
- updates the current assignment metadata;
- appends an immutable `UserCorrection` containing the previous and corrected
  categories and the transaction features used for future retrieval; and
- upserts the owner's merchant mapping when the transaction has a merchant.

Corrections never cross owners. Foreign and absent transaction/category IDs have the
same public not-found behavior. Correction history is append-only and newest-first.

Every current assignment exposes source, classifier version, confidence, and whether
it is a user override. Confidence is deterministic policy metadata, not a calibrated
probability.

## Baseline evaluation

The committed synthetic fixture and pure evaluator report accuracy, macro F1, and
per-category errors for the deterministic layers. pgvector remains absent. It may be
introduced only through ADR-006 after a versioned comparison shows a material quality
or cost improvement over this baseline.

## Verification

```text
make migrate
make eval-categorization
make check
```
