"""Code that the 3D Scene and 3D Model components share.

The component modules must not import filly: PsychoPy imports them to list components and to
compile experiments, also where filly is not installed. Generated code calls
`psychopy_filly.runtime` (Python) or `filly-psychojs.js` (PsychoJS).
"""

import importlib.util
import shutil
from pathlib import Path

from psychopy import logging
from psychopy.experiment.components import Param
from psychopy.localization import _translate

# filly's web build and the PsychoJS runtime, copied into each experiment folder.
WEB_FILES = Path(__file__).parents[1] / "web"
WEB_FOLDER = "filly"
# The 3D Model component's default model, as PsychoPy's image default is "default.png": filly's
# sample Suzanne. A file of this name in the experiment folder takes precedence.
DEFAULT_MODEL = "default.glb"
URL = "https://github.com/aforren1/psychopy-filly#readme"

ALL_UPDATES = ["constant", "set every repeat", "set every frame"]
REPEAT_UPDATES = ["constant", "set every repeat"]

# Code that the first 3D component in a script writes: load the PsychoJS runtime once.
JS_RUNTIME = (
    "// filly's runtime for 3D stimuli, in the experiment's filly folder\n"
    "if (typeof filly_runtime === 'undefined') {\n"
    f"  filly_runtime = await import('./{WEB_FOLDER}/filly-psychojs.js');\n"
    "  filly_runtime.init({ util, visual });\n"
    "}\n")


def default_model_file():
    """Return the path of filly's sample model, or None, without importing filly."""
    spec = importlib.util.find_spec("filly")
    return Path(spec.origin).parent / "samples" / "suzanne.glb" if spec and spec.origin else None


def add_params(component, specs, values):
    """Add parameters from (name, default, valType, inputType, tab, allowed updates, allowed
    values, label, hint) tuples. `values` overrides defaults by name."""
    unknown = set(values) - {spec[0] for spec in specs}
    if unknown:
        raise TypeError(f"Unknown parameters: {sorted(unknown)}")
    for key, default, valType, inputType, categ, updates, allowedVals, label, hint in specs:
        extra = {"allowedVals": allowedVals} if allowedVals else {}
        component.params[key] = Param(
            values.get(key, default), valType=valType, inputType=inputType, categ=categ,
            updates="constant", allowedUpdates=list(updates), allowedTypes=[],
            hint=_translate(hint), label=_translate(label), **extra)
        component.order.append(key)


def writes(component, specs, key):
    """Whether the generated call needs `key`: constant parameters at their default are left out."""
    param = component.params[key]
    default = next(spec[1] for spec in specs if spec[0] == key)
    return param.updates != "constant" or str(param.val) != str(default)


def js_literals(inits):
    # As ImageStim does: JavaScript literals for booleans and absent values.
    for key, param in inits.items():
        if param.val is True:
            inits[key] = "true"
        elif param.val is False:
            inits[key] = "false"
        elif param.val in (None, "None", "none", ""):
            inits[key] = "undefined"
    return inits


def experiment_folder(exp):
    exp_path = getattr(exp, "expPath", None) or exp.filename
    return Path(exp_path).parent if exp_path else None


def copy_web_files(exp, extra=()):
    """Copy filly's web files, and `extra` (source, name) pairs, into the experiment's filly
    folder, so that the experiment loads them from its own origin, locally and on Pavlovia."""
    folder = experiment_folder(exp)
    if folder is None:
        logging.warning("psychopy-filly: save the experiment before compiling it to PsychoJS; "
                        "the web files were not copied")
        return
    target = folder / WEB_FOLDER
    target.mkdir(exist_ok=True)
    files = [(source, target / source.relative_to(WEB_FILES))
             for source in WEB_FILES.rglob("*") if source.is_file()]
    files += [(source, target / name) for source, name in extra]
    for source, destination in files:
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Unchanged files keep their time stamps, so Pavlovia sync uploads only updates. Copies
        # keep the source's time stamp, so that the next compile (one per component) can skip a
        # copy by size and time without reading the 3.7 MB of files.
        if destination.exists():
            have, want = destination.stat(), source.stat()
            if have.st_size == want.st_size and (
                    have.st_mtime_ns == want.st_mtime_ns or destination.read_bytes() == source.read_bytes()):
                continue
        shutil.copy2(source, destination)


def write_close_code(buff):
    # Close order: scenes, then renderers, then (in quit()) the window. Repeated calls are
    # valid, so several components can each write this.
    buff.writeIndentedLines(
        "# release filly scenes and renderers while the window is open\n"
        "filly_runtime.close_all()\n")


def write_close_code_js(buff):
    # quitPsychoJS() runs at the end and after Escape, before it closes the window.
    buff.writeIndentedLines(
        "// release filly scenes and renderers while the window is open\n"
        "if (typeof filly_runtime !== 'undefined') {\n"
        "  await filly_runtime.closeAll();\n"
        "}\n")
