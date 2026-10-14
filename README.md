# psychopy-filly

A PsychoPy plugin that shows 3D glTF models in Builder experiments. It adds two components to
the **Stimuli** category:

- **3D Scene** shows the rendered image. It has the camera, the lights, the environment, and
  the rendering settings. You place it like an image, with **Position**, **Size**, and
  **Spatial units**.
- **3D Model** adds one glTF model to a scene. It has the model file, its pose, its materials,
  and its animation.

[filly](https://github.com/aforren1/filly) renders the models. The components work in local
experiments (PsychoPy) and in online experiments (PsychoJS).

## Requirements

- Windows or Linux. filly does not support macOS.
- PsychoPy 2024.2 or later. Tested with PsychoPy 2024.2.4 and 2026.2.4.
- The pyglet window backend and an "average" blend mode (the defaults).
- Online: a browser with WebGL2.

If the window shows no stimuli at all, also without a 3D Scene, set **Blend mode** to
**average (no FBO)** in the experiment settings, on the **Screen** tab.

## Install

Install psychopy-filly with PsychoPy's plugin manager, or with pip in the Python environment
that runs PsychoPy:

```powershell
python -m pip install psychopy-filly
```

## Quick start

1. In a routine, add a **3D Scene** component. Its default name is `scene`.
2. Below it, add a **3D Model** component. Its **Scene** is `scene` by default; if you renamed
   the 3D Scene component, use that name.
3. Optional: set **Model file** to a `.glb` file. The default, `default.glb`, is filly's sample
   model: Suzanne, in blue metal.
4. Optional: to turn the model, set **Rotation [x,y,z]** to `(0, 90*t, 0)` and its update mode
   to **set every frame**.
5. Run the experiment.

The camera frames the models automatically, and one directional light illuminates them. For
more models in the same image, add more 3D Model components with the same **Scene**.

## Run online

Compile the experiment to JavaScript, or sync it to Pavlovia. The compile adds a `filly` folder
to the experiment folder. Keep that folder with the experiment. See
[run an experiment online](https://github.com/aforren1/psychopy-filly/blob/main/docs/how-to/run-online.md)
for the limits.

## Documentation

- How-to guides:
  [change the model per trial](https://github.com/aforren1/psychopy-filly/blob/main/docs/how-to/change-model-per-trial.md),
  [select models with the mouse](https://github.com/aforren1/psychopy-filly/blob/main/docs/how-to/select-models.md),
  [play an animation](https://github.com/aforren1/psychopy-filly/blob/main/docs/how-to/play-animation.md),
  [run an experiment online](https://github.com/aforren1/psychopy-filly/blob/main/docs/how-to/run-online.md),
  [develop the plugin](https://github.com/aforren1/psychopy-filly/blob/main/docs/how-to/develop.md)
- Reference:
  [component parameters](https://github.com/aforren1/psychopy-filly/blob/main/docs/reference/parameters.md),
  [runtime API for Code components](https://github.com/aforren1/psychopy-filly/blob/main/docs/reference/runtime.md),
  [performance](https://github.com/aforren1/psychopy-filly/blob/main/docs/reference/performance.md)
- Explanation:
  [how the plugin works](https://github.com/aforren1/psychopy-filly/blob/main/docs/explanation/how-it-works.md)

## License

MIT. See [LICENSE](https://github.com/aforren1/psychopy-filly/blob/main/LICENSE). The files in
`psychopy_filly/web` other than `filly-psychojs.js` are from filly and its dependencies. Their
licenses are in `psychopy_filly/web/licenses`. The sample model is modified from Suzanne by
Norbert Nopper (UX3D), from the Khronos glTF Sample Assets, under CC0 1.0.
