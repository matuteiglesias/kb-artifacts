#!/usr/bin/env python3
"""Cross-repo fixture proof for Knowledge Inspect generic evidence export."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from kb_artifacts.artifact_identity import selected_evidence_artifact_id
from kb_artifacts.profiles import load_corpus_profiles
from kb_artifacts.selection import SelectionRequest, select

CORPUS_ID = "knowledge-inspect-m7"
RUN_ID = "m7-knowledge-inspect-fixture"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_profiles(path: Path, evidence: Path) -> None:
    path.write_text(
        "[corpora.knowledge-inspect-m7]\n"
        'description = "Pinned Knowledge Inspect M7 fixture"\n'
        f'chunk_globs = ["{evidence.as_posix()}"]\n'
        "excerpts_permitted_by_default = false\n"
        "\n"
        "[corpora.knowledge-inspect-m7.annotations]\n"
        'producer = "knowledge-inspect"\n',
        encoding="utf-8",
    )


def _run_adapter(producer_root: Path, evidence: Path) -> dict:
    fixture = (
        producer_root
        / "tests"
        / "fixtures"
        / "evidence_export"
        / "summary_bus.json"
    )
    if not fixture.is_file():
        raise RuntimeError(f"missing pinned producer fixture: {fixture}")

    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(producer_root)
        if not existing
        else str(producer_root) + os.pathsep + existing
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "kb.cli.kb_evidence_export",
            str(fixture),
            "--output",
            str(evidence),
        ],
        cwd=producer_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Knowledge Inspect adapter failed: "
            + (result.stderr.strip() or result.stdout.strip())
        )
    return json.loads(result.stdout)


def verify(
    producer_root: Path,
    output_root: Path,
) -> dict:
    producer_root = producer_root.resolve()
    output_root = output_root.resolve()
    if output_root.exists():
        raise RuntimeError(
            f"proof output already exists: {output_root}"
        )

    with tempfile.TemporaryDirectory(
        prefix="kb-artifacts-m7-"
    ) as temp_dir:
        temp = Path(temp_dir)
        evidence = temp / "knowledge-inspect.evidence.jsonl"
        profiles_path = temp / "corpora.toml"

        adapter_receipt = _run_adapter(
            producer_root,
            evidence,
        )
        _write_profiles(profiles_path, evidence)
        profiles = load_corpus_profiles(profiles_path)

        manifest = select(
            SelectionRequest(
                corpus=CORPUS_ID,
                tags=("knowledge-inspect",),
            ),
            output=output_root,
            profiles=profiles,
        )

        selected_path = output_root / "selected.jsonl"
        manifest_path = output_root / "manifest.json"
        selected_lines = selected_path.read_text(
            encoding="utf-8"
        ).splitlines()
        if len(selected_lines) != 1:
            raise RuntimeError(
                f"expected one selected record, got {len(selected_lines)}"
            )

        record = json.loads(selected_lines[0])
        if (
            record.get("record_id")
            != "knowledge-inspect:summary:kb_chat_analyze_20261007T120000Z"
        ):
            raise RuntimeError(
                "selected record did not preserve producer source_ref identity"
            )

        provenance = record.get("provenance")
        if not isinstance(provenance, dict):
            raise RuntimeError("selected record missing provenance")
        if provenance.get("partition") != (
            "corpus:knowledge-inspect-m7/chunk:1"
        ):
            raise RuntimeError(
                "selected record did not use logical corpus partition alias"
            )

        partitions = manifest.get("matched_partitions")
        if (
            not isinstance(partitions, list)
            or len(partitions) != 1
        ):
            raise RuntimeError(
                "selection manifest must describe exactly one partition"
            )
        partition = partitions[0]
        if "path" in partition:
            raise RuntimeError(
                "selection manifest leaked a physical input path"
            )
        if partition.get("source_id") != "chunk:1":
            raise RuntimeError(
                "selection manifest did not use logical source_id"
            )
        if partition.get("sha256") != _sha256(evidence):
            raise RuntimeError(
                "selection manifest input checksum disagrees with adapter output"
            )

        serialized = (
            selected_path.read_text(encoding="utf-8")
            + manifest_path.read_text(encoding="utf-8")
        )
        for forbidden in (
            str(producer_root),
            str(temp),
        ):
            if forbidden in serialized:
                raise RuntimeError(
                    "consumer output leaked a physical producer/work path"
                )

        selected_bytes = selected_path.read_bytes()
        artifact_id = selected_evidence_artifact_id(
            selected_bytes
        )
        receipt = {
            "contract": "m7.knowledge-composition-fixture@1",
            "producer_adapter_contract": adapter_receipt[
                "contract"
            ],
            "producer_adapter_output_sha256": adapter_receipt[
                "output_sha256"
            ],
            "consumer_corpus": CORPUS_ID,
            "selection_counts": manifest["counts"],
            "selected_evidence_sha256": hashlib.sha256(
                selected_bytes
            ).hexdigest(),
            "selected_evidence_artifact_id": artifact_id,
            "manifest_input_sha256": partition["sha256"],
            "manifest_uses_logical_source_id": True,
            "physical_path_leakage": False,
        }
        (output_root / "m7-proof-receipt.json").write_text(
            json.dumps(
                receipt,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--producer-root",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("artifacts/runs") / RUN_ID,
    )
    args = parser.parse_args()

    try:
        receipt = verify(
            args.producer_root,
            args.output_root,
        )
    except Exception as exc:
        sys.stderr.write(
            json.dumps(
                {
                    "error_code": "m7_fixture_proof_failed",
                    "message": str(exc),
                },
                sort_keys=True,
            )
            + "\n"
        )
        return 1

    sys.stdout.write(
        json.dumps(receipt, indent=2, sort_keys=True)
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
