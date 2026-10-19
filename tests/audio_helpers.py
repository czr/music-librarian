"""Helpers for creating real audio files in tests."""

import functools
import subprocess

from mutagen.flac import FLAC


@functools.cache
def _silent_flac_bytes():
    """A short silent FLAC, generated once and reused as raw material."""
    result = subprocess.run(
        [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t",
            "0.1",
            "-c:a",
            "flac",
            "-f",
            "flac",
            "-",
        ],
        check=True,
        capture_output=True,
    )
    return result.stdout


def make_flac(path, **tags):
    """Create a silent FLAC at `path` with the given tags (e.g. album="X")."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_silent_flac_bytes())
    audio = FLAC(path)
    for key, value in tags.items():
        audio[key.upper()] = value
    audio.save()
    return path
