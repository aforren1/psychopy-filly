"""Browser tests: compiled PsychoJS experiments with a 3D Model component.

They need Node.js, `npm install` in tests/web, an installed browser, and network access on the
first run, which downloads the PsychoJS library from lib.pavlovia.org into tests/web/.cache.
Browsers: FILLY_TEST_BROWSERS, a comma-separated list of chrome, edge, and firefox (default:
chrome). Executables: FILLY_TEST_<BROWSER> overrides the default install path.

Run them with:  pytest -m browser
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pytest

import builder_helpers
from conftest import TESTS

pytestmark = pytest.mark.browser

WEB = TESTS / "web"
BACKGROUND = 128  # the window color, rgb (0, 0, 0)
EXECUTABLES = {
    "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "firefox": r"C:\Program Files\Mozilla Firefox\firefox.exe",
}
BROWSERS = os.environ.get("FILLY_TEST_BROWSERS", "chrome").split(",")


def _executable(browser):
    path = os.environ.get(f"FILLY_TEST_{browser.upper()}", EXECUTABLES.get(browser, ""))
    if not Path(path).is_file():
        pytest.skip(f"{browser} not found at {path!r}; set FILLY_TEST_{browser.upper()}")
    return path


@pytest.fixture(scope="session")
def node():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    if not (WEB / "node_modules" / "puppeteer-core").is_dir():
        pytest.skip("run `npm install` in tests/web first")
    return node


@pytest.fixture(scope="session")
def psychojs_lib():
    """The PsychoJS library of the installed PsychoPy version, as the Builder export loads it."""
    import psychopy
    version = psychopy.__version__
    cache = WEB / ".cache" / f"psychojs-{version}"
    for ext in ("js", "css"):
        file = cache / f"psychojs-{version}.{ext}"
        if not file.is_file():
            cache.mkdir(parents=True, exist_ok=True)
            try:
                urllib.request.urlretrieve(f"https://lib.pavlovia.org/psychojs-{version}.{ext}", file)
            except OSError as error:
                pytest.skip(f"could not download PsychoJS {version}: {error}")
    return cache


def _experiment(folder, lib, duration=3.0, **params):
    builder_helpers.write_cube(folder / "cube.glb")
    builder_helpers.compile_js(builder_helpers.build_experiment(duration=duration, **params), folder,
                               duration=duration)
    shutil.copytree(lib, folder / "lib", dirs_exist_ok=True)
    return folder


def _run(node, folder, browser, **config):
    config = {"folder": str(folder), "browser": browser, "executable": _executable(browser),
              "out": str(folder / browser), **config}
    config_file = folder / f"run-{browser}.json"
    config_file.write_text(json.dumps(config))
    result = subprocess.run([node, str(WEB / "run_experiment.mjs"), str(config_file)],
                            capture_output=True, text=True, timeout=180, cwd=WEB)
    assert result.returncode == 0, result.stderr[-3000:]
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["pageErrors"] == [], report["pageErrors"]
    assert report["consoleErrors"] == [], report["consoleErrors"]
    return report


def _screenshot(path):
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGB")).astype(int)


def _model_fraction(pixels):
    return float((np.abs(pixels - BACKGROUND).sum(axis=2) > 12).mean())


@pytest.mark.parametrize("browser", BROWSERS)
def test_rotating_model(tmp_path, node, psychojs_lib, browser):
    folder = _experiment(tmp_path, psychojs_lib, duration=4.0)
    # The compile copied the vendored web files unchanged.
    web = Path(__file__).parents[1] / "psychopy_filly" / "web"
    for name in ("filly.js", "filly-core.js", "filly-core.wasm", "filly-psychojs.js"):
        assert (folder / "filly" / name).read_bytes() == (web / name).read_bytes()
    report = _run(node, folder, browser, screenshots=[1.5, 2.5])
    first, second = (_screenshot(path) for path in report["screenshots"])
    assert 0.02 < _model_fraction(first) < 0.5
    assert 0.02 < _model_fraction(second) < 0.5
    assert np.abs(first - second).sum(axis=2).astype(bool).mean() > 0.01


PARITY = dict(
    size="(320, 240)", units="pix", resolution="(320, 240)", rotation="(20, 35, 10)",
    modelPos="(0.1, -0.05, 0)", camPos="(0.5, 1.0, 3.0)", fov=35, near=0.5, far=10,
    backgroundColor="$[-0.6, -0.4, 0.2]", lightDir="(-1, -2, -1)", lightIntensity=80000,
    envIntensity=15000, antialiasing="none")


def _desktop_reference(cube_path):
    """The parity scene rendered offscreen by desktop filly: RGBA rows from the top."""
    filly = pytest.importorskip("filly")
    display = np.array([0.2, 0.3, 0.6])  # PsychoPy rgb (-0.6, -0.4, 0.2)
    linear = np.where(display <= 0.04045, display / 12.92, ((display + 0.055) / 1.055) ** 2.4)
    with filly.Renderer() as renderer:
        scene = renderer.create_scene()
        scene.transparent = True
        model = scene.load(str(cube_path))
        model.rotation_euler_deg = (20, 35, 10)
        center = np.asarray(model.bounds).mean(axis=0)
        model.position = tuple(np.array([0.1, -0.05, 0]) - np.asarray(model.transform)[:3, :3] @ center)
        camera = renderer.create_camera()
        camera.set_perspective(fov_y_deg=35, near=0.5, far=10)
        camera.position = (0.5, 1.0, 3.0)
        camera.look_at((0, 0, 0))
        scene.camera = camera
        scene.add_directional_light(direction=(-1, -2, -1), intensity=80000)
        scene.environment = renderer.create_environment(np.ones((8, 16, 3), np.float32))
        scene.environment_intensity = 15000
        scene.background = (*linear, 1.0)
        target = renderer.create_render_target(width=320, height=240)
        renderer.render(scene, target)
        pixels = target.read().astype(int)
        target.close()
    return pixels


@pytest.mark.display
@pytest.mark.parametrize("browser", BROWSERS)
def test_matches_desktop_render(tmp_path, node, psychojs_lib, browser):
    """The browser renders the scene of the desktop runtime, with the same material path.

    Rasterization differs between drivers at color edges; everywhere else the output is within
    one 8-bit level of desktop filly.
    """
    folder = _experiment(tmp_path, psychojs_lib, duration=10.0, **PARITY)
    report = _run(node, folder, browser, screenshots=[1.0], read=True)
    read = report["read"]
    web = np.array(read["pixels"]).reshape(read["height"], read["width"], 4)
    desktop = _desktop_reference(folder / "cube.glb")
    # Flat neighborhoods: every pixel in the 3 x 3 neighborhood within 4 levels.
    padded = np.pad(desktop, ((1, 1), (1, 1), (0, 0)), mode="edge")
    stack = np.stack([padded[1 + dy:1 + dy + 240, 1 + dx:1 + dx + 320] for dy in (-1, 0, 1) for dx in (-1, 0, 1)])
    flat = (stack.max(axis=0) - stack.min(axis=0)).max(axis=2) <= 4
    difference = np.abs(desktop - web).max(axis=2)
    assert flat.mean() > 0.9
    assert difference[flat].max() <= 1, np.bincount(difference[flat])
    assert (difference > 1).mean() < 0.03
    # The background is the requested PsychoPy color, and alpha is opaque.
    assert web[2, 2].tolist() == [51, 76, 153, 255]


def test_cross_origin_isolated(tmp_path, node, psychojs_lib):
    """A page with COOP and COEP headers loads the vendored files: they are same-origin."""
    folder = _experiment(tmp_path, psychojs_lib)
    report = _run(node, folder, "chrome", screenshots=[1.5], isolate=True)
    assert report["crossOriginIsolated"] is True
    assert 0.02 < _model_fraction(_screenshot(report["screenshots"][0])) < 0.5


def test_python_http_server(tmp_path, node, psychojs_lib):
    """The experiment runs from `python -m http.server`, as PsychoPy's local browser pilot serves it.

    On Windows, Python takes MIME types from the registry, where `.mjs` can be `text/plain`;
    browsers do not run modules of that type, so the web files must use `.js`.
    """
    folder = _experiment(tmp_path, psychojs_lib)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                              cwd=folder, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 10
        while True:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html").close()
                break
            except OSError:
                assert time.monotonic() < deadline, "http.server did not start"
                time.sleep(0.1)
        report = _run(node, folder, "chrome", screenshots=[1.5], url=f"http://127.0.0.1:{port}/index.html")
    finally:
        server.terminate()
        server.wait()
    assert 0.02 < _model_fraction(_screenshot(report["screenshots"][0])) < 0.5


def test_default_model(tmp_path, node, psychojs_lib):
    """The default model loads from the experiment's filly folder, not as a PsychoJS resource."""
    folder = _experiment(tmp_path, psychojs_lib, model="default.glb")
    report = _run(node, folder, "chrome", screenshots=[1.5])
    assert 0.02 < _model_fraction(_screenshot(report["screenshots"][0])) < 0.5


def test_set_model(tmp_path, node, psychojs_lib):
    """setModel() replaces the model in a running experiment; the new one is drawn."""
    folder = _experiment(tmp_path, psychojs_lib, model="default.glb", duration=10.0)
    report = _run(node, folder, "chrome", screenshots=[0.5], setModel="cube.glb")
    assert report["setModel"] == {"before": ["Suzanne"], "after": ["painted", "red"], "hiddenWhileLoading": True}
    pixels = _screenshot(report["screenshots"][0])
    assert 0.02 < _model_fraction(pixels) < 0.5
    # The cube's material is not Suzanne's blue.
    model = pixels[np.abs(pixels - BACKGROUND).sum(axis=2) > 12]
    assert model[:, 2].mean() < model[:, 0].mean() + 40


def test_two_models_in_one_scene(tmp_path, node, psychojs_lib):
    """Two 3D Model components in one 3D Scene: the white cube and the blue sample model."""
    from psychopy_filly.components.model3d import Model3DComponent
    exp = builder_helpers.build_experiment(modelPos="(-0.8, 0, 0)", rotation="(20, 30, 0)",
                                           size=(1.2, 0.6), duration=10.0)
    second = Model3DComponent(exp, "trial", name="suzanne", startVal=0.0, stopVal=10.0)
    second.params["modelPos"].val = "(0.8, 0, 0)"
    exp.routines["trial"].addComponent(second)
    builder_helpers.write_cube(tmp_path / "cube.glb")
    builder_helpers.compile_js(exp, tmp_path, duration=10.0)
    shutil.copytree(psychojs_lib, tmp_path / "lib", dirs_exist_ok=True)
    report = _run(node, tmp_path, "chrome", screenshots=[0.5])
    pixels = _screenshot(report["screenshots"][0])
    model = pixels[np.abs(pixels - BACKGROUND).sum(axis=2) > 12]
    # Blue pixels of Suzanne and gray-white pixels of the cube are both in the image.
    blue = (model[:, 2] > model[:, 0] + 60).sum()
    white = (np.abs(model[:, 0] - model[:, 2]) < 20).sum()
    assert blue > 500 and white > 500, (blue, white)


def test_render_scale(tmp_path, node, psychojs_lib):
    """Render scale 0.5 renders a quarter of the pixels and stretches them to the same size."""
    folder = _experiment(tmp_path, psychojs_lib, renderScale=0.5, size=(0.6, 0.6))
    report = _run(node, folder, "chrome", screenshots=[0.5], read=True)
    # 0.6 of the 700-pixel window height is 420 pixels; half of that is rendered.
    assert (report["read"]["width"], report["read"]["height"]) == (210, 210)
    assert 0.02 < _model_fraction(_screenshot(report["screenshots"][0])) < 0.5


def test_escape_closes(tmp_path, node, psychojs_lib):
    folder = _experiment(tmp_path, psychojs_lib, duration=30.0)
    report = _run(node, folder, "chrome", screenshots=[1.0], escape=True)
    assert report["afterEscape"] == {"stimuli": 0}


def test_gltf_with_external_buffer(tmp_path, node, psychojs_lib):
    """A .gltf model loads with its buffer file, which PsychoJS does not know about."""
    folder = _experiment(tmp_path, psychojs_lib, model="cube.gltf")
    builder_helpers.write_cube_gltf(folder)
    report = _run(node, folder, "chrome", screenshots=[1.5])
    assert 0.02 < _model_fraction(_screenshot(report["screenshots"][0])) < 0.5


def test_load_uploads_before_returning(tmp_path, node):
    """Scene.load() leaves no vertex or index upload for the next render.

    Loading frees its source buffers when it returns. Filament 1.77.1's single-threaded
    flushAndWait() does not run the pending command buffer, and filly flushes first; without
    that, the first render uploads from freed memory, and the model renders garbled at random.
    """
    shutil.copytree(Path(__file__).parents[1] / "psychopy_filly" / "web", tmp_path / "filly")
    shutil.copy(WEB / "uploads.html", tmp_path)
    builder_helpers.write_cube(tmp_path / "cube.glb")
    report = _run(node, tmp_path, "chrome", page="uploads.html")
    assert report["page"] == {"uploads": []}


def test_opacity_ramp_keeps_one_sprite(tmp_path, node, psychojs_lib):
    """Opacity changes move no new PIXI objects: a new sprite texture would leave a listener on
    the base texture at every change (PIXI 6)."""
    folder = _experiment(tmp_path, psychojs_lib, duration=10.0)
    report = _run(node, folder, "chrome", screenshots=[0.2], evaluate="""
        const base = scene._baseTexture;
        const sprite = scene._pixi;
        const before = base.listeners("update").length;
        for (let i = 0; i < 120; i++) {
            scene.setOpacity(0.5 + 0.5 * Math.cos(i / 10));
            await new Promise(requestAnimationFrame);
        }
        return { before, after: base.listeners("update").length, sameSprite: scene._pixi === sprite,
                 alpha: scene._pixi.alpha };
    """)
    result = report["evaluate"]
    assert result["after"] == result["before"] and result["sameSprite"], result
    assert result["alpha"] == pytest.approx(0.5 + 0.5 * np.cos(11.9))


def test_hidden_scene_survives_texture_gc(tmp_path, node, psychojs_lib):
    """PIXI's texture garbage collection deletes textures that it has not drawn for a while. A
    scene that is hidden that long and shown again without a change still shows its image."""
    folder = _experiment(tmp_path, psychojs_lib, duration=10.0, rotation="(20, 30, 0)")
    report = _run(node, folder, "chrome", screenshots=[0.5], evaluate="""
        const pixi = scene._host.pixi;
        // Collect textures idle for 5 frames, every 5 frames, instead of after a minute.
        pixi.textureGC.maxIdle = 5;
        pixi.textureGC.checkCountMax = 5;
        const texture = scene._glTexture;
        scene.setAutoDraw(false);
        for (let i = 0; i < 30; i++) await new Promise(requestAnimationFrame);
        scene.setAutoDraw(true);
        for (let i = 0; i < 5; i++) await new Promise(requestAnimationFrame);
        return { same: scene._glTexture === texture, alive: pixi.gl.isTexture(texture) };
    """)
    assert report["evaluate"] == {"same": True, "alive": True}
    assert 0.02 < _model_fraction(_screenshot(report["screenshots"][0])) < 0.5


def test_model_cache_alternation(tmp_path, node, psychojs_lib):
    """A/B/A/B models: each file is fetched and loaded once, and a model of a kept asset renders
    the pixels of a load."""
    folder = _experiment(tmp_path, psychojs_lib, model="default.glb", duration=20.0, rotation="(20, 30, 0)",
                         modelCacheMiB="64")
    report = _run(node, folder, "chrome", evaluate="""
        const frames = async (n) => { for (let i = 0; i < n; i++) await new Promise(requestAnimationFrame); };
        const digest = () => {
            let hash = 2166136261;
            for (const value of scene._target.read()) hash = Math.imul(hash ^ value, 16777619);
            return hash >>> 0;
        };
        await frames(3);
        const shots = [digest()];  // the model that the experiment loaded, without the cache
        for (const name of ["cube.glb", "default.glb", "cube.glb", "default.glb"]) {
            await model.setModel(name);
            await frames(3);
            shots.push(digest());
        }
        const cache = scene._host.modelCache;
        return { shots, loads: cache.loads, entries: cache.entries.size, limit: cache.effectiveLimit(),
                 bytes: cache.size(), models: scene._host.renderer.stats.liveModels };
    """)
    result = report["evaluate"]
    shots = result["shots"]
    assert result["loads"] == 2 and result["entries"] == 2, result
    # The 3D Scene's parameter set the limit; the estimate counts both assets.
    assert result["limit"] == 64 * 2**20 and 0 < result["bytes"] < result["limit"]
    assert shots[0] == shots[2] == shots[4] and shots[1] == shots[3] and shots[0] != shots[1], result
    # The assets belong to the renderer and are not models: only the shown model is live.
    assert result["models"] == 1


def test_model_cache_too_large(tmp_path, node, psychojs_lib):
    """A file above the cache limit shows its one model and is not cached; showing it again loads
    it again."""
    folder = _experiment(tmp_path, psychojs_lib, model="default.glb", duration=20.0, rotation="(20, 30, 0)")
    report = _run(node, folder, "chrome", screenshots=[0.2], evaluate="""
        const cache = scene._host.modelCache;
        cache.limit = 1;  // bytes: every file is too large
        for (const name of ["cube.glb", "default.glb", "cube.glb"]) {
            await model.setModel(name);
        }
        return { loads: cache.loads, entries: cache.entries.size, tooLarge: cache.tooLarge.size,
                 models: scene._host.renderer.stats.liveModels, materials: Object.keys(model._materials) };
    """)
    assert report["evaluate"] == {"loads": 3, "entries": 0, "tooLarge": 2, "models": 1,
                                  "materials": ["painted", "red"]}
    assert 0.02 < _model_fraction(_screenshot(report["screenshots"][0])) < 0.5


def test_scenes_share_environment(tmp_path, node, psychojs_lib):
    """The scenes of a window share one uniform environment, which the host keeps after a scene
    closes."""
    folder = _experiment(tmp_path, psychojs_lib, duration=10.0)
    report = _run(node, folder, "chrome", evaluate="""
        const second = await runtime.SceneStim.create({ win: scene.win, name: "second", size: [0.2, 0.2],
                                                        units: "height" });
        const shared = second._scene.environment.equals(scene._scene.environment);
        second.close();
        return { shared, environments: scene._host.environments.size,
                 open: !(await scene._host.environments.get("uniform")).closed };
    """)
    assert report["evaluate"] == {"shared": True, "environments": 1, "open": True}


@pytest.mark.parametrize("browser", BROWSERS)
@pytest.mark.parametrize("where", ["model", "background"])
def test_mouse_click_on_model(tmp_path, node, psychojs_lib, browser, where):
    """A Mouse component lists the model as a clickable stimulus and ends the routine on a valid
    click. The scene tracks the pointer, so contains() has an answer when the click arrives."""
    builder_helpers.write_cube(tmp_path / "cube.glb")
    experiment = builder_helpers.build_experiment(duration=10.0, fill=0.5)
    builder_helpers.add_mouse(experiment)
    builder_helpers.compile_js(experiment, tmp_path, duration=10.0)
    shutil.copytree(psychojs_lib, tmp_path / "lib", dirs_exist_ok=True)
    # The page is 1000 x 700 pixels and the window units are "height": the scene spans 0.6 * 700
    # pixels about the center, and the rotating cube about half of that.
    point = [500, 350] if where == "model" else [500 + 0.25 * 700, 350 - 0.25 * 700]
    click = _run(node, tmp_path, browser, click=point)["click"]
    if where == "model":
        # The valid click ended the routine, and with it the experiment, which closed the scene.
        assert click["open"] == 0 and click["clickedName"] == "cube"
        assert click["hit"]["modelName"] == "cube" and click["hit"]["node"] == "cube"
        assert click["hit"]["depth"] > 0 and isinstance(click["frame"], int) and click["flipTime"] > 0
    else:
        assert click["open"] == 1 and click["hit"] is None
