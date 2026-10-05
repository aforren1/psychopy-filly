"""Run-time support for psychopy-filly components.

This module is the only part of the plugin that calls the filly API. Generated experiment code
calls `SceneStim`, `SceneModel`, and `close_all()`; the component code does not know filly.

One filly renderer serves each PsychoPy window. Close order: every target, then the renderer,
then the window. `close_all()` does the first two steps. The generated code calls it from
`runAtExit`, which PsychoPy runs before `quit()` closes the window, on the normal path and on
Escape. An `atexit` handler covers scripts that stop with an exception.
"""

import atexit
import collections
import math
import sys
import urllib.parse
from pathlib import Path

import numpy as np
from psychopy import logging
from psychopy import __version__ as psychopy_version
from psychopy.colors import Color
from psychopy.layout import Size
from psychopy.visual.basevisual import MinimalStim

from . import gltf_info

__all__ = ["SceneStim", "SceneModel", "close_all", "TESTED_PSYCHOPY", "DEFAULT_MODEL"]

# The 3D Model component's default model, filly's sample Suzanne. A file of this name in the working
# directory takes precedence.
DEFAULT_MODEL = "default.glb"

# The filly adapter uses PsychoPy internals (ImageStim texture path, the window's image shader).
TESTED_PSYCHOPY = ("2026.2.4",)

# Memory limit of each window's model cache (see _ModelCache), in bytes of filly's estimate.
# 0 turns the cache off; None removes the limit. A 3D Scene's "Model cache (MiB)" parameter
# overrides it for its window. Change it before the experiment calls setModel().
MODEL_CACHE_MAX_BYTES = 2**30

_hosts = []  # _Host objects, one per window
_atexit_registered = False
_version_checked = False


def _check_environment(win):
    global _version_checked
    if sys.platform not in ("win32", "linux"):
        raise RuntimeError(f"psychopy-filly supports Windows and Linux only, not {sys.platform}")
    if win.winType != "pyglet":
        raise RuntimeError(
            f"psychopy-filly requires the pyglet window backend, but this window uses "
            f"{win.winType!r}. Set the window backend to pyglet in the experiment settings.")
    if win.blendMode != "avg":
        raise RuntimeError(
            f"psychopy-filly requires the 'avg' blend mode, but this window uses "
            f"{win.blendMode!r}. Set the blend mode to 'average' in the experiment settings.")
    if not _version_checked:
        _version_checked = True
        if psychopy_version not in TESTED_PSYCHOPY:
            logging.warning(
                f"psychopy-filly was tested with PsychoPy {', '.join(TESTED_PSYCHOPY)}, "
                f"not {psychopy_version}")


class _Host:
    """The renderer for one window and the stimuli that use it."""

    def __init__(self, win, precompiled_shaders):
        # Imported here so that the Builder component and code generation work where filly is
        # not installed, for example in the standalone PsychoPy app.
        import filly
        from filly.integrations.psychopy import create_renderer

        # Filament's startup details would fill the Runner output; warnings and errors remain.
        filly.set_log_level("warning")
        self.win = win
        self.renderer = create_renderer(win, precompiled_shaders=precompiled_shaders)
        self.stims = []
        self.transparent_ready = False  # whether a transparent scene has rendered
        self.model_cache = _ModelCache(self.renderer)

    def close(self):
        # Targets first: closing a target fences the window's last draw of it.
        try:
            for stim in list(self.stims):
                stim.close()
            self.model_cache.close()
        finally:
            self.renderer.close()


def _host_for(win, precompiled_shaders):
    global _atexit_registered
    for host in _hosts:
        if host.win is win:
            if host.renderer.precompiled_shaders != precompiled_shaders:
                # One renderer per window: the first stimulus decides.
                logging.warning(
                    f"precompiled_shaders={precompiled_shaders} ignored: the window's renderer "
                    f"already uses {host.renderer.precompiled_shaders}")
            return host
    _check_environment(win)
    host = _Host(win, precompiled_shaders)
    _hosts.append(host)
    if not _atexit_registered:
        # PsychoPy registered its window close at window creation, earlier than this. atexit runs
        # handlers in reverse order, so this one runs while the window is still open.
        atexit.register(close_all)
        _atexit_registered = True
    return host


def close_all():
    """Close all stimuli and renderers that this module created. The windows stay open.

    Repeated calls are valid.
    """
    while _hosts:
        _hosts.pop(0).close()


# --- value conversion ------------------------------------------------------------------------
# Builder passes lists, tuples, numbers, and strings. Blank fields arrive as None or "".

def _blank(value):
    return value is None or (isinstance(value, str) and value.strip() in ("", "None", "none"))


def _vector(value, name, size=3):
    values = np.asarray(value, dtype=float).reshape(-1)
    if values.size != size or not np.all(np.isfinite(values)):
        raise ValueError(f"{name} needs {size} finite numbers, got {value!r}")
    return tuple(values.tolist())


def _scale(value):
    values = np.asarray(value, dtype=float).reshape(-1)
    if values.size == 1:
        values = np.repeat(values, 3)
    if values.size != 3 or not np.all(np.isfinite(values)) or np.any(values == 0):
        raise ValueError(f"modelScale needs 1 or 3 nonzero numbers, got {value!r}")
    return tuple(values.tolist())


def _number(value, name, low=-math.inf, high=math.inf, low_open=False):
    number = float(value)
    if not (low < number if low_open else low <= number) or not number <= high:
        raise ValueError(f"{name} must be in {'(' if low_open else '['}{low}, {high}], got {value!r}")
    return number


def _srgb_to_linear(values):
    values = np.clip(np.asarray(values, dtype=float), 0.0, 1.0)
    return np.where(values <= 0.04045, values / 12.92, ((values + 0.055) / 1.055) ** 2.4)


def _linear_color(value, space, name):
    """Convert a PsychoPy color to linear RGBA in [0, 1].

    PsychoPy colors are display values. filly's inputs are linear and its output is sRGB encoded,
    so this conversion makes an unlit surface or the background show the PsychoPy color.
    """
    color = value if isinstance(value, Color) else Color(value, space)
    if not color.valid:
        raise ValueError(f"{name}: {value!r} is not a valid color in color space {space!r}")
    rgb = _srgb_to_linear(color.rgb1)
    return (*rgb.tolist(), float(color.alpha))


def _key(value, names):
    """Return a filly lookup key: a name if it exists, else an index typed as text or a number."""
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = str(value).strip()
    if text in names or not text.isdigit():
        return text
    return int(text)


def _euler_matrix(degrees):
    # filly applies Euler rotations about X, then Y, then Z: R = Rz @ Ry @ Rx. The product is
    # written out because "set every frame" rotations build it every frame.
    x, y, z = (math.radians(v) for v in degrees)
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    return np.array([[cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx],
                     [sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx],
                     [-sy, cy * sx, cy * cx]])


def _animated_base_colors(model):
    """Return the names of the materials whose base color a clip of the filly model animates.

    Applying or resetting any clip restores those base colors to their loaded values, so a base
    color setting must be written to them again afterwards. Other materials keep it.
    """
    return {name for clip in model.animations for name, parameter in clip.material_properties
            if parameter == "baseColorFactor"}


def _uniform_panorama():
    # A uniform panorama gives even ambient light, so faces away from the key light stay visible.
    return np.full((8, 16, 3), 1.0, dtype=np.float32)


# Defaults for arguments given as None. The Builder components document the same values.
_DEFAULTS = {
    "rotation": (0.0, 0.0, 0.0),
    "modelPos": (0.0, 0.0, 0.0),
    "modelScale": (1.0, 1.0, 1.0),
    "fov": 30.0,
    "lookAt": (0.0, 0.0, 0.0),
    "fill": 0.9,
    "lightDir": (-1.0, -1.0, -2.0),
    "lightIntensity": 100000.0,
    "lightColor": (1.0, 1.0, 1.0, 1.0),
    "envIntensity": 20000.0,
    "envRotation": 0.0,
    "animTime": 0.0,
}
# The framing box of a scene without models.
_EMPTY_BOX = ((-1.0, -1.0, -1.0), (1.0, 1.0, 1.0))


def _box_corners(box):
    low, high = np.asarray(box[0], dtype=float), np.asarray(box[1], dtype=float)
    return np.array([[(low, high)[i >> k & 1][k] for k in range(3)] for i in range(8)])


def _merge_spheres(spheres):
    """Return a sphere (center, radius) that encloses all given spheres. Centers are tuples."""
    center, radius = spheres[0]
    for other_center, other_radius in spheres[1:]:
        offset = [b - a for a, b in zip(center, other_center)]
        distance = math.hypot(*offset)
        if distance + other_radius <= radius:
            continue
        if distance + radius <= other_radius:
            center, radius = other_center, other_radius
            continue
        new_radius = (distance + radius + other_radius) / 2
        center = tuple(a + d / distance * (new_radius - radius) for a, d in zip(center, offset))
        radius = new_radius
    return center, radius


def _file_size(path):
    """Return the size of a model file in bytes, with the external buffers and images of a .gltf."""
    size = path.stat().st_size
    if path.suffix.lower() == ".gltf":
        document = gltf_info.read_document(path)
        for item in document.get("buffers", []) + document.get("images", []):
            uri = item.get("uri", "")
            if uri and not uri.startswith("data:"):
                external = path.parent / urllib.parse.unquote(uri)
                size += external.stat().st_size if external.is_file() else 0
    return size


def _cache_limit(value):
    """Convert a "Model cache (MiB)" value to bytes: None for blank (the module setting), math.inf
    for 'unlimited'."""
    if _blank(value):
        return None
    if isinstance(value, str) and value.strip().lower() == "unlimited":
        return math.inf
    return round(_number(value, "modelCacheMiB", 0) * 2**20)


class _ModelCache:
    """Hidden prototypes of the model files that setModel() loaded in one window.

    A file shown again, as in conditions that alternate models, is then a clone of its prototype.
    On the test laptop (Intel Iris Xe), a clone took 0.1 to 8 ms where a load took 1 to 150 ms,
    for files of 0.07 to 7.4 MB, and needs no texture upload. Clones share the prototype's
    geometry, textures, and compiled materials, and have their own material instances, so a base
    color or variant stays with its model.

    The cost: each prototype keeps its asset, also while no model shows it: the source data that
    cloning needs and the decoded textures and geometry on the GPU. The entries total at most the
    limit in filly's estimate (Model.memory: cpu_bytes + gpu_bytes, which also holds what earlier
    clones left), least recently used out first. A model above the limit loads without source
    data and is not cached. Models that show are the experiment's own; only the prototypes count.

    The prototypes live in a hidden scene of the cache, so that a scene can close while other
    scenes of the window still clone them. filly clones across the scenes of one renderer.
    """

    def __init__(self, renderer):
        self._renderer = renderer
        self._scene = None  # the hidden scene, made at the first prototype
        self._entries = collections.OrderedDict()  # key: prototype, least recently used first
        self._too_large = set()  # keys of files above the limit, loaded without source data
        self.limit = None  # bytes from a scene's parameter; None: MODEL_CACHE_MAX_BYTES
        self.loads = 0  # files loaded, for tests

    def _limit(self):
        limit = MODEL_CACHE_MAX_BYTES if self.limit is None else self.limit
        return math.inf if limit is None else limit

    @staticmethod
    def _bytes(model):
        memory = model.memory
        return memory.cpu_bytes + memory.gpu_bytes

    def size(self):
        """The estimated bytes that the prototypes hold."""
        return sum(self._bytes(prototype) for prototype in self._entries.values())

    def instance(self, path, scene, refraction):
        """Return a new filly Model of the file at `path` in `scene`: a clone, or a load.

        A clone keeps the material setup of its asset's load, which depends on the refraction
        setting of the loading scene, so that setting is part of the key.
        """
        path = Path(path)
        limit = self._limit()
        try:
            stat = path.stat()
            size = _file_size(path)
        except (OSError, ValueError, UnicodeDecodeError):
            size = None  # filly reports the error
        key = None if size is None else (str(path.resolve()), stat.st_size, stat.st_mtime_ns, refraction)
        # The source data alone is about the file size, so a larger file cannot fit.
        if key is None or key in self._too_large or size > limit:
            self.loads += 1
            return scene.load(str(path))
        prototype = self._entries.get(key)
        if prototype is None:
            self.loads += 1
            loaded = scene.load(str(path), clonable=True)
            if self._bytes(loaded) > limit:
                # Loaded again without the source data, which the model would otherwise keep
                # while it shows. Once per file: the key remembers it.
                loaded.close()
                self._too_large.add(key)
                self.loads += 1
                return scene.load(str(path))
            if self._scene is None:
                self._scene = self._renderer.create_scene()
            self._entries[key] = loaded.clone(scene=self._scene)
            self._evict(key)
            return loaded
        self._entries.move_to_end(key)
        model = prototype.clone(scene=scene)
        # A clone leaves bone and animation data with the asset, so the entry can grow past the
        # limit.
        self._evict(key)
        return model

    def _evict(self, keep):
        total, limit = self.size(), self._limit()
        # A prototype can close while clones of it show: they keep the shared asset.
        for key in list(self._entries):
            if total <= limit:
                break
            if key == keep:
                continue
            prototype = self._entries.pop(key)
            total -= self._bytes(prototype)
            prototype.close()

    def close(self):
        for prototype in self._entries.values():
            prototype.close()
        self._entries.clear()
        if self._scene is not None:
            self._scene.close()
            self._scene = None


class _Settings:
    """State that setters change and that the next render applies, in named groups."""

    def _init_settings(self):
        self._state = {}
        self._dirty = set()
        self._inputs = {}  # key: the setter input that gave the stored value, see _update()

    def _update(self, key, raw, convert, groups, log):
        """Convert a setter input and store it; return whether the value changed.

        "Set every frame" calls each setter in every frame, mostly with an unchanged input, and a
        color conversion alone takes tens of microseconds. An input equal to the previous one
        therefore skips the conversion and its checks. Only inputs that cannot change in place
        qualify: a list compares by a copy, other mutable inputs always convert.
        """
        token = (list, tuple(raw)) if type(raw) is list else (
            (type(raw), raw) if isinstance(raw, (str, int, float, tuple, type(None))) else None)
        if token is not None:
            try:
                if self._inputs.get(key) == token:
                    return False
            except (TypeError, ValueError):  # elements that do not compare to a bool, such as arrays
                token = None
        changed = self._set(key, convert(raw), groups, log)
        self._inputs[key] = token
        return changed

    def _set(self, key, value, groups, log):
        """Store a value; return whether it changed."""
        if self._state.get(key, object()) == value:
            return False
        self._state[key] = value
        self._dirty.update(groups)
        if log or (log is None and self.autoLog):
            logging.exp(f"Set {self.name} {key}={value}", obj=self)
        return True

    def _get(self, key):
        return self._state[key]

    @staticmethod
    def _default(value, key):
        return _DEFAULTS[key] if _blank(value) else value


class SceneStim(MinimalStim, _Settings):
    """A filly scene rendered into a texture and drawn in a PsychoPy window.

    `SceneModel` objects add models to the scene. The texture is placed like a
    `visual.ImageStim`: `pos`, `size`, `units`, `ori`, and `opacity` move or fade it and need no
    new render. The other parameters describe the camera, the lights, and the rendering. Each has
    a `set<Name>()` method, named as the Builder parameter. `draw()` renders a new frame only
    after a change to the scene or to one of its models.

    Arguments that are None take their default. Colors are PsychoPy colors in `colorSpace`.

    Parameters
    ----------
    win : psychopy.visual.Window
        Window to draw in. It must use the pyglet backend and the 'avg' blend mode.
    pos, size, units, ori, opacity
        Placement of the drawn texture, as for `visual.ImageStim`. `size` is required.
    resolution : sequence of 2 int, optional
        Render-target size in pixels. Default: the initial `size` in window pixels, times
        `renderScale`.
    renderScale : float
        Factor for the default render-target size, in (0, 2]. Default 1. Below 1 renders fewer
        pixels and stretches the image bilinearly, which blurs edges and fine detail. Not used
        with `resolution`.
    projection : {'perspective', 'orthographic'}
    fov : float
        Vertical field of view in degrees, for the perspective projection. Default 30.
    viewHeight : float, optional
        Height of the orthographic view in scene units. Default: from the framing.
    camPos : sequence of 3 float, optional
        Camera position in scene units. Default: framing. The camera is placed on the +Z axis
        and looks toward -Z at the origin, at the distance where the framing box fills `fill` of
        the narrower image axis. The framing box encloses every model of the scene in its rest
        pose, placed as when it was loaded. Later changes of pose, visibility, or animation do
        not move the camera; loading a model does.
    lookAt : sequence of 3 float
        Point that the camera looks at, with `camPos`. Default (0, 0, 0).
    near, far : float, optional
        Clipping planes. Default: planes that enclose the bounding spheres of the models at
        their current poses.
    fill : float
        Fraction of the view that the framing gives the framing box, in (0, 1]. Default 0.9.
    exposure : float, optional
        Camera exposure as EV100. Lower values give a brighter image. Default: filly's (15).
    light : bool
        Add a directional light. Default True.
    lightDir, lightIntensity, lightColor
        Direction (from the light), illuminance in lux, and color of that light.
        Defaults: (-1, -1, -2), 100000, white.
    environment : {'uniform', 'none', 'file'}
        Image-based lighting: even light from every direction, none, or `envFile`.
    envFile : str, optional
        A 2:1 panorama (Radiance HDR, PNG, or JPEG), or a KTX cubemap made by Filament's cmgen.
    envIntensity, envRotation : float
        Environment intensity in lux (default 20000) and rotation about Y in degrees.
    envVisible : bool
        Draw the environment instead of the background. Default False.
    backgroundColor : color, optional
        Background of the rendered image. Default: transparent, so that the models cover only
        their own pixels.
    toneMapping : str
        A filly tone mapper (Scene.tone_mapping). Default 'linear'.
    antialiasing : {'none', 'fxaa'}
        Default 'fxaa'.
    msaa : {1, 2, 4, 8}
    shadows : bool
        Shadows from the directional light. Default False.
    refraction : bool
        Screen-space refraction for glass materials. Default False.
    precompiledShaders : bool
        filly's `precompiled_shaders` renderer option. The first scene in a window sets it.
    modelCacheMiB : float or str, optional
        Memory limit of the window's model cache in MiB (see `SceneModel.setModel()`). None:
        `MODEL_CACHE_MAX_BYTES`. 0 turns the cache off; 'unlimited' removes the limit. The first
        scene in a window that sets it decides.
    depth : float
        Draw order for autoDraw, as for other PsychoPy stimuli.
    """

    def __init__(self, win, *, pos=(0, 0), size, units=None, ori=0.0, opacity=None,
                 resolution=None, renderScale=1.0, projection="perspective", fov=None, viewHeight=None,
                 camPos=None, lookAt=None, near=None, far=None, fill=None, exposure=None,
                 light=True, lightDir=None, lightIntensity=None, lightColor=None,
                 environment="uniform", envFile=None, envIntensity=None, envRotation=None,
                 envVisible=False, backgroundColor=None, colorSpace="rgb",
                 toneMapping="linear", antialiasing="fxaa", msaa=1, shadows=False,
                 refraction=False, precompiledShaders=False, modelCacheMiB=None, name=None, depth=0,
                 autoLog=None):
        from filly.integrations.psychopy import SharedTarget

        super().__init__(name=name, autoLog=False)
        self.__dict__["win"] = win
        self.depth = depth
        self._closed = True
        self.colorSpace = colorSpace or "rgb"
        if projection not in ("perspective", "orthographic"):
            raise ValueError(f"projection must be 'perspective' or 'orthographic', not {projection!r}")
        if environment not in ("uniform", "none", "file"):
            raise ValueError(f"environment must be 'uniform', 'none', or 'file', not {environment!r}")
        if environment == "file" and _blank(envFile):
            raise ValueError("environment='file' needs envFile")
        units = units or win.units
        if _blank(resolution):
            scale = _number(1.0 if _blank(renderScale) else renderScale, "renderScale", 0, 2, low_open=True)
            resolution = np.abs(Size(size, units=units, win=win).pix) * scale
        width, height = (int(min(max(round(float(v)), 1), 8192)) for v in _vector(resolution, "resolution", 2))
        self._aspect = width / height
        self._projection = projection
        self.models = []
        self._camera_model = None  # the model whose file camera the scene uses, if any
        self._frame_box = _EMPTY_BOX

        self._host = host = _host_for(win, bool(precompiledShaders))
        renderer = host.renderer
        limit = _cache_limit(modelCacheMiB)
        if limit is not None:
            if host.model_cache.limit is None:
                host.model_cache.limit = limit
            elif host.model_cache.limit != limit:
                # One cache per window: the first scene that sets the limit decides.
                logging.warning(f"modelCacheMiB={modelCacheMiB} ignored: the window's model cache "
                                f"already has a limit of {host.model_cache.limit / 2**20} MiB")
        self._refraction = bool(refraction)
        self._scene = scene = renderer.create_scene()
        try:
            scene.refraction = bool(refraction)  # before loading: glass needs it at load
            scene.tone_mapping = toneMapping or "linear"
            scene.antialiasing = antialiasing or "none"
            scene.msaa = int(msaa or 1)
            scene.shadows = bool(shadows)
            self.camera = scene.create_camera()
            scene.camera = self.camera
            self.light = None
            if light:
                self.light = scene.add_directional_light(direction=_DEFAULTS["lightDir"])
                self.light.casts_shadows = bool(shadows)
            if environment == "uniform":
                scene.set_environment(_uniform_panorama())
            elif environment == "file":
                path = Path(str(envFile))
                if path.suffix.lower() == ".ktx":
                    scene.load_environment_ktx(str(path))
                else:
                    scene.load_environment(str(path))
            self._has_environment = environment != "none"
            scene.environment_visible = bool(envVisible)
            # The visible environment is opaque and covers the background.
            self._opaque_environment = self._has_environment and bool(envVisible)
            self._target = SharedTarget(renderer, win, width, height)
        except BaseException:
            scene.close()
            raise
        host.stims.append(self)
        self._closed = False

        self._image = self._target.as_psychopy_texture(win, size=size, pos=pos, units=units)
        self._image.ori = ori
        if opacity is not None:
            self._image.opacity = opacity

        self._init_settings()
        self._camera_position = None  # from the framing, see _apply_camera()
        self._planes = None  # the clipping planes that the camera has
        self.setFov(fov, log=False)
        self.setViewHeight(viewHeight, log=False)
        self.setCamPos(camPos, log=False)
        self.setLookAt(lookAt, log=False)
        self.setNear(near, log=False)
        self.setFar(far, log=False)
        self.setFill(fill, log=False)
        self.setExposure(exposure, log=False)
        self.setLightDir(lightDir, log=False)
        self.setLightIntensity(lightIntensity, log=False)
        self.setLightColor(lightColor, log=False)
        self.setEnvIntensity(envIntensity, log=False)
        self.setEnvRotation(envRotation, log=False)
        self.setBackgroundColor(backgroundColor, log=False)
        self.autoLog = autoLog

    @property
    def closed(self):
        return self._closed

    def _check_open(self):
        if self._closed:
            raise RuntimeError(f"{self.name} is closed")

    # --- models ------------------------------------------------------------------------------

    def _models_changed(self):
        """Fit the framing box to the models again, after a model loaded or closed."""
        boxes = [model._frame_box for model in self.models]
        if boxes:
            self._frame_box = (tuple(np.min([box[0] for box in boxes], axis=0)),
                               tuple(np.max([box[1] for box in boxes], axis=0)))
        else:
            self._frame_box = _EMPTY_BOX
        self._dirty.add("camera")

    def _use_camera(self, model, camera):
        """Render through `camera`, a camera in `model`'s file; None: the scene's own camera."""
        if camera is None:
            if self._camera_model is model:
                self._camera_model = None
                self._scene.camera = self.camera
                self._dirty.update(("camera", "exposure"))
            return
        if self._camera_model not in (None, model):
            raise ValueError(f"{self.name}: {self._camera_model.name} already provides the scene's "
                             f"camera from its file; only one model can")
        self._camera_model = model
        self._scene.camera = camera
        self._dirty.update(("camera", "exposure"))

    # --- camera ------------------------------------------------------------------------------

    # The camera's position depends on the framing; the automatic clipping planes ("clip") also
    # depend on the models' poses, which can change in every frame.
    def setFov(self, fov, log=None):
        """Set the vertical field of view of the perspective projection in degrees."""
        self._update("fov", fov, lambda v: _number(self._default(v, "fov"), "fov", 0, 180, low_open=True),
                     ("camera",), log)

    def setViewHeight(self, viewHeight, log=None):
        """Set the orthographic view height in scene units. None: from the framing."""
        self._update("viewHeight", viewHeight,
                     lambda v: None if _blank(v) else _number(v, "viewHeight", 0, low_open=True),
                     ("camera",), log)

    def setCamPos(self, camPos, log=None):
        """Set the camera position in scene units. None: framing."""
        self._update("camPos", camPos, lambda v: None if _blank(v) else _vector(v, "camPos"),
                     ("camera",), log)

    def setLookAt(self, lookAt, log=None):
        """Set the point that the camera looks at, with a camera position."""
        self._update("lookAt", lookAt, lambda v: _vector(self._default(v, "lookAt"), "lookAt"),
                     ("camera",), log)

    def setNear(self, near, log=None):
        """Set the near clipping plane. None: automatic."""
        self._update("near", near, lambda v: None if _blank(v) else _number(v, "near", 0, low_open=True),
                     ("clip",), log)

    def setFar(self, far, log=None):
        """Set the far clipping plane. None: automatic."""
        self._update("far", far, lambda v: None if _blank(v) else _number(v, "far", 0, low_open=True),
                     ("clip",), log)

    def setFill(self, fill, log=None):
        """Set the fraction of the view that the framing gives the framing box."""
        self._update("fill", fill, lambda v: _number(self._default(v, "fill"), "fill", 0, 1, low_open=True),
                     ("camera",), log)

    def setExposure(self, exposure, log=None):
        """Set the camera exposure as EV100. None: filly's default."""
        self._update("exposure", exposure, lambda v: None if _blank(v) else _number(v, "exposure", -10, 24),
                     ("exposure",), log)

    # --- lighting and appearance -------------------------------------------------------------

    def setLightDir(self, lightDir, log=None):
        """Set the direction of the directional light, from the light toward the scene."""
        def convert(v):
            value = _vector(self._default(v, "lightDir"), "lightDir")
            if not any(value):
                raise ValueError("lightDir must not be zero")
            return value
        self._update("lightDir", lightDir, convert, ("light",), log)

    def setLightIntensity(self, lightIntensity, log=None):
        """Set the illuminance of the directional light in lux."""
        self._update("lightIntensity", lightIntensity,
                     lambda v: _number(self._default(v, "lightIntensity"), "lightIntensity", 0),
                     ("light",), log)

    def setLightColor(self, lightColor, log=None):
        """Set the color of the directional light, in `colorSpace`."""
        self._update("lightColor", lightColor,
                     lambda v: _DEFAULTS["lightColor"] if _blank(v) else _linear_color(v, self.colorSpace, "lightColor"),
                     ("light",), log)

    def setEnvIntensity(self, envIntensity, log=None):
        """Set the environment intensity in lux."""
        self._update("envIntensity", envIntensity,
                     lambda v: _number(self._default(v, "envIntensity"), "envIntensity", 0),
                     ("environment",), log)

    def setEnvRotation(self, envRotation, log=None):
        """Set the environment rotation about Y in degrees."""
        self._update("envRotation", envRotation,
                     lambda v: _number(self._default(v, "envRotation"), "envRotation"),
                     ("environment",), log)

    def setBackgroundColor(self, backgroundColor, log=None):
        """Set the background color, in `colorSpace`. None: transparent."""
        self._update("backgroundColor", backgroundColor,
                     lambda v: None if _blank(v) else _linear_color(v, self.colorSpace, "backgroundColor"),
                     ("background",), log)

    def invalidate(self):
        """Render again at the next draw. Call this after changing the filly scene, camera,
        light, or a model directly: the stimulus tracks only changes made through setters."""
        self._dirty.add("render")

    # Placement changes move the drawn texture only; they need no new render.
    def setPos(self, pos, log=None):
        self._image.setPos(pos, log=False)

    def setSize(self, size, log=None):
        self._image.setSize(size, log=False)

    def setOri(self, ori, log=None):
        self._image.setOri(ori, log=False)

    def setOpacity(self, opacity, log=None):
        self._image.setOpacity(opacity, log=False)

    @property
    def pos(self):
        return self._image.pos

    @property
    def size(self):
        return self._image.size

    # --- applying state ----------------------------------------------------------------------

    def _apply_camera(self):
        """Place the scene's camera and set its planes. Without camPos, the position depends on
        the framing box, fill, fov, and aspect only, so pose changes need only _apply_clip()."""
        get = self._get
        if self._camera_model is not None:
            return
        camera = self.camera
        orthographic = self._projection == "orthographic"
        # frame() places the camera for the default position; the planes are placeholders.
        if orthographic:
            camera.set_orthographic(height=1.0, near=0.1, far=1.0)
        else:
            camera.set_perspective(fov_y=get("fov"), near=0.1, far=1.0)
        camera.frame(self._frame_box, fill=get("fill"), direction=(0, 0, -1), aspect=self._aspect)
        position = np.asarray(camera.position, dtype=float)
        if get("camPos") is not None:
            position, target = np.asarray(get("camPos")), np.asarray(get("lookAt"))
            if np.allclose(position, target):
                raise ValueError(f"{self.name}: camPos and lookAt are the same point")
            camera.position = tuple(position)
            # look_at needs an up vector that is not parallel to the view direction.
            direction = (target - position) / np.linalg.norm(target - position)
            camera.look_at(tuple(target), up=(0, 0, -1) if abs(direction[1]) > 0.999 else (0, 1, 0))
        self._camera_position = tuple(position.tolist())
        if orthographic:
            # The framing height: the framing box's bounding sphere spans `fill` of the narrower
            # axis.
            height = get("viewHeight")
            if height is None:
                box = np.asarray(self._frame_box, dtype=float)
                height = float(np.linalg.norm(box[1] - box[0])) / get("fill") / min(1.0, self._aspect)
            self._view_height = height
        self._planes = None  # frame() replaced them
        self._apply_clip()

    def _apply_clip(self):
        """Set the clipping planes. The default planes enclose the models' bounding spheres at
        their current poses."""
        get = self._get
        if self._camera_model is not None:
            return
        spheres = [model._sphere() for model in self.models]
        if spheres:
            center, radius = _merge_spheres(spheres)
        else:
            center, radius = tuple((a + b) / 2 for a, b in zip(*self._frame_box)), 1.0
        distance = math.dist(center, self._camera_position)
        near = get("near") if get("near") is not None else max(distance - 1.05 * radius, 0.01 * radius)
        far = get("far") if get("far") is not None else distance + 1.05 * radius
        if far <= near:
            raise ValueError(f"{self.name}: far ({far}) must be greater than near ({near})")
        # A model that turns about its center keeps its sphere, and the planes stay.
        if (near, far) == self._planes:
            return
        self._planes = (near, far)
        if self._projection == "orthographic":
            self.camera.set_orthographic(height=self._view_height, near=near, far=far)
        else:
            self.camera.set_perspective(fov_y=get("fov"), near=near, far=far)

    def _apply(self):
        dirty, get = self._dirty, self._get
        if "camera" in dirty:
            self._apply_camera()
        elif "clip" in dirty:
            self._apply_clip()
        if "exposure" in dirty and get("exposure") is not None:
            self._scene.camera.exposure = get("exposure")
        if "light" in dirty and self.light is not None:
            self.light.direction = get("lightDir")
            self.light.intensity = get("lightIntensity")
            self.light.color = get("lightColor")[:3]
        if "environment" in dirty and self._has_environment:
            self._scene.environment_intensity = get("envIntensity")
            self._scene.environment_rotation = get("envRotation")
        if "background" in dirty:
            background = get("backgroundColor")
            # Transparent output composites the models over the window and the stimuli drawn
            # before them, as an ImageStim with alpha does. It costs Filament an extra pass, so it
            # is on only where the image can have alpha below one.
            self._scene.transparent = not self._opaque_environment and (background is None or background[3] < 1)
            self._scene.background = (0, 0, 0, 0) if background is None else background
        dirty.clear()

    # --- drawing -----------------------------------------------------------------------------

    def _needs_render(self):
        return bool(self._dirty) or any(model._dirty for model in self.models)

    def _render(self):
        for model in self.models:
            if model._dirty:
                model._apply()
        if self._dirty:
            self._apply()
        self._host.renderer.render(self._scene, self._target)

    def draw(self, win=None):
        """Render if the scene or a model changed since the last render, then draw the texture."""
        self._check_open()
        if self._needs_render():
            self._render()
        self._image.draw(win)

    def close(self):
        """Release the models, the target, and the scene. Repeated calls are valid."""
        if self._closed:
            return
        self._closed = True
        if self in self.win._toDraw:
            self.autoDraw = False
        try:
            for model in list(self.models):
                model.close()
            self._target.close()
            self._scene.close()
        finally:
            self._image = None
            if self in self._host.stims:
                self._host.stims.remove(self)


class SceneModel(_Settings):
    """A glTF model in a `SceneStim`.

    The model is hidden until `setAutoDraw(True)`; Builder calls it when the component starts,
    and `setAutoDraw(False)` when it stops. Its scene draws it. Each parameter has a
    `set<Name>()` method, named as the Builder parameter.

    Parameters
    ----------
    scene : SceneStim
        The scene to add the model to.
    model : str or pathlib.Path or None
        Path of a .glb or .gltf file. 'default.glb' is filly's sample model, unless the working
        directory has a file of that name. None: no model until `setModel()`. Builder uses
        None when the model changes on every repeat. Without a model, the names of `variant`,
        `material`, and `animation` are checked when the model renders first.
    rotation : sequence of 3 float
        Rotation in degrees about X, then Y, then Z. Default (0, 0, 0).
    modelPos : sequence of 3 float
        Position in scene units, applied after the rotation. Default (0, 0, 0).
    modelScale : float or sequence of 3 float
        Scale factors. Default 1.
    center : bool
        Move the center of the model's bounding box to `modelPos`, so that the model rotates
        about its center. Default True. With False, the model rotates about its own origin.
    fileCamera : str or int, optional
        Name or glTF node index of a camera in the model file. The scene renders through it,
        and the scene's camera parameters, except exposure, do not apply. Only one model of a
        scene can name a file camera.
    fileLights : bool
        Keep the punctual lights in the model file. Default True.
    variant : str or int, optional
        Material variant to apply.
    material : str, optional
        Material that `baseColor` changes. Default: every material of the model.
    baseColor : color, optional
        Base color factor that replaces the material's, in `colorSpace`. Its alpha stays.
    animation : str or int, optional
        Animation clip to show. `animTime` selects the pose.
    animTime : float
        Time in the clip in seconds. Default 0. Use `t` in Builder to play the clip.
    animLoop : bool
        Wrap times beyond the clip duration. Default True. With False, the last pose holds.
    """

    def __init__(self, scene, model, *, rotation=None, modelPos=None, modelScale=None,
                 center=True, fileCamera=None, fileLights=True, variant=None, material=None,
                 baseColor=None, animation=None, animTime=None, animLoop=True,
                 colorSpace="rgb", name=None, autoLog=None):
        scene._check_open()
        self.scene = scene
        self.name = name or "model"
        # Builder's routine code resets the status of components that have one.
        self.status = None
        self.autoLog = False
        self.colorSpace = colorSpace or "rgb"
        self._closed = True
        self._center_model = bool(center)
        self._file_camera = None if _blank(fileCamera) else fileCamera
        self._file_lights = bool(fileLights)
        self._anim_loop = bool(animLoop)
        self.model = None
        self._matrix = self._sphere_cache = None  # for the current pose, see _model_matrix()
        self._init_settings()
        # The pose comes first: the framing box uses the pose at load time.
        self.setRotation(rotation, log=False)
        self.setModelPos(modelPos, log=False)
        self.setModelScale(modelScale, log=False)
        self._state["autoDraw"] = False
        # What a loaded file provides; without a file, the model is not part of the scene.
        self._materials, self._clips, self._variants = {}, [], []
        self._animated_colors, self._handles, self._colored = set(), {}, frozenset()
        if not _blank(model):
            self._attach(model)
            scene.models.append(self)
            scene._models_changed()
            self._state["model"] = str(model)
        self._closed = False
        self.setVariant(variant, log=False)
        self.setMaterial(material, log=False)
        self.setBaseColor(baseColor, log=False)
        self.setAnimation(animation, log=False)
        self.setAnimTime(animTime, log=False)
        self._dirty.update(("model", "visible"))
        if self.model is not None:
            self._warm_up(apply=True)
        self.autoLog = autoLog

    def _warm_up(self, apply):
        """Render once with the model shown, and wait until the GPU has done all queued work.

        Shader compilation and texture uploads then happen here and not in the first frame that
        shows the model: Filament compiles only what it draws, and its driver thread uploads
        textures after the load returns. The next draw renders again with the real visibility.
        With `apply` False, the model's pending settings do not apply (see setModel()).
        """
        scene = self.scene
        renderer = scene._host.renderer
        if apply:
            self._apply()
        else:
            # Only the pose and the framing, which cannot fail: Filament culls a model that the
            # stale camera does not see, and would then compile nothing for it.
            self.model.transform = self._model_matrix()
            scene._apply_camera()
        self.model.visible = True
        try:
            if apply:
                scene._render()
            else:
                renderer.render(scene._scene, scene._target)
            if not scene._scene.transparent and not scene._host.transparent_ready:
                # A blank background later switches to transparent output, whose first render
                # compiles Filament's pass for it, once per renderer: 3 to 6 ms more in the
                # first such frame on the test laptop.
                scene._scene.transparent = True
                try:
                    renderer.render(scene._scene, scene._target)
                finally:
                    scene._scene.transparent = False
            scene._host.transparent_ready = True
        finally:
            self.model.visible = self._state["autoDraw"]
            # The target now shows the model; the scene's next draw must render the real image.
            scene._dirty.add("render")
        renderer.finish()

    def _attach(self, model, cached=False):
        """Load a model file in place of the current model, if any; with `cached`, through the
        window's model cache.

        Everything that depends on the file is derived again: the framing box, the materials and
        their loaded base colors, the clip names, and the file camera. The old model is closed
        only after the new one has loaded, so a failed load keeps the old one.
        """
        if str(model) == DEFAULT_MODEL and not Path(model).is_file():
            from filly.samples import SUZANNE
            model = SUZANNE
        scene = self.scene
        loaded = (scene._host.model_cache.instance(model, scene._scene, scene._refraction) if cached
                  else scene._scene.load(str(model)))
        try:
            bounds = np.asarray(loaded.bounds, dtype=float)
            if not np.all(np.isfinite(bounds)) or np.any(bounds[0] >= bounds[1]):
                raise ValueError(f"{model} has no geometry with finite, nonzero bounds")
            camera = None
            if self._file_camera is not None:
                camera = loaded.camera(_key(self._file_camera, loaded.node_names))
            self.scene._use_camera(self, camera)
            materials = {name: tuple(loaded.material(name).base_color)
                         for name in loaded.material_names if name is not None}
        except BaseException:
            loaded.close()
            raise
        if not self._file_lights:
            for imported in loaded.lights:
                imported.close()
        old, self.model = self.model, loaded
        if old is not None:
            old.close()
        self._bounds = bounds
        self._bounds_center = bounds.mean(axis=0)
        self._radius = float(np.linalg.norm(bounds[1] - bounds[0]) / 2)
        self._pose_changed()  # the center moved
        self._materials = materials
        self._handles = {}  # material name: filly Material, made at first use
        self._colored = frozenset()  # the materials that have the base color setting
        self._animated_colors = _animated_base_colors(loaded)
        self._clips = [clip.name for clip in loaded.animations]
        self._variants = loaded.variants
        # These inputs are names or indices that only the old model's names resolved.
        for key in ("variant", "material", "animation"):
            self._inputs.pop(key, None)
        # Framing box: the rest-pose bounds, placed by the model's transform at load time.
        matrix = self._model_matrix()
        corners = _box_corners(bounds) @ matrix[:3, :3].T + matrix[:3, 3]
        self._frame_box = (tuple(corners.min(axis=0)), tuple(corners.max(axis=0)))
        self.model.visible = self._state["autoDraw"]

    @property
    def closed(self):
        return self._closed

    def _check_open(self):
        if self._closed:
            raise RuntimeError(f"{self.name} is closed")

    def _pose_changed(self):
        self._matrix = self._sphere_cache = None
        # The automatic clipping planes depend on every model's pose.
        self.scene._dirty.add("clip")

    def setModel(self, model, log=None):
        """Show another model file. Loads it now; the next draw renders it.

        The settings stay: variant, material, base color, animation, and pose apply to the new
        model at the next draw, and must exist in it. The scene fits its framing box again.
        The call returns after the shaders are compiled and the textures are on the GPU, so the
        first frame that shows the model does not wait for them. Load in a static period
        (Builder: "set during") or at the routine start to keep this out of the trial's frames.
        Handles to the old model are closed. A file that a scene of the window showed before is
        a clone of its first load, which is much faster for large files: see
        MODEL_CACHE_MAX_BYTES.
        """
        self._check_open()
        if self._state.get("model") == str(model):
            return
        self._attach(model, cached=True)
        self._set("model", str(model), ("model", "variant", "animation", "material", "visible"), log)
        if self not in self.scene.models:
            self.scene.models.append(self)
        self.scene._models_changed()
        # Builder sets the trial's other parameters after this one, so the warm-up must not apply
        # the previous trial's clip or variant: the new model may not have them.
        self._warm_up(apply=False)

    def setAutoDraw(self, value, log=None):
        """Show (True) or hide (False) the model in its scene."""
        self._check_open()
        self._set("autoDraw", bool(value), ("visible",), log)

    @property
    def autoDraw(self):
        return self._state["autoDraw"]

    # Pose. The scene's camera depends on it only through the automatic clipping planes.
    def setRotation(self, rotation, log=None):
        """Set the rotation in degrees about X, then Y, then Z."""
        if self._update("rotation", rotation, lambda v: _vector(self._default(v, "rotation"), "rotation"),
                        ("model",), log):
            self._pose_changed()

    def setModelPos(self, modelPos, log=None):
        """Set the position in scene units."""
        if self._update("modelPos", modelPos, lambda v: _vector(self._default(v, "modelPos"), "modelPos"),
                        ("model",), log):
            self._pose_changed()

    def setModelScale(self, modelScale, log=None):
        """Set the scale: one factor, or one for each axis."""
        if self._update("modelScale", modelScale, lambda v: _scale(self._default(v, "modelScale")),
                        ("model",), log):
            self._pose_changed()

    # Appearance.
    def setVariant(self, variant, log=None):
        """Apply a material variant by name or index. None keeps the current materials."""
        # A variant replaces material instances, so a base color must be written again.
        self._update("variant", variant, lambda v: None if _blank(v) else _key(v, self._variants),
                     ("variant", "material"), log)

    def setMaterial(self, material, log=None):
        """Select the material that `baseColor` changes. None: every material."""
        def convert(v):
            value = None if _blank(v) else str(v)
            # Without a model, filly checks the name when the model renders.
            if value is not None and self.model is not None and value not in self._materials:
                raise ValueError(f"{self.name}: no material named {value!r}; "
                                 f"the model has {sorted(self._materials)}")
            return value
        self._update("material", material, convert, ("material",), log)

    def setBaseColor(self, baseColor, log=None):
        """Set the base color of the selected materials, in `colorSpace`. None: as loaded."""
        self._update("baseColor", baseColor,
                     lambda v: None if _blank(v) else _linear_color(v, self.colorSpace, "baseColor")[:3],
                     ("material",), log)

    # Animation. Applying a clip restores the base colors that clips animate, so the base color
    # setting is written again after it, for those materials only.
    def _animation_groups(self):
        return ("animation", "material") if self._animated_colors else ("animation",)

    def setAnimation(self, animation, log=None):
        """Select an animation clip by name or index. None: the authored pose."""
        self._update("animation", animation, lambda v: None if _blank(v) else _key(v, self._clips),
                     self._animation_groups(), log)

    def setAnimTime(self, animTime, log=None):
        """Set the time in the animation clip in seconds."""
        # Without a clip, the time changes nothing; do not render again for it.
        groups = self._animation_groups() if self._state.get("animation") is not None else ()
        self._update("animTime", animTime, lambda v: _number(self._default(v, "animTime"), "animTime", 0),
                     groups, log)

    @property
    def rotation(self):
        return self._state["rotation"]

    # --- applying state ----------------------------------------------------------------------

    def _model_matrix(self):
        """The model's transform. Cached until the pose changes: a pose set in every frame needs
        it twice per frame, for the transform and for the clipping planes. Do not modify it."""
        if self._matrix is None:
            get = self._get
            matrix = np.eye(4)
            matrix[:3, :3] = _euler_matrix(get("rotation"))
            matrix[:3, :3] *= get("modelScale")
            matrix[:3, 3] = get("modelPos")
            if self._center_model and hasattr(self, "_bounds_center"):
                matrix[:3, 3] -= matrix[:3, :3] @ self._bounds_center
            self._matrix = matrix
        return self._matrix

    def _sphere(self):
        """The bounding sphere at the current pose, for the scene's clipping planes."""
        if self._sphere_cache is None:
            matrix = self._model_matrix()
            center = matrix[:3, :3] @ self._bounds_center + matrix[:3, 3]
            self._sphere_cache = (tuple(center.tolist()),
                                  self._radius * max(map(abs, self._get("modelScale"))))
        return self._sphere_cache

    def _material(self, name):
        handle = self._handles.get(name)
        if handle is None:
            handle = self._handles[name] = self.model.material(name)
        return handle

    def _color_targets(self):
        """The materials that the base color setting applies to."""
        get = self._get
        if get("baseColor") is None:
            return frozenset()
        return frozenset((get("material"),) if get("material") is not None else self._materials)

    def _apply_colors(self, targets):
        """Write the base color setting to `targets`; restore the materials that it left."""
        color = self._get("baseColor")
        for name in self._colored - targets:
            # Animation has already restored the animated ones (see _apply()).
            if name not in self._animated_colors:
                self._material(name).base_color = self._materials[name]
        for name in targets:
            material = self._material(name)
            # An animated alpha is the clip's; any other is the loaded one.
            alpha = material.base_color[3] if name in self._animated_colors else self._materials[name][3]
            material.base_color = (*color, alpha)
        self._colored = targets

    def _apply(self):
        dirty, get, model = self._dirty, self._get, self.model
        if "variant" in dirty and get("variant") is not None:
            model.apply_variant(get("variant"))
        targets = self._color_targets() if "material" in dirty else None
        # Applying or resetting a clip also removes a base color that no longer applies from the
        # materials whose base color a clip animates.
        if "animation" in dirty or (targets is not None and (self._colored - targets) & self._animated_colors):
            if get("animation") is None:
                model.reset_animation()
            else:
                model.apply_animation(get("animation"), get("animTime"), loop=self._anim_loop)
        if targets is not None:
            self._apply_colors(targets)
        if "model" in dirty:
            model.transform = self._model_matrix()
        if "visible" in dirty:
            model.visible = get("autoDraw")
        dirty.clear()

    def close(self):
        """Remove the model from its scene. Repeated calls are valid."""
        if self._closed:
            return
        self._closed = True
        scene = self.scene
        try:
            if scene._camera_model is self:
                scene._use_camera(self, None)
            if not scene._closed and self.model is not None:
                self.model.close()
        finally:
            if self in scene.models:
                scene.models.remove(self)
            if not scene._closed:
                scene._models_changed()
