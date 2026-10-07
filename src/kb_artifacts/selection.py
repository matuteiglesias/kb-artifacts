"""Generic, read-only evidence selection and multi-format export."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

from kb_artifacts.classification import classify
from kb_artifacts.contracts import EvidenceRecord, SelectionDecision
from kb_artifacts.normalization import normalize_value, tag_lexeme
from kb_artifacts.query import QueryExpression, evaluate_query, parse_query
from kb_artifacts.profiles import CorpusProfiles, resolve_corpus_sources
from kb_artifacts.sources.jsonl_bus import SourceInputError, expand_globs, scan_jsonl


@dataclass(frozen=True)
class SelectionRequest:
    chunk_globs: tuple[str, ...] = ()
    summary_globs: tuple[str, ...] = ()
    start: date | None = None
    end: date | None = None
    tags: tuple[str, ...] = ()
    fields: tuple[tuple[str, str], ...] = ()
    text_pattern: str | None = None
    families: tuple[str, ...] = ()
    maturities: tuple[str, ...] = ()
    limit: int | None = None
    deduplicate: bool = True
    group_by: str = "domain"
    query: QueryExpression | Mapping[str, object] | None = None
    corpus: str | None = None


def _fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _key(record: EvidenceRecord) -> str:
    return record.provenance.text_sha256 or record.record_id


def _sort_key(record: EvidenceRecord) -> tuple[datetime, str, str, int]:
    return (record.timestamp or datetime.min.replace(tzinfo=timezone.utc), record.record_id, record.provenance.partition, record.provenance.line_number)


def _field_matches(record: EvidenceRecord, field: str, wanted: str) -> bool:
    value = record.annotations.get(field)
    values = value if isinstance(value, (list, tuple, set)) else (value,)
    return any(normalize_value(item) == normalize_value(wanted) for item in values)


def _matches(record: EvidenceRecord, request: SelectionRequest, pattern: re.Pattern[str] | None) -> tuple[bool, list[str], object | None]:
    reasons: list[str] = []
    if request.start and (not record.timestamp or record.timestamp.date() < request.start): return False, reasons, None
    if request.end and (not record.timestamp or record.timestamp.date() > request.end): return False, reasons, None
    if request.start: reasons.append(f"from:{request.start.isoformat()}")
    if request.end: reasons.append(f"to:{request.end.isoformat()}")
    if request.tags:
        tags = {tag_lexeme(tag) for tag in record.tags}
        requested = {normalize_value(tag) for tag in request.tags}
        if not tags.intersection(requested): return False, reasons, None
        reasons.append("tag:" + sorted(tags.intersection(requested))[0])
    for field, wanted in request.fields:
        if not _field_matches(record, field, wanted): return False, reasons, None
        reasons.append(f"field:{field}={normalize_value(wanted)}")
    result = classify(record) if request.families or request.maturities else None
    if request.families and result.family not in set(request.families): return False, reasons, result
    if request.maturities and result.maturity not in set(request.maturities): return False, reasons, result
    if result and request.families: reasons.append(f"family:{result.family}")
    if result and request.maturities: reasons.append(f"maturity:{result.maturity}")
    if pattern and not pattern.search("\n".join(part for part in (record.title, record.summary, record.text) if part)):
        return False, reasons, result
    if pattern: reasons.append("text_match")
    if request.query is not None and not evaluate_query(record, request.query):
        return False, reasons, result
    if request.query is not None: reasons.append("query_match")
    return True, reasons, result


def _payload(record: EvidenceRecord, decision: SelectionDecision, partition_alias: str | None = None) -> dict[str, object]:
    provenance = asdict(record.provenance)
    if partition_alias is not None: provenance["partition"] = partition_alias
    return {"record_id": record.record_id, "source_kind": record.source_kind, "title": record.title,
            "summary": record.summary, "annotations": dict(record.annotations), "tags": list(record.tags),
            "timestamp": record.timestamp.isoformat() if record.timestamp else None,
            "provenance": provenance, "selection_reasons": list(decision.reasons),
            "artifact_family": decision.artifact_family, "artifact_maturity": decision.artifact_maturity}


def _compute_selection(
    request: SelectionRequest,
    paths: list[tuple[str, Path]],
) -> tuple[list[EvidenceRecord], list[dict[str, object]], int, list[tuple[EvidenceRecord, SelectionDecision]]]:
    if request.query is not None: parse_query(request.query)
    try: pattern = re.compile(request.text_pattern, re.IGNORECASE) if request.text_pattern else None
    except re.error as error: raise SourceInputError(f"Invalid text pattern: {error}") from error
    records: list[EvidenceRecord] = []; errors: list[dict[str, object]] = []
    for kind, path in paths:
        found, diagnostics = scan_jsonl([path], source_kind=kind)
        records.extend(found); errors.extend(diagnostics)
    records.sort(key=_sort_key)
    unique: list[EvidenceRecord] = []; duplicate_count = 0; seen: set[str] = set()
    for record in records:
        if request.deduplicate and _key(record) in seen:
            duplicate_count += 1; continue
        seen.add(_key(record)); unique.append(record)
    selected: list[tuple[EvidenceRecord, SelectionDecision]] = []
    for record in unique:
        matched, reasons, result = _matches(record, request, pattern)
        if matched:
            selected.append((record, SelectionDecision(record.record_id, "selected", 1, tuple(reasons), {}, artifact_family=result.family if result else None, artifact_maturity=result.maturity if result else None, classification_reasons=result.reasons if result else ())))
    if request.limit is not None: selected = selected[:request.limit]
    return records, errors, duplicate_count, selected


def _render_jsonl(payloads: list[dict[str, object]]) -> bytes:
    return b"".join(
        (json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        for item in payloads
    )


def _render_csv(
    selected: list[tuple[EvidenceRecord, SelectionDecision]],
    payloads: list[dict[str, object]],
) -> bytes:
    target = io.StringIO(newline="")
    fieldnames = ("record_id", "source_kind", "timestamp", "title", "summary", "tags", "artifact_family", "artifact_maturity", "selection_reasons", "text_excerpt", "source_ref")
    writer = csv.DictWriter(target, fieldnames=fieldnames)
    writer.writeheader()
    for (record, decision), item in zip(selected, payloads):
        writer.writerow({**{key: item.get(key, "") for key in fieldnames}, "tags": ", ".join(record.tags), "selection_reasons": "; ".join(decision.reasons), "text_excerpt": (record.text or "")[:320], "source_ref": record.provenance.source_ref or record.record_id})
    return target.getvalue().encode("utf-8")


def _render_markdown(
    selected: list[tuple[EvidenceRecord, SelectionDecision]],
    group_by: str,
) -> bytes:
    groups: dict[str, list[tuple[EvidenceRecord, SelectionDecision]]] = {}
    for record, decision in selected:
        value = record.conversation_id if group_by == "conversation" else record.timestamp.date().isoformat() if group_by == "date" and record.timestamp else record.annotations.get(group_by)
        group = str(value or "Unclassified"); groups.setdefault(group, []).append((record, decision))
    lines = ["# Selected evidence", "", "Generated from read-only governed bus records.", ""]
    for group in sorted(groups, key=str.casefold):
        lines += [f"## {group}", ""]
        for record, decision in groups[group]:
            lines += [f"### {record.title or record.summary or (record.text or 'Untitled evidence')[:120]}", "", record.summary or record.text or "", "", f"- Selection: {', '.join(decision.reasons)}", f"- Source: `{record.provenance.source_ref or record.record_id}`", ""]
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def _build_legacy_manifest(
    request: SelectionRequest,
    paths: list[tuple[str, Path]],
    records: list[EvidenceRecord],
    errors: list[dict[str, object]],
    duplicate_count: int,
    selected_count: int,
) -> dict[str, object]:
    selection_request = {"chunk_globs": list(request.chunk_globs), "summary_globs": list(request.summary_globs), "from": request.start.isoformat() if request.start else None, "to": request.end.isoformat() if request.end else None, "tags": list(request.tags), "fields": dict(request.fields), "text_pattern": request.text_pattern, "families": list(request.families), "maturities": list(request.maturities), "limit": request.limit, "deduplicate": request.deduplicate, "group_by": request.group_by}
    if request.corpus is not None:
        selection_request["corpus"] = request.corpus
    if request.query is not None:
        selection_request["query"] = parse_query(request.query).to_dict()
    partitions = [{"source_kind": kind, **({"source_id": f"{kind}:{index}"} if request.corpus else {"path": str(path)}), "sha256": _fingerprint(path)} for index, (kind, path) in enumerate(paths, start=1)]
    return {"selection_request": selection_request, "generated_at": datetime.now(timezone.utc).isoformat(), "matched_partitions": partitions, "counts": {"scanned": len(records) + len(errors), "invalid": len(errors), "deduplicated": duplicate_count, "selected": selected_count}, "outputs": ["selected.jsonl", "selected.csv", "artifact.md", "manifest.json"]}


def _write_candidate_file(path: Path, content: bytes) -> None:
    path.write_bytes(content)


def _write_outputs(output: Path, rendered: dict[str, bytes]) -> None:
    for filename, content in rendered.items():
        _write_candidate_file(output / filename, content)


def _validate_candidate(candidate: Path, rendered: dict[str, bytes]) -> None:
    actual = {path.name for path in candidate.iterdir()}
    if actual != set(rendered):
        raise SourceInputError("Staged output validation failed: unexpected file set")
    for filename, expected in rendered.items():
        path = candidate / filename
        if path.is_symlink() or not path.is_file() or path.read_bytes() != expected:
            raise SourceInputError(f"Staged output validation failed: {filename}")


def _hash_candidate_files(candidate: Path, filenames: Iterable[str]) -> dict[str, str]:
    return {filename: _fingerprint(candidate / filename) for filename in filenames}


def _promote_candidate(candidate: Path, output: Path) -> None:
    os.replace(candidate, output)


def _has_symlink_component(path: Path) -> bool:
    absolute = path.absolute()
    return any(component.is_symlink() for component in (absolute, *absolute.parents))


def _stage_and_promote(output: Path, rendered: dict[str, bytes]) -> dict[str, str]:
    if _has_symlink_component(output):
        raise SourceInputError(f"Output path must not contain a symlink: {output}")
    if output.exists() and not output.is_dir():
        raise SourceInputError(f"Output path is not a directory: {output}")
    if output.exists() and any(output.iterdir()):
        raise SourceInputError(f"Output directory is not empty: {output}")

    output.parent.mkdir(parents=True, exist_ok=True)
    candidate = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent))
    try:
        _write_outputs(candidate, rendered)
        _validate_candidate(candidate, rendered)
        hashes = _hash_candidate_files(candidate, rendered)
        _promote_candidate(candidate, output)
        return hashes
    except SourceInputError:
        raise
    except OSError as error:
        raise SourceInputError(f"Could not publish selection output: {error}") from error
    finally:
        if candidate.exists():
            shutil.rmtree(candidate, ignore_errors=True)


def select(
    request: SelectionRequest,
    *,
    output: str | os.PathLike[str],
    allow_empty: bool = False,
    profiles: CorpusProfiles | None = None,
) -> dict:
    """Select once from both buses and render JSONL, CSV, Markdown, and evidence."""
    output = Path(output)
    if _has_symlink_component(output):
        raise SourceInputError(f"Output path must not contain a symlink: {output}")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise SourceInputError(f"Output directory is not empty: {output}")
    chunk_globs, summary_globs, _profile = resolve_corpus_sources(chunk_globs=request.chunk_globs, summary_globs=request.summary_globs, corpus=request.corpus, profiles=profiles)
    paths = [("chunk", path) for path in expand_globs(chunk_globs)] + [("summary", path) for path in expand_globs(summary_globs)]
    if not paths: raise SourceInputError("No input files matched the requested globs")
    records, errors, duplicate_count, selected = _compute_selection(request, paths)
    if not selected and not allow_empty: raise SourceInputError("No records matched; rerun with --allow-empty only when an empty export is intentional")
    aliases = {str(path): f"corpus:{request.corpus}/{kind}:{index}" for index, (kind, path) in enumerate(paths, start=1)} if request.corpus else {}
    payloads = [_payload(record, decision, aliases.get(record.provenance.partition)) for record, decision in selected]
    manifest = _build_legacy_manifest(request, paths, records, errors, duplicate_count, len(selected))
    body_outputs = {
        "selected.jsonl": _render_jsonl(payloads),
        "selected.csv": _render_csv(selected, payloads),
        "artifact.md": _render_markdown(selected, request.group_by),
    }
    manifest["output_checksums"] = {
        filename: hashlib.sha256(content).hexdigest()
        for filename, content in sorted(body_outputs.items())
    }
    rendered = {
        **body_outputs,
        "manifest.json": (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    }
    _stage_and_promote(output, rendered)
    return manifest
