# Music Librarian Tool Specification

## Overview

A Python command-line tool for transcoding FLAC/WAV music collections to Opus format while preserving directory structure and handling metadata overrides.

## Requirements

### Core Functionality
- Transcode FLAC and WAV files to Opus format using opusenc
- Preserve source directory structure in destination
- Handle metadata overrides via `metadata.txt` files
- Copy cover art files when present
- Skip existing files by default with option to force overwrite

### Environment Variables
- `MUSIC_SOURCE_ROOT`: Root directory of the source music collection
- `MUSIC_DEST_ROOT`: Root directory of the destination music collection
- `OPUS_QUALITY` (optional): Opus encoding quality setting (default: TBD)

## Command Line Interface

There is currently only one command, `transcode`, but it is expected that more will be added later.

### Usage
```bash
music-librarian <command> <source_directory> [source_directory ...] [options]
```

### Commands

- `transcode`: transcode FLAC/WAV files from source collection to destination collection.

### Arguments
- `source_directory`: One or more paths to directories containing files to transcode (must be under `MUSIC_SOURCE_ROOT`)

### Options
- `--force, -f`: Overwrite existing files in destination
- `--help, -h`: Show help message

### Examples
```bash
export MUSIC_SOURCE_ROOT=/media/external/flac
export MUSIC_DEST_ROOT=/home/user/music/opus

# Transcode an album
music-librarian transcode /media/external/flac/Pink\ Floyd/Dark\ Side\ of\ the\ Moon/

# Transcode multiple albums at once
music-librarian transcode /media/external/flac/Pink\ Floyd/Dark\ Side\ of\ the\ Moon/ /media/external/flac/Led\ Zeppelin/IV/

# Transcode all albums for a single artist
music-librarian transcode /media/external/flac/Pink\ Floyd/
```

## Behavior

### Path Resolution
1. Validate that each`source_directory` is under `MUSIC_SOURCE_ROOT`
2. For each source directory:
   - Strip `MUSIC_SOURCE_ROOT` prefix from `source_directory`
   - Append remaining path to `MUSIC_DEST_ROOT` to get destination directory
   - Create destination directories as needed

**Example:**
```
MUSIC_SOURCE_ROOT=/media/external/flac
MUSIC_DEST_ROOT=/home/user/music/opus
transcode /media/external/flac/Pink Floyd/Dark Side of the Moon/
→ Creates/uses /home/user/music/opus/Pink Floyd/Dark Side of the Moon/
```

### File Processing
Source directories are processed sequentially. Within each directory:

1. Recursively scan for FLAC and WAV files
2. For each audio file:
   - Generate destination path with `.opus` extension
   - Skip if destination exists (unless `--force` specified)
   - Transcode using opusenc with configured quality settings
   - Apply metadata overrides from `metadata.txt` if present
3. After all files in a directory are transcoded, generate ReplayGain tags:
   - Use rsgain to process all `.opus` files directly in each destination directory
   - Files are treated as a single album for ReplayGain calculation

### Cover Art Handling
1. In each directory, look for cover art files using case-insensitive matching:
   - File names starting with: `cover`, `folder`, `front`, `album`
   - With extensions: `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`
   - Examples: `Cover.jpg`, `FOLDER.PNG`, `front.jpeg`
2. Copy first matching file to corresponding destination directory
3. Skip if destination cover file already exists (unless `--force` specified)

### Metadata Override Processing
1. Look for `metadata.txt` in each album directory
2. Parse file for metadata overrides using the format specified below
3. Apply overrides during transcoding process
4. If no `metadata.txt` exists or entries are missing, preserve original metadata from source file
5. Fatal error if a filename listed in `metadata.txt` doesn't exist in source directory

## Metadata Format Specification

### File Format
The `metadata.txt` file uses a simple key-value format with file-specific sections:

```
# Album-wide metadata (before first file: section)
title: Album Title
artist: Album Artist
date: YYYY[-MM[-DD]]

# File-specific overrides
file: exact_filename.flac:
field: value
field: value

file: another_filename.wav:
field: value
```

### Parsing Rules
- **Case sensitivity**: Field names are case-sensitive (`title` ≠ `Title`)
- **Whitespace**: Leading and trailing whitespace is trimmed from values
- **Empty values**: Empty fields (e.g., `title:`) set the tag to empty string
- **File matching**: Filenames must match source files exactly (including extension)
- **Duplicate keys**: Not specified (implementation decision)

### Supported Fields
- **`title`**:
  - Album-wide: Sets album title
  - File-specific: Sets track title
- **`artist`**:
  - Album-wide: Sets both artist and album artist for all tracks
  - File-specific: Overrides artist only (album artist remains unchanged)
- **`date`**: Release date in format YYYY, YYYY-MM, or YYYY-MM-DD (as per opusenc)
- **`track number`**: Track number (file-specific only)

### Example
```
title: TERROR 404
artist: Perturbator
date: 2012

file: Perturbator - TERROR 404 - 01 - Opening Credits.flac:
track number: 01
title: Opening Credits

file: Perturbator & Lueur Verte - TERROR 404 - 05 - Mirage.flac:
artist: Perturbator & Lueur Verte
track number: 05
title: Mirage
```

In this example, the album artist for Mirage is "Perturbator" but the track artist is "Perturbator & Lueur Verte".

## Error Handling

All errors are fatal - the program will exit immediately when any error occurs, allowing the user to fix issues and re-run the command.

### Fatal Errors
- Any `source_directory` not under `MUSIC_SOURCE_ROOT`
- Required environment variables not set
- opusenc or rsgain not available in PATH
- Individual file transcoding failures
- ReplayGain processing failures
- `metadata.txt` parsing errors
- Cover art file operation failures (when cover art files are present)

### Non-Fatal Conditions
- No cover art files present in source directory

## Dependencies

### External Tools
- opusenc (from opus-tools package)
- rsgain for ReplayGain tag generation

### Python Libraries
- Standard library modules for file operations, argument parsing
- Audio metadata library (TBD - mutagen, eyed3, etc.)

## Configuration

### Default Opus Quality
- TBD (research recommended settings for music archival)
- Configurable via `OPUS_QUALITY` environment variable

### Supported Audio Formats
- Input: FLAC (.flac), WAV (.wav)
- Output: Opus (.opus)
