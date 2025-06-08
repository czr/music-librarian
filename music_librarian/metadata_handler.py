"""Metadata handling for lossy audio files using mutagen."""

import os
from pathlib import Path
from typing import Dict, Any
import mutagen
from mutagen.mp3 import MP3
from mutagen.oggvorbis import OggVorbis
from mutagen.mp4 import MP4
from mutagen.oggopus import OggOpus


def supports_format(extension: str) -> bool:
    """Check if the given file extension is supported for metadata editing.

    Args:
        extension: File extension (without dot)

    Returns:
        True if format is supported, False otherwise
    """
    supported_extensions = {"mp3", "ogg", "aac", "m4a", "opus", "flac", "wav"}
    return extension.lower() in supported_extensions


def read_metadata_from_file(file_path: str) -> Dict[str, str]:
    """Read metadata from an audio file.

    Args:
        file_path: Path to the audio file

    Returns:
        Dictionary of metadata fields

    Raises:
        ValueError: If file format is not supported
        IOError: If file cannot be read
    """
    if not os.path.exists(file_path):
        raise IOError(f"File does not exist: {file_path}")

    path = Path(file_path)
    extension = path.suffix.lower().lstrip(".")

    if not supports_format(extension):
        raise ValueError(f"Unsupported format: {extension}")

    # Load the audio file
    audio_file = mutagen.File(file_path)
    if audio_file is None:
        raise IOError(f"Could not load audio file: {file_path}")

    # Extract metadata based on file type
    metadata = {}

    if isinstance(audio_file, MP3):
        metadata = _read_mp3_metadata(audio_file)
    elif isinstance(audio_file, OggVorbis):
        metadata = _read_ogg_metadata(audio_file)
    elif isinstance(audio_file, MP4):
        metadata = _read_mp4_metadata(audio_file)
    elif isinstance(audio_file, OggOpus):
        metadata = _read_opus_metadata(audio_file)
    else:
        # Try generic approach for other formats (FLAC, etc.)
        metadata = _read_generic_metadata(audio_file)

    return metadata


def apply_metadata_to_file(file_path: str, metadata: Dict[str, Any]) -> None:
    """Apply metadata tags to a lossy audio file.

    Args:
        file_path: Path to the audio file
        metadata: Dictionary of metadata tags to apply

    Raises:
        ValueError: If file format is not supported
        IOError: If file cannot be read/written
    """
    if not os.path.exists(file_path):
        raise IOError(f"File does not exist: {file_path}")

    path = Path(file_path)
    extension = path.suffix.lower().lstrip(".")

    if not supports_format(extension):
        raise ValueError(f"Unsupported format: {extension}")

    # Load the audio file
    audio_file = mutagen.File(file_path)
    if audio_file is None:
        raise IOError(f"Could not load audio file: {file_path}")

    # Apply metadata based on file type
    if isinstance(audio_file, MP3):
        _apply_mp3_metadata(audio_file, metadata)
    elif isinstance(audio_file, OggVorbis):
        _apply_ogg_metadata(audio_file, metadata)
    elif isinstance(audio_file, MP4):
        _apply_mp4_metadata(audio_file, metadata)
    elif isinstance(audio_file, OggOpus):
        _apply_opus_metadata(audio_file, metadata)
    else:
        # Try generic approach for other formats
        _apply_generic_metadata(audio_file, metadata)

    # Save the changes
    audio_file.save()


def _apply_mp3_metadata(audio_file: MP3, metadata: Dict[str, Any]) -> None:
    """Apply metadata to MP3 file using ID3 tags."""
    from mutagen.id3 import TIT2, TPE1, TALB, TDRC, TRCK, TPE2

    # Map our metadata fields to ID3 frames
    tag_mapping = {
        "title": TIT2,
        "artist": TPE1,
        "album": TALB,
        "date": TDRC,
        "track number": TRCK,
        "albumartist": TPE2,
    }

    for field, value in metadata.items():
        if field in tag_mapping and value:
            frame_class = tag_mapping[field]
            audio_file.tags[frame_class.__name__] = frame_class(
                encoding=3, text=str(value)
            )


def _apply_ogg_metadata(audio_file: OggVorbis, metadata: Dict[str, Any]) -> None:
    """Apply metadata to OGG Vorbis file using Vorbis comments."""
    # Map our metadata fields to Vorbis comment names
    tag_mapping = {
        "title": "TITLE",
        "artist": "ARTIST",
        "album": "ALBUM",
        "date": "DATE",
        "track number": "TRACKNUMBER",
        "albumartist": "ALBUMARTIST",
    }

    for field, value in metadata.items():
        if field in tag_mapping and value:
            vorbis_tag = tag_mapping[field]
            audio_file[vorbis_tag] = [str(value)]


def _apply_mp4_metadata(audio_file: MP4, metadata: Dict[str, Any]) -> None:
    """Apply metadata to MP4/AAC file using iTunes-style tags."""
    # Map our metadata fields to MP4 atom names
    tag_mapping = {
        "title": "©nam",
        "artist": "©ART",
        "album": "©alb",
        "date": "©day",
        "track number": "trkn",
        "albumartist": "aART",
    }

    for field, value in metadata.items():
        if field in tag_mapping and value:
            mp4_tag = tag_mapping[field]
            if field == "track number":
                # Track number needs special handling as tuple
                try:
                    track_num = int(value)
                    audio_file[mp4_tag] = [(track_num, 0)]
                except ValueError:
                    audio_file[mp4_tag] = [(1, 0)]
            else:
                audio_file[mp4_tag] = [str(value)]


def _apply_opus_metadata(audio_file: OggOpus, metadata: Dict[str, Any]) -> None:
    """Apply metadata to Opus file using Vorbis comments."""
    # Opus uses same comment format as OGG Vorbis
    _apply_ogg_metadata(audio_file, metadata)


def _apply_generic_metadata(audio_file: Any, metadata: Dict[str, Any]) -> None:
    """Apply metadata using generic mutagen approach."""
    # Try to use common tag names
    tag_mapping = {
        "title": ["TITLE", "TIT2"],
        "artist": ["ARTIST", "TPE1"],
        "album": ["ALBUM", "TALB"],
        "date": ["DATE", "TDRC"],
        "track number": ["TRACKNUMBER", "TRCK"],
        "albumartist": ["ALBUMARTIST", "TPE2"],
    }

    for field, value in metadata.items():
        if field in tag_mapping and value:
            possible_tags = tag_mapping[field]
            for tag in possible_tags:
                try:
                    audio_file[tag] = str(value)
                    break  # Use first successful tag
                except:
                    continue


def _read_mp3_metadata(audio_file: MP3) -> Dict[str, str]:
    """Read metadata from MP3 file using ID3 tags."""
    metadata = {}

    if audio_file.tags is not None:
        # Map ID3 frames to our metadata fields
        tag_mapping = {
            "TIT2": "title",
            "TPE1": "artist",
            "TALB": "album",
            "TDRC": "date",
            "TRCK": "track number",
            "TPE2": "albumartist",
        }

        for frame_id, field in tag_mapping.items():
            if frame_id in audio_file.tags:
                value = str(audio_file.tags[frame_id])
                metadata[field] = value

    return metadata


def _read_ogg_metadata(audio_file: OggVorbis) -> Dict[str, str]:
    """Read metadata from OGG Vorbis file using Vorbis comments."""
    metadata = {}

    # Map Vorbis comment names to our metadata fields
    tag_mapping = {
        "TITLE": "title",
        "ARTIST": "artist",
        "ALBUM": "album",
        "DATE": "date",
        "TRACKNUMBER": "track number",
        "ALBUMARTIST": "albumartist",
    }

    for vorbis_tag, field in tag_mapping.items():
        if vorbis_tag in audio_file:
            # Vorbis comments are lists
            value = str(audio_file[vorbis_tag][0])
            metadata[field] = value

    return metadata


def _read_mp4_metadata(audio_file: MP4) -> Dict[str, str]:
    """Read metadata from MP4/AAC file using iTunes-style tags."""
    metadata = {}

    # Map MP4 atom names to our metadata fields
    tag_mapping = {
        "©nam": "title",
        "©ART": "artist",
        "©alb": "album",
        "©day": "date",
        "trkn": "track number",
        "aART": "albumartist",
    }

    for mp4_tag, field in tag_mapping.items():
        if mp4_tag in audio_file:
            if field == "track number":
                # Track number is a tuple (track, total)
                value = str(audio_file[mp4_tag][0][0])
            else:
                value = str(audio_file[mp4_tag][0])
            metadata[field] = value

    return metadata


def _read_opus_metadata(audio_file: OggOpus) -> Dict[str, str]:
    """Read metadata from Opus file using Vorbis comments."""
    # Opus uses same comment format as OGG Vorbis
    return _read_ogg_metadata(audio_file)


def _read_generic_metadata(audio_file: Any) -> Dict[str, str]:
    """Read metadata using generic mutagen approach."""
    metadata = {}

    # Try common tag names
    tag_mapping = {
        "title": ["TITLE", "TIT2"],
        "artist": ["ARTIST", "TPE1"],
        "album": ["ALBUM", "TALB"],
        "date": ["DATE", "TDRC"],
        "track number": ["TRACKNUMBER", "TRCK"],
        "albumartist": ["ALBUMARTIST", "TPE2"],
    }

    for field, possible_tags in tag_mapping.items():
        for tag in possible_tags:
            if tag in audio_file:
                try:
                    value = str(audio_file[tag])
                    # Handle list values (common in some formats)
                    if isinstance(audio_file[tag], list):
                        value = str(audio_file[tag][0])
                    metadata[field] = value
                    break  # Use first successful tag
                except:
                    continue

    return metadata
