import logging
import time
import threading
import re
import json
import os
from datetime import datetime

import gspread
import requests
from flask import Flask, request, jsonify
from oauth2client.service_account import ServiceAccountCredentials

import config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
user_cache = {}
stop_monitoring = False

def get_google_client():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            'credentials.json', scope
        )
        client = gspread.authorize(creds)
        logger.info("✅ Google Sheets подключена")
        return client
    except Exception as e:
        logger.error(f"❌ Ошибка Google: {e}")
        raise

def get_sheet():
    client = get_google_client()
    return client.open_by_key(config.SPREADSHEET_ID).worksheet(config.WORKSHEET_NAME)

def get_all_employees():
    sheet = get_sheet()
    return sheet.get_all_records()

def find_employee_by_phone(phone):
    records = get_all_employees()
    clean_phone = re.sub(r'\D', '', str(phone))
    
    for record in records:
        record_phone = re.sub(r'\D', '', str(record.get('Номер телефона', '')))
        if record_phone == clean_phone:
            return record
    return None

def update_user_id_in_sheet(phone, user_id):
    try:
        sheet = get_sheet()
        clean_phone = re.sub(r'\D', '', str(phone))
        
        cell = sheet.find(clean_phone, in_column=2)
        if not cell:
            logger.warning(f"⚠️ Номер {phone} не найден")
            return False
        
        headers = sheet.row_values(1)
        try:
            col = headers.index('user_id') + 1
            sheet.update_cell(cell.row, col, str(user_id))
            logger.info(f"✅ user_id обновлен: {phone} -> {user_id}")
            user_cache[clean_phone] = str(user_id)
            return True
        except ValueError:
            logger.error("❌ В таблице нет колонки 'user_id'")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка обновления: {e}")
        return False

def get_employee_status(phone):
    employee = find_employee_by_phone(phone)
    if employee:
        return (
            employee.get('Статус', '').strip(),
            employee.get('user_id', ''),
            employee.get('ФИО', '')
        )
    return None, None, None

def send_message(user_id, text):
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
        logger.info(f"📤 Сообщение отправлено {user_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка отправки: {e}")
        return False

def add_user_to_chat(user_id, name=""):
    url = f"https://platform-api2.max.ru/chats/{config.CHAT_ID}/members"
    headers = {
        "Authorization": config.MAX_BOT_TOKEN,
        "Content-Type": "application/json"
    }
    payload = {"user_id": str(user_id)}
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        logger.info(f"✅ {name} добавлен в чат")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка добавления: {e}")
        return False

def remove_user_from_chat(user_id, name=""):
    url = f"https://platform-api2.max.ru/chats/{config.CHAT_ID}/members"
    headers = {
        "Authorization": config.MAX_BOT_TOKEN,
        "Content-Type": "application/json"
    }
    params = {"user_id": str(user_id)}
    
    try:
        response = requests.delete(url, headers=headers, params=params)
        if response.status_code == 200:
            logger.info(f"✅ {name} исключен из чата")
            return True
        elif response.status_code == 404:
            logger.warning(f"⚠️ {user_id} уже не в чате")
            return True
        else:
            logger.error(f"❌ Ошибка: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return False

def process_start(user_id, phone):
    logger.info(f"🔄 Регистрация {user_id}, телефон: {phone}")
    
    status, existing_user_id, name = get_employee_status(phone)
    
    if not status:
        send_message(user_id, "❌ Номер не найден в системе")
        return
    
    if status.lower() == "уволен":
        send_message(user_id, "🚫 Доступ запрещен")
        return
    
    if status.lower() == "работает":
        if update_user_id_in_sheet(phone, user_id):
            if add_user_to_chat(user_id, name):
                send_message(user_id, f"✅ Добро пожаловать, {name}!")
            else:
                send_message(user_id, "⚠️ Доступ открыт, но ошибка добавления в чат")
        else:
            send_message(user_id, "❌ Ошибка регистрации")
    else:
        send_message(user_id, f"❌ Неизвестный статус: {status}")

def check_terminated():
    logger.info("🔍 Проверка уволенных...")
    
    try:
        records = get_all_employees()
        
        for record in records:
            phone = re.sub(r'\D', '', str(record.get('Номер телефона', '')))
            status = record.get('Статус', '').strip()
            user_id = record.get('user_id', '')
            name = record.get('ФИО', '')
            
            if status.lower() == "уволен" and user_id:
                if phone in user_cache and user_cache[phone] == str(user_id):
                    if remove_user_from_chat(user_id, name):
                        del user_cache[phone]
                else:
                    user_cache[phone] = str(user_id)
                    if remove_user_from_chat(user_id, name):
                        del user_cache[phone]
                        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки: {e}")

def monitoring_loop():
    logger.info("🔄 Мониторинг запущен")
    while not stop_monitoring:
        try:
            check_terminated()
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
        time.sleep(config.CHECK_INTERVAL)
    logger.info("🛑 Мониторинг остановлен")

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.json
        logger.info(f"📨 Вебхук получен")
        
        if 'message' in data:
            msg = data['message']
            text = msg.get('text', '')
            user_id = msg.get('user_id')
            
            if text and text.startswith('/start'):
                parts = text.split()
                if len(parts) > 1:
                    phone = parts[1]
                    threading.Thread(
                        target=process_start,
                        args=(user_id, phone)
                    ).start()
                else:
                    send_message(user_id, "📱 Укажите номер: /start 79001234567")
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "ok",
        "time": datetime.now().isoformat(),
        "cache": len(user_cache)
    }), 200

def load_cache():
    try:
        records = get_all_employees()
        count = 0
        for record in records:
            phone = re.sub(r'\D', '', str(record.get('Номер телефона', '')))
            user_id = record.get('user_id', '')
            if phone and user_id:
                user_cache[phone] = str(user_id)
                count += 1
        logger.info(f"✅ Загружено {count} записей")
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки кеша: {e}")

if __name__ == "__main__":
    load_cache()
    
    monitor_thread = threading.Thread(target=monitoring_loop, daemon=True)
    monitor_thread.start()
    
    port = int(os.environ.get("PORT", 3000))
    logger.info(f"🚀 Бот запущен на порту {port}")
    app.run(host='0.0.0.0', port=port)
