from pathlib import Path

import pytest

from provenance.paths import resolve_layout_path, resolve_root_relative_path, validate_run_id


@pytest.mark.parametrize("run_id", ["A", "demo_001", "a.b-c_1", "9"])
def test_validate_run_id_accepts_safe_identifiers(run_id: str) -> None:
    assert validate_run_id(run_id) == run_id


@pytest.mark.parametrize(
    "run_id",
    ["", ".hidden", "-leading", "../escape", "a/b", "a\\b", "two words", ".."],
)
def test_validate_run_id_rejects_unsafe_identifiers(run_id: str) -> None:
    with pytest.raises(ValueError, match="run_id must match"):
        validate_run_id(run_id)


def test_resolve_root_relative_path_rejects_absolute_and_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="relative path"):
        resolve_root_relative_path(tmp_path, tmp_path / "outside", field_name="test.path")
    with pytest.raises(ValueError, match="without '..'"):
        resolve_root_relative_path(tmp_path, "../outside", field_name="test.path")


def test_resolve_root_relative_path_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="outside its designated root"):
        resolve_root_relative_path(root, "link/file.txt", field_name="test.path")


def test_resolve_layout_path_formats_safe_run_id(tmp_path: Path) -> None:
    resolved = resolve_layout_path(
        tmp_path,
        {"run_root": "runs/{run_id}"},
        "run_root",
        "demo_001",
    )

    assert resolved == tmp_path / "runs" / "demo_001"


def test_resolve_layout_path_rejects_escaping_template(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="without '..'"):
        resolve_layout_path(
            tmp_path,
            {"run_root": "../runs/{run_id}"},
            "run_root",
            "demo_001",
        )
