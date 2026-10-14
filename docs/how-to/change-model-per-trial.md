# Change the model per trial

Show a different glTF model in each trial, from a column of the conditions file.

## Set the model file per trial

1. In the conditions file, add a column with the model file names, for example `modelFile`.
2. In the 3D Model component, set **Model file** to `$modelFile`.
3. Set the update mode of **Model file** to **set every repeat**.

The component then behaves as follows:

- It has no model until the first trial sets the file. Nothing loads at the start of the
  experiment.
- Each change loads the new file when the routine starts. The other settings stay and apply to
  the new model. Thus the trial's clip, variant, and material names must exist in the new
  model.
- The scene frames its models again when a model loads, unless **Camera position** is set.
- The load is complete before the routine's first frame: the shaders are compiled and the
  textures are on the GPU. Thus the first frame of the trial does not wait for them.

## Load the model before the trial

The first load of a file takes tens to hundreds of milliseconds, and more for the first file
that uses a material type. To keep this out of the routine's start:

1. Add a **Static** component (an ISI) to the routine, before the model's start.
2. Set the update mode of **Model file** to **set during: trial.ISI** (the name of your
   routine and Static component).

Online, the scene is not drawn until the model has loaded. If the static period is too short,
the scene is missing at the start of the trial. It does not show the previous model.

## Set the model cache limit

Each window keeps a copy of each file that a change loaded. A file that a scene shows again, as
in conditions that alternate models, then loads much faster and needs no texture upload. All
3D Scenes of a window share the cache. Each model has its own material settings, so a base
color or variant stays with its model.

The cache keeps its copies within one memory limit. Set the limit in one of these ways:

| Where | Name | Default | Values |
| --- | --- | --- | --- |
| 3D Scene, **Rendering** tab | **Model cache (MiB)** | blank: the runtime default | A number of MiB; `0`: off; `unlimited`: no limit. The first 3D Scene in a window that sets it decides |
| Local: a Code component, **Before Experiment** | `filly_runtime.MODEL_CACHE_MAX_BYTES` | 1 GiB (`2**30`) | Bytes; `0`: off; `None`: no limit |
| Online: a Code component, **Begin Experiment**, after the 3D Scene component | `filly_runtime.modelCache.maxBytes` | 256 MiB (`256 * 2 ** 20`) | Bytes; `0`: off; `Infinity` or `null`: no limit |

The parameter has priority over the code setting.

To choose a limit:

- A cached copy stays in memory while no model shows it. The cache counts filly's estimate of
  that memory, which can be many times the file size for files with large textures. See
  [performance](../reference/performance.md#model-cache) for examples.
- On a computer with an integrated GPU, the GPU part of a copy also uses system memory.
- Models that the experiment shows do not count against the limit.
- A file whose estimate is above the limit is not cached.
- Online, the cache memory is not given back to the browser. The limit sets the highest memory
  use of the cache, not its current use.

For how the cache works, see
[how the plugin works](../explanation/how-it-works.md#model-cache).
