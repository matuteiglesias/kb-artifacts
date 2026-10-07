# Knowledge Inspect evidence adapter integration

KB Artifacts remains a producer-agnostic JSONL selector. It does not parse
Knowledge Inspect native artifacts.

The accepted producer interface is:

```text
producer-local:knowledge-inspect.evidence-jsonl@1
```

Knowledge Inspect owns the native `summary_bus` -> generic JSONL projection.
KB Artifacts consumes the resulting JSONL through its existing generic reader.

## Cross-repository proof

The M7 proof checks out an exact Knowledge Inspect commit, runs:

```text
kb.cli.kb_evidence_export
```

against the producer-owned sanitized fixture, then selects the emitted record
through a named KB Artifacts corpus profile.

The named profile is required for this composition path because KB Artifacts
then records logical partition identity:

```text
corpus:knowledge-inspect-m7/chunk:1
```

rather than a physical input path.

The proof asserts:

- producer adapter contract identity;
- one generic JSONL evidence record;
- source_ref identity preserved as the selected record ID;
- adapter output SHA-256 equals the consumer manifest input SHA-256;
- one selected record;
- content-addressed selected-evidence identity;
- no producer checkout or temporary work path in selected JSONL or manifest.

## Authority

This adoption does not add a Knowledge Inspect parser to KB Artifacts and does
not transfer producer semantics.

KB Artifacts still owns only deterministic inspection, selection, selected
artifact identity, manifests, and promotion mechanics. Promotion remains a
separate consequential action and is not performed by the M7 fixture proof.
