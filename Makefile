# Make is the stable local stage contract invoked by Ansible and by
# developers who need focused debugging of one provenance workflow step.

.DEFAULT_GOAL := help

RUN_ID ?= demo_001
CONTROLLED_SOURCE_REPO ?= ../controlled-source-demo
CONTROLLED_SOURCE_REF ?= controlled-source-demo-v0.1.0
PYTHON_PACKAGE := src/provenance
RUN_ROOT := runs/$(RUN_ID)
PROVENANCE_ROOT := $(RUN_ROOT)/provenance

.PHONY: help \
	bootstrap-controlled-source preflight prepare-workspace \
	materialize-inputs materialize-procs submit-mock-lsf run-simulation \
	extract-required extract-ad-hoc build-reports inventory-pre inventory-post \
	validate manifest manifest-smoke format lint typecheck test check clean

help: ## Show documented Make targets.
	@awk 'BEGIN {FS = ":.*## "; printf "Usage: make <target> [RUN_ID=%s]\n\nTargets:\n", "$(RUN_ID)"} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-28s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

bootstrap-controlled-source: ## Bootstrap or verify the sibling controlled source demo repository.
	./scripts/bootstrap_controlled_source.sh "$(CONTROLLED_SOURCE_REPO)"

preflight: ## Run the Git-controlled source entrance gate before workflow stages.
	uv run provenance preflight \
		--config configs/run.synthetic.yaml \
		--wrapper-repo . \
		--controlled-source-repo "$(CONTROLLED_SOURCE_REPO)" \
		--controlled-source-ref "$(CONTROLLED_SOURCE_REF)" \
		--output "$(PROVENANCE_ROOT)/preflight.json"

prepare-workspace: ## Prepare runs/$(RUN_ID)/sim-run-root and provenance sidecar directories.
	uv run provenance prepare-workspace \
		--config configs/run.synthetic.yaml \
		--run-id "$(RUN_ID)" \
		--workspace-root .

materialize-inputs: ## Copy controlled fixture inputs into the run workspace.
	uv run provenance materialize-inputs \
		--config configs/run.synthetic.yaml \
		--run-id "$(RUN_ID)" \
		--workspace-root . \
		--controlled-source-repo "$(CONTROLLED_SOURCE_REPO)" \
		--controlled-source-ref "$(CONTROLLED_SOURCE_REF)" \
		--output "$(PROVENANCE_ROOT)/inventories/materialized_inputs.json"

materialize-procs: ## Materialize sim-run-root/procs/run-script.sh from controlled source.
	uv run provenance materialize-procs \
		--config configs/run.synthetic.yaml \
		--run-id "$(RUN_ID)" \
		--workspace-root . \
		--controlled-source-repo "$(CONTROLLED_SOURCE_REPO)" \
		--controlled-source-ref "$(CONTROLLED_SOURCE_REF)" \
		--output "$(PROVENANCE_ROOT)/inventories/materialized_runtime_scripts.json"

submit-mock-lsf: ## Write mock LSF scheduler metadata without requiring real LSF tools.
	uv run provenance submit-mock-lsf \
		--config configs/run.synthetic.yaml \
		--run-id "$(RUN_ID)" \
		--workspace-root . \
		--output "$(PROVENANCE_ROOT)/scheduler/submission.yaml"

run-simulation: ## Execute the controlled synthetic simulation stage.
	uv run provenance run-simulation \
		--config configs/run.synthetic.yaml \
		--run-id "$(RUN_ID)" \
		--workspace-root . \
		--controlled-source-repo "$(CONTROLLED_SOURCE_REPO)" \
		--output "$(PROVENANCE_ROOT)/logs/run_simulation.stage.json"

extract-required: ## Produce the required extracted CSV from raw simulation outputs.
	uv run provenance extract-required \
		--config configs/run.synthetic.yaml \
		--run-id "$(RUN_ID)" \
		--workspace-root . \
		--controlled-source-repo "$(CONTROLLED_SOURCE_REPO)" \
		--output "$(PROVENANCE_ROOT)/logs/extract_required.stage.json"

extract-ad-hoc: ## Produce the ad hoc extracted CSV from raw simulation outputs.
	uv run provenance extract-ad-hoc \
		--config configs/run.synthetic.yaml \
		--run-id "$(RUN_ID)" \
		--workspace-root . \
		--controlled-source-repo "$(CONTROLLED_SOURCE_REPO)" \
		--output "$(PROVENANCE_ROOT)/logs/extract_ad_hoc.stage.json"

build-reports: ## Generate summary.xlsx, chart.png, and briefing.pptx derived reports.
	uv run provenance build-reports \
		--run-id "$(RUN_ID)" \
		--workspace-root . \
		--output "$(PROVENANCE_ROOT)/inventories/report_products.json" \
		--stage-output "$(PROVENANCE_ROOT)/logs/build_reports.stage.json"

inventory-pre: ## Inventory pre-run controlled inputs and runtime scripts.
	uv run provenance inventory-pre \
		--run-id "$(RUN_ID)" \
		--workspace-root . \
		--inputs-output "$(PROVENANCE_ROOT)/inventories/pre_run_inputs.json" \
		--scripts-output "$(PROVENANCE_ROOT)/inventories/pre_run_controlled_scripts.json"

inventory-post: ## Inventory post-run raw outputs and derived products.
	uv run provenance inventory-post \
		--run-id "$(RUN_ID)" \
		--workspace-root . \
		--raw-output "$(PROVENANCE_ROOT)/inventories/post_run_raw_outputs.json" \
		--products-output "$(PROVENANCE_ROOT)/inventories/post_run_derived_products.json"

validate: ## Validate extracted products.
	uv run provenance validate-required \
		--shape-config configs/expected_shape.required_extract.yaml \
		--run-id "$(RUN_ID)" \
		--workspace-root .

manifest: ## Assemble runs/$(RUN_ID)/provenance/manifest.yaml.
	uv run provenance assemble-run-manifest \
		--config configs/run.synthetic.yaml \
		--run-id "$(RUN_ID)" \
		--workspace-root . \
		--controlled-source-repo "$(CONTROLLED_SOURCE_REPO)" \
		--controlled-source-ref "$(CONTROLLED_SOURCE_REF)" \
		--output "$(PROVENANCE_ROOT)/manifest.yaml"

manifest-smoke: ## Smoke-validate required manifest sections and key values.
	uv run provenance smoke-manifest \
		"$(PROVENANCE_ROOT)/manifest.yaml" \
		--output "$(PROVENANCE_ROOT)/validations/manifest_smoke.json"

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
