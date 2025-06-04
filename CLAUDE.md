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