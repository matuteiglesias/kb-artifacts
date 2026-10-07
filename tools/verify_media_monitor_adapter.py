#!/usr/bin/env python3
"""Cross-repo proof for Media Monitor generic summary evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

from kb_artifacts.artifact_identity import selected_evidence_artifact_id
from kb_artifacts.profiles import load_corpus_profiles
from kb_artifacts.selection import SelectionRequest, select

CORPUS_ID = "media-monitor-m7"
RUN_ID = "m7-media-monitor-fixture"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_profiles(path: Path, evidence: Path) -> None:
    path.write_text(
        "[corpora.media-monitor-m7]\n"
        'description = "Pinned Media Monitor M7 fixture"\n'
        f'chunk_globs = ["{evidence.as_posix()}"]\n'
        "excerpts_permitted_by_default = false\n"
        "\n"
        "[corpora.media-monitor-m7.annotations]\n"
        'producer = "media-monitor"\n',
        encoding="utf-8",
    )


def _run(command: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"command failed: {command}")
    return result


def _run_adapter(producer_root: Path, store: Path, evidence: Path) -> dict:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(producer_root) if not existing else str(producer_root) + os.pathsep + existing
    _run(
        [sys.executable, "-m", "apps.media_watch.evidence_fixture", "--store-root", str(store)],
        cwd=producer_root,
        env=env,
    )
    result = _run(
        [
            sys.executable, "-m", "apps.media_watch.evidence_export",
            "--store-root", str(store),
            "--output", str(evidence),
        ],
        cwd=producer_root,
        env=env,
    )
    return json.loads(result.stdout)


def verify(producer_root: Path, output_root: Path) -> dict:
    producer_root = producer_root.resolve()
    output_root = output_root.resolve()
    if output_root.exists():
        raise RuntimeError(f"proof output already exists: {output_root}")

    with tempfile.TemporaryDirectory(prefix="kb-artifacts-media-m7-") as temp_dir:
        temp = Path(temp_dir)
        store = temp / "store"
        evidence = temp / "media-monitor.evidence.jsonl"
        profiles_path = temp / "corpora.toml"

        adapter_receipt = _run_adapter(producer_root, store, evidence)
        if adapter_receipt.get("contract") != "producer-local:media-monitor.evidence-jsonl@1":
            raise RuntimeError("unexpected Media Monitor adapter contract")
        if adapter_receipt.get("records") != 2:
            raise RuntimeError("expected exactly two producer fixture records")

        _write_profiles(profiles_path, evidence)
        profiles = load_corpus_profiles(profiles_path)
        manifest = select(
            SelectionRequest(
                corpus=CORPUS_ID,
                start=date(2026, 8, 29),
                end=date(2026, 8, 31),
                text_pattern=r"inflaci[oó]n",
                group_by="source_id",
            ),
            output=output_root,
            profiles=profiles,
        )

        selected_path = output_root / "selected.jsonl"
        manifest_path = output_root / "manifest.json"
        rows = [json.loads(line) for line in selected_path.read_text(encoding="utf-8").splitlines()]
        if len(rows) != 2:
            raise RuntimeError(f"expected two selected records, got {len(rows)}")

        source_ids = {row.get("annotations", {}).get("source_id") for row in rows}
        if source_ids != {"el-destape-youtube", "futurock-youtube"}:
            raise RuntimeError(f"selection did not preserve two-channel identity: {sorted(str(x) for x in source_ids)}")
        if any(not str(row.get("record_id", "")).startswith("media-summary:") for row in rows):
            raise RuntimeError("selected record did not preserve media summary source_ref identity")
        if any(not row.get("summary") for row in rows):
            raise RuntimeError("selected evidence lost governed summary bodies")
        if any(len(row.get("annotations", {}).get("key_points") or []) < 2 for row in rows):
            raise RuntimeError("selected evidence lost governed summary key points")
        if any("inflación" not in (row.get("summary") or "").casefold() for row in rows):
            raise RuntimeError("topic slice contains a non-matching summary")

        partitions = manifest.get("matched_partitions")
        if not isinstance(partitions, list) or len(partitions) != 1:
            raise RuntimeError("selection manifest must contain one logical producer partition")
        partition = partitions[0]
        if "path" in partition or partition.get("source_id") != "chunk:1":
            raise RuntimeError("selection manifest leaked or failed logical partition identity")
        if partition.get("sha256") != adapter_receipt.get("output_sha256") or partition.get("sha256") != _sha256(evidence):
            raise RuntimeError("producer adapter checksum continuity failed")

        serialized = selected_path.read_text(encoding="utf-8") + manifest_path.read_text(encoding="utf-8")
        for forbidden in (str(producer_root), str(temp), str(store)):
            if forbidden in serialized:
                raise RuntimeError("consumer output leaked a producer/work physical path")

        selected_bytes = selected_path.read_bytes()
        receipt = {
            "contract": "m7.media-composition-fixture@1",
            "producer_adapter_contract": adapter_receipt["contract"],
            "producer_adapter_output_sha256": adapter_receipt["output_sha256"],
            "consumer_corpus": CORPUS_ID,
            "selection_window": {"from": "2026-08-29", "to": "2026-08-31"},
            "topic_pattern": r"inflaci[oó]n",
            "selection_counts": manifest["counts"],
            "selected_channels": sorted(source_ids),
            "selected_record_ids": sorted(row["record_id"] for row in rows),
            "selected_evidence_sha256": hashlib.sha256(selected_bytes).hexdigest(),
            "selected_evidence_artifact_id": selected_evidence_artifact_id(selected_bytes),
            "manifest_input_sha256": partition["sha256"],
            "summary_bodies_present": True,
            "key_points_present": True,
            "manifest_uses_logical_source_id": True,
            "physical_path_leakage": False,
            "promotion_performed": False,
        }
        (output_root / "m7-media-proof-receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--producer-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("artifacts/runs") / RUN_ID)
    args = parser.parse_args()
    try:
        receipt = verify(args.producer_root, args.output_root)
    except Exception as exc:
        sys.stderr.write(json.dumps({"error_code": "m7_media_proof_failed", "message": str(exc)}, sort_keys=True) + "\n")
        return 1
    sys.stdout.write(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
