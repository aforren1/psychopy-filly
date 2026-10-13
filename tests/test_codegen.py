"""Code generation and Builder integration. These tests need no display and no filly."""

import ast
import hashlib
import inspect
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import builder_helpers
from conftest import DATA, TESTS

# The expected script comes from this PsychoPy version; other versions change the template.
FIXTURE_PSYCHOPY = "2026.2.4"
FIXTURE = DATA / "filly_cube.py"
RUNTIME_JS = TESTS.parent / "psychopy_filly" / "web" / "filly-psychojs.js"

# A value other than the default for each parameter of the scene and the model, as Builder would
# store it. build_experiment() gives each to the component that has it.
NON_DEFAULTS = {
    "rotation": "(10, 20, 30)", "modelPos": "(0.1, 0, 0)", "modelScale": "(1, 2, 1)",
    "center": False, "resolution": "(256, 128)", "renderScale": 0.5, "projection": "orthographic", "fov": 45,
    "viewHeight": 2.5, "camPos": "(0, 1, 4)", "lookAt": "(0, 0.5, 0)", "fill": 0.5,
    "near": 0.5, "far": 20, "exposure": 12, "fileCamera": "front", "light": False,
    "lightDir": "(0, -1, 0)", "lightIntensity": 50000, "lightColor": "red", "fileLights": False,
    "environment": "file", "envFile": "studio.hdr", "envIntensity": 30000, "envRotation": 90,
    "envVisible": True, "backgroundColor": "$[0, 0, 0]", "variant": "red",
    "material": "painted", "baseColor": "blue", "animation": "spin", "animTime": 1.5,
    "animLoop": False, "toneMapping": "aces_legacy", "antialiasing": "none", "msaa": 4,
    "shadows": True, "modelCacheMiB": "512", "picking": True,
}


def _normalize(script):
    return script.replace("\r\n", "\n")


def _scene_params():
    from psychopy_filly.components.scene3d import SCENE_PARAMS
    return SCENE_PARAMS


def _model_params():
    from psychopy_filly.components.model3d import MODEL_PARAMS
    return MODEL_PARAMS


def _component(exp, name):
    return next(c for c in exp.routines["trial"] if c.name == name)


def _allowed(key):
    return next(p[5] for p in _scene_params() + _model_params() if p[0] == key)


def _call(script, start, end):
    call = script[script.index(start):]
    return call[:call.index(end) + len(end)]


def test_entry_points_register_components_without_filly():
    # A fresh process shows what PsychoPy does at startup, and that filly stays unimported.
    code = (
        "import sys, json\n"
        "from psychopy import plugins, experiment\n"
        "before = 'Model3DComponent' in experiment.getAllComponents()\n"
        "plugins.activatePlugins()\n"
        "comps = experiment.getAllComponents()\n"
        "print('RESULT', json.dumps([before, 'Scene3DComponent' in comps, 'Model3DComponent' in comps,\n"
        "                  'psychopy-filly' in plugins.listPlugins('loaded'),\n"
        "                  'filly' in sys.modules]))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    # PsychoPy's console log shares stdout and can follow the result.
    line = next(line for line in out.stdout.splitlines() if line.startswith("RESULT "))
    assert json.loads(line[len("RESULT "):]) == [False, True, True, True, False]


def test_compiled_script_matches_fixture():
    import psychopy
    if psychopy.__version__ != FIXTURE_PSYCHOPY:
        pytest.skip(f"fixture compiled with PsychoPy {FIXTURE_PSYCHOPY}, not {psychopy.__version__}")
    script = builder_helpers.compile_script(builder_helpers.build_experiment())
    assert _normalize(script) == _normalize(FIXTURE.read_text(encoding="utf-8"))


def test_generated_code():
    script = builder_helpers.compile_script(builder_helpers.build_experiment())
    ast.parse(script)
    assert "from psychopy_filly import runtime as filly_runtime\n" in script
    # Constant parameters at their default are left out of the calls.
    assert (
        "    scene = filly_runtime.SceneStim(\n"
        "        win=win, name='scene',\n"
        "        pos=(0, 0), size=(0.6, 0.6), units=win.units, ori=0.0, opacity=None,\n"
        "        colorSpace='rgb',\n"
        "        depth=0.0)\n"
    ) in script
    assert (
        "    cube = filly_runtime.SceneModel(\n"
        "        scene, 'cube.glb', name='cube', colorSpace='rgb',\n"
        "        rotation=None,\n"
        "    )\n"
    ) in script
    # Escape skips the end code; the runtime closes filly in win.close() instead.
    assert "runAtExit.append(filly" not in script
    assert "cube.setRotation((20, 90*t, 0), log=False)\n" in script
    # Both start: the scene draws, and the model shows in it.
    assert "scene.setAutoDraw(True)\n" in script and "cube.setAutoDraw(True)\n" in script
    # close_all() runs in run() before endExperiment(), so before quit() closes the window.
    end = script.index("filly_runtime.close_all()\n")
    assert end < script.index("    # mark experiment as finished\n    endExperiment(")
    # The color controls of ImageStim do not apply.
    assert "setColor" not in script and "fillColor" not in script.split("SceneStim(")[1][:400]


def test_constant_and_repeat_rotation():
    constant = builder_helpers.compile_script(builder_helpers.build_experiment(rotation="(0, 30, 0)"))
    assert "rotation=(0, 30, 0),\n" in constant
    assert "setRotation" not in constant
    repeat = builder_helpers.compile_script(
        builder_helpers.build_experiment(rotation=("$angles", "set every repeat")))
    assert "rotation=None,\n" in repeat
    assert "cube.setRotation(angles)\n" in repeat
    assert "setRotation(angles, log=False)" not in repeat


def test_non_default_constants_are_arguments():
    script = builder_helpers.compile_script(builder_helpers.build_experiment(**NON_DEFAULTS))
    ast.parse(script)
    scene = _call(script, "filly_runtime.SceneStim(", "depth=")
    model = _call(script, "filly_runtime.SceneModel(", "\n    )\n")
    expected_scene = {
        "resolution": "(256, 128)", "renderScale": "0.5", "projection": "'orthographic'", "fov": "45.0",
        "viewHeight": "2.5", "camPos": "(0, 1, 4)", "fill": "0.5", "exposure": "12.0",
        "light": "False", "lightColor": "'red'", "environment": "'file'",
        "envFile": "'studio.hdr'", "backgroundColor": "[0, 0, 0]",
        "toneMapping": "'aces_legacy'", "msaa": "4", "shadows": "True",
        "modelCacheMiB": "'512'", "picking": "True",
    }
    expected_model = {
        "rotation": "(10, 20, 30)", "modelPos": "(0.1, 0, 0)", "modelScale": "(1, 2, 1)",
        "center": "False", "fileCamera": "'front'", "fileLights": "False", "variant": "'red'",
        "baseColor": "'blue'", "animation": "'spin'", "animTime": "1.5", "animLoop": "False",
    }
    for key, value in expected_scene.items():
        assert f"        {key}={value},\n" in scene, key
    for key, value in expected_model.items():
        assert f"        {key}={value},\n" in model, key
    for key, *_ in _scene_params():
        assert f"        {key}=" in scene, key
    for key, *_ in _model_params():
        if key not in ("scene", "model"):
            assert f"        {key}=" in model, key


def test_every_changing_parameter_has_a_setter():
    from psychopy_filly.runtime import SceneModel, SceneStim
    exp = builder_helpers.build_experiment()
    for name, cls, required in (("scene", SceneStim, {"camPos", "lightDir", "pos", "opacity"}),
                                ("cube", SceneModel, {"model", "rotation", "baseColor", "animTime"})):
        comp = _component(exp, name)
        changing = [key for key, param in comp.params.items()
                    if "set every repeat" in (param.allowedUpdates or [])]
        assert required <= set(changing)
        for key in changing:
            assert callable(getattr(cls, f"set{comp._getParamCaps(key)}", None)), key


def test_every_parameter_is_an_argument():
    from psychopy_filly.runtime import SceneModel, SceneStim
    scene = set(inspect.signature(SceneStim).parameters)
    assert {key for key, *_ in _scene_params()} | {"colorSpace", "pos", "size"} <= scene
    model = set(inspect.signature(SceneModel).parameters)
    assert {key for key, *_ in _model_params()} | {"colorSpace", "name"} <= model


def test_setters_every_frame_and_every_repeat():
    frame = {key: (str(value) if not isinstance(value, str) else value, "set every frame")
             for key, value in NON_DEFAULTS.items()
             if "set every frame" in _allowed(key)}
    repeat = {key: (str(value) if not isinstance(value, str) else value, "set every repeat")
              for key, value in NON_DEFAULTS.items()
              if "set every frame" not in _allowed(key) and "set every repeat" in _allowed(key)}
    assert {"animation", "variant", "material"} <= set(repeat)
    exp = builder_helpers.build_experiment(**frame, **repeat)
    script = builder_helpers.compile_script(exp)
    ast.parse(script)
    for key in frame:
        name = "cube" if key in _component(exp, "cube").params else "scene"
        setter = f"set{_component(exp, name)._getParamCaps(key)}"
        line = script.split(f"{name}.{setter}(")[1].split("\n")[0]
        assert ", log=False)" in line, key
        assert f"        {key}=None,\n" in script, key
    for key in repeat:
        setter = f"set{_component(exp, 'cube')._getParamCaps(key)}"
        assert "log=False" not in script.split(f"cube.{setter}(")[1].split("\n")[0], key
    # Color parameters take the component's color space in the runtime, not in the call.
    assert "cube.setBaseColor('blue', log=False)\n" in script
    assert "scene.setBackgroundColor([0, 0, 0], log=False)\n" in script


def test_two_models_in_one_scene():
    from psychopy_filly.components.model3d import Model3DComponent
    exp = builder_helpers.build_experiment()
    second = Model3DComponent(exp, "trial", name="ball", startVal=1.0, stopVal=1.0)
    second.params["modelPos"].val = "(0.5, 0, 0)"
    exp.routines["trial"].addComponent(second)
    script = builder_helpers.compile_script(exp)
    assert script.count("filly_runtime.SceneStim(") == 1
    assert "    ball = filly_runtime.SceneModel(\n        scene, 'default.glb', name='ball'," in script
    # Each model shows from its own start to its own stop.
    assert "ball.setAutoDraw(True)\n" in script and "ball.setAutoDraw(False)\n" in script


def test_scene_must_exist_and_come_first():
    from psychopy.experiment.routines import Routine
    from psychopy_filly.components.model3d import Model3DComponent
    exp = builder_helpers.build_experiment(scene="stage")
    with pytest.raises(ValueError, match="Scene must name a 3D Scene component, not 'stage'"):
        builder_helpers.compile_script(exp)
    # A model above its scene in the same routine would be created first.
    exp = builder_helpers.build_experiment()
    routine = exp.routines["trial"]
    routine.insert(0, routine.pop(routine.index(_component(exp, "cube"))))
    with pytest.raises(ValueError, match="its scene scene must come before it"):
        builder_helpers.compile_script(exp)
    # A scene in an earlier routine is fine.
    exp = builder_helpers.build_experiment()
    later = Routine("later", exp)
    exp.addRoutine("later", later)
    exp.flow.addRoutine(later, 1)
    later.addComponent(Model3DComponent(exp, "later", name="ball"))
    ast.parse(builder_helpers.compile_script(exp))


def test_one_file_camera_per_scene():
    from psychopy_filly.components.model3d import Model3DComponent
    exp = builder_helpers.build_experiment(fileCamera="front")
    second = Model3DComponent(exp, "trial", name="ball")
    second.params["fileCamera"].val = "eye"
    exp.routines["trial"].addComponent(second)
    with pytest.raises(ValueError, match="both set a camera from their files for scene scene"):
        builder_helpers.compile_script(exp)


def test_psyexp_round_trip(tmp_path):
    # Studio saves the experiment and compiles a fresh Experiment loaded from the file.
    from psychopy import experiment
    from psychopy.plugins import activatePlugins
    activatePlugins()
    psyexp = tmp_path / "filly_cube.psyexp"
    params = dict(NON_DEFAULTS, animTime=("t", "set every frame"))
    builder_helpers.build_experiment(**params).saveToXML(str(psyexp))
    loaded = experiment.Experiment()
    loaded.loadFromXML(str(psyexp))
    names = [type(c).__name__ for c in loaded.routines["trial"]]
    assert [name for name in names if name.endswith("3DComponent")] == ["Scene3DComponent", "Model3DComponent"]
    cube = _component(loaded, "cube")
    assert cube.params["rotation"].updates == "constant"
    assert cube.params["animTime"].updates == "set every frame"
    assert cube.params["scene"].val == "scene"
    direct = builder_helpers.compile_script(
        builder_helpers.build_experiment(**params), modular=True, expPath=str(psyexp))
    studio = builder_helpers.compile_script(loaded, modular=True, expPath=str(psyexp))
    assert studio == direct


def test_files_are_resources(tmp_path, cube_path):
    (tmp_path / "studio.hdr").write_bytes(b"")
    exp = builder_helpers.build_experiment(environment="file", envFile="studio.hdr")
    psyexp = tmp_path / "filly_cube.psyexp"
    exp.saveToXML(str(psyexp))
    resources = exp.getResourceFiles()
    assert sorted(r["rel"] for r in resources) == ["cube.glb", "studio.hdr"]
    assert Path(next(r["abs"] for r in resources if r["rel"] == "cube.glb")) == cube_path


def test_unknown_parameter_rejected():
    from psychopy import experiment
    from psychopy_filly.components.model3d import Model3DComponent
    from psychopy_filly.components.scene3d import Scene3DComponent
    with pytest.raises(TypeError, match="Unknown parameters"):
        Scene3DComponent(experiment.Experiment(), "trial", camPosition="(0, 0, 1)")
    with pytest.raises(TypeError, match="Unknown parameters"):
        Model3DComponent(experiment.Experiment(), "trial", camPos="(0, 0, 1)")


def test_studio_profiles():
    from psychopy.experiment.components import getAllComponents
    from psychopy.liaison import LiaisonJSONEncoder
    from psychopy.plugins import activatePlugins
    activatePlugins()
    components = getAllComponents()
    if not hasattr(components["Scene3DComponent"], "getTemplateJSON"):
        pytest.skip("This PsychoPy predates Studio component profiles")
    for name, icon, specs, base in (
            ("Scene3DComponent", "scene3d.png", _scene_params(),
             {"pos", "size", "units", "ori", "opacity", "startVal", "stopVal", "colorSpace"}),
            ("Model3DComponent", "model3d.png", _model_params(), {"startVal", "stopVal", "colorSpace"})):
        cls = components[name]
        profile = json.loads(json.dumps(cls.getTemplateJSON(), cls=LiaisonJSONEncoder))
        assert profile["categories"] == ["Stimuli"]
        assert profile["targets"] == ["PsychoPy", "PsychoJS"]
        assert profile["plugin"] == "psychopy-filly"
        assert profile["iconSVG"].lstrip().startswith("<?xml")
        assert Path(profile["iconFile"]).name == icon
        params = profile["params"]
        assert base <= set(params)
        assert {key for key, *_ in specs} <= set(params)
        assert not {"color", "fillColor", "borderColor", "contrast"} & set(params)
    model = json.loads(json.dumps(components["Model3DComponent"].getTemplateJSON(), cls=LiaisonJSONEncoder))
    assert model["params"]["model"]["valType"] == "file"
    assert "set every frame" in model["params"]["rotation"]["allowedUpdates"]
    assert not {"pos", "size", "camPos"} & set(model["params"])


def test_icons_present():
    for stem in ("model3d", "scene3d"):
        folder = TESTS.parent / "psychopy_filly" / "components" / stem
        for theme in ("classic", "light", "dark"):
            for name in (f"{stem}.png", f"{stem}@2x.png"):
                assert (folder / theme / name).is_file(), f"{stem}/{theme}/{name}"
        assert (folder / f"{stem}.svg").is_file()


# --- PsychoJS ----------------------------------------------------------------------------------

def test_psychojs_script(tmp_path):
    builder_helpers.write_cube(tmp_path / "cube.glb")
    script = builder_helpers.compile_js(builder_helpers.build_experiment(), tmp_path)
    # PsychoPy adds variable declarations only when esprima parses the script; without them the
    # module fails at its first assignment.
    assert "var filly_runtime;\n" in script and "var scene;\n" in script and "var cube;\n" in script
    assert (
        "  if (typeof filly_runtime === 'undefined') {\n"
        "    filly_runtime = await import('./filly/filly-psychojs.js');\n"
        "    filly_runtime.init({ util, visual });\n"
        "  }\n"
        "  scene = await filly_runtime.SceneStim.create({\n"
        "    win: psychoJS.window, name: 'scene',\n"
        "    pos: [0, 0], size: [0.6, 0.6], units: psychoJS.window.units, ori: 0.0, opacity: undefined,\n"
        "    colorSpace: 'rgb',\n"
        "    depth: 0.0\n"
        "  });\n"
    ) in script
    assert (
        "  cube = await filly_runtime.SceneModel.create({\n"
        "    scene: scene, name: 'cube', model: 'cube.glb', colorSpace: 'rgb',\n"
        "    rotation: undefined,\n"
        "  });\n"
    ) in script
    assert "cube.setRotation([20, (90 * t), 0], false);\n" in script
    assert "scene.setAutoDraw(true);\n" in script and "cube.setAutoDraw(true);\n" in script
    # closeAll() runs in quitPsychoJS(), at the end and after Escape, before the window closes.
    quit_function = script[script.index("async function quitPsychoJS("):]
    assert quit_function.index("await filly_runtime.closeAll();") < quit_function.index("psychoJS.window.close();")
    # The model file is a resource that PsychoJS downloads.
    assert "{'name': 'cube.glb', 'path': 'cube.glb'}" in script


def test_psychojs_copies_web_files(tmp_path):
    from psychopy_filly.components._common import WEB_FILES
    builder_helpers.compile_js(builder_helpers.build_experiment(), tmp_path)
    copied = sorted(p.relative_to(tmp_path / "filly").as_posix() for p in (tmp_path / "filly").rglob("*") if p.is_file())
    vendored = sorted(p.relative_to(WEB_FILES).as_posix() for p in WEB_FILES.rglob("*") if p.is_file())
    assert copied == vendored
    assert {"filly.js", "filly-core.js", "filly-core.wasm", "filly-psychojs.js", "licenses/Filament.txt"} <= set(copied)
    for name in copied:
        assert (tmp_path / "filly" / name).read_bytes() == (WEB_FILES / name).read_bytes()
    # The vendor record matches the files.
    record = json.loads((WEB_FILES / "VENDOR.json").read_text(encoding="utf-8"))["files"]
    for name, entry in record.items():
        assert hashlib.sha256((WEB_FILES / name).read_bytes()).hexdigest() == entry["sha256"], name


def test_default_model(tmp_path):
    import filly.samples
    from psychopy_filly import runtime
    from psychopy_filly.components._common import DEFAULT_MODEL, default_model_file
    from psychopy_filly.components.model3d import Model3DComponent

    assert DEFAULT_MODEL == runtime.DEFAULT_MODEL == "default.glb"
    assert default_model_file() == filly.samples.SUZANNE
    exp = builder_helpers.build_experiment()
    assert Model3DComponent(exp, "trial").params["model"].val == DEFAULT_MODEL
    # Only an experiment that shows the default model gets a copy, and PsychoJS does not
    # download it as a resource: the runtime loads it from the filly folder.
    script = builder_helpers.compile_js(builder_helpers.build_experiment(model=DEFAULT_MODEL), tmp_path)
    assert (tmp_path / "filly" / DEFAULT_MODEL).read_bytes() == filly.samples.SUZANNE.read_bytes()
    assert "model: 'default.glb'," in script
    assert "'path': 'default.glb'" not in script
    other = tmp_path / "other"
    other.mkdir()
    builder_helpers.compile_js(builder_helpers.build_experiment(), other)
    assert not (other / "filly" / DEFAULT_MODEL).exists()


@pytest.mark.parametrize("target", ["PsychoPy", "PsychoJS"])
def test_compile_reports_names_missing_from_the_model(tmp_path, monkeypatch, target):
    from psychopy_filly.components import model3d
    warnings = []
    monkeypatch.setattr(model3d.logging, "warning", warnings.append)
    builder_helpers.write_cube(tmp_path / "cube.glb")
    # Right names, glTF indices, blanks, and code are not reported.
    exp = builder_helpers.build_experiment(animation="run", variant="blue", material="painted",
                                           fileCamera="$camera", baseColor="red")
    if target == "PsychoJS":
        builder_helpers.compile_js(exp, tmp_path)
    else:
        builder_helpers.compile_script(exp, expPath=str(tmp_path / "filly_cube.psyexp"))
    assert warnings == [
        "psychopy-filly: cube: the animation clip 'run' is not in cube.glb. Its animation clips: 'spin'",
        "psychopy-filly: cube: the material variant 'blue' is not in cube.glb. Its material variants: 'red'",
    ]


def test_psychojs_non_default_arguments(tmp_path):
    script = builder_helpers.compile_js(builder_helpers.build_experiment(**NON_DEFAULTS), tmp_path)
    scene = _call(script, "filly_runtime.SceneStim.create(", "depth:")
    model = _call(script, "filly_runtime.SceneModel.create(", "\n  });\n")
    expected_scene = {"projection": "'orthographic'", "camPos": "[0, 1, 4]", "light": "false",
                      "lightColor": "'red'", "backgroundColor": "[0, 0, 0]", "msaa": "4",
                      "shadows": "true"}
    expected_model = {"rotation": "[10, 20, 30]", "center": "false", "fileCamera": "'front'",
                      "variant": "'red'", "animation": "'spin'", "animLoop": "false"}
    for key, value in expected_scene.items():
        assert f"    {key}: {value},\n" in scene, key
    for key, value in expected_model.items():
        assert f"    {key}: {value},\n" in model, key
    for key, *_ in _scene_params():
        if key != "picking":  # browsers have no first-pick cost to move
            assert f"    {key}: " in scene, key
    for key, *_ in _model_params():
        if key not in ("scene", "model"):
            assert f"    {key}: " in model, key


def test_psychojs_setters(tmp_path):
    frame = {key: (str(value) if not isinstance(value, str) else value, "set every frame")
             for key, value in NON_DEFAULTS.items() if "set every frame" in _allowed(key)}
    exp = builder_helpers.build_experiment(**frame)
    script = builder_helpers.compile_js(exp, tmp_path)
    assert "cube.setBaseColor('blue', false);\n" in script
    assert "scene.setBackgroundColor([0, 0, 0], false);\n" in script
    assert "scene.setCamPos([0, 1, 4], false);\n" in script
    runtime = RUNTIME_JS.read_text(encoding="utf-8")
    comp = _component(exp, "cube")
    for key in frame:
        assert re.search(rf"^\t+set{comp._getParamCaps(key)}\(", runtime, re.M), key


def test_model_set_every_repeat(tmp_path):
    exp = builder_helpers.build_experiment(model=("$modelFile", "set every repeat"))
    script = builder_helpers.compile_script(exp, expPath=str(tmp_path / "filly_cube.psyexp"))
    # The model is not known at init: the component starts without one, and loads nothing.
    assert "        scene, None, name='cube'," in script
    routine_start = script[script.index("# --- Prepare to start Routine \"trial\" ---"):]
    assert "    cube.setModel(modelFile)\n" in routine_start
    js = builder_helpers.compile_js(builder_helpers.build_experiment(model=("$modelFile", "set every repeat")),
                                    tmp_path)
    assert "model: undefined," in js
    # The routine's start waits for the load, so its first frame shows the new model.
    assert "    await cube.setModel(modelFile);\n" in js
    assert (tmp_path / "filly" / "default.glb").is_file()


def test_model_set_during_static_period(tmp_path):
    from psychopy.experiment.components.static import StaticComponent
    exp = builder_helpers.build_experiment(model=("$modelFile", "set during: trial.ISI"))
    routine = exp.routines["trial"]
    isi = StaticComponent(exp, "trial", name="ISI", startVal=0.0, stopVal=0.5)
    routine.insert(0, isi)
    isi.addComponentUpdate("trial", "cube", "model")
    script = builder_helpers.compile_script(exp, expPath=str(tmp_path / "filly_cube.psyexp"))
    static_code = script[script.index("# Updating other components during *ISI*"):]
    assert "cube.setModel(modelFile)" in static_code[:static_code.index("# Component updates done")]
    js = builder_helpers.compile_js(exp, tmp_path)
    static_js = js[js.index("// Updating other components during *ISI*"):]
    static_js = static_js[:static_js.index("// Component updates done")]
    # PsychoPy writes the static period's call without await; the runtime does not draw the
    # scene until the model has loaded.
    assert "cube.setModel(modelFile);" in static_js and "await cube.setModel" not in static_js


def test_web_files_copy_only_changes(tmp_path, monkeypatch):
    """Each component's compile copies the web files; unchanged copies are skipped by size and
    time stamp, without reading the 3.7 MB, and keep their time stamps."""
    import os
    from types import SimpleNamespace
    from psychopy_filly.components import _common

    exp = SimpleNamespace(expPath=str(tmp_path / "experiment.psyexp"), filename=None)
    _common.copy_web_files(exp)
    wasm = tmp_path / _common.WEB_FOLDER / "filly-core.wasm"
    assert wasm.read_bytes() == (_common.WEB_FILES / "filly-core.wasm").read_bytes()
    reads = []
    read_bytes = Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes", lambda path: reads.append(path) or read_bytes(path))
    _common.copy_web_files(exp)
    assert reads == []
    # Same contents with another time stamp: compared, and left alone.
    earlier = wasm.stat().st_mtime_ns - 10**9
    os.utime(wasm, ns=(earlier, earlier))
    _common.copy_web_files(exp)
    assert reads == [wasm, _common.WEB_FILES / "filly-core.wasm"] and wasm.stat().st_mtime_ns == earlier
    # Changed contents: copied.
    runtime = tmp_path / _common.WEB_FOLDER / "filly-psychojs.js"
    runtime.write_text("changed")
    _common.copy_web_files(exp)
    assert read_bytes(runtime) == read_bytes(_common.WEB_FILES / "filly-psychojs.js")


@pytest.mark.parametrize("value, python, js", [
    ("512", "modelCacheMiB='512',", "modelCacheMiB: '512',"),
    ("0", "modelCacheMiB='0',", "modelCacheMiB: '0',"),
    ("unlimited", "modelCacheMiB='unlimited',", "modelCacheMiB: 'unlimited',"),
    ("$cacheSize", "modelCacheMiB=cacheSize,", "modelCacheMiB: cacheSize,"),
])
def test_model_cache_parameter(tmp_path, value, python, js):
    """The 3D Scene's model cache limit reaches both runtimes; blank writes nothing."""
    from psychopy_filly.runtime import _cache_limit
    script = builder_helpers.compile_script(builder_helpers.build_experiment(modelCacheMiB=value))
    assert f"    {python}\n" in _call(script, "filly_runtime.SceneStim(", "depth=")
    javascript = builder_helpers.compile_js(builder_helpers.build_experiment(modelCacheMiB=value), tmp_path)
    assert f"  {js}\n" in javascript
    if not value.startswith("$"):
        assert _cache_limit(value) == (float("inf") if value == "unlimited" else int(value) * 2**20)
    blank = builder_helpers.compile_script(builder_helpers.build_experiment())
    assert "modelCacheMiB" not in blank
    runtime = RUNTIME_JS.read_text(encoding="utf-8")
    assert "modelCacheMiB" in runtime


@pytest.mark.parametrize("clickable", ["cube", "scene", "cube, scene"])
def test_mouse_clickable_models(tmp_path, clickable):
    """A Mouse component can list 3D Models and 3D Scenes as clickable stimuli and correct answers:
    PsychoPy calls their contains() with the mouse."""
    experiment = builder_helpers.build_experiment(duration=5.0)
    builder_helpers.add_mouse(experiment, clickable=clickable)
    script = builder_helpers.compile_script(experiment)
    ast.parse(script)
    assert "if obj.contains(mouse):" in script
    names = clickable if "," not in clickable else f"[{clickable}]"
    assert f"getFromNames({names}, namespace=locals())" in script
    builder_helpers.write_cube(tmp_path / "cube.glb")
    js = builder_helpers.compile_js(experiment, tmp_path)
    assert "if (obj.contains(mouse)) {" in js
    # Online, contains() answers from picks of the pointer that started before the click.
    assert js.count("    trackPointer: true,\n") == 1


def test_scene_tracks_pointer_only_for_mouse_components(tmp_path):
    experiment = builder_helpers.build_experiment(duration=5.0)
    assert "trackPointer" not in builder_helpers.compile_js(experiment, tmp_path / "plain")
    builder_helpers.add_mouse(experiment, clickable="", end="any click")
    assert "trackPointer" not in builder_helpers.compile_js(experiment, tmp_path / "unrelated")
    mouse = _component(experiment, "mouse")
    mouse.params["storeCorrect"].val = True
    mouse.params["correctAns"].val = "cube"
    assert "trackPointer: true" in builder_helpers.compile_js(experiment, tmp_path / "correct")


def _add_code(exp, python, js):
    from psychopy.experiment.components.code import CodeComponent

    code = CodeComponent(exp, "trial", name="code")
    code.params["Code Type"].val = "Both"
    code.params["Each Frame"].val = python
    code.params["Each JS Frame"].val = js
    exp.routines["trial"].addComponent(code)


@pytest.mark.parametrize("python,js,picking,tracks", [
    (None, None, False, False),
    ("if cube.contains(mouse):\n    pass", "if (cube.contains(mouse)) {}", True, True),
    ("if mouse.isPressedIn(scene):\n    pass", "if (mouse.isPressedIn(scene)) {}", True, True),
    ("query = scene.pick(mouse)", "query = scene.pick(mouse);", True, False),
    ("hit = scene.lastPick", "hit = scene.lastPick;", True, False),
    ("cubes.contains(mouse)", "cubes.contains(mouse);", False, False),  # another object's name
])
def test_scene_prepares_picking_only_when_used(tmp_path, python, js, picking, tracks):
    """The window prepares picking at start (60 to 75 ms on Intel Iris Xe) only for scenes that a
    Mouse component or a Code component picks with; online, only synchronous calls need the
    pointer picks of trackPointer."""
    experiment = builder_helpers.build_experiment(duration=5.0)
    if python is not None:
        _add_code(experiment, python, js)
    script = builder_helpers.compile_script(experiment)
    ast.parse(script)
    assert ("    picking=True,\n" in script) == picking
    builder_helpers.write_cube(tmp_path / "cube.glb")
    assert ("trackPointer: true" in builder_helpers.compile_js(experiment, tmp_path)) == tracks


def test_mouse_component_prepares_picking():
    experiment = builder_helpers.build_experiment(duration=5.0)
    builder_helpers.add_mouse(experiment, clickable="cube")
    assert builder_helpers.compile_script(experiment).count("    picking=True,\n") == 1


def test_mouse_picking_checkbox(tmp_path):
    """The checkbox covers code that the text search does not find. Online it changes nothing:
    browsers have no one-time first-pick cost to move."""
    experiment = builder_helpers.build_experiment(duration=5.0, picking=True)
    assert builder_helpers.compile_script(experiment).count("    picking=True,\n") == 1
    builder_helpers.write_cube(tmp_path / "cube.glb")
    js = builder_helpers.compile_js(experiment, tmp_path)
    assert "picking" not in js and "trackPointer" not in js
