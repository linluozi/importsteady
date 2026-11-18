"""Test fixture: parent package that must not absorb its children's cost."""

from . import fastmod
from . import slowmod
from . import sub

__all__ = ["fastmod", "slowmod", "sub"]
