import asyncio
import json
import logging
import os
import random
import time
import sqlite3
import aiohttp
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
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

# Базовые курсы (обновляются автоматически)
EXCHANGE_RATES = {"UZS": 135.00, "TJS": 0.115, "KGS": 0.95, "AZN": 0.018}
COMMISSION_MARGIN = 0.95 

user_cooldowns = {}

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# === ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ SQLite ===
def init_db():
    conn = sqlite3.connect('koropay.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, username TEXT, strikes INTEGER DEFAULT 0, is_banned INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS transfers 
                 (tx_id TEXT PRIMARY KEY, user_id INTEGER, country TEXT, rub_amount TEXT, local_amount TEXT, currency TEXT, status TEXT)''')
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('koropay.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = c.fetchone()
    conn.close()
    return user

def add_strike(user_id):
    conn = sqlite3.connect('koropay.db')
    c = conn.cursor()
    c.execute("UPDATE users SET strikes = strikes + 1 WHERE user_id=?", (user_id,))
    c.execute("UPDATE users SET is_banned = 1 WHERE user_id=? AND strikes >= 3", (user_id,))
    conn.commit()
    conn.close()

# Парсер курсов
async def update_rates():
    global EXCHANGE_RATES
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://open.er-api.com/v6/latest/RUB") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        rates = data.get("rates", {})
                        if rates:
                            if "UZS" in rates: EXCHANGE_RATES["UZS"] = rates["UZS"] * COMMISSION_MARGIN
                            if "TJS" in rates: EXCHANGE_RATES["TJS"] = rates["TJS"] * COMMISSION_MARGIN
                            if "KGS" in rates: EXCHANGE_RATES["KGS"] = rates["KGS"] * COMMISSION_MARGIN
                            if "AZN" in rates: EXCHANGE_RATES["AZN"] = rates["AZN"] * COMMISSION_MARGIN
        except Exception as e:
            logging.error(f"Ошибка обновления курсов: {e}")
        await asyncio.sleep(3600)


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "Аноним"
    
    conn = sqlite3.connect('koropay.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    conn.close()

    user_data = get_user(user_id)
    if user_data and user_data[3] == 1:
        await message.answer("🚫 Ваш аккаунт заблокирован за нарушение правил сервиса.")
        return

    web_app_kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💸 Отправить перевод", web_app=WebAppInfo(url=WEBAPP_URL))]]
    )
    await message.answer(
        "<b>🌐 Koro Pay — Международные переводы</b>\n\n"
        "Лимит перевода: до 25 000 ₽ за раз.\n"
        "<i>Нажмите кнопку ниже, чтобы открыть приложение.</i>\n\n"
        "Проверить историю переводов: /profile",
        reply_markup=web_app_kb, parse_mode="HTML"
    )

@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    user_id = message.from_user.id
    conn = sqlite3.connect('koropay.db')
    c = conn.cursor()
    c.execute("SELECT tx_id, rub_amount, local_amount, currency, status FROM transfers WHERE user_id=? ORDER BY ROWID DESC LIMIT 5", (user_id,))
    history = c.fetchall()
    conn.close()

    if not history:
        await message.answer("У вас пока нет истории переводов.")
        return

    text = "<b>📁 Ваши последние переводы:</b>\n\n"
    for tx in history:
        status_emoji = "✅" if tx[4] == "SUCCESS" else ("❌" if tx[4] == "REJECTED" else "⏳")
        text += f"{status_emoji} <code>{tx[0]}</code> | {tx[1]} ➡️ {tx[2]} {tx[3]}\n"
    
    await message.answer(text, parse_mode="HTML")


async def api_order_handler(request):
    try:
        data = await request.json()
        user_id = data.get("user_id", 0)

        current_time = time.time()
        if user_id in user_cooldowns and current_time - user_cooldowns[user_id] < 60:
            return web.json_response({"status": "error", "message": "Подождите минуту перед созданием новой заявки."}, status=400)
        user_cooldowns[user_id] = current_time

        user_data = get_user(user_id)
        if user_data and user_data[3] == 1:
            return web.json_response({"status": "error", "message": "Аккаунт заблокирован."}, status=403)

        country = data.get("country", "СНГ")
        rub_amount = data.get("rub_amount", "0")
        local_received = data.get("local_received", "0")
        currency = data.get("currency", "VAL")
        recipient_name = data.get("recipient_name", "Не указано")
        recipient_card = data.get("recipient_card", "Не указано")
        transfer_comment = data.get("transfer_comment", "Нет комментария")
        user_name = data.get("username", "Аноним")

        tx_id = transfer_comment

        conn = sqlite3.connect('koropay.db')
        c = conn.cursor()
        c.execute("INSERT INTO transfers VALUES (?, ?, ?, ?, ?, ?, ?)", 
                  (tx_id, user_id, country, rub_amount, local_received, currency, "PENDING"))
        conn.commit()
        conn.close()

        admin_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Пришло", callback_data=f"approve_{user_id}_{tx_id}")],
                [InlineKeyboardButton(text="❌ Фейк (Не пришло)", callback_data=f"reject_{user_id}_{tx_id}")]
            ]
        )

        admin_message = (
            f"🚨 <b>Новый перевод на проверку!</b>\n\n"
            f"🆔 Транзакция: <code>{tx_id}</code>\n"
            f"👤 Клиент: @{user_name} (ID: <code>{user_id}</code>)\n"
            f"🇷🇺 Отправлено: <b>{rub_amount}</b>\n"
            f"💶 К выплате: <b>{local_received} {currency}</b>\n\n"
            f"💳 Карта получателя: <code>{recipient_card}</code>\n"
            f"👤 Имя получателя: <b>{recipient_name}</b>\n\n"
            f"👉 Проверьте поступление на {RECEIVE_CARD} с комментарием '{tx_id}'."
        )

        if ADMIN_CHAT_ID:
            await bot.send_message(ADMIN_CHAT_ID, admin_message, parse_mode="HTML", reply_markup=admin_kb)

        return web.json_response({"status": "success", "tx_id": tx_id})
    except Exception as e:
        logging.error(f"Ошибка API: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=400)


@dp.callback_query(F.data.startswith("approve_"))
async def process_approve(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    target_user_id = int(parts[1])
    tx_id = parts[2]

    conn = sqlite3.connect('koropay.db')
    c = conn.cursor()
    c.execute("UPDATE transfers SET status='SUCCESS' WHERE tx_id=?", (tx_id,))
    conn.commit()
    conn.close()

    await callback.message.edit_text(callback.message.text + f"\n\n✅ <b>ПОДТВЕРЖДЕН</b>", parse_mode="HTML")
    try:
        await bot.send_message(target_user_id, f"🎉 <b>Перевод {tx_id} выполнен!</b>\nСредства отправлены получателю.", parse_mode="HTML")
    except: pass
    await callback.answer("Перевод подтвержден!")

@dp.callback_query(F.data.startswith("reject_"))
async def process_reject(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    target_user_id = int(parts[1])
    tx_id = parts[2]

    conn = sqlite3.connect('koropay.db')
    c = conn.cursor()
    c.execute("UPDATE transfers SET status='REJECTED' WHERE tx_id=?", (tx_id,))
    conn.commit()
    conn.close()
    add_strike(target_user_id)

    await callback.message.edit_text(callback.message.text + f"\n\n❌ <b>ОТКЛОНЕН (ФЕЙК)</b>", parse_mode="HTML")
    try:
        await bot.send_message(target_user_id, f"❌ Ваш платеж <code>{tx_id}</code> не найден. Вы получили предупреждение. За 3 ложных заявки аккаунт блокируется.", parse_mode="HTML")
    except: pass
    await callback.answer("Отклонено!")


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
                --bg-color: #0c0d12; --card-bg: #151721; --card-inner: #1e2130;
                --accent: #8b5cf6; --accent-gradient: linear-gradient(135deg, #a855f7 0%, #6366f1 100%);
                --text-main: #ffffff; --text-muted: #9ca3af;
                --border: rgba(139, 92, 246, 0.2); --success: #22c55e;
            }}
            body {{
                background: var(--bg-color); color: var(--text-main);
                font-family: -apple-system, sans-serif;
                margin: 0; padding: 16px; display: flex; flex-direction: column; align-items: center;
                min-height: 100vh; box-sizing: border-box;
            }}
            .container {{
                width: 100%; max-width: 400px; margin: auto;
                background: var(--card-bg); border: 1px solid var(--border);
                border-radius: 20px; padding: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.5);
                box-sizing: border-box; position: relative;
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
            .link {{ color: #c084fc; text-decoration: underline; cursor: pointer; }}
            button.main-btn {{
                width: 100%; padding: 14px; background: var(--accent-gradient);
                color: white; border: none; border-radius: 12px; font-size: 16px; font-weight: bold;
                cursor: pointer; box-shadow: 0 4px 15px rgba(139,92,246,0.4);
            }}
            .screen {{ display: none; }}
            .active {{ display: block; }}
            .req-box {{ background: var(--card-inner); border: 1px solid var(--border); border-radius: 12px; padding: 14px; margin: 12px 0; text-align: left; }}
            .copy-btn {{
                background: rgba(139,92,246,0.2); border: 1px solid var(--accent); color: #c084fc;
                padding: 8px; border-radius: 8px; font-size: 13px; font-weight: bold; cursor: pointer; width: 100%; margin-top: 8px;
            }}
            .timer {{ font-size: 14px; color: #f59e0b; text-align: center; font-weight: bold; margin-bottom: 10px; }}
            
            /* Модальное окно */
            .modal-overlay {{
                display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
                background: rgba(0,0,0,0.8); z-index: 100; justify-content: center; align-items: center; padding: 16px; box-sizing: border-box;
            }}
            .modal-content {{
                background: var(--card-bg); border: 1px solid var(--border); border-radius: 16px;
                padding: 20px; width: 100%; max-width: 360px; max-height: 80vh; overflow-y: auto;
            }}
            .modal-content h3 {{ margin-top: 0; font-size: 18px; color: #fff; }}
            .modal-content p {{ font-size: 12px; color: var(--text-muted); line-height: 1.5; margin-bottom: 10px; }}
            .close-modal {{
                background: var(--card-inner); border: 1px solid var(--border); color: #fff;
                padding: 10px; width: 100%; border-radius: 8px; margin-top: 10px; cursor: pointer; font-weight:bold;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <!-- ЭКРАН 1: ФОРМА -->
            <div id="screenForm" class="screen active">
                <h2>Koro Pay</h2>
                <div class="subtitle">Защищенные переводы в СНГ</div>

                <div class="form-group">
                    <label>Страна назначения</label>
                    <select id="country" onchange="calculateLocal()">
                        <option value="Uzbekistan|UZS|{EXCHANGE_RATES['UZS']}">🇺🇿 Узбекистан (UZS)</option>
                        <option value="Tajikistan|TJS|{EXCHANGE_RATES['TJS']}">🇹🇯 Таджикистан (TJS)</option>
                        <option value="Kyrgyzstan|KGS|{EXCHANGE_RATES['KGS']}">🇰🇬 Киргизия (KGS)</option>
                        <option value="Azerbaijan|AZN|{EXCHANGE_RATES['AZN']}">🇦🇿 Азербайджан (AZN)</option>
                    </select>
                </div>

                <div class="form-group">
                    <label>Сумма отправки (в рублях)</label>
                    <input type="number" id="amount" placeholder="Макс. 25 000 ₽" oninput="calculateLocal()">
                </div>

                <div class="calc-box">
                    <span>Получатель заберет:</span>
                    <span class="calc-val" id="totalLocal">0.00 UZS</span>
                </div>

                <div class="form-group">
                    <input type="text" id="recName" placeholder="ФИО получателя">
                </div>
                <div class="form-group">
                    <input type="text" id="recCard" placeholder="Номер карты получателя">
                </div>

                <div class="security-notice">
                    🛡 <b>Безопасность:</b> Перевод должен осуществляться строго с вашей личной карты. Третьи лица не допускаются.
                </div>

                <div class="checkbox-group">
                    <input type="checkbox" id="termsCheck">
                    <label for="termsCheck" style="text-transform: none; display: inline; color: var(--text-muted); cursor: pointer;">
                        Я согласен с <span class="link" onclick="openModal(event)">условиями оферты</span> и подтверждаю легальность средств.
                    </label>
                </div>

                <button class="main-btn" onclick="submitForm()">Продолжить</button>
            </div>

            <!-- ЭКРАН 2: ОПЛАТА -->
            <div id="screenPay" class="screen">
                <h2>Оплата перевода</h2>
                <div class="subtitle">Защищенный шлюз</div>
                <div class="timer" id="timerDisplay">Осталось времени: 15:00</div>
                
                <div class="req-box">
                    <div style="font-size: 11px; color: var(--text-muted);">К ОПЛАТЕ:</div>
                    <div id="payRubSum" style="font-size: 20px; font-weight: bold; color: #c084fc; margin-top: 4px;">0 ₽</div>
                </div>

                <div class="req-box">
                    <div style="font-size: 11px; color: var(--text-muted);">ОБЯЗАТЕЛЬНЫЙ КОММЕНТАРИЙ К ПЕРЕВОДУ:</div>
                    <div id="transferCommentText" style="font-size: 18px; font-weight: bold; margin-top: 4px; color: #f59e0b;">KORO-0000</div>
                    <button class="copy-btn" id="copyCommentBtn" onclick="copyComment()">📋 Скопировать комментарий</button>
                </div>

                <div class="req-box">
                    <div style="font-size: 11px; color: var(--text-muted);">РЕКВИЗИТЫ ({RECEIVE_BANK}):</div>
                    <div style="font-size: 16px; font-weight: bold; margin-top: 4px; word-break: break-all;">{RECEIVE_CARD}</div>
                    <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">Получатель: <b>{RECEIVE_HOLDER}</b></div>
                    <button class="copy-btn" id="copyCardBtn" onclick="copyCard()">📋 Скопировать карту</button>
                </div>

                <button class="main-btn" onclick="confirmPayment()" style="background: var(--success); box-shadow: 0 4px 15px rgba(34,197,94,0.4);">Я оплатил(а)</button>
            </div>

            <!-- ЭКРАН 3: УСПЕХ -->
            <div id="screenWait" class="screen" style="text-align: center;">
                <div style="font-size: 40px; margin: 20px 0;">✅</div>
                <h3 style="margin: 0 0 8px 0;">Заявка отправлена!</h3>
                <p style="color: var(--text-muted); font-size: 13px; line-height: 1.5;">
                    Мы проверяем поступление средств. Уведомление об успешном переводе придет вам в этот чат.
                </p>
                <button class="main-btn" onclick="tg.close()" style="margin-top: 20px; background: var(--card-inner); border: 1px solid var(--accent); box-shadow: none;">Вернуться в чат</button>
            </div>
        </div>

        <!-- МОДАЛЬНОЕ ОКНО -->
        <div id="termsModal" class="modal-overlay">
            <div class="modal-content">
                <h3>Условия использования (Оферта)</h3>
                <p><b>1. Общие положения.</b> Koro Pay предоставляет услуги по содействию в P2P-переводах. Пользователь гарантирует легальное происхождение средств.</p>
                <p><b>2. Безопасность.</b> Запрещено использование сервиса в мошеннических целях. Перевод должен осуществляться исключительно с личных счетов.</p>
                <p><b>3. Ответственность.</b> Сервис не несет ответственности за переводы по ошибочно указанным реквизитам.</p>
                <button class="close-modal" onclick="closeModal()">Понятно</button>
            </div>
        </div>

        <script>
            let tg = window.Telegram.WebApp;
            tg.expand();

            let currentMultiplier = 135, currentCurr = 'UZS', enteredRub = 0, calculatedLocal = 0, currentOrderCode = '', timerInterval;

            window.onload = function() {{ calculateLocal(); }};

            function openModal(e) {{ e.preventDefault(); e.stopPropagation(); document.getElementById('termsModal').style.display = 'flex'; }}
            function closeModal() {{ document.getElementById('termsModal').style.display = 'none'; }}

            function calculateLocal() {{
                let val = document.getElementById('country').value.split('|');
                currentCurr = val[1]; currentMultiplier = parseFloat(val[2]);
                enteredRub = parseFloat(document.getElementById('amount').value) || 0;
                calculatedLocal = enteredRub * currentMultiplier;
                document.getElementById('totalLocal').textContent = (enteredRub > 0 ? calculatedLocal.toFixed(2) : '0.00') + ' ' + currentCurr;
            }}

            function copyCard() {{
                navigator.clipboard.writeText("{RECEIVE_CARD}".replace(/\\s+/g, ''));
                let btn = document.getElementById('copyCardBtn'); btn.textContent = '✅ Скопировано!';
                setTimeout(() => {{ btn.textContent = '📋 Скопировать карту'; }}, 2000);
            }}

            function copyComment() {{
                navigator.clipboard.writeText(currentOrderCode);
                let btn = document.getElementById('copyCommentBtn'); btn.textContent = '✅ Скопировано!';
                setTimeout(() => {{ btn.textContent = '📋 Скопировать комментарий'; }}, 2000);
            }}

            function startTimer(duration) {{
                let timer = duration, minutes, seconds;
                clearInterval(timerInterval);
                timerInterval = setInterval(function () {{
                    minutes = parseInt(timer / 60, 10); seconds = parseInt(timer % 60, 10);
                    minutes = minutes < 10 ? "0" + minutes : minutes; seconds = seconds < 10 ? "0" + seconds : seconds;
                    document.getElementById('timerDisplay').textContent = "Осталось времени: " + minutes + ":" + seconds;
                    if (--timer < 0) {{ clearInterval(timerInterval); alert('Время вышло.'); location.reload(); }}
                }}, 1000);
            }}

            async function submitForm() {{
                enteredRub = parseFloat(document.getElementById('amount').value) || 0;
                if (enteredRub <= 0 || enteredRub > 25000) {{ alert('Проверьте сумму перевода (лимит 25 000 ₽)!'); return; }}
                if (!document.getElementById('recName').value || !document.getElementById('recCard').value) {{ alert('Заполните данные получателя!'); return; }}
                if (!document.getElementById('termsCheck').checked) {{ alert('Необходимо согласиться с условиями оферты!'); return; }}

                currentOrderCode = 'KORO-' + Math.floor(1000 + Math.random() * 9000);
                document.getElementById('transferCommentText').textContent = currentOrderCode;
                document.getElementById('payRubSum').textContent = enteredRub + ' ₽';
                
                document.getElementById('screenForm').classList.remove('active');
                document.getElementById('screenPay').classList.add('active');
                startTimer(900);
            }}

            async function confirmPayment() {{
                let user = tg.initDataUnsafe?.user || {{}};
                clearInterval(timerInterval);
                try {{
                    let response = await fetch('/api/order', {{
                        method: 'POST', headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{
                            country: document.getElementById('country').value.split('|')[0],
                            rub_amount: enteredRub + ' ₽',
                            local_received: calculatedLocal.toFixed(2),
                            currency: currentCurr,
                            recipient_name: document.getElementById('recName').value,
                            recipient_card: document.getElementById('recCard').value,
                            transfer_comment: currentOrderCode,
                            username: user.username || 'Аноним', user_id: user.id || 0
                        }})
                    }});
                    let result = await response.json();
                    if (!response.ok) {{ alert(result.message || 'Ошибка обработки.'); location.reload(); return; }}
                    
                    document.getElementById('screenPay').classList.remove('active');
                    document.getElementById('screenWait').classList.add('active');
                }} catch (e) {{ alert('Ошибка связи с сервером.'); }}
            }}
        </script>
    </body>
    </html>
    """
  return web.Response(text=html_content, content_type="text/html")


async def main():
  init_db()
  app = web.Application()
  app.router.add_get("/", webapp_handler)
  app.router.add_post("/api/order", api_order_handler)
  runner = web.AppRunner(app)
  await runner.setup()
  site = web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 8080)))
  await site.start()
  
  asyncio.create_task(update_rates())
  
  logging.info(f"Защищенный сервер запущен...")
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())