import logging
import os

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from .client import ask_orchestrator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]


async def _reply(update: Update, message: str) -> None:
    """Send message to orchestrator and reply with the result."""
    thinking = await update.message.reply_text("...")
    output = await ask_orchestrator(message)
    if len(output) > 4096:
        output = output[:4090] + "\n[truncated]"
    try:
        await thinking.edit_text(output)
    except Exception:
        await update.message.reply_text(output)


async def cmd_sleep(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = " ".join(context.args) if context.args else "analyze my sleep"
    await _reply(update, f"sleep {text}")


async def cmd_workout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = " ".join(context.args) if context.args else "analyze my workout"
    await _reply(update, f"workout {text}")


async def cmd_nutrition(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = " ".join(context.args) if context.args else "analyze my nutrition"
    await _reply(update, f"nutrition {text}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply(update, update.message.text)


def main() -> None:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("sleep", cmd_sleep))
    app.add_handler(CommandHandler("workout", cmd_workout))
    app.add_handler(CommandHandler("nutrition", cmd_nutrition))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot started, polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
