import logging
import re
import os
import httpx
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

async def ask_groq(user: dict, prompt: str) -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return "Internal Error: GROQ_API_KEY is not configured."
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    system_content = (
        "You are an expert, highly capable AI assistant powered by state-of-the-art models. "
        "Provide accurate, insightful, and well-structured answers."
    )
    if user.get("name"):
        system_content += f" The user's name is {user.get('name')}."
    if user.get("project"):
        system_content += f" The user is working on a project named {user.get('project')}."

    messages = [{"role": "system", "content": system_content}]
    
    history = user.get("chat_history", [])
    messages.extend(history)
    messages.append({"role": "user", "content": prompt})

    data = {
        "model": "llama-3.3-70b-versatile",
        "messages": messages,
        "max_tokens": 2048
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=data, timeout=30.0)
            response.raise_for_status()
            result = response.json()
            reply = result["choices"][0]["message"]["content"]

            history.append({"role": "user", "content": prompt})
            history.append({"role": "assistant", "content": reply})
            storage.update_user(user["chat_id"], "chat_history", history[-20:])

            return reply
    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return "Sorry, I couldn't reach the AI at the moment."

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _log_request(update, "COMMAND /start")
    chat_id = str(update.effective_chat.id)
    username = update.effective_user.username or update.effective_user.first_name

    user = storage.find_user(chat_id)
    if not user:
        storage.create_user(chat_id, username)

    await update.message.reply_text("Welcome! I am your AI Chatbot and Daily Reporter. Use /setup if you want to configure daily reporting, or just start chatting!")

async def setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _log_request(update, "COMMAND /setup")
    chat_id = str(update.effective_chat.id)
    username = update.effective_user.username or update.effective_user.first_name

    user = storage.find_user(chat_id)
    if not user:
        storage.create_user(chat_id, username)

    storage.update_user(chat_id, "name", None)
    storage.update_user(chat_id, "project", None)
    storage.update_user(chat_id, "step", "ASK_NAME")
    await update.message.reply_text("Let's set up your profile for daily reports!\nPlease enter your name:")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _log_request(update, "MESSAGE")
    chat_id = str(update.effective_chat.id)
    text = update.message.text.strip()
    user = storage.find_user(chat_id)

    if not user:
        user = storage.create_user(chat_id, update.effective_user.username or update.effective_user.first_name)

    step = user.get("step")

    if step == "ASK_NAME":
        storage.update_user(chat_id, "name", text)
        storage.update_user(chat_id, "step", "ASK_PROJECT")
        return await update.message.reply_text("Got it!\nNow enter your project:")

    if step == "ASK_PROJECT":
        storage.update_user(chat_id, "project", text)
        storage.update_user(chat_id, "step", "READY")
        return await update.message.reply_text("Setup complete! You can now log tasks or chat with me.")

    # Process report OR Chat
    match = re.search(r"(\d+)%?$", text)
    
    if not match:
        await update.message.chat.send_action(action="typing")
        reply = await ask_groq(user, text)
        return await update.message.reply_text(reply)

    percent = int(match.group(1))
    task = re.sub(r"\s*(\d+)%?$", "", text).strip()

    if not task:
        # If it's just a number without task text, also treat as chat
        await update.message.chat.send_action(action="typing")
        reply = await ask_groq(user, text)
        return await update.message.reply_text(reply)

    if not user.get("name") or not user.get("project"):
        return await update.message.reply_text("You haven't set up your profile for tracking tasks yet. Please use /setup first.")

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

    sep = ""
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

async def show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _log_request(update, "COMMAND /show")
    chat_id = str(update.effective_chat.id)
    user = storage.find_user(chat_id)
    
    if not user or not user.get("name") or not user.get("project"):
        return await update.message.reply_text("Please use /start to set your name and project first.")
        
    now = datetime.now()
    date_str = now.strftime("%d-%m-%Y")
    date_display = now.strftime("%d %B %Y")
    
    report_data = storage.load_today_report(user, date_str)
    tasks = report_data.get("tasks", []) if report_data else []
    
    if not tasks:
        return await update.message.reply_text("You have no tasks recorded for today.")
        
    completed = [t for t in tasks if t["status"] == "Completed"]
    in_progress = [t for t in tasks if t["status"] == "In Progress"]
    
    sep = ""
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

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _log_request(update, "COMMAND /clear")
    chat_id = str(update.effective_chat.id)
    user = storage.find_user(chat_id)
    
    if not user or not user.get("name"):
        return await update.message.reply_text("Please use /start to set your name first.")
        
    now = datetime.now()
    date_str = now.strftime("%d-%m-%Y")
    storage.clear_today_report(user, date_str)
    await update.message.reply_text("Today's tasks have been cleared.")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _log_request(update, "COMMAND /reset")
    chat_id = str(update.effective_chat.id)
    user = storage.find_user(chat_id)
    
    if not user:
        return await update.message.reply_text("Please use /start to set your name first.")

    storage.update_user(chat_id, "name", None)
    storage.update_user(chat_id, "project", None)
    storage.update_user(chat_id, "step", "ASK_NAME")
    await update.message.reply_text("Your name and project have been reset. Please enter your name:")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _log_request(update, "COMMAND /profile")
    chat_id = str(update.effective_chat.id)
    user = storage.find_user(chat_id)
    
    if not user or not user.get("name") or not user.get("project"):
        return await update.message.reply_text("You haven't set up your profile yet. Please use /start.")
        
    name = user.get("name")
    project = user.get("project")
    await update.message.reply_text(f"Profile Information:\nName: {name}\nProject: {project}")
