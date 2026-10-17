import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiohttp import web

# === ТВОИ ДАННЫЕ ВСТРОЕНЫ ===
TOKEN = "8639644231:AAF2-UwFK-lxtaqqwHOi6zPf8pcQ8xe5vGY"
ADMIN_CHAT_ID = 6084347801
WEBAPP_URL = "https://koro-pay-bot.onrender.com/webapp"  # После деплоя на Render заменишь на свою ссылку (или можешь пока протестировать через ngrok)
# ============================

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()


# Старт бота: выдает кнопку для открытия Веб-Аппа
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
  web_app_kb = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🚀 Открыть Koro Pay",
                  web_app=WebAppInfo(url=WEBAPP_URL),
              )
          ]
      ]
  )
  welcome_text = (
      "<b>👋 Добро пожаловать в Koro Pay!</b>\n\n"
      "Профессиональный сервис международных платежей и переводов.\n"
      "Нажмите кнопку ниже, чтобы запустить приложение и оформить заявку.\n\n"
      "<i>Платежи. Переводы. Больше.</i>"
  )
  await message.answer(
      welcome_text, reply_markup=web_app_kb, parse_mode="HTML"
  )


# Обработка данных, прилетающих из Веб-Аппа
@dp.message(F.web_app_data)
async def handle_webapp_data(message: types.Message):
  data = message.web_app_data.data
  user = message.from_user
  user_info = (
      f"@{user.username}" if user.username else f"ID: {user.id} ({user.full_name})"
  )

  # Отправляем заявку тебе (админу)
  if ADMIN_CHAT_ID:
    try:
      await bot.send_message(
          ADMIN_CHAT_ID,
          f"🚨 <b>Новая заявка из Web App!</b>\n\n"
          f"👤 Клиент: {user_info}\n"
          f"📦 Данные формы: <code>{data}</code>\n\n"
          f"👉 Проверьте данные и подготовьте расчет суммы в рублях.",
          parse_mode="HTML",
      )
    except Exception as e:
      logging.error(f"Ошибка отправки админу: {e}")

  # Ответ клиенту в чат бота
  await message.answer(
      "✅ <b>Заявка успешно отправлена!</b>\n\n"
      "Мы получили параметры вашего платежа. Менеджер свяжется с вами для согласования расчета.\n\n"
      "Благодарим за обращение в Koro Pay.",
      parse_mode="HTML",
  )


# Веб-сервер для отдачи интерфейса Веб-Аппа
async def webapp_handler(request):
  html_content = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Koro Pay Web App</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            body {
                background-color: #0f1016; color: #ffffff;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                margin: 0; padding: 20px; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh;
            }
            .container {
                width: 100%; max-width: 400px; background: #1a1c24; padding: 24px; border-radius: 16px; box-shadow: 0 8px 24px rgba(0,0,0,0.5); box-sizing: border-box;
            }
            h2 { margin-top: 0; font-size: 22px; text-align: center; color: #a855f7; }
            p { font-size: 14px; color: #9ca3af; text-align: center; margin-bottom: 20px; }
            label { font-size: 13px; color: #d1d5db; display: block; margin-bottom: 6px; }
            input, textarea {
                width: 100%; padding: 12px; background: #111319; border: 1px solid #374151; border-radius: 8px; color: #fff; font-size: 15px; margin-bottom: 16px; box-sizing: border-box;
            }
            input:focus, textarea:focus { border-color: #a855f7; outline: none; }
            button {
                width: 100%; padding: 14px; background: linear-gradient(135deg, #9333ea, #7e22ce); color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: bold; cursor: pointer;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Koro Pay</h2>
            <p>Укажите данные для проведения платежа</p>
            <label for="service">Сервис или назначение платежа:</label>
            <input type="text" id="service" placeholder="Например: ChatGPT Plus, 20$">
            <label for="amount">Сумма в валюте / детали:</label>
            <textarea id="amount" rows="3" placeholder="Укажите точную сумму или прикрепите ссылку на инвойс"></textarea>
            <button id="submitBtn">Отправить заявку</button>
        </div>
        <script>
            let tg = window.Telegram.WebApp;
            tg.expand();
            document.getElementById('submitBtn').addEventListener('click', function() {
                let service = document.getElementById('service').value;
                let details = document.getElementById('amount').value;
                if (!service) { alert('Пожалуйста, укажите сервис!'); return; }
                tg.sendData(`Сервис: ${service} | Детали: ${details}`);
            });
        </script>
    </body>
    </html>
    """
  return web.Response(text=html_content, content_type="text/html")


async def main():
  app = web.Application()
  app.router.add_get("/webapp", webapp_handler)

  runner = web.AppRunner(app)
  await runner.setup()
  port = int(os.environ.get("PORT", 8080))
  site = web.TCPSite(runner, "0.0.0.0", port)
  await site.start()
  logging.info(f"Веб-сервер интерфейса запущен на порту {port}...")

  logging.info("Бот Koro Pay запущен...")
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())