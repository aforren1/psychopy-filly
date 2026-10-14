# Play an animation

Play an animation clip from a glTF model, or show one pose of it.

1. In the 3D Model component, on the **Animation** tab, set **Animation clip** to the name or
   index of a clip. To list the clips of a model, see
   [names in a model file](../reference/parameters.md#names-in-a-model-file).
2. Set **Animation time (s)** and its update mode from this table. The examples use a 3D Model
   named `cube`:

| Goal | Animation time (s) | Update mode |
| --- | --- | --- |
| Play from the model's start | `t - cube.tStart` | set every frame |
| Play at half speed | `0.5 * (t - cube.tStart)` | set every frame |
| Play from the routine's start | `t` | set every frame |
| One pose per trial | `$pose_time`, a conditions column | set every repeat |
| A fixed pose | a number, for example `1.2` | constant |

With `t - cube.tStart`, the clip starts at 0 when the model appears: `cube.tStart` is the
model's start time, and the time updates only while the model shows.

With **Loop animation** on (the default), times after the end of the clip wrap to its start.
With it off, those times hold the last pose.
