import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiohttp import web

# === ТВОИ ДАННЫЕ ===
TOKEN = "8639644231:AAF2-UwFK-lxtaqqwHOi6zPf8pcQ8xe5vGY"
ADMIN_CHAT_ID = 6084347801
WEBAPP_URL = "https://koropay-en5x.onrender.com"
# ===================

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


# Обработка данных из Веб-Аппа
@dp.message(F.web_app_data)
async def handle_webapp_data(message: types.Message):
  data = message.web_app_data.data
  user = message.from_user
  user_info = (
      f"@{user.username}" if user.username else f"ID: {user.id} ({user.full_name})"
  )

  if ADMIN_CHAT_ID:
    try:
      await bot.send_message(
          ADMIN_CHAT_ID,
          f"🚨 <b>Новая заявка из Web App!</b>\n\n"
          f"👤 Клиент: {user_info}\n"
          f"📦 Данные заявки:\n<code>{data}</code>\n\n"
          f"👉 Проверьте данные и подготовьте расчет суммы в рублях.",
          parse_mode="HTML",
      )
    except Exception as e:
      logging.error(f"Ошибка отправки админу: {e}")

  await message.answer(
      "✅ <b>Заявка успешно принята в обработку!</b>\n\n"
      "Мы получили параметры вашего платежа. Менеджер свяжется с вами в ближайшее время для согласования расчета.\n\n"
      "Благодарим за обращение в Koro Pay.",
      parse_mode="HTML",
  )


# Веб-сервер с премиальным дизайном под стиль аватара
async def webapp_handler(request):
  html_content = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Koro Pay — Международные платежи</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            :root {
                --bg-color: #0b0c10;
                --card-bg: #151720;
                --accent: #8b5cf6;
                --accent-hover: #7c3aed;
                --text-main: #ffffff;
                --text-muted: #9ca3af;
                --border: #232634;
                --input-bg: #0e1017;
            }
            body {
                background-color: var(--bg-color);
                color: var(--text-main);
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                margin: 0;
                padding: 16px;
                display: flex;
                flex-direction: column;
                align-items: center;
                min-height: 100vh;
                box-sizing: border-box;
            }
            .container {
                width: 100%;
                max-width: 400px;
                background: var(--card-bg);
                padding: 24px;
                border-radius: 20px;
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.6);
                border: 1px solid var(--border);
                box-sizing: border-box;
                margin-top: auto;
                margin-bottom: auto;
            }
            .logo-container {
                text-align: center;
                margin-bottom: 20px;
            }
            .logo-badge {
                display: inline-block;
                width: 50px;
                height: 50px;
                background: linear-gradient(135deg, #a855f7, #6366f1);
                border-radius: 14px;
                line-height: 50px;
                font-size: 24px;
                font-weight: bold;
                color: white;
                box-shadow: 0 4px 15px rgba(139, 92, 246, 0.4);
                margin-bottom: 10px;
            }
            h2 {
                margin: 0 0 6px 0;
                font-size: 20px;
                text-align: center;
                letter-spacing: 0.5px;
            }
            p.subtitle {
                font-size: 13px;
                color: var(--text-muted);
                text-align: center;
                margin: 0 0 20px 0;
            }
            .form-group {
                margin-bottom: 16px;
            }
            label {
                font-size: 12px;
                font-weight: 600;
                color: var(--text-muted);
                display: block;
                margin-bottom: 6px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            input, textarea, select {
                width: 100%;
                padding: 12px 14px;
                background: var(--input-bg);
                border: 1px solid var(--border);
                border-radius: 10px;
                color: var(--text-main);
                font-size: 15px;
                box-sizing: border-box;
                transition: border-color 0.2s;
            }
            input:focus, textarea:focus, select:focus {
                border-color: var(--accent);
                outline: none;
            }
            button {
                width: 100%;
                padding: 14px;
                background: linear-gradient(135deg, #9333ea, #6366f1);
                color: white;
                border: none;
                border-radius: 12px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                box-shadow: 0 4px 15px rgba(147, 51, 234, 0.4);
                transition: opacity 0.2s, transform 0.1s;
                margin-top: 10px;
            }
            button:active {
                transform: scale(0.98);
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo-container">
                <div class="logo-badge">K</div>
                <h2>Koro Pay</h2>
                <p class="subtitle">Безопасная оплата зарубежных сервисов</p>
            </div>
            
            <div class="form-group">
                <label for="service">Сервис или назначение платежа</label>
                <input type="text" id="service" placeholder="Например: ChatGPT Plus, Hosting, инвойс">
            </div>

            <div class="form-group">
                <label for="amount">Сумма и валюта</label>
                <input type="text" id="amount" placeholder="Например: 20 USD или 50 EUR">
            </div>

            <div class="form-group">
                <label for="details">Комментарий / Ссылка на оплату</label>
                <textarea id="details" rows="2" placeholder="Вставьте ссылку на инвойс или детали заказа"></textarea>
            </div>

            <button id="submitBtn">Отправить заявку</button>
        </div>

        <script>
            let tg = window.Telegram.WebApp;
            tg.expand();

            document.getElementById('submitBtn').addEventListener('click', function() {
                let service = document.getElementById('service').value.trim();
                let amount = document.getElementById('amount').value.trim();
                let details = document.getElementById('details').value.trim();

                if (!service) {
                    alert('Пожалуйста, укажите сервис!');
                    return;
                }
                if (!amount) {
                    alert('Пожалуйста, укажите сумму!');
                    return;
                }

                let payload = `Сервис: ${service} | Сумма: ${amount} | Детали: ${details || 'нет'}`;
                
                // Отправляем данные боту и закрываем веб-апп
                tg.sendData(payload);
                tg.close();
            });
        </script>
    </body>
    </html>
    """
  return web.Response(text=html_content, content_type="text/html")


async def main():
  app = web.Application()
  app.router.add_get("/", webapp_handler)

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