# Make is the stable local stage contract invoked by Ansible and by
# developers who need focused debugging of one provenance workflow step.

.DEFAULT_GOAL := help

RUN_ID ?= demo_001
CONTROLLED_SOURCE_REPO ?= ../controlled-source-demo
CONTROLLED_SOURCE_REF ?= controlled-source-demo-v0.1.0
PYTHON_PACKAGE := src/provenance

.PHONY: help \
	bootstrap-controlled-source preflight prepare-workspace \
	materialize-inputs materialize-procs submit-mock-lsf run-simulation \
	extract-required extract-ad-hoc build-reports inventory-pre inventory-post \
	validate manifest format lint typecheck test check clean

help: ## Show documented Make targets.
	@awk 'BEGIN {FS = ":.*## "; printf "Usage: make <target> [RUN_ID=%s]\n\nTargets:\n", "$(RUN_ID)"} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-28s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

bootstrap-controlled-source: ## Bootstrap or verify the sibling controlled source demo repository.
	@$(MAKE) _not-implemented TARGET=$@ BEAD=ansible-mvp-izo.2.1

preflight: ## Run the Git-controlled source entrance gate before workflow stages.
	@$(MAKE) _not-implemented TARGET=$@ BEAD=ansible-mvp-izo.4.3

prepare-workspace: ## Prepare runs/$(RUN_ID)/sim-run-root and provenance sidecar directories.
	@$(MAKE) _not-implemented TARGET=$@ BEAD=ansible-mvp-izo.4.4

materialize-inputs: ## Copy controlled fixture inputs into the run workspace.
	@$(MAKE) _not-implemented TARGET=$@ BEAD=ansible-mvp-izo.4.5

materialize-procs: ## Materialize sim-run-root/procs/run-script.sh from controlled source.
	@$(MAKE) _not-implemented TARGET=$@ BEAD=ansible-mvp-izo.4.5

submit-mock-lsf: ## Write mock LSF scheduler metadata without requiring real LSF tools.
	@$(MAKE) _not-implemented TARGET=$@ BEAD=ansible-mvp-izo.4.6

run-simulation: ## Execute the controlled synthetic simulation stage.
	@$(MAKE) _not-implemented TARGET=$@ BEAD=ansible-mvp-izo.5.1

extract-required: ## Produce the required extracted CSV from raw simulation outputs.
	@$(MAKE) _not-implemented TARGET=$@ BEAD=ansible-mvp-izo.5.2

extract-ad-hoc: ## Produce the ad hoc extracted CSV from raw simulation outputs.
	@$(MAKE) _not-implemented TARGET=$@ BEAD=ansible-mvp-izo.5.3

build-reports: ## Generate summary.xlsx, chart.png, and briefing.pptx derived reports.
	@$(MAKE) _not-implemented TARGET=$@ BEAD=ansible-mvp-izo.5.4

inventory-pre: ## Inventory pre-run controlled inputs and runtime scripts.
	@$(MAKE) _not-implemented TARGET=$@ BEAD=ansible-mvp-izo.6.1

inventory-post: ## Inventory post-run raw outputs and derived products.
	@$(MAKE) _not-implemented TARGET=$@ BEAD=ansible-mvp-izo.6.2

validate: ## Validate extracted products and run manifest smoke checks.
	@$(MAKE) _not-implemented TARGET=$@ BEAD=ansible-mvp-izo.6.3

manifest: ## Assemble runs/$(RUN_ID)/provenance/manifest.yaml.
	@$(MAKE) _not-implemented TARGET=$@ BEAD=ansible-mvp-izo.6.4

format: ## Format Python source and tests with Ruff.
	uv run ruff format $(PYTHON_PACKAGE) tests

lint: ## Check Python source and tests with Ruff.
	uv run ruff check $(PYTHON_PACKAGE) tests

typecheck: ## Type-check provenance helpers with mypy.
	uv run mypy

test: ## Run pytest when tests exist; pass clearly while tests are scaffold-only.
	@if find tests -type f \( -name 'test_*.py' -o -name '*_test.py' \) | grep -q .; then \
		uv run pytest; \
	else \
		printf 'No pytest test files found yet; skipping pytest for scaffold-only state.\n'; \
	fi

check: ## Run the quality gate: format check, lint, typecheck, then tests.
	uv run ruff format --check $(PYTHON_PACKAGE) tests
	uv run ruff check $(PYTHON_PACKAGE) tests
	uv run mypy
	@$(MAKE) test

clean: ## Remove local caches and generated run outputs.
	rm -rf .pytest_cache .ruff_cache .mypy_cache runs/*
	touch runs/.gitkeep

.PHONY: _not-implemented
_not-implemented:
	@printf '%s is not implemented yet; see %s.\n' "$(TARGET)" "$(BEAD)" >&2
	@exit 2
