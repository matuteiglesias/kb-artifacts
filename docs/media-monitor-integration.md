# Media Monitor integration

KB Artifacts consumes Media Monitor only through the producer-owned generic interface:

`producer-local:media-monitor.evidence-jsonl@1`

The consumer does not parse `media_summary.v1`, YouTube items, Media Monitor storage, or Gemini responses.

The pinned cross-repository proof:

1. checks out an exact Media Monitor commit;
2. executes Media Monitor's own sanitized two-channel summary fixture;
3. executes Media Monitor's own generic evidence exporter;
4. registers the JSONL as a named corpus;
5. selects an explicit three-day window using an `inflación` topic regex;
6. requires both configured channel identities in selected evidence;
7. preserves summary source refs, summary bodies, key points and checksum continuity;
8. verifies the selected artifact and manifest contain no producer/work physical paths;
9. performs no promotion or publication.

This is a producer/consumer interoperability proof, not a claim that KB Artifacts owns media semantics.
