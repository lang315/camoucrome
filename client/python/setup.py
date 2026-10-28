"""Copies the repository's settings tables into the package at build time,
so a wheel built from a git subdirectory install carries the tag's tables.
Copied fresh on every build: a stale copy would ship another tag's data."""
import pathlib
import shutil

from setuptools import setup
from setuptools.command.build_py import build_py

HERE = pathlib.Path(__file__).resolve().parent
SETTINGS = HERE.parents[1] / "settings"
NEEDED = ["webgl", "fonts.json", "voices.json", "audio.json", "locale_zones.json"]
DEST = HERE / "camoucrome" / "_settings" / "settings"


class CopySettings(build_py):
    def run(self):
        if SETTINGS.is_dir():  # only a git/source-tree build is supported; an sdist rebuilt away from the repo would ship no tables
            shutil.rmtree(DEST.parent, ignore_errors=True)
            DEST.mkdir(parents=True)
            for n in NEEDED:
                src = SETTINGS / n
                (shutil.copytree if src.is_dir() else shutil.copy2)(src, DEST / n)
        super().run()


setup(cmdclass={"build_py": CopySettings})
