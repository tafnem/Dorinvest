import os
from dotenv import load_dotenv

load_dotenv()

# Токен бота MAX
BOT_TOKEN = os.getenv("MAX_BOT_TOKEN")

# ID рабочей группы
WORK_CHAT_ID = os.getenv("WORK_CHAT_ID")

# Настройки Google Sheets
GOOGLE_SHEETS_CREDENTIALS = os.getenv("GOOGLE_SHEETS_CREDENTIALS", "credentials.json")
SPREADSHEET_NAME = os.getenv("SPREADSHEET_NAME", "Сотрудники")

# Индексы колонок в таблице (начинаются с 1)
COL_PHONE = 1      # Номер телефона
COL_NAME = 2       # ФИО
COL_STATUS = 3     # Статус (Работает/Уволен)
COL_USER_ID = 4    # user_id (технический)

# Статусы сотрудников
STATUS_ACTIVE = "Работает"
STATUS_INACTIVE = "Уволен"

# Проверка обязательных переменных
if not BOT_TOKEN:
    raise ValueError("❌ MAX_BOT_TOKEN не найден в .env файле!")
if not WORK_CHAT_ID:
    raise ValueError("❌ WORK_CHAT_ID не найден в .env файле!")
