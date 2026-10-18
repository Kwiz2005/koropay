import asyncio
import json
import logging
import os
from aiogram import Bot, Dispatcher, types
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


# API-обработчик для приема заявок из Web App (100% надежная доставка)
async def api_order_handler(request):
  try:
    data = await request.json()
    service = data.get("service", "Не указано")
    amount = data.get("amount", "0")
    currency = data.get("currency", "USD")
    details = data.get("details", "Нет")
    user_name = data.get("username", "Аноним")
    user_id = data.get("user_id", "Неизвестно")

    user_info = f"@{user_name}" if user_name != "Аноним" else f"ID: {user_id}"

    # Формируем красивое сообщение для админа
    admin_message = (
        f"🚨 <b>Новая заявка Koro Pay!</b>\n\n"
        f"👤 Клиент: {user_info} (ID: <code>{user_id}</code>)\n"
        f"🎯 Сервис: <b>{service}</b>\n"
        f"💰 Сумма: <b>{amount} {currency}</b>\n"
        f"📝 Детали / Ссылка: <code>{details}</code>\n\n"
        f"👉 Подготовьте расчет в рублях и свяжитесь с клиентом."
    )

    if ADMIN_CHAT_ID:
      await bot.send_message(ADMIN_CHAT_ID, admin_message, parse_mode="HTML")

    return web.json_response({"status": "success"})
  except Exception as e:
    logging.error(f"Ошибка обработки заказа: {e}")
    return web.json_response(
        {"status": "error", "message": str(e)}, status=400
    )


# Веб-сервер с полноценным финтех-интерфейсом и точной копией фирменного стиля
async def webapp_handler(request):
  html_content = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Koro Pay — Финтех платформа</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            :root {
                --bg-gradient: radial-gradient(circle at 50% 0%, #1a1535 0%, #0b0c10 70%);
                --card-bg: rgba(21, 23, 32, 0.85);
                --accent-purple: #8b5cf6;
                --accent-hover: #7c3aed;
                --text-main: #ffffff;
                --text-muted: #9ca3af;
                --border: rgba(139, 92, 246, 0.2);
                --input-bg: #0e1017;
            }
            body {
                background: var(--bg-gradient);
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
                backdrop-filter: blur(12px);
                padding: 24px;
                border-radius: 24px;
                box-shadow: 0 16px 40px rgba(0, 0, 0, 0.7);
                border: 1px solid var(--border);
                box-sizing: border-box;
                margin: auto;
            }
            .brand-header {
                text-align: center;
                margin-bottom: 24px;
            }
            /* Логотип в точности как на вашем бренде */
            .logo-box {
                width: 64px;
                height: 64px;
                margin: 0 auto 12px auto;
                background: linear-gradient(135deg, #a855f7 0%, #6366f1 100%);
                border-radius: 18px;
                display: flex;
                align-items: center;
                justify-content: center;
                box-shadow: 0 8px 25px rgba(139, 92, 246, 0.45);
                position: relative;
            }
            .logo-k {
                font-size: 36px;
                font-weight: 900;
                color: white;
                letter-spacing: -1px;
            }
            h1 {
                margin: 0;
                font-size: 24px;
                font-weight: 800;
                letter-spacing: -0.5px;
            }
            h1 span {
                color: #a855f7;
            }
            .tagline {
                font-size: 12px;
                color: var(--text-muted);
                margin-top: 4px;
                text-transform: uppercase;
                letter-spacing: 1.5px;
                font-weight: 600;
            }
            .form-group {
                margin-bottom: 16px;
            }
            label {
                font-size: 12px;
                font-weight: 700;
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
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
                color: var(--text-main);
                font-size: 15px;
                box-sizing: border-box;
                transition: all 0.2s ease;
            }
            input:focus, textarea:focus, select:focus {
                border-color: var(--accent-purple);
                box-shadow: 0 0 10px rgba(139, 92, 246, 0.25);
                outline: none;
            }
            .row {
                display: flex;
                gap: 10px;
            }
            .row .form-group {
                flex: 1;
            }
            button.submit-btn {
                width: 100%;
                padding: 15px;
                background: linear-gradient(135deg, #9333ea 0%, #6366f1 100%);
                color: white;
                border: none;
                border-radius: 14px;
                font-size: 16px;
                font-weight: 700;
                cursor: pointer;
                box-shadow: 0 6px 20px rgba(147, 51, 234, 0.4);
                transition: transform 0.1s ease, opacity 0.2s;
                margin-top: 8px;
            }
            button.submit-btn:active {
                transform: scale(0.97);
            }
            .success-screen {
                display: none;
                text-align: center;
                padding: 20px 0;
            }
            .success-icon {
                width: 60px;
                height: 60px;
                background: rgba(34, 197, 94, 0.2);
                color: #22c55e;
                font-size: 30px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0 auto 16px auto;
            }
            .success-title {
                font-size: 20px;
                font-weight: bold;
                margin-bottom: 8px;
            }
            .success-text {
                font-size: 14px;
                color: var(--text-muted);
                line-height: 1.5;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div id="formContainer">
                <div class="brand-header">
                    <div class="logo-box">
                        <div class="logo-k">K</div>
                    </div>
                    <h1>Koro <span>Pay</span></h1>
                    <div class="tagline">Платежи. Переводы. Больше.</div>
                </div>
                
                <div class="form-group">
                    <label for="service">Сервис или назначение платежа</label>
                    <input type="text" id="service" placeholder="Например: ChatGPT Plus, Hosting, инвойс">
                </div>

                <div class="row">
                    <div class="form-group">
                        <label for="amount">Сумма</label>
                        <input type="number" id="amount" placeholder="20">
                    </div>
                    <div class="form-group">
                        <label for="currency">Валюта</label>
                        <select id="currency">
                            <option value="USD">USD ($)</option>
                            <option value="EUR">EUR (€)</option>
                            <option value="USDT">USDT</option>
                            <option value="TRY">TRY (₺)</option>
                        </select>
                    </div>
                </div>

                <div class="form-group">
                    <label for="details">Ссылка на инвойс / комментарий</label>
                    <textarea id="details" rows="2" placeholder="Вставьте ссылку на оплату или реквизиты"></textarea>
                </div>

                <button class="submit-btn" id="submitBtn">Отправить заявку</button>
            </div>

            <div id="successContainer" class="success-screen">
                <div class="success-icon">✓</div>
                <div class="success-title">Заявка принята!</div>
                <div class="success-text">Менеджер уже получил ваши данные, производит расчет и свяжется с вами в Telegram.</div>
            </div>
        </div>

        <script>
            let tg = window.Telegram.WebApp;
            tg.expand();

            document.getElementById('submitBtn').addEventListener('click', async function() {
                let service = document.getElementById('service').value.trim();
                let amount = document.getElementById('amount').value.trim();
                let currency = document.getElementById('currency').value;
                let details = document.getElementById('details').value.trim();

                if (!service) {
                    alert('Пожалуйста, укажите сервис!');
                    return;
                }
                if (!amount || Number(amount) <= 0) {
                    alert('Пожалуйста, укажите корректную сумму!');
                    return;
                }

                let btn = document.getElementById('submitBtn');
                btn.disabled = true;
                btn.textContent = 'Отправка...';

                let userData = tg.initDataUnsafe || {};
                let user = userData.user || {};

                try {
                    let response = await fetch('/api/order', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            service: service,
                            amount: amount,
                            currency: currency,
                            details: details || 'Нет',
                            username: user.username || 'Аноним',
                            user_id: user.id || 0
                        })
                    });

                    if (response.ok) {
                        document.getElementById('formContainer').style.display = 'none';
                        document.getElementById('successContainer').style.display = 'block';
                        setTimeout(() => {
                            tg.close();
                        }, 2500);
                    } else {
                        alert('Ошибка отправки. Попробуйте еще раз.');
                        btn.disabled = false;
                        btn.textContent = 'Отправить заявку';
                    }
                } catch (err) {
                    alert('Ошибка соединения с сервером.');
                    btn.disabled = false;
                    btn.textContent = 'Отправить заявку';
                }
            });
        </script>
    </body>
    </html>
    """
  return web.Response(text=html_content, content_type="text/html")


async def main():
  app = web.Application()
  app.router.add_get("/", webapp_handler)
  app.router.add_post("/api/order", api_order_handler)

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