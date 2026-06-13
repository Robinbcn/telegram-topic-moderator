import os
import json
import re
import logging

from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
CONFIG_FILE = "config.json"

# ---------------- LOGGING ----------------

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("bot_pedidos")


# ---------------- CONFIG ----------------

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    return {
        "pedidos_chat": None,
        "destino_thread": None,
    }


def save_config(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)


config = load_config()


# ---------------- COMMANDS ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot de pedidos activo.")


async def setdestino(update: Update, context: ContextTypes.DEFAULT_TYPE):
    thread_id = update.message.message_thread_id

    if not thread_id:
        await update.message.reply_text(
            "❌ Este comando debe ejecutarse dentro del tema destino."
        )
        return

    config["pedidos_chat"] = update.message.chat_id
    config["destino_thread"] = thread_id

    save_config(config)

    log.info(
        "Destino configurado: chat=%s thread=%s",
        update.message.chat_id, thread_id,
    )

    await update.message.reply_text(
        f"✅ Destino configurado.\n"
        f"Chat: {update.message.chat_id}\n"
        f"Tema: {thread_id}"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📌 Chat pedidos: {config['pedidos_chat']}\n"
        f"📦 Tema destino: {config['destino_thread']}\n"
        f"🆔 Este chat: {update.message.chat_id}"
    )


# ---------------- CORE LOGIC ----------------

async def process_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message

    if not message:
        return

    log.info(
        "Mensaje recibido | chat=%s thread=%s foto=%s texto=%r",
        message.chat_id,
        message.message_thread_id,
        bool(message.photo),
        (message.caption or message.text or "")[:50],
    )

    if message.from_user and message.from_user.is_bot:
        return

    pedidos_chat = config.get("pedidos_chat")
    destino_thread = config.get("destino_thread")

    if not pedidos_chat or not destino_thread:
        log.warning("Sin configurar. Ejecuta /setdestino en el tema destino.")
        return

    # Solo actuar en el grupo configurado
    if message.chat_id != pedidos_chat:
        log.warning(
            "Chat distinto al configurado: recibido=%s esperado=%s "
            "(si activaste temas, el chat_id cambió: vuelve a ejecutar /setdestino)",
            message.chat_id, pedidos_chat,
        )
        return

    # No procesar mensajes del propio tema destino (evitar bucles)
    if message.message_thread_id == destino_thread:
        return

    text = message.caption or message.text or ""

    if not text:
        return

    bot_username = context.bot.username.lower()

    # Debe mencionar al bot (por texto o por entidad de mención)
    if f"@{bot_username}" not in text.lower():
        return

    log.info("Mención detectada, procesando pedido...")

    username = (
        f"@{message.from_user.username}"
        if message.from_user.username
        else message.from_user.first_name
    )

    # Debe tener imagen
    if not message.photo:
        try:
            await message.delete()
        except Exception as e:
            log.warning("No pude borrar el mensaje: %s", e)
            await context.bot.send_message(
            chat_id=message.chat_id,
            message_thread_id=message.message_thread_id,
            text=(
                f"{username} ❌ Pedido inválido.\n"
                "Debe incluir una imagen y una descripción."
            )
        )
        return

    # Quitar mención del bot
    clean_text = re.sub(
        rf"@{re.escape(bot_username)}",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()

    # Debe quedar descripción real
    if not clean_text:
        try:
            await message.delete()
        except Exception as e:
            log.warning("No pude borrar el mensaje: %s", e)

        await context.bot.send_message(
            chat_id=message.chat_id,
            message_thread_id=message.message_thread_id,
            text=(
                f"{username} ❌ Pedido inválido.\n"
                "Debes añadir una descripción además de mencionar al bot."
            )
        )
        return

    final_caption = (
        f"{clean_text}\n\n"
        f"Pedido realizado por {username}"
    )

    photo = message.photo[-1].file_id

    # Enviar al tema destino
    await context.bot.send_photo(
        chat_id=message.chat_id,
        message_thread_id=destino_thread,
        photo=photo,
        caption=final_caption,
    )

    log.info("Pedido enviado al tema destino %s", destino_thread)

    # Borrar mensaje original
    try:
        await message.delete()
    except Exception as e:
        log.warning("No pude borrar el original: %s", e)

    # Confirmación
    await context.bot.send_message(
        chat_id=message.chat_id,
        message_thread_id=message.message_thread_id,
        text=f"{username} ✅ Pedido realizado."
    )


# ---------------- MAIN ----------------

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setdestino", setdestino))
    app.add_handler(CommandHandler("status", status))

    app.add_handler(
        MessageHandler(
            filters.ALL,
            process_message
        )
    )

    print("🤖 Bot iniciado...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
