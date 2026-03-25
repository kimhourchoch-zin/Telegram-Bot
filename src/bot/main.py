import os
import logging
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from src.bot.handlers import start, handle_message

load_dotenv()
TOKEN = os.getenv("TOKEN")

logging.basicConfig(
    format='[%(levelname)s] %(asctime)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def run():
    if not TOKEN:
        logger.error("No TOKEN provided!")
        return

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Starting bot...")
    app.run_polling()
