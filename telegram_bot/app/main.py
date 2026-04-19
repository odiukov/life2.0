import logging
import os
import re

from telegram import BotCommand, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters, ContextTypes


_BOT_COMMANDS: list[BotCommand] = [
    BotCommand("sleep", "Анализ сна / запись"),
    BotCommand("workout", "Тренировки / запись"),
    BotCommand("nutrition", "Питание / запись"),
    BotCommand("body", "Состав тела"),
    BotCommand("mood", "Записать настроение"),
    BotCommand("journal", "Свободная запись (как /mood)"),
    BotCommand("coach", "Коуч-сессия (/coach stop — выход)"),
    BotCommand("habits", "Список привычек + отметка"),
    BotCommand("habit", "Отметка привычки / создание / архив"),
    BotCommand("med", "Приём лекарств / создание / архив / список"),
    BotCommand("sync", "Запустить утренний синк + бриф вручную"),
    BotCommand("new", "Начать новый разговор (сбросить контекст)"),
    BotCommand("dashboard", "Полный обзор (on-demand)"),
]


async def _set_commands(app: Application) -> None:
    await app.bot.set_my_commands(_BOT_COMMANDS)

from .client import ask_orchestrator, sync_body_pdf, habits_a2a_call, trigger_full_sync, fetch_dashboard, medication_a2a_call, upload_finance_csv
from .threads import bump_reset_count, compute_thread_id
from .habits_ui import on_habit_callback
from .vihealth import build_sync_payload
from .coach import CoachLoop, CoachAlreadyActive, CoachUnavailable, default_llm_call, default_log_mood_call

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

_MAX_COACH_TURNS = int(os.environ.get("MAX_COACH_TURNS", "6"))

try:
    _COACH: CoachLoop | None = CoachLoop(
        llm_call=default_llm_call(),
        log_mood_call=default_log_mood_call(),
        max_turns=_MAX_COACH_TURNS,
    )
except Exception as e:
    logger.warning("Coach disabled at startup: %s", e)
    _COACH = None


async def _reply(update: Update, message: str) -> None:
    """Send message to orchestrator and reply with the result."""
    thread_id = compute_thread_id(update.effective_chat.id)
    thinking = await update.message.reply_text("...")
    output = await ask_orchestrator(message, thread_id)
    _MARKER = "\n[truncated]"
    if len(output) > 4096:
        output = output[: 4096 - len(_MARKER)] + _MARKER
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


async def cmd_coach(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if _COACH is None:
        await update.message.reply_text("Coach unavailable (GROQ_API_KEY not set).")
        return
    chat_id = update.effective_chat.id
    args = context.args or []
    if args and args[0].lower() == "stop":
        reply = await _COACH.stop(chat_id=chat_id)
        await update.message.reply_text(reply)
        return
    if _COACH.has_session(chat_id):
        await update.message.reply_text("You already have an active session. Use /coach stop to end it.")
        return
    try:
        reply = await _COACH.start(chat_id=chat_id, recent_context="")
    except CoachAlreadyActive:
        await update.message.reply_text("You already have an active session.")
        return
    except CoachUnavailable:
        await update.message.reply_text("Coach unavailable right now, try later.")
        return
    await update.message.reply_text(reply)


async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reset the current Telegram conversation thread for this chat."""
    bump_reset_count(update.effective_chat.id)
    await update.message.reply_text("Новый разговор начат ✨")


async def cmd_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    thinking = await update.message.reply_text("Собираю дашборд...")
    try:
        text = await fetch_dashboard()
    except Exception as e:
        await thinking.edit_text(f"Dashboard unavailable: {e}")
        return
    if len(text) > 4096:
        text = text[: 4096 - len(_MARKER)] + _MARKER
    try:
        await thinking.edit_text(text)
    except Exception:
        await update.message.reply_text(text)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if _COACH is not None and _COACH.has_session(chat_id):
        try:
            reply = await _COACH.continue_(chat_id=chat_id, user_text=update.message.text)
        except CoachUnavailable:
            await update.message.reply_text("Coach unavailable. Session closed.")
            return
        await update.message.reply_text(reply)
        return
    await _reply(update, update.message.text)


async def handle_finance_csv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    doc = update.message.document
    if not doc:
        return
    thinking = await update.message.reply_text("Обрабатываю CSV…")
    tg_file = await doc.get_file()
    blob = bytes(await tg_file.download_as_bytearray())
    result = await upload_finance_csv(blob, filename=doc.file_name or "payoneer.csv")
    if "error" in result:
        await thinking.edit_text(result["error"])
        return
    await thinking.edit_text(result.get("summary", "(empty summary)"))


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


_HABIT_VALUE_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*([A-Za-z]+)?$")


def parse_habit_args(args: list[str]) -> dict:
    """Parse `/habit <args>` into a structured dict.

    Reserved first-words:
      - 'new <free text>' → {"action": "new", "text": <free text>}
      - 'stop <name>'     → {"action": "stop", "name": <name>}

    Otherwise:
      - 'name'                       → {"name": ...}
      - 'name VALUEunit'             → {"name": ..., "value": float, "unit": ...}
      - 'name VALUE unit [note...]'  → {"name": ..., "value": float, "unit": ..., "note": ...}
    """
    if not args:
        return {}
    if args[0].lower() == "new":
        return {"action": "new", "text": " ".join(args[1:])}
    if args[0].lower() == "stop":
        return {"action": "stop", "name": args[1] if len(args) > 1 else ""}

    name = args[0]
    if len(args) == 1:
        return {"name": name}

    # Case "NAME 15min [note...]" — only when value and unit are concatenated (e.g. "15min")
    m = _HABIT_VALUE_RE.match(args[1])
    if m and m.group(2):  # unit present in same token
        value = float(m.group(1))
        unit = m.group(2)
        out = {"name": name, "value": value, "unit": unit}
        if len(args) > 2:
            out["note"] = " ".join(args[2:])
        return out

    # Case "NAME 15 min note..."
    try:
        value = float(args[1])
        out = {"name": name, "value": value}
        if len(args) > 2:
            out["unit"] = args[2]
        if len(args) > 3:
            out["note"] = " ".join(args[3:])
        return out
    except ValueError:
        return {"name": name, "note": " ".join(args[1:])}


async def cmd_habit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    parsed = parse_habit_args(args)

    if not parsed:
        await update.message.reply_text(
            "usage: /habit <name> [value unit], /habit new <description>, /habit stop <name>"
        )
        return

    if parsed.get("action") == "new":
        if not parsed.get("text"):
            await update.message.reply_text("usage: /habit new <description>")
            return
        try:
            text = await habits_a2a_call(
                skill="define_habit", message=parsed["text"], params={"source": "telegram"},
            )
        except Exception:
            await update.message.reply_text("habits agent unavailable — try later")
            return
        await update.message.reply_text(text or "couldn't create habit")
        return

    if parsed.get("action") == "stop":
        if not parsed.get("name"):
            await update.message.reply_text("usage: /habit stop <name>")
            return
        try:
            text = await habits_a2a_call(
                skill="archive_habit", message=f"stop {parsed['name']}",
                params={"name": parsed["name"]},
            )
        except Exception:
            await update.message.reply_text("habits agent unavailable — try later")
            return
        await update.message.reply_text(text or "archived")
        return

    # normal log_habit_check
    log_params = {"source": "telegram", **{k: v for k, v in parsed.items() if k != "name"},
                  "name": parsed["name"]}
    try:
        text = await habits_a2a_call(
            skill="log_habit_check",
            message=f"/habit {' '.join(args)}",
            params=log_params,
        )
    except Exception:
        await update.message.reply_text("habits agent unavailable — try later")
        return
    await update.message.reply_text(text or "logged")


def parse_med_args(args: list[str]) -> dict:
    """Parse /med args.

    Reserved first-words: new | stop | list.
    Otherwise: <name> [dose_override] [note...]
    """
    if not args:
        return {}
    head = args[0].lower()
    if head == "new":
        return {"action": "new", "text": " ".join(args[1:])}
    if head == "stop":
        return {"action": "stop", "name": args[1] if len(args) > 1 else ""}
    if head == "list":
        return {"action": "list"}
    name = args[0]
    if len(args) == 1:
        return {"name": name}
    out: dict = {"name": name, "dose_override": args[1]}
    if len(args) > 2:
        out["note"] = " ".join(args[2:])
    return out


async def cmd_med(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    parsed = parse_med_args(args)

    if not parsed:
        await update.message.reply_text(
            "usage: /med <name> [dose] [note], /med new <desc>, /med stop <name>, /med list"
        )
        return

    if parsed.get("action") == "new":
        if not parsed.get("text"):
            await update.message.reply_text("usage: /med new <description>")
            return
        try:
            text = await medication_a2a_call(
                skill="define_medication", message=parsed["text"], params={"source": "telegram"},
            )
        except Exception:
            await update.message.reply_text("medication agent unavailable — try later")
            return
        await update.message.reply_text(text or "couldn't create medication")
        return

    if parsed.get("action") == "stop":
        if not parsed.get("name"):
            await update.message.reply_text("usage: /med stop <name>")
            return
        try:
            text = await medication_a2a_call(
                skill="archive_medication", message=f"stop {parsed['name']}",
                params={"name": parsed["name"]},
            )
        except Exception:
            await update.message.reply_text("medication agent unavailable — try later")
            return
        await update.message.reply_text(text or "archived")
        return

    if parsed.get("action") == "list":
        try:
            text = await medication_a2a_call(
                skill="list_active", message="list", params={},
            )
        except Exception:
            await update.message.reply_text("medication agent unavailable — try later")
            return
        await update.message.reply_text(text or "no active medications")
        return

    # normal log_taken
    log_params = {"source": "telegram", **{k: v for k, v in parsed.items() if k != "name"},
                  "name": parsed["name"]}
    try:
        text = await medication_a2a_call(
            skill="log_taken", message=f"/med {' '.join(args)}", params=log_params,
        )
    except Exception:
        await update.message.reply_text("medication agent unavailable — try later")
        return
    await update.message.reply_text(text or "logged")


async def cmd_sync(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    thinking = await update.message.reply_text("Syncing Garmin + Yazio…")
    result = await trigger_full_sync()
    try:
        await thinking.edit_text(result)
    except Exception:
        await update.message.reply_text(result)


async def cmd_habits(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from .habits_ui import build_habits_keyboard
    try:
        markup, empty_msg = await build_habits_keyboard()
    except Exception:
        await update.message.reply_text("habits agent unavailable — try later")
        return
    if markup is None:
        await update.message.reply_text(empty_msg)
    else:
        await update.message.reply_text("Active habits:", reply_markup=markup)


def main() -> None:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(_set_commands).build()
    app.add_handler(CommandHandler("sleep", cmd_sleep))
    app.add_handler(CommandHandler("workout", cmd_workout))
    app.add_handler(CommandHandler("nutrition", cmd_nutrition))
    app.add_handler(CommandHandler("body", cmd_body))
    app.add_handler(CommandHandler("mood", cmd_mood))
    app.add_handler(CommandHandler("journal", cmd_journal))
    app.add_handler(CommandHandler("coach", cmd_coach))
    app.add_handler(CommandHandler("habit", cmd_habit))
    app.add_handler(CommandHandler("med", cmd_med))
    app.add_handler(CommandHandler("habits", cmd_habits))
    app.add_handler(CommandHandler("sync", cmd_sync))
    app.add_handler(CommandHandler("new", cmd_new))
    app.add_handler(CommandHandler("dashboard", cmd_dashboard))
    app.add_handler(CallbackQueryHandler(on_habit_callback, pattern=r"^h:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(
        MessageHandler(
            filters.Document.MimeType("text/csv") | filters.Document.FileExtension("csv"),
            handle_finance_csv,
        )
    )
    app.add_handler(MessageHandler(filters.Document.PDF, handle_document))
    logger.info("Bot started, polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
