"""The "3D Model" Builder component: one glTF model in a 3D Scene component's scene.

The model is visible in its scene from its start to its stop. See _common.py: this module must
not import filly.
"""

from pathlib import Path

from psychopy import logging
from psychopy.experiment.components import BaseComponent, BaseVisualComponent, Param, getInitVals
from psychopy.localization import _translate

from ... import gltf_info
from .._common import (ALL_UPDATES, DEFAULT_MODEL, REPEAT_UPDATES, URL, WEB_FOLDER, add_params,
                       copy_web_files, default_model_file, experiment_folder, js_literals,
                       write_close_code, write_close_code_js, writes)

_here = Path(__file__).parent
SCENE_TYPE = "Scene3D"
CHECK = " A name that the model file does not have is reported with its names when the experiment compiles"

# Parameters that name something in the model file: (gltf_info.Contents attribute, description).
_NAME_PARAMS = {
    "animation": ("animations", "animation clip"),
    "variant": ("variants", "material variant"),
    "material": ("materials", "material"),
    "fileCamera": ("cameras", "camera node"),
}

# Parameters in dialog order, as
# (name, default, valType, inputType, tab, allowed updates, allowed values, label, hint).
# Each name is also the SceneModel argument and, with "set" and a capital, its setter.
MODEL_PARAMS = [
    # A name, not code: Builder evaluates constant code fields and warns about the NameError.
    ("scene", "scene", "str", "single", "Basic", [], None, "Scene",
     "Name of the 3D Scene component that shows this model. It must come before this component: "
     "in an earlier routine, or above it in the same routine"),
    ("model", DEFAULT_MODEL, "file", "file", "Basic", REPEAT_UPDATES, None, "Model file",
     "The glTF model to show: a .glb file (preferred) or a .gltf file. "
     "default.glb: filly's sample model, Suzanne"),
    ("rotation", "(0, 0, 0)", "list", "single", "Basic", ALL_UPDATES, None, "Rotation [x,y,z]",
     "Rotation in degrees about X, then Y, then Z, for example (0, 45*t, 0)"),
    ("modelPos", "(0, 0, 0)", "list", "single", "Basic", ALL_UPDATES, None,
     "Model position [x,y,z]", "Position in scene units (glTF units are meters)"),
    ("modelScale", "1", "list", "single", "Basic", ALL_UPDATES, None, "Model scale",
     "One scale factor, or [x,y,z] factors"),
    ("center", True, "bool", "bool", "Basic", [], None, "Center model",
     "Put the center of the model's bounding box at the model position, so that the model "
     "rotates about its center"),

    ("fileLights", True, "bool", "bool", "File", [], None, "Lights from file",
     "Keep the lights in the model file"),
    ("fileCamera", "", "str", "single", "File", [], None, "Camera from file",
     "Name or node index of a camera in the model file. The scene renders through it, and the "
     "scene's camera settings, except exposure, do not apply. Only one model of a scene can set "
     "it." + CHECK),

    ("variant", "", "str", "single", "Appearance", REPEAT_UPDATES, None, "Material variant",
     "Name or index of a material variant in the model file." + CHECK),
    ("material", "", "str", "single", "Appearance", REPEAT_UPDATES, None, "Material name",
     "Material that the base color changes. Blank: all materials." + CHECK),
    ("baseColor", "", "color", "color", "Appearance", ALL_UPDATES, None, "Base color",
     "Base color that replaces the material's. Blank: as in the file"),

    ("animation", "", "str", "single", "Animation", REPEAT_UPDATES, None, "Animation clip",
     "Name or index of an animation clip in the model file. Blank: no animation." + CHECK),
    ("animTime", "", "num", "single", "Animation", ALL_UPDATES, None, "Animation time (s)",
     "Time in the clip, in seconds. To play the clip from this model's start, use "
     "t - <name>.tStart (for example t - cube.tStart) with 'set every frame'. For one pose per "
     "trial, use a conditions column with 'set every repeat'. Blank: the clip's first pose"),
    ("animLoop", True, "bool", "bool", "Animation", [], None, "Loop animation",
     "Wrap times beyond the clip duration. Otherwise the last pose holds"),
]


class Model3DComponent(BaseComponent):
    """Show a glTF model in a 3D Scene component's scene, rendered by filly."""

    categories = ["Stimuli"]
    targets = ["PsychoPy", "PsychoJS"]
    plugin = "psychopy-filly"
    # PsychoPy finds classic/, light/, and dark/ versions and @2x files from this name.
    iconFile = _here / "model3d.png"
    # PsychoPy Studio shows this file.
    iconSVG = _here / "model3d.svg"
    tooltip = _translate("3D Model: show a glTF model in a 3D Scene")
    # Builder's Help button opens this page.
    url = URL
    # Earliest supported PsychoPy. For an experiment whose "Use version" is earlier, Builder saves
    # a legacy copy without this component.
    version = "2024.2.0"
    beta = True

    # Start and stop show and hide the model: the same code as for visual components, with the
    # model's setAutoDraw(). Routine ends call setAutoDraw(False) on every component that has it.
    writeFrameCode = BaseVisualComponent.writeFrameCode
    writeFrameCodeJS = BaseVisualComponent.writeFrameCodeJS

    def __init__(self, exp, parentName, name="model", colorSpace="rgb",
                 startType="time (s)", startVal=0.0,
                 stopType="duration (s)", stopVal=1.0,
                 startEstim="", durationEstim="", **values):
        super().__init__(
            exp, parentName, name=name, startType=startType, startVal=startVal,
            stopType=stopType, stopVal=stopVal, startEstim=startEstim,
            durationEstim=durationEstim, syncScreenRefresh=True)
        self.type = "Model3D"
        self.exp.requireImport(importName="runtime", importFrom="psychopy_filly",
                               importAs="filly_runtime")
        add_params(self, MODEL_PARAMS, values)
        self.params["colorSpace"] = Param(
            colorSpace, valType="str", inputType="choice", categ="Appearance",
            allowedVals=["named", "hex", "rgb", "dkl", "lms", "hsv"], updates="constant",
            hint=_translate("Color space of the base color"), label=_translate("Color space"))

    # --- code ------------------------------------------------------------------------------

    def _init_vals(self, target):
        inits = getInitVals(self.params, target)
        # A model that changes per repeat is not known at init. Start without one: a stand-in
        # would load, compile, and upload for nothing before the first repeat replaces it.
        if self._model_changes():
            inits["model"].val = None
            inits["model"].valType = "code"
        return inits

    def _arguments(self, inits, python):
        return "".join(
            (f"    {key}={inits[key]},\n" if python else f"  {key}: {inits[key]},\n")
            for key, *_ in MODEL_PARAMS
            if key not in ("scene", "model") and writes(self, MODEL_PARAMS, key))

    def writeInitCode(self, buff):
        self._check()
        inits = self._init_vals("PsychoPy")
        code = (
            "{name} = filly_runtime.SceneModel(\n"
            "    {scene}, {model}, name='{name}', colorSpace={colorSpace},\n"
            "{arguments}"
            ")\n"
        ).format(name=inits["name"], scene=self._scene_name(), model=inits["model"],
                 colorSpace=inits["colorSpace"], arguments=self._arguments(inits, True))
        buff.writeIndentedLines(code)

    def writeExperimentEndCode(self, buff):
        write_close_code(buff)

    def writeInitCodeJS(self, buff):
        self._check()
        extra = []
        # Only experiments that can show the default model upload it. A model that changes per
        # repeat can be the default model, from a conditions file.
        if str(self.params["model"].val).strip() == DEFAULT_MODEL or self._model_changes():
            source = default_model_file()
            if source and source.is_file():
                extra.append((source, DEFAULT_MODEL))
            else:
                logging.warning("psychopy-filly: filly's sample model was not found; install filly, "
                                f"or put a {DEFAULT_MODEL} in the experiment folder")
        copy_web_files(self.exp, extra)
        folder = experiment_folder(self.exp)
        if extra and not (folder and (folder / DEFAULT_MODEL).is_file()):
            # A Static or Resource Manager component that prepares the model file would download
            # default.glb from the experiment folder, where it is not, and a Static component then
            # waits for that download. A downloaded resource of that name satisfies both.
            buff.writeIndentedLines(
                "await psychoJS.serverManager.prepareResources([\n"
                f"  {{name: '{DEFAULT_MODEL}', path: '{WEB_FOLDER}/{DEFAULT_MODEL}'}}]);\n")
        inits = js_literals(self._init_vals("PsychoJS"))
        code = (
            "{name} = await filly_runtime.SceneModel.create({{\n"
            "  scene: {scene}, name: '{name}', model: {model}, colorSpace: {colorSpace},\n"
            "{arguments}"
            "}});\n"
        ).format(name=inits["name"], scene=self._scene_name(), model=inits["model"],
                 colorSpace=inits["colorSpace"], arguments=self._arguments(inits, False))
        buff.writeIndentedLines(code)

    def writeExperimentEndCodeJS(self, buff):
        write_close_code_js(buff)

    def writeParamUpdate(self, buff, compName, paramName, val, updateType, params=None,
                         target="PsychoPy"):
        # In JS the model loads asynchronously. The routine's start code can wait for it, so its
        # first frame shows the new model. (A static period's code calls setModel() without
        # waiting; the scene is not drawn until the model has loaded.)
        if paramName == "model" and target == "PsychoJS":
            buff.writeIndentedLines(f"await {compName}.setModel({str(val).strip()});\n")
            return
        super().writeParamUpdate(buff, compName, paramName, val, updateType, params=params, target=target)

    # --- checks ----------------------------------------------------------------------------

    def _scene_name(self):
        return str(self.params["scene"].val).strip().lstrip("$").strip()

    def _model_changes(self):
        return self.params["model"].updates not in ("constant", None, "None", "")

    def _position(self, component):
        """(routine position in the flow, component position in the routine), or None."""
        routines = []
        for entry in self.exp.flow:
            name = getattr(entry, "name", None)
            if name in self.exp.routines and name not in routines:
                routines.append(name)
        for index, name in enumerate(routines):
            routine = self.exp.routines[name]
            if component in routine:
                return index, routine.index(component)
        return None

    def _check(self):
        """Fail the compile for a missing scene, or one created after this model; warn about
        names that the model file does not have."""
        name = self._scene_name()
        scene = self.exp.getComponentFromName(name) if name else None
        if scene is None or getattr(scene, "type", None) != SCENE_TYPE:
            raise ValueError(f"psychopy-filly: {self.name}: Scene must name a 3D Scene component, "
                             f"not {name!r}")
        own, scenes = self._position(self), self._position(scene)
        if own is not None and scenes is not None and scenes > own:
            raise ValueError(f"psychopy-filly: {self.name}: its scene {name} must come before it: "
                             "in an earlier routine, or above it in the same routine")
        if str(self.params["fileCamera"].val).strip():
            for routine in self.exp.routines.values():
                for other in routine:
                    if (other is not self and getattr(other, "type", None) == self.type
                            and other._scene_name() == name and str(other.params["fileCamera"].val).strip()):
                        raise ValueError(f"psychopy-filly: {self.name} and {other.name} both set a camera "
                                         f"from their files for scene {name}; only one model can")
        self._check_names()

    def _model_file(self):
        """Return the model file that the experiment loads, or None if code chooses it."""
        value = str(self.params["model"].val).strip()
        if not value or value.startswith("$") or self._model_changes():
            return None
        return gltf_info.model_file(value, experiment_folder(self.exp) or None)

    def _check_names(self):
        """Warn about clip, variant, material, and camera names that the model file does not have.

        Builder has no stable way to offer the names in its dialog, so the compile reports a
        wrong name together with the names that the file has.
        """
        path = self._model_file()
        if path is None or not path.is_file():
            return
        try:
            contents = gltf_info.contents(path)
        except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
            logging.warning(f"psychopy-filly: {self.name}: cannot read the names in {path.name}: {error}")
            return
        for key, (attribute, what) in _NAME_PARAMS.items():
            value = str(self.params[key].val).strip()
            # Blank, code, and glTF indices are not checked here.
            if not value or value.startswith("$") or value.isdigit():
                continue
            items = getattr(contents, attribute)
            if value in {item.key for item in items}:
                continue
            names = ", ".join(f"'{item.key}'" for item in items[:20]) or "none"
            if len(items) > 20:
                names += f", and {len(items) - 20} more"
            logging.warning(f"psychopy-filly: {self.name}: the {what} '{value}' is not in {path.name}. "
                            f"Its {what}s: {names}")
