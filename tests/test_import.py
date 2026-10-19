"""Tests for the import command."""

import unicodedata
import zipfile

import pytest

from music_librarian.importer import (
    ImportFailed,
    find_matching_entry,
    folder_name_for,
    is_clutter,
    unpack,
)


def make_zip(path, members):
    """Create a zip at `path` from a dict of member name -> bytes content."""
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in members.items():
            zf.writestr(name, content)
    return path


def make_tree(root, members):
    """Create files under `root` from a dict of relative path -> bytes content."""
    for name, content in members.items():
        file_path = root / name
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content)
    return root


def list_tree(root):
    """Return the sorted relative paths of all files under `root`."""
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


class TestFolderNameFor:
    def test_plain_name_is_unchanged(self):
        assert folder_name_for("Magna Silentia") == "Magna Silentia"

    def test_slash_is_replaced_with_hyphen(self):
        assert (
            folder_name_for("Consecrare/Via Peregrinus") == "Consecrare-Via Peregrinus"
        )

    def test_colon_is_replaced_with_hyphen(self):
        assert folder_name_for("Live: Zagreb") == "Live- Zagreb"

    def test_other_punctuation_is_kept(self):
        assert folder_name_for("Seven Sorrows (CD) - Reissue?") == (
            "Seven Sorrows (CD) - Reissue?"
        )


class TestFindMatchingEntry:
    def test_returns_none_when_parent_is_empty(self, tmp_path):
        assert find_matching_entry(tmp_path, "Arcana") is None

    def test_returns_exact_match(self, tmp_path):
        (tmp_path / "Arcana").mkdir()

        assert find_matching_entry(tmp_path, "Arcana") == "Arcana"

    def test_ignores_case_and_returns_existing_spelling(self, tmp_path):
        (tmp_path / "biosphere").mkdir()

        assert find_matching_entry(tmp_path, "Biosphere") == "biosphere"

    def test_ignores_unicode_normalization(self, tmp_path):
        decomposed = unicodedata.normalize("NFD", "Arvo Pärt")
        composed = unicodedata.normalize("NFC", "Arvo Pärt")
        (tmp_path / decomposed).mkdir()

        assert find_matching_entry(tmp_path, composed) is not None

    def test_does_not_match_different_name(self, tmp_path):
        (tmp_path / "Arcana").mkdir()

        assert find_matching_entry(tmp_path, "Arcanum") is None

    def test_matches_files_as_well_as_directories(self, tmp_path):
        (tmp_path / "Thaw").write_text("")

        assert find_matching_entry(tmp_path, "thaw") == "Thaw"

    def test_returns_none_when_parent_does_not_exist(self, tmp_path):
        assert find_matching_entry(tmp_path / "missing", "Arcana") is None


class TestIsClutter:
    @pytest.mark.parametrize(
        "path",
        [".DS_Store", "Disc 1/.DS_Store", "._01 Track.flac", "__MACOSX/01.flac"],
    )
    def test_macos_clutter(self, path):
        assert is_clutter(path)

    @pytest.mark.parametrize(
        "path", ["01 Track.flac", "cover.jpg", "Disc 1/01.flac", "booklet.pdf"]
    )
    def test_real_files(self, path):
        assert not is_clutter(path)


class TestUnpack:
    def test_flat_zip_is_extracted(self, tmp_path):
        source = make_zip(
            tmp_path / "Arcana - Magna Silentia.zip",
            {"01 Det Stora Tysta.flac": b"audio", "cover.jpg": b"image"},
        )
        workdir = tmp_path / "work"
        workdir.mkdir()

        root = unpack(source, workdir)

        assert list_tree(root) == ["01 Det Stora Tysta.flac", "cover.jpg"]
        assert (root / "cover.jpg").read_bytes() == b"image"

    def test_zip_clutter_is_dropped(self, tmp_path):
        source = make_zip(
            tmp_path / "album.zip",
            {
                "01.flac": b"audio",
                ".DS_Store": b"junk",
                "._01.flac": b"junk",
                "__MACOSX/._01.flac": b"junk",
            },
        )
        workdir = tmp_path / "work"
        workdir.mkdir()

        root = unpack(source, workdir)

        assert list_tree(root) == ["01.flac"]

    def test_single_top_level_folder_in_zip_is_unwrapped(self, tmp_path):
        source = make_zip(
            tmp_path / "album.zip",
            {"Magna Silentia/01.flac": b"audio", "Magna Silentia/cover.jpg": b"x"},
        )
        workdir = tmp_path / "work"
        workdir.mkdir()

        root = unpack(source, workdir)

        assert list_tree(root) == ["01.flac", "cover.jpg"]

    def test_single_top_level_folder_is_unwrapped_despite_clutter(self, tmp_path):
        source = make_zip(
            tmp_path / "album.zip",
            {"Album/01.flac": b"audio", "__MACOSX/Album/._01.flac": b"junk"},
        )
        workdir = tmp_path / "work"
        workdir.mkdir()

        root = unpack(source, workdir)

        assert list_tree(root) == ["01.flac"]

    def test_disc_subfolders_are_kept(self, tmp_path):
        source = make_zip(
            tmp_path / "album.zip",
            {"Disc 1/01.flac": b"a", "Disc 2/01.flac": b"b", "cover.jpg": b"c"},
        )
        workdir = tmp_path / "work"
        workdir.mkdir()

        root = unpack(source, workdir)

        assert list_tree(root) == ["Disc 1/01.flac", "Disc 2/01.flac", "cover.jpg"]

    def test_directory_is_used_in_place(self, tmp_path):
        source = make_tree(tmp_path / "Magna Silentia", {"01.flac": b"audio"})
        workdir = tmp_path / "work"
        workdir.mkdir()

        root = unpack(source, workdir)

        assert root == source
        assert list(workdir.iterdir()) == []

    def test_directory_with_single_subfolder_is_unwrapped(self, tmp_path):
        source = make_tree(
            tmp_path / "download", {"Album/01.flac": b"audio", ".DS_Store": b"junk"}
        )
        workdir = tmp_path / "work"
        workdir.mkdir()

        root = unpack(source, workdir)

        assert root == source / "Album"

    def test_missing_source_fails(self, tmp_path):
        with pytest.raises(ImportFailed, match="not a zip file or directory"):
            unpack(tmp_path / "missing.zip", tmp_path)

    def test_non_zip_file_fails(self, tmp_path):
        source = tmp_path / "notes.txt"
        source.write_text("hello")

        with pytest.raises(ImportFailed, match="not a zip file or directory"):
            unpack(source, tmp_path)

    def test_corrupt_zip_fails(self, tmp_path):
        source = tmp_path / "broken.zip"
        source.write_bytes(b"this is not a zip")

        with pytest.raises(ImportFailed, match="could not read zip"):
            unpack(source, tmp_path)
