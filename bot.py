# bot.py
import logging
import time
import threading
import re
import json
from datetime import datetime

import gspread
import requests
from flask import Flask, request, jsonify
from oauth2client.service_account import ServiceAccountCredentials
from gspread.exceptions import WorksheetNotFound, CellNotFound

import config

# --- НАСТРОЙКА ЛОГИРОВАНИЯ ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ---
# Кеш соответствия номеров и user_id
user_cache = {}
# Флаг остановки мониторинга
stop_monitoring = False
# Flask приложение
app = Flask(__name__)

# --- 1. РАБОТА С GOOGLE TABLES ---

def get_google_client():
    """Получение клиента для работы с Google Sheets."""
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            'credentials.json', scope
        )
        client = gspread.authorize(creds)
        logger.info("✅ Авторизация в Google Sheets успешна")
        return client
    except Exception as e:
        logger.error(f"❌ Ошибка авторизации Google Sheets: {e}")
        raise

def get_sheet():
    """Получение рабочего листа таблицы."""
    client = get_google_client()
    try:
        sheet = client.open_by_key(config.SPREADSHEET_ID).worksheet(config.WORKSHEET_NAME)
        return sheet
    except Exception as e:
        logger.error(f"❌ Ошибка открытия таблицы: {e}")
        raise

def get_employee_data():
    """Загрузка всех данных сотрудников."""
    sheet = get_sheet()
    records = sheet.get_all_records()
    logger.info(f"📊 Загружено {len(records)} записей из таблицы")
    return records

def find_employee_by_phone(phone_number):
    """Поиск сотрудника по номеру телефона."""
    records = get_employee_data()
    # Очищаем номер от лишних символов
    clean_phone = re.sub(r'\D', '', str(phone_number))
    
    for record in records:
        record_phone = re.sub(r'\D', '', str(record.get('Номер телефона', '')))
        if record_phone == clean_phone:
            return record
    return None

def update_user_id(phone_number, user_id):
    """Обновление user_id в таблице."""
    try:
        sheet = get_sheet()
        # Ищем номер телефона в колонке B (2)
        cell = sheet.find(re.sub(r'\D', '', str(phone_number)), in_column=2)
        
        if cell:
            # Находим колонку user_id по заголовку
            headers = sheet.row_values(1)
            try:
                user_id_col = headers.index('user_id') + 1
                sheet.update_cell(cell.row, user_id_col, str(user_id))
                logger.info(f"✅ Обновлен user_id для {phone_number} -> {user_id}")
                
                # Обновляем кеш
                clean_phone = re.sub(r'\D', '', str(phone_number))
                user_cache[clean_phone] = str(user_id)
                return True
            except ValueError:
                logger.error("❌ В таблице нет колонки 'user_id'")
                return False
        else:
            logger.warning(f"⚠️ Номер {phone_number} не найден в таблице")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка обновления user_id: {e}")
        return False

def check_employee_status(phone_number):
    """Проверка статуса сотрудника."""
    employee = find_employee_by_phone(phone_number)
    if employee:
        status = employee.get('Статус', '').strip()
        user_id = employee.get('user_id', '')
        name = employee.get('ФИО', '')
        return status, user_id, name
    return None, None, None

# --- 2. РАБОТА С API MAX ---

def send_message(user_id, text):
    """Отправка сообщения пользователю."""
    url = "https://platform-api2.max.ru/messages"
    headers = {
        "Authorization": config.MAX_BOT_TOKEN,
        "Content-Type": "application/json"
    }
    payload = {
        "user_id": str(user_id),
        "text": text
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        logger.info(f"📤 Сообщение отправлено пользователю {user_id}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Ошибка отправки сообщения: {e}")
        if hasattr(e, 'response') and e.response:
            logger.error(f"Ответ сервера: {e.response.text}")
        return False

def remove_user_from_chat(user_id, name=""):
    """Исключение пользователя из чата."""
    url = f"https://platform-api2.max.ru/chats/{config.CHAT_ID}/members"
    headers = {
        "Authorization": config.MAX_BOT_TOKEN,
        "Content-Type": "application/json"
    }
    params = {
        "user_id": str(user_id)
    }
    
    try:
        response = requests.delete(url, headers=headers, params=params)
        
        if response.status_code == 200:
            logger.info(f"✅ Пользователь {name} (ID: {user_id}) исключен из чата")
            return True
        elif response.status_code == 404:
            logger.warning(f"⚠️ Пользователь {user_id} уже не в чате")
            return True
        else:
            logger.error(f"❌ Ошибка исключения: {response.status_code} - {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Ошибка API: {e}")
        return False

def add_user_to_chat(user_id, name=""):
    """Добавление пользователя в чат."""
    url = f"https://platform-api2.max.ru/chats/{config.CHAT_ID}/members"
    headers = {
        "Authorization": config.MAX_BOT_TOKEN,
        "Content-Type": "application/json"
    }
    payload = {
        "user_id": str(user_id)
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        logger.info(f"✅ Пользователь {name} (ID: {user_id}) добавлен в чат")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Ошибка добавления в чат: {e}")
        return False

# --- 3. ЛОГИКА БОТА ---

def process_start_command(user_id, phone_number):
    """Обработка команды /start."""
    logger.info(f"🔄 Обработка /start от {user_id}, номер: {phone_number}")
    
    # Проверяем статус
    status, existing_user_id, name = check_employee_status(phone_number)
    
    if not status:
        send_message(user_id, "❌ Ваш номер не найден в системе. Доступ запрещен.")
        return
    
    if status.lower() == "уволен":
        send_message(user_id, "🚫 Ваш доступ отключен. Обратитесь к администратору.")
        return
    
    if status.lower() == "работает":
        # Обновляем user_id
        if update_user_id(phone_number, user_id):
            # Добавляем в чат
            if add_user_to_chat(user_id, name):
                send_message(user_id, f"✅ Добро пожаловать, {name}! Доступ к рабочему чату открыт.")
            else:
                send_message(user_id, "⚠️ Доступ предоставлен, но возникла ошибка добавления в чат. Обратитесь к администратору.")
        else:
            send_message(user_id, "❌ Ошибка регистрации. Обратитесь к администратору.")
    else:
        send_message(user_id, f"❌ Неизвестный статус '{status}'. Обратитесь к администратору.")

def check_terminated_employees():
    """Проверка уволенных сотрудников."""
    logger.info("🔍 Проверка уволенных сотрудников...")
    
    try:
        records = get_employee_data()
        terminated_found = False
        
        for record in records:
            phone = re.sub(r'\D', '', str(record.get('Номер телефона', '')))
            status = record.get('Статус', '').strip()
            user_id = record.get('user_id', '')
            name = record.get('ФИО', '')
            
            # Если сотрудник уволен и есть user_id
            if status.lower() == "уволен" and user_id:
                # Проверяем, не исключили ли мы его уже
                if phone in user_cache and user_cache[phone] == str(user_id):
                    # Исключаем из чата
                    if remove_user_from_chat(user_id, name):
                        # Удаляем из кеша
                        del user_cache[phone]
                        terminated_found = True
                else:
                    # Если нет в кеше, добавляем и исключаем
                    user_cache[phone] = str(user_id)
                    if remove_user_from_chat(user_id, name):
                        del user_cache[phone]
                        terminated_found = True
        
        if not terminated_found:
            logger.info("✅ Уволенные сотрудники не обнаружены")
            
    except Exception as e:
        logger.error(f"❌ Ошибка проверки уволенных: {e}")

def monitoring_loop():
    """Фоновый цикл мониторинга."""
    logger.info("🔄 Запущен фоновый мониторинг")
    
    while not stop_monitoring:
        try:
            check_terminated_employees()
        except Exception as e:
            logger.error(f"❌ Ошибка в цикле мониторинга: {e}")
        
        time.sleep(config.CHECK_INTERVAL)
    
    logger.info("🛑 Мониторинг остановлен")

# --- 4. WEBHOOK ОБРАБОТЧИК ---

@app.route('/webhook', methods=['POST'])
def webhook():
    """Обработка вебхука от MAX."""
    try:
        data = request.json
        logger.info(f"📨 Получен вебхук: {json.dumps(data, ensure_ascii=False)}")
        
        # Проверяем, что это сообщение
        if 'message' in data:
            message = data['message']
            text = message.get('text', '')
            user_id = message.get('user_id')
            
            logger.info(f"💬 Сообщение от {user_id}: {text}")
            
            # Обработка команды /start
            if text and text.startswith('/start'):
                # Извлекаем номер телефона
                parts = text.split()
                if len(parts) > 1:
                    phone_number = parts[1]
                    # Запускаем обработку в отдельном потоке, чтобы не блокировать ответ
                    threading.Thread(
                        target=process_start_command,
                        args=(user_id, phone_number)
                    ).start()
                else:
                    send_message(user_id, "📱 Пожалуйста, укажите номер телефона: /start 79001234567")
        
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        logger.error(f"❌ Ошибка обработки вебхука: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Проверка работоспособности."""
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "cache_size": len(user_cache)
    }), 200

# --- 5. ЗАПУСК ---

def load_cache():
    """Загрузка кеша при старте."""
    try:
        records = get_employee_data()
        count = 0
        for record in records:
            phone = re.sub(r'\D', '', str(record.get('Номер телефона', '')))
            user_id = record.get('user_id', '')
            if phone and user_id:
                user_cache[phone] = str(user_id)
                count += 1
        logger.info(f"✅ Загружено {count} записей в кеш")
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки кеша: {e}")

def setup_webhook():
    """Настройка вебхука в MAX."""
    url = "https://platform-api2.max.ru/webhooks"
    headers = {
        "Authorization": config.MAX_BOT_TOKEN,
        "Content-Type": "application/json"
    }
    payload = {
        "url": config.WEBHOOK_URL
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            logger.info(f"✅ Вебхук настроен: {config.WEBHOOK_URL}")
            return True
        else:
            logger.error(f"❌ Ошибка настройки вебхука: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка настройки вебхука: {e}")
        return False

if __name__ == "__main__":
    # Загружаем кеш
    load_cache()
    
    # Настраиваем вебхук
    setup_webhook()
    
    # Запускаем мониторинг в фоновом потоке
    monitor_thread = threading.Thread(target=monitoring_loop, daemon=True)
    monitor_thread.start()
    
    # Запускаем Flask сервер
    logger.info(f"🚀 Бот запущен на порту {config.PORT}")
    app.run(host='0.0.0.0', port=config.PORT)