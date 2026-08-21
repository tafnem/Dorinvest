# config.py
import os

# === НАСТРОЙКИ MAX ===
# Токен бота из MAX (раздел Интеграция)
MAX_BOT_TOKEN = "f9LHodD0cOLoNWzZmiwaarGx87HmGGSW1TThS-gfJpzPxJ2ieDBvguGwdXsTncoplRBPHgbQONoOD0VFtOvC"

# ID чата (группы), откуда будем исключать
# Для групповых чатов ID обычно отрицательный
CHAT_ID = -78013816902930

# === НАСТРОЙКИ GOOGLE TABLES ===
# ID таблицы (из URL: https://docs.google.com/spreadsheets/d/ЭТОТ_ID)
SPREADSHEET_ID = "1ldc6Nat5YlrH8KuLPFLTpEbdk-bGBn-hzy_pm6wO8x8/edit?gid=0#gid=0"

# Имя листа в таблице
WORKSHEET_NAME = "Сотрудники"

# === НАСТРОЙКИ СКРИПТА ===
# Интервал проверки таблицы (в секундах)
CHECK_INTERVAL = 60

# === НАСТРОЙКИ WEBHOOK ===
# URL, куда MAX будет отправлять обновления
# Для локальной разработки используй ngrok или аналоги
WEBHOOK_URL = "https://ваш-сервер.ngrok.io/webhook"

# Порт для Flask-сервера
PORT = 5000