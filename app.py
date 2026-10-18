import asyncio
import json
import logging
import os
import random
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)
from aiohttp import web

# === ТВОИ ДАННЫЕ ===
TOKEN = "8639644231:AAF2-UwFK-lxtaqqwHOi6zPf8pcQ8xe5vGY"
ADMIN_CHAT_ID = 6084347801
WEBAPP_URL = "https://koropay-en5x.onrender.com"
# ===================

RECEIVE_CARD = "2200 3204 4647 4787"
RECEIVE_BANK = "Озон Банк"
RECEIVE_HOLDER = "Mirelem Ismailzade"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
  web_app_kb = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="💸 Отправить перевод в СНГ",
                  web_app=WebAppInfo(url=WEBAPP_URL),
              )
          ]
      ]
  )
  welcome_text = (
      "<b> Koro Pay — Международные переводы в СНГ</b>\n\n"
      "Быстро, безопасно и по выгодному курсу в национальных валютах.\n\n"
      "<i>Нажмите кнопку ниже, чтобы открыть приложение.</i>"
  )
  await message.answer(
      welcome_text, reply_markup=web_app_kb, parse_mode="HTML"
  )


# Обработка заявок от Web App
async def api_order_handler(request):
  try:
    data = await request.json()
    country = data.get("country", "СНГ")
    local_amount = data.get("local_amount", "0")
    currency = data.get("currency", "VAL")
    rub_total = data.get("rub_total", "0")
    recipient_name = data.get("recipient_name", "Не указано")
    recipient_card = data.get("recipient_card", "Не указано")
    user_name = data.get("username", "Аноним")
    user_id = data.get("user_id", "0")

    user_info = f"@{user_name}" if user_name != "Аноним" else f"ID: {user_id}"
    tx_id = f"KP-{random.randint(100000, 999999)}"

    # Кнопка для админа, чтобы подтвердить платеж
    admin_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить перевод (Пришло)",
                    callback_data=f"approve_{user_id}_{tx_id}",
                )
            ]
        ]
    )

    admin_message = (
        f"🚨 <b>Новый перевод на проверку! [<code>{tx_id}</code>]</b>\n\n"
        f"👤 Клиент: {user_info} (ID: <code>{user_id}</code>)\n"
        f"🌍 Направление: <b>{country}</b>\n"
        f"💶 Сумма: <b>{local_amount} {currency}</b>\n"
        f"🇷🇺 Ожидается от клиента: <b>{rub_total} RUB</b>\n\n"
        f"👤 Получатель: <b>{recipient_name}</b>\n"
        f"💳 Карта получателя: <code>{recipient_card}</code>\n\n"
        f"👉 Проверьте Озон Банк ({RECEIVE_CARD}). Если деньги поступили, нажмите кнопку ниже:"
    )

    if ADMIN_CHAT_ID:
      await bot.send_message(
          ADMIN_CHAT_ID, admin_message, parse_mode="HTML", reply_markup=admin_kb
      )

    return web.json_response({"status": "success", "tx_id": tx_id})
  except Exception as e:
    logging.error(f"Ошибка API: {e}")
    return web.json_response(
        {"status": "error", "message": str(e)}, status=400
    )


# Обработка нажатия кнопки админом в Telegram
@dp.callback_query(F.data.startswith("approve_"))
async def process_approve(callback: types.CallbackQuery):
  parts = callback.data.split("_")
  target_user_id = int(parts[1])
  tx_id = parts[2]

  await callback.message.edit_text(
      callback.message.text
      + f"\n\n✅ <b>ПЛАТЕЖ ПОДТВЕРЖДЕН И ОТПРАВЛЕН!</b> [Транзакция: {tx_id}]",
      parse_mode="HTML",
  )

  try:
    success_text = (
        f"🎉 <b>Ваш перевод успешно выполнен!</b>\n\n"
        f"🆔 Номер транзакции: <code>{tx_id}</code>\n"
        f"✅ Средства отправлены получателю.\n\n"
        f"Благодарим за использование <b>Koro Pay</b>! Пожалуйста, ожидайте зачисления средств."
    )
    await bot.send_message(target_user_id, success_text, parse_mode="HTML")
  except Exception as e:
    logging.error(f"Не удалось отправить уведомление клиенту: {e}")

  await callback.answer("Перевод подтвержден!")


async def webapp_handler(request):
  html_content = f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Koro Pay — Денежные переводы</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            :root {{
                --bg-color: #0c0d12;
                --card-bg: #151721;
                --card-inner: #1e2130;
                --accent: #8b5cf6;
                --accent-gradient: linear-gradient(135deg, #a855f7 0%, #6366f1 100%);
                --text-main: #ffffff;
                --text-muted: #9ca3af;
                --border: rgba(139, 92, 246, 0.2);
                --success: #22c55e;
            }}
            body {{
                background: var(--bg-color);
                color: var(--text-main);
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                margin: 0; padding: 16px;
                display: flex; flex-direction: column; align-items: center;
                min-height: 100vh; box-sizing: border-box;
            }}
            .container {{
                width: 100%; max-width: 400px; margin: auto;
                background: var(--card-bg); border: 1px solid var(--border);
                border-radius: 20px; padding: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.5);
                box-sizing: border-box;
            }}
            h2 {{ margin: 0 0 4px 0; font-size: 20px; text-align: center; }}
            .subtitle {{ font-size: 12px; color: var(--text-muted); text-align: center; margin-bottom: 20px; text-transform: uppercase; letter-spacing: 1px; }}
            
            .form-group {{ margin-bottom: 14px; }}
            label {{ font-size: 11px; font-weight: 700; color: var(--text-muted); display: block; margin-bottom: 6px; text-transform: uppercase; }}
            input, select {{
                width: 100%; padding: 12px; background: var(--card-inner);
                border: 1px solid rgba(255,255,255,0.08); border-radius: 10px;
                color: #fff; font-size: 15px; box-sizing: border-box;
            }}
            input:focus, select:focus {{ border-color: var(--accent); outline: none; }}
            
            .calc-box {{
                background: rgba(139,92,246,0.08); border: 1px dashed rgba(139,92,246,0.3);
                border-radius: 10px; padding: 12px; margin-bottom: 16px;
                display: flex; justify-content: space-between; align-items: center;
            }}
            .calc-val {{ font-size: 18px; font-weight: bold; color: #c084fc; }}
            
            button.main-btn {{
                width: 100%; padding: 14px; background: var(--accent-gradient);
                color: white; border: none; border-radius: 12px; font-size: 16px; font-weight: bold;
                cursor: pointer; box-shadow: 0 4px 15px rgba(139,92,246,0.4);
            }}
            
            .screen {{ display: none; }}
            .active {{ display: block; }}
            
            .req-box {{
                background: var(--card-inner); border: 1px solid var(--border);
                border-radius: 12px; padding: 14px; margin: 12px 0; text-align: left;
            }}
            .copy-btn {{
                background: rgba(139,92,246,0.2); border: 1px solid var(--accent);
                color: #c084fc; padding: 8px; border-radius: 8px; font-size: 13px;
                font-weight: bold; cursor: pointer; width: 100%; margin-top: 8px;
            }}
            .spinner {{
                font-size: 40px; text-align: center; margin: 20px 0;
                animation: pulse 1.5s infinite;
            }}
            @keyframes pulse {{ 0% {{ opacity: 0.3; }} 50% {{ opacity: 1; }} 100% {{ opacity: 0.3; }} }}
        </style>
    </head>
    <body>
        <div class="container">
            <!-- ЭКРАН 1: ВВОД ДАННЫХ -->
            <div id="screenForm" class="screen active">
                <h2>Koro Pay</h2>
                <div class="subtitle">Переводы в страны СНГ</div>

                <div class="form-group">
                    <label for="country">Страна назначения</label>
                    <select id="country" onchange="updateCurrency()">
                        <option value="Uzbekistan|UZS|94">🇺🇿 Узбекистан (UZS)</option>
                        <option value="Tajikistan|TJS|11.5">🇹🇯 Таджикистан (TJS)</option>
                        <option value="Kyrgyzstan|KGS|1.1">🇰🇬 Киргизия (KGS)</option>
                        <option value="Azerbaijan|AZN|57">🇦🇿 Азербайджан (AZN)</option>
                    </select>
                </div>

                <div class="form-group">
                    <label for="amount">Сумма в валюте страны</label>
                    <input type="number" id="amount" placeholder="Например: 500000" oninput="calculateRub()">
                </div>

                <div class="calc-box">
                    <span>Итого к оплате:</span>
                    <span class="calc-val" id="totalRub">0 ₽</span>
                </div>

                <div class="form-group">
                    <label for="recName">ФИО получателя</label>
                    <input type="text" id="recName" placeholder="Иван Иванов">
                </div>

                <div class="form-group">
                    <label for="recCard">Номер карты получателя</label>
                    <input type="text" id="recCard" placeholder="9860 ... или 4000 ...">
                </div>

                <button class="main-btn" onclick="submitForm()">Продолжить</button>
            </div>

            <!-- ЭКРАН 2: ОПЛАТА ПО РЕКВИЗИТАМ -->
            <div id="screenPay" class="screen">
                <h2>Оплата перевода</h2>
                <div class="subtitle">Лимит: до 25 000 ₽</div>

                <div class="req-box">
                    <div style="font-size: 11px; color: var(--text-muted);">К ОПЛАТЕ В РУБЛЯХ:</div>
                    <div id="payRubSum" style="font-size: 20px; font-weight: bold; color: #c084fc; margin-top: 4px;">0 ₽</div>
                </div>

                <div class="req-box">
                    <div style="font-size: 11px; color: var(--text-muted);">РЕКВИЗИТЫ ({RECEIVE_BANK}):</div>
                    <div id="cardText" style="font-size: 16px; font-weight: bold; margin-top: 4px; word-break: break-all;">{RECEIVE_CARD}</div>
                    <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">Получатель: <b>{RECEIVE_HOLDER}</b></div>
                    <button class="copy-btn" onclick="copyCard()">📋 Скопировать карту</button>
                </div>

                <button class="main-btn" onclick="confirmPayment()" style="background: var(--success); box-shadow: 0 4px 15px rgba(34,197,94,0.4);">Я оплатил(а)</button>
            </div>

            <!-- ЭКРАН 3: ОЖИДАНИЕ ПРОВЕРКИ АДМИНОМ -->
            <div id="screenWait" class="screen" style="text-align: center;">
                <div class="spinner">⏳</div>
                <h3 style="margin: 0 0 8px 0;">Проверка платежа</h3>
                <p style="color: var(--text-muted); font-size: 13px; line-height: 1.5;">
                    Мы проверяем поступление средств на наш счет. Пожалуйста, не закрывайте приложение, скоро здесь появится статус транзакции.
                </p>
            </div>
        </div>

        <script>
            let tg = window.Telegram.WebApp;
            tg.expand();

            let currentRate = 94;
            let currentCurr = 'UZS';
            let calculatedRub = 0;

            function updateCurrency() {{
                let val = document.getElementById('country').value.split('|');
                currentCurr = val[1];
                currentRate = parseFloat(val[2]);
                calculateRub();
            }}

            function calculateRub() {{
                let amt = parseFloat(document.getElementById('amount').value) || 0;
                // Расчет рублей по курсу + небольшая комиссия
                calculatedRub = Math.round(amt / currentRate * 1.05); 
                document.getElementById('totalRub').textContent = amt > 0 ? calculatedRub.toLocaleString('ru-RU') + ' ₽' : '0 ₽';
            }}

            function copyCard() {{
                navigator.clipboard.writeText("{RECEIVE_CARD}".replace(/\\s+/g, ''));
                let btn = document.querySelector('.copy-btn');
                btn.textContent = '✅ Скопировано!';
                setTimeout(() => {{ btn.textContent = '📋 Скопировать карту'; }}, 2000);
            }}

            async function submitForm() {{
                let amt = parseFloat(document.getElementById('amount').value) || 0;
                let name = document.getElementById('recName').value.trim();
                let card = document.getElementById('recCard').value.trim();

                if (amt <= 0) {{
                    alert('Введите корректную сумму!');
                    return;
                }}
                if (calculatedRub > 25000) {{
                    alert('Максимальная сумма отправки составляет 25 000 рублей!');
                    return;
                }}
                if (!name || !card) {{
                    alert('Заполните данные получателя!');
                    return;
                }}

                document.getElementById('payRubSum').textContent = calculatedRub.toLocaleString('ru-RU') + ' ₽';
                
                document.getElementById('screenForm').classList.remove('active');
                document.getElementById('screenPay').classList.add('active');
            }}

            async function confirmPayment() {{
                let countrySelect = document.getElementById('country');
                let countryName = countrySelect.options[countrySelect.selectedIndex].text;
                let amt = document.getElementById('amount').value;
                let name = document.getElementById('recName').value;
                let card = document.getElementById('recCard').value;

                let user = (tg.initDataUnsafe && tg.initDataUnsafe.user) ? tg.initDataUnsafe.user : {{}};

                document.getElementById('screenPay').classList.remove('active');
                document.getElementById('screenWait').classList.add('active');

                try {{
                    let response = await fetch('/api/order', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{
                            country: countryName,
                            local_amount: amt,
                            currency: currentCurr,
                            rub_total: calculatedRub + ' ₽',
                            recipient_name: name,
                            recipient_card: card,
                            username: user.username || 'Аноним',
                            user_id: user.id || 0
                        }})
                    }});
                    // Ожидание подтверждения от бота происходит через вебсокет/опрос или бота
                }} catch (e) {{
                    alert('Ошибка связи с сервером.');
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
  logging.info(f"Сервер запущен на порту {port}...")

  logging.info("Бот Koro Pay запущен...")
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())