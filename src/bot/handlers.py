import logging
import re
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from src.bot import storage

logger = logging.getLogger(__name__)

def _log_request(update: Update, action: str):
    user = update.effective_user
    logger.info(
        f"chat_id={update.effective_chat.id} user={user.username or user.first_name} "
        f"action={action} text=\"{update.message.text}\""
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _log_request(update, "COMMAND /start")
    chat_id = str(update.effective_chat.id)
    username = update.effective_user.username or update.effective_user.first_name

    user = storage.find_user(chat_id)
    if not user:
        user = storage.create_user(chat_id, username)

    if user.get("name") and user.get("project"):
        await update.message.reply_text("Welcome back! You're already set up.")
    else:
        await update.message.reply_text("Welcome!\nPlease enter your name:")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _log_request(update, "MESSAGE")
    chat_id = str(update.effective_chat.id)
    text = update.message.text.strip()
    user = storage.find_user(chat_id)

    if not user:
        return await update.message.reply_text("Use /start first")

    if not user.get("name"):
        storage.update_user(chat_id, "name", text)
        storage.update_user(chat_id, "step", "ASK_PROJECT")
        return await update.message.reply_text("Got it!\nNow enter your project:")

    if not user.get("project"):
        storage.update_user(chat_id, "project", text)
        storage.update_user(chat_id, "step", "READY")
        return await update.message.reply_text("Setup complete!")

    # Process report
    match = re.search(r"(\d+)%?$", text)
    percent = int(match.group(1)) if match else 0
    task = re.sub(r"\s*(\d+)%?$", "", text).strip()

    if not task:
        return await update.message.reply_text("Please include a task description, e.g. fixed bugs 100%")

    status_text = "Completed" if percent == 100 else "In Progress"

    now = datetime.now()
    date_str = now.strftime("%d-%m-%Y")
    date_display = now.strftime("%d %B %Y")

    storage.save_report(user, task, percent, status_text, date_str, now.strftime("%H:%M"))

    # Build formatted report
    report_data = storage.load_today_report(user, date_str)
    tasks = report_data.get("tasks", []) if report_data else []

    completed = [t for t in tasks if t["status"] == "Completed"]
    in_progress = [t for t in tasks if t["status"] == "In Progress"]

    sep = "\u2501" * 24
    lines = []
    lines.append("DAILY PROGRESS REPORT")
    lines.append(sep)
    lines.append(f"Date: {date_display}")
    lines.append(f"Employee: {user.get('name')}")
    lines.append(f"Project: {user.get('project')}")
    lines.append(sep)
    lines.append("1. Code Inspection")
    lines.append("Status: N/A")
    lines.append("2. Progress on Tasks")
    if completed:
        lines.append("Completed")
        for t in completed:
            lines.append(f"\u2022 {t['task']} ({t['percent']}%)")
    if in_progress:
        lines.append("In Progress")
        for t in in_progress:
            lines.append(f"\u2022 {t['task']} ({t['percent']}%)")
    if not completed and not in_progress:
        lines.append("Status: N/A")
    lines.append("3. Challenges / Issues")
    lines.append("Status: N/A")
    lines.append("4. Problem-Solving Approach")
    lines.append("Status: N/A")
    lines.append(sep)

    await update.message.reply_text("\n".join(lines))
