import logging
import asyncio
from maxapi import Bot
from config import BOT_TOKEN, WORK_CHAT_ID
from google_sheets import GoogleSheetsManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OffboardingService:
    """Сервис автоматического исключения уволенных сотрудников"""
    
    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)
        self.sheets = GoogleSheetsManager()
        self.running = True
        self.check_interval = 30  # секунд
        logger.info("✅ Сервис оффбординга инициализирован")

    async def process_offboarding(self):
        """Обработка уволенных сотрудников"""
        try:
            inactive_employees = self.sheets.get_inactive_employees_with_user_id()
            
            if not inactive_employees:
                return
            
            logger.info(f"📋 Найдено {len(inactive_employees)} уволенных сотрудников")
            
            for employee in inactive_employees:
                user_id = int(employee["user_id"])
                name = employee["name"]
                row_index = employee["row_index"]
                
                try:
                    # Исключение из группы
                    await self.bot.remove_chat_member(
                        chat_id=WORK_CHAT_ID,
                        user_id=user_id
                    )
                    
                    logger.info(f"✅ {name} (ID: {user_id}) исключен из чата")
                    
                    # Очистка user_id в таблице
                    self.sheets.clear_user_id(row_index)
                    
                    # Уведомление в чат
                    await self.bot.send_message(
                        chat_id=WORK_CHAT_ID,
                        text=(
                            f"👋 **Сотрудник покинул компанию**\n\n"
                            f"👤 {name}\n\n"
                            f"Доступ к чату отозван автоматически."
                        ),
                        parse_mode="Markdown"
                    )
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка исключения {name}: {e}")
                    
                    # Если пользователь уже не в группе - очищаем user_id
                    error_msg = str(e).lower()
                    if "not a member" in error_msg or "user not found" in error_msg:
                        logger.info(f"ℹ️ {name} уже не в группе, очищаем user_id")
                        self.sheets.clear_user_id(row_index)
                    
        except Exception as e:
            logger.error(f"❌ Ошибка в process_offboarding: {e}")

    async def run(self):
        """Основной цикл проверки"""
        logger.info(f"🔄 Запуск цикла оффбординга (интервал: {self.check_interval}с)")
        
        while self.running:
            try:
                await self.process_offboarding()
            except Exception as e:
                logger.error(f"❌ Критическая ошибка в цикле: {e}")
            
            await asyncio.sleep(self.check_interval)

    def stop(self):
        """Остановка сервиса"""
        self.running = False
        logger.info("🛑 Сервис оффбординга остановлен")


async def main():
    """Запуск сервиса"""
    service = OffboardingService()
    
    try:
        await service.run()
    except KeyboardInterrupt:
        logger.info("⏹ Получен сигнал остановки")
        service.stop()
    except Exception as e:
        logger.error(f"❌ Фатальная ошибка: {e}")


if __name__ == "__main__":
    asyncio.run(main())
