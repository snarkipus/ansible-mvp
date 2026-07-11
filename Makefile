# Make is the stable local stage contract invoked by Ansible and by
# developers who need focused debugging of one provenance workflow step.

.DEFAULT_GOAL := help

RUN_ID ?= demo_001
CONTROLLED_SOURCE_REPO ?= ../controlled-source-demo
CONTROLLED_SOURCE_REF ?= controlled-source-demo-v0.1.2
RUN_ROOT_POLICY ?= fresh
PYTHON_PACKAGE := src/provenance
RUN_ROOT := runs/$(RUN_ID)
PROVENANCE_ROOT := $(RUN_ROOT)/provenance

.PHONY: help \
	bootstrap-controlled-source workflow-stage-targets preflight prepare-workspace \
	materialize-inputs materialize-procs submit-mock-lsf wait-mock-lsf collect-mock-lsf run-simulation \
	extract-required extract-ad-hoc build-reports inventory-pre inventory-post \
	validate manifest manifest-smoke format lint typecheck test check clean

help: ## Show documented Make targets.
	@awk 'BEGIN {FS = ":.*## "; printf "Usage: make <target> [RUN_ID=%s]\n\nTargets:\n", "$(RUN_ID)"} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-28s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# Bootstrap: local demo setup outside ordinary production-shaped runs.
bootstrap-controlled-source: ## Bootstrap or verify the sibling controlled source demo repository.
	./scripts/bootstrap_controlled_source.sh "$(CONTROLLED_SOURCE_REPO)"

# Admission: fail fast before the run can start.
workflow-stage-targets: ## List configured workflow Make targets in run order.
	uv run provenance list-run-stage-targets \
		--config configs/run.synthetic.yaml \
		--format lines

preflight: ## Run the Git-controlled source entrance gate before workflow stages.
	uv run provenance preflight \
		--config configs/run.synthetic.yaml \
		--run-id "$(RUN_ID)" \
		--wrapper-repo . \
		--controlled-source-repo "$(CONTROLLED_SOURCE_REPO)" \
		--controlled-source-ref "$(CONTROLLED_SOURCE_REF)" \
		--run-root-policy "$(RUN_ROOT_POLICY)" \
		--output "$(PROVENANCE_ROOT)/preflight.json" \
		--stage-output "$(PROVENANCE_ROOT)/logs/preflight.stage.json"

# Setup: create the run workspace and materialize runtime plumbing.
prepare-workspace: ## Prepare runs/$(RUN_ID)/sim-run-root and provenance sidecar directories.
	uv run provenance prepare-workspace \
		--config configs/run.synthetic.yaml \
		--run-id "$(RUN_ID)" \
		--workspace-root . \
		--stage-output "$(PROVENANCE_ROOT)/logs/prepare_workspace.stage.json"

materialize-inputs: ## Copy controlled fixture inputs into the run workspace.
	uv run provenance materialize-inputs \
		--config configs/run.synthetic.yaml \
		--run-id "$(RUN_ID)" \
		--workspace-root . \
		--controlled-source-repo "$(CONTROLLED_SOURCE_REPO)" \
		--controlled-source-ref "$(CONTROLLED_SOURCE_REF)" \
		--output "$(PROVENANCE_ROOT)/inventories/materialized_inputs.json" \
		--stage-output "$(PROVENANCE_ROOT)/logs/materialize_inputs.stage.json"

materialize-procs: ## Materialize sim-run-root/procs/run-script.sh from controlled source.
	uv run provenance materialize-procs \
		--config configs/run.synthetic.yaml \
		--run-id "$(RUN_ID)" \
		--workspace-root . \
		--controlled-source-repo "$(CONTROLLED_SOURCE_REPO)" \
		--controlled-source-ref "$(CONTROLLED_SOURCE_REF)" \
		--output "$(PROVENANCE_ROOT)/inventories/materialized_runtime_scripts.json" \
		--stage-output "$(PROVENANCE_ROOT)/logs/materialize_procs.stage.json"

# Factory: produce or transform consumed and delivered domain artifacts.
submit-mock-lsf: ## Write mock LSF scheduler metadata without requiring real LSF tools.
	uv run provenance submit-mock-lsf \
		--config configs/run.synthetic.yaml \
		--run-id "$(RUN_ID)" \
		--workspace-root . \
		--controlled-source-repo "$(CONTROLLED_SOURCE_REPO)" \
		--output "$(PROVENANCE_ROOT)/scheduler/submission.yaml" \
		--stage-output "$(PROVENANCE_ROOT)/logs/submit_mock_lsf.stage.json"

wait-mock-lsf: ## Wait for mock LSF terminal state.
	uv run provenance wait-mock-lsf \
		--config configs/run.synthetic.yaml \
		--run-id "$(RUN_ID)" \
		--workspace-root . \
		--output "$(PROVENANCE_ROOT)/scheduler/job-state.json" \
		--stage-output "$(PROVENANCE_ROOT)/logs/wait_mock_lsf.stage.json"

collect-mock-lsf: ## Collect mock LSF accounting evidence.
	uv run provenance collect-mock-lsf \
		--config configs/run.synthetic.yaml \
		--run-id "$(RUN_ID)" \
		--workspace-root . \
		--output "$(PROVENANCE_ROOT)/scheduler/accounting.yaml" \
		--stage-output "$(PROVENANCE_ROOT)/logs/collect_mock_lsf.stage.json"

run-simulation: ## Execute the controlled synthetic simulation stage.
	uv run provenance run-simulation \
		--config configs/run.synthetic.yaml \
		--run-id "$(RUN_ID)" \
		--workspace-root . \
		--controlled-source-repo "$(CONTROLLED_SOURCE_REPO)" \
		--stage-output "$(PROVENANCE_ROOT)/logs/run_simulation.stage.json"

extract-required: ## Produce the required extracted CSV from raw simulation outputs.
	uv run provenance extract-required \
		--config configs/run.synthetic.yaml \
		--run-id "$(RUN_ID)" \
		--workspace-root . \
		--controlled-source-repo "$(CONTROLLED_SOURCE_REPO)" \
		--stage-output "$(PROVENANCE_ROOT)/logs/extract_required.stage.json"

extract-ad-hoc: ## Produce the ad hoc extracted CSV from raw simulation outputs.
	uv run provenance extract-ad-hoc \
		--config configs/run.synthetic.yaml \
		--run-id "$(RUN_ID)" \
		--workspace-root . \
		--controlled-source-repo "$(CONTROLLED_SOURCE_REPO)" \
		--stage-output "$(PROVENANCE_ROOT)/logs/extract_ad_hoc.stage.json"

build-reports: ## Generate summary.xlsx, chart.png, and briefing.pptx derived reports.
	uv run provenance build-reports \
		--run-id "$(RUN_ID)" \
		--workspace-root . \
		--output "$(PROVENANCE_ROOT)/inventories/report_products.json" \
		--stage-output "$(PROVENANCE_ROOT)/logs/build_reports.stage.json"

validate: ## Validate extracted products.
	uv run provenance validate-required \
		--shape-config configs/expected_shape.required_extract.yaml \
		--run-id "$(RUN_ID)" \
		--workspace-root . \
		--stage-output "$(PROVENANCE_ROOT)/logs/validate.stage.json"
	uv run provenance validate-required \
		--shape-config configs/expected_shape.ad_hoc_extract.yaml \
		--run-id "$(RUN_ID)" \
		--workspace-root . \
		--stage-output "$(PROVENANCE_ROOT)/logs/validate.stage.json"

# Finalization: inventory outputs, assemble the manifest, and verify the receipt.
inventory-pre: ## Inventory pre-run controlled inputs and runtime scripts.
	uv run provenance inventory-pre \
		--run-id "$(RUN_ID)" \
		--workspace-root . \
		--inputs-output "$(PROVENANCE_ROOT)/inventories/pre_run_inputs.json" \
		--scripts-output "$(PROVENANCE_ROOT)/inventories/pre_run_controlled_scripts.json" \
		--stage-output "$(PROVENANCE_ROOT)/logs/inventory_pre.stage.json"

inventory-post: ## Inventory post-run raw outputs and derived products.
	uv run provenance inventory-post \
		--config configs/run.synthetic.yaml \
		--run-id "$(RUN_ID)" \
		--workspace-root . \
		--raw-output "$(PROVENANCE_ROOT)/inventories/post_run_raw_outputs.json" \
		--products-output "$(PROVENANCE_ROOT)/inventories/post_run_derived_products.json" \
		--stage-output "$(PROVENANCE_ROOT)/logs/inventory_post.stage.json"

manifest: ## Assemble runs/$(RUN_ID)/provenance/manifest.yaml.
	uv run provenance assemble-run-manifest \
		--config configs/run.synthetic.yaml \
		--run-id "$(RUN_ID)" \
		--workspace-root . \
		--controlled-source-repo "$(CONTROLLED_SOURCE_REPO)" \
		--controlled-source-ref "$(CONTROLLED_SOURCE_REF)" \
		--output "$(PROVENANCE_ROOT)/manifest.yaml" \
		--stage-output "$(PROVENANCE_ROOT)/logs/manifest.stage.json"

manifest-smoke: ## Smoke-validate required manifest sections and key values.
	uv run provenance smoke-manifest \
		"$(PROVENANCE_ROOT)/manifest.yaml" \
		--output "$(PROVENANCE_ROOT)/validations/manifest_smoke.json" \
		--config configs/run.synthetic.yaml \
		--run-id "$(RUN_ID)" \
		--workspace-root . \
		--controlled-source-repo "$(CONTROLLED_SOURCE_REPO)" \
		--controlled-source-ref "$(CONTROLLED_SOURCE_REF)" \
		--stage-output "$(PROVENANCE_ROOT)/logs/manifest_smoke.stage.json"

# Developer quality targets.
format: ## Format Python source and tests with Ruff.
	uv run ruff format $(PYTHON_PACKAGE) tests

lint: ## Check Python source and tests with Ruff.
	uv run ruff check $(PYTHON_PACKAGE) tests

typecheck: ## Type-check provenance helpers with basedpyright.
	uv run basedpyright

test: ## Run pytest.
	uv run pytest

check: ## Run the quality gate: format check, lint, typecheck, then tests.
	uv run ruff format --check $(PYTHON_PACKAGE) tests
	uv run ruff check $(PYTHON_PACKAGE) tests
	uv run basedpyright
	uv run pytest

clean: ## Remove local caches and generated run outputs.
	rm -rf .pytest_cache .ruff_cache .basedpyright_cache runs/*
	touch runs/.gitkeep

.PHONY: _not-implemented
_not-implemented:
	@printf '%s is not implemented yet; see %s.\n' "$(TARGET)" "$(BEAD)" >&2
	@exit 2
