# Component parameters

The parameters of the **3D Scene** and **3D Model** components, in dialog order. The tables
follow `SCENE_PARAMS` in `psychopy_filly/components/scene3d/__init__.py` and `MODEL_PARAMS` in
`psychopy_filly/components/model3d/__init__.py`.

## Conventions

- **Updates** lists the update modes that a parameter accepts:
  - constant: the parameter cannot change during the experiment.
  - every repeat: **constant** or **set every repeat**.
  - every frame: **constant**, **set every repeat**, or **set every frame**.
- A blank field takes the default.
- Colors use the component's **Color space**. Online, PsychoJS accepts only `rgb`, `rgb255`,
  `hex`, and `named`.
- Colors are display values, as for other PsychoPy stimuli: an unlit surface or the background
  shows the given color.
- A name that is all digits is an index, unless the model has an item with that name.
- Each parameter that can change has a `set<Name>()` method in the
  [runtime API](runtime.md).

## 3D Scene

On the **Basic** tab, **Position**, **Size**, **Spatial units**, **Orientation**, and
**Opacity** place the image, as for an image stimulus. They need no new render. The default
size is `(0.5, 0.5)`. **Color space** applies to the light and background colors.

| Tab | Parameter | Default | Updates | Meaning |
| --- | --- | --- | --- | --- |
| Layout | Render size [w,h] | the initial size in window pixels, times the render scale | constant | Pixels of the rendered image. Set it if the size changes during the experiment |
| Layout | Render scale | 1 | constant | Factor for the automatic render size, in (0, 2]. Below 1 renders fewer pixels and stretches the image bilinearly, which blurs edges and fine detail. 2 renders twice the pixels and averages them. Not used with a render size |
| Layout | Mouse picking | off | constant | Prepare the window for clicks on the scene's models when the experiment starts, so that the first click is not slow. See [timing](../how-to/select-models.md#timing) |
| Camera | Projection | perspective | constant | perspective or orthographic |
| Camera | Field of view (deg) | 30 | every frame | Vertical field of view of the perspective projection |
| Camera | View height | from the framing | every frame | Height of the orthographic view in scene units |
| Camera | Camera position [x,y,z] | framing | every frame | Camera position in scene units. Blank: see [camera framing](#camera-framing) |
| Camera | Look at [x,y,z] | `(0, 0, 0)` | every frame | Point that the camera looks at when the camera position is set |
| Camera | Framing fill | 0.9 | every frame | Fraction of the narrower image axis that the framed models span, in (0, 1] |
| Camera | Near clip, Far clip | automatic | every frame | Clipping planes in scene units. Automatic planes enclose the bounding spheres of the models at their current poses |
| Camera | Exposure (EV100) | 15 | every frame | Lower values give a brighter image |
| Lighting | Directional light | on | constant | Add one directional light |
| Lighting | Light direction [x,y,z] | `(-1, -1, -2)` | every frame | Direction in which the light shines |
| Lighting | Light intensity (lux) | 100000 | every frame | Illuminance of the directional light |
| Lighting | Light color | white | every frame | |
| Lighting | Environment light | uniform | constant | Image-based light: `uniform` (even from all directions), `none`, or `file` |
| Lighting | Environment file | | constant | A 2:1 panorama (`.hdr`, `.png`, `.jpg`) or a KTX cubemap made by Filament's cmgen. Used with `file` |
| Lighting | Environment intensity (lux) | 20000 | every frame | |
| Lighting | Environment rotation (deg) | 0 | every frame | Rotation about the vertical axis |
| Lighting | Show environment | off | constant | Draw the environment behind the models instead of the background |
| Appearance | Background color | transparent | every frame | An opaque color, or **Show environment**, also saves the extra pass that transparent output costs |
| Rendering | Tone mapping | linear | constant | `linear` clamps. `aces_legacy` matches Filament's gltf_viewer. Also `aces`, `filmic`, `pbr_neutral`, `gt7`, `agx`, `agx_punchy`, `agx_golden`, `generic` |
| Rendering | Antialiasing | fxaa | constant | `none` or `fxaa` (post-process) |
| Rendering | MSAA samples | 1 | constant | 1, 2, 4, or 8 |
| Rendering | Shadows | off | constant | Shadows from the directional light. Glass refracts without a setting |
| Rendering | Model cache (MiB) | the runtime default | constant | Memory limit of the window's model cache: a number of MiB, `0` for off, or `unlimited`. See [the model cache](../how-to/change-model-per-trial.md#set-the-model-cache-limit) |

### Camera framing

With **Camera position** blank, the camera is on the +Z axis and looks along -Z at the origin.
It frames all models of the scene, as placed when they loaded, so that they fill **Framing
fill** of the narrower image axis. Loading or closing a model frames the scene again. Later
changes of pose, visibility, or animation do not move the camera.

Without other settings, one directional light and even ambient light (the uniform environment)
illuminate the models. The background is transparent, so the models cover only their own
pixels.

## 3D Model

The model is visible in its scene from the component's start to its stop.

| Tab | Parameter | Default | Updates | Meaning |
| --- | --- | --- | --- | --- |
| Basic | Scene | `scene` | constant | Name of the 3D Scene component that shows the model. It must come before this component: in an earlier routine, or above it in the same routine |
| Basic | Model file | `default.glb` | every repeat, or set during a static period | A `.glb` file (preferred) or a `.gltf` file. See [model files](#model-files) and [change the model per trial](../how-to/change-model-per-trial.md) |
| Basic | Rotation [x,y,z] | `(0, 0, 0)` | every frame | Degrees about X, then Y, then Z, for example `(0, 45*t, 0)` |
| Basic | Model position [x,y,z] | `(0, 0, 0)` | every frame | Scene units (glTF units are meters) |
| Basic | Model scale | `1` | every frame | One factor, or `[x,y,z]` factors |
| Basic | Center model | on | constant | Put the center of the bounding box at the model position, so that the model rotates about its center. Off: the model rotates about its own origin |
| File | Lights from file | on | constant | Keep the lights in the model file |
| File | Camera from file | | constant | Name or node index of a camera in the model file. The scene renders through it, and the scene's camera settings, except exposure, do not apply. One model per scene |
| Appearance | Material variant | | every repeat | Name or index of a material variant |
| Appearance | Material name | all materials | every repeat | Material that the base color changes |
| Appearance | Base color | as in the file | every frame | Replaces the material's base color. The alpha stays |
| Appearance | Color space | rgb | constant | Color space of the base color |
| Animation | Animation clip | no animation | every repeat | Name or index of an animation clip |
| Animation | Animation time (s) | the clip's first pose | every frame | Time in the clip. See [play an animation](../how-to/play-animation.md) |
| Animation | Loop animation | on | constant | Wrap times beyond the clip duration. Off: the last pose holds |

### Model files

- The default, `default.glb`, is filly's sample model: Suzanne, in blue metal (CC0 1.0). A file
  named `default.glb` in the experiment folder replaces it.
- PsychoPy does not know the external `.bin` and image files of a `.gltf` file. Keep them in the
  experiment folder.
- With more 3D Models in one scene, the models hide each other where they overlap. With
  **Shadows** on, they cast shadows on each other. Place them apart with **Model position**. Two
  scenes are two separate images: their models do not interact.

### Names in a model file

To list the animation clips, material variants, materials, and cameras in a model, run:

```powershell
python -m psychopy_filly.gltf_info model.glb
```

It also lists lights, morph targets, skins with their bones, and the node tree.

## Compile checks

The compile stops with an error in these cases:

- A 3D Model's **Scene** is not the name of a 3D Scene component.
- The scene comes after the model: in a later routine, or below it in the same routine.
- Two models of one scene set **Camera from file**.

If **Animation clip**, **Material variant**, **Material name**, or **Camera from file** has a
name that the model does not have, the compile logs a warning with the names that the model
has, and the experiment stops with an error that lists them. For a model that changes per
trial, the runtime checks the names when the model renders first.
