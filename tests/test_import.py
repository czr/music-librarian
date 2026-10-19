"""Tests for the import command."""

import shutil
import unicodedata
import zipfile

import pytest
from audio_helpers import make_flac
from click.testing import CliRunner

from music_librarian.cli import cli

from music_librarian.importer import (
    ImportFailed,
    find_matching_entry,
    folder_name_for,
    is_clutter,
    plan_imports,
    read_album_identity,
    run_import,
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


def make_album_zip(path, artist, album, track_names, extras=None):
    """Create a Bandcamp-style zip of tagged tracks plus optional extra files."""
    staging = path.parent / f".{path.stem}-contents"
    for name in track_names:
        make_flac(staging / name, artist=artist, albumartist=artist, album=album)
    for name, content in (extras or {}).items():
        (staging / name).write_bytes(content)

    with zipfile.ZipFile(path, "w") as zf:
        for file_path in sorted(staging.rglob("*")):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(staging))
    shutil.rmtree(staging)
    return path


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


class TestReadAlbumIdentity:
    def test_uses_albumartist_and_album(self, tmp_path):
        make_flac(
            tmp_path / "01.flac",
            artist="Arcana feat. Someone",
            albumartist="Arcana",
            album="Magna Silentia",
        )

        assert read_album_identity(tmp_path) == ("Arcana", "Magna Silentia")

    def test_falls_back_to_artist(self, tmp_path):
        make_flac(tmp_path / "01.flac", artist="Arcana", album="Magna Silentia")

        assert read_album_identity(tmp_path) == ("Arcana", "Magna Silentia")

    def test_all_tracks_agreeing_is_fine(self, tmp_path):
        for n in (1, 2, 3):
            make_flac(
                tmp_path / f"0{n}.flac",
                artist="Desiderii Marginis",
                albumartist="Desiderii Marginis",
                album="Consecrare/Via Peregrinus",
            )

        assert read_album_identity(tmp_path) == (
            "Desiderii Marginis",
            "Consecrare/Via Peregrinus",
        )

    def test_tracks_in_disc_subfolders_are_read(self, tmp_path):
        make_flac(tmp_path / "Disc 1" / "01.flac", artist="A", album="B")
        make_flac(tmp_path / "Disc 2" / "01.flac", artist="A", album="B")

        assert read_album_identity(tmp_path) == ("A", "B")

    def test_non_audio_files_are_ignored(self, tmp_path):
        make_flac(tmp_path / "01.flac", artist="A", album="B")
        (tmp_path / "cover.jpg").write_bytes(b"image")
        (tmp_path / "booklet.pdf").write_bytes(b"pdf")

        assert read_album_identity(tmp_path) == ("A", "B")

    def test_clutter_is_ignored(self, tmp_path):
        make_flac(tmp_path / "01.flac", artist="A", album="B")
        (tmp_path / "._01.flac").write_bytes(b"resource fork")

        assert read_album_identity(tmp_path) == ("A", "B")

    def test_no_audio_fails(self, tmp_path):
        (tmp_path / "cover.jpg").write_bytes(b"image")

        with pytest.raises(ImportFailed, match="no audio files"):
            read_album_identity(tmp_path)

    def test_missing_artist_fails_naming_the_file(self, tmp_path):
        make_flac(tmp_path / "01 Untagged.flac", album="B")

        with pytest.raises(ImportFailed, match="01 Untagged.flac.*artist"):
            read_album_identity(tmp_path)

    def test_missing_album_fails_naming_the_file(self, tmp_path):
        make_flac(tmp_path / "01 Untagged.flac", artist="A")

        with pytest.raises(ImportFailed, match="01 Untagged.flac.*album"):
            read_album_identity(tmp_path)

    def test_disagreeing_artists_fail_listing_them(self, tmp_path):
        make_flac(tmp_path / "01.flac", albumartist="Arcana", album="B")
        make_flac(tmp_path / "02.flac", albumartist="Arcana & Friends", album="B")

        with pytest.raises(ImportFailed, match="artist.*'Arcana'.*'Arcana & Friends'"):
            read_album_identity(tmp_path)

    def test_disagreeing_albums_fail_listing_them(self, tmp_path):
        make_flac(tmp_path / "01.flac", artist="A", album="Thaw")
        make_flac(tmp_path / "02.flac", artist="A", album="Strife")

        with pytest.raises(ImportFailed, match="album.*'Strife'.*'Thaw'"):
            read_album_identity(tmp_path)

    def test_unreadable_audio_fails_naming_the_file(self, tmp_path):
        (tmp_path / "01 Broken.flac").write_bytes(b"not really flac")

        with pytest.raises(ImportFailed, match="01 Broken.flac"):
            read_album_identity(tmp_path)


class TestPlanImports:
    def test_plans_destination_from_tags(self, tmp_path):
        library = tmp_path / "library"
        library.mkdir()
        source = make_album_zip(
            tmp_path / "Desiderii Marginis - Consecrare-Via Peregrinus.zip",
            "Desiderii Marginis",
            "Consecrare/Via Peregrinus",
            ["01 Consecrare.flac", "02 Hostia.flac"],
            extras={"cover.jpg": b"image"},
        )

        [plan] = plan_imports([source], library, tmp_path / "work")

        assert plan.source == source
        assert plan.artist_folder == "Desiderii Marginis"
        assert plan.album_folder == "Consecrare-Via Peregrinus"
        assert plan.new_artist is True
        assert plan.track_count == 2
        assert plan.other_count == 1

    def test_uses_existing_artist_spelling(self, tmp_path):
        library = tmp_path / "library"
        (library / "ARCANA" / "Dark Age Of Reason").mkdir(parents=True)
        source = make_album_zip(
            tmp_path / "a.zip", "Arcana", "Magna Silentia", ["01.flac"]
        )

        [plan] = plan_imports([source], library, tmp_path / "work")

        assert plan.artist_folder == "ARCANA"
        assert plan.new_artist is False

    def test_existing_album_fails(self, tmp_path):
        library = tmp_path / "library"
        (library / "Desiderii Marginis" / "Songs Over Ruins").mkdir(parents=True)
        source = make_album_zip(
            tmp_path / "dm.zip", "Desiderii Marginis", "Songs over Ruins", ["01.flac"]
        )

        with pytest.raises(
            ImportFailed,
            match="dm.zip: Desiderii Marginis/Songs Over Ruins already exists",
        ):
            plan_imports([source], library, tmp_path / "work")

    def test_two_sources_for_the_same_album_fail(self, tmp_path):
        library = tmp_path / "library"
        library.mkdir()
        first = make_album_zip(tmp_path / "one.zip", "A", "Album", ["01.flac"])
        second = make_album_zip(tmp_path / "two.zip", "a", "ALBUM", ["01.flac"])

        with pytest.raises(ImportFailed, match="one.zip and two.zip would both"):
            plan_imports([first, second], library, tmp_path / "work")

    def test_errors_name_the_source(self, tmp_path):
        library = tmp_path / "library"
        library.mkdir()
        source = make_zip(tmp_path / "empty-ish.zip", {"cover.jpg": b"image"})

        with pytest.raises(ImportFailed, match="empty-ish.zip: no audio files"):
            plan_imports([source], library, tmp_path / "work")

    def test_one_bad_source_fails_the_whole_batch_before_writing(self, tmp_path):
        library = tmp_path / "library"
        library.mkdir()
        good = make_album_zip(tmp_path / "good.zip", "A", "Album", ["01.flac"])
        bad = make_zip(tmp_path / "bad.zip", {"cover.jpg": b"image"})

        with pytest.raises(ImportFailed, match="bad.zip"):
            plan_imports([good, bad], library, tmp_path / "work")

        assert list(library.iterdir()) == []


class TestRunImport:
    def plan_one(self, tmp_path, source):
        library = tmp_path / "library"
        library.mkdir(exist_ok=True)
        [plan] = plan_imports([source], library, tmp_path / "work")
        return library, plan

    def test_album_lands_in_artist_album_folder(self, tmp_path):
        source = make_album_zip(
            tmp_path / "Arcana - Magna Silentia.zip",
            "Arcana",
            "Magna Silentia",
            ["01 Det Stora Tysta.flac", "02 The Adversity Bell.flac"],
            extras={"cover.jpg": b"image"},
        )
        library, plan = self.plan_one(tmp_path, source)

        destination = run_import(plan, library, create_metadata=False)

        assert destination == library / "Arcana" / "Magna Silentia"
        assert list_tree(destination) == [
            "01 Det Stora Tysta.flac",
            "02 The Adversity Bell.flac",
            "cover.jpg",
        ]

    def test_files_are_copied_byte_for_byte(self, tmp_path):
        source_dir = tmp_path / "download"
        make_flac(source_dir / "01.flac", artist="A", album="B")
        (source_dir / "cover.jpg").write_bytes(b"image")
        original = (source_dir / "01.flac").read_bytes()
        library, plan = self.plan_one(tmp_path, source_dir)

        destination = run_import(plan, library)

        assert (destination / "01.flac").read_bytes() == original

    def test_directory_source_is_left_untouched(self, tmp_path):
        source_dir = tmp_path / "download"
        make_flac(source_dir / "01.flac", artist="A", album="B")
        (source_dir / ".DS_Store").write_bytes(b"junk")
        library, plan = self.plan_one(tmp_path, source_dir)

        destination = run_import(plan, library, create_metadata=False)

        assert list_tree(source_dir) == [".DS_Store", "01.flac"]
        assert list_tree(destination) == ["01.flac"]

    def test_zip_source_is_left_untouched(self, tmp_path):
        source = make_album_zip(tmp_path / "a.zip", "A", "B", ["01.flac"])
        original = source.read_bytes()
        library, plan = self.plan_one(tmp_path, source)

        run_import(plan, library)

        assert source.read_bytes() == original

    def test_disc_subfolders_are_kept(self, tmp_path):
        source_dir = tmp_path / "download"
        make_flac(source_dir / "Disc 1" / "01.flac", artist="A", album="B")
        make_flac(source_dir / "Disc 2" / "01.flac", artist="A", album="B")
        library, plan = self.plan_one(tmp_path, source_dir)

        destination = run_import(plan, library, create_metadata=False)

        assert list_tree(destination) == ["Disc 1/01.flac", "Disc 2/01.flac"]

    def test_existing_artist_folder_is_reused(self, tmp_path):
        library = tmp_path / "library"
        (library / "arcana" / "Petrichor").mkdir(parents=True)
        source = make_album_zip(
            tmp_path / "a.zip", "Arcana", "Magna Silentia", ["01.flac"]
        )
        library, plan = self.plan_one(tmp_path, source)

        destination = run_import(plan, library)

        assert destination == library / "arcana" / "Magna Silentia"
        assert sorted(p.name for p in (library / "arcana").iterdir()) == [
            "Magna Silentia",
            "Petrichor",
        ]

    def test_no_staging_directory_is_left_behind(self, tmp_path):
        source = make_album_zip(tmp_path / "a.zip", "A", "B", ["01.flac"])
        library, plan = self.plan_one(tmp_path, source)

        run_import(plan, library)

        assert [p.name for p in library.iterdir()] == ["A"]

    def test_album_appearing_after_planning_fails_without_overwriting(self, tmp_path):
        source = make_album_zip(tmp_path / "a.zip", "A", "B", ["01.flac"])
        library, plan = self.plan_one(tmp_path, source)
        (library / "A" / "b").mkdir(parents=True)
        (library / "A" / "b" / "mine.flac").write_bytes(b"precious")

        with pytest.raises(ImportFailed, match="A/b already exists"):
            run_import(plan, library)

        assert list_tree(library) == ["A/b/mine.flac"]

    def test_failure_cleans_up_new_artist_folder_and_staging(
        self, tmp_path, monkeypatch
    ):
        source = make_album_zip(tmp_path / "a.zip", "A", "B", ["01.flac"])
        library, plan = self.plan_one(tmp_path, source)

        def fail_rename(src, dst):
            raise OSError("disk unplugged")

        monkeypatch.setattr("music_librarian.importer.os.rename", fail_rename)

        with pytest.raises(OSError, match="disk unplugged"):
            run_import(plan, library)

        assert list(library.iterdir()) == []


class TestRunImportMetadata:
    def plan_one(self, tmp_path, source):
        library = tmp_path / "library"
        library.mkdir(exist_ok=True)
        [plan] = plan_imports([source], library, tmp_path / "work")
        return library, plan

    def test_metadata_txt_is_generated_from_tags(self, tmp_path):
        source_dir = tmp_path / "download"
        make_flac(
            source_dir / "01 Det Stora Tysta.flac",
            artist="Arcana",
            album="Magna Silentia",
            title="Det Stora Tysta",
            tracknumber="1",
        )
        library, plan = self.plan_one(tmp_path, source_dir)

        destination = run_import(plan, library)

        content = (destination / "metadata.txt").read_text()
        assert "title: Magna Silentia" in content
        assert "artist: Arcana" in content
        assert "file: 01 Det Stora Tysta.flac:" in content
        assert "title: Det Stora Tysta" in content

    def test_metadata_txt_is_generated_in_each_disc_folder(self, tmp_path):
        source_dir = tmp_path / "download"
        make_flac(source_dir / "Disc 1" / "01.flac", artist="A", album="B")
        make_flac(source_dir / "Disc 2" / "01.flac", artist="A", album="B")
        library, plan = self.plan_one(tmp_path, source_dir)

        destination = run_import(plan, library)

        assert (destination / "Disc 1" / "metadata.txt").exists()
        assert (destination / "Disc 2" / "metadata.txt").exists()

    def test_existing_metadata_txt_is_kept(self, tmp_path):
        source_dir = tmp_path / "download"
        make_flac(source_dir / "01.flac", artist="A", album="B")
        (source_dir / "metadata.txt").write_text("title: My Own Title\n")
        library, plan = self.plan_one(tmp_path, source_dir)

        destination = run_import(plan, library)

        assert (destination / "metadata.txt").read_text() == "title: My Own Title\n"

    def test_metadata_txt_can_be_skipped(self, tmp_path):
        source_dir = tmp_path / "download"
        make_flac(source_dir / "01.flac", artist="A", album="B")
        library, plan = self.plan_one(tmp_path, source_dir)

        destination = run_import(plan, library, create_metadata=False)

        assert list_tree(destination) == ["01.flac"]


def run_cli(args, env):
    """Run the CLI with only the given music environment variables set."""
    clean_env = {"MUSIC_SOURCE_ROOT": None, "MUSIC_DEST_ROOT": None, **env}
    return CliRunner().invoke(cli, args, env=clean_env)


class TestImportCLI:
    def test_imports_a_zip(self, tmp_path):
        library = tmp_path / "library"
        library.mkdir()
        source = make_album_zip(
            tmp_path / "Arcana - Magna Silentia.zip",
            "Arcana",
            "Magna Silentia",
            ["01.flac", "02.flac"],
            extras={"cover.jpg": b"image"},
        )

        result = run_cli(["import", str(source)], {"MUSIC_SOURCE_ROOT": str(library)})

        assert result.exit_code == 0, result.output
        assert (library / "Arcana" / "Magna Silentia" / "01.flac").exists()
        assert (library / "Arcana" / "Magna Silentia" / "metadata.txt").exists()
        assert "Arcana - Magna Silentia.zip" in result.output
        assert "Arcana/Magna Silentia" in result.output
        assert "2 tracks, 1 other file" in result.output

    def test_imports_several_sources_including_a_directory(self, tmp_path):
        library = tmp_path / "library"
        library.mkdir()
        zipped = make_album_zip(tmp_path / "a.zip", "A", "First", ["01.flac"])
        directory = tmp_path / "download"
        make_flac(directory / "01.flac", artist="B", album="Second")

        result = run_cli(
            ["import", str(zipped), str(directory)],
            {"MUSIC_SOURCE_ROOT": str(library)},
        )

        assert result.exit_code == 0, result.output
        assert (library / "A" / "First" / "01.flac").exists()
        assert (library / "B" / "Second" / "01.flac").exists()

    def test_reports_new_artist(self, tmp_path):
        library = tmp_path / "library"
        library.mkdir()
        source = make_album_zip(tmp_path / "a.zip", "Arcana", "M", ["01.flac"])

        result = run_cli(["import", str(source)], {"MUSIC_SOURCE_ROOT": str(library)})

        assert "new artist" in result.output

    def test_does_not_report_existing_artist_as_new(self, tmp_path):
        library = tmp_path / "library"
        (library / "Arcana").mkdir(parents=True)
        source = make_album_zip(tmp_path / "a.zip", "Arcana", "M", ["01.flac"])

        result = run_cli(["import", str(source)], {"MUSIC_SOURCE_ROOT": str(library)})

        assert result.exit_code == 0, result.output
        assert "new artist" not in result.output

    def test_no_metadata_flag_skips_metadata_txt(self, tmp_path):
        library = tmp_path / "library"
        library.mkdir()
        source = make_album_zip(tmp_path / "a.zip", "A", "B", ["01.flac"])

        result = run_cli(
            ["import", "--no-metadata", str(source)],
            {"MUSIC_SOURCE_ROOT": str(library)},
        )

        assert result.exit_code == 0, result.output
        assert not (library / "A" / "B" / "metadata.txt").exists()

    def test_requires_a_source(self, tmp_path):
        result = run_cli(["import"], {"MUSIC_SOURCE_ROOT": str(tmp_path)})

        assert result.exit_code != 0

    def test_fails_when_source_root_not_set(self, tmp_path):
        source = make_album_zip(tmp_path / "a.zip", "A", "B", ["01.flac"])

        result = run_cli(["import", str(source)], {})

        assert result.exit_code == 1
        assert "MUSIC_SOURCE_ROOT" in result.output

    def test_fails_when_source_root_missing(self, tmp_path):
        source = make_album_zip(tmp_path / "a.zip", "A", "B", ["01.flac"])
        missing = tmp_path / "Volumes" / "Music"

        result = run_cli(["import", str(source)], {"MUSIC_SOURCE_ROOT": str(missing)})

        assert result.exit_code == 1
        assert "does not exist" in result.output
        assert not missing.exists()

    def test_problem_with_one_source_imports_nothing(self, tmp_path):
        library = tmp_path / "library"
        (library / "B" / "Taken").mkdir(parents=True)
        good = make_album_zip(tmp_path / "good.zip", "A", "Fine", ["01.flac"])
        bad = make_album_zip(tmp_path / "bad.zip", "B", "Taken", ["01.flac"])

        result = run_cli(
            ["import", str(good), str(bad)], {"MUSIC_SOURCE_ROOT": str(library)}
        )

        assert result.exit_code == 1
        assert "bad.zip: B/Taken already exists" in result.output
        assert sorted(p.name for p in library.iterdir()) == ["B"]

    def test_export_requires_dest_root_before_importing(self, tmp_path):
        library = tmp_path / "library"
        library.mkdir()
        source = make_album_zip(tmp_path / "a.zip", "A", "B", ["01.flac"])

        result = run_cli(
            ["import", "--export", str(source)], {"MUSIC_SOURCE_ROOT": str(library)}
        )

        assert result.exit_code == 1
        assert "MUSIC_DEST_ROOT" in result.output
        assert list(library.iterdir()) == []

    def test_export_requires_tools_before_importing(self, tmp_path, monkeypatch):
        library = tmp_path / "library"
        library.mkdir()
        source = make_album_zip(tmp_path / "a.zip", "A", "B", ["01.flac"])
        monkeypatch.setattr("music_librarian.cli.shutil.which", lambda tool: None)

        result = run_cli(
            ["import", "--export", str(source)],
            {
                "MUSIC_SOURCE_ROOT": str(library),
                "MUSIC_DEST_ROOT": str(tmp_path / "out"),
            },
        )

        assert result.exit_code == 1
        assert "not found in PATH" in result.output
        assert list(library.iterdir()) == []

    def test_export_transcodes_imported_albums(self, tmp_path):
        library = tmp_path / "library"
        library.mkdir()
        dest = tmp_path / "exported"
        source = make_album_zip(
            tmp_path / "a.zip",
            "Arcana",
            "Consecrare/Via",
            ["01.flac", "02.flac"],
            extras={"cover.jpg": b"image"},
        )

        result = run_cli(
            ["import", "--export", str(source)],
            {"MUSIC_SOURCE_ROOT": str(library), "MUSIC_DEST_ROOT": str(dest)},
        )

        assert result.exit_code == 0, result.output
        assert list_tree(dest) == [
            "Arcana/Consecrare-Via/01.opus",
            "Arcana/Consecrare-Via/02.opus",
            "Arcana/Consecrare-Via/cover.jpg",
        ]

    def test_export_failure_keeps_the_import(self, tmp_path, monkeypatch):
        library = tmp_path / "library"
        library.mkdir()
        source = make_album_zip(tmp_path / "a.zip", "A", "B", ["01.flac"])

        def failing_export(source_dir, dest_dir, force=False, debug=False):
            raise RuntimeError("opusenc exploded")

        monkeypatch.setattr("music_librarian.cli.process_directory", failing_export)

        result = run_cli(
            ["import", "--export", str(source)],
            {
                "MUSIC_SOURCE_ROOT": str(library),
                "MUSIC_DEST_ROOT": str(tmp_path / "out"),
            },
        )

        assert result.exit_code == 1
        assert "opusenc exploded" in result.output
        assert "A/B" in result.output
        assert (library / "A" / "B" / "01.flac").exists()
