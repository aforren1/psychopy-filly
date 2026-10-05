"""Run a compiled Builder script and record frames and the close order.

Usage: python run_with_capture.py SCRIPT OUT_DIR FRAME [FRAME ...]

If the environment variable ESCAPE_AT is set to a flip count, the default keyboard reports
Escape from that flip on, as if the participant pressed it.

Writes OUT_DIR/frame_<n>.png for each requested flip count (back buffer before the flip) and
OUT_DIR/events.json with the close events in order. The script runs as __main__, so it ends
with core.quit(), as in the Runner.
"""

import atexit
import json
import os
import runpy
import sys
from pathlib import Path


def main():
    script, out_dir, *frames = sys.argv[1:]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    wanted = {int(f) for f in frames}
    events = []

    from psychopy import visual
    from filly.integrations.psychopy import SharedTarget
    from psychopy_filly import runtime

    flip = visual.Window.flip
    counter = {"n": 0}

    # The frame is read from the back buffer right after the 3D scene draws itself, which
    # Builder's autoDraw does inside flip(). On the test laptop, the front buffer after a flip of
    # a window with useFBO=True read as the background only, although the screen showed the
    # stimuli.
    def capture_flip(self, *args, **kwargs):
        counter["n"] += 1
        counter["capture"] = counter["n"] in wanted
        return flip(self, *args, **kwargs)

    stim_draw = runtime.SceneStim.draw

    def capturing_draw(self, *args, **kwargs):
        result = stim_draw(self, *args, **kwargs)
        if counter.pop("capture", False):
            self.win._getFrame(buffer="back").save(out_dir / f"frame_{counter['n']}.png")
        return result

    target_close = SharedTarget.close

    def logged_target_close(self):
        events.append(("target", self.closed, _open(self._win)))
        target_close(self)

    host_close = runtime._Host.close

    def logged_host_close(self):
        host_close(self)
        events.append(("renderer", self.renderer.closed, _open(self.win)))

    window_close = visual.Window.close

    def logged_window_close(self):
        events.append(("window", False, _open(self)))
        window_close(self)

    escape_at = int(os.environ.get("ESCAPE_AT", "0"))
    if escape_at:
        from psychopy.hardware import keyboard
        # Builder scripts check Escape on the device manager's KeyboardDevice.
        get_keys = keyboard.KeyboardDevice.getKeys

        def escape_keys(self, keyList=None, *args, **kwargs):
            keys = get_keys(self, keyList, *args, **kwargs)
            if counter["n"] >= escape_at and keyList and "escape" in keyList:
                events.append(("escape", counter["n"], True))
                return ["escape"]
            return keys

        keyboard.KeyboardDevice.getKeys = escape_keys

    visual.Window.flip = capture_flip
    runtime.SceneStim.draw = capturing_draw
    SharedTarget.close = logged_target_close
    runtime._Host.close = logged_host_close
    visual.Window.close = logged_window_close

    def write_events():
        (out_dir / "events.json").write_text(
            json.dumps({"events": events, "flips": counter["n"]}, indent=1))

    # Registered before the script creates its window, so it runs after every other handler.
    atexit.register(write_events)
    os.chdir(Path(script).parent)
    sys.argv = [script]
    runpy.run_path(script, run_name="__main__")


def _open(win):
    return not getattr(win, "_closed", False)


if __name__ == "__main__":
    main()
