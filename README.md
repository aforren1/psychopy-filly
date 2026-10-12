# psychopy-filly

A PsychoPy plugin that adds the **3D Scene** and **3D Model** components to Builder. They show
glTF models that [filly](https://github.com/aforren1/filly) renders. They work in local experiments (PsychoPy) and in
online experiments (PsychoJS):

- Locally, filly renders into an OpenGL texture that the PsychoPy window shares. PsychoPy draws
  the texture like an image stimulus.
- Online, filly's WebAssembly build renders into a WebGL texture that PsychoJS owns, in
  PsychoJS's own WebGL2 context. PsychoJS draws the texture like an image stimulus.

Neither path copies pixels through the CPU. PsychoPy and PsychoJS keep control of the frame.

Status: phase 1 (local) and the online component of [PLAN.md](PLAN.md) are done. The plugin is
not released. Online experiments ran in Chrome, Edge, and Firefox on one Windows laptop; they
were not run on Pavlovia.

## Requirements

Local experiments:

- Windows or Linux. filly does not support macOS.
- PsychoPy 2024.2 or later, with the pyglet window backend and the "average" blend mode.
  Tested with PsychoPy 2024.2.4 (Python 3.10) and 2026.2.4 (Python 3.11). Earlier standalone
  installs ship Python 3.8 or earlier, and filly needs Python 3.10 or later. The component
  also loads and compiles in the PsychoPy 2026.1.2 app.
- filly 0.2 or later, installed in the Python environment that runs the experiment. filly 0.2
  is not released: install it from source.

Online experiments:

- A browser with WebGL2. PsychoJS uses WebGL1 on Android and other non-Apple mobile devices,
  and there the component stops the experiment with an error message.
- No special server headers. The page does not have to be cross-origin isolated.

## Install for development

```powershell
uv pip install --python <env>\Scripts\python.exe -e . --no-deps
```

The package requires `psychopy>=2024.2`. The standalone app registers the `psychopy`
distribution, so installing the plugin there adds nothing else. An environment with only
`psychopy-lib` gets `psychopy` installed next to it; use `--no-deps` there.
`psychopy_filly.runtime.TESTED_PSYCHOPY` lists the tested versions; other versions log a
warning.

## Use the components

The plugin adds two components to **Stimuli**:

- **3D Scene** shows the rendered image. It has the camera, the lights, the environment, the
  background, and the rendering settings. Place it like an image, with **Position**, **Size**,
  and **Spatial units**.
- **3D Model** adds one glTF model to a scene. It has the model file, its pose, its materials,
  and its animation. The model is visible in the scene from the component's start to its stop.

To show a model:

1. Add a **3D Scene** component. Its default name is `scene`.
2. Below it in the same routine, or in a later routine, add a **3D Model** component. Set its
   **Scene** to the name of the 3D Scene component.
3. Set **Model file** to a `.glb` file. A `.gltf` file also works, but PsychoPy does not know
   its external `.bin` and image files: keep them in the experiment folder. The default,
   `default.glb`, is filly's sample model: Suzanne, in blue metal (public domain). A file named
   `default.glb` in the experiment folder replaces it.
4. Set **Rotation [x,y,z]** in degrees. To rotate the model over time, type an expression such
   as `(0, 90*t, 0)` and set its update mode to **set every frame**.

For more models in the same image, add more 3D Model components with the same **Scene**. They
hide each other where they overlap, and with **Shadows** on, they cast shadows on each other.
Place them apart with **Model position**. Two scenes are two separate images: their models do
not interact.

Without other settings, the camera looks along -Z and frames all models of the scene, as placed
when they loaded, so that they fill 90% of the narrower image axis in a 30-degree perspective
view. Later changes of pose, visibility, or animation do not move the camera. Set **Camera
position** to place the camera yourself. One directional light and even ambient light
illuminate the models. The background is transparent, so the models cover only their own
pixels.

To find the names of animation clips, material variants, materials, and cameras in a model,
run `python -m psychopy_filly.gltf_info model.glb`. It also lists lights, morph targets, skins
with their bones, and the node tree. If **Animation clip**, **Material variant**, **Material
name**, or **Camera from file** has a name that the model does not have, the compile logs a
warning with the names that the model has, and the experiment stops with an error that lists
them.

The compile stops with an error if a 3D Model's **Scene** is not the name of a 3D Scene
component, if the scene comes after the model (a later routine, or below it in the same
routine), or if two models of one scene set **Camera from file**.

Both of Builder's average blend modes work, with and without a framebuffer object (FBO). If
the window shows no stimuli at all, also without the 3D scene, set **Blend mode** to
**average (no FBO)** in the experiment settings, on the **Screen** tab. Earlier tests on one
laptop suggested that FBO windows show nothing; that came from reading the front buffer back,
which returns only the background there, while the screen shows the stimuli.

### Change the model per trial

To show a different model in each trial, put the file names in a column of the conditions
file, for example `modelFile`. In the 3D Model component, set **Model file** to `$modelFile`
and its update mode to **set every repeat**.

- The component has no model until the first trial sets the file. Nothing loads at the start
  of the experiment.
- Each change loads the new file when the routine starts. The other settings stay and apply
  to the new model, so the trial's clip, variant, and material names must exist in it.
- The scene frames its models again when a model loads, unless **Camera position** is set.
- The load is complete before the routine's first frame: the shaders are compiled and the
  textures are on the GPU. Thus the first frame of the trial does not wait for them. On the
  test laptop, without this wait, the first frames after a change took 40 to 400 ms locally
  and 33 to 250 ms in Chrome.
- The first load of a file takes time: tens to hundreds of milliseconds, and more for the first
  file that uses a material type. To keep this out of the routine's start, add a **Static**
  component (ISI) before the model and set the update mode to **set during: trial.ISI**.
  Online, the scene is not drawn until the model has loaded. If the static period is too short,
  the scene is missing at the start of the trial instead of showing the previous model.

#### Model cache

Each window keeps a copy of each file that a change loaded. All 3D Scenes of the window
share these copies. A file that a scene shows again, as in conditions that alternate models, is
then a new model of its copy: no new load and no texture upload. On the test laptop, a change
between two cached models (7.4 MB and 2.2 MB) took a median of 5 to 7 ms instead of 84 to
119 ms. Each model has its own material settings, so a base color or variant stays with it.

A cached copy stays in memory while no model shows it: the file's source data, and its decoded
textures and geometry in GPU memory. The cache counts filly's estimate of this memory
(`Asset.memory`: CPU bytes plus GPU bytes). On the test laptop, the estimate was 79 MiB for the
7.4 MB file with large textures and 18 MiB for the 2.2 MB file. On a computer with an
integrated GPU, both parts use system memory.

The cache keeps its copies within one memory limit. When a new copy goes past the limit, the
least recently used copies go first. A file whose estimate is above the limit is not cached, and
its model keeps no source data. Models that the experiment shows do not count, also when
they come from a cached copy.

Set the limit in one of these ways:

| Where | Name | Default | Values |
| --- | --- | --- | --- |
| 3D Scene, **Rendering** tab | **Model cache (MiB)** | blank: the runtime default | A number of MiB; `0`: off; `unlimited`: no limit. The first 3D Scene in a window that sets it decides |
| Local, in a Code component, **Before Experiment** | `filly_runtime.MODEL_CACHE_MAX_BYTES` | 1 GiB (`2**30`) | Bytes; `0`: off; `None`: no limit |
| Online, in a Code component, **Begin Experiment**, after the 3D Scene component | `filly_runtime.modelCache.maxBytes` | 256 MiB (`256 * 2 ** 20`) | Bytes; `0`: off; `Infinity` or `null`: no limit |

The parameter has priority over the code setting.

Online, the CPU part of the cache is in the WebAssembly memory, which never gets smaller. When
the cache removes a copy, filly can use that memory again, but the browser does not get it
back. Thus, online, the limit sets the highest memory use of the cache, not its current use.

### Run online

1. Save the experiment.
2. Compile it to JavaScript, or sync it to Pavlovia. The compile copies the folder `filly` into
   the experiment folder. It holds filly's WebAssembly build and the PsychoJS runtime.
3. Keep the `filly` folder with the experiment. Pavlovia sync uploads it with the other files.

The experiment loads these files from its own server. Thus a page with cross-origin isolation
headers (COOP and COEP) can load them too; see [cross-origin isolation](#cross-origin-isolation).

## Parameters

Each parameter that can change during the experiment has the update modes **constant**,
**set every repeat**, and, where the table says so, **set every frame**. A blank field takes the
default. Colors use the component's **Color space** (rgb, rgb255, hex, or named online).

### 3D Scene

Basic: **Position**, **Size**, **Spatial units**, **Orientation**, and **Opacity** place the
image, as for an image stimulus; they need no new render.

| Tab | Parameter | Default | Changes | Meaning |
| --- | --- | --- | --- | --- |
| Layout | Render size [w,h] | initial size | constant | Pixels of the rendered image. Set it if the size changes during the experiment |
| Layout | Render scale | 1 | constant | Factor for the automatic render size, in (0, 2]. Below 1 is faster for expensive scenes but stretches the image bilinearly, which blurs edges and fine detail. Not used with a render size |
| Camera | Projection | perspective | constant | perspective or orthographic |
| Camera | Field of view (deg) | 30 | every frame | Vertical field of view of the perspective projection |
| Camera | View height | from framing | every frame | Height of the orthographic view in scene units |
| Camera | Camera position [x,y,z] | framing | every frame | Blank: on the +Z axis, framing all models |
| Camera | Look at [x,y,z] | `(0, 0, 0)` | every frame | Used with a camera position |
| Camera | Framing fill | 0.9 | every frame | Fraction of the narrower axis that the framed models span |
| Camera | Near clip, Far clip | automatic | every frame | Clipping planes in scene units |
| Camera | Exposure (EV100) | 15 | every frame | Lower values give a brighter image |
| Lighting | Directional light | on | constant | Add one directional light |
| Lighting | Light direction, intensity, color | `(-1, -1, -2)`, 100000 lux, white | every frame | |
| Lighting | Environment light | uniform | constant | uniform, none, or file |
| Lighting | Environment file | | constant | 2:1 panorama (`.hdr`, `.png`, `.jpg`) or a cmgen KTX cubemap |
| Lighting | Environment intensity, rotation | 20000 lux, 0 degrees | every frame | |
| Lighting | Show environment | off | constant | Draw the environment instead of the background |
| Appearance | Background color | transparent | every frame | An opaque color, or **Show environment**, also saves the extra pass that transparent output costs |
| Rendering | Tone mapping | linear | constant | `aces_legacy` matches Filament's gltf_viewer |
| Rendering | Antialiasing, MSAA samples | fxaa, 1 | constant | |
| Rendering | Shadows | off | constant | Glass refracts without a setting |
| Rendering | Model cache (MiB) | default | constant | Memory limit of the window's [model cache](#model-cache): a number, `0` for off, or `unlimited` |

### 3D Model

| Tab | Parameter | Default | Changes | Meaning |
| --- | --- | --- | --- | --- |
| Basic | Scene | `scene` | constant | Name of the 3D Scene component that shows the model |
| Basic | Model file | `default.glb` | constant, set every repeat, set during | `.glb` or `.gltf` file. `default.glb`: the sample model. See [change the model per trial](#change-the-model-per-trial) and the [model cache](#model-cache) |
| Basic | Rotation [x,y,z] | `(0, 0, 0)` | every frame | Degrees about X, then Y, then Z |
| Basic | Model position [x,y,z] | `(0, 0, 0)` | every frame | Scene units (glTF units are meters) |
| Basic | Model scale | `1` | every frame | One factor or `[x,y,z]` |
| Basic | Center model | on | constant | Put the bounding-box center at the model position, and rotate about it |
| File | Lights from file | on | constant | Keep the model's own lights |
| File | Camera from file | | constant | Name or node index of a camera in the model file. The scene renders through it; one model per scene |
| Appearance | Material variant | | every repeat | Name or index |
| Appearance | Material name | all | every repeat | Material that the base color changes |
| Appearance | Base color | as in file | every frame | Replaces the base color; alpha stays |
| Animation | Animation clip | | every repeat | Name or index |
| Animation | Animation time (s) | 0 | every frame | For example `t` to play the clip |
| Animation | Loop animation | on | constant | |

A name that is all digits is an index unless the model has an item with that name. Colors are
display values, as for other PsychoPy stimuli: an unlit surface or the background shows the
given color.

## Generated code

The components write calls to a runtime module, the only code that calls filly.

PsychoPy:

```python
from psychopy_filly import runtime as filly_runtime

# At initialization. Loading and shader compilation happen here, not in the frame loop.
scene = filly_runtime.SceneStim(
    win=win, name='scene',
    pos=(0, 0), size=(0.6, 0.6), units=win.units, ori=0.0, opacity=None,
    colorSpace='rgb',
    depth=0.0)
cube = filly_runtime.SceneModel(
    scene, 'cube.glb', name='cube', colorSpace='rgb',
    rotation=None,
)

# Each frame. The scene's autoDraw draws it at the flip; the model's autoDraw shows it in the scene.
cube.setRotation((20, 90*t, 0), log=False)

# At the end of the experiment.
filly_runtime.close_all()
```

PsychoJS:

```javascript
// In experimentInit()
if (typeof filly_runtime === 'undefined') {
  filly_runtime = await import('./filly/filly-psychojs.js');
  filly_runtime.init({ util, visual });
}
scene = await filly_runtime.SceneStim.create({
  win: psychoJS.window, name: 'scene',
  pos: [0, 0], size: [0.6, 0.6], units: psychoJS.window.units, ori: 0.0, opacity: undefined,
  colorSpace: 'rgb',
  depth: 0.0
});
cube = await filly_runtime.SceneModel.create({
  scene: scene, name: 'cube', model: 'cube.glb', colorSpace: 'rgb',
  rotation: undefined,
});

// Each frame
cube.setRotation([20, (90 * t), 0], false);

// In quitPsychoJS(), at the end and after Escape
await filly_runtime.closeAll();
```

Constant parameters at their default are not written. Each parameter that can change has a
`set<Name>()` method on `SceneStim` or `SceneModel`. A scene renders a new image only after a
change to it or to one of its models. Position, size, orientation, and opacity move or fade the
drawn texture and need no new render. In Code components, `scene.models` lists the scene's
models, and `model.model` is the filly model.

PsychoJS updates every stimulus in the frame after its parameters change, so online, a change
shows one frame later than in a local experiment.

## Online details

### How the browser renders

filly's WebAssembly module is filly's own C++ core, compiled with Emscripten. It uses filly's
precompiled materials and output passes, so online output follows the same material path as
local output. PsychoJS's renderer (PIXI) and filly share one WebGL2 context: filly renders into
a texture that PIXI allocated, and PIXI draws it as a sprite. The runtime hands the context back
to PIXI before each PIXI frame. See filly's [web explanation](https://github.com/aforren1/filly/blob/main/docs/explanation/web.md).

Measured on one laptop (Intel Iris Xe, Windows 11, 60 Hz) with a rotating cube, two runs per
browser, with the earlier one-component runtime. Creating a scene and its model now does the
same steps in two calls:

| | Chrome | Edge | Firefox |
| --- | --- | --- | --- |
| Creating the stimulus, including the module start | 0.41 to 0.44 s | 0.45 to 0.66 s | 0.44 to 0.53 s |
| Shader compilation during creation, without blocking | 190 to 195 ms | 216 to 278 ms | none: compiles at the first render |
| First render | 29 to 31 ms | 29 to 45 ms | 237 to 269 ms |
| Longest frame during creation | 67 to 100 ms | 83 to 150 ms | 250 to 283 ms |
| CPU time of a render, median (95th percentile) | 0.6 to 0.7 (1.4) ms | 0.6 (1.2 to 1.4) ms | 1 (2) ms |
| Frame interval, median | 16.7 ms | 16.7 ms | 16.7 ms |

Firefox's timer has a resolution of 1 ms on pages that are not cross-origin isolated. The
module is 3.5 MB, or 1.4 MB compressed.

`SceneStim.create()` and `SceneModel.create()` let the browser draw frames between their steps,
and the model's creation compiles the shaders without blocking the page where the browser can
(`KHR_parallel_shader_compile`; Chrome and Edge, not Firefox). It then renders once and waits,
without blocking the page, until the GPU has finished, so that no compilation or texture upload
falls on a trial frame. `setModel()` does the same. You can thus also create a scene or a model during a
routine, but frames during creation can still be long (see the table). Before these changes, the page showed no new frame for about 0.5 s per stimulus.
A uniform environment is not filtered; see filly's
[environment lighting](https://github.com/aforren1/filly/blob/main/docs/reference/api.md#environment-lighting).

### Difference from local output

With the same scene, the browser image matched desktop filly within one 8-bit level on the 97%
of pixels in flat regions, in Chrome, Edge, and Firefox on the test laptop. Pixels on color
edges differ more, because the GPU drivers rasterize triangle edges differently. A test checks
this (`tests/test_web.py`).

### Cross-origin isolation

The experiment loads the files in `filly` from its own origin, and the WebAssembly module uses
no threads. Thus:

- A page without COOP and COEP headers, such as a Pavlovia experiment, works.
- A page with them (cross-origin isolated) also works, because same-origin files need no
  `Cross-Origin-Resource-Policy` header. A copy of filly on a CDN would need one. A test serves
  an experiment with both headers.

Cross-origin isolation gives finer timers (`performance.now()`), but this plugin does not need
it. Pavlovia does not send these headers.

### Known PsychoPy export defects

Two defects of the PsychoJS export in psychopy-lib 2026.2.4 stop an experiment in the browser,
with or without this plugin, for experiments made outside the Builder app:

- The default participant value is a Python f-string. The export cannot parse its own script,
  so it adds no variable declarations, and the script fails at its first assignment.
- A Routine without a maximum duration writes `trialMaxDuration = None`.

The test helper `compile_js()` in `tests/builder_helpers.py` avoids both.

## Test

Make one environment for each tested PsychoPy version. PsychoPy 2024.2.4 must have Python
3.10. Its `psychopy` distribution requires `pypi-search`, which PyPI no longer has;
`tests/psychopy-overrides.txt` removes that requirement. filly 0.2 is not on PyPI yet, so the
command installs it from a filly checkout next to this one (`..\filly`); this builds filly.

```powershell
uv venv --python 3.10 <env>
uv pip install --python <env>\Scripts\python.exe --override tests\psychopy-overrides.txt psychopy==2024.2.4 ..\filly -e .[tests]
```

For PsychoPy 2026.2.4, use Python 3.11 and `psychopy==2026.2.4`. Then:

```powershell
<env>\Scripts\python.exe -m pytest -m "not display and not browser"   # code generation
<env>\Scripts\python.exe -m pytest -m display                         # opens windows, needs filly
cd tests\web; npm install; cd ..\..
<env>\Scripts\python.exe -m pytest -m browser                         # runs experiments in browsers
```

The browser tests need Node.js and an installed browser. They use Chrome by default; set
`FILLY_TEST_BROWSERS=chrome,edge,firefox` for more. On their first run they download the PsychoJS
library of the installed PsychoPy version from lib.pavlovia.org into `tests/web/.cache`.

On Windows, the tests point `APPDATA` to an empty folder. PsychoPy adds the app's plugin
folder (`%APPDATA%\psychopy3\packages`) to `sys.path`, and copies of filly or
psychopy-filly installed there by the app would replace the code under test.

`tests/data/filly_cube.py` is the expected script for PsychoPy 2026.2.4; the test that
compares it skips other versions. After an intended change to the generated code, write it
again with PsychoPy 2026.2.4:

```powershell
<env>\Scripts\python.exe -c "import sys; sys.path.insert(0, 'tests'); import builder_helpers as h; open('tests/data/filly_cube.py', 'w', encoding='utf-8', newline='\n').write(h.compile_script(h.build_experiment()))"
```

`tools/check_builder.py OUT_DIR` checks plugin discovery, the wxPython Builder compile, and the
calls that PsychoPy Studio makes. It needs no display and no filly, so it also runs in the
standalone app's Python. `tools/make_icons.py` writes the placeholder icons.

## Update the web build

`psychopy_filly/web` holds a copy of filly's web build. To update it:

1. In filly, build the Filament WebAssembly SDK once, then filly's module (on Linux or WSL):
   `tools/build_filament_web.sh`, then `tools/build_filly_web.sh`. See filly's
   [build guide](https://github.com/aforren1/filly/blob/main/docs/how-to/build.md#build-for-the-web).
2. Here: `python tools/vendor_web.py ../filly/build/web`. It copies the files and writes their
   sizes and SHA-256 hashes to `psychopy_filly/web/VENDOR.json`.

`psychopy_filly/web/filly-psychojs.js` is this plugin's own code, not part of the copy.

The default model is `filly.samples.SUZANNE`. The JavaScript compile copies it to the
experiment's `filly` folder as `default.glb`, only if the experiment can show it: a constant
**Model file** of `default.glb`, or a model that changes per trial.

## Publish a release

[Build and release](.github/workflows/release.yml) builds the sdist and the wheel on every push
and pull request, and tests the built wheel with the tests that need no display. A pushed tag
`vX.Y.Z` that matches the version in `pyproject.toml` publishes both to PyPI through trusted
publishing. A manual run can publish to TestPyPI instead.

Set up once: on pypi.org and test.pypi.org, add a pending publisher for project
`psychopy-filly`, owner `aforren1`, repository `psychopy-filly`, workflow `release.yml`, with the
environments `pypi` and `testpypi`. Create the same environments in the GitHub repository
settings.

Publish filly 0.2 first: the tests install it from PyPI, and PyPI has only filly 0.1.0, which
cannot run this plugin. For a final release, require a final filly, for example
`filly>=0.2.0,<0.3` in `pyproject.toml`. Then set `version`, commit, and push a tag such as
`v0.1.0`.

## License

MIT. See [LICENSE](LICENSE). The files in `psychopy_filly/web` other than
`filly-psychojs.js` are filly's and its dependencies'; their licenses are in
`psychopy_filly/web/licenses`.
