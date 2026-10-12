"""Run-time tests. They open windows and need a display, an OpenGL driver, and filly.

Run them with:  pytest -m display
"""

import json
import math
from pathlib import Path
import os
import subprocess
import sys

import numpy as np
import pytest

import builder_helpers
from conftest import TESTS

pytestmark = pytest.mark.display
pytest.importorskip("filly")

BACKGROUND = 128  # PsychoPy's default window color, (0, 0, 0) in rgb, read back as 128


def _model_fraction(path):
    from PIL import Image
    pixels = np.asarray(Image.open(path).convert("RGB")).astype(int)
    return float((np.abs(pixels - BACKGROUND).sum(axis=2) > 12).mean()), pixels


def _run_compiled(tmp_path, frames, escape_at=None, duration=2.0, blend_mode="nofbo"):
    script = tmp_path / "filly_cube.py"
    experiment = builder_helpers.build_experiment(duration=duration, blend_mode=blend_mode)
    script.write_text(builder_helpers.compile_script(experiment), encoding="utf-8")
    builder_helpers.write_cube(tmp_path / "cube.glb")
    env = dict(os.environ)
    if escape_at:
        env["ESCAPE_AT"] = str(escape_at)
    # A separate process: one window per process avoids pyglet 1.4.11's window-class reuse crash,
    # and the script ends with core.quit(), as in the Runner.
    result = subprocess.run(
        [sys.executable, "-W", "default", str(TESTS / "run_with_capture.py"), str(script),
         str(tmp_path / "capture"), *map(str, frames)],
        capture_output=True, text=True, timeout=120, env=env)
    events = json.loads((tmp_path / "capture" / "events.json").read_text())
    return result, events


def _close_order(events):
    return [(kind, window_open) for kind, _, window_open in events if kind != "escape"]


@pytest.mark.parametrize("blend_mode", ["nofbo", "avg"])
def test_compiled_experiment_shows_rotating_model(tmp_path, blend_mode):
    # "avg" is Builder's default blend mode, which makes a window with useFBO=True.
    result, events = _run_compiled(tmp_path, frames=(20, 60), blend_mode=blend_mode)
    assert result.returncode == 0, result.stderr[-3000:]
    assert "Traceback" not in result.stderr
    assert "was not closed" not in result.stderr
    # Targets, then the renderer, both while the window is open, then the window.
    assert _close_order(events["events"]) == [("target", True), ("renderer", True), ("window", True)]
    first, a = _model_fraction(tmp_path / "capture" / "frame_20.png")
    second, b = _model_fraction(tmp_path / "capture" / "frame_60.png")
    assert 0.03 < first < 0.5 and 0.03 < second < 0.5
    # Rotation changes the image.
    assert np.abs(a - b).sum(axis=2).astype(bool).mean() > 0.01


def test_escape_closes_in_order(tmp_path):
    result, events = _run_compiled(tmp_path, frames=(), escape_at=10, duration=10.0)
    assert result.returncode == 0, result.stderr[-3000:]
    assert events["events"][0][0] == "escape"
    assert events["flips"] < 60
    assert _close_order(events["events"]) == [("target", True), ("renderer", True), ("window", True)]


@pytest.fixture
def window():
    from psychopy import visual
    from psychopy_filly import runtime

    win = visual.Window(size=(320, 240), units="pix", winType="pyglet", useFBO=False,
                        color=(0, 0, 0), checkTiming=False)
    yield win
    runtime.close_all()
    win.close()


def _create(win, model, **arguments):
    """A scene with one shown model. Each argument goes to the scene or the model that takes it."""
    import inspect
    from psychopy_filly import runtime

    model_keys = set(inspect.signature(runtime.SceneModel).parameters) - {"scene", "model", "name"}
    scene = runtime.SceneStim(win, **{k: v for k, v in arguments.items() if k not in model_keys})
    shown = runtime.SceneModel(scene, model, **{k: v for k, v in arguments.items() if k in model_keys})
    shown.setAutoDraw(True)
    return scene, shown


def _front(win):
    return np.asarray(win._getFrame(buffer="front")).astype(int)


def _show(win, scene):
    scene.draw()
    win.flip()
    return _front(win)


def _model_mask(pixels, background=BACKGROUND):
    return np.abs(pixels - background).sum(axis=2) > 12


def test_scene_renders_only_after_change(window, cube_path):
    from psychopy_filly import runtime

    win = window
    scene, cube = _create(win, cube_path, size=(200, 200), rotation=(20, 30, 0))
    stats = lambda: scene._host.renderer.stats.frames_rendered  # noqa: E731
    assert stats() == 1  # the warmup render when the model joined
    for _ in range(5):
        scene.draw()
        win.flip()
    assert stats() == 2  # the first draw shows the model
    cube.setRotation((20, 30, 0))
    scene.setPos((10, 0))  # moves the texture only
    scene.draw()
    assert stats() == 2
    cube.setRotation((20, 60, 0))
    scene.draw()
    assert stats() == 3
    win.flip()
    pixels = _front(win)
    assert (np.abs(pixels[100:140, 150:190] - BACKGROUND).sum(axis=2) > 12).mean() > 0.9

    renderer = scene._host.renderer
    runtime.close_all()
    assert scene.closed and cube.closed and scene._target.closed and renderer.closed
    assert not win._closed
    runtime.close_all()  # repeated calls are valid
    with pytest.raises(RuntimeError, match="closed"):
        scene.draw()


# A new value for each setter, valid for the test cube.
SCENE_CHANGES = {
    "setFov": 40, "setViewHeight": 3.0, "setCamPos": (0, 1, 4), "setLookAt": (0, 0.2, 0),
    "setNear": 0.5, "setFar": 50, "setFill": 0.5, "setExposure": 14,
    "setLightDir": (1, -1, -1), "setLightIntensity": 50000, "setLightColor": "red",
    "setEnvIntensity": 10000, "setEnvRotation": 45, "setBackgroundColor": "blue",
}
MODEL_CHANGES = {
    "setRotation": (0, 45, 0), "setModelPos": (0.1, 0, 0), "setModelScale": 0.8,
    "setVariant": "red", "setMaterial": "painted", "setBaseColor": "green",
    "setAnimation": "spin", "setAnimTime": 0.7, "setAutoDraw": False,
    "setModel": None,  # a copy of the test cube, made by the test
}


def test_each_setter_renders_once(window, cube_path, tmp_path):
    from psychopy_filly import runtime

    (tmp_path / "copy.glb").write_bytes(Path(cube_path).read_bytes())
    scene, cube = _create(window, cube_path, size=(160, 120), autoLog=False)
    placement = ("setPos", "setSize", "setOri", "setOpacity", "setAutoDraw", "setAutoLog", "setName")
    assert sorted(n for n in dir(runtime.SceneStim) if n.startswith("set") and n not in placement) \
        == sorted(SCENE_CHANGES)
    assert sorted(n for n in dir(runtime.SceneModel) if n.startswith("set")) == sorted(MODEL_CHANGES)
    renderer = scene._host.renderer
    scene.draw()
    changes = [(scene, name, value) for name, value in SCENE_CHANGES.items()]
    # Dictionary order: setAnimTime renders only once a clip is selected.
    changes += [(cube, name, value) for name, value in dict(MODEL_CHANGES, setModel=str(tmp_path / "copy.glb")).items()]
    for owner, name, value in changes:
        # setModel() also renders once to warm up the new model.
        expected = renderer.stats.frames_rendered + (2 if name == "setModel" else 1)
        getattr(owner, name)(value)
        scene.draw()
        assert renderer.stats.frames_rendered == expected, name
        getattr(owner, name)(value)
        scene.draw()
        assert renderer.stats.frames_rendered == expected, f"{name} repeated"
    window.flip()


def test_matches_direct_filly_render(window, cube_path):
    """The stimulus shows the pixels of the same scene set up with the filly API directly."""
    win = window
    width, height = (int(v) for v in win.size)
    scene, _ = _create(
        win, cube_path, size=(width, height), rotation=(20, 35, 10), modelPos=(0.1, -0.05, 0),
        camPos=(0.5, 1.0, 3.0), lookAt=(0, 0, 0), fov=35, near=0.5, far=10,
        backgroundColor=(-0.6, -0.4, 0.2), lightDir=(-1, -2, -1), lightIntensity=80000,
        envIntensity=15000, antialiasing="none")
    shown = _show(win, scene)

    renderer = scene._host.renderer
    direct_scene = renderer.create_scene()
    try:
        direct_scene.transparent = True
        model = direct_scene.load(str(cube_path))
        model.rotation_euler_deg = (20, 35, 10)
        center = np.asarray(model.bounds).mean(axis=0)
        model.position = tuple(np.array([0.1, -0.05, 0])
                               - np.asarray(model.transform)[:3, :3] @ center)
        camera = renderer.create_camera()
        camera.set_perspective(fov_y_deg=35, near=0.5, far=10)
        camera.position = (0.5, 1.0, 3.0)
        camera.look_at((0, 0, 0))
        direct_scene.camera = camera
        direct_scene.add_directional_light(direction=(-1, -2, -1), intensity=80000)
        direct_scene.environment = renderer.create_environment(np.ones((8, 16, 3), np.float32))
        direct_scene.environment_intensity = 15000
        # PsychoPy rgb (-0.6, -0.4, 0.2) is the display value (0.2, 0.3, 0.6); filly takes linear.
        display = np.array([0.2, 0.3, 0.6])
        linear = np.where(display <= 0.04045, display / 12.92, ((display + 0.055) / 1.055) ** 2.4)
        direct_scene.background = (*linear, 1.0)
        target = renderer.create_render_target(width=width, height=height)
        renderer.render(direct_scene, target)
        direct = target.read()[:, :, :3].astype(int)  # rows from the top, as the window
        target.close()
    finally:
        direct_scene.close()
    difference = np.abs(shown - direct)
    assert difference.max() <= 1, (difference.max(), (difference > 1).mean())
    # The background shows the requested PsychoPy color.
    assert np.abs(shown[2, 2] - np.round(display * 255)).max() <= 1
    assert _model_mask(shown, shown[2, 2]).mean() > 0.05  # the cube is there


def test_background_in_window_color_is_invisible(window, cube_path):
    scene, _ = _create(window, cube_path, size=(200, 200), backgroundColor=(0, 0, 0), modelScale=0.3)
    pixels = _show(window, scene)
    # Corners of the rendered square show the background, which equals the window color.
    assert np.abs(pixels[25:35, 65:75] - BACKGROUND).max() <= 1
    assert np.abs(pixels[205:215, 245:255] - BACKGROUND).max() <= 1


def test_rotation_matches_filly_euler(window, cube_path):
    from psychopy_filly import runtime

    _, cube = _create(window, cube_path, size=(64, 64))
    for angles in [(10, 0, 0), (0, 20, 0), (0, 0, 30), (15, -40, 70)]:
        cube.model.rotation_euler_deg = angles
        assert np.allclose(runtime._euler_matrix(angles),
                           np.asarray(cube.model.transform)[:3, :3], atol=1e-6)


def test_file_camera_animation_and_variant(window, cube_path):
    win = window
    scene, cube = _create(win, cube_path, size=(240, 240), fileCamera="front",
                          animation="spin", animTime=0, environment="none")
    start = _show(win, scene)
    # The file camera at z=4 with a 30-degree view shows the unit cube at about a third.
    fraction = _model_mask(start)[0:240, 40:280].mean()
    assert 0.05 < fraction < 0.4
    cube.setAnimTime(0.5)
    quarter = _show(win, scene)
    assert np.abs(quarter - start).max() > 30
    cube.setAnimTime(2.0)  # loops back to the start pose
    assert np.abs(_show(win, scene) - start).max() <= 1
    cube.setAnimation(None)  # the authored pose, which is the clip's first key
    assert np.abs(_show(win, scene) - start).max() <= 1

    cube.setVariant("red")
    red = _show(win, scene)
    inside = _model_mask(start)
    assert red[inside][:, 0].mean() > red[inside][:, 1].mean() + 40
    cube.setBaseColor((1, -1, 1))  # magenta replaces the variant's red
    magenta = _show(win, scene)
    assert magenta[inside][:, 2].mean() > red[inside][:, 2].mean() + 30


def test_orthographic_view_height(window, cube_path):
    win = window
    scene, _ = _create(win, cube_path, size=(240, 240), projection="orthographic", viewHeight=2.0)
    pixels = _show(win, scene)
    # A unit cube seen face-on in a 2-unit view spans half the render size: 120 pixels.
    rows = np.flatnonzero(_model_mask(pixels).any(axis=1))
    assert abs((rows[-1] - rows[0] + 1) - 120) <= 2
    scene.setViewHeight(4.0)
    rows = np.flatnonzero(_model_mask(_show(win, scene)).any(axis=1))
    assert abs((rows[-1] - rows[0] + 1) - 60) <= 2


def test_invalid_values_raise(window, cube_path):
    import filly
    from psychopy_filly import runtime

    scene, cube = _create(window, cube_path, size=(64, 64))
    with pytest.raises(ValueError, match="rotation"):
        cube.setRotation((1, 2))
    with pytest.raises(ValueError, match="fill"):
        scene.setFill(0)
    with pytest.raises(ValueError, match="material"):
        cube.setMaterial("nonexistent")
    with pytest.raises(ValueError, match="modelScale"):
        cube.setModelScale(0)
    with pytest.raises(ValueError, match="environment"):
        runtime.SceneStim(window, size=(64, 64), environment="file")
    # Names reach filly, whose errors list the names that the model has.
    with pytest.raises(filly.AssetError, match="^Unknown camera node 'back'; the model has: 'front'$"):
        runtime.SceneModel(scene, cube_path, fileCamera="back")
    cube.setAnimation("run")
    with pytest.raises(filly.AssetError, match="^Unknown animation 'run'; the model has: 'spin'$"):
        scene.draw()
    cube.setAnimation(None)
    cube.setVariant("blue")
    with pytest.raises(filly.AssetError, match="^Unknown variant 'blue'; the model has: 'red'$"):
        scene.draw()


def test_default_model(window, cube_path, tmp_path, monkeypatch):
    from psychopy_filly import runtime

    monkeypatch.chdir(tmp_path)
    scene, suzanne = _create(window, runtime.DEFAULT_MODEL, size=(200, 200))
    assert suzanne.model.material_names == ["Suzanne"]
    pixels = _show(window, scene)
    mask = _model_mask(pixels)
    # The framing fits the box's bounding sphere, which Suzanne fills only in part: about 8%.
    assert 0.04 < mask.mean() < 0.2
    red, green, blue = pixels[mask].mean(axis=0)
    assert blue > green > red
    suzanne.close()
    # A file of the same name in the working directory takes precedence.
    (tmp_path / runtime.DEFAULT_MODEL).write_bytes(Path(cube_path).read_bytes())
    cube = runtime.SceneModel(scene, runtime.DEFAULT_MODEL)
    assert "Suzanne" not in cube.model.material_names


def test_set_model(window, cube_path):
    import filly

    scene, shown = _create(window, cube_path, size=(200, 200), animation="spin", animTime=0.5,
                           material="painted", baseColor="green")
    cube = _show(window, scene)
    renders = scene._host.renderer.stats.frames_rendered
    # Builder sets the model first, then the trial's other parameters. setModel() renders once
    # to warm up the new model, without the old settings, which the new model may not have.
    shown.setModel(filly.samples.SUZANNE)
    shown.setAnimation(None)
    shown.setMaterial(None)
    shown.setBaseColor(None)
    assert scene._host.renderer.stats.frames_rendered == renders + 1
    assert shown.model.material_names == ["Suzanne"]
    pixels = _show(window, scene)
    mask = _model_mask(pixels)
    red, green, blue = pixels[mask].mean(axis=0)
    assert blue > green > red
    assert (mask != _model_mask(cube)).mean() > 0.01
    # The same file again does nothing.
    model = shown.model
    shown.setModel(filly.samples.SUZANNE)
    assert shown.model is model
    # A failed load keeps the current model.
    with pytest.raises(filly.AssetError):
        shown.setModel("missing.glb")
    assert shown.model is model and not model.closed
    # Settings that the new model lacks fail at the draw, with the names that it has.
    shown.setModel(cube_path)
    shown.setAnimation("spin")
    np.testing.assert_array_equal(_show(window, scene)[mask], _show(window, scene)[mask])
    shown.setModel(filly.samples.SUZANNE)
    with pytest.raises(filly.AssetError, match="Unknown animation 'spin'; the model has no named animations"):
        scene.draw()


def test_transparent_only_when_needed(window, cube_path):
    """Transparent output costs an extra pass, so only images that can have alpha below one use it."""
    # FXAA finds edges from a different luma in transparent output, so it is off here.
    scene, _ = _create(window, cube_path, size=(200, 200), modelScale=0.3, antialiasing="none")
    see_through = _show(window, scene)
    assert scene._scene.transparent  # no background: the window shows around the model
    scene.setBackgroundColor((0, 0, 0))
    opaque = _show(window, scene)
    assert not scene._scene.transparent
    # The window color as an opaque background looks the same.
    assert np.abs(opaque - see_through).max() <= 1
    scene.setBackgroundColor(None)
    _show(window, scene)
    assert scene._scene.transparent
    from psychopy_filly import runtime
    sky = runtime.SceneStim(window, size=(64, 64), envVisible=True)
    runtime.SceneModel(sky, cube_path).setAutoDraw(True)
    sky.draw()
    assert not sky._scene.transparent  # the visible environment covers the background


def test_base_color_follows_settings(window, tmp_path):
    """The base color applies to the selected materials only, also across clips that animate it."""
    path = builder_helpers.write_cube(tmp_path / "pulse.glb", pulse=True)
    scene, cube = _create(window, path, size=(64, 64), material="painted", baseColor=(1, -1, -1))

    def color(name):
        return tuple(round(v, 3) for v in cube.model.material(name).base_color)

    assert cube._animated_colors == {"painted"}
    scene.draw()
    assert color("painted") == (1, 0, 0, 1)
    # The clip restores the animated base color; the setting's color applies again, with the
    # clip's alpha.
    cube.setAnimation("pulse")
    cube.setAnimTime(1.0)
    scene.draw()
    assert color("painted") == (1, 0, 0, 0.5)
    cube.setBaseColor(None)
    scene.draw()
    assert color("painted") == (0.5, 0.5, 0.5, 0.5)
    # Another material: the first one shows the clip again, the new one the setting.
    cube.setBaseColor((-1, 1, -1))
    cube.setMaterial("red")
    scene.draw()
    assert color("painted") == (0.5, 0.5, 0.5, 0.5) and color("red") == (0, 1, 0, 1)
    # A clip that does not animate it keeps the setting.
    cube.setAnimation("spin")
    for time in (0.3, 0.6):
        cube.setAnimTime(time)
        scene.draw()
        assert color("red") == (0, 1, 0, 1)
    assert color("painted") == (1, 1, 1, 1)  # the pulse clip no longer applies
    # Without a base color, a material that no clip animates shows its loaded color again.
    cube.setBaseColor(None)
    scene.draw()
    assert color("red") == (1, 0, 0, 1)


def test_pose_changes_update_clip_planes(window, cube_path):
    scene, cube = _create(window, cube_path, size=(200, 200))
    _show(window, scene)
    planes = scene._planes
    position = scene._camera_position
    # Turning a model about its center keeps its bounding sphere and the planes.
    cube.setRotation((0, 60, 0))
    _show(window, scene)
    assert scene._planes == planes and scene._camera_position == position
    # Moving it away moves the far plane, not the camera, and the model stays in view.
    cube.setModelPos((0, 0, -3))
    pixels = _show(window, scene)
    assert scene._planes[1] > planes[1] + 2.9 and scene._camera_position == position
    assert _model_mask(pixels).mean() > 0.01


def test_unchanged_setter_input_skips_conversion(window, cube_path, monkeypatch):
    from psychopy_filly import runtime

    scene, cube = _create(window, cube_path, size=(64, 64))
    cube.setBaseColor("red")
    cube.setRotation([0, 10, 0])
    calls = []
    monkeypatch.setattr(runtime, "_linear_color", lambda *a: calls.append(a) or (0, 1, 0, 1))
    monkeypatch.setattr(runtime, "_vector", lambda v, *a: calls.append(v) or tuple(v))
    cube.setBaseColor("red")
    rotation = [0, 10, 0]
    cube.setRotation(rotation)
    assert calls == []
    # A list changed in place is a new input.
    rotation[1] = 20
    cube.setRotation(rotation)
    cube.setBaseColor("blue")
    assert calls == [[0, 20, 0], ("blue", "rgb", "baseColor")]
    assert cube.rotation == (0, 20, 0)


def test_model_starts_without_file(window, cube_path):
    """Builder's "set every repeat" model: nothing loads before the first repeat sets the file."""
    from psychopy_filly import runtime

    scene = runtime.SceneStim(window, size=(200, 200))
    renderer = scene._host.renderer
    shown = runtime.SceneModel(scene, None, material="painted", baseColor=(1, -1, -1), animation="spin")
    assert shown.model is None and scene.models == [] and renderer.stats.frames_rendered == 0
    shown.setAutoDraw(True)
    _show(window, scene)  # an empty scene
    shown.setModel(cube_path)
    assert scene.models == [shown]
    pixels = _show(window, scene)
    mask = _model_mask(pixels)
    assert mask.mean() > 0.05
    red, green, blue = pixels[mask].mean(axis=0)
    assert red > green + 40 and red > blue + 40
    shown.close()
    assert scene.models == []


def test_model_cache_alternation(window, cube_path, monkeypatch):
    """A/B/A/B models across routines: each file loads once, and a model of a kept asset shows the
    pixels of a load."""
    import filly
    from psychopy_filly import runtime

    def scene_with_model():
        scene = runtime.SceneStim(window, size=(200, 200), camPos=(0, 0, 6), antialiasing="none")
        shown = runtime.SceneModel(scene, None, rotation=(20, 30, 0))
        shown.setAutoDraw(True)
        return scene, shown

    # References from plain loads, with the cache off.
    monkeypatch.setattr(runtime, "MODEL_CACHE_MAX_BYTES", 0)
    scene, shown = scene_with_model()
    cache = scene._host.model_cache
    references = {}
    for path in (cube_path, filly.samples.SUZANNE):
        shown.setModel(path)
        references[path] = _show(window, scene)
    assert cache.loads == 2 and not cache._entries
    scene.close()

    monkeypatch.undo()
    scene, shown = scene_with_model()
    assert scene._host.model_cache is cache  # one cache per window
    for path in (cube_path, filly.samples.SUZANNE) * 2:
        shown.setModel(path)
        np.testing.assert_array_equal(_show(window, scene), references[path])
    assert cache.loads == 4 and len(cache._entries) == 2
    # The assets belong to the renderer and are not models: only the shown model is live.
    renderer = scene._host.renderer
    assert renderer.stats.live_models == 1
    assets = list(cache._entries.values())
    runtime.close_all()
    # The renderer's close releases the assets.
    assert renderer.closed and all(asset.closed for asset in assets)


def test_model_cache_outlives_scenes(window, cube_path):
    """The window's scenes share the cache, and a closed scene leaves its assets usable."""
    from psychopy_filly import runtime

    first = runtime.SceneStim(window, size=(200, 200))
    runtime.SceneModel(first, None).setModel(cube_path)
    cache = first._host.model_cache
    first.close()
    second = runtime.SceneStim(window, size=(200, 200), camPos=(0, 0, 6))
    shown = runtime.SceneModel(second, None, rotation=(20, 30, 0))
    shown.setModel(cube_path)
    shown.setAutoDraw(True)
    assert cache.loads == 1
    assert _model_mask(_show(window, second)).mean() > 0.05
    # Every scene adds the same asset, whatever its rendering settings.
    other = runtime.SceneStim(window, size=(64, 64), antialiasing="none", msaa=4)
    runtime.SceneModel(other, None).setModel(cube_path)
    assert cache.loads == 1 and len(cache._entries) == 1


def test_scenes_share_environments(window, tmp_path):
    """A window's scenes share one filtered Environment per file, and the uniform one."""
    from PIL import Image
    from psychopy_filly import runtime

    first = runtime.SceneStim(window, size=(64, 64), envIntensity=10000)
    second = runtime.SceneStim(window, size=(64, 64), envRotation=90)
    none = runtime.SceneStim(window, size=(64, 64), environment="none")
    assert first._scene.environment == second._scene.environment
    assert none._scene.environment is None
    # Intensity and rotation stay per scene.
    first.draw()
    second.draw()
    assert (first._scene.environment_intensity, second._scene.environment_intensity) == (10000, 20000)
    assert second._scene.environment_rotation_deg == 90
    panorama = tmp_path / "sky.png"
    Image.fromarray(np.full((8, 16, 3), 128, np.uint8)).save(panorama)
    files = [runtime.SceneStim(window, size=(64, 64), environment="file", envFile=str(panorama))
             for _ in range(2)]
    assert files[0]._scene.environment == files[1]._scene.environment != first._scene.environment
    first.close()
    assert not second._scene.environment.closed


def test_model_cache_limits_and_models(window, cube_path, tmp_path, monkeypatch):
    import filly
    from psychopy_filly import runtime

    scene = runtime.SceneStim(window, size=(200, 200), camPos=(0, 0, 6), environment="none")
    cache = scene._host.model_cache
    # Models of one asset keep their own settings.
    left = runtime.SceneModel(scene, None, modelPos=(-1, 0, 0), baseColor=(1, -1, -1))
    right = runtime.SceneModel(scene, None, modelPos=(1, 0, 0), baseColor=(-1, -1, 1))
    for model in (left, right):
        model.setModel(cube_path)
        model.setAutoDraw(True)
    assert cache.loads == 1
    _show(window, scene)
    assert tuple(left.model.material("painted").base_color) == (1, 0, 0, 1)
    assert tuple(right.model.material("painted").base_color) == (0, 0, 1, 1)
    # The limit counts filly's estimate of the assets' memory; the least recently used go.
    cube_bytes = cache.size()
    assert cube_bytes > 0
    suzanne = filly.samples.SUZANNE
    left.setModel(suzanne)
    both = cache.size()
    monkeypatch.setattr(runtime, "MODEL_CACHE_MAX_BYTES", both - 1)
    copy = tmp_path / "copy.glb"
    copy.write_bytes(Path(cube_path).read_bytes())
    right.setModel(copy)  # a third entry: the least recently used, the cube, goes
    keys = [key[0] for key in cache._entries]
    assert cache.loads == 3 and str(Path(cube_path).resolve()) not in keys and keys[-1] == str(copy.resolve())
    assert cache.size() <= both - 1
    # An asset above the limit shows its model, releases its source data, and is not cached. This
    # limit is above
    # the file size, so the first load measures the asset.
    monkeypatch.setattr(runtime, "MODEL_CACHE_MAX_BYTES", Path(cube_path).stat().st_size + 1)
    assert cube_bytes > 2 * runtime.MODEL_CACHE_MAX_BYTES
    left.setModel(cube_path)
    assert left.model.memory.cpu_bytes < runtime.MODEL_CACHE_MAX_BYTES / 4
    assert str(Path(cube_path).resolve()) not in [key[0] for key in cache._entries]
    loads = cache.loads
    left.setModel(suzanne)
    left.setModel(cube_path)  # known to be too large: one plain load
    assert cache.loads == loads + 2
    # None removes the limit; 0 turns the cache off.
    monkeypatch.setattr(runtime, "MODEL_CACHE_MAX_BYTES", None)
    right.setModel(cube_path)
    assert cache._limit() == math.inf and len(cache._entries) >= 2
    monkeypatch.setattr(runtime, "MODEL_CACHE_MAX_BYTES", 0)
    loads = cache.loads
    right.setModel(suzanne)
    right.setModel(copy)
    assert cache.loads == loads + 2


def test_model_cache_scene_parameter(window, cube_path, monkeypatch):
    """The 3D Scene's "Model cache (MiB)" parameter: blank keeps the module setting, the first scene
    that sets it decides for the window."""
    from psychopy_filly import runtime

    assert runtime._cache_limit(None) is None and runtime._cache_limit("") is None
    assert runtime._cache_limit("unlimited") == math.inf
    assert runtime._cache_limit(0) == 0 and runtime._cache_limit("1.5") == 1.5 * 2**20
    with pytest.raises(ValueError, match="modelCacheMiB"):
        runtime._cache_limit(-1)
    plain = runtime.SceneStim(window, size=(64, 64))
    cache = plain._host.model_cache
    assert cache.limit is None and cache._limit() == runtime.MODEL_CACHE_MAX_BYTES == 2**30
    runtime.SceneStim(window, size=(64, 64), modelCacheMiB=0)
    assert cache._limit() == 0
    warnings = []
    monkeypatch.setattr(runtime.logging, "warning", warnings.append)
    runtime.SceneStim(window, size=(64, 64), modelCacheMiB="unlimited")
    assert cache._limit() == 0 and "ignored" in warnings[0]


# --- several models in one scene ----------------------------------------------------------------

def test_models_occlude_each_other(window, cube_path):
    from psychopy_filly import runtime

    scene = runtime.SceneStim(window, size=(240, 240), camPos=(0, 0, 4), environment="none",
                              lightDir=(0, 0, -1), antialiasing="none")
    back = runtime.SceneModel(scene, cube_path, modelPos=(0.3, 0, -1), baseColor="red")
    front = runtime.SceneModel(scene, cube_path, modelPos=(-0.3, 0, 0), baseColor="lime")
    for model in (back, front):
        model.setAutoDraw(True)
    pixels = _show(window, scene)
    # At the center both cubes cover the view; the front, green one hides the red one.
    red, green, blue = pixels[120, 160]
    assert green > red + 40
    # Right of the front cube, the back cube shows.
    red, green, blue = pixels[120, 225]
    assert red > green + 40
    # A hidden model does not draw.
    front.setAutoDraw(False)
    red, green, blue = _show(window, scene)[120, 160]
    assert red > green + 40


def test_framing_covers_all_models(window, cube_path):
    from psychopy_filly import runtime

    scene = runtime.SceneStim(window, size=(240, 240))
    left = runtime.SceneModel(scene, cube_path)
    one = scene._frame_box
    right = runtime.SceneModel(scene, cube_path, modelPos=(3, 0, 0))
    # The framing box grows to the second model as placed when it loaded.
    assert scene._frame_box[0] == one[0] and scene._frame_box[1][0] == pytest.approx(one[1][0] + 3)
    for model in (left, right):
        model.setAutoDraw(True)
    mask = _model_mask(_show(window, scene))
    columns = np.flatnonzero(mask.any(axis=0))
    # Both cubes are in view, with a gap between them.
    assert columns[0] > 40 and columns[-1] < 280 and not mask[:, 150:170].any()
    # Moving a model later does not move the camera.
    right.setModelPos((5, 0, 0))
    assert scene._frame_box[1][0] == pytest.approx(one[1][0] + 3)
    # Closing a model fits the box to the others again.
    right.close()
    assert scene._frame_box == one and scene.models == [left]


def test_one_file_camera_per_scene(window, cube_path):
    from psychopy_filly import runtime

    scene = runtime.SceneStim(window, size=(64, 64))
    first = runtime.SceneModel(scene, cube_path, fileCamera="front")
    with pytest.raises(ValueError, match="already provides the scene's camera"):
        runtime.SceneModel(scene, cube_path, fileCamera="front")
    assert scene.models == [first]
    # Without the file camera, the scene renders through its own camera again.
    first.close()
    assert scene._scene.camera == scene.camera


def test_new_model_stays_hidden_until_it_starts(window, cube_path):
    from psychopy_filly import runtime

    scene, _ = _create(window, cube_path, size=(240, 240), modelPos=(-1, 0, 0), camPos=(0, 0, 6))
    before = _show(window, scene)
    # A model added while the scene draws: its warm-up render shows it once, off screen.
    later = runtime.SceneModel(scene, cube_path, modelPos=(1, 0, 0), baseColor="red")
    assert np.abs(_show(window, scene) - before).max() <= 1
    later.setAutoDraw(True)
    assert (_model_mask(_show(window, scene)) & ~_model_mask(before)).mean() > 0.02


def test_render_scale(window, cube_path):
    from psychopy_filly import runtime

    half = runtime.SceneStim(window, size=(200, 100), renderScale=0.5)
    assert (half._target.width, half._target.height) == (100, 50)
    runtime.SceneModel(half, cube_path).setAutoDraw(True)
    stretched = _model_mask(_show(window, half))
    half.close()
    full = runtime.SceneStim(window, size=(200, 100))
    runtime.SceneModel(full, cube_path).setAutoDraw(True)
    sharp = _model_mask(_show(window, full))
    full.close()
    # The stretched render covers the same area, with a blurred fringe at the edges.
    assert sharp.mean() > 0.02
    assert (sharp & stretched).sum() > 0.97 * sharp.sum()
    assert (stretched & ~sharp).sum() < 0.25 * sharp.sum()
    # The render size, when set, wins.
    sized = runtime.SceneStim(window, size=(200, 100), resolution=(64, 32), renderScale=0.5)
    assert (sized._target.width, sized._target.height) == (64, 32)
    with pytest.raises(ValueError, match="renderScale"):
        runtime.SceneStim(window, size=(200, 100), renderScale=0)
