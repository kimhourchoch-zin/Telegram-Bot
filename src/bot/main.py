import os
import logging
from dotenv import load_dotenv
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from src.bot.handlers import start, handle_message

# Load env variables
load_dotenv()
TOKEN = os.getenv("TOKEN")

# Setup Logging
logging.basicConfig(
    format='[%(levelname)s] %(asctime)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def run():
    if not TOKEN:
        logger.error("No TELEGRAM_TOKEN provided!")
        return

    # TODO: Switch to Webhooks for Cloudflare
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    
    logger.info("Starting bot...")
    updater.start_polling()
    updater.idle()
