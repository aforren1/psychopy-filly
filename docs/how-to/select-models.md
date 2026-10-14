# Select models with the mouse

Let participants click 3D models, and log which model, node, and surface point they clicked.

A click is on a model when the image that the window showed has that model in front at the
click point. The model's bounding box does not count. Cut-out (mask) regions and blended
materials let the click pass to what is behind them. The background, the environment, and
hidden models are not hits.

## Set up the Mouse component

1. Add a Mouse component to the routine, below the 3D Scene and 3D Model components.
2. In **Clickable stimuli**, type the names of the 3D Model components, for example
   `cube, sphere`. The name of a 3D Scene accepts a click on any of its models.
3. Optional: to end the routine on a click on a model, set **End Routine on press** to
   **valid click**.
4. Keep `name` in **Store params for clicked**. The data then has the component name of the
   clicked model in `mouse.clicked_name`.

## Log the model, node, and point

The 3D Scene keeps the result of the last check as `scene.lastPick`. See
[ScenePick](../reference/runtime.md#scenepick) and [SceneHit](../reference/runtime.md#scenehit)
for all attributes.

Add a Code component below the Mouse component. In **End Routine**, Python:

```python
pick = scene.lastPick
hit = pick.result if pick is not None else None
thisExp.addData('pick.model', hit.modelName if hit else None)
thisExp.addData('pick.node', hit.node if hit else None)
thisExp.addData('pick.point', list(hit.point) if hit else None)
thisExp.addData('pick.depth', hit.depth if hit else None)
thisExp.addData('pick.frame', pick.frame if pick is not None else None)
thisExp.addData('pick.flipTime', pick.flipTime if pick is not None else None)
```

For an online experiment, set the Code component's type to **Both**, and use this JavaScript:

```javascript
const pick = scene.lastPick;
const hit = pick ? pick.result : null;
psychoJS.experiment.addData('pick.model', hit ? hit.modelName : null);
psychoJS.experiment.addData('pick.node', hit ? hit.node : null);
psychoJS.experiment.addData('pick.point', hit ? hit.point : null);
psychoJS.experiment.addData('pick.depth', hit ? hit.depth : null);
psychoJS.experiment.addData('pick.frame', pick ? pick.frame : null);
psychoJS.experiment.addData('pick.flipTime', pick ? pick.flipTime : null);
```

## Find the model at a point without a Mouse component

To check a point in each frame, or a point that does not come from a click, call
`scene.pick(pos)` with a position in the window's units, such as `mouse.getPos()`. It returns a
pick at once. The answer arrives some frames later. Call `pick.ready()` once per frame, and read
`pick.result` when `ready()` returns true.

## Moving models

A pick describes the image that the window showed when the code ran: the scene as it was last
rendered. Changes that the routine makes in the same frame apply after the pick. Thus a click
on a moving model counts where the participant saw the model. Log `flipTime` to know when that
image appeared. For the reason, see
[how the plugin works](../explanation/how-it-works.md#picking).

## Timing

Locally, a check renders the shown image again and waits for the GPU. This happens only for a
click inside the scene's image. If the scene also changes in the click frame, that frame
renders twice. With a heavy scene on an integrated GPU, a click frame can then drop a frame.
See [performance](../reference/performance.md#picking-local) for measured costs.

The first pick of a window costs some GPU drivers a one-time delay of tens of milliseconds. The
plugin moves it to the start of the experiment when a 3D Scene picks:

- a Mouse component lists the scene or one of its models, or
- a Code component calls `pick()`, `contains()`, `isPressedIn()`, or `lastPick` on them, or
- the scene's **Mouse picking** checkbox (**Layout** tab) is on.

The compile does not find code that reaches the objects another way, for example through a
list. For such code, turn on **Mouse picking**, or the first click is slow.

## Online

The browser gives the answer of a pick only 2 or 3 frames after the render, but the Mouse
component needs it in the frame of the click. Thus:

- The scene picks the pointer position after each frame in which the pointer moved over the
  scene or the image changed. The compile turns this on when a Mouse component names the scene
  or one of its models. In code, set `scene.trackPointer = true`.
- A click then uses the answer for the click pixel. That answer describes an image of a few
  frames before the click.
- If no answer is there for the click pixel, the check returns false and starts a pick. This
  happens when the click comes less than 3 frames after the pointer arrived, for example on a
  touch screen. For such devices, use `scene.pick()` in a Code component instead.
- Each tracked frame renders a pick query. When the scene renders in that frame anyway, the
  query adds only Filament's depth pass for picking. Otherwise the scene renders once more.
