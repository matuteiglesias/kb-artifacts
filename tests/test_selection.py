from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from typer.testing import CliRunner

from kb_artifacts.cli import app


def _row(identifier: str, text: str, *, kind: str = "chunk", **meta: object) -> dict:
    return {"text": text, "summary": meta.pop("summary", None), "text_sha256": meta.pop("text_sha256", identifier), "tags": meta.pop("tags", []), "meta": {"message_id": identifier, "conversation_id": "c1", "timestamp": meta.pop("timestamp", "2026-06-01T12:00:00Z"), "provenance": {"source_ref": f"test:{kind}:{identifier}"}, **meta}}


def test_select_filters_both_buses_and_exports_identical_ids(tmp_path: Path) -> None:
    chunks, summaries, output = tmp_path / "chunks.jsonl", tmp_path / "summaries.jsonl", tmp_path / "result"
    chunks.write_text("\n".join(json.dumps(row) for row in [_row("one", "Checklist steps", tags=["Run_book"], note_type="procedure", actionable=True), _row("old", "Checklist", tags=["runbook"], timestamp="2025-01-01T00:00:00Z")]) + "\n", encoding="utf-8")
    summaries.write_text(json.dumps(_row("two", "Summary checklist", kind="summary", tags=["RUN_BOOK"], note_type="procedure", summary="Checklist summary", actionable=True)) + "\n", encoding="utf-8")
    result = CliRunner().invoke(app, ["select", "--chunk-glob", str(chunks), "--summary-glob", str(summaries), "--from", "2026-01-01", "--tag", "run book", "--field", "note_type=procedure", "--text", "checklist", "--output", str(output)])
    assert result.exit_code == 0, result.output
    jsonl_ids = {json.loads(line)["record_id"] for line in (output / "selected.jsonl").read_text().splitlines()}
    csv_ids = {row["record_id"] for row in csv.DictReader((output / "selected.csv").open())}
    markdown = (output / "artifact.md").read_text()
    assert jsonl_ids == csv_ids == {"test:chunk:one", "test:summary:two"}
    assert all(identifier in markdown for identifier in jsonl_ids)
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["counts"] == {"deduplicated": 0, "invalid": 0, "scanned": 3, "selected": 2}
    assert "output_checksums" not in manifest


def test_select_deduplication_and_empty_are_explicit(tmp_path: Path) -> None:
    source, output = tmp_path / "bus.jsonl", tmp_path / "result"
    source.write_text("\n".join(json.dumps(row) for row in [_row("first", "A useful checklist", text_sha256="same", tags=["x"]), _row("second", "A duplicate checklist", text_sha256="same", tags=["x"])]) + "\n", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(app, ["select", "--chunk-glob", str(source), "--tag", "x", "--output", str(output)])
    assert result.exit_code == 0, result.output
    assert json.loads((output / "manifest.json").read_text())["counts"]["deduplicated"] == 1
    empty = runner.invoke(app, ["select", "--chunk-glob", str(source), "--tag", "missing", "--output", str(tmp_path / "empty")])
    assert empty.exit_code == 2 and "No records matched" in empty.output


def test_classification_filter_is_optional_and_canonical_code_has_no_legacy_imports(tmp_path: Path) -> None:
    source = tmp_path / "bus.jsonl"
    source.write_text(json.dumps(_row("ops", "Purpose: recover. 1. Back up. 2. Verify. Before you begin, ensure access. Validate completion.", tags=["runbook"], note_type="procedure")) + "\n", encoding="utf-8")
    result = CliRunner().invoke(app, ["select", "--chunk-glob", str(source), "--family", "operations", "--maturity", "ready", "--output", str(tmp_path / "result")])
    assert result.exit_code == 0, result.output
    legacy_package = "digests" + "_project"
    assert not any(legacy_package in path.read_text(encoding="utf-8") for path in (Path(__file__).parents[1] / "src" / "kb_artifacts").rglob("*.py"))
