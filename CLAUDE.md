# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Music Librarian is a Python command-line tool for managing a music collection: importing downloaded albums into the source collection, and exporting the collection by transcoding FLAC/WAV to Opus (lossy files are copied). It preserves directory structure, applies metadata overrides from `metadata.txt` files, and handles cover art. User-facing behaviour is documented in the README; otherwise the code and tests are the reference.

## Development Commands

### Setup
```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install in development mode with test dependencies
pip install -e '.[test]'
```

### Testing
```bash
# Run all tests
python -m pytest

# Run specific test
python -m pytest tests/test_music_librarian.py::test_version
```

### Running the Tool
```bash
# Run via module
python -m music_librarian --help

# Run via installed command (after pip install)
music-librarian --help
```

## Architecture

Entry point: `music-librarian = "music_librarian.cli:cli"` in `pyproject.toml`.

- `cli.py`: Click commands (`import`, `export`, `extract-metadata`) and their output. Other modules raise exceptions; only this layer exits.
- `importer.py`: `import` — unpack zips or folders, name `Artist/Album` from tags, stage and rename into `MUSIC_SOURCE_ROOT`.
- `exporter.py`: `export` — transcode/copy into `MUSIC_DEST_ROOT`, cover art, ReplayGain via rsgain.
- `extractor.py`: `extract-metadata` — generate `metadata.txt` from existing tags.
- `metadata_file.py`: the `metadata.txt` format — parse, validate, merge with source tags, generate.
- `metadata_handler.py`: read and write tags with mutagen.
- `audio_processor.py`: per-file operations — opusenc command, copying lossy files with metadata.
- `file_discovery.py`: finding audio files and cover art.
- `data/rsgain_preset.ini`: bundled rsgain preset.

External tools: `opusenc` (opus-tools) and `rsgain`; tests also use `ffmpeg` to generate audio.

## Coding Guidelines

- Follow PEP-8 conventions.
- Format with black at the end of any set of edits.

## Testing Guidelines

### Test Data Setup
When writing tests, avoid setting up common representative data in shared setup routines (like `setUp` or `setup_method`). Instead, create test data on a per-test basis for these reasons:

- **Edge case testing**: It's difficult to test edge cases (like "no data" or "malformed data") when you've already created representative data
- **Test clarity**: Each test clearly shows exactly what data it needs to verify specific behavior
- **Test independence**: Tests don't break when other tests change their data requirements

**Best practices:**
- Create helper functions to make data setup easy and clean within individual tests
- Each test should create only the specific data it needs to verify the behavior being tested
- Use descriptive test data that makes the test's intent clear

## Project Memories

- We're going to go test first for all features.
- Remember to run black on both the code and the tests after making edits.
