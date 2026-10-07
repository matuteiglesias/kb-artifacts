# AGENTS.md — KB Artifacts

## Mission

Maintain deterministic selection, manifest, promotion, and publication mechanics for governed knowledge evidence.

This repository owns how eligible inputs become selected evidence artifacts. It may consume declared producer-local JSONL evidence interfaces through its existing generic reader. It does not own source-document meaning, producer-specific conversion, shared interoperability contracts, general analysis, context routing, paper parsing, or MCP access policy.

## Authority boundary

Matías owns selection policy, profile meaning, promotion approval, release acceptance, and any decision about what evidence is suitable for downstream use.

Agents may:

- repair deterministic selection and manifest defects;
- improve fixture-driven tests, provenance, diagnostics, and release verification;
- implement an explicitly approved policy or contract change;
- prepare comparison evidence for a proposed promotion.

Agents must not independently:

- change ranking, eligibility, exclusion, deduplication, scoring, or promotion semantics;
- publish or promote an artifact merely because generation succeeded;
- rewrite selected outputs or manifests by hand;
- copy source semantics or shared schemas into a competing local authority;
- ingest arbitrary new source content;
- add a Knowledge Inspect-specific parser when the declared producer-local JSONL interface can be consumed through the generic reader;
- expose private source material, absolute paths, secrets, or large bodies in fixtures or logs;
- modify producer, routing, contract, or MCP repositories.

## Determinism and provenance

For identical approved inputs, configuration, code, and environment assumptions, selection output should be reproducible.

Every accepted output must identify, as applicable:

- source artifact and stable identity;
- exact input version or checksum;
- selection profile and parameters;
- code or release version;
- run or artifact ID;
- selected and excluded counts;
- output manifest and checksums;
- promotion state and approving authority.

Unknown provenance is a blocked result, not permission to infer or reconstruct silently.

## Generated artifacts

Run records, selected-evidence outputs, manifests, exports, caches, and promoted bundles are generated evidence.

Do not hand-edit them. Fix the selector, contract, approved configuration, or source mapping; rerun; validate; and compare exact outputs.

Do not commit large source corpora or copied evidence bodies for convenience. Use minimal sanitized fixtures.

## Commands

Use the current root Make surface:

```bash
make test
make smoke
make contract-release-verify
make knowledge-inspect-proof KNOWLEDGE_INSPECT_ROOT=/path/to/pinned/knowledge-inspect
```

`make install` changes the local environment and should not be part of an ordinary check unless setup is explicitly required.

Before introducing a generic `make check`, confirm that the composed commands are deterministic, offline, and acceptably bounded.

Publication or promotion commands exposed through `kbctl` are consequential. Do not run them unless the task explicitly identifies the target, expected manifest, destination, and approval state.

## Knowledge Inspect adoption boundary

The accepted producer interface is
`producer-local:knowledge-inspect.evidence-jsonl@1`.

The cross-repository proof must:

- pin an exact Knowledge Inspect commit;
- execute the producer-owned adapter against its producer-owned sanitized fixture;
- consume the result through the ordinary generic JSONL reader;
- select through a named corpus profile so manifests use logical aliases;
- prove input checksum continuity and absence of physical paths;
- perform no promotion or publication.

No Knowledge Inspect native summary parser belongs in this repository.

## Media Monitor adoption boundary

The accepted producer interface is `producer-local:media-monitor.evidence-jsonl@1`.

The cross-repository proof must:

- pin an exact Media Monitor commit;
- execute Media Monitor's producer-owned sanitized evidence fixture and producer-owned adapter;
- consume the result through the ordinary generic JSONL reader;
- select by explicit date window and topic pattern through a named corpus profile;
- preserve media-summary source_ref identity, channel annotations, governed summary bodies and key points;
- prove adapter-output checksum continuity and absence of physical paths;
- perform no promotion, publication, model call, or media-specific parsing inside KB Artifacts.

Knowledge Inspect is not an ingestion dependency for this path.

## Contract changes

When changing a manifest, profile, artifact identity, or shared interface:

1. identify the owning contract;
2. preserve stable references where required;
3. add valid, invalid, and compatibility fixtures;
4. state whether existing outputs require regeneration;
5. verify exact release evidence;
6. identify downstream consumers;
7. keep shared-contract changes in `kb-contracts` rather than duplicating them locally.

## Change discipline

- Prefer one selection or promotion defect per PR.
- Keep selection logic separate from source interpretation.
- Make randomness absent or explicit and seeded.
- Preserve failed-run evidence and do not report partial output as promoted success.
- Avoid broad storage, framework, or orchestration changes during a selector repair.
- Never claim a selection, promotion, publication, contract verification, or source inspection that did not occur.

## Completion report

```text
Changed:
Selection policy changed:
Inputs/fixtures:
Commands run:
Determinism checked:
Manifests/checksums:
Artifacts generated:
Promotion/publication performed:
Contracts affected:
Private/source content accessed:
Blocked:
Next:
```
