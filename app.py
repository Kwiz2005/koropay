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
        inline_keyboard=[[InlineKeyboardButton(text="📱 Открыть Koro Pay", web_app=WebAppInfo(url=WEBAPP_URL))]]
    )
    await message.answer(
        "<b>🌐 Koro Pay — Международные переводы</b>\n\n"
        "Лимит перевода: до 25 000 ₽ за раз.\n"
        "<i>Нажмите кнопку ниже, чтобы войти в приложение.</i>",
        reply_markup=web_app_kb, parse_mode="HTML"
    )

# API для выдачи истории внутри Web App
async def api_history_handler(request):
    try:
        user_id = int(request.rel_url.query.get('user_id', 0))
        conn = sqlite3.connect('koropay.db')
        c = conn.cursor()
        c.execute("SELECT tx_id, country, rub_amount, local_amount, currency, status FROM transfers WHERE user_id=? ORDER BY ROWID DESC LIMIT 15", (user_id,))
        history = c.fetchall()
        conn.close()
        
        result = []
        for tx in history:
            result.append({
                "tx_id": tx[0], "country": tx[1], "rub": tx[2], 
                "local": tx[3], "currency": tx[4], "status": tx[5]
            })
        return web.json_response({"status": "success", "data": result})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=400)


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
            f"🚨 <b>Новый перевод!</b>\n\n"
            f"🆔 Транзакция: <code>{tx_id}</code>\n"
            f"👤 Клиент: @{user_name} (ID: <code>{user_id}</code>)\n"
            f"🇷🇺 Отправлено: <b>{rub_amount}</b>\n"
            f"💶 К выплате: <b>{local_received} {currency}</b>\n\n"
            f"💳 Карта получателя: <code>{recipient_card}</code>\n"
            f"👤 Имя получателя: <b>{recipient_name}</b>\n\n"
            f"👉 Проверьте {RECEIVE_BANK} ({RECEIVE_CARD}) с комментарием '{tx_id}'."
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
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>Koro Pay</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
        <style>
            :root {{
                --bg: #000000; --surface: #1C1C1E; --surface-hover: #2C2C2E;
                --primary: #0A84FF; --primary-grad: linear-gradient(135deg, #0A84FF 0%, #5E5CE6 100%);
                --text: #FFFFFF; --text-sec: #EBEBF599; --border: #38383A;
                --success: #30D158; --danger: #FF453A; --warning: #FF9F0A;
            }}
            * {{ box-sizing: border-box; -webkit-tap-highlight-color: transparent; }}
            body {{
                background: var(--bg); color: var(--text); font-family: 'Inter', sans-serif;
                margin: 0; padding: 0; display: flex; flex-direction: column; height: 100vh;
                overflow: hidden;
            }}
            
            /* Header */
            .header {{ padding: 20px 20px 10px; display: flex; justify-content: space-between; align-items: center; }}
            .header-title {{ font-size: 22px; font-weight: 700; }}
            .user-greeting {{ font-size: 13px; color: var(--text-sec); }}
            
            /* Main Content Area */
            .content {{ flex: 1; overflow-y: auto; padding: 10px 20px 80px; }}
            .screen {{ display: none; animation: fadeIn 0.3s ease; }}
            .screen.active {{ display: block; }}
            @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: translateY(0); }} }}

            /* Banking Cards & Forms */
            .card-panel {{ background: var(--surface); border-radius: 16px; padding: 16px; margin-bottom: 16px; border: 1px solid var(--border); }}
            .input-group {{ margin-bottom: 16px; }}
            .input-group:last-child {{ margin-bottom: 0; }}
            label {{ display: block; font-size: 12px; font-weight: 600; color: var(--text-sec); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; }}
            
            input, select {{
                width: 100%; padding: 14px; background: var(--bg); border: 1px solid var(--border);
                border-radius: 12px; color: var(--text); font-size: 16px; font-family: 'Inter', sans-serif;
                transition: border-color 0.2s; outline: none;
            }}
            input:focus, select:focus {{ border-color: var(--primary); }}
            
            /* Quick Amounts */
            .quick-amounts {{ display: flex; gap: 8px; margin-top: 10px; }}
            .quick-btn {{
                flex: 1; padding: 8px 0; background: var(--surface-hover); color: var(--text);
                border: none; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer;
            }}
            
            /* Receipt Details */
            .receipt-row {{ display: flex; justify-content: space-between; font-size: 14px; margin-bottom: 8px; color: var(--text-sec); }}
            .receipt-row.total {{ font-size: 18px; font-weight: 700; color: var(--text); margin-top: 12px; padding-top: 12px; border-top: 1px dashed var(--border); margin-bottom: 0; }}
            
            /* Buttons */
            .btn-primary {{
                width: 100%; padding: 16px; background: var(--primary-grad); color: #fff;
                border: none; border-radius: 14px; font-size: 16px; font-weight: 700;
                cursor: pointer; display: flex; justify-content: center; align-items: center;
                box-shadow: 0 4px 15px rgba(10, 132, 255, 0.3);
            }}
            .btn-copy {{
                background: var(--surface-hover); color: var(--primary); padding: 10px;
                border: none; border-radius: 10px; font-size: 14px; font-weight: 600; width: 100%; margin-top: 10px; cursor: pointer;
            }}

            /* Security & Terms */
            .checkbox-wrapper {{ display: flex; align-items: center; gap: 10px; font-size: 12px; color: var(--text-sec); margin-bottom: 16px; }}
            .checkbox-wrapper input {{ width: 20px; height: 20px; accent-color: var(--primary); }}
            .link {{ color: var(--primary); text-decoration: none; font-weight: 600; cursor: pointer; }}
            
            /* Bottom Navigation */
            .bottom-nav {{
                position: fixed; bottom: 0; left: 0; width: 100%; background: rgba(28, 28, 30, 0.95);
                backdrop-filter: blur(10px); border-top: 1px solid var(--border);
                display: flex; justify-content: space-around; padding: 10px 0 20px; z-index: 50;
            }}
            .nav-item {{ display: flex; flex-direction: column; align-items: center; color: var(--text-sec); font-size: 10px; cursor: pointer; }}
            .nav-item.active {{ color: var(--primary); }}
            .nav-icon {{ font-size: 20px; margin-bottom: 4px; }}
            
            /* History List */
            .history-card {{ display: flex; justify-content: space-between; align-items: center; padding: 14px 0; border-bottom: 1px solid var(--border); }}
            .history-card:last-child {{ border-bottom: none; padding-bottom: 0; }}
            .h-left .h-title {{ font-size: 15px; font-weight: 600; margin-bottom: 4px; }}
            .h-left .h-desc {{ font-size: 12px; color: var(--text-sec); }}
            .h-right {{ text-align: right; }}
            .h-right .h-amount {{ font-size: 15px; font-weight: 700; margin-bottom: 4px; }}
            .badge {{ font-size: 10px; font-weight: 700; padding: 4px 8px; border-radius: 6px; display: inline-block; }}
            .b-pending {{ background: rgba(255, 159, 10, 0.15); color: var(--warning); }}
            .b-success {{ background: rgba(48, 209, 88, 0.15); color: var(--success); }}
            .b-reject {{ background: rgba(255, 69, 58, 0.15); color: var(--danger); }}

            /* Modals */
            .modal {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 100; justify-content: center; align-items: flex-end; }}
            .modal-content {{ background: var(--surface); width: 100%; border-radius: 20px 20px 0 0; padding: 24px; max-height: 80vh; overflow-y: auto; animation: slideUp 0.3s; }}
            @keyframes slideUp {{ from {{ transform: translateY(100%); }} to {{ transform: translateY(0); }} }}
            .modal-close {{ width: 40px; height: 5px; background: var(--border); border-radius: 3px; margin: 0 auto 20px; }}
            .legal-text h3 {{ margin-top: 0; font-size: 18px; }}
            .legal-text p {{ font-size: 13px; color: var(--text-sec); line-height: 1.6; margin-bottom: 12px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <div>
                <div class="user-greeting" id="userGreeting">Добрый день</div>
                <div class="header-title">Koro Pay</div>
            </div>
            <div style="width: 40px; height: 40px; border-radius: 20px; background: var(--surface-hover); display: flex; justify-content: center; align-items: center; font-size: 20px;">
                👤
            </div>
        </div>

        <div class="content">
            <!-- Вкладка 1: ПЕРЕВОД -->
            <div id="tab-transfer" class="screen active">
                <div class="card-panel">
                    <div class="input-group">
                        <label>Направление перевода</label>
                        <select id="country" onchange="calculateParams()">
                            <option value="Uzbekistan|UZS|{EXCHANGE_RATES['UZS']}">🇺🇿 Узбекистан (UZS)</option>
                            <option value="Tajikistan|TJS|{EXCHANGE_RATES['TJS']}">🇹🇯 Таджикистан (TJS)</option>
                            <option value="Kyrgyzstan|KGS|{EXCHANGE_RATES['KGS']}">🇰🇬 Киргизия (KGS)</option>
                            <option value="Azerbaijan|AZN|{EXCHANGE_RATES['AZN']}">🇦🇿 Азербайджан (AZN)</option>
                        </select>
                    </div>
                    <div class="input-group">
                        <label>Сумма списания (₽)</label>
                        <input type="number" id="amount" placeholder="0" oninput="calculateParams()">
                        <div class="quick-amounts">
                            <button class="quick-btn" onclick="setAmount(1000)">1 000</button>
                            <button class="quick-btn" onclick="setAmount(5000)">5 000</button>
                            <button class="quick-btn" onclick="setAmount(15000)">15 000</button>
                            <button class="quick-btn" onclick="setAmount(25000)">MAX</button>
                        </div>
                    </div>
                </div>

                <div class="card-panel">
                    <div class="input-group">
                        <label>Карта получателя</label>
                        <input type="tel" id="recCard" placeholder="0000 0000 0000 0000" maxlength="19" oninput="formatCard(this)">
                    </div>
                    <div class="input-group">
                        <label>ФИО получателя</label>
                        <input type="text" id="recName" placeholder="Иванов Иван Иванович">
                    </div>
                </div>

                <div class="card-panel">
                    <div class="receipt-row">
                        <span>Текущий курс</span>
                        <span id="rateDisplay">0.00</span>
                    </div>
                    <div class="receipt-row">
                        <span>Комиссия сервиса</span>
                        <span style="color: var(--success);">0 ₽</span>
                    </div>
                    <div class="receipt-row total">
                        <span>К зачислению</span>
                        <span id="totalLocal">0.00 UZS</span>
                    </div>
                </div>

                <div class="checkbox-wrapper">
                    <input type="checkbox" id="termsCheck">
                    <label for="termsCheck" style="margin: 0; text-transform: none; letter-spacing: 0;">
                        Я подтверждаю легальность средств и согласен с <span class="link" onclick="openModal('ofertaModal')">Условиями оферты</span>.
                    </label>
                </div>

                <button class="btn-primary" onclick="initiateTransfer()">Продолжить</button>
            </div>

            <!-- Вкладка 2: ОПЛАТА (ШЛЮЗ) -->
            <div id="tab-payment" class="screen">
                <div style="text-align: center; margin-bottom: 20px;">
                    <div style="font-size: 40px; margin-bottom: 10px;">🛡</div>
                    <h2 style="margin:0;">Оплата перевода</h2>
                    <div style="color: var(--warning); font-weight: 700; margin-top: 10px;" id="timerDisplay">15:00</div>
                </div>

                <div class="card-panel">
                    <label>Сумма к оплате</label>
                    <div id="payRubSum" style="font-size: 28px; font-weight: 800; color: var(--primary);">0 ₽</div>
                </div>

                <div class="card-panel">
                    <label>Реквизиты для перевода ({RECEIVE_BANK})</label>
                    <div style="font-size: 20px; font-weight: 700; letter-spacing: 1px; margin-bottom: 4px;">{RECEIVE_CARD}</div>
                    <div style="font-size: 13px; color: var(--text-sec);">{RECEIVE_HOLDER}</div>
                    <button class="btn-copy" id="btnCopyCard" onclick="copyText('{RECEIVE_CARD}', 'btnCopyCard')">Скопировать номер карты</button>
                </div>

                <div class="card-panel" style="border-color: var(--warning);">
                    <label style="color: var(--warning);">Комментарий к переводу (Обязательно!)</label>
                    <div id="transferCommentText" style="font-size: 20px; font-weight: 700;">KORO-0000</div>
                    <button class="btn-copy" id="btnCopyComment" onclick="copyText(currentOrderCode, 'btnCopyComment')" style="color: var(--warning);">Скопировать комментарий</button>
                </div>

                <button class="btn-primary" onclick="confirmPayment()" style="background: var(--success); box-shadow: 0 4px 15px rgba(48, 209, 88, 0.3);">Я перевел(а) деньги</button>
            </div>

            <!-- Вкладка 3: ИСТОРИЯ -->
            <div id="tab-history" class="screen">
                <h2 style="margin-bottom: 20px;">История операций</h2>
                <div class="card-panel" id="historyContainer">
                    <div style="text-align:center; padding: 20px; color: var(--text-sec);">⏳ Загрузка...</div>
                </div>
            </div>

            <!-- Вкладка 4: ПРОФИЛЬ -->
            <div id="tab-profile" class="screen">
                <h2 style="margin-bottom: 20px;">Профиль</h2>
                <div class="card-panel">
                    <div class="receipt-row" style="padding: 12px 0; border-bottom: 1px solid var(--border); margin:0; cursor:pointer;" onclick="openModal('ofertaModal')">
                        <span style="font-weight:600; color:var(--text);">📄 Условия оферты</span>
                        <span>›</span>
                    </div>
                    <div class="receipt-row" style="padding: 12px 0; border-bottom: 1px solid var(--border); margin:0; cursor:pointer;">
                        <span style="font-weight:600; color:var(--text);">🎧 Поддержка</span>
                        <span>›</span>
                    </div>
                    <div class="receipt-row" style="padding: 12px 0; margin:0;">
                        <span style="font-weight:600; color:var(--text);">Версия приложения</span>
                        <span>2.0.1</span>
                    </div>
                </div>
            </div>

            <!-- Экран успеха -->
            <div id="tab-success" class="screen" style="text-align: center; padding-top: 60px;">
                <div style="font-size: 60px; margin-bottom: 20px;">✅</div>
                <h2 style="margin-bottom: 10px;">Средства в обработке</h2>
                <p style="color: var(--text-sec); font-size: 14px; line-height: 1.5; margin-bottom: 30px;">Мы проверяем ваш платеж. Уведомление о зачислении придет в чат с ботом.</p>
                <button class="btn-primary" onclick="tg.close()">Вернуться в Telegram</button>
            </div>
        </div>

        <!-- Навигация -->
        <div class="bottom-nav" id="bottomNav">
            <div class="nav-item active" onclick="switchTab('tab-transfer', this)">
                <div class="nav-icon">💸</div>
                <div>Перевод</div>
            </div>
            <div class="nav-item" onclick="switchTab('tab-history', this); loadHistory();">
                <div class="nav-icon">🕒</div>
                <div>История</div>
            </div>
            <div class="nav-item" onclick="switchTab('tab-profile', this)">
                <div class="nav-icon">⚙️</div>
                <div>Профиль</div>
            </div>
        </div>

        <!-- Модальное окно ОФЕРТЫ -->
        <div id="ofertaModal" class="modal" onclick="if(event.target==this) closeModal('ofertaModal')">
            <div class="modal-content legal-text">
                <div class="modal-close"></div>
                <h3>Договор-оферта на оказание услуг P2P-переводов</h3>
                <p><b>1. Предмет соглашения.</b> Настоящая Оферта является официальным предложением сервиса Koro Pay (далее — «Сервис») по предоставлению информационно-технологического шлюза для осуществления международных P2P переводов.</p>
                <p><b>2. Противодействие мошенничеству (AML).</b> Пользователь гарантирует легальное происхождение переводимых средств. Строго запрещено использование карт третьих лиц. При выявлении подозрительных операций Сервис вправе заморозить заявку и запросить верификацию (KYC).</p>
                <p><b>3. Финансовые условия.</b> Расчетный курс фиксируется в момент оформления заявки сроком на 15 минут. Комиссия Сервиса уже включена в отображаемый курс конвертации.</p>
                <p><b>4. Порядок исполнения и возвраты.</b> Обязательства Сервиса считаются выполненными в момент отправки средств по указанным Пользователем реквизитам. Возврат средств после успешной отправки в иностранный банк невозможен.</p>
                <p><b>5. Ответственность.</b> Сервис не несет финансовой ответственности за ошибки, допущенные Пользователем при вводе номера карты или ФИО получателя.</p>
                <button class="btn-primary" style="margin-top: 20px;" onclick="closeModal('ofertaModal')">Ознакомлен</button>
            </div>
        </div>

        <script>
            let tg = window.Telegram.WebApp;
            tg.expand();
            tg.ready();

            let currentMultiplier = 135, currentCurr = 'UZS', enteredRub = 0, calculatedLocal = 0;
            let currentOrderCode = '', timerInterval;

            // Установка имени пользователя
            window.onload = function() {{
                let user = tg.initDataUnsafe?.user;
                if(user && user.first_name) {{
                    document.getElementById('userGreeting').textContent = 'Добрый день, ' + user.first_name;
                }}
                calculateParams();
            }};

            // Вибрация
            function haptic() {{
                if (tg.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
            }}

            // Навигация
            function switchTab(tabId, el) {{
                haptic();
                document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
                document.getElementById(tabId).classList.add('active');
                
                if(el) {{
                    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
                    el.classList.add('active');
                }}
            }}

            // Модалки
            function openModal(id) {{ haptic(); document.getElementById(id).style.display = 'flex'; }}
            function closeModal(id) {{ haptic(); document.getElementById(id).style.display = 'none'; }}

            // Форматирование карты (пробелы каждые 4 цифры)
            function formatCard(input) {{
                let val = input.value.replace(/\\D/g, '');
                let formatted = val.match(/.{{1,4}}/g)?.join(' ') || '';
                input.value = formatted;
            }}

            // Быстрые суммы
            function setAmount(val) {{
                haptic();
                document.getElementById('amount').value = val;
                calculateParams();
            }}

            // Расчеты
            function calculateParams() {{
                let val = document.getElementById('country').value.split('|');
                currentCurr = val[1]; 
                currentMultiplier = parseFloat(val[2]);
                
                document.getElementById('rateDisplay').textContent = `1 ₽ = ${{currentMultiplier.toFixed(2)}} ${{currentCurr}}`;
                
                enteredRub = parseFloat(document.getElementById('amount').value) || 0;
                calculatedLocal = enteredRub * currentMultiplier;
                
                let displayVal = enteredRub > 0 ? calculatedLocal.toLocaleString('ru-RU', {{minimumFractionDigits: 2, maximumFractionDigits: 2}}) : '0.00';
                document.getElementById('totalLocal').textContent = displayVal + ' ' + currentCurr;
            }}

            // Копирование
            function copyText(text, btnId) {{
                haptic();
                navigator.clipboard.writeText(text.replace(/\\s+/g, ''));
                let btn = document.getElementById(btnId);
                let origText = btn.textContent;
                btn.textContent = '✅ Скопировано!';
                setTimeout(() => {{ btn.textContent = origText; }}, 2000);
            }}

            // Загрузка Истории
            async function loadHistory() {{
                let user_id = tg.initDataUnsafe?.user?.id || 0;
                let container = document.getElementById('historyContainer');
                try {{
                    let response = await fetch('/api/history?user_id=' + user_id);
                    let res = await response.json();
                    
                    if(res.data.length === 0) {{
                        container.innerHTML = '<div style="text-align:center; padding: 20px; color: var(--text-sec);">Список операций пуст</div>';
                        return;
                    }}

                    container.innerHTML = '';
                    res.data.forEach(tx => {{
                        let bClass = tx.status === 'SUCCESS' ? 'b-success' : (tx.status === 'REJECTED' ? 'b-reject' : 'b-pending');
                        let bText = tx.status === 'SUCCESS' ? 'Успешно' : (tx.status === 'REJECTED' ? 'Отклонено' : 'В обработке');
                        
                        container.innerHTML += `
                            <div class="history-card">
                                <div class="h-left">
                                    <div class="h-title">${{tx.country}}</div>
                                    <div class="h-desc">ID: ${{tx.tx_id}}</div>
                                </div>
                                <div class="h-right">
                                    <div class="h-amount">${{tx.rub}} ₽</div>
                                    <div class="badge ${{bClass}}">${{bText}}</div>
                                </div>
                            </div>
                        `;
                    }});
                }} catch(e) {{
                    container.innerHTML = '<div style="text-align:center; padding: 20px; color: var(--danger);">Ошибка загрузки</div>';
                }}
            }}

            // Таймер
            function startTimer(duration) {{
                let timer = duration, minutes, seconds;
                clearInterval(timerInterval);
                timerInterval = setInterval(function () {{
                    minutes = parseInt(timer / 60, 10); seconds = parseInt(timer % 60, 10);
                    minutes = minutes < 10 ? "0" + minutes : minutes; seconds = seconds < 10 ? "0" + seconds : seconds;
                    document.getElementById('timerDisplay').textContent = minutes + ":" + seconds;
                    if (--timer < 0) {{ clearInterval(timerInterval); alert('Время сессии истекло.'); location.reload(); }}
                }}, 1000);
            }}

            // Создание заявки
            async function initiateTransfer() {{
                haptic();
                enteredRub = parseFloat(document.getElementById('amount').value) || 0;
                let card = document.getElementById('recCard').value.replace(/\\s+/g, '');
                
                if (enteredRub <= 0 || enteredRub > 25000) {{ tg.showAlert('Лимит перевода от 1 до 25 000 ₽'); return; }}
                if (card.length < 16) {{ tg.showAlert('Проверьте номер карты получателя'); return; }}
                if (!document.getElementById('recName').value) {{ tg.showAlert('Укажите ФИО получателя'); return; }}
                if (!document.getElementById('termsCheck').checked) {{ tg.showAlert('Необходимо согласиться с Офертой'); return; }}

                currentOrderCode = 'KORO-' + Math.floor(1000 + Math.random() * 9000);
                document.getElementById('transferCommentText').textContent = currentOrderCode;
                document.getElementById('payRubSum').textContent = enteredRub.toLocaleString('ru-RU') + ' ₽';
                
                document.getElementById('bottomNav').style.display = 'none'; // Прячем меню
                switchTab('tab-payment', null);
                startTimer(900);
            }}

            // Подтверждение оплаты
            async function confirmPayment() {{
                haptic();
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
                    if (!response.ok) {{ tg.showAlert(result.message || 'Ошибка сервера.'); location.reload(); return; }}
                    
                    switchTab('tab-success', null);
                }} catch (e) {{ tg.showAlert('Ошибка связи с сервером.'); }}
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
  app.router.add_get("/api/history", api_history_handler)
  runner = web.AppRunner(app)
  await runner.setup()
  site = web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 8080)))
  await site.start()
  
  asyncio.create_task(update_rates())
  
  logging.info(f"Сервер Koro Pay запущен...")
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())