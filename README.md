# Music Librarian

Music Librarian is a Python command-line tool for processing music collections. It transcodes lossless audio (FLAC/WAV) to Opus format and copies lossy audio files (MP3, OGG, etc.) while preserving directory structure and handling metadata overrides.

## Features

- **Mixed format processing**: Transcodes lossless files to Opus, copies lossy files as-is
- **Metadata management**: Override metadata using `metadata.txt` files
- **ReplayGain support**: Automatically applies ReplayGain tags for consistent volume
- **Cover art handling**: Copies album artwork alongside audio files
- **Metadata extraction**: Generate `metadata.txt` templates from existing audio files

## Installation

```bash
pip install music-librarian
```

## Setup

Set the required environment variables:

```bash
export MUSIC_SOURCE_ROOT="/path/to/your/music/collection"
export MUSIC_DEST_ROOT="/path/to/processed/music"
export OPUS_QUALITY="128"  # Optional, defaults to 128 kbps
```

## Usage

### Export Command

Export audio files from your source collection to the destination, transcoding lossless files to Opus and copying lossy files:

```bash
# Export a single album
music-librarian export "Pink Floyd/Dark Side of the Moon"

# Export multiple albums
music-librarian export "Pink Floyd/Dark Side of the Moon" "Led Zeppelin/IV"

# Export all albums for an artist
music-librarian export "Pink Floyd"

# Force overwrite existing files
music-librarian export --force "Pink Floyd/Dark Side of the Moon"
```

**What happens:**
- FLAC/WAV files → transcoded to Opus
- MP3/OGG/AAC files → copied without transcoding
- Cover art → copied automatically
- ReplayGain tags → applied to all files as an album

### Extract Metadata Command

Generate `metadata.txt` files from your existing audio files to create editable templates:

```bash
# Generate metadata.txt for an album
music-librarian extract-metadata "Pink Floyd/Dark Side of the Moon"

# Generate for multiple albums
music-librarian extract-metadata "Pink Floyd/Dark Side of the Moon" "Led Zeppelin/IV"

# Generate empty templates (no values extracted)
music-librarian extract-metadata --template-only "Pink Floyd/Dark Side of the Moon"

# Overwrite existing metadata.txt files
music-librarian extract-metadata --force "Pink Floyd/Dark Side of the Moon"
```

**What happens:**
- Finds all directories containing audio files
- Creates `metadata.txt` in each directory with current metadata values
- Each file contains only audio files from that specific directory

## Metadata Override Files

Create a `metadata.txt` file in any album directory to override metadata during export:

```
# Album metadata
title: The Dark Side of the Moon
artist: Pink Floyd
date: 1973

# Per-file metadata
file: 01-speak_to_me.flac:
title: Speak to Me
track number: 1

file: 02-breathe.flac:
title: Breathe (In the Air)
track number: 2
```

**Supported fields:**
- `title` (album title when used at top level, track title when used per-file)
- `artist` (album artist when used at top level, track artist when used per-file)
- `date` (release date in YYYY, YYYY-MM, or YYYY-MM-DD format)
- `track number` (per-file only)

## Directory Structure

The tool preserves your directory structure. For example:

```
Source: /music/Pink Floyd/Dark Side of the Moon/01-speak_to_me.flac
Output: /processed/Pink Floyd/Dark Side of the Moon/01-speak_to_me.opus
```

## Requirements

**External tools (must be in PATH):**
- `opusenc` (from opus-tools package)
- `rsgain` for ReplayGain processing

**Supported audio formats:**
- **Lossless input**: FLAC (.flac), WAV (.wav) → transcoded to Opus
- **Lossy input**: MP3 (.mp3), OGG (.ogg), AAC (.aac, .m4a), Opus (.opus) → copied as-is

**Cover art formats:**
- JPG, JPEG, PNG, GIF, WebP
- Must be named: cover, folder, front, or album (case-insensitive)

## Examples

### Basic Workflow

```bash
# 1. Set up environment
export MUSIC_SOURCE_ROOT="/media/music"
export MUSIC_DEST_ROOT="/home/user/processed-music"

# 2. Generate metadata templates (optional)
music-librarian extract-metadata "Pink Floyd"

# 3. Edit the generated metadata.txt files as needed

# 4. Export the processed music
music-librarian export "Pink Floyd"
```

### Complex Directory Structure

For a structure like this:
```
Pink Floyd/
├── Daybreak.mp3
├── Dark Side of the Moon/
│   ├── 01-speak_to_me.flac
│   └── cover.jpg
└── Wish You Were Here/
    ├── Disc 1/
    │   └── 01-shine_on.flac
    └── Disc 2/
        └── 01-live_track.flac
```

Running `music-librarian extract-metadata "Pink Floyd"` creates:
- `Pink Floyd/metadata.txt`
- `Pink Floyd/Dark Side of the Moon/metadata.txt`
- `Pink Floyd/Wish You Were Here/Disc 1/metadata.txt`
- `Pink Floyd/Wish You Were Here/Disc 2/metadata.txt`

## Error Handling

The tool uses fail-fast error handling - it will stop immediately if any error occurs, allowing you to fix issues and re-run. Common errors:

- Source directory not under `MUSIC_SOURCE_ROOT`
- Missing environment variables
- External tools not found in PATH
- File referenced in `metadata.txt` doesn't exist

## Development

To contribute to this tool, first checkout the code. Then create a new virtual environment:

```bash
cd music-librarian
python -m venv venv
source venv/bin/activate
```

Now install the dependencies and test dependencies:

```bash
pip install -e '.[test]'
```

To run the tests:

```bash
python -m pytest
```

## Release

1. Bump the version number in `pyproject.toml`
2. Create the release in GitHub: `gh release create v1.2.6 --target main`
3. Update `music-librarian` in the `homebrew-czr` repo

## License

MIT License
