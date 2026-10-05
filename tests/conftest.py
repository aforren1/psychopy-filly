from pathlib import Path

import pytest

TESTS = Path(__file__).parent
DATA = TESTS / "data"


@pytest.fixture
def cube_path(tmp_path):
    import builder_helpers
    return builder_helpers.write_cube(tmp_path / "cube.glb")
