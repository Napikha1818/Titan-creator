"""Unit tests for core data models."""

from pathlib import Path

from src.models import (
    JobContext,
    PipelineResult,
    PipelineStage,
    Segment,
    TranslatedSegment,
)


class TestSegment:
    """Tests for the Segment dataclass."""

    def test_duration_positive(self):
        seg = Segment(start=1.0, end=3.5, text="halo")
        assert seg.duration == 2.5

    def test_duration_small(self):
        seg = Segment(start=0.0, end=0.5, text="ya")
        assert seg.duration == 0.5

    def test_frozen(self):
        seg = Segment(start=0.0, end=1.0, text="test")
        try:
            seg.start = 5.0  # type: ignore[misc]
            assert False, "Should have raised FrozenInstanceError"
        except AttributeError:
            pass

    def test_fields(self):
        seg = Segment(start=10.0, end=20.0, text="kuda e4")
        assert seg.start == 10.0
        assert seg.end == 20.0
        assert seg.text == "kuda e4"


class TestTranslatedSegment:
    """Tests for the TranslatedSegment dataclass."""

    def test_duration(self):
        ts = TranslatedSegment(
            start=2.0, end=5.0, original_text="kuda", translated_text="knight"
        )
        assert ts.duration == 3.0

    def test_frozen(self):
        ts = TranslatedSegment(
            start=0.0, end=1.0, original_text="a", translated_text="b"
        )
        try:
            ts.start = 5.0  # type: ignore[misc]
            assert False, "Should have raised FrozenInstanceError"
        except AttributeError:
            pass

    def test_fields(self):
        ts = TranslatedSegment(
            start=1.0, end=4.0, original_text="benteng", translated_text="rook"
        )
        assert ts.start == 1.0
        assert ts.end == 4.0
        assert ts.original_text == "benteng"
        assert ts.translated_text == "rook"


class TestPipelineStage:
    """Tests for the PipelineStage enum."""

    def test_all_stages_exist(self):
        expected = [
            "AUDIO_EXTRACTION",
            "TRANSCRIPTION",
            "TRANSLATION",
            "TTS_SYNTHESIS",
            "SUBTITLE_GENERATION",
            "VIDEO_MERGE",
            "UPLOADING",
        ]
        actual = [stage.name for stage in PipelineStage]
        assert actual == expected

    def test_stage_values_are_strings(self):
        for stage in PipelineStage:
            assert isinstance(stage.value, str)

    def test_stage_count(self):
        assert len(PipelineStage) == 7


class TestPipelineResult:
    """Tests for the PipelineResult dataclass."""

    def test_success_result(self):
        result = PipelineResult(success=True, output_path=Path("/tmp/out.mp4"))
        assert result.success is True
        assert result.output_path == Path("/tmp/out.mp4")
        assert result.error_message is None
        assert result.error_stage is None

    def test_failure_result(self):
        result = PipelineResult(
            success=False,
            error_message="FFmpeg failed",
            error_stage=PipelineStage.VIDEO_MERGE,
        )
        assert result.success is False
        assert result.output_path is None
        assert result.error_message == "FFmpeg failed"
        assert result.error_stage == PipelineStage.VIDEO_MERGE


class TestJobContext:
    """Tests for the JobContext dataclass."""

    def test_defaults(self):
        ctx = JobContext(
            chat_id=123, video_path=Path("/tmp/vid.mp4"), work_dir=Path("/tmp/work")
        )
        assert ctx.chat_id == 123
        assert ctx.video_path == Path("/tmp/vid.mp4")
        assert ctx.work_dir == Path("/tmp/work")
        assert ctx.audio_path is None
        assert ctx.segments == []
        assert ctx.translated_segments == []
        assert ctx.tts_audio_path is None
        assert ctx.subtitle_path is None
        assert ctx.output_path is None

    def test_mutable_segments(self):
        ctx = JobContext(
            chat_id=1, video_path=Path("/tmp/v.mp4"), work_dir=Path("/tmp/w")
        )
        seg = Segment(start=0.0, end=1.0, text="test")
        ctx.segments.append(seg)
        assert len(ctx.segments) == 1

    def test_independent_default_lists(self):
        ctx1 = JobContext(
            chat_id=1, video_path=Path("/tmp/a.mp4"), work_dir=Path("/tmp/a")
        )
        ctx2 = JobContext(
            chat_id=2, video_path=Path("/tmp/b.mp4"), work_dir=Path("/tmp/b")
        )
        ctx1.segments.append(Segment(start=0.0, end=1.0, text="x"))
        assert len(ctx2.segments) == 0
