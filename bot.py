import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, APIC

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получаем токен из переменных окружения
BOT_TOKEN = os.environ.get('8283286774:AAEY6R72BHGHg-ef5CkSDF_wyWFtw-Tu_Nk')

if not BOT_TOKEN:
    logger.error("BOT_TOKEN не установлен!")
    exit(1)

# Состояния
WAITING_FOR_TITLE, WAITING_FOR_ARTIST, WAITING_FOR_PHOTO = range(3)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start - показывает главное меню"""
    keyboard = [
        [InlineKeyboardButton("📝 Изменить название", callback_data="change_title")],
        [InlineKeyboardButton("🎤 Изменить исполнителя", callback_data="change_artist")],
        [InlineKeyboardButton("🖼️ Изменить обложку", callback_data="change_cover")],
        [InlineKeyboardButton("📊 Показать теги", callback_data="show_tags")],
        [InlineKeyboardButton("📥 Скачать файл", callback_data="download_file")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🎵 Добро пожаловать в MP3 Tag Editor!\n\n"
        "Отправьте мне MP3-файл, а затем используйте кнопки ниже для редактирования тегов.",
        reply_markup=reply_markup
    )

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает входящий MP3-файл"""
    audio_file = update.message.audio
    
    if not audio_file or audio_file.mime_type != "audio/mpeg":
        await update.message.reply_text("❌ Пожалуйста, отправьте файл в формате MP3.")
        return

    try:
        # Скачиваем файл
        file = await audio_file.get_file()
        file_path = f"temp_{audio_file.file_id}.mp3"
        await file.download_to_drive(file_path)
        
        # Сохраняем информацию о файле
        context.user_data['current_file_path'] = file_path
        context.user_data['original_file_id'] = audio_file.file_id
        
        # Инициализируем ID3 теги если их нет
        audio = MP3(file_path, ID3=ID3)
        if audio.tags is None:
            audio.add_tags()
            audio.save()
            
        await show_main_menu(update.message, "✅ Файл получен! Выберите действие:")
        
    except Exception as e:
        logger.error(f"Ошибка при обработке аудио: {e}")
        await update.message.reply_text("❌ Ошибка при обработке файла. Попробуйте другой файл.")

async def show_main_menu(message, text="Выберите действие:"):
    """Показывает главное меню с кнопками"""
    keyboard = [
        [InlineKeyboardButton("📝 Изменить название", callback_data="change_title")],
        [InlineKeyboardButton("🎤 Изменить исполнителя", callback_data="change_artist")],
        [InlineKeyboardButton("🖼️ Изменить обложку", callback_data="change_cover")],
        [InlineKeyboardButton("📊 Показать теги", callback_data="show_tags")],
        [InlineKeyboardButton("📥 Скачать файл", callback_data="download_file")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(text, reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия кнопок"""
    query = update.callback_query
    await query.answer()
    
    if 'current_file_path' not in context.user_data:
        await query.edit_message_text("❌ Сначала отправьте мне MP3-файл.")
        return
    
    data = query.data
    
    if data == "change_title":
        await query.edit_message_text("✏️ Введите новое название для аудиозаписи:")
        context.user_data['waiting_for'] = WAITING_FOR_TITLE
        
    elif data == "change_artist":
        await query.edit_message_text("🎤 Введите имя исполнителя:")
        context.user_data['waiting_for'] = WAITING_FOR_ARTIST
        
    elif data == "change_cover":
        await query.edit_message_text("🖼️ Отправьте обложку для аудиозаписи:")
        context.user_data['waiting_for'] = WAITING_FOR_PHOTO
        
    elif data == "show_tags":
        await show_current_tags(query, context)
        
    elif data == "download_file":
        await send_edited_file(query, context)
        
    elif data == "back_to_menu":
        await show_main_menu(query.message, "Главное меню:")

async def show_current_tags(query, context):
    """Показывает текущие теги файла"""
    file_path = context.user_data['current_file_path']
    
    try:
        audio = MP3(file_path, ID3=ID3)
        
        title = "Не указан"
        artist = "Не указан"
        
        if 'TIT2' in audio:
            title = str(audio['TIT2'])
        if 'TPE1' in audio:
            artist = str(audio['TPE1'])
        
        # Проверяем наличие обложки
        has_cover = False
        if audio.tags:
            for key in audio.tags.keys():
                if key.startswith('APIC'):
                    has_cover = True
                    break
        
        tags_info = (
            "📊 Текущие теги:\n\n"
            f"📝 Название: {title}\n"
            f"🎤 Исполнитель: {artist}\n"
            f"🖼️ Обложка: {'✅ Есть' if has_cover else '❌ Нет'}"
        )
        
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(tags_info, reply_markup=reply_markup)
        
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка при чтении тегов: {e}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает текстовые сообщения"""
    if 'waiting_for' not in context.user_data:
        return
    
    user_text = update.message.text
    file_path = context.user_data['current_file_path']
    waiting_for = context.user_data['waiting_for']
    
    try:
        audio = MP3(file_path, ID3=ID3)
        
        if waiting_for == WAITING_FOR_TITLE:
            audio['TIT2'] = TIT2(encoding=3, text=user_text)
            action_text = "название"
            
        elif waiting_for == WAITING_FOR_ARTIST:
            audio['TPE1'] = TPE1(encoding=3, text=user_text)
            action_text = "имя исполнителя"
        
        audio.save()
        del context.user_data['waiting_for']
        
        await update.message.reply_text(f"✅ {action_text.capitalize()} успешно изменено!")
        await show_main_menu(update.message, "Что дальше?")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при изменении тега: {e}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает отправку фотографии из галереи"""
    if 'waiting_for' not in context.user_data or context.user_data['waiting_for'] != WAITING_FOR_PHOTO:
        return
    
    file_path = context.user_data['current_file_path']
    photo_path = f"temp_cover_{update.update_id}.jpg"
    
    try:
        # Берем фото с наибольшим разрешением
        photo_file = await update.message.photo[-1].get_file()
        await photo_file.download_to_drive(photo_path)
        
        # Читаем данные обложки
        with open(photo_path, 'rb') as f:
            cover_data = f.read()
        
        # Обрабатываем MP3 файл
        audio = MP3(file_path, ID3=ID3)
        
        # Убедимся, что теги существуют
        if audio.tags is None:
            audio.add_tags()
        
        # Удаляем старые обложки
        apic_keys = [key for key in audio.tags.keys() if key.startswith('APIC')]
        for key in apic_keys:
            del audio.tags[key]
        
        # Добавляем новую обложку
        audio.tags.add(
            APIC(
                encoding=3,
                mime='image/jpeg',
                type=3,
                desc='Cover',
                data=cover_data
            )
        )
        
        audio.save()
        
        # Убираем состояние ожидания
        del context.user_data['waiting_for']
        
        await update.message.reply_text("✅ Обложка успешно обновлена!")
        await show_main_menu(update.message, "Что дальше?")
        
    except Exception as e:
        logger.error(f"Ошибка при установке обложки: {e}")
        await update.message.reply_text("❌ Не удалось установить обложку. Попробуйте другой файл.")
        
    finally:
        # Удаляем временный файл обложки
        if os.path.exists(photo_path):
            os.remove(photo_path)

async def send_edited_file(query, context):
    """Отправляет отредактированный файл пользователю"""
    file_path = context.user_data['current_file_path']
    
    try:
        # Проверяем теги перед отправкой
        audio = MP3(file_path, ID3=ID3)
        title = str(audio['TIT2']) if 'TIT2' in audio else "Не указано"
        artist = str(audio['TPE1']) if 'TPE1' in audio else "Не указано"
        
        has_cover = False
        if audio.tags:
            has_cover = any(key.startswith('APIC') for key in audio.tags.keys())
        
        caption = (
            f"✅ Ваш отредактированный файл готов!\n\n"
            f"📝 Название: {title}\n"
            f"🎤 Исполнитель: {artist}\n"
            f"🖼️ Обложка: {'✅ Есть' if has_cover else '❌ Нет'}"
        )
        
        with open(file_path, 'rb') as audio_file:
            await query.message.reply_audio(
                audio=audio_file,
                caption=caption,
                title=title,
                performer=artist
            )
        
        # Очищаем временные файлы
        if os.path.exists(file_path):
            os.remove(file_path)
            del context.user_data['current_file_path']
            
        await show_main_menu(query.message, "Файл отправлен! Что дальше?")
        
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка при отправке файла: {e}")

def main():
    """Запускает бота"""
    try:
        # Создаем Application
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Обработчики команд
        application.add_handler(CommandHandler("start", start))
        
        # Обработчики кнопок
        application.add_handler(CallbackQueryHandler(button_handler))
        
        # Обработчики сообщений
        application.add_handler(MessageHandler(filters.AUDIO, handle_audio))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        
        # Запускаем бота
        print("🚀 Бот запущен в режиме polling...")
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        print(f"❌ Критическая ошибка: {e}")

if __name__ == '__main__':
    main()
