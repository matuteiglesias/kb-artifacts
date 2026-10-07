PY ?= python3
.PHONY: test install smoke distribution-test contract-release-verify knowledge-inspect-proof

CONTRACT_RELEASE_MANIFEST ?= interop/vendor/kb-interop.v1-rc1/release.json
CONTRACT_RELEASE_ROOT ?= interop/vendor/kb-interop.v1-rc1
KNOWLEDGE_INSPECT_ROOT ?=
M7_OUTPUT_ROOT ?= artifacts/runs/m7-knowledge-inspect-fixture

test:
	$(PY) -m pytest -q

install:
	$(PY) -m pip install -e . --no-build-isolation

smoke:
	PYTHONPATH=src $(PY) -m kb_artifacts.cli --help

distribution-test:
	$(PY) tools/verify_distribution.py

contract-release-verify:
	$(PY) tools/verify_contract_release.py $(CONTRACT_RELEASE_MANIFEST) --bundle-root $(CONTRACT_RELEASE_ROOT)

knowledge-inspect-proof:
	@test -n "$(KNOWLEDGE_INSPECT_ROOT)" || (echo "KNOWLEDGE_INSPECT_ROOT is required" >&2; exit 2)
	PYTHONPATH=src $(PY) tools/verify_knowledge_inspect_adapter.py \
	  --producer-root "$(KNOWLEDGE_INSPECT_ROOT)" \
	  --output-root "$(M7_OUTPUT_ROOT)"
