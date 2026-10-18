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


# Старт бота: выдает кнопку для открытия Банк-клиента
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
  web_app_kb = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🏦 Открыть Koro Pay Bank",
                  web_app=WebAppInfo(url=WEBAPP_URL),
              )
          ]
      ]
  )
  welcome_text = (
      "<b>👋 Добро пожаловать в Koro Pay!</b>\n\n"
      "Ваш персональный цифровой банк для международных платежей и подписок.\n"
      "Нажмите кнопку ниже, чтобы зайти в личный кабинет.\n\n"
      "<i>Платежи. Переводы. Больше.</i>"
  )
  await message.answer(
      welcome_text, reply_markup=web_app_kb, parse_mode="HTML"
  )


# API-обработчик для приема заявок из банко-приложения
async def api_order_handler(request):
  try:
    data = await request.json()
    service = data.get("service", "Не указано")
    amount = data.get("amount", "0")
    currency = data.get("currency", "USD")
    rub_total = data.get("rub_total", "0")
    user_name = data.get("username", "Аноним")
    user_id = data.get("user_id", "Неизвестно")

    user_info = f"@{user_name}" if user_name != "Аноним" else f"ID: {user_id}"

    # Уведомление для тебя (админа) в стиле банковского шлюза
    admin_message = (
        f"💳 <b>Новый платежный ордер Koro Pay!</b>\n\n"
        f"👤 Клиент: {user_info} (ID: <code>{user_id}</code>)\n"
        f"🎯 Назначение: <b>{service}</b>\n"
        f"🌍 Сумма: <b>{amount} {currency}</b>\n"
        f"🇷🇺 К списанию с клиента: <b>{rub_total} RUB</b>\n\n"
        f"👉 Подтвердите операцию и предоставьте реквизиты."
    )

    if ADMIN_CHAT_ID:
      await bot.send_message(ADMIN_CHAT_ID, admin_message, parse_mode="HTML")

    return web.json_response({"status": "success"})
  except Exception as e:
    logging.error(f"Ошибка обработки ордера: {e}")
    return web.json_response(
        {"status": "error", "message": str(e)}, status=400
    )


# Веб-сервер: полноценный интерфейс необанка
async def webapp_handler(request):
  html_content = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Koro Pay — Мобильный банк</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            :root {
                --bg-gradient: radial-gradient(circle at 50% 0%, #17132d 0%, #07080c 75%);
                --card-bg: rgba(20, 22, 30, 0.85);
                --card-inner: rgba(28, 31, 43, 0.9);
                --accent-purple: #8b5cf6;
                --accent-gradient: linear-gradient(135deg, #a855f7 0%, #6366f1 100%);
                --text-main: #ffffff;
                --text-muted: #9ca3af;
                --border: rgba(139, 92, 246, 0.2);
                --success: #22c55e;
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
                box-sizing: border-box;
                margin: auto;
            }
            /* Шапка банка */
            .bank-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
                padding: 0 4px;
            }
            .profile-info {
                display: flex;
                align-items: center;
                gap: 12px;
            }
            .avatar-badge {
                width: 42px;
                height: 42px;
                background: var(--accent-gradient);
                border-radius: 12px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: 900;
                font-size: 20px;
                box-shadow: 0 4px 15px rgba(139, 92, 246, 0.4);
            }
            .user-name {
                font-size: 15px;
                font-weight: 700;
            }
            .user-status {
                font-size: 11px;
                color: var(--success);
                background: rgba(34, 197, 94, 0.15);
                padding: 2px 8px;
                border-radius: 6px;
                display: inline-block;
                margin-top: 2px;
            }
            
            /* Банковская карта-счет */
            .bank-card {
                background: linear-gradient(135deg, #1f1a3a 0%, #12141c 100%);
                border: 1px solid var(--border);
                border-radius: 20px;
                padding: 20px;
                margin-bottom: 20px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.5);
                position: relative;
                overflow: hidden;
            }
            .bank-card::before {
                content: '';
                position: absolute;
                top: -50px; right: -50px;
                width: 120px; height: 120px;
                background: rgba(168, 85, 247, 0.1);
                border-radius: 50%;
                filter: blur(20px);
            }
            .card-title {
                font-size: 12px;
                color: var(--text-muted);
                text-transform: uppercase;
                letter-spacing: 1px;
                font-weight: 600;
            }
            .card-balance {
                font-size: 28px;
                font-weight: 800;
                margin: 8px 0 16px 0;
                letter-spacing: -0.5px;
            }
            .card-footer {
                display: flex;
                justify-content: space-between;
                font-size: 12px;
                color: var(--text-muted);
            }

            /* Панель услуг / калькулятор */
            .operations-box {
                background: var(--card-bg);
                backdrop-filter: blur(12px);
                border: 1px solid var(--border);
                border-radius: 22px;
                padding: 20px;
                box-shadow: 0 12px 35px rgba(0,0,0,0.6);
            }
            .section-title {
                font-size: 14px;
                font-weight: 700;
                margin-bottom: 14px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .form-group {
                margin-bottom: 14px;
            }
            label {
                font-size: 11px;
                font-weight: 700;
                color: var(--text-muted);
                display: block;
                margin-bottom: 6px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            input, select {
                width: 100%;
                padding: 12px 14px;
                background: var(--card-inner);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
                color: var(--text-main);
                font-size: 15px;
                box-sizing: border-box;
                transition: border-color 0.2s;
            }
            input:focus, select:focus {
                border-color: var(--accent-purple);
                outline: none;
            }
            .calc-result {
                background: rgba(139, 92, 246, 0.08);
                border: 1px dashed rgba(139, 92, 246, 0.3);
                border-radius: 12px;
                padding: 12px;
                margin-bottom: 16px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .calc-label {
                font-size: 13px;
                color: var(--text-muted);
            }
            .calc-value {
                font-size: 18px;
                font-weight: 800;
                color: #c084fc;
            }
            button.pay-btn {
                width: 100%;
                padding: 15px;
                background: var(--accent-gradient);
                color: white;
                border: none;
                border-radius: 14px;
                font-size: 16px;
                font-weight: 700;
                cursor: pointer;
                box-shadow: 0 6px 20px rgba(147, 51, 234, 0.4);
                transition: transform 0.1s ease;
            }
            button.pay-btn:active {
                transform: scale(0.97);
            }

            /* Экран успеха */
            .success-screen {
                display: none;
                text-align: center;
                padding: 30px 10px;
                background: var(--card-bg);
                border-radius: 22px;
                border: 1px solid var(--border);
            }
            .success-icon {
                width: 60px; height: 60px;
                background: rgba(34, 197, 94, 0.2);
                color: var(--success);
                font-size: 30px;
                border-radius: 50%;
                display: flex; align-items: center; justify-content: center;
                margin: 0 auto 16px auto;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div id="mainBankApp">
                <!-- Шапка -->
                <div class="bank-header">
                    <div class="profile-info">
                        <div class="avatar-badge">K</div>
                        <div>
                            <div class="user-name" id="userNameLabel">Клиент Koro Pay</div>
                            <div class="user-status">● Онлайн шлюз</div>
                        </div>
                    </div>
                </div>

                <!-- Банковский счет / Карта -->
                <div class="bank-card">
                    <div class="card-title">Виртуальный шлюз оплаты</div>
                    <div class="card-balance">Koro Pay Prime</div>
                    <div class="card-footer">
                        <span>Безопасная сделка</span>
                        <span>0% комиссия за скрытые сборы</span>
                    </div>
                </div>

                <!-- Форма заказа / Банковский перевод -->
                <div class="operations-box">
                    <div class="section-title">
                        <span>Новый платеж / Подписка</span>
                        <span style="font-size: 11px; color: #a855f7;">Авто-расчет</span>
                    </div>

                    <div class="form-group">
                        <label for="service">Сервис или назначение</label>
                        <input type="text" id="service" placeholder="Например: ChatGPT Plus, Steam, Хостинг">
                    </div>

                    <div class="form-group">
                        <label for="amount">Сумма в валюте</label>
                        <input type="number" id="amount" placeholder="20" oninput="calculateTotal()">
                    </div>

                    <div class="form-group">
                        <label for="currency">Валюта платежа</label>
                        <select id="currency" onchange="calculateTotal()">
                            <option value="USD">USD ($) — Курс 98 ₽</option>
                            <option value="EUR">EUR (€) — Курс 106 ₽</option>
                            <option value="USDT">USDT — Курс 96 ₽</option>
                            <option value="TRY">TRY (₺) — Курс 3.1 ₽</option>
                        </select>
                    </div>

                    <!-- Интерактивный калькулятор -->
                    <div class="calc-result">
                        <span class="calc-label">Итого к оплате:</span>
                        <span class="calc-value" id="totalRub">0 ₽</span>
                    </div>

                    <button class="pay-btn" onclick="submitOrder()">Провести оплату</button>
                </div>
            </div>

            <!-- Экран подтверждения -->
            <div id="successScreen" class="success-screen">
                <div class="success-icon">✓</div>
                <h2 style="margin:0 0 8px 0; font-size: 20px;">Ордер создан</h2>
                <p style="color: var(--text-muted); font-size: 14px; line-height: 1.5; margin-bottom: 20px;">
                    Запрос передан в процессинг. Менеджер банка уже проверяет детали и свяжется с вами для завершения операции.
                </p>
            </div>
        </div>

        <script>
            let tg = window.Telegram.WebApp;
            tg.expand();

            // Автоопределение имени пользователя из Telegram
            let user = (tg.initDataUnsafe && tg.initDataUnsafe.user) ? tg.initDataUnsafe.user : {};
            if (user.first_name) {
                document.getElementById('userNameLabel').textContent = user.first_name + (user.last_name ? ' ' + user.last_name : '');
            }

            // Курсы валют (можно гибко менять)
            const rates = {
                'USD': 98,
                'EUR': 106,
                'USDT': 96,
                'TRY': 3.1
            };

            function calculateTotal() {
                let amount = parseFloat(document.getElementById('amount').value) || 0;
                let currency = document.getElementById('currency').value;
                let rate = rates[currency] || 95;
                
                // Наценка/комиссия сервиса (например, +10% или фиксированная)
                let total = Math.round(amount * rate * 1.08); 
                document.getElementById('totalRub').textContent = amount > 0 ? total.toLocaleString('ru-RU') + ' ₽' : '0 ₽';
            }

            async function submitOrder() {
                let service = document.getElementById('service').value.trim();
                let amount = document.getElementById('amount').value.trim();
                let currency = document.getElementById('currency').value;
                let totalRub = document.getElementById('totalRub').textContent;

                if (!service) {
                    alert('Пожалуйста, укажите назначение платежа!');
                    return;
                }
                if (!amount || Number(amount) <= 0) {
                    alert('Пожалуйста, укажите корректную сумму!');
                    return;
                }

                let btn = document.querySelector('.pay-btn');
                btn.disabled = true;
                btn.textContent = 'Обработка шлюза...';

                try {
                    let response = await fetch('/api/order', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            service: service,
                            amount: amount,
                            currency: currency,
                            rub_total: totalRub,
                            username: user.username || 'Аноним',
                            user_id: user.id || 0
                        })
                    });

                    if (response.ok) {
                        document.getElementById('mainBankApp').style.display = 'none';
                        document.getElementById('successScreen').style.display = 'block';
                        setTimeout(() => {
                            tg.close();
                        }, 3000);
                    } else {
                        alert('Ошибка шлюза. Повторите попытку.');
                        btn.disabled = false;
                        btn.textContent = 'Провести оплату';
                    }
                } catch (err) {
                    alert('Ошибка соединения с банком.');
                    btn.disabled = false;
                    btn.textContent = 'Провести оплату';
                }
            }
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
  logging.info(f"Банковский веб-сервер запущен на порту {port}...")

  logging.info("Бот Koro Pay Bank запущен...")
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())