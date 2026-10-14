# Run an experiment online

Run an experiment with 3D Scene and 3D Model components in a browser, for example on Pavlovia.

The online components were tested in Chrome, Edge, and Firefox on one Windows laptop. They were
not tested on Pavlovia.

## Compile and upload

1. Save the experiment.
2. Compile it to JavaScript, or sync it to Pavlovia. The compile copies a folder named `filly`
   into the experiment folder. The folder holds filly's WebAssembly build and the PsychoJS
   runtime of the plugin.
3. Keep the `filly` folder with the experiment. Pavlovia sync uploads it with the other files.

The compile copies the default model to `filly/default.glb` only if the experiment can show it:
a constant **Model file** of `default.glb`, or a model that changes per trial.

The experiment loads the files in `filly` from its own server. It needs no special server
headers. It also works on a page with cross-origin isolation headers (COOP and COEP). See
[cross-origin isolation](../explanation/how-it-works.md#cross-origin-isolation).

## Limits online

- The participant's browser must support WebGL2. On Android and other mobile devices that are
  not Apple devices, PsychoJS uses WebGL1. There the component stops the experiment with an
  error message.
- PsychoJS applies parameter changes one frame later than PsychoPy, for every stimulus. Thus a
  change of a 3D Scene or 3D Model shows one frame later than in a local experiment.
- Color parameters accept only the color spaces `rgb`, `rgb255`, `hex`, and `named`.
- When a model changes per trial, the scene is not drawn until the new model has loaded. Load
  it during a static period; see
  [change the model per trial](change-model-per-trial.md#load-the-model-before-the-trial).
- The default model cache limit is 256 MiB, and the cache memory is not given back to the
  browser. See [set the model cache limit](change-model-per-trial.md#set-the-model-cache-limit).
- Clicks on models need the pointer to be over the scene for at least 3 frames before the
  click. Touch screens do not give that. See
  [select models with the mouse](select-models.md#online).
- Creating a scene or a model takes about half a second, and some frames during creation are
  long. Firefox compiles the shaders at the first render, so its first render takes longer.
  The generated code creates the stimuli before the first routine. See
  [performance](../reference/performance.md#online-stimulus-creation).
- The online image matches the local image within one 8-bit level in flat regions. Pixels on
  color edges can differ more. See
  [difference from local output](../explanation/how-it-works.md#difference-from-local-output).
