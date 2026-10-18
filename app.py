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

EXCHANGE_RATES = {"UZS": 135.00, "TJS": 0.115, "KGS": 0.95, "AZN": 0.018}
COMMISSION_MARGIN = 0.95 

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# === ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ SQLite ===
def init_db():
    conn = sqlite3.connect('koropay.db')
    c = conn.cursor()
    # Таблица пользователей (учет страйков и банов)
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, username TEXT, strikes INTEGER DEFAULT 0, is_banned INTEGER DEFAULT 0)''')
    # Таблица переводов
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
    
    # Регистрируем пользователя в БД
    conn = sqlite3.connect('koropay.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    conn.close()

    user_data = get_user(user_id)
    if user_data and user_data[3] == 1:
        await message.answer("🚫 Ваш аккаунт заблокирован за нарушение правил сервиса (слишком много неоплаченных заявок).")
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

        tx_id = transfer_comment # Используем сгенерированный код как ID транзакции

        # Сохраняем транзакцию в БД
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
            f"💳 Карта получателя: <code>{recipient_card}</code>\n\n"
            f"👉 Проверьте поступление с комментарием '{tx_id}'."
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

    # Обновляем статус в БД
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

    # Обновляем статус и даем страйк
    conn = sqlite3.connect('koropay.db')
    c = conn.cursor()
    c.execute("UPDATE transfers SET status='REJECTED' WHERE tx_id=?", (tx_id,))
    conn.commit()
    conn.close()
    add_strike(target_user_id)

    await callback.message.edit_text(callback.message.text + f"\n\n❌ <b>ОТКЛОНЕН (ФЕЙК)</b>", parse_mode="HTML")
    try:
        await bot.send_message(target_user_id, f"❌ Ваш платеж <code>{tx_id}</code> не найден. Вы получили предупреждение.", parse_mode="HTML")
    except: pass
    await callback.answer("Отклонено!")


async def webapp_handler(request):
  html_content = f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Koro Pay</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            :root {{ --bg-color: #0c0d12; --card-bg: #151721; --card-inner: #1e2130; --accent: #8b5cf6; --text-main: #ffffff; --text-muted: #9ca3af; --border: rgba(139, 92, 246, 0.2); --success: #22c55e; }}
            body {{ background: var(--bg-color); color: var(--text-main); font-family: -apple-system, sans-serif; margin: 0; padding: 16px; display: flex; justify-content: center; }}
            .container {{ width: 100%; max-width: 400px; background: var(--card-bg); border: 1px solid var(--border); border-radius: 20px; padding: 20px; box-sizing: border-box; }}
            h2 {{ margin: 0 0 4px 0; text-align: center; }}
            .form-group {{ margin-bottom: 14px; }}
            label {{ font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 6px; text-transform: uppercase; }}
            input, select {{ width: 100%; padding: 12px; background: var(--card-inner); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; color: #fff; box-sizing: border-box; }}
            .calc-box {{ background: rgba(139,92,246,0.08); border: 1px dashed rgba(139,92,246,0.3); border-radius: 10px; padding: 12px; margin-bottom: 16px; display: flex; justify-content: space-between; }}
            button.main-btn {{ width: 100%; padding: 14px; background: linear-gradient(135deg, #a855f7 0%, #6366f1 100%); color: white; border: none; border-radius: 12px; font-size: 16px; font-weight: bold; cursor: pointer; }}
            .screen {{ display: none; }}
            .active {{ display: block; }}
            .req-box {{ background: var(--card-inner); border: 1px solid var(--border); border-radius: 12px; padding: 14px; margin: 12px 0; }}
            .copy-btn {{ background: rgba(139,92,246,0.2); color: #c084fc; padding: 8px; border: none; border-radius: 8px; width: 100%; margin-top: 8px; cursor: pointer; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div id="screenForm" class="screen active">
                <h2>Koro Pay</h2>
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
                    <label>Сумма (в рублях)</label>
                    <input type="number" id="amount" placeholder="Макс. 25 000 ₽" oninput="calculateLocal()">
                </div>
                <div class="calc-box">
                    <span>Получатель заберет:</span>
                    <span id="totalLocal" style="color:#c084fc; font-weight:bold;">0.00 UZS</span>
                </div>
                <div class="form-group"><input type="text" id="recName" placeholder="ФИО получателя"></div>
                <div class="form-group"><input type="text" id="recCard" placeholder="Номер карты"></div>
                <button class="main-btn" onclick="submitForm()">Продолжить</button>
            </div>

            <div id="screenPay" class="screen">
                <h2>Оплата</h2>
                <div class="req-box">
                    <div style="font-size: 11px; color: #9ca3af;">КОММЕНТАРИЙ К ПЕРЕВОДУ (ОБЯЗАТЕЛЬНО):</div>
                    <div id="transferCommentText" style="font-size: 18px; color: #f59e0b; font-weight:bold; margin-top:4px;"></div>
                    <button class="copy-btn" id="copyCommentBtn" onclick="copyComment()">📋 Скопировать</button>
                </div>
                <div class="req-box">
                    <div style="font-size: 11px; color: #9ca3af;">СУММА И РЕКВИЗИТЫ:</div>
                    <div id="payRubSum" style="font-size: 20px; color: #c084fc; font-weight:bold;">0 ₽</div>
                    <div style="font-size: 16px; margin-top: 8px;">{RECEIVE_BANK}</div>
                    <div style="font-size: 18px; font-weight: bold;">{RECEIVE_CARD}</div>
                    <button class="copy-btn" id="copyCardBtn" onclick="copyCard()">📋 Скопировать карту</button>
                </div>
                <button class="main-btn" onclick="confirmPayment()" style="background: #22c55e;">Я оплатил(а)</button>
            </div>
            
            <div id="screenWait" class="screen" style="text-align: center;">
                <div style="font-size: 40px; margin: 20px 0;">✅</div>
                <h3>Заявка отправлена!</h3>
                <button class="main-btn" onclick="tg.close()" style="margin-top: 20px;">Вернуться в чат</button>
            </div>
        </div>

        <script>
            let tg = window.Telegram.WebApp;
            tg.expand();
            let currentMultiplier = 135, currentCurr = 'UZS', enteredRub = 0, calculatedLocal = 0, currentOrderCode = '';
            
            window.onload = function() {{ calculateLocal(); }};

            function calculateLocal() {{
                let val = document.getElementById('country').value.split('|');
                currentCurr = val[1]; currentMultiplier = parseFloat(val[2]);
                enteredRub = parseFloat(document.getElementById('amount').value) || 0;
                calculatedLocal = enteredRub * currentMultiplier;
                document.getElementById('totalLocal').textContent = (enteredRub > 0 ? calculatedLocal.toFixed(2) : '0.00') + ' ' + currentCurr;
            }}

            function copyCard() {{ navigator.clipboard.writeText("{RECEIVE_CARD}".replace(/\\s+/g, '')); document.getElementById('copyCardBtn').textContent = '✅'; }}
            function copyComment() {{ navigator.clipboard.writeText(currentOrderCode); document.getElementById('copyCommentBtn').textContent = '✅'; }}

            function submitForm() {{
                enteredRub = parseFloat(document.getElementById('amount').value) || 0;
                if (enteredRub <= 0 || enteredRub > 25000 || !document.getElementById('recName').value || !document.getElementById('recCard').value) {{ alert('Проверьте данные!'); return; }}
                currentOrderCode = 'KORO-' + Math.floor(1000 + Math.random() * 9000);
                document.getElementById('transferCommentText').textContent = currentOrderCode;
                document.getElementById('payRubSum').textContent = enteredRub + ' ₽';
                document.getElementById('screenForm').classList.remove('active');
                document.getElementById('screenPay').classList.add('active');
            }}

            async function confirmPayment() {{
                let user = tg.initDataUnsafe?.user || {{}};
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
                    if (!response.ok) {{ alert('Ошибка. Возможно, аккаунт заблокирован.'); tg.close(); return; }}
                    document.getElementById('screenPay').classList.remove('active');
                    document.getElementById('screenWait').classList.add('active');
                }} catch (e) {{ alert('Ошибка связи.'); }}
            }}
        </script>
    </body>
    </html>
    """
  return web.Response(text=html_content, content_type="text/html")

async def main():
  init_db() # Создаем базу данных при старте
  app = web.Application()
  app.router.add_get("/", webapp_handler)
  app.router.add_post("/api/order", api_order_handler)
  runner = web.AppRunner(app)
  await runner.setup()
  site = web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 8080)))
  await site.start()
  asyncio.create_task(update_rates())
  await dp.start_polling(bot)

if __name__ == "__main__":
  asyncio.run(main())