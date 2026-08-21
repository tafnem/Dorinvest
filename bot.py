import logging
import asyncio
from maxapi import Bot, Dispatcher, F
from maxapi.types import BotStarted, MessageCreated
from config import BOT_TOKEN, WORK_CHAT_ID
from google_sheets import GoogleSheetsManager

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Инициализация Google Sheets
try:
    sheets = GoogleSheetsManager()
except Exception as e:
    logger.error(f"❌ Не удалось инициализировать Google Sheets: {e}")
    sheets = None


@dp.bot_started()
async def bot_started(event: BotStarted):
    """Обработчик команды /start"""
    chat_id = event.chat_id
    logger.info(f"👤 Новый пользователь: {chat_id}")
    
    if not sheets:
        await bot.send_message(
            chat_id=chat_id,
            text="⚠️ Сервис временно недоступен. Пожалуйста, попробуйте позже."
        )
        return
    
    await bot.send_message(
        chat_id=chat_id,
        text=(
            "👋 **Добро пожаловать в HR-бот!**\n\n"
            "Для верификации, пожалуйста, подтвердите свой номер телефона."
        ),
        parse_mode="Markdown",
        attachments=[{
            "type": "inline_keyboard",
            "buttons": [{
                "type": "request_contact",
                "text": "📱 Подтвердить номер",
                "payload": {"action": "verify_phone"}
            }]
        }]
    )


@dp.message_created(F.message.attachments[0].type == "contact")
async def handle_contact(event: MessageCreated):
    """Обработчик полученного контакта"""
    chat_id = event.chat_id
    logger.info(f"📱 Получен контакт от {chat_id}")
    
    if not sheets:
        await bot.send_message(
            chat_id=chat_id,
            text="⚠️ Сервис временно недоступен."
        )
        return
    
    try:
        # Получаем номер телефона из контакта
        contact = event.message.attachments[0].payload
        user_phone = contact.get('max_info', {}).get('phone_number')
        
        if not user_phone:
            await bot.send_message(
                chat_id=chat_id,
                text="❌ Не удалось получить номер телефона. Попробуйте еще раз."
            )
            return
        
        logger.info(f"🔍 Проверка номера: {user_phone}")
        
        # Поиск сотрудника в таблице
        employee = sheets.find_employee_by_phone(user_phone)
        
        if not employee:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "❌ **Доступ запрещен**\n\n"
                    "Ваш номер не найден в базе данных сотрудников.\n"
                    "Обратитесь в отдел кадров."
                ),
                parse_mode="Markdown"
            )
            return
        
        # Проверка статуса
        if employee["status"] != "Работает":
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "❌ **Доступ запрещен**\n\n"
                    "Ваш аккаунт помечен как уволенный.\n"
                    "Обратитесь в отдел кадров."
                ),
                parse_mode="Markdown"
            )
            return
        
        # Проверка, не зарегистрирован ли уже
        if employee["user_id"]:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"✅ **Вы уже зарегистрированы!**\n\n"
                    f"Добро пожаловать обратно, {employee['name']}! 🎉"
                ),
                parse_mode="Markdown"
            )
            return
        
        # Регистрация пользователя
        success = sheets.update_user_id(employee["row_index"], str(chat_id))
        
        if success:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"✅ **Верификация пройдена!**\n\n"
                    f"Добро пожаловать в команду, {employee['name']}! 🎉\n\n"
                    "Вам открыт доступ к рабочему чату."
                ),
                parse_mode="Markdown"
            )
            
            # Уведомление в рабочий чат
            try:
                await bot.send_message(
                    chat_id=WORK_CHAT_ID,
                    text=(
                        f"🔔 **Новый сотрудник присоединился!**\n\n"
                        f"👤 {employee['name']}\n"
                        f"📱 {employee['phone']}\n\n"
                        f"Добро пожаловать в команду! 🎉"
                    ),
                    parse_mode="Markdown"
                )
                logger.info(f"✅ Уведомление отправлено в группу")
            except Exception as e:
                logger.error(f"❌ Ошибка отправки уведомления: {e}")
        else:
            await bot.send_message(
                chat_id=chat_id,
                text="❌ Ошибка регистрации. Попробуйте позже."
            )
            
    except Exception as e:
        logger.error(f"❌ Ошибка в handle_contact: {e}")
        await bot.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка. Попробуйте позже."
        )


@dp.message_created(F.message.text)
async def handle_other_messages(event: MessageCreated):
    """Обработчик остальных сообщений"""
    chat_id = event.chat_id
    
    if event.message.text and not event.message.attachments:
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "ℹ️ Для верификации используйте кнопку "
                "**'Подтвердить номер'** ниже."
            ),
            parse_mode="Markdown"
        )


async def main():
    """Запуск бота"""
    logger.info("🚀 Бот запускается...")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")


if __name__ == "__main__":
    asyncio.run(main())
