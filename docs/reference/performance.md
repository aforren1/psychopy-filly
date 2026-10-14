# Performance

Measurements of psychopy-filly on one computer. Other computers give other numbers. Use them as
an order of magnitude, and measure your own experiment on the computer that runs it.

## Test computer

| Item | Value |
| --- | --- |
| Machine | Laptop with two GPUs: Intel Iris Xe, and an NVIDIA RTX A500 Laptop GPU. Results are for the Intel GPU unless a table names the NVIDIA GPU |
| System | Windows 11, 60 Hz display |
| Browsers | Chrome, Edge, and Firefox. The Intel GPU, through ANGLE on Direct3D 11 |

filly's own measurements on this laptop, with driver versions and the method, are in filly's
[performance reference](https://github.com/aforren1/filly/blob/main/docs/reference/performance.md).

## Model changes

Measured on 2026-10-04 with the runtime of that date.

| Measurement | Local | Chrome |
| --- | --- | --- |
| Worst of the first 10 frames after a model change, without the wait for the GPU | 39 to 398 ms (draw time) | 33 to 250 ms (frame interval) |
| The same, with the wait for the GPU that `setModel()` now does | 1.6 to 5.6 ms | 17 ms |

The first load of a file takes tens to hundreds of milliseconds, and more for the first file
that uses a material type.

## Model cache

Measured locally by 2026-10-05, with the earlier cache, which kept cloned copies of the
models instead of filly assets:

| Measurement | Value |
| --- | --- |
| Change between two cached models (7.4 MB and 2.2 MB files), median | 5 to 7 ms |
| The same change without the cache, median | 84 to 119 ms |
| filly's memory estimate of the cached 7.4 MB file, which has large textures | 79 MiB |
| filly's memory estimate of the cached 2.2 MB file | 18 MiB |

With the current cache of filly assets (2026-10-12), a new model of a cached file took 0.1 to
8 ms, where a load took 1 to 150 ms, for files of 0.07 to 7.4 MB.

## Picking, local

Measured on 2026-10-13 with a full-screen 1920 x 1080 scene and one check per 30 frames.

Time of one check (a render of the shown image with a pick query, and a wait for the GPU):

| Scene | Intel Iris Xe | NVIDIA RTX A500 |
| --- | --- | --- |
| Lit cube | 6 to 8 ms | 1.3 to 2.8 ms |
| ChronographWatch | 12 to 15 ms | 2 to 9 ms |

Click frames in which the scene also changed, as with a moving model, render twice:

| Scene | Intel Iris Xe | NVIDIA RTX A500 |
| --- | --- | --- |
| Lit cube | Median click-frame interval 18 to 21 ms | No dropped frames |
| ChronographWatch | Click frames of 27 to 29 ms: one dropped frame | No dropped frames |

The first pick of a renderer costs some GPU drivers a one-time delay: 45 to 100 ms on Intel
Iris Xe. With **Mouse picking** on, the window pays it during setup instead: 60 to 75 ms on
Intel Iris Xe.

## Picking, online

The browser gives the answer of a pick 2 or 3 frames after the render.

## Online stimulus creation

Measured on 2026-10-03 with a rotating cube, two runs per browser. The runtime of that date had
one component; creating a scene and its model now does the same steps in two calls.

| | Chrome | Edge | Firefox |
| --- | --- | --- | --- |
| Creating the stimulus, including the module start | 0.41 to 0.44 s | 0.45 to 0.66 s | 0.44 to 0.53 s |
| Shader compilation during creation, without blocking | 190 to 195 ms | 216 to 278 ms | none: compiles at the first render |
| First render | 29 to 31 ms | 29 to 45 ms | 237 to 269 ms |
| Longest frame during creation | 67 to 100 ms | 83 to 150 ms | 250 to 283 ms |
| CPU time of a render, median (95th percentile) | 0.6 to 0.7 (1.4) ms | 0.6 (1.2 to 1.4) ms | 1 (2) ms |
| Frame interval, median | 16.7 ms | 16.7 ms | 16.7 ms |

- Firefox's timer has a resolution of 1 ms on pages that are not cross-origin isolated.
- Before creation yielded frames between its steps, the page showed no new frame for about
  0.5 s per stimulus.
- filly's WebAssembly module is 3.5 MB, or 1.4 MB compressed.
