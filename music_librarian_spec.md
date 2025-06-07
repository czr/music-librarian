# Music Librarian Tool Specification

## Overview

A Python command-line tool for processing music collections. The tool transcodes lossless audio (FLAC/WAV) to Opus format, and copies lossy audio files (MP3, OGG, etc.) while preserving directory structure and handling metadata overrides in both cases.

## Requirements

### Core Functionality
- Transcode lossless audio files (FLAC, WAV) to Opus format using opusenc
- Copy lossy audio files (MP3, OGG, AAC, etc.) without transcoding
- Apply metadata overrides to copied lossy files
- Preserve source directory structure in destination
- Handle metadata overrides via `metadata.txt` files
- Copy cover art files when present
- Generate ReplayGain tags for all processed audio files
- Skip existing files by default with option to force overwrite

### Environment Variables
- `MUSIC_SOURCE_ROOT`: Root directory of the source music collection
- `MUSIC_DEST_ROOT`: Root directory of the destination music collection
- `OPUS_QUALITY` (optional): Opus encoding quality setting (default: TBD)

## Command Line Interface

There is currently only one command, `export`, but it is expected that more will be added later.

### Usage
```bash
music-librarian <command> <source_directory> [source_directory ...] [options]
```

### Commands

- `export`: export audio files from source collection to destination collection (transcode lossless to Opus, copy lossy files).

### Arguments
- `source_directory`: One or more paths to directories containing audio files to process (must be under `MUSIC_SOURCE_ROOT`)

### Options
- `--force, -f`: Overwrite existing files in destination
- `--help, -h`: Show help message

### Examples
```bash
export MUSIC_SOURCE_ROOT=/media/external/music
export MUSIC_DEST_ROOT=/home/user/music/processed

# Export an album (mix of FLAC and MP3 files)
music-librarian export /media/external/music/Pink\ Floyd/Dark\ Side\ of\ the\ Moon/

# Export multiple albums at once
music-librarian export /media/external/music/Pink\ Floyd/Dark\ Side\ of\ the\ Moon/ /media/external/music/Led\ Zeppelin/IV/

# Export all albums for a single artist
music-librarian export /media/external/music/Pink\ Floyd/
```

### Processing Behavior Examples
Given a source directory containing both lossless and lossy files:
```
/media/external/music/Album/
├── 01-track.flac     → transcoded to /home/user/music/processed/Album/01-track.opus
├── 02-track.mp3      → copied to /home/user/music/processed/Album/02-track.mp3
├── 03-track.ogg      → copied to /home/user/music/processed/Album/03-track.ogg
└── cover.jpg         → copied to /home/user/music/processed/Album/cover.jpg
```

All processed files (both transcoded and copied) will have ReplayGain tags applied as a cohesive album.

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
export /media/external/flac/Pink Floyd/Dark Side of the Moon/
→ Creates/uses /home/user/music/opus/Pink Floyd/Dark Side of the Moon/
```

### File Processing
Source directories are processed sequentially. Within each directory:

1. Recursively scan for audio files:
   - **Lossless formats**: FLAC (.flac), WAV (.wav)
   - **Lossy formats**: MP3 (.mp3), OGG Vorbis (.ogg), AAC (.aac, .m4a), Opus (.opus)
2. For each lossless audio file:
   - Generate destination path with `.opus` extension
   - Skip if destination exists (unless `--force` specified)
   - Transcode using opusenc with configured quality settings
   - Apply metadata overrides from `metadata.txt` if present
3. For each lossy audio file:
   - Generate destination path preserving original extension
   - Skip if destination exists (unless `--force` specified)
   - Copy file to destination without transcoding
   - Apply metadata overrides from `metadata.txt` using appropriate metadata library
4. After all files in a directory are processed, generate ReplayGain tags:
   - Use rsgain to process all audio files directly in each destination directory
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
- Audio metadata library for lossy file processing (TBD - mutagen, eyed3, etc.)
- Note: opusenc handles metadata for transcoded files, but copied lossy files need separate metadata processing

## Configuration

### Default Opus Quality
- TBD (research recommended settings for music archival)
- Configurable via `OPUS_QUALITY` environment variable

### Supported Audio Formats
- **Lossless input (transcoded to Opus)**: FLAC (.flac), WAV (.wav)
- **Lossy input (copied without transcoding)**: MP3 (.mp3), OGG Vorbis (.ogg), AAC (.aac, .m4a), Opus (.opus)
- **Output**: Opus (.opus) for transcoded files, original format preserved for copied files
