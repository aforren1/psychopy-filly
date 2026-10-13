"""Shared helpers: a cube model file and a Builder experiment that shows it.

The scripts in tools/ also use these helpers, so keep them free of pytest.
"""

import json
import math
import re
import struct
from pathlib import Path

# Per-face colors make the rotation visible in a screenshot.
_FACES = [  # normal, color
    ((1, 0, 0), (0.9, 0.2, 0.2)), ((-1, 0, 0), (0.2, 0.9, 0.2)),
    ((0, 1, 0), (0.2, 0.3, 0.9)), ((0, -1, 0), (0.9, 0.9, 0.2)),
    ((0, 0, 1), (0.9, 0.5, 0.1)), ((0, 0, -1), (0.6, 0.2, 0.8)),
]


def cube_glb(half=0.5, pulse=False):
    """Return a GLB with a cube of the given half size, 24 vertices, and per-face colors.

    It also has what the component's file parameters need: a camera node "front" at (0, 0, 4)
    looking along -Z with a 30-degree field of view, a 2-second clip "spin" that turns the cube
    once about Y, and a material variant "red". With `pulse`, a second 2-second clip "pulse"
    animates the base color of "painted" from (1, 1, 1, 1) to (0, 0, 0, 0) (KHR_animation_pointer).
    """
    positions, normals, colors, indices = [], [], [], []
    for normal, color in _FACES:
        axis = max(range(3), key=lambda i: abs(normal[i]))
        u, v = [i for i in range(3) if i != axis]
        sign = normal[axis]
        base = len(positions)
        for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            p = [0.0, 0.0, 0.0]
            p[axis], p[u], p[v] = sign * half, a * half, b * half
            positions.append(p)
            normals.append(list(map(float, normal)))
            colors.append([*color, 1.0])
        # Counterclockwise when seen from outside the cube.
        quad = [0, 1, 2, 0, 2, 3]
        cross = _cross(_sub(positions[base + 1], positions[base]), _sub(positions[base + 2], positions[base]))
        if sum(c * n for c, n in zip(cross, normal)) < 0:
            quad = [0, 2, 1, 0, 3, 2]
        indices += [base + i for i in quad]

    # Clip: quaternions about Y at 0, 90, 180, 270, and 360 degrees, one key every 0.5 s.
    times = [0.0, 0.5, 1.0, 1.5, 2.0]
    rotations = []
    for i in range(5):
        angle = math.radians(90 * i) / 2
        rotations.append([0.0, math.sin(angle), 0.0, math.cos(angle)])
    blobs = [
        struct.pack(f"<{len(positions) * 3}f", *sum(positions, [])),
        struct.pack(f"<{len(normals) * 3}f", *sum(normals, [])),
        struct.pack(f"<{len(colors) * 4}f", *sum(colors, [])),
        struct.pack(f"<{len(indices)}H", *indices),
        struct.pack(f"<{len(times)}f", *times),
        struct.pack(f"<{len(rotations) * 4}f", *sum(rotations, [])),
        struct.pack("<2f", 0.0, 2.0),
        struct.pack("<8f", 1, 1, 1, 1, 0, 0, 0, 0),
    ]
    views, offset = [], 0
    for blob in blobs:
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(blob)})
        offset += (len(blob) + 3) & ~3
    binary = b"".join(blob + b"\0" * (((len(blob) + 3) & ~3) - len(blob)) for blob in blobs)
    document = {
        "asset": {"version": "2.0", "generator": "psychopy-filly tests"},
        "extensionsUsed": ["KHR_materials_variants"],
        "extensions": {"KHR_materials_variants": {"variants": [{"name": "red"}]}},
        "scene": 0,
        "scenes": [{"nodes": [0, 1]}],
        "nodes": [{"mesh": 0, "name": "cube"},
                  {"camera": 0, "name": "front", "translation": [0, 0, 4]}],
        "cameras": [{"type": "perspective", "perspective": {
            "yfov": math.radians(30), "znear": 0.1, "zfar": 100}}],
        "meshes": [{"primitives": [{
            "attributes": {"POSITION": 0, "NORMAL": 1, "COLOR_0": 2}, "indices": 3, "material": 0,
            "extensions": {"KHR_materials_variants": {"mappings": [{"material": 1, "variants": [0]}]}},
        }]}],
        "materials": [
            {"name": "painted", "pbrMetallicRoughness": {
                "baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0.0, "roughnessFactor": 0.6}},
            {"name": "red", "pbrMetallicRoughness": {
                "baseColorFactor": [1, 0, 0, 1], "metallicFactor": 0.0, "roughnessFactor": 0.6}},
        ],
        "animations": [{"name": "spin",
                        "samplers": [{"input": 4, "output": 5, "interpolation": "LINEAR"}],
                        "channels": [{"sampler": 0, "target": {"node": 0, "path": "rotation"}}]}],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": views,
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 24, "type": "VEC3",
             "min": [-half] * 3, "max": [half] * 3},
            {"bufferView": 1, "componentType": 5126, "count": 24, "type": "VEC3"},
            {"bufferView": 2, "componentType": 5126, "count": 24, "type": "VEC4"},
            {"bufferView": 3, "componentType": 5123, "count": len(indices), "type": "SCALAR"},
            {"bufferView": 4, "componentType": 5126, "count": len(times), "type": "SCALAR",
             "min": [times[0]], "max": [times[-1]]},
            {"bufferView": 5, "componentType": 5126, "count": len(rotations), "type": "VEC4"},
            {"bufferView": 6, "componentType": 5126, "count": 2, "type": "SCALAR", "min": [0.0], "max": [2.0]},
            {"bufferView": 7, "componentType": 5126, "count": 2, "type": "VEC4"},
        ],
    }
    if pulse:
        document["extensionsUsed"].append("KHR_animation_pointer")
        document["animations"].append({
            "name": "pulse", "samplers": [{"input": 6, "output": 7, "interpolation": "LINEAR"}],
            "channels": [{"sampler": 0, "target": {"path": "pointer", "extensions": {"KHR_animation_pointer": {
                "pointer": "/materials/0/pbrMetallicRoughness/baseColorFactor"}}}}]})
    text = json.dumps(document, separators=(",", ":")).encode()
    text += b" " * (-len(text) % 4)
    chunks = (struct.pack("<II", len(text), 0x4E4F534A) + text
              + struct.pack("<II", len(binary), 0x004E4942) + binary)
    return struct.pack("<III", 0x46546C67, 2, 12 + len(chunks)) + chunks


def write_cube_gltf(folder, name="cube.gltf", buffer="cube data.bin"):
    """Write the cube as a .gltf document and an external buffer file, and return its path.

    The buffer's file name has a space, so its URI is percent-encoded.
    """
    folder = Path(folder)
    data = cube_glb()
    json_length = struct.unpack_from("<I", data, 12)[0]
    document = json.loads(data[20:20 + json_length])
    binary_length = struct.unpack_from("<I", data, 20 + json_length)[0]
    binary = data[28 + json_length:28 + json_length + binary_length]
    document["buffers"][0]["uri"] = buffer.replace(" ", "%20")
    (folder / buffer).write_bytes(binary)
    path = folder / name
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _sub(a, b):
    return [x - y for x, y in zip(a, b)]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def write_cube(path, pulse=False):
    path = Path(path)
    path.write_bytes(cube_glb(pulse=pulse))
    return path


def build_experiment(model="cube.glb", duration=3.0, win_size=(800, 600), blend_mode="nofbo",
                     size=(0.6, 0.6), **params):
    """Return a one-routine experiment with a 3D Scene component named "scene" and, below it, a
    3D Model component named "cube" in that scene.

    Each keyword in `params` sets a parameter of whichever component has it: a value, or
    (value, updates). The default rotates the model: rotation=("(20, 90*t, 0)", "set every frame").

    The settings suit unattended runs: no info dialog, no frame-rate measurement, a window.
    The default blend mode is "nofbo" (average, no framebuffer object).
    """
    from psychopy import experiment
    from psychopy.experiment.routines import Routine
    from psychopy_filly.components.model3d import Model3DComponent
    from psychopy_filly.components.scene3d import Scene3DComponent

    exp = experiment.Experiment()
    exp.settings.params["expName"].val = "filly_cube"
    settings = exp.settings.params
    settings["Show info dlg"].val = False
    settings["Full-screen window"].val = False
    settings["Window size (pixels)"].val = list(win_size)
    settings["measureFrameRate"].val = False
    settings["frameRate"].val = 60
    settings["blendMode"].val = blend_mode
    routine = Routine("trial", exp)
    exp.addRoutine("trial", routine)
    exp.flow.addRoutine(routine, 0)
    scene = Scene3DComponent(exp, "trial", name="scene", startVal=0.0, stopVal=duration, size=size)
    cube = Model3DComponent(exp, "trial", name="cube", startVal=0.0, stopVal=duration)
    params["model"] = model
    params.setdefault("rotation", ("(20, 90*t, 0)", "set every frame"))
    for key, value in params.items():
        value, updates = value if isinstance(value, tuple) else (value, "constant")
        # The model's own colorSpace, name, and timing stay; shared names go to the model.
        component = cube if key in cube.params else scene
        component.params[key].val = value
        component.params[key].updates = updates
    routine.addComponent(scene)
    routine.addComponent(cube)
    return exp


def add_mouse(exp, clickable="cube", end="valid click", save="final"):
    """Add a Mouse component named "mouse" below the 3D components of the experiment's routine:
    `clickable` names its clickable stimuli, and `end` ends the routine on that kind of click."""
    from psychopy.experiment.components.mouse import MouseComponent

    routine = exp.routines["trial"]
    stop = next(c for c in routine if c.name == "scene").params["stopVal"].val
    mouse = MouseComponent(exp, "trial", name="mouse", startVal=0.0, stopVal=stop, save=save,
                           forceEndRoutineOnPress=end)
    mouse.params["clickable"].val = clickable
    routine.addComponent(mouse)
    return mouse


def compile_script(exp, **kwargs):
    """Compile to a PsychoPy script with the build date removed, so output is reproducible."""
    script = exp.writeScript(target="PsychoPy", **kwargs)
    # The date format follows the platform's locale: "October 13, 2026, at 19:42" on Windows,
    # "Tue Oct 13 19:42:39 2026" on Linux.
    return re.sub(r"(Experiment Builder \(v[^)]*\),\n\s*on ).*", r"\g<1><date>", script, count=1)


def compile_js(exp, folder, duration=None):
    """Save the experiment in folder and compile it to PsychoJS there; return the script.

    Two defects of the PsychoJS export in psychopy-lib 2026.2.4 break the script in a browser,
    with or without this plugin, and are avoided here:
    - The default participant value is a Python f-string. The export cannot parse the script,
      so it adds no variable declarations, and the module fails on its first assignment.
    - A Routine without a maximum duration writes `trialMaxDuration = None`.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    exp.settings.params["Experiment info"].val = "{'participant': '1', 'session': '001'}"
    for routine in exp.routines.values():
        if routine.settings.params["stopVal"].val in ("", None, "None"):
            routine.settings.params["stopVal"].val = duration or 1.0
    psyexp = folder / "filly_cube.psyexp"
    exp.filename = str(psyexp)
    exp.saveToXML(str(psyexp))
    script = exp.writeScript(target="PsychoJS", expPath=str(psyexp))
    (folder / "filly_cube.js").write_text(script, encoding="utf-8")
    return script
