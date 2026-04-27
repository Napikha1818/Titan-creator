"""Unit tests for ChessTranslator."""

from unittest.mock import MagicMock, patch

import pytest

from src.errors import TranslationError
from src.models import Segment, TranslatedSegment
from src.translator import ChessTranslator


class TestChessTranslatorInit:
    """Tests for ChessTranslator initialization."""

    def test_chess_terms_loaded(self):
        translator = ChessTranslator()
        assert "kuda" in translator.CHESS_TERMS
        assert translator.CHESS_TERMS["kuda"] == "knight"
        assert translator.CHESS_TERMS["benteng"] == "rook"
        assert translator.CHESS_TERMS["gajah"] == "bishop"

    def test_sorted_terms_longest_first(self):
        translator = ChessTranslator()
        # "skak mat" should come before "skak"
        skak_mat_idx = translator._sorted_terms.index("skak mat")
        skak_idx = translator._sorted_terms.index("skak")
        assert skak_mat_idx < skak_idx

    def test_uses_gcp_when_api_key_provided(self):
        translator = ChessTranslator(api_key="test-key")
        assert translator._use_gcp is True

    def test_falls_back_without_api_key(self):
        translator = ChessTranslator(api_key=None)
        assert translator._use_gcp is False


class TestApplyChessTerms:
    """Tests for _apply_chess_terms method."""

    def setup_method(self):
        self.translator = ChessTranslator()

    def test_single_chess_term_replaced(self):
        result = self.translator._apply_chess_terms("kuda ke e4")
        assert "kuda" not in result.lower()
        assert "CHESSTERM" in result

    def test_multiple_chess_terms_replaced(self):
        result = self.translator._apply_chess_terms("kuda makan benteng")
        assert "kuda" not in result.lower()
        assert "benteng" not in result.lower()

    def test_case_insensitive_replacement(self):
        result = self.translator._apply_chess_terms("Kuda ke E4")
        assert "Kuda" not in result
        assert "CHESSTERM" in result

    def test_multi_word_term_skak_mat(self):
        result = self.translator._apply_chess_terms("ini adalah skak mat")
        assert "skak mat" not in result.lower()
        assert "CHESSTERM" in result

    def test_text_without_chess_terms_unchanged(self):
        text = "ini adalah teks biasa tanpa istilah catur"
        result = self.translator._apply_chess_terms(text)
        assert result == text

    def test_mixed_chess_and_normal_text(self):
        result = self.translator._apply_chess_terms("pindahkan kuda ke posisi yang bagus")
        assert "kuda" not in result.lower()
        assert "pindahkan" in result
        assert "posisi" in result
        assert "bagus" in result


class TestTranslateText:
    """Tests for translate_text method."""

    def test_successful_translation_with_deep_translator(self):
        """Test translation via deep-translator fallback (no API key)."""
        translator = ChessTranslator(api_key=None)

        with patch.object(translator, "_deep_translate", return_value="Hello world"):
            result = translator.translate_text("Halo dunia")
            assert result == "Hello world"

    def test_translation_failure_raises_error(self):
        translator = ChessTranslator(api_key=None)

        with patch.object(translator, "_deep_translate", side_effect=Exception("API error")):
            with pytest.raises(TranslationError, match="Failed to translate text"):
                translator.translate_text("Halo dunia")

    def test_chess_terms_preserved_in_translation(self):
        """Chess terms should be replaced with placeholders before translation,
        then restored with English terms after."""
        translator = ChessTranslator(api_key=None)

        placeholder_kuda = translator._term_to_placeholder["kuda"]

        with patch.object(
            translator, "_deep_translate",
            return_value=f"move {placeholder_kuda} to e4"
        ):
            result = translator.translate_text("pindahkan kuda ke e4")
            assert "knight" in result
            assert "CHESSTERM" not in result

    def test_gcp_translate_called_when_api_key_set(self):
        """When API key is set, should use Google Cloud Translation API."""
        translator = ChessTranslator(api_key="test-key")

        with patch.object(translator, "_google_cloud_translate", return_value="translated") as mock_gcp:
            result = translator.translate_text("teks")
            mock_gcp.assert_called_once()
            assert result == "translated"


class TestTranslateSegments:
    """Tests for translate_segments method."""

    def test_timestamps_preserved(self):
        """Requirement 4.2: Timestamps must be preserved from original segments."""
        translator = ChessTranslator(api_key=None)

        with patch.object(translator, "translate_text", return_value="translated text"):
            segments = [
                Segment(start=1.5, end=4.0, text="teks pertama"),
                Segment(start=5.0, end=8.5, text="teks kedua"),
            ]
            result = translator.translate_segments(segments)

            assert len(result) == 2
            assert result[0].start == 1.5
            assert result[0].end == 4.0
            assert result[1].start == 5.0
            assert result[1].end == 8.5

    def test_original_text_preserved(self):
        translator = ChessTranslator(api_key=None)

        with patch.object(translator, "translate_text", return_value="translated"):
            segments = [Segment(start=0.0, end=2.0, text="teks asli")]
            result = translator.translate_segments(segments)
            assert result[0].original_text == "teks asli"

    def test_fallback_on_failure(self):
        """Requirement 4.3: If translation fails, use original text as fallback."""
        translator = ChessTranslator(api_key=None)

        with patch.object(
            translator, "translate_text",
            side_effect=["first translated", Exception("API error"), "third translated"],
        ):
            segments = [
                Segment(start=0.0, end=2.0, text="pertama"),
                Segment(start=2.0, end=4.0, text="kedua gagal"),
                Segment(start=4.0, end=6.0, text="ketiga"),
            ]
            result = translator.translate_segments(segments)

            assert len(result) == 3
            assert result[0].translated_text == "first translated"
            assert result[1].translated_text == "kedua gagal"
            assert result[2].translated_text == "third translated"

    def test_empty_segments_list(self):
        translator = ChessTranslator(api_key=None)
        result = translator.translate_segments([])
        assert result == []

    def test_output_count_matches_input(self):
        translator = ChessTranslator(api_key=None)

        with patch.object(translator, "translate_text", return_value="translated"):
            segments = [
                Segment(start=0.0, end=1.0, text="a"),
                Segment(start=1.0, end=2.0, text="b"),
                Segment(start=2.0, end=3.0, text="c"),
                Segment(start=3.0, end=4.0, text="d"),
            ]
            result = translator.translate_segments(segments)
            assert len(result) == len(segments)

    def test_all_translations_fail_uses_all_fallbacks(self):
        translator = ChessTranslator(api_key=None)

        with patch.object(translator, "translate_text", side_effect=Exception("API down")):
            segments = [
                Segment(start=0.0, end=2.0, text="pertama"),
                Segment(start=2.0, end=4.0, text="kedua"),
            ]
            result = translator.translate_segments(segments)

            assert len(result) == 2
            assert result[0].translated_text == "pertama"
            assert result[1].translated_text == "kedua"
