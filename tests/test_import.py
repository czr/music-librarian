"""Tests for the import command."""

import unicodedata

from music_librarian.importer import find_matching_entry, folder_name_for


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
