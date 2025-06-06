# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Music Librarian is a Python command-line tool for transcoding FLAC/WAV music collections to Opus format. The tool preserves directory structure, handles metadata overrides via `metadata.txt` files, and processes cover art files.

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

### Core Structure
- `music_librarian/cli.py`: Click-based CLI interface with command groups and options
- `music_librarian/__main__.py`: Entry point for module execution
- Entry point defined in `pyproject.toml` as `music-librarian = "music_librarian.cli:cli"`

### Key Dependencies
- **Click**: Command-line interface framework
- **External tools required**: opusenc (opus-tools), rsgain for ReplayGain processing

### Expected Implementation
Based on the specification, the tool should implement:
- `transcode` command for FLAC/WAV to Opus conversion
- Environment variable configuration (`MUSIC_SOURCE_ROOT`, `MUSIC_DEST_ROOT`, `OPUS_QUALITY`)
- Metadata override processing from `metadata.txt` files
- Cover art copying with case-insensitive pattern matching
- ReplayGain tag generation using rsgain

### Current Status
The CLI structure is scaffolded with a placeholder command. The actual transcoding functionality needs to be implemented per the detailed specification in `music_librarian_spec.md`.


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