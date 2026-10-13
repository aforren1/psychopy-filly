"""The mapping from window points to render-target pixels that picks use, in Python and PsychoJS.

These tests need no display and no filly. The run-time tests of picking are in test_runtime.py.
"""

import json
import shutil
import subprocess

import pytest

from conftest import TESTS

RUNTIME_JS = TESTS.parent / "psychopy_filly" / "web" / "filly-psychojs.js"

# (point, image center, signed image size, ori, target width, target height, expected pixel)
CASES = [
    ((0, 0), (0, 0), (200, 100), 0, 200, 100, (100, 50)),
    ((50, 25), (0, 0), (200, 100), 0, 200, 100, (150, 75)),
    # The image position moves the image; the pixel stays with the image.
    ((60, 30), (10, 5), (200, 100), 0, 200, 100, (150, 75)),
    # A render scale of 2 (or a device pixel ratio of 2) doubles the pixel coordinates.
    ((50, 25), (0, 0), (200, 100), 0, 400, 200, (300, 150)),
    ((50, 25), (0, 0), (200, 100), 0, 100, 50, (75, 37.5)),
    # A negative size flips the image, as for ImageStim.
    ((50, 25), (0, 0), (-200, 100), 0, 200, 100, (50, 75)),
    ((50, 25), (0, 0), (200, -100), 0, 200, 100, (150, 25)),
    # ori turns the image clockwise: the image's right edge points down at 90 degrees.
    ((0, -50), (0, 0), (200, 100), 90, 400, 200, (300, 100)),
    ((0, 49), (0, 0), (200, 100), 180, 200, 100, (100, 1)),
    ((35.355, 35.355), (0, 0), (200, 200), -45, 200, 200, (150, 100)),
    # Outside the image, or on its right or top edge: no pixel.
    ((101, 0), (0, 0), (200, 100), 0, 200, 100, None),
    ((100, 0), (0, 0), (200, 100), 0, 200, 100, None),
    ((0, 50), (0, 0), (200, 100), 0, 200, 100, None),
    ((-100, -50), (0, 0), (200, 100), 0, 200, 100, (0, 0)),
    ((0, 0), (0, 0), (0, 100), 0, 200, 100, None),
]


def _check(actual, expected):
    if expected is None:
        assert actual is None
    else:
        assert actual == pytest.approx(expected, abs=1e-3)


@pytest.mark.parametrize("point, center, size, ori, width, height, expected", CASES)
def test_target_pixel(point, center, size, ori, width, height, expected):
    from psychopy_filly.runtime import _target_pixel
    _check(_target_pixel(point, center, size, ori, width, height), expected)


def test_psychojs_target_pixel_matches():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    cases = [list(case[:6]) for case in CASES]
    script = (f"import {{ targetPixel }} from {json.dumps(RUNTIME_JS.as_uri())};\n"
              f"console.log(JSON.stringify({json.dumps(cases)}.map((c) => targetPixel(...c))));\n")
    result = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True,
                            timeout=60)
    assert result.returncode == 0, result.stderr
    for actual, case in zip(json.loads(result.stdout), CASES):
        _check(actual if actual is None else tuple(actual), case[6])
