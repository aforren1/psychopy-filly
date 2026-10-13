"""The "3D Scene" Builder component: the image, camera, lights, and rendering of a filly scene.

3D Model components add models to it. See _common.py: this module must not import filly.
"""

import re
from pathlib import Path

from psychopy.experiment.components import BaseVisualComponent, getInitVals
from psychopy.localization import _translate

from .._common import (ALL_UPDATES, JS_RUNTIME, URL, add_params, copy_web_files, js_literals,
                       write_close_code, write_close_code_js, writes)

_here = Path(__file__).parent
TONE_MAPPERS = ["linear", "aces_legacy", "aces", "filmic", "pbr_neutral", "gt7", "agx",
                "agx_punchy", "agx_golden", "generic"]

# Parameters in dialog order, as
# (name, default, valType, inputType, tab, allowed updates, allowed values, label, hint).
# Each name is also the SceneStim argument and, with "set" and a capital, its setter.
SCENE_PARAMS = [
    ("resolution", "", "list", "single", "Layout", [], None, "Render size [w,h]",
     "Size of the rendered image in pixels. Blank: the initial size in window pixels, times "
     "the render scale. Set it when the size changes during the experiment"),
    ("renderScale", 1, "num", "single", "Layout", [], None, "Render scale",
     "Factor for the automatic render size, in (0, 2]. Below 1 renders fewer pixels and "
     "stretches the image, which blurs edges and fine detail; 2 renders twice the pixels and "
     "averages them. Not used when the render size is set"),

    ("projection", "perspective", "str", "choice", "Camera", [], ["perspective", "orthographic"],
     "Projection", "Perspective or orthographic (parallel) projection"),
    ("fov", 30, "num", "single", "Camera", ALL_UPDATES, None, "Field of view (deg)",
     "Vertical field of view of the perspective projection, in degrees"),
    ("viewHeight", "", "num", "single", "Camera", ALL_UPDATES, None, "View height",
     "Height of the orthographic view in scene units. Blank: from the framing"),
    ("camPos", "", "list", "single", "Camera", ALL_UPDATES, None, "Camera position [x,y,z]",
     "Camera position in scene units. Blank: the camera looks along -Z and frames all models "
     "of the scene, as placed when they loaded"),
    ("lookAt", "(0, 0, 0)", "list", "single", "Camera", ALL_UPDATES, None, "Look at [x,y,z]",
     "Point that the camera looks at when the camera position is set"),
    ("fill", 0.9, "num", "single", "Camera", ALL_UPDATES, None, "Framing fill",
     "Fraction of the narrower image axis that the framed models span when the camera "
     "position is blank"),
    ("near", "", "num", "single", "Camera", ALL_UPDATES, None, "Near clip",
     "Near clipping plane in scene units. Blank: automatic"),
    ("far", "", "num", "single", "Camera", ALL_UPDATES, None, "Far clip",
     "Far clipping plane in scene units. Blank: automatic"),
    ("exposure", "", "num", "single", "Camera", ALL_UPDATES, None, "Exposure (EV100)",
     "Camera exposure. Lower values give a brighter image. Blank: 15"),

    ("light", True, "bool", "bool", "Lighting", [], None, "Directional light",
     "Add a directional light"),
    ("lightDir", "(-1, -1, -2)", "list", "single", "Lighting", ALL_UPDATES, None,
     "Light direction [x,y,z]", "Direction in which the light shines"),
    ("lightIntensity", 100000, "num", "single", "Lighting", ALL_UPDATES, None,
     "Light intensity (lux)", "Illuminance of the directional light"),
    ("lightColor", "white", "color", "color", "Lighting", ALL_UPDATES, None, "Light color",
     "Color of the directional light"),
    ("environment", "uniform", "str", "choice", "Lighting", [], ["uniform", "none", "file"],
     "Environment light", "Image-based light: even from all directions, none, or from a file"),
    ("envFile", "", "file", "file", "Lighting", [], None, "Environment file",
     "A 2:1 panorama (.hdr, .png, .jpg) or a cmgen KTX cubemap, for 'file'"),
    ("envIntensity", 20000, "num", "single", "Lighting", ALL_UPDATES, None,
     "Environment intensity (lux)", "Intensity of the environment light"),
    ("envRotation", 0, "num", "single", "Lighting", ALL_UPDATES, None,
     "Environment rotation (deg)", "Rotation of the environment about the vertical axis"),
    ("envVisible", False, "bool", "bool", "Lighting", [], None, "Show environment",
     "Draw the environment behind the models instead of the background"),

    ("backgroundColor", "", "color", "color", "Appearance", ALL_UPDATES, None,
     "Background color", "Background of the rendered image. Blank: transparent"),

    ("toneMapping", "linear", "str", "choice", "Rendering", [], TONE_MAPPERS, "Tone mapping",
     "Tone mapper. 'linear' clamps; 'aces_legacy' matches Filament's gltf_viewer"),
    ("antialiasing", "fxaa", "str", "choice", "Rendering", [], ["none", "fxaa"],
     "Antialiasing", "Post-process antialiasing"),
    ("msaa", 1, "int", "choice", "Rendering", [], [1, 2, 4, 8], "MSAA samples",
     "Multisample antialiasing"),
    ("shadows", False, "bool", "bool", "Rendering", [], None, "Shadows",
     "Shadows from the directional light"),
    # Like PsychoPy's "Draggable?": a checkbox that the stimulus constructor takes. Picking works
    # without it; it only moves a one-time driver cost from the first click to the start.
    ("picking", False, "bool", "bool", "Layout", [], None, "Mouse picking",
     "Prepare the window for clicks on this scene's models when the experiment starts, so that "
     "the first click is not slow (about 60 ms on Intel graphics). On automatically when a Mouse "
     "component lists the scene or its models, or a Code component calls pick(), contains(), "
     "isPressedIn(), or lastPick on them; turn it on for other code"),
    # Text, not a number, so that "unlimited" compiles to a string in both targets.
    ("modelCacheMiB", "", "str", "single", "Rendering", [], None, "Model cache (MiB)",
     "Memory limit of the window's cache of model files that changed per trial. Blank: the "
     "default (1024 MiB locally, 256 MiB online); 0: off; unlimited: no limit. The first 3D "
     "Scene in a window that sets this decides"),
]


# Calls that answer a click in the frame of the click. Online they need the pointer picks that
# trackPointer starts before the click.
_ANSWERS_AT_ONCE = ("contains", "isPressedIn")

class Scene3DComponent(BaseVisualComponent):
    """Show a 3D scene rendered by filly. 3D Model components add models to it."""

    categories = ["Stimuli"]
    targets = ["PsychoPy", "PsychoJS"]
    plugin = "psychopy-filly"
    # PsychoPy finds classic/, light/, and dark/ versions and @2x files from this name.
    iconFile = _here / "scene3d.png"
    # PsychoPy Studio shows this file.
    iconSVG = _here / "scene3d.svg"
    tooltip = _translate("3D Scene: the camera, lights, and image of 3D models rendered with filly")
    # Builder's Help button opens this page.
    url = URL
    # Earliest supported PsychoPy. For an experiment whose "Use version" is earlier, Builder saves
    # a legacy copy without this component.
    version = "2024.2.0"
    beta = True

    def __init__(self, exp, parentName, name="scene",
                 units="from exp settings", pos=(0, 0), size=(0.5, 0.5), ori=0, opacity="",
                 colorSpace="rgb",
                 startType="time (s)", startVal=0.0,
                 stopType="duration (s)", stopVal=1.0,
                 startEstim="", durationEstim="", **values):
        super().__init__(
            exp, parentName, name=name, units=units, pos=pos, size=size, ori=ori,
            opacity=opacity, colorSpace=colorSpace, startType=startType, startVal=startVal,
            stopType=stopType, stopVal=stopVal, startEstim=startEstim,
            durationEstim=durationEstim)
        self.type = "Scene3D"
        self.exp.requireImport(importName="runtime", importFrom="psychopy_filly",
                               importAs="filly_runtime")
        # filly draws its own colors; these ImageStim-style controls do not apply. colorSpace
        # stays: it applies to the color parameters below.
        for key in ("color", "fillColor", "borderColor", "contrast"):
            del self.params[key]
        add_params(self, SCENE_PARAMS, values)
        self.params["colorSpace"].hint = _translate("Color space of the light and background colors")

    def _arguments(self, inits, python):
        # "picking" is written by writeInitCode, which also turns it on when the experiment picks.
        return "".join(
            (f"    {key}={inits[key]},\n" if python else f"  {key}: {inits[key]},\n")
            for key, *_ in SCENE_PARAMS if key != "picking" and writes(self, SCENE_PARAMS, key))

    def writeInitCode(self, buff):
        inits = getInitVals(self.params, "PsychoPy")
        code = (
            "{name} = filly_runtime.SceneStim(\n"
            "    win=win, name='{name}',\n"
            "    pos={pos}, size={size}, units={units}, ori={ori}, opacity={opacity},\n"
            "    colorSpace={colorSpace},\n"
            "{arguments}"
            "{picking}"
            "    depth={depth:.1f})\n"
        ).format(name=inits["name"], pos=inits["pos"], size=inits["size"], units=inits["units"],
                 ori=inits["ori"], opacity=inits["opacity"], colorSpace=inits["colorSpace"],
                 arguments=self._arguments(inits, True),
                 picking="    picking=True,\n" if self._picks() else "",
                 depth=-self.getPosInRoutine())
        buff.writeIndentedLines(code)

    def writeExperimentEndCode(self, buff):
        write_close_code(buff)

    def writeInitCodeJS(self, buff):
        copy_web_files(self.exp)
        inits = js_literals(getInitVals(self.params, "PsychoJS"))
        code = (
            "{name} = await filly_runtime.SceneStim.create({{\n"
            "  win: psychoJS.window, name: '{name}',\n"
            "  pos: {pos}, size: {size}, units: {units}, ori: {ori}, opacity: {opacity},\n"
            "  colorSpace: {colorSpace},\n"
            "{arguments}"
            "{track}"
            "  depth: {depth:.1f}\n"
            "}});\n"
        ).format(name=inits["name"], pos=inits["pos"], size=inits["size"], units=inits["units"],
                 ori=inits["ori"], opacity=inits["opacity"], colorSpace=inits["colorSpace"],
                 arguments=self._arguments(inits, False),
                 track=("  trackPointer: true,\n"
                        if self._clicked() or self._code_calls(_ANSWERS_AT_ONCE) else ""),
                 depth=-self.getPosInRoutine())
        buff.writeIndentedLines(JS_RUNTIME + code)

    def _components(self):
        return [component for routine in self.exp.routines.values() for component in routine]

    def _own_names(self):
        """This scene's name and the names of its 3D Model components."""
        name = self.params["name"].val
        return {name} | {component.params["name"].val for component in self._components()
                         if getattr(component, "type", None) == "Model3D" and component._scene_name() == name}

    def _clicked(self):
        """Whether a Mouse component lists this scene or one of its models as a clickable stimulus
        or a correct answer. Online, contains() answers a click only from picks of the pointer
        position that started before it (see trackPointer in filly-psychojs.js)."""
        own = self._own_names()
        for component in self._components():
            if getattr(component, "type", None) != "Mouse":
                continue
            for key in ("clickable", "correctAns"):
                if key in component.params and own & set(re.findall(r"\w+", str(component.params[key].val))):
                    return True
        return False

    def _code_calls(self, methods):
        """Whether a Code component calls one of `methods` on this scene or one of its models, as
        `name.method` or `mouse.isPressedIn(name)`. A text search: code that reaches the objects
        another way is not found, and only pays the first pick's cost then."""
        own = "|".join(re.escape(name) for name in sorted(self._own_names()))
        calls = "|".join(methods)
        pattern = re.compile(rf"\b(?:{own})\s*\.\s*(?:{calls})\b"
                             + (rf"|\bisPressedIn\s*\(\s*(?:{own})\b" if "isPressedIn" in methods else ""))
        for component in self._components():
            if getattr(component, "type", None) != "Code":
                continue
            if any(pattern.search(str(param.val)) for param in component.params.values()):
                return True
        return False

    def _picks(self):
        """Whether the window prepares picking at start: the "Mouse picking" checkbox, or a Mouse
        or Code component that picks with this scene."""
        return (str(self.params["picking"].val).lower() == "true" or self._clicked()
                or self._code_calls(_ANSWERS_AT_ONCE + ("pick", "lastPick")))

    def writeExperimentEndCodeJS(self, buff):
        write_close_code_js(buff)
