# Runtime API

The generated code calls a runtime module. Code components can use the same objects. The
module is the only part of the plugin that calls filly.

| Target | Module | Name in the generated code |
| --- | --- | --- |
| PsychoPy | `psychopy_filly.runtime` | `filly_runtime` |
| PsychoJS | `filly/filly-psychojs.js` in the experiment folder | `filly_runtime` |

A 3D Scene component is a `SceneStim`, and a 3D Model component is a `SceneModel`, with the
component name as the variable name. The JavaScript API has the same names and parameters,
except where this page says otherwise. For what the generated code looks like, see
[how the plugin works](../explanation/how-it-works.md#generated-code).

## SceneStim

A filly scene rendered into a texture and drawn in the window.

```python
SceneStim(win, *, pos=(0, 0), size, units=None, ori=0.0, opacity=None, <scene parameters>,
          colorSpace="rgb", picking=False, name=None, depth=0)
```

```javascript
scene = await filly_runtime.SceneStim.create({ win, name, pos, size, units, ori, opacity,
  <scene parameters>, colorSpace, depth, trackPointer });
```

- The keyword arguments have the names of the [3D Scene parameters](parameters.md#3d-scene):
  `resolution`, `renderScale`, `projection`, `fov`, `viewHeight`, `camPos`, `lookAt`, `near`,
  `far`, `fill`, `exposure`, `light`, `lightDir`, `lightIntensity`, `lightColor`,
  `environment`, `envFile`, `envIntensity`, `envRotation`, `envVisible`, `backgroundColor`,
  `toneMapping`, `antialiasing`, `msaa`, `shadows`, `modelCacheMiB`, `picking`. Arguments that
  are `None` take their default.
- `win` must use the pyglet backend and the `avg` blend mode. `size` is required.
- `pos`, `size`, `units`, `ori`, and `opacity` place the texture as for `visual.ImageStim`, and
  need no new render.

| Member | Meaning |
| --- | --- |
| `set<Name>(value, log=None)` | Set a parameter that can change: `setFov`, `setViewHeight`, `setCamPos`, `setLookAt`, `setNear`, `setFar`, `setFill`, `setExposure`, `setLightDir`, `setLightIntensity`, `setLightColor`, `setEnvIntensity`, `setEnvRotation`, `setBackgroundColor`, and `setPos`, `setSize`, `setOri`, `setOpacity`. `None` sets the default where the parameter has a blank default |
| `draw()` | Render if the scene or one of its models changed since the last render, then draw the texture |
| `invalidate()` | Render again at the next draw. Call it after you change the filly scene, camera, light, or a model directly: the stimulus tracks only changes made through setters |
| `pick(pos, units=None)` | Start to find the model that the window shows at `pos`, and return a [`ScenePick`](#scenepick) at once. `units` default: the window's units, as for mouse positions |
| `contains(x, y=None, units=None)` | Whether the window shows a model of this scene at a point: a Mouse, a point, or x and y. A Mouse component can thus list the scene as a clickable stimulus |
| `lastPick` | The `ScenePick` that answered the last `contains()` check of the scene or one of its models, or `None`. Online, a check without an answer leaves it unchanged |
| `models` | The scene's `SceneModel` objects |
| `camera` | The filly camera |
| `trackPointer` | JavaScript only. Pick the pointer position after each frame in which the pointer moved or the image changed, so that `contains()` has an answer at a click. The compile sets it when a Mouse component names the scene or one of its models |
| `close()` | Release the models, the target, the scene, and the camera. Repeated calls are valid |

`pick()` and `contains()` need a render size of at least 32 x 32 pixels. A point outside the
image, or a scene that the window has not shown, is an immediate miss without a render.

Locally, `contains()` waits for the answer: it renders and waits for the GPU, but only for a
point inside the image. Online, it returns the latest answer for the same pixel that has
arrived, or `false` and starts a pick. See
[select models with the mouse](../how-to/select-models.md#online).

`picking=True` moves a one-time driver cost from the first pick to the creation of the scene.
Picking works without it.

## SceneModel

A glTF model in a `SceneStim`.

```python
SceneModel(scene, model, *, <model parameters>, colorSpace="rgb", name=None)
```

```javascript
cube = await filly_runtime.SceneModel.create({ scene, name, model, <model parameters>, colorSpace });
```

- The keyword arguments have the names of the [3D Model parameters](parameters.md#3d-model):
  `rotation`, `modelPos`, `modelScale`, `center`, `fileCamera`, `fileLights`, `variant`,
  `material`, `baseColor`, `animation`, `animTime`, `animLoop`.
- `model` is the path of a `.glb` or `.gltf` file. `'default.glb'` is filly's sample model,
  unless the working directory has a file of that name. `None`: no model until `setModel()`.
  Builder uses `None` when the model changes per repeat.
- The model is hidden until `setAutoDraw(True)`. Builder calls it when the component starts,
  and `setAutoDraw(False)` when it stops.

| Member | Meaning |
| --- | --- |
| `set<Name>(value, log=None)` | `setRotation`, `setModelPos`, `setModelScale`, `setVariant`, `setMaterial`, `setBaseColor`, `setAnimation`, `setAnimTime` |
| `setModel(model)` | Show another model file. See below |
| `setAutoDraw(value)` | Show (`True`) or hide (`False`) the model in its scene |
| `contains(x, y=None, units=None)` | Whether the window shows this model at a point, in front of everything else. Arguments as for `SceneStim.contains()`. The scene's `lastPick` keeps the pick |
| `model` | The filly model, or `None` before the first model loads |
| `scene` | The `SceneStim` |
| `close()` | Remove the model from its scene. Repeated calls are valid |

`setModel()` loads the file at once. It returns after the shaders are compiled and the
textures are on the GPU, so the first frame that shows the model does not wait for them. In
JavaScript it returns a promise, and the scene is not drawn until the promise resolves. The
other settings stay and apply to the new model, so its clip, variant, and material names must
exist in it. The scene frames its models again. Handles to the old model are closed. A file
that an earlier `setModel()` of the window loaded, and that the cache kept, becomes a new model
of the kept copy. The model given at creation is not cached.

## ScenePick

A pick that `SceneStim.pick()` or `contains()` started: what the window showed at a point.

| Member | Meaning |
| --- | --- |
| `pos`, `units` | The point as given |
| `pixel` | The render-target pixel of the point, from the lower-left corner. `None` (`null`) for a point outside the image |
| `frame` | filly's frame number of the render that answered the pick. `None` without a render |
| `flipTime` | Time of the window flip that first showed the picked image, on the clock of the log file. `None` without a render |
| `ready()` | Whether the answer has arrived. It does not wait for the GPU: call it once per frame |
| `result` | A [`SceneHit`](#scenehit), or `None` (`null`) where the window showed no model. Raises an error until `ready()` returns true |

## SceneHit

The model surface that a pick found.

| Attribute | Meaning |
| --- | --- |
| `model` | The `SceneModel` that the window showed at the point. `None` for a filly model that no `SceneModel` owns, such as one that code added to the filly scene |
| `modelName` | Its name: the Builder component name |
| `node` | Name of the glTF node that carries the mesh, or `None` for an unnamed node |
| `nodeIndex` | Index of that node in the glTF file. Each instance of an `EXT_mesh_gpu_instancing` node has its own index |
| `point` | World position of the surface at the center of the picked pixel, in scene units |
| `depth` | Distance from the camera to `point` along the camera's viewing direction |

## Module functions and settings

| Name | Meaning |
| --- | --- |
| `close_all()` (JavaScript: `await closeAll()`) | Close all stimuli and renderers that the module created. The windows stay open. Repeated calls are valid. The generated code calls it at the end of the experiment |
| `MODEL_CACHE_MAX_BYTES` | Python. Memory limit of each window's model cache, in bytes of filly's estimate. Default `2**30` (1 GiB). `0` turns the cache off; `None` removes the limit. Change it before the experiment calls `setModel()` |
| `modelCache.maxBytes` | JavaScript. The same limit online. Default `256 * 2 ** 20` (256 MiB). `0` turns the cache off; `Infinity` or `null` removes the limit |
| `DEFAULT_MODEL` | `'default.glb'`, the 3D Model component's default model |

A 3D Scene's **Model cache (MiB)** parameter overrides the module setting for its window.
