"""Audio extraction from video files using FFmpeg."""

import subprocess
from pathlib import Path

from src.errors import AudioExtractionError


class AudioExtractor:
    """Ekstraksi audio dari video menggunakan FFmpeg."""

    def extract(self, video_path: Path, output_path: Path) -> Path:
        """Ekstrak audio dari video ke WAV mono 16kHz.

        Args:
            video_path: Path ke file video input.
            output_path: Path untuk menyimpan file WAV output.

        Returns:
            Path ke file WAV yang dihasilkan.

        Raises:
            AudioExtractionError: Jika file video corrupt atau tidak memiliki audio track.
        """
        video_path = Path(video_path)
        output_path = Path(output_path)

        if not video_path.exists():
            raise AudioExtractionError(
                f"File video tidak ditemukan: {video_path}"
            )

        self._check_audio_stream(video_path)

        self._extract_audio(video_path, output_path)

        return output_path

    def _check_audio_stream(self, video_path: Path) -> None:
        """Periksa apakah video memiliki audio stream.

        Args:
            video_path: Path ke file video.

        Raises:
            AudioExtractionError: Jika file corrupt atau tidak ada audio stream.
        """
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=codec_type",
            "-of", "csv=p=0",
            str(video_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError:
            raise AudioExtractionError(
                "FFmpeg/ffprobe tidak ditemukan. Pastikan FFmpeg terinstall."
            )
        except subprocess.TimeoutExpired:
            raise AudioExtractionError(
                f"Timeout saat memeriksa audio stream: {video_path}"
            )

        if result.returncode != 0:
            raise AudioExtractionError(
                f"File video tidak dapat diproses (kemungkinan corrupt): {video_path}"
            )

        if not result.stdout.strip():
            raise AudioExtractionError(
                f"Video tidak mengandung audio track: {video_path}"
            )

    def _extract_audio(self, video_path: Path, output_path: Path) -> None:
        """Jalankan FFmpeg untuk mengekstrak audio ke WAV mono 16kHz.

        Args:
            video_path: Path ke file video input.
            output_path: Path untuk menyimpan file WAV output.

        Raises:
            AudioExtractionError: Jika proses ekstraksi gagal.
        """
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            "-y",
            str(output_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except FileNotFoundError:
            raise AudioExtractionError(
                "FFmpeg tidak ditemukan. Pastikan FFmpeg terinstall."
            )
        except subprocess.TimeoutExpired:
            raise AudioExtractionError(
                f"Timeout saat mengekstrak audio dari: {video_path}"
            )

        if result.returncode != 0:
            raise AudioExtractionError(
                f"Gagal mengekstrak audio dari video: {result.stderr.strip()}"
            )
