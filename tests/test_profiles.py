from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from kb_artifacts import SelectionRequest, count_corpus, describe_corpus, facet_corpus, load_corpus_profiles, sample_corpus, select
from kb_artifacts.cli import app
from kb_artifacts.profiles import CorpusProfileError, resolve_corpus_sources


def _configured(tmp_path: Path, *, excerpts: bool = False):
    source = tmp_path / "sanitized.jsonl"
    source.write_text(json.dumps({"title": "Runbook", "text": "PRIVATE BODY", "tags": ["playbook"], "text_sha256": "one", "meta": {"domain": "automation", "score": 4, "provenance": {"source_ref": "fixture:one"}}}) + "\n", encoding="utf-8")
    config = tmp_path / "corpora.toml"
    config.write_text(f'''[corpora.chatgpt-history]
description = "Sanitized history"
chunk_globs = ["{source}"]
excerpts_permitted_by_default = {str(excerpts).lower()}
[corpora.chatgpt-history.annotations]
access = "local-approved"
''', encoding="utf-8")
    return source, config, load_corpus_profiles(config)


def test_load_and_list_valid_profiles_without_paths(tmp_path: Path) -> None:
    source, _config, profiles = _configured(tmp_path)
    profile = profiles.get("chatgpt-history")
    assert profile.chunk_globs == (str(source),)
    listing = profiles.list()
    assert listing["corpora"][0]["id"] == "chatgpt-history"
    assert str(tmp_path) not in json.dumps(listing)


def test_unknown_malformed_and_ambiguous_profiles(tmp_path: Path) -> None:
    _source, _config, profiles = _configured(tmp_path)
    with pytest.raises(CorpusProfileError, match="Unknown corpus"):
        profiles.get("missing")
    malformed = tmp_path / "bad.toml"
    malformed.write_text('[corpora.bad]\nchunk_globs = "not-an-array"\n', encoding="utf-8")
    with pytest.raises(CorpusProfileError, match="array"):
        load_corpus_profiles(malformed)
    with pytest.raises(CorpusProfileError, match="cannot be combined"):
        resolve_corpus_sources(chunk_globs=("explicit.jsonl",), summary_globs=(), corpus="chatgpt-history", profiles=profiles)


def test_profile_backed_python_exploration_and_privacy(tmp_path: Path) -> None:
    _source, _config, profiles = _configured(tmp_path)
    common = {"corpus": "chatgpt-history", "profiles": profiles}
    description = describe_corpus(**common)
    assert description["counts"]["records_observed"] == 1
    assert "path" not in description["source_inventory"][0]
    assert facet_corpus(field="domain", **common)["values"] == [{"value": "automation", "count": 1}]
    assert count_corpus(query={"gte": {"field": "score", "value": 4}}, **common)["counts"]["records_matching"] == 1
    sample = sample_corpus(**common)
    assert sample["samples"][0]["provenance"]["source_ref"] == "fixture:one"
    assert "PRIVATE BODY" not in json.dumps(sample)
    with pytest.raises(CorpusProfileError, match="does not permit excerpts"):
        sample_corpus(excerpt_chars=10, **common)


def test_profile_backed_cli_list_explore_and_select_are_json_or_private(tmp_path: Path) -> None:
    _source, config, _profiles = _configured(tmp_path)
    runner = CliRunner()
    listed = runner.invoke(app, ["corpus", "list", "--profiles-file", str(config)])
    assert listed.exit_code == 0, listed.output
    assert json.loads(listed.stdout)["corpora"][0]["id"] == "chatgpt-history"
    assert str(tmp_path) not in listed.stdout
    for command in (["describe"], ["facet", "domain"], ["count"], ["sample"]):
        result = runner.invoke(app, ["corpus", *command, "--corpus", "chatgpt-history", "--profiles-file", str(config)])
        assert result.exit_code == 0, result.output
        assert isinstance(json.loads(result.stdout), dict)
        assert str(tmp_path) not in result.stdout
    output = tmp_path / "selected"
    selected = runner.invoke(app, ["select", "--corpus", "chatgpt-history", "--profiles-file", str(config), "--query", '{"gte":{"field":"score","value":4}}', "--output", str(output)])
    assert selected.exit_code == 0, selected.output
    assert str(tmp_path) not in (output / "manifest.json").read_text()
    assert str(tmp_path) not in (output / "selected.jsonl").read_text()
    assert json.loads((output / "manifest.json").read_text())["selection_request"]["query"] == {"gte": {"field": "score", "value": 4}}
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["output_checksums"]["selected.jsonl"] == hashlib.sha256(
        (output / "selected.jsonl").read_bytes()
    ).hexdigest()


def test_profile_backed_select_python_and_direct_globs_remain_supported(tmp_path: Path) -> None:
    source, _config, profiles = _configured(tmp_path)
    profile_output = tmp_path / "profile-output"
    manifest = select(SelectionRequest(corpus="chatgpt-history"), output=profile_output, profiles=profiles)
    assert manifest["selection_request"]["corpus"] == "chatgpt-history"
    direct_output = tmp_path / "direct-output"
    direct = select(SelectionRequest(chunk_globs=(str(source),)), output=direct_output)
    assert direct["counts"]["selected"] == 1
