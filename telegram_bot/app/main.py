import logging
import os

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from .client import ask_orchestrator, sync_body_pdf
from .vihealth import build_sync_payload

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


async def cmd_body(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = " ".join(context.args) if context.args else "what's my current body composition"
    await _reply(update, f"body {text}")


async def cmd_mood(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = " ".join(context.args) if context.args else "how has my mood been lately"
    await _reply(update, f"mood {text}")


async def cmd_journal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = " ".join(context.args) if context.args else "journal entry placeholder"
    await _reply(update, f"mood {text}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply(update, update.message.text)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    doc = update.message.document
    if not doc or not doc.file_name or not doc.file_name.lower().endswith(".pdf"):
        await update.message.reply_text("Send a ViHealth PDF report to import body composition data.")
        return

    thinking = await update.message.reply_text("Analysing ViHealth report...")
    tg_file = await doc.get_file()
    pdf_bytes = bytes(await tg_file.download_as_bytearray())

    try:
        payload = build_sync_payload(pdf_bytes)
    except Exception as e:
        await thinking.edit_text(f"Could not parse PDF: {e}")
        return

    result = await sync_body_pdf(payload)
    await thinking.edit_text(result)


def main() -> None:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("sleep", cmd_sleep))
    app.add_handler(CommandHandler("workout", cmd_workout))
    app.add_handler(CommandHandler("nutrition", cmd_nutrition))
    app.add_handler(CommandHandler("body", cmd_body))
    app.add_handler(CommandHandler("mood", cmd_mood))
    app.add_handler(CommandHandler("journal", cmd_journal))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_document))
    logger.info("Bot started, polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
