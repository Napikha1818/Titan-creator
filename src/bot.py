"""Telegram Bot handler for Chess Video Translator."""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from src.config import AppConfig, is_supported_video_format
from src.drive_manager import download_from_drive, is_drive_url
from src.errors import DriveDownloadError, PipelineError
from src.pipeline import PipelineProcessor, format_error_message

logger = logging.getLogger(__name__)

USAGE_GUIDE = (
    "🎬 *Chess Video Translator Bot*\n\n"
    "Kirim video analisis catur berbahasa Indonesia, "
    "dan saya akan menerjemahkannya ke bahasa Inggris "
    "dengan audio dan subtitle\\.\n\n"
    "*Cara penggunaan:*\n"
    "1\\. Kirim file video langsung \\(MP4, AVI, MKV, MOV, WEBM\\)\n"
    "2\\. Kirim link Google Drive ke video \\(pastikan public\\)\n\n"
    "*Format yang didukung:* MP4, AVI, MKV, MOV, WEBM"
)

UNSUPPORTED_FORMAT_MSG = (
    "❌ Format file tidak didukung\\.\n\n"
    "Format video yang didukung: MP4, AVI, MKV, MOV, WEBM\\.\n"
    "Silakan kirim ulang dengan format yang benar\\."
)

DRIVE_INACCESSIBLE_MSG = (
    "❌ Link Google Drive tidak dapat diakses atau tidak valid\\.\n\n"
    "Pastikan:\n"
    "1\\. Link sudah benar\n"
    "2\\. File di\\-share secara publik \\(Anyone with the link\\)\n"
    "3\\. File adalah video dengan format yang didukung"
)


class TelegramBotHandler:
    """Handler untuk interaksi Telegram Bot."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    async def handle_video(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle video file sent by user."""
        chat_id = update.effective_chat.id
        video = update.message.video

        file_name = video.file_name or "video.mp4"
        extension = Path(file_name).suffix

        if not is_supported_video_format(extension):
            await context.bot.send_message(
                chat_id=chat_id,
                text=UNSUPPORTED_FORMAT_MSG,
                parse_mode="MarkdownV2",
            )
            return

        work_dir = self.config.temp_dir / str(uuid.uuid4())
        work_dir.mkdir(parents=True, exist_ok=True)
        video_path = work_dir / file_name

        try:
            tg_file = await video.get_file()
            await tg_file.download_to_drive(str(video_path))
        except Exception as exc:
            logger.error("Failed to download video from Telegram: %s", exc)
            await self.send_error(chat_id, f"Gagal mengunduh video: {exc}", context)
            return

        await self._process_video(chat_id, video_path, work_dir, context)

    async def handle_document(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle document (video sent as file) by user."""
        chat_id = update.effective_chat.id
        document = update.message.document

        file_name = document.file_name or "video"
        extension = Path(file_name).suffix

        if not is_supported_video_format(extension):
            await context.bot.send_message(
                chat_id=chat_id,
                text=UNSUPPORTED_FORMAT_MSG,
                parse_mode="MarkdownV2",
            )
            return

        work_dir = self.config.temp_dir / str(uuid.uuid4())
        work_dir.mkdir(parents=True, exist_ok=True)
        video_path = work_dir / file_name

        try:
            tg_file = await document.get_file()
            await tg_file.download_to_drive(str(video_path))
        except Exception as exc:
            logger.error("Failed to download document from Telegram: %s", exc)
            await self.send_error(
                chat_id, f"Gagal mengunduh dokumen: {exc}", context
            )
            return

        await self._process_video(chat_id, video_path, work_dir, context)

    async def handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle text message: check for Google Drive link or show usage guide."""
        chat_id = update.effective_chat.id
        text = update.message.text or ""

        if is_drive_url(text):
            await self._handle_drive_link(chat_id, text, context)
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=USAGE_GUIDE,
                parse_mode="MarkdownV2",
            )

    async def _handle_drive_link(
        self,
        chat_id: int,
        drive_url: str,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Download video from Google Drive (direct, no API) and start pipeline."""
        work_dir = self.config.temp_dir / str(uuid.uuid4())
        work_dir.mkdir(parents=True, exist_ok=True)
        video_path = work_dir / "drive_video.mp4"

        await context.bot.send_message(
            chat_id=chat_id,
            text="⬇️ Mengunduh video dari Google Drive...",
        )

        try:
            # Run download in thread to avoid blocking event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: download_from_drive(drive_url, video_path),
            )
        except DriveDownloadError:
            logger.exception("Failed to download from Google Drive")
            await context.bot.send_message(
                chat_id=chat_id,
                text=DRIVE_INACCESSIBLE_MSG,
                parse_mode="MarkdownV2",
            )
            return
        except Exception as exc:
            logger.error("Unexpected error downloading from Drive: %s", exc)
            await self.send_error(
                chat_id, f"Gagal mengunduh dari Google Drive: {exc}", context
            )
            return

        await self._process_video(chat_id, video_path, work_dir, context)

    async def send_progress(
        self,
        chat_id: int,
        stage: str,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Send a progress status message to the user."""
        try:
            await context.bot.send_message(chat_id=chat_id, text=f"⏳ {stage}")
        except Exception:
            logger.warning("Failed to send progress message for stage: %s", stage)

    async def send_result(
        self,
        chat_id: int,
        video_path: Path,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Send the result video to the user via Telegram.

        Sends as document if > 50MB (Telegram allows up to 2GB for documents via bot).
        Sends as video if <= 50MB.
        Retries once on timeout.
        """
        file_size = video_path.stat().st_size

        for attempt in range(2):  # retry once on timeout
            try:
                if file_size > self.config.telegram_file_limit:
                    with open(video_path, "rb") as f:
                        await context.bot.send_document(
                            chat_id=chat_id,
                            document=f,
                            caption="✅ Video berhasil diterjemahkan! (dikirim sebagai file karena ukuran > 50MB)",
                            read_timeout=600,
                            write_timeout=600,
                            connect_timeout=120,
                        )
                else:
                    with open(video_path, "rb") as f:
                        await context.bot.send_video(
                            chat_id=chat_id,
                            video=f,
                            caption="✅ Video berhasil diterjemahkan!",
                            read_timeout=600,
                            write_timeout=600,
                            connect_timeout=120,
                        )
                return  # success
            except Exception as exc:
                if attempt == 0 and "Timed out" in str(exc):
                    logger.warning("Send attempt %d timed out, retrying...", attempt + 1)
                    continue
                logger.error("Failed to send video via Telegram: %s", exc)
                await self.send_error(
                    chat_id,
                    f"Gagal mengirim video: {exc}",
                    context,
                )

    async def send_error(
        self,
        chat_id: int,
        error_message: str,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Send an error message to the user."""
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ {error_message}",
            )
        except Exception:
            logger.warning("Failed to send error message to chat %s", chat_id)

    async def _process_video(
        self,
        chat_id: int,
        video_path: Path,
        work_dir: Path,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Run the translation pipeline."""
        await context.bot.send_message(
            chat_id=chat_id,
            text="🎬 Memulai pemrosesan video... Ini mungkin memakan waktu beberapa menit.",
        )

        async def progress_callback(stage: str) -> None:
            await self.send_progress(chat_id, stage, context)

        pipeline = PipelineProcessor(
            work_dir=work_dir,
            progress_callback=progress_callback,
            config=self.config,
        )

        try:
            output_path = await pipeline.process(video_path)
            await self.send_result(chat_id, output_path, context)
        except PipelineError as exc:
            error_msg = format_error_message(exc.stage, str(exc))
            await self.send_error(chat_id, error_msg, context)
        except Exception as exc:
            logger.exception("Unexpected error during pipeline processing")
            await self.send_error(
                chat_id,
                f"Terjadi kesalahan tak terduga: {exc}",
                context,
            )
        finally:
            # Cleanup work_dir after sending (or on error)
            pipeline.cleanup()
