import os
import logging
import requests
import threading
import time
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

BOT_TOKEN = os.environ.get('BOT_TOKEN')

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не установлен!")
    exit(1)

# Состояния
WAITING_FOR_TITLE, WAITING_FOR_ARTIST, WAITING_FOR_PHOTO = range(3)

def keep_alive():
    """Пингует сервер чтобы предотвратить сон на Render"""
    def ping():
        while True:
            try:
                # Получаем URL из переменных окружения или используем дефолтный
                render_url = os.environ.get('RENDER_URL', 'https://your-bot-name.onrender.com')
                
                # Отправляем GET запрос
                response = requests.get(render_url, timeout=10)
                
                if response.status_code == 200:
                    logger.info(f"🏓 Успешный ping в {time.strftime('%H:%M:%S')}")
                else:
                    logger.warning(f"⚠️ Ping вернул статус {response.status_code}")
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"❌ Ошибка ping: {e}")
            except Exception as e:
                logger.error(f"❌ Неожиданная ошибка: {e}")
            
            # Ждем 10 минут перед следующим ping
            time.sleep(600)
    
    try:
        thread = threading.Thread(target=ping)
        thread.daemon = True  # Поток завершится при завершении main потока
        thread.start()
        logger.info("🔄 Keep-alive запущен (ping каждые 10 минут)")
        return True
    except Exception as e:
        logger.error(f"❌ Не удалось запустить keep-alive: {e}")
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start - показывает главное меню"""
    await update.message.reply_text(
        "🎵 Добро пожаловать в MP3 Tag Editor!\n\n"
        "📱 **Как использовать:**\n"
        "1. Отправьте MP3 файл\n"
        "2. Используйте кнопки для редактирования\n"
        "3. Для обложки: нажмите 'Изменить обложку' → выберите фото из галереи",
        reply_markup=get_main_menu()
    )

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает входящий MP3-файл"""
    try:
        audio_file = update.message.audio
        
        if not audio_file or audio_file.mime_type != "audio/mpeg":
            await update.message.reply_text("❌ Пожалуйста, отправьте файл в формате MP3.")
            return

        # ⚠️ ВАЖНО: Очищаем предыдущие данные
        if 'current_file_path' in context.user_data:
            old_path = context.user_data['current_file_path']
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                    logger.info(f"🗑️ Удален старый файл: {old_path}")
                except Exception as e:
                    logger.warning(f"Не удалось удалить старый файл: {e}")
        
        # Очищаем состояние
        context.user_data.clear()

        # Скачиваем новый файл
        file = await audio_file.get_file()
        file_path = f"temp_{audio_file.file_id}_{update.update_id}.mp3"
        await file.download_to_drive(file_path)
        
        # Сохраняем информацию о новом файле
        context.user_data['current_file_path'] = file_path
        
        await update.message.reply_text(
            "✅ Файл получен!\n\n"
            "📱 **Совет:** При отправке обложки просто выберите фото из галереи телефона",
            reply_markup=get_main_menu()
        )
        
    except Exception as e:
        logger.error(f"Ошибка при обработке аудио: {e}")
        await update.message.reply_text("❌ Ошибка при обработке файла.")

def get_main_menu():
    """Возвращает главное меню с кнопками"""
    keyboard = [
        [InlineKeyboardButton("📝 Изменить название", callback_data="change_title")],
        [InlineKeyboardButton("🎤 Изменить исполнителя", callback_data="change_artist")],
        [InlineKeyboardButton("🖼️ Изменить обложку", callback_data="change_cover")],
        [InlineKeyboardButton("📊 Показать теги", callback_data="show_tags")],
        [InlineKeyboardButton("📥 Скачать файл", callback_data="download_file")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия кнопок"""
    query = update.callback_query
    
    try:
        await query.answer()  # Подтверждаем нажатие кнопки
    except Exception as e:
        # Игнорируем ошибки устаревших callback query
        if "too old" in str(e) or "timeout" in str(e) or "invalid" in str(e):
            logger.warning(f"Пропущен устаревший callback: {e}")
            return
        else:
            logger.error(f"Ошибка в callback: {e}")
            return
    
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
        await query.edit_message_text(
            "🖼️ **Отправьте обложку из галереи телефона:**\n\n"
            "1. 📱 Нажмите на скрепку\n"
            "2. 🖼️ Выберите 'Галерея' или 'Фото'\n" 
            "3. ✅ Выберите изображение\n"
            "4. 📤 Отправьте как фото\n\n"
            "_Бот автоматически установит обложку_"
        )
        context.user_data['waiting_for'] = WAITING_FOR_PHOTO
        
    elif data == "show_tags":
        await show_current_tags(query, context)
        
    elif data == "download_file":
        await send_edited_file(query, context)

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
        
        # Проверяем обложку
        has_cover = False
        cover_info = ""
        if audio.tags:
            for key in audio.tags.keys():
                if key.startswith('APIC'):
                    has_cover = True
                    cover_info = f" ({len(audio.tags[key].data)} байт)"
                    break
        
        tags_info = (
            "📊 Текущие теги:\n\n"
            f"📝 Название: {title}\n"
            f"🎤 Исполнитель: {artist}\n"
            f"🖼️ Обложка: {'✅ Есть' + cover_info if has_cover else '❌ Нет'}"
        )
        
        await query.edit_message_text(tags_info, reply_markup=get_main_menu())
        
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
        
        if audio.tags is None:
            audio.add_tags()
        
        if waiting_for == WAITING_FOR_TITLE:
            audio['TIT2'] = TIT2(encoding=3, text=user_text)
            action_text = "название"
            
        elif waiting_for == WAITING_FOR_ARTIST:
            audio['TPE1'] = TPE1(encoding=3, text=user_text)
            action_text = "имя исполнителя"
        
        audio.save()
        del context.user_data['waiting_for']
        
        await update.message.reply_text(f"✅ {action_text.capitalize()} успешно изменено!", reply_markup=get_main_menu())
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при изменении тега: {e}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает отправку фотографии ИЗ ГАЛЕРЕИ ТЕЛЕФОНА"""
    if 'waiting_for' not in context.user_data or context.user_data['waiting_for'] != WAITING_FOR_PHOTO:
        logger.warning("❌ Получено фото, но бот не ожидает обложку")
        return
    
    # ⚠️ ПРОВЕРКА: Есть ли MP3 файл
    if 'current_file_path' not in context.user_data:
        await update.message.reply_text("❌ Сначала отправьте MP3 файл")
        return
        
    file_path = context.user_data['current_file_path']
    
    # ⚠️ ПРОВЕРКА: Существует ли файл
    if not os.path.exists(file_path):
        await update.message.reply_text("❌ Файл MP3 не найден. Отправьте файл заново.")
        if 'current_file_path' in context.user_data:
            del context.user_data['current_file_path']
        return
    
    photo_path = f"temp_cover_{update.update_id}.jpg"
    
    try:
        # Сообщаем о начале обработки
        await update.message.reply_text("⏳ Обрабатываю обложку...")
        
        # Берем фото с НАИЛУЧШИМ качеством (последнее в массиве - самое большое)
        photo_file = await update.message.photo[-1].get_file()
        await photo_file.download_to_drive(photo_path)
        
        # Читаем данные обложки
        with open(photo_path, 'rb') as f:
            cover_data = f.read()
        
        file_size_kb = len(cover_data) / 1024
        logger.info(f"📸 Обложка из галереи: {file_size_kb:.1f} КБ")
        
        # Обрабатываем MP3 файл
        audio = MP3(file_path, ID3=ID3)
        
        if audio.tags is None:
            audio.add_tags()
        
        # Удаляем старые обложки
        for key in list(audio.tags.keys()):
            if key.startswith('APIC'):
                del audio.tags[key]
        
        # Добавляем новую обложку
        audio.tags.add(
            APIC(
                encoding=3,
                mime='image/jpeg',
                type=3,  # Обложка альбома
                desc='Cover',
                data=cover_data
            )
        )
        
        # Сохраняем
        audio.save()
        
        # Проверяем что обложка сохранилась
        audio_check = MP3(file_path, ID3=ID3)
        has_cover = any(key.startswith('APIC') for key in audio_check.tags.keys()) if audio_check.tags else False
        
        del context.user_data['waiting_for']
        
        if has_cover:
            await update.message.reply_text(
                f"✅ Обложка успешно установлена!\n"
                f"📏 Размер: {file_size_kb:.1f} КБ\n"
                f"💾 Сохранено в MP3",
                reply_markup=get_main_menu()
            )
        else:
            await update.message.reply_text("❌ Обложка не сохранилась в файле", reply_markup=get_main_menu())
        
    except Exception as e:
        logger.error(f"❌ Ошибка при установке обложки: {e}")
        await update.message.reply_text(
            f"❌ Ошибка при установке обложки:\n{str(e)}",
            reply_markup=get_main_menu()
        )
        
    finally:
        if os.path.exists(photo_path):
            os.remove(photo_path)

async def send_edited_file(query, context):
    """Отправляет отредактированный файл пользователю"""
    file_path = context.user_data['current_file_path']
    
    try:
        audio = MP3(file_path, ID3=ID3)
        title = str(audio['TIT2']) if 'TIT2' in audio else "Не указано"
        artist = str(audio['TPE1']) if 'TPE1' in audio else "Не указано"
        
        has_cover = any(key.startswith('APIC') for key in audio.tags.keys()) if audio.tags else False
        
        caption = (
            f"✅ Ваш отредактированный файл!\n\n"
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
        
        # Очистка
        if os.path.exists(file_path):
            os.remove(file_path)
        if 'current_file_path' in context.user_data:
            del context.user_data['current_file_path']
            
        await query.message.reply_text("🎉 Файл отправлен!", reply_markup=get_main_menu())
            
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка при отправке файла: {e}")

def main():
    """Запускает бота"""
    try:
        # 🆕 Запускаем keep-alive для предотвращения сна
        keep_alive()
        
        application = Application.builder().token(BOT_TOKEN).build()
        
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CallbackQueryHandler(button_handler))
        application.add_handler(MessageHandler(filters.AUDIO, handle_audio))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        
        # Добавляем обработчик ошибок
        async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            logger.error(f"Ошибка в боте: {context.error}")
        
        application.add_error_handler(error_handler)
        
        logger.info("🚀 Бот запущен! Готов принимать обложки из галереи телефона!")
        
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")

if __name__ == '__main__':
    main()
