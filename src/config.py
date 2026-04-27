"""Configuration and constants for Chess Video Translator."""

import os
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    """Konfigurasi aplikasi."""

    telegram_token: str
    google_credentials_path: Path | None = None
    google_drive_folder_id: str | None = None
    google_tts_api_key: str | None = None
    google_translate_api_key: str | None = None
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    tts_voice: str = "en-US-Neural2-D"  # Google Cloud TTS Neural2 male voice
    tts_engine: str = "google"  # "google" or "edge" (fallback)
    max_processing_time: int = 1800  # 30 menit dalam detik
    telegram_file_limit: int = 50 * 1024 * 1024  # 50MB
    supported_formats: tuple[str, ...] = (".mp4", ".avi", ".mkv", ".mov", ".webm")
    temp_dir: Path = Path("/tmp/chess-translator")


SUPPORTED_VIDEO_EXTENSIONS: set[str] = {".mp4", ".avi", ".mkv", ".mov", ".webm"}

GOOGLE_DRIVE_PATTERNS: list[str] = [
    r"https?://drive\.google\.com/file/d/([a-zA-Z0-9_-]+)",
    r"https?://drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)",
]

CHESS_TERM_MAPPING: dict[str, str] = {
    # Pieces
    "kuda": "knight",
    "benteng": "rook",
    "gajah": "bishop",
    "menteri": "queen",
    "raja": "king",
    "bidak": "pawn",
    # Actions
    "makan": "take",
    "dimakan": "taken",
    "memakan": "captures",
    "ambil": "capture",
    "tumbal": "sacrifice",
    "menumbalkan": "sacrifices",
    "korban": "sacrifice",
    "tukar": "exchange",
    "langkah": "move",
    "mundur": "retreat",
    "maju": "advance",
    "serang": "attack",
    "menyerang": "attacks",
    "mengancam": "threatens",
    "ancam": "threaten",
    "lindungi": "defend",
    "melindungi": "defends",
    "blokir": "block",
    # Game states
    "skak mat": "checkmate",
    "sekak mat": "checkmate",
    "skakmat": "checkmate",
    "skak": "check",
    "sekak": "check",
    "rokade panjang": "long castling",
    "rokade pendek": "short castling",
    "rokade": "castling",
    "roket panjang": "long castling",
    "roket pendek": "short castling",
    "rokat panjang": "long castling",
    "rokat pendek": "short castling",
    "castling panjang": "long castling",
    "castling pendek": "short castling",
    "castling": "castling",
    "en passant": "en passant",
    "en pasan": "en passant",
    "promosi": "promotion",
    "pat": "stalemate",
    "remis": "draw",
    "seri": "draw",
    "kalah": "lose",
    "menang": "win",
    # Tactics
    "gambit": "gambit",
    "fianchetto": "fianchetto",
    "pin": "pin",
    "fork": "fork",
    "skewer": "skewer",
    "garpu": "fork",
    "tusukan": "skewer",
    "baterai": "battery",
    # Positions
    "sayap raja": "kingside",
    "sayap menteri": "queenside",
    "pusat": "center",
    "tengah": "center",
    "pembukaan": "opening",
    "tengah permainan": "middlegame",
    "akhir permainan": "endgame",
}


def is_supported_video_format(extension: str) -> bool:
    """Check if a file extension is a supported video format.

    Args:
        extension: File extension string (e.g., ".mp4", ".MP4").

    Returns:
        True if the lowercased extension is in SUPPORTED_VIDEO_EXTENSIONS.
    """
    return extension.lower() in SUPPORTED_VIDEO_EXTENSIONS


def load_config() -> AppConfig:
    """Load application configuration from environment variables.

    Required environment variables:
        TELEGRAM_TOKEN: Telegram Bot API token.
        GOOGLE_CREDENTIALS_PATH: Path to Google service account credentials JSON.
        GOOGLE_DRIVE_FOLDER_ID: Google Drive folder ID for uploads.

    Optional environment variables:
        WHISPER_MODEL: Whisper model size (default: "small").
        WHISPER_DEVICE: Whisper device (default: "cpu").
        TTS_VOICE: Edge TTS voice name (default: "en-US-AriaNeural").
        MAX_PROCESSING_TIME: Max processing time in seconds (default: 1800).
        TELEGRAM_FILE_LIMIT: Telegram file size limit in bytes (default: 52428800).
        TEMP_DIR: Temporary directory path (default: "/tmp/chess-translator").

    Returns:
        AppConfig instance with values from environment.

    Raises:
        ValueError: If required environment variables are missing.
    """
    telegram_token = os.environ.get("TELEGRAM_TOKEN")
    if not telegram_token:
        raise ValueError("TELEGRAM_TOKEN environment variable is required")

    google_credentials_path = os.environ.get("GOOGLE_CREDENTIALS_PATH")
    google_drive_folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")

    return AppConfig(
        telegram_token=telegram_token,
        google_credentials_path=Path(google_credentials_path) if google_credentials_path else None,
        google_drive_folder_id=google_drive_folder_id,
        google_tts_api_key=os.environ.get("GOOGLE_TTS_API_KEY"),
        google_translate_api_key=os.environ.get("GOOGLE_TRANSLATE_API_KEY"),
        whisper_model=os.environ.get("WHISPER_MODEL", "small"),
        whisper_device=os.environ.get("WHISPER_DEVICE", "cpu"),
        tts_voice=os.environ.get("TTS_VOICE", "en-US-Neural2-D"),
        tts_engine=os.environ.get("TTS_ENGINE", "google"),
        max_processing_time=int(os.environ.get("MAX_PROCESSING_TIME", "1800")),
        telegram_file_limit=int(
            os.environ.get("TELEGRAM_FILE_LIMIT", str(50 * 1024 * 1024))
        ),
        temp_dir=Path(os.environ.get("TEMP_DIR", "/tmp/chess-translator")),
    )
