# How the plugin works

This page explains what the components generate, how filly draws into PsychoPy and PsychoJS
windows, and why picks and the model cache behave as they do. For the steps, see the how-to
guides; for the API, see the [runtime reference](../reference/runtime.md).

## Two paths, no pixel copies

- Locally, filly renders into an OpenGL texture that the PsychoPy window shares. PsychoPy draws
  the texture like an image stimulus.
- Online, filly's WebAssembly build renders into a WebGL texture that PsychoJS owns, in
  PsychoJS's own WebGL2 context. PsychoJS draws the texture like an image stimulus.

Neither path copies pixels through the CPU. PsychoPy and PsychoJS keep control of the frame.

## Generated code

The components write calls to a runtime module: `psychopy_filly.runtime` locally, and
`filly/filly-psychojs.js` online. The runtime is the only code that calls filly. For a scene
named `scene` and a model named `cube` that turns, the local script has:

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

# Each frame.
cube.setRotation((20, 90*t, 0), log=False)

# At the end of the experiment.
filly_runtime.close_all()
```

The PsychoJS script has:

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

Constant parameters at their default are not written. The scene draws itself at each flip
while it shows. A model is part of its scene's image from its start to its stop.

A scene renders a new image only after a change to it or to one of its models. Position, size,
orientation, and opacity move or fade the drawn texture, and need no new render.

PsychoJS updates every stimulus in the frame after its parameters change. Thus, online, a
change shows one frame later than in a local experiment.

## Locally

One filly renderer serves each PsychoPy window. The renderer must close before the window, and
closing the renderer also closes every target, model, and scene that it created.
`close_all()` closes the renderers at the end of the experiment. Escape skips that call, so the
runtime also closes a window's renderer when the window's `close()` starts. An `atexit` handler
covers scripts that stop with an exception.

Both of Builder's average blend modes work, with and without a framebuffer object (FBO).

## In the browser

filly's WebAssembly module is filly's own C++ core, compiled with Emscripten. It uses filly's
precompiled materials and output passes, so online output follows the same material path as
local output.

PsychoJS's renderer (PIXI) and filly share one WebGL2 context. filly renders into a texture
that PIXI allocated, and PIXI draws it as a sprite. The runtime hands the context back to PIXI
before each PIXI frame. For the state that each side must reset, see filly's
[web explanation](https://github.com/aforren1/filly/blob/main/docs/explanation/web.md).

PsychoJS uses WebGL1 on Android and other mobile devices that are not Apple devices. filly
needs WebGL2, so the runtime stops the experiment there.

`SceneStim.create()` and `SceneModel.create()` let the browser draw frames between their
steps. The model's creation compiles the shaders without blocking the page where the browser
can (`KHR_parallel_shader_compile`: Chrome and Edge, not Firefox). It then renders once and
waits, without blocking the page, until the GPU has finished. Thus no shader compilation or
texture upload falls on a trial frame. `setModel()` does the same. You can also create a scene
or a model during a routine, but frames during creation can still be long (see
[performance](../reference/performance.md#online-stimulus-creation)).

A uniform environment is not filtered. See filly's
[environment lighting](https://github.com/aforren1/filly/blob/main/docs/reference/api.md#environment-lighting).

### Difference from local output

With the same scene, the browser image matched desktop filly within one 8-bit level on the 97%
of pixels in flat regions, in Chrome, Edge, and Firefox on the test laptop. Pixels on color
edges differ more, because the GPU drivers rasterize triangle edges differently.
`tests/test_web.py` checks this.

### Cross-origin isolation

The experiment loads the files in `filly` from its own origin, and the WebAssembly module uses
no threads. Thus:

- A page without COOP and COEP headers, such as a Pavlovia experiment, works. Pavlovia does not
  send these headers.
- A page with them (cross-origin isolated) also works, because same-origin files need no
  `Cross-Origin-Resource-Policy` header. A copy of filly on a CDN would need one.

Cross-origin isolation gives finer timers (`performance.now()`), but this plugin does not need
it.

## Picking

A pick describes the image that the window showed: the scene as it was last rendered. The
setters only store values, and the next draw applies them, so the filly scene still holds the
state of the shown image when the pick runs. The pick renders that state again with a pick
query. Thus a click on a moving model counts where the participant saw the model. The cost is
a second render in click frames in which the scene also changed. The alternative, picking the
next render, would render once, but it would describe an image that the participant saw only
after the click.

Locally, `contains()` renders, waits for the GPU, and answers at once. The models of one
clickable list share that render: the scene keeps the answer for the same pixel and image.

Online, WebGL gives the answer only 2 or 3 frames after the render, so `contains()` cannot wait.
It returns the latest answer for the same pixel whose image is at most 4 renders older than the
shown one. Pointer tracking (`trackPointer`) makes such an answer available at the click.

The first pick of a renderer makes some GPU drivers do one-time work. Locally, when the plugin
knows that a scene picks (`SceneStim(picking=True)`), it does a hidden pick once per window when
it creates the scene, so that the cost falls on setup. The compile sets `picking` from the
**Mouse picking** checkbox, from Mouse components, and from a text search of Code components.

## Model cache

Each window keeps a filly asset of each file that a per-trial change loaded. All 3D Scenes of
the window share these assets. A file that a scene shows again becomes a new model of its
asset: no new load and no texture upload. Models of an asset share its geometry, textures, and
compiled materials, and have their own material instances. Thus a base color or variant stays
with its model.

A cached asset stays in memory while no model shows it: the file's source data, and its decoded
textures and geometry in GPU memory. The cache counts filly's estimate of this memory
(`Asset.memory`: CPU bytes plus GPU bytes). When a new asset goes past the limit, the least
recently used assets close first. An asset whose estimate is above the limit shows its one
model and then releases its source data; the file is not cached. Models that the experiment
shows do not count, also when they come from a cached asset. The limit is on the memory that
the cache keeps without being asked, not on the experimenter's models.

Online, the CPU part of the cache is in the WebAssembly memory, which never gets smaller. When
the cache removes an asset, filly can use that memory again, but the browser does not get it
back. Thus, online, the limit sets the highest memory use of the cache, not its current use.
That is why the online default (256 MiB) is lower than the local default (1 GiB).

## Supported PsychoPy versions

The plugin needs PsychoPy 2024.2 or later, because 2024.2 is the first release whose standalone
install ships Python 3.10, and filly needs Python 3.10 or later. The tests run with PsychoPy
2024.2.4 (Python 3.10) and 2026.2.4 (Python 3.11).
