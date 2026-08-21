import logging
import time
import threading
import re
import json
import os
from datetime import datetime

import gspread
import requests
from oauth2client.service_account import ServiceAccountCredentials

import config

# --- ОТКЛЮЧАЕМ SSL ПРОВЕРКУ ---
import ssl
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except:
    pass

requests.packages.urllib3.disable_warnings()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

user_cache = {}
stop_monitoring = False
last_marker = None

def make_request(method, url, **kwargs):
    kwargs['verify'] = False
    try:
        response = requests.request(method, url, **kwargs)
        return response
    except Exception as e:
        logger.error(f"❌ Ошибка запроса: {e}")
        raise

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
    try:
        sheet = get_sheet()
        logger.info(f"📊 Лист: {sheet.title}")
        logger.info(f"📊 Количество строк: {len(sheet.get_all_values())}")
        
        records = sheet.get_all_records()
        logger.info(f"📊 Получено записей: {len(records)}")
        
        for i, record in enumerate(records[:2]):
            logger.info(f"📊 Запись {i+1}: {record}")
        
        return records
    except Exception as e:
        logger.error(f"❌ Ошибка чтения таблицы: {e}")
        raise

def find_employee_by_phone(phone):
    records = get_all_employees()
    clean_phone = re.sub(r'\D', '', str(phone))
    logger.info(f"🔍 Ищем номер: {clean_phone}")
    
    for record in records:
        record_phone = str(record.get('Номер телефона', ''))
        record_phone = re.sub(r'\D', '', record_phone)
        
        if record_phone == clean_phone:
            logger.info(f"✅ Найден сотрудник: {record}")
            return record
    
    logger.warning(f"⚠️ Номер {clean_phone} не найден в таблице")
    return None

def update_user_id_in_sheet(phone, user_id):
    try:
        sheet = get_sheet()
        clean_phone = re.sub(r'\D', '', str(phone))
        logger.info(f"🔍 Обновляем user_id для номера: {clean_phone}")
        
        # Ищем номер во всех ячейках
        cell = sheet.find(clean_phone)
        if not cell:
            logger.warning(f"⚠️ Номер {clean_phone} не найден в таблице")
            return False
        
        logger.info(f"✅ Номер найден в строке {cell.row}, колонке {cell.col}")
        
        # Находим колонку user_id по заголовку
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
    logger.info(f"📤 Отправка сообщения пользователю {user_id}: {text}")
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
        response = make_request('POST', url, headers=headers, json=payload)
        response.raise_for_status()
        logger.info(f"✅ Сообщение отправлено {user_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка отправки: {e}")
        if hasattr(e, 'response') and e.response:
            logger.error(f"Ответ сервера: {e.response.text}")
        return False

def add_user_to_chat(user_id, name=""):
    logger.info(f"👤 Добавление пользователя {user_id} в чат {config.CHAT_ID}")
    url = f"https://platform-api2.max.ru/chats/{config.CHAT_ID}/members"
    headers = {
        "Authorization": config.MAX_BOT_TOKEN,
        "Content-Type": "application/json"
    }
    payload = {"user_id": str(user_id)}
    
    try:
        response = make_request('POST', url, headers=headers, json=payload)
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
        response = make_request('DELETE', url, headers=headers, params=params)
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
    logger.info("🔄 Мониторинг уволенных запущен")
    while not stop_monitoring:
        try:
            check_terminated()
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
        time.sleep(config.CHECK_INTERVAL)

def process_updates():
    global last_marker
    logger.info("🔄 Запущен цикл получения сообщений")
    
    while not stop_monitoring:
        try:
            url = "https://platform-api2.max.ru/updates"
            headers = {
                "Authorization": config.MAX_BOT_TOKEN,
                "Content-Type": "application/json"
            }
            params = {
                "timeout": 30,
                "limit": 10,
                "marker": last_marker
            }
            
            response = make_request('GET', url, headers=headers, params=params, timeout=35)
            
            if response.status_code == 200:
                data = response.json()
                updates = data.get('updates', [])
                new_marker = data.get('marker')
                
                if updates:
                    logger.info(f"📨 Получено {len(updates)} обновлений")
                    
                    for update in updates:
                        try:
                            if 'message' not in update:
                                continue
                            
                            msg = update['message']
                            
                            user_id = None
                            if 'recipient' in msg and isinstance(msg['recipient'], dict):
                                user_id = msg['recipient'].get('user_id')
                            elif 'user_id' in msg:
                                user_id = msg['user_id']
                            
                            text = None
                            if 'body' in msg:
                                body = msg['body']
                                if isinstance(body, dict):
                                    text = body.get('text') or body.get('body') or body.get('message', '')
                                elif isinstance(body, str):
                                    text = body
                            
                            if isinstance(text, dict):
                                text = text.get('text', '') or text.get('body', '') or ''
                            
                            if text and user_id:
                                logger.info(f"💬 Сообщение от {user_id}: {str(text)[:50]}")
                                
                                if isinstance(text, str) and text.startswith('/start'):
                                    parts = text.split()
                                    if len(parts) > 1:
                                        phone = parts[1]
                                        logger.info(f"🔍 Найдена команда /start от {user_id} с номером {phone}")
                                        threading.Thread(
                                            target=process_start,
                                            args=(user_id, phone)
                                        ).start()
                                    else:
                                        send_message(user_id, "📱 Укажите номер: /start 79001234567")
                        except Exception as e:
                            logger.error(f"❌ Ошибка обработки обновления: {e}")
                            continue
                
                if new_marker is not None:
                    last_marker = new_marker
            else:
                logger.warning(f"⚠️ Ошибка получения обновлений: {response.status_code}")
                time.sleep(5)
                
        except Exception as e:
            logger.error(f"❌ Ошибка в цикле получения сообщений: {e}")
            time.sleep(5)

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
    
    try:
        process_updates()
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен")
        stop_monitoring = True
        monitor_thread.join(timeout=2)
