import requests
import time
import threading
import os
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def ping_server():
    """Пингует сервер чтобы предотвратить сон"""
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

def start_keep_alive():
    """Запускает keep-alive в фоновом потоке"""
    try:
        thread = threading.Thread(target=ping_server)
        thread.daemon = True  # Поток завершится при завершении main потока
        thread.start()
        logger.info("🔄 Keep-alive запущен (ping каждые 10 минут)")
        return True
    except Exception as e:
        logger.error(f"❌ Не удалось запустить keep-alive: {e}")
        return False

# Автоматический запуск при импорте
if __name__ == "__main__":
    start_keep_alive()
    # Бесконечный цикл чтобы скрипт не завершался
    while True:
        time.sleep(1)
