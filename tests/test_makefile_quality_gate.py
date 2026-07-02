from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PUBLIC_TARGETS = {
    "bootstrap-controlled-source",
    "preflight",
    "prepare-workspace",
    "materialize-inputs",
    "materialize-procs",
    "submit-mock-lsf",
    "run-simulation",
    "extract-required",
    "extract-ad-hoc",
    "build-reports",
    "inventory-pre",
    "inventory-post",
    "validate",
    "manifest",
    "manifest-smoke",
    "format",
    "lint",
    "typecheck",
    "test",
    "check",
    "clean",
}


def _target_recipe(target_name: str) -> list[str]:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8").splitlines()
    target_header = f"{target_name}:"
    for index, line in enumerate(makefile):
        if line.startswith(target_header):
            recipe: list[str] = []
            for recipe_line in makefile[index + 1 :]:
                if recipe_line and not recipe_line.startswith("\t"):
                    break
                if recipe_line.startswith("\t"):
                    recipe.append(recipe_line.strip())
            return recipe
    raise AssertionError(f"Make target not found: {target_name}")


def test_check_target_runs_quality_gate_commands_in_documented_order() -> None:
    assert _target_recipe("check") == [
        "uv run ruff format --check $(PYTHON_PACKAGE) tests",
        "uv run ruff check $(PYTHON_PACKAGE) tests",
        "uv run basedpyright",
        "uv run pytest",
    ]


def test_public_make_targets_remain_stable() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8").splitlines()
    declared_targets = {
        line.split(":", 1)[0] for line in makefile if line and line[0].isalnum() and ":" in line
    }

    assert PUBLIC_TARGETS.issubset(declared_targets)
