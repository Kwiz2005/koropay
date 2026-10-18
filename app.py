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

# Твои реквизиты для приема рублей от клиента (можешь изменить в любой момент)
RECEIVE_CARD = "2202 2010 4455 6677"
RECEIVE_HOLDER = "Мирелем И. (Koro Pay)"
RECEIVE_BANK = "Т-Банк / Сбер (по СБП)"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()


# Старт бота
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
  web_app_kb = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🌍 Сделать международный перевод",
                  web_app=WebAppInfo(url=WEBAPP_URL),
              )
          ]
      ]
  )
  welcome_text = (
      "<b>🌐 Добро пожаловать в Koro Pay Remittance!</b>\n\n"
      "Сервис быстрых и надежных денежных переводов за рубеж.\n"
      "Отправляйте средства по всему миру безопасно и по выгодному курсу.\n\n"
      "<i>Нажмите кнопку ниже, чтобы рассчитать и оформить перевод.</i>"
  )
  await message.answer(
      welcome_text, reply_markup=web_app_kb, parse_mode="HTML"
  )


# API-обработчик: фиксирует заявку и шлет отчет админу
async def api_order_handler(request):
  try:
    data = await request.json()
    direction = data.get("direction", "За рубеж")
    amount = data.get("amount", "0")
    currency = data.get("currency", "USD")
    rub_total = data.get("rub_total", "0")
    recipient_info = data.get("recipient_info", "Не указано")
    user_name = data.get("username", "Аноним")
    user_id = data.get("user_id", "Неизвестно")

    user_info = f"@{user_name}" if user_name != "Аноним" else f"ID: {user_id}"

    admin_message = (
        f"💸 <b>Новая заявка на перевод!</b>\n\n"
        f"👤 Клиент: {user_info} (ID: <code>{user_id}</code>)\n"
        f"🌐 Направление: <b>{direction}</b>\n"
        f"💶 Сумма отправки: <b>{amount} {currency}</b>\n"
        f"🇷🇺 К получению от клиента: <b>{rub_total}</b>\n"
        f"📍 Реквизиты получателя: <code>{recipient_info}</code>\n\n"
        f"👉 Ожидайте поступления средств на ваши реквизиты."
    )

    if ADMIN_CHAT_ID:
      await bot.send_message(ADMIN_CHAT_ID, admin_message, parse_mode="HTML")

    return web.json_response({"status": "success"})
  except Exception as e:
    logging.error(f"Ошибка перевода: {e}")
    return web.json_response(
        {"status": "error", "message": str(e)}, status=400
    )


# Веб-интерфейс необанка для переводов
async def webapp_handler(request):
  html_content = f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Koro Pay — Международные переводы</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            :root {{
                --bg-gradient: radial-gradient(circle at 50% 0%, #17132d 0%, #07080c 75%);
                --card-bg: rgba(20, 22, 30, 0.9);
                --card-inner: rgba(28, 31, 43, 0.95);
                --accent-purple: #8b5cf6;
                --accent-gradient: linear-gradient(135deg, #a855f7 0%, #6366f1 100%);
                --text-main: #ffffff;
                --text-muted: #9ca3af;
                --border: rgba(139, 92, 246, 0.25);
                --success: #22c55e;
            }}
            body {{
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
            }}
            .container {{
                width: 100%;
                max-width: 400px;
                box-sizing: border-box;
                margin: auto;
            }}
            .bank-header {{
                display: flex;
                align-items: center;
                gap: 12px;
                margin-bottom: 20px;
                padding: 0 4px;
            }}
            .avatar-badge {{
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
            }}
            .user-name {{
                font-size: 15px;
                font-weight: 700;
            }}
            .user-status {{
                font-size: 11px;
                color: var(--success);
                background: rgba(34, 197, 94, 0.15);
                padding: 2px 8px;
                border-radius: 6px;
                display: inline-block;
                margin-top: 2px;
            }
            .operations-box {{
                background: var(--card-bg);
                backdrop-filter: blur(12px);
                border: 1px solid var(--border);
                border-radius: 22px;
                padding: 20px;
                box-shadow: 0 12px 35px rgba(0,0,0,0.6);
            }}
            .section-title {{
                font-size: 14px;
                font-weight: 700;
                margin-bottom: 14px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            .form-group {{
                margin-bottom: 14px;
            }}
            label {{
                font-size: 11px;
                font-weight: 700;
                color: var(--text-muted);
                display: block;
                margin-bottom: 6px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            input, select, textarea {{
                width: 100%;
                padding: 12px 14px;
                background: var(--card-inner);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
                color: var(--text-main);
                font-size: 15px;
                box-sizing: border-box;
                transition: border-color 0.2s;
            }}
            input:focus, select:focus, textarea:focus {{
                border-color: var(--accent-purple);
                outline: none;
            }}
            .calc-result {{
                background: rgba(139, 92, 246, 0.08);
                border: 1px dashed rgba(139, 92, 246, 0.3);
                border-radius: 12px;
                padding: 12px;
                margin-bottom: 16px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            .calc-label {{
                font-size: 13px;
                color: var(--text-muted);
            }}
            .calc-value {{
                font-size: 18px;
                font-weight: 800;
                color: #c084fc;
            }}
            button.pay-btn {{
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
            }}
            button.pay-btn:active {{
                transform: scale(0.97);
            }}
            /* Экран с реквизитами */
            .requisites-screen {{
                display: none;
                background: var(--card-bg);
                border: 1px solid var(--border);
                border-radius: 22px;
                padding: 20px;
                text-align: center;
            }}
            .req-box {{
                background: var(--card-inner);
                border: 1px solid rgba(139, 92, 246, 0.3);
                border-radius: 14px;
                padding: 14px;
                margin: 14px 0;
                text-align: left;
            }}
            .req-label {{
                font-size: 11px;
                color: var(--text-muted);
                text-transform: uppercase;
            }}
            .req-val {{
                font-size: 18px;
                font-weight: bold;
                color: #fff;
                margin-top: 4px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div id="transferApp">
                <div class="bank-header">
                    <div class="avatar-badge">K</div>
                    <div>
                        <div class="user-name" id="userNameLabel">Клиент Koro Pay</div>
                        <div class="user-status">● Шлюз переводов активен</div>
                    </div>
                </div>

                <div class="operations-box">
                    <div class="section-title">
                        <span>Международный перевод</span>
                        <span style="font-size: 11px; color: #a855f7;">Secure Transfer</span>
                    </div>

                    <div class="form-group">
                        <label for="direction">Направление перевода</label>
                        <select id="direction">
                            <option value="Europe (IBAN)">Европа (SEPA / IBAN)</option>
                            <option value="Turkey (Card/IBAN)">Турция (Карта / IBAN)</option>
                            <option value="Global SWIFT">Весь мир (SWIFT перевод)</option>
                            <option value="USDT Crypto">Криптоперевод (USDT TRC20)</option>
                        </select>
                    </div>

                    <div class="form-group">
                        <label for="amount">Сумма перевода</label>
                        <input type="number" id="amount" placeholder="100" oninput="calculateTotal()">
                    </div>

                    <div class="form-group">
                        <label for="currency">Валюта получения</label>
                        <select id="currency" onchange="calculateTotal()">
                            <option value="USD">USD ($) — Курс 98 ₽</option>
                            <option value="EUR">EUR (€) — Курс 106 ₽</option>
                            <option value="USDT">USDT — Курс 96 ₽</option>
                            <option value="TRY">TRY (₺) — Курс 3.1 ₽</option>
                        </select>
                    </div>

                    <div class="form-group">
                        <label for="recipient">Реквизиты получателя за рубежом</label>
                        <textarea id="recipient" rows="2" placeholder="ФИО получателя, IBAN / Номер карты / Банк"></textarea>
                    </div>

                    <div class="calc-result">
                        <span class="calc-label">К оплате в рублях:</span>
                        <span class="calc-value" id="totalRub">0 ₽</span>
                    </div>

                    <button class="pay-btn" onclick="submitTransfer()">Получить реквизиты для оплаты</button>
                </div>
            </div>

            <!-- Экран выдачи реквизитов клиенту -->
            <div id="requisitesScreen" class="requisites-screen">
                <div style="font-size: 36px; margin-bottom: 10px;">⏳</div>
                <h3 style="margin: 0 0 8px 0; font-size: 20px;">Заявка создана!</h3>
                <p style="color: var(--text-muted); font-size: 13px; line-height: 1.4; margin-bottom: 16px;">
                    Для завершения перевода переведите точную сумму на наши реквизиты в РФ. После поступления средств мы отправим деньги получателю.
                </p>

                <div class="req-box">
                    <div class="req-label">Сумма к оплате:</div>
                    <div class="req-val" id="finalPaySum" style="color: #c084fc;">0 ₽</div>
                </div>

                <div class="req-box">
                    <div class="req-label">Номер карты / СБП для оплаты:</div>
                    <div class="req-val">{RECEIVE_CARD}</div>
                    <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">{RECEIVE_BANK} ({RECEIVE_HOLDER})</div>
                </div>

                <button class="pay-btn" onclick="tg.close()" style="margin-top: 10px;">Готово, я оплатил(а)</button>
            </div>
        </div>

        <script>
            let tg = window.Telegram.WebApp;
            tg.expand();

            let user = (tg.initDataUnsafe && tg.initDataUnsafe.user) ? tg.initDataUnsafe.user : {{}};
            if (user.first_name) {{
                document.getElementById('userNameLabel').textContent = user.first_name;
            }}

            const rates = {{
                'USD': 98,
                'EUR': 106,
                'USDT': 96,
                'TRY': 3.1
            }};

            function calculateTotal() {{
                let amount = parseFloat(document.getElementById('amount').value) || 0;
                let currency = document.getElementById('currency').value;
                let rate = rates[currency] || 95;
                let total = Math.round(amount * rate * 1.05); // Комиссия сервиса 5%
                document.getElementById('totalRub').textContent = amount > 0 ? total.toLocaleString('ru-RU') + ' ₽' : '0 ₽';
            }}

            async function submitTransfer() {{
                let direction = document.getElementById('direction').value;
                let amount = document.getElementById('amount').value.trim();
                let currency = document.getElementById('currency').value;
                let recipient = document.getElementById('recipient').value.trim();
                let totalRub = document.getElementById('totalRub').textContent;

                if (!amount || Number(amount) <= 0) {{
                    alert('Укажите корректную сумму перевода!');
                    return;
                }}
                if (!recipient) {{
                    alert('Укажите реквизиты получателя за рубежом!');
                    return;
                }}

                let btn = document.querySelector('.pay-btn');
                btn.disabled = true;
                btn.textContent = 'Генерация реквизитов...';

                try {{
                    let response = await fetch('/api/order', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{
                            direction: direction,
                            amount: amount,
                            currency: currency,
                            rub_total: totalRub,
                            recipient_info: recipient,
                            username: user.username || 'Аноним',
                            user_id: user.id || 0
                        }})
                    }});

                    if (response.ok) {{
                        document.getElementById('transferApp').style.display = 'none';
                        document.getElementById('finalPaySum').textContent = totalRub;
                        document.getElementById('requisitesScreen').style.display = 'block';
                    }} else {{
                        alert('Ошибка создания перевода. Повторите попытку.');
                        btn.disabled = false;
                        btn.textContent = 'Получить реквизиты для оплаты';
                    }}
                }} catch (err) {{
                    alert('Ошибка соединения с сервером.');
                    btn.disabled = false;
                    btn.textContent = 'Получить реквизиты для оплаты';
                }}
            }}
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
  logging.info(f"Сервер переводов запущен на порту {port}...")

  logging.info("Бот Koro Pay запущен...")
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())