import pytest
from pathlib import Path


@pytest.fixture
def project_root():
    """Return the project root directory."""
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def backend_dir(project_root):
    """Return the backend directory."""
    return project_root / "backend"


@pytest.fixture
def tmp_workdir(tmp_path):
    """Provide a temporary working directory with a few dummy files."""
    for name in ["alpha.txt", "bravo.txt", "charlie.txt"]:
        (tmp_path / name).write_text(f"contents of {name}\n")
    return tmp_path
