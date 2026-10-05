"""Check that PsychoPy discovers the component and compiles an experiment with it.

Usage: python tools/check_builder.py OUT_DIR

Run it with the Python of each PsychoPy installation to check. It needs no display and no filly.
It reproduces three paths:

1. Plugin discovery, as the wxPython app and Studio's liaison do: `plugins.activatePlugins()`.
2. The wxPython Builder compile: `psychopy.scripts.psyexpCompile.generateScript`.
3. The Studio calls: `psychopy.experiment:getElementProfiles`, then `Experiment()`,
   `loadFromXML(psyexp)`, and `writeScript(target="PsychoPy", modular=True, expPath=psyexp)`.

It writes the profile, the psyexp file, and the scripts to OUT_DIR and prints a summary.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))


def main():
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    report = {"python": sys.version.split()[0]}

    import psychopy
    from psychopy import experiment, plugins
    report["psychopy"] = psychopy.__version__

    # --- 1. discovery
    report["registered_before_activate"] = "Model3DComponent" in experiment.getAllComponents()
    plugins.scanPlugins()
    report["listPlugins_all"] = "psychopy-filly" in plugins.listPlugins("all")
    plugins.activatePlugins()
    report["listPlugins_loaded"] = "psychopy-filly" in plugins.listPlugins("loaded")
    report["listPlugins_failed"] = plugins.listPlugins("failed")
    components = experiment.getAllComponents()
    report["registered_after_activate"] = {name: name in components
                                           for name in ("Scene3DComponent", "Model3DComponent")}
    report["pluginComponents"] = sorted(experiment.components.pluginComponents)
    report["module_attribute"] = {name: hasattr(experiment.components, name)
                                  for name in ("Scene3DComponent", "Model3DComponent")}
    report["filly_imported_by_activation"] = "filly" in sys.modules
    cls = components["Model3DComponent"]
    report["class"] = f"{cls.__module__}:{cls.__qualname__}"

    # --- 3a. Studio profile call, serialized as the liaison does
    profile = experiment.getElementProfiles()["Model3DComponent"]
    try:
        from psychopy.liaison import LiaisonJSONEncoder
        encoder = LiaisonJSONEncoder
    except ImportError:  # the liaison needs websockets
        encoder = None
    text = json.dumps(profile, cls=encoder, default=None if encoder else str, indent=1)
    (out / "profile.json").write_text(text, encoding="utf-8")
    loaded = json.loads(text)
    report["profile_summary"] = {
        key: loaded.get(key) for key in (
            "__class__", "__name__", "categories", "targets", "plugin", "iconFile", "tooltip",
            "version", "beta", "helpLink")}
    report["profile_iconSVG_chars"] = len(loaded.get("iconSVG") or "")
    report["profile_params"] = list(loaded["params"])

    # --- 2. wxPython Builder compile (in-process, as Builder's Compile command does)
    import builder_helpers
    exp = builder_helpers.build_experiment()
    builder_helpers.write_cube(out / "cube.glb")
    psyexp = out / "filly_cube.psyexp"
    exp.saveToXML(str(psyexp))
    from psychopy.scripts.psyexpCompile import generateScript
    wx_script = out / "filly_cube_wx.py"
    generateScript(exp, str(wx_script))
    wx_text = wx_script.read_text("utf-8-sig")
    report["wx_compile_has_scene_and_model"] = ("filly_runtime.SceneStim(" in wx_text
                                                and "filly_runtime.SceneModel(" in wx_text)

    # --- 3b. Studio compile: a fresh Experiment loaded from the psyexp file
    studio_exp = experiment.Experiment()
    studio_exp.loadFromXML(str(psyexp))
    routine = studio_exp.routines["trial"]
    report["studio_loaded_component_type"] = [
        type(c).__name__ for c in routine if c.name in ("scene", "cube")]
    script = studio_exp.writeScript(target="PsychoPy", modular=True, expPath=str(psyexp))
    (out / "filly_cube_studio.py").write_text(script, encoding="utf-8")
    report["studio_compile_has_scene_and_model"] = ("filly_runtime.SceneStim(" in script
                                                    and "filly_runtime.SceneModel(" in script)
    report["resources"] = [str(r) for r in studio_exp.getResourceFiles()]

    print(json.dumps(report, indent=1, default=str))


if __name__ == "__main__":
    main()
