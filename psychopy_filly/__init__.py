"""PsychoPy plugin with Builder components that render 3D models with filly.

Keep this module light: PsychoPy imports it when it activates plugins. Do not import filly here.
"""

import importlib.metadata

try:
    __version__ = importlib.metadata.version("psychopy-filly")
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.dev"
