"""Video merging with new audio and burn-in subtitles using FFmpeg."""

import json
import subprocess
from pathlib import Path

from src.errors import VideoMergeError


class VideoMerger:
    """Penggabungan video final menggunakan FFmpeg."""

    def merge(
        self,
        video_path: Path,
        audio_path: Path,
        subtitle_path: Path,
        output_path: Path,
        background_audio_path: Path | None = None,
    ) -> Path:
        """Gabungkan video asli dengan audio baru dan burn-in subtitle.

        If background_audio_path is provided, mixes it with the TTS audio
        so chess move sounds are preserved.

        Output: MP4 H.264/AAC.
        """
        video_path = Path(video_path)
        audio_path = Path(audio_path)
        subtitle_path = Path(subtitle_path)
        output_path = Path(output_path)

        self._validate_inputs(video_path, audio_path, subtitle_path)

        input_duration = self._get_duration(video_path)

        self._run_merge(video_path, audio_path, subtitle_path, output_path,
                       background_audio_path=background_audio_path)

        if not output_path.exists():
            raise VideoMergeError(
                "Video output tidak dihasilkan oleh FFmpeg."
            )

        output_duration = self._get_duration(output_path)
        self._verify_duration(input_duration, output_duration)

        return output_path

    def _validate_inputs(
        self, video_path: Path, audio_path: Path, subtitle_path: Path
    ) -> None:
        """Validasi bahwa semua file input ada.

        Args:
            video_path: Path ke file video.
            audio_path: Path ke file audio.
            subtitle_path: Path ke file subtitle.

        Raises:
            VideoMergeError: Jika salah satu file tidak ditemukan.
        """
        if not video_path.exists():
            raise VideoMergeError(
                f"File video tidak ditemukan: {video_path}"
            )
        if not audio_path.exists():
            raise VideoMergeError(
                f"File audio tidak ditemukan: {audio_path}"
            )
        if not subtitle_path.exists():
            raise VideoMergeError(
                f"File subtitle tidak ditemukan: {subtitle_path}"
            )

    def _get_duration(self, file_path: Path) -> float:
        """Dapatkan durasi file media menggunakan ffprobe.

        Args:
            file_path: Path ke file media.

        Returns:
            Durasi dalam detik.

        Raises:
            VideoMergeError: Jika durasi tidak dapat dibaca.
        """
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            str(file_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError:
            raise VideoMergeError(
                "FFmpeg/ffprobe tidak ditemukan. Pastikan FFmpeg terinstall."
            )
        except subprocess.TimeoutExpired:
            raise VideoMergeError(
                f"Timeout saat membaca durasi: {file_path}"
            )

        if result.returncode != 0:
            raise VideoMergeError(
                f"Gagal membaca durasi file: {file_path} - {result.stderr.strip()}"
            )

        try:
            probe_data = json.loads(result.stdout)
            duration = float(probe_data["format"]["duration"])
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            raise VideoMergeError(
                f"Gagal parsing durasi dari ffprobe output: {e}"
            )

        return duration

    def _run_merge(
        self,
        video_path: Path,
        audio_path: Path,
        subtitle_path: Path,
        output_path: Path,
        background_audio_path: Path | None = None,
    ) -> None:
        """Jalankan FFmpeg untuk menggabungkan video, audio, dan subtitle.

        If background_audio_path is provided, mixes background SFX with TTS.
        """
        subtitle_filter_path = str(subtitle_path).replace("\\", "\\\\").replace(":", "\\:")

        if background_audio_path and background_audio_path.exists():
            # Mix background SFX with TTS audio — no original voice
            cmd = [
                "ffmpeg",
                "-i", str(video_path),
                "-i", str(audio_path),
                "-i", str(background_audio_path),
                "-filter_complex",
                f"[1:a]volume=1.0[tts];[2:a]volume=0.3[bg];[tts][bg]amix=inputs=2:duration=first:normalize=0[aout];[0:v]subtitles={subtitle_filter_path}[vout]",
                "-map", "[vout]",
                "-map", "[aout]",
                "-c:v", "libx264",
                "-c:a", "aac",
                "-y",
                str(output_path),
            ]
        else:
            # No background audio — just replace audio track
            cmd = [
                "ffmpeg",
                "-i", str(video_path),
                "-i", str(audio_path),
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-vf", f"subtitles={subtitle_filter_path}",
                "-c:v", "libx264",
                "-c:a", "aac",
                "-y",
                str(output_path),
            ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1800,  # 30 menit timeout
            )
        except FileNotFoundError:
            raise VideoMergeError(
                "FFmpeg tidak ditemukan. Pastikan FFmpeg terinstall."
            )
        except subprocess.TimeoutExpired:
            raise VideoMergeError(
                "Timeout saat menggabungkan video (melebihi 30 menit)."
            )

        if result.returncode != 0:
            raise VideoMergeError(
                f"Gagal menggabungkan video: {result.stderr.strip()}"
            )

    def _verify_duration(
        self, input_duration: float, output_duration: float
    ) -> None:
        """Verifikasi durasi output sesuai dengan input (toleransi 5 detik).

        Args:
            input_duration: Durasi video input dalam detik.
            output_duration: Durasi video output dalam detik.

        Raises:
            VideoMergeError: Jika selisih durasi melebihi 5 detik.
        """
        duration_diff = abs(output_duration - input_duration)
        if duration_diff > 5.0:
            raise VideoMergeError(
                f"Durasi video output ({output_duration:.1f}s) berbeda "
                f"dari input ({input_duration:.1f}s) melebihi toleransi 5 detik "
                f"(selisih: {duration_diff:.1f}s)."
            )
