"""Entry point for Chess Video Translator Telegram Bot."""

from __future__ import annotations

import logging

from telegram.ext import Application, MessageHandler, filters
from telegram.request import HTTPXRequest

from src.bot import TelegramBotHandler
from src.config import load_config

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Load configuration, set up handlers, and start the Telegram bot."""
    config = load_config()
    handler = TelegramBotHandler(config)

    # Build application with extended timeouts for large file uploads
    request = HTTPXRequest(
        read_timeout=600,
        write_timeout=600,
        connect_timeout=60,
    )
    application = (
        Application.builder()
        .token(config.telegram_token)
        .request(request)
        .build()
    )

    # Register handlers: video, document, then text message (fallback)
    application.add_handler(
        MessageHandler(filters.VIDEO, handler.handle_video)
    )
    application.add_handler(
        MessageHandler(filters.Document.ALL, handler.handle_document)
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handler.handle_message)
    )

    logger.info("Bot started. Polling for updates...")
    application.run_polling()


if __name__ == "__main__":
    main()
