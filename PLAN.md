# psychopy-filly: plan for PsychoPy Builder components

This document describes a PsychoPy plugin that gives Builder users 3D stimuli from the filly
renderer. Phases 0 and 1 are done, and the online component (phases 4 and 5) is built but not
yet run on Pavlovia: see [Phases](#phases). Facts marked "(phase 0)" were checked on
2026-09-29.

## Goal

- Builder users add a 3D stimulus to a routine without code: choose a glTF file, set the camera,
  lights, and pose, and make parameters change per trial or per frame, as with other Builder
  components.
- Local experiments render with filly into a shared OpenGL texture that PsychoPy draws. There is
  no readback, and PsychoPy keeps control of the flip.
- Online experiments (PsychoJS on Pavlovia) use filly's WebAssembly build. See
  [Online experiments](#online-experiments).

## Out of scope

- macOS. filly supports only Windows and Linux. The component must fail with a clear message on
  macOS, not crash.
- A general 3D scene editor in Builder. Builder parameters describe one stimulus at a time; users
  who need complex scenes use a Code component and the filly API.
- Coder support. Coder users call filly directly with `filly.integrations.psychopy`.

## Name and location

- Package `psychopy-filly`, module `psychopy_filly`. The PsychoPy plugin guide requires the
  `psychopy-` prefix and a module name with underscores.
- Keep the plugin in its own repository. Unlike the MATLAB frontend, it contains no native code:
  it generates Python and JavaScript that call filly's public API, and it depends on a released
  filly version.

## How PsychoPy plugins work

References: [Using plugins](https://psychopy.org/usingplugins.html),
[Creating plugins](https://psychopy.org/developers/pluginDevGuide.html), and the
[plugin template](https://github.com/psychopy/psychopy-plugin-template). Facts below were checked
against psychopy-lib 2026.2.4.

- **Discovery.** A plugin is a pip package that declares Python entry points. PsychoPy lists
  installed plugins with `psychopy.plugins.listPlugins()` and loads them with
  `activatePlugins()`. Builder scripts call `plugins.activatePlugins()` at the top.
- **Loading (phase 0).** `activatePlugins()` loads every installed plugin, not only the start-up
  list. For each plugin it imports the top-level module (`psychopy_filly`), loads each entry
  point, and sets it as an attribute of the group's module. For a component it also calls
  `psychopy.experiment.components.addComponent()`, which puts the class in `pluginComponents`;
  `getAllComponents()` merges that dictionary. The wxPython app calls `activatePlugins()` at
  start-up. Consequence: the package root and the component module must import quickly and must
  not import filly. They do not; a test checks it.
- **Command-line compile drops plugin components (phase 0).** `python -m
  psychopy.scripts.psyexpCompile` does not activate plugins. It writes
  `# Unknown component ignored: cube` but keeps `components=[cube]`, so the script fails at run
  time. The wxPython Builder uses this path when the experiment sets **Use version**. In-process
  compiles (Builder's Compile command, Studio) activate plugins first and work.
- **Entry-point groups** used by the template's `pyproject.toml`:

  | Group | Purpose |
  |---|---|
  | `psychopy.experiment.components` | A component in the Builder components panel |
  | `psychopy.experiment.routines` | A standalone routine |
  | `psychopy.visual` | A class importable from `psychopy.visual` |
  | `psychopy.hardware` | A device class |
  | `psychopy.app.builder`, `psychopy.app.coder`, `psychopy.app.runner` | Ribbon sections in the wxPython app |
  | `psychopy.app.themes.icons` | Icons for the app. PsychoPy 2026.1.2 registers this group; 2026.2.4 checks `psychopy_app.themes.icons` instead (phase 0). Component icons do not use it. |

- **Component classes.** A component subclasses `BaseComponent` or `BaseVisualComponent` from
  `psychopy.experiment.components`. Class attributes: `categories` (panel section), `targets`
  (`"PsychoPy"`, `"PsychoJS"`, or both), `plugin` (the package name), `iconFile`, and `tooltip`.
  Parameters are `Param` objects with a `valType` (for example `'file'`), an `updates` mode, and
  `allowedUpdates`: `'constant'`, `'set every repeat'`, or `'set every frame'`.
  Also (phase 0): `iconSVG` (the icon that Studio shows), `version` (earliest PsychoPy version),
  and `beta`. The wxPython app takes `iconFile`'s stem and folder and loads
  `<folder>/<theme>/<stem>*.png` for the themes `classic`, `light`, and `dark`, with `@2x`
  variants, as the template does.
- **Code generation hooks** in `psychopy/experiment/components/_base.py`: `writePreCode`,
  `writeStartCode`, `writeInitCode`, `writeRoutineStartCode`, `writeFrameCode`,
  `writeRoutineEndCode`, `writeExperimentEndCode`, and the matching `...JS` methods for PsychoJS.
  `BaseVisualComponent` already writes the start and stop timing logic for visual stimuli.
- **Where the hooks write (phase 0, modular script).** `writeInitCode` writes into `run()` after
  window creation, under "Initialize components", although its docstring says "before window
  creation". `BaseVisualComponent.writeFrameCode` writes `setAutoDraw(True/False)` and one
  `set<Param>(value, log=False)` call per parameter that is set every frame; the window's flip
  then calls the stimulus's `draw()`. `writeExperimentEndCode` writes at the end of `run()`,
  which Escape skips. Code that must run on both paths appends a function to the script's
  `runAtExit` list: `endExperiment()` calls it before `quit()` closes the window.
  `exp.requireImport()` adds an import at the top of the script.
- **Online resources.** The JavaScript export collects the files named by `'file'` parameters
  into the experiment's resource list. Phase 0 checked the Python side:
  `Experiment.getResourceFiles()` lists the component's model file once the experiment has a
  file name. It adds external scripts the same way: a Staircase loop adds
  `https://lib.pavlovia.org/vendors/jsQUEST.min.js` to that list.
- **Plugin index.** The plugin manager reads `https://psychopy.org/plugins.json`. A plugin must be
  added to that index to appear in the manager; otherwise users install it with pip.

### Two Builders

The wxPython Builder (`psychopy-app`) is being replaced by
[PsychoPy Studio](https://github.com/psychopy/psychopy-studio), a Svelte and Electron application.
Studio gets component profiles (categories, targets, icon, tooltip, parameters) from Python
through its "liaison", and compiles experiments with `psychopy.experiment.Experiment`. A component
that is defined only by its class attributes and `Param` objects therefore works in both Builders.

Checked in the Studio source (phase 0):

- Studio starts `python -m liaison.websocket`, a separate `liaison` package, not
  `psychopy.liaison`. At start it runs `psychopy.plugins:activatePlugins`.
- The components panel runs `psychopy.experiment:getElementProfiles`, which returns
  `cls.getTemplateJSON()` for each component: `categories`, `targets`, `plugin`, `iconSVG` (the
  SVG text), `iconFile`, `tooltip`, `version`, `beta`, `helpLink`, and a template for each
  parameter. The panel shows `iconSVG`, so a plugin component needs an SVG icon for Studio.
- To compile, Studio saves the `.psyexp` file, then runs `Experiment()`, `loadFromXML(psyexp)`,
  and `writeScript(target=..., modular=True, expPath=psyexp)`. The component must therefore
  survive a save and load. A test checks that the round trip gives the same script.

Rule: put all component behavior in the component class and its parameters. Do not depend on
wxPython dialogs or ribbon sections for anything required.

## Components

### "3D Scene" and "3D Model" (since 2026-10-04)

Phase 1 had one "3D Model" component with one model, camera, and lights. On 2026-10-04 it was
split, before any release, so that several models can share one image, with occlusion and
shadows between them:

- **3D Scene** (`Scene3DComponent`, a visual component; runtime `SceneStim`) owns the camera,
  lights, environment, background, rendering settings, and the shared render target, and draws
  the image like an `ImageStim`.
- **3D Model** (`Model3DComponent`, a plain component; runtime `SceneModel`) names its scene in
  **Scene** and has the file, pose, materials, file lights, file camera, and animation. Its
  start and stop call `setAutoDraw(True/False)`, which shows and hides the model in its scene.
  The frame code is `BaseVisualComponent.writeFrameCode`, which uses nothing but that call.
  Routine ends call `setAutoDraw(False)` on every component that has it, so models hide too.

The pattern follows PsychoPy's own references between components: Static periods update other
components by name, mouse "clickable stimuli" name components, and device components name a
device. Unlike clickable stimuli, the generated code passes the scene object, so a wrong name
fails at compile time. Decisions:

- Automatic framing (camera position blank) fits the box that encloses all models of the scene
  in their rest poses, placed as when they loaded. Loading or closing a model fits it again;
  pose, visibility, and animation changes do not. Camera position overrides it.
- Camera from file is a model parameter. The scene renders through it; two models of one scene
  with a file camera are a compile error and a runtime error.
- Precompiled shaders stays on the scene. One renderer serves a window, so the first scene
  decides; the runtime warns when a later one differs.
- The compile fails if a model's scene is missing, is not a 3D Scene, or comes after the model.
- A model is hidden until its start. Filament compiles only what it draws, so the warm-up render
  at creation shows the model once. Creation and `setModel()` then wait until the GPU has done
  all queued work (`renderer.finish()` locally, a fence polled between frames online), so that
  the first trial frame does not wait for shader compilation or texture uploads. `setModel()`
  renders without the model's other settings, because Builder sets them after the model and
  the new model may not have the previous trial's names. Measured on 2026-10-04: the worst of
  the first 10 draws after a change went from 39 to 398 ms to 1.6 to 5.6 ms locally, and the
  worst frame interval from 33 to 250 ms to 17 ms in Chrome.
- A model that changes per repeat starts without a file (`SceneModel(scene, None)`), so no
  stand-in loads at the start of the experiment.
- Each window (one filly renderer) caches the files that `setModel()` loaded as clonable
  prototypes, and later changes to a cached file clone them into the scene that asks
  (`Model.clone(scene=)`; decisions of 2026-10-04 and 2026-10-05). The prototypes live in a
  hidden scene of the cache, so that closing the scene that first loaded a file leaves its
  prototype usable; a test closes that scene and clones again. The key holds the scene's
  refraction setting, because a clone keeps the material setup of its asset's load.
- The cache has one limit, in filly's memory estimate of the prototypes (`Model.memory`:
  `cpu_bytes + gpu_bytes`, which include what earlier clones left with the asset), least
  recently used out first. A file larger than the limit loads without source data; a file
  whose estimate after a clonable load is above the limit loads again without it, once. Only
  the prototypes count: we limit the memory that the cache keeps without being asked, not the
  experimenter's models. Defaults: 1 GiB locally (`MODEL_CACHE_MAX_BYTES`), 256 MiB online
  (`modelCache.maxBytes`), because the WebAssembly heap never shrinks: online, the limit
  bounds the high-water mark. The 3D Scene parameter **Model cache (MiB)** overrides both;
  `0` turns the cache off, and `unlimited` (code: `None`, `Infinity`) removes the limit.
- Transparent output is on only when the image can have alpha below one: no background color
  and no visible environment. Filament's transparent view costs an extra pass. The warm-up
  renders the transparent path once per renderer, so a later switch to a blank background does
  not compile it in a trial.
- Pose changes recompute only the clipping planes, not the framing; the model matrix is cached
  per pose. A clip re-applies the base color only to the materials whose base color a clip
  animates (filly's `AnimationInfo.material_properties`).

The parameter tables are in the README.

### Generated code (local)

Phase 0 generates this code (see `tests/data/filly_cube.py`):

```python
# exp.requireImport(): top of the script
from psychopy_filly import runtime as filly_runtime

# writeInitCode: in run(), after window creation. Loading and shader compilation happen here,
# never in the frame loop.
scene = filly_runtime.SceneStim(
    win=win, name='scene',
    pos=(0, 0), size=(0.6, 0.6), units=win.units, ori=0.0, opacity=None,
    colorSpace='rgb',
    depth=0.0)
if filly_runtime.close_all not in runAtExit:
    runAtExit.append(filly_runtime.close_all)
cube = filly_runtime.SceneModel(
    scene, 'cube.glb', name='cube', colorSpace='rgb',
    rotation=None,
)

# BaseVisualComponent.writeFrameCode: autoDraw and one setter per parameter set every frame.
# The flip calls scene.draw(), which renders only after a change to the scene or its models.
scene.setAutoDraw(True)
cube.setAutoDraw(True)
cube.setRotation((20, 90*t, 0), log=False)

# writeExperimentEndCode: normal end only. runAtExit covers Escape.
filly_runtime.close_all()
```

Consequence: every per-frame parameter needs a `set<Param>()` method on `SceneStim` or `SceneModel`, named
after the parameter key (`_getParamCaps`). Direct attribute assignments such as
`cube.model.rotation_euler_deg = ...` would need a custom `writeFrameCode`.

- `psychopy_filly.runtime` holds one renderer per window and builds on
  `filly.integrations.psychopy`. It is the only place that knows filly's API, so filly API changes
  touch one module, not the code generator.
- `SceneStim.draw()` renders only when the scene or one of its models changed since the last draw. A static stimulus
  costs one texture draw per frame. (phase 0: a test counts `renderer.stats.frames_rendered`.)
- The close order (target, renderer, window) goes in `writeExperimentEndCode` and in `runAtExit`.
  `writeExperimentEndCode` alone misses Escape (phase 0). The runtime also registers an `atexit`
  handler; PsychoPy registered its window close earlier, so the runtime's handler runs first.
  filly also releases everything if the window closes first, so an aborted experiment does not
  crash.

### Resources

- `'file'` parameters make PsychoPy check paths and copy files for online runs. A `.gltf` file can
  reference external `.bin` and image files that PsychoPy does not know about. Recommend `.glb`,
  and have the component list a `.gltf` file's external files as extra resources.
- Load models in init code. First load compiles shaders and can take hundreds of milliseconds.
  Expose filly's `precompiled_shaders` option in the Advanced tab for experiments that load many
  models.

## Dependencies and compatibility

- `psychopy-filly` depends on `filly` and on the PsychoPy versions its adapter supports. The filly
  PsychoPy adapter uses PsychoPy internals: the `ImageStim` texture-provider path, the window's
  image shader program, and a patched fragment shader. Pin the tested PsychoPy versions, and test
  each PsychoPy release before widening the pin.
- PsychoPy cannot be a pip dependency (phase 0). It ships as two distributions, `psychopy` (the
  standalone app's) and `psychopy-lib`. A requirement on either makes pip install it next to the
  other. `psychopy_filly.runtime.TESTED_PSYCHOPY` lists the tested versions and the runtime logs a
  warning for others. The `tests` extra pins `psychopy-lib==2026.2.4`, the version filly's adapter
  is tested with.
- psychopy-lib 2026.2.4 cannot compile experiments without `esprima`, which it does not declare
  (phase 0). The standalone app includes it.
- PsychoPy standalone installs ship their own Python. filly publishes wheels for Python 3.10, 3.11,
  and 3.12 and later (one `cp312-abi3` wheel), for Windows and Linux x86_64. Check the Python
  version of each standalone release. PsychoPy 2026.1.2 (Windows) ships Python 3.10.11,
  pyglet 1.4.11, and wxPython 4.2.5 (phase 0). No filly wheel exists yet.
- PsychoPy pins pyglet 1.4.11 on Windows only. psychopy-lib 2026.2.4 requires pyglet 1.5.27 on
  other platforms (phase 0), so Linux runs need their own tests. Version 1.4.11 can crash when a
  program closes a window and then opens another (see filly's validation reference). A normal
  experiment opens one window; the component does not need a workaround.
- PsychoPy must use the pyglet window backend. Check `win.winType` at init and fail with a clear
  message otherwise. (phase 0: done, also for `blendMode`, which the adapter requires to be
  `avg`.)
- Builder's default blend mode, "average", writes `useFBO=True`. Phase 0 concluded that such a
  window shows no stimuli on the test machine, from front-buffer reads after the flip. On
  2026-10-03 the user saw the 3D stimulus on screen with FBO on (PsychoPy 2026.1.2 app), and a
  back-buffer read right after the stimulus draws shows it with FBO on and off; the front-buffer
  read returns only the background. The runtime no longer warns for `useFBO=True`, and the
  compiled-experiment test runs both blend modes.

## Online experiments

Built on 2026-10-03 (phases 4 and 5 below). This section describes the design as built; the
earlier plan assumed Filament's stock JavaScript build and is replaced.

### What exists

- PsychoJS 2026.2.4 renders with PIXI.js 6.0.4 (`pixi.js-legacy`) into its own WebGL context.
  PIXI uses WebGL2 except on non-Apple mobile devices, where it uses WebGL1
  (`settings.PREFER_ENV`). PsychoJS does not export PIXI.
- The Filament npm package stops at version 1.53.4. Filament material packages are tied to the
  engine version, so filly builds Filament 1.77.1 for WebAssembly itself
  (`filly/tools/build_filament_web.sh`).
- filly's core compiles with Emscripten (`filly/web`, `filly/tools/build_filly_web.sh`): the same
  C++ as the desktop module, with filly's precompiled material archive and output passes, for
  GLSL ES 3.00. The module is single-threaded, so pages need no cross-origin isolation.

### Design

- **One context, no copy.** Filament renders into the page's WebGL2 context, the one that PIXI
  uses, through Emscripten's context registration. It renders into a texture that PIXI
  allocated, and PIXI draws that texture as a sprite. Filament documents this use
  (`Engine::resetBackendState()`, WebGL only). The earlier options (an offscreen canvas uploaded
  each frame, or stacked canvases) are not needed.
- **Hand-over.** Both renderers cache GL state. filly enters the context before its first call
  after PIXI drew and hands it back at PIXI's `prerender` event. See filly's
  [web explanation](../filly/docs/explanation/web.md) for the state that each side must reset;
  three defects found during the spike are listed there.
- **Same material path.** filly's own provider and archive run in the browser, so filly's
  extensions (anisotropy, iridescence, diffuse transmission) and its orthographic refraction fix
  also work online. No parameter is local-only, except `precompiledShaders`, which has no effect
  online.
- **Vendored files.** The plugin ships filly's web build in `psychopy_filly/web`, and the compile
  copies it into the experiment folder (`filly/`). The experiment imports it from its own origin.
  No CDN hosts filly's build, and a same-origin copy also loads on a cross-origin-isolated page.

### Generated code (online)

- `writeInitCodeJS` imports `./filly/filly-psychojs.js` with a dynamic `import()` in
  `experimentInit()`, passes it PsychoJS's `util` and `visual`, and awaits `SceneStim.create()`
  and `SceneModel.create()`.
  PsychoPy's esprima pass accepts the dynamic import and adds the variable declarations.
- `BaseVisualComponent.writeFrameCodeJS` writes `setAutoDraw()` and the per-frame setters.
- `writeExperimentEndCodeJS` awaits `closeAll()` in `quitPsychoJS()`, which runs at the end and
  after Escape, before the window closes.
- PsychoJS's resource manager downloads unknown file types as text, which garbles a `.glb`. The
  stimulus fetches the model from the resource's path itself; the browser cache serves it.

## Phases

| Phase | Work | Done when |
|---|---|---|
| 0 | A stub component that draws a rotating cube through `filly.integrations.psychopy`. | It appears and compiles in the wxPython Builder and in Studio, runs locally on Windows, and the experiment-end hook closes everything in order. Done 2026-09-29; see [Phase 0 results](#phase-0-results). |
| 1 | The "3D Model" component and `psychopy_filly.runtime`, local only. | A Builder experiment shows the same pixels as the equivalent direct filly script. Per-frame parameters cost no reload. Tests run under PsychoPy with a display. Done 2026-10-03; see [Phase 1 results](#phase-1-results). |
| 2 | Packaging: PyPI release, documentation, the PsychoPy version pin, and a request to add the plugin to `plugins.json`. | Users install it from the plugin manager. |
| 3 | "3D Scene" and "3D Object" components, if phase 1 users ask for several objects. | Two objects with separate poses render in one scene. |
| 4 | Online spike: build Filament 1.77.1 for WebAssembly, and show a `.glb` model in a hand-written PsychoJS experiment. | Frame time is measured in Chrome and Firefox, and the resource loading question is answered. Done 2026-10-03 on one laptop; see [Online results](#online-results). |
| 5 | Online component: `writeInitCodeJS`, `writeFrameCodeJS`, the PsychoJS runtime, and filly's web build. | A Builder experiment runs on Pavlovia, and the difference from local output is measured and documented. Built and measured on 2026-10-03; not run on Pavlovia yet. |

### Phase 0 results

- Package: `pyproject.toml`, `psychopy_filly.runtime`, the `Model3DComponent` class with
  placeholder icons, tests, and `tools/check_builder.py`.
- psychopy-lib 2026.2.4 (Python 3.11): a compiled experiment with a rotating cube runs, the
  captured frames show the cube at different angles, and the process exits with code 0. Close
  order on the normal path and after Escape: targets, then the renderer (window still open),
  then the window.
- PsychoPy 2026.1.2 app (Python 3.10, wxPython): `activatePlugins()` registers the component,
  the app's icon code loads all three themes, `generateScript()` compiles the experiment, and
  the psyexp round trip compiles. It cannot run there: no filly wheel.
- Studio: not launched. The profile and compile calls that Studio makes give the expected
  profile and the same script as a direct compile.
- Not done: the wxPython Builder window and the Studio app were not opened. Only their Python
  calls were reproduced.

### Phase 1 results

- The component has the parameters of the [table above](#phase-1-one-3d-model-component), as
  listed in the README. Differences from the table: field of view, view height, clipping planes,
  and light and environment intensity can change every frame; the environment source is
  constant, because loading a panorama filters it.
- Each changing parameter has a `set<Name>()` method on `SceneStim` or `SceneModel`. A test calls each setter with a new
  value and checks that the next draw renders once, and that the same value renders nothing.
- A Builder-style stimulus with an explicit camera and an opaque background matches the same
  scene set up with the filly API within one 8-bit level, drawn in a PsychoPy window.
- psychopy-lib 2026.2.4: the code generation and display tests pass (`tests/test_codegen.py`,
  `tests/test_runtime.py`). PsychoPy 2026.1.2 app: discovery, the wxPython compile, and the
  Studio calls give the same initialization code (`tools/check_builder.py`).
- filly gained `create_renderer(win, precompiled_shaders=...)` for the Advanced tab option.

### Online results

All on one laptop: Intel Iris Xe (ANGLE on Direct3D 11), Windows 11, 60 Hz; Chrome, Edge, and
Firefox in headless mode with the GPU.

- Spike (Filament's own bindings and gltfio, 2026-10-03): Filament renders a glTF cube into a
  PIXI texture in PsychoJS's context. Three state leaks had to be fixed first; see filly's web
  explanation.
- filly's module: 3.5 MB, 1.4 MB compressed, with the full JavaScript API (3.4 MB before it).
  The stock `filament.wasm` 1.77.1 is 3.5 MB.
- Timing with the 3D Model component (rotating cube, two runs per browser):

  | | Chrome | Edge | Firefox |
  |---|---|---|---|
  | `ModelStim.create()`, including the module start | 0.41 to 0.44 s | 0.45 to 0.66 s | 0.44 to 0.53 s |
  | Shader compilation in `create()`, without blocking | 190 to 195 ms | 216 to 278 ms | none: compiles at the first render |
  | First render | 29 to 31 ms | 29 to 45 ms | 237 to 269 ms |
  | Longest frame during `create()` | 67 to 100 ms | 83 to 150 ms | 250 to 283 ms |
  | CPU time of a render, median (95th percentile) | 0.6 to 0.7 (1.4) ms | 0.6 (1.2 to 1.4) ms | 1 (2) ms |
  | Frame interval, median | 16.7 ms | 16.7 ms | 16.7 ms |

  Before 2026-10-03, `ModelStim.create()` blocked Chrome for one frame of 0.47 to 0.5 s:
  renderer 45 ms, model 100 ms, uniform environment 224 ms, target 25 ms, first render 141 ms.
  Now it yields a frame between steps, the uniform environment skips filtering, and
  `renderer.prepare()` compiles the shaders without blocking before the warmup render. Firefox
  has no `KHR_parallel_shader_compile`, so its first render still compiles. In Chrome and Edge,
  a transparent scene still compiles Filament's blit at the first render (about 25 ms, once per
  renderer).
- Output difference from desktop filly (same scene, 320 x 240): within one 8-bit level on the
  97% of pixels whose 3 x 3 neighborhood is flat (8% of them differ by one level); up to 79
  levels on color edges, from different rasterization. The same in all three browsers.
- Resource loading: a dynamic `import()` loads the runtime; the model is fetched by the stimulus
  (see [Generated code (online)](#generated-code-online)).
- PsychoPy's local browser pilot serves the experiment with `python -m http.server`. On Windows,
  that sends `.mjs` as `text/plain`, and the browser refused the module ("Failed to fetch
  dynamically imported module"; found 2026-10-03 in the PsychoPy 2026.1.2 app). The web files
  now use `.js`, and a test runs the experiment from `python -m http.server`.
- Cross-origin isolation: an experiment served with COOP and COEP headers loads and renders;
  `crossOriginIsolated` is true. Pavlovia's run server sends neither header.
- A defect in Filament's single-threaded `flushAndWait()` made models render garbled at random
  after loading; filly works around it (see filly's web explanation). A browser test checks that
  no vertex upload remains after a load.
- Not done: a run on Pavlovia, other GPUs, macOS and mobile browsers, and the reference asset set
  of filly's parity harness.

## Finding names in a model

Builder has no stable way for a plugin to offer the names in a model file. The wxPython dialog
picks controls by input type from a registry that a plugin can join, but that ties the plugin to
the dialog's private classes, which PsychoPy is moving to the psychopy-app distribution while
Studio replaces it. Studio's controls are fixed in its own code. A version with a Contents
button and name menus worked in the 2026.1.2 app and was removed on 2026-10-03 for this reason.
Instead:

- `psychopy_filly.gltf_info` reads the names from the glTF JSON without filly, and
  `python -m psychopy_filly.gltf_info FILE` prints them.
- The compile warns about clip, variant, material, and camera names that the model file does
  not have, and lists the names that it has.
- filly's lookup errors list the names of that kind in the model, locally and online.

## Tests

- **Code generation.** Compile experiments with each parameter combination, and compare the
  generated Python and JavaScript with checked-in expected files. These tests need no display.
- **Local rendering.** Run compiled experiments under PsychoPy with a display, and compare a frame
  with the direct filly render of the same scene. Run them separately, as filly's PsychoPy tests
  are run.
- **Builder compatibility.** Load the component in both Builders for each supported PsychoPy
  version.
- **Online.** `tests/test_web.py` compiles experiments, serves them, and runs them in installed
  browsers with Node.js and puppeteer-core: a rotating model, the comparison with desktop
  filly, cross-origin isolation, Escape, a `.gltf` with an external buffer, the upload check,
  an opacity ramp (one sprite, no added PIXI listeners), a scene hidden past PIXI's texture
  garbage collection, and A/B/A/B model changes through the cache.

## Risks and open questions

| Item | Status | How to resolve |
|---|---|---|
| The filly PsychoPy adapter uses PsychoPy internals | Known | Pin PsychoPy versions; test each release |
| The PsychoJS runtime uses PsychoJS and PIXI internals (`Window._renderer`, the background sprite's classes, `_needUpdate`, `BaseTexture._glTextures`, `TextureSystem.managedTextures`) | Known | Pin PsychoJS versions with the PsychoPy pin; run the browser tests for each release |
| Studio's component and liaison interfaces can change while it replaces the wxPython app | Profile and compile calls checked in phase 0 | Follow Studio releases; open the component in the Studio app |
| Front-buffer reads of `useFBO=True` windows return only the background on the test laptop | The screen shows the stimuli (user check, 2026-10-03); tests read the back buffer | Check other GPUs; the README keeps "average (no FBO)" as a troubleshooting step |
| Command-line compile (`psyexpCompile`, used with **Use version**) drops plugin components | Seen in phase 0 | Document; report upstream |
| PsychoJS export defects in psychopy-lib 2026.2.4 (f-string participant default; `MaxDuration = None`) | Seen on 2026-10-03, also without filly, for experiments made in Python | Check in the Builder app; report upstream |
| PsychoPy standalone Python versions and filly wheel coverage | Not checked | Check at phase 2 for each supported standalone release |
| `.gltf` external files not collected as resources | Known; they load if they are in the experiment folder | Recommend `.glb`; list external files in the component |
| WebGL1 on Android and other non-Apple mobile devices | The component stops with a message | Set PIXI's `PREFER_ENV` before the window opens, if PsychoJS allows it; test on devices |
| Frames during stimulus creation take up to 150 ms (Chrome, Edge) or 283 ms (Firefox) | Measured on 2026-10-03 after frame yields, the uniform environment, and `prepare()` | Split the remaining steps; give transparent scenes an alpha swap chain so that Filament needs no blit; wait for Firefox to support `KHR_parallel_shader_compile` |
| A run on Pavlovia | Not done | Sync a test experiment |
| Rare crash of filly's desktop test suite when browsers use the same GPU at the same time | Seen once on 2026-10-03 | Track with filly's open concurrent-context crash |
