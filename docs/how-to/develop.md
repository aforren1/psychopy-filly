# Develop the plugin

Install psychopy-filly for development, run the tests, update the web build, and publish a
release. This page is for maintainers.

## Install for development

```powershell
uv pip install --python <env>\Scripts\python.exe -e . --no-deps
```

The package requires `psychopy>=2024.2`. The standalone PsychoPy app registers the `psychopy`
distribution, so installing the plugin there adds nothing else. An environment with only
`psychopy-lib` gets `psychopy` installed next to it: use `--no-deps` there.

The PsychoPy app keeps its own copy of the packages that it installs, in
`%APPDATA%\psychopy3\packages` on Windows, and it keeps the component classes that it loaded.
After a change, install the plugin in the app again and restart the app.

## Test

The tested PsychoPy versions are 2024.2.4 and 2026.2.4, the CI matrix in
`.github/workflows/release.yml`. Make one environment for each:

- PsychoPy 2024.2.4 needs Python 3.10. Earlier standalone installs ship Python 3.8 or earlier,
  and filly needs Python 3.10 or later.
- PsychoPy 2026.2.4: use Python 3.11.

```powershell
uv venv --python 3.10 <env>
uv pip install --python <env>\Scripts\python.exe --override tests\psychopy-overrides.txt psychopy==2024.2.4 -e .[tests]
```

For PsychoPy 2026.2.4, use `--python 3.11` and `psychopy==2026.2.4`.

`tests/psychopy-overrides.txt` removes two requirements of the `psychopy` distribution:
`pypi-search` (2023.2 to 2024.2), which PyPI no longer has, and wxPython on Linux (2024.2),
which has no Linux wheels on PyPI. The tests do not use either.

The command installs filly from PyPI. To test unreleased filly changes, add the path of a
filly checkout, for example `..\filly`, to the command. This builds filly.

CI tests with both filly versions. `.github/workflows/release.yml` uses the filly release on
PyPI. `.github/workflows/filly-main.yml` uses the wheels of filly's latest successful build of
its main branch. It runs daily and at each push, and it also runs the display tests, under Xvfb
with software OpenGL.

Run the tests:

```powershell
<env>\Scripts\python.exe -m pytest -m "not display and not browser"   # code generation
<env>\Scripts\python.exe -m pytest -m display                         # opens windows, needs filly
cd tests\web; npm install; cd ..\..
<env>\Scripts\python.exe -m pytest -m browser                         # runs experiments in browsers
```

- The browser tests need Node.js and an installed browser. They use Chrome by default. Set
  `FILLY_TEST_BROWSERS=chrome,edge,firefox` for more. On their first run, they download the
  PsychoJS library of the installed PsychoPy version from lib.pavlovia.org into
  `tests/web/.cache`.
- On Windows, the tests point `APPDATA` to an empty folder. PsychoPy adds the app's plugin
  folder (`%APPDATA%\psychopy3\packages`) to `sys.path`, and copies of filly or psychopy-filly
  that the app installed there would replace the code under test.
- The display tests read the back buffer. On the test laptop, front-buffer reads of windows
  with a framebuffer object (FBO) returned only the background, while the screen showed the
  stimuli.
- `tests/test_web.py` checks that the browser image matches desktop filly. A browser test also
  serves an experiment with cross-origin isolation headers.

### Update the expected script

`tests/data/filly_cube.py` is the expected script for PsychoPy 2026.2.4. The test that compares
it skips other versions. After an intended change to the generated code, write it again with
PsychoPy 2026.2.4:

```powershell
<env>\Scripts\python.exe -c "import sys; sys.path.insert(0, 'tests'); import builder_helpers as h; open('tests/data/filly_cube.py', 'w', encoding='utf-8', newline='\n').write(h.compile_script(h.build_experiment()))"
```

### PsychoPy export defects

Two defects of the PsychoJS export in psychopy-lib 2026.2.4 stop an experiment in the browser,
with or without this plugin, for experiments made outside the Builder app. In practice, this
means the tests:

- The default participant value is a Python f-string. The export cannot parse its own script,
  so it adds no variable declarations, and the script fails at its first assignment.
- A routine without a maximum duration writes `trialMaxDuration = None`.

The test helper `compile_js()` in `tests/builder_helpers.py` avoids both.

### Tools

- `tools/check_builder.py OUT_DIR` checks plugin discovery, the wxPython Builder compile, and
  the calls that PsychoPy Studio makes. It needs no display and no filly, so it also runs in
  the standalone app's Python. The components also load and compile in the PsychoPy 2026.1.2
  app.
- `tools/make_icons.py` writes the placeholder icons.

## Update the web build

`psychopy_filly/web` holds a copy of filly's web build. To update it:

1. In filly, build the Filament WebAssembly SDK once, then filly's module, on Linux or WSL:
   `web/tools/build_filament_web.sh`, then `web/tools/build_filly_web.sh`. See filly's
   [build guide](https://github.com/aforren1/filly/blob/main/docs/how-to/build.md#build-for-the-web).
2. In psychopy-filly, run `python tools/vendor_web.py ../filly/build/web`. It copies the files
   and writes their sizes and SHA-256 hashes to `psychopy_filly/web/VENDOR.json`.

Do not edit the copied files by hand. `psychopy_filly/web/filly-psychojs.js` is this plugin's
own code, not part of the copy.

The default model is `filly.samples.SUZANNE`. The JavaScript compile copies it to the
experiment's `filly` folder as `default.glb`, only if the experiment can show it.

## Publish a release

The [Build and release](../../.github/workflows/release.yml) workflow builds the sdist and the
wheel on every push and pull request. It tests the built wheel with the tests that need no
display, with each tested PsychoPy version. A pushed tag `vX.Y.Z` that matches the version in
`pyproject.toml` publishes both to PyPI through trusted publishing. A manual run can publish to
TestPyPI instead.

Set up once: on pypi.org and test.pypi.org, add a pending publisher for project
`psychopy-filly`, owner `aforren1`, repository `psychopy-filly`, workflow `release.yml`, with
the environments `pypi` and `testpypi`. Create the same environments in the GitHub repository
settings.

To publish:

1. The workflow installs filly from PyPI. If the plugin needs filly changes that are not
   released, publish filly first.
2. For a final release, require a final filly in `pyproject.toml`, for example
   `filly>=0.2.0,<0.3`.
3. Set `version` in `pyproject.toml`, commit, and push a tag such as `v0.1.0`.
