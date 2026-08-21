import gspread
from oauth2client.service_account import ServiceAccountCredentials
from config import (
    GOOGLE_SHEETS_CREDENTIALS, 
    SPREADSHEET_NAME, 
    COL_PHONE, 
    COL_NAME, 
    COL_STATUS, 
    COL_USER_ID,
    STATUS_INACTIVE
)
import logging

logger = logging.getLogger(__name__)

class GoogleSheetsManager:
    """Класс для работы с Google Таблицей сотрудников"""
    
    def __init__(self):
        """Инициализация подключения к Google Таблицам"""
        try:
            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"
            ]
            creds = ServiceAccountCredentials.from_json_keyfile_name(
                GOOGLE_SHEETS_CREDENTIALS, scope
            )
            self.client = gspread.authorize(creds)
            self.sheet = self.client.open(SPREADSHEET_NAME).sheet1
            logger.info("✅ Подключение к Google Таблицам установлено")
        except FileNotFoundError:
            logger.error(f"❌ Файл {GOOGLE_SHEETS_CREDENTIALS} не найден!")
            raise
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Google Таблицам: {e}")
            raise

    def find_employee_by_phone(self, phone_number: str):
        """
        Поиск сотрудника по номеру телефона.
        
        Args:
            phone_number: Номер телефона для поиска
            
        Returns:
            dict: Данные сотрудника или None
        """
        try:
            cell = self.sheet.find(phone_number)
            if cell:
                row = self.sheet.row_values(cell.row)
                return {
                    "row_index": cell.row,
                    "phone": row[COL_PHONE - 1] if len(row) >= COL_PHONE else "",
                    "name": row[COL_NAME - 1] if len(row) >= COL_NAME else "",
                    "status": row[COL_STATUS - 1] if len(row) >= COL_STATUS else "",
                    "user_id": row[COL_USER_ID - 1] if len(row) >= COL_USER_ID else ""
                }
            return None
        except Exception as e:
            logger.error(f"Ошибка поиска сотрудника: {e}")
            return None

    def update_user_id(self, row_index: int, user_id: str) -> bool:
        """
        Обновляет user_id сотрудника в таблице.
        
        Args:
            row_index: Номер строки в таблице
            user_id: ID пользователя в MAX
            
        Returns:
            bool: True в случае успеха
        """
        try:
            self.sheet.update_cell(row_index, COL_USER_ID, user_id)
            logger.info(f"✅ User_id {user_id} записан для строки {row_index}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка обновления user_id: {e}")
            return False

    def clear_user_id(self, row_index: int) -> bool:
        """
        Очищает user_id сотрудника при увольнении.
        
        Args:
            row_index: Номер строки в таблице
            
        Returns:
            bool: True в случае успеха
        """
        try:
            self.sheet.update_cell(row_index, COL_USER_ID, "")
            logger.info(f"✅ User_id очищен для строки {row_index}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка очистки user_id: {e}")
            return False

    def get_all_employees(self) -> list:
        """
        Получает всех сотрудников из таблицы.
        
        Returns:
            list: Список словарей с данными сотрудников
        """
        try:
            records = self.sheet.get_all_records()
            employees = []
            for i, record in enumerate(records, start=2):
                employee = {
                    "row_index": i,
                    "phone": record.get("Номер телефона", ""),
                    "name": record.get("ФИО", ""),
                    "status": record.get("Статус", ""),
                    "user_id": record.get("user_id", "")
                }
                employees.append(employee)
            return employees
        except Exception as e:
            logger.error(f"Ошибка получения списка сотрудников: {e}")
            return []

    def get_inactive_employees_with_user_id(self) -> list:
        """
        Получает список уволенных сотрудников с user_id.
        
        Returns:
            list: Список уволенных сотрудников
        """
        employees = self.get_all_employees()
        return [
            emp for emp in employees 
            if emp["status"] == STATUS_INACTIVE and emp["user_id"]
        ]
