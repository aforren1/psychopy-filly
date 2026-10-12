import os
from pathlib import Path
import sys
import tempfile

import pytest

TESTS = Path(__file__).parent
DATA = TESTS / "data"

# PsychoPy puts the app's plugin folder (%APPDATA%\psychopy3\packages\PythonXY\site-packages) on
# sys.path. Copies of filly and psychopy-filly installed there by the app shadow the code under
# test. Set before any test imports PsychoPy; subprocesses inherit it.
if sys.platform == "win32":
    os.environ["APPDATA"] = tempfile.mkdtemp(prefix="psychopy-filly-appdata-")


@pytest.fixture
def cube_path(tmp_path):
    import builder_helpers
    return builder_helpers.write_cube(tmp_path / "cube.glb")
