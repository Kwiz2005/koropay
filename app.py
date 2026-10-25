import asyncio
import json
import logging
import os
import random
import time
import hmac
import hashlib
from urllib.parse import parse_qsl
import csv
import aiohttp
import aiosqlite
import urllib.request
from datetime import datetime
from io import BytesIO, StringIO
from PIL import Image, ImageDraw, ImageFont

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
    BufferedInputFile,
    FSInputFile
)
from aiohttp import web

# === НАСТРОЙКИ СЕРВЕРА ===
TOKEN = "8639644231:AAGNysKoCaTQyqg0pvPEXUxgOH5nJgG-pAk"
ADMIN_CHAT_ID = 6084347801
WEBAPP_URL = "https://koropay-en5x.onrender.com"
CRYPTO_PAY_TOKEN = "659313:AA4ny26j7kzZSueEiwPXYimHuTfwyfc14e1"
# =========================

RECEIVE_BANK = "Озон Банк"
RECEIVE_HOLDER = "Mirelem Ismailzade"

EXCHANGE_RATES = {
    "UZS": 135.00, "TJS": 0.115, "KGS": 0.95, "AZN": 0.018,
    "KZT": 5.15, "AMD": 4.15, "GEL": 0.028, "MDL": 0.18,
    "EUR": 0.0095, "USD": 0.01
}
COMMISSION_MARGIN = 0.95 

user_cooldowns = {}
api_ip_cooldowns = {}
active_crypto_invoices = {}

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- ВАЛИДАЦИЯ ТЕЛЕГРАМ (БЕЗОПАСНОСТЬ) ---
def validate_webapp_data(init_data: str, bot_token: str) -> bool:
    try:
        parsed_data = dict(parse_qsl(init_data))
        if 'hash' not in parsed_data: return False
        hash_val = parsed_data.pop('hash')
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        calc_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        return calc_hash == hash_val
    except Exception: return False

# --- АСИНХРОННАЯ БАЗА ДАННЫХ (AIOSQLITE) ---
async def init_db():
    async with aiosqlite.connect('koropay.db') as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users 
                     (user_id INTEGER PRIMARY KEY, username TEXT, strikes INTEGER DEFAULT 0, is_banned INTEGER DEFAULT 0, referrer_id INTEGER, bonus_balance REAL DEFAULT 0.0)''')
        
        try: await db.execute("ALTER TABLE users ADD COLUMN referrer_id INTEGER")
        except: pass
        try: await db.execute("ALTER TABLE users ADD COLUMN bonus_balance REAL DEFAULT 0.0")
        except: pass

        await db.execute('''CREATE TABLE IF NOT EXISTS transfers 
                     (tx_id TEXT PRIMARY KEY, user_id INTEGER, country TEXT, rub_amount TEXT, local_amount TEXT, currency TEXT, status TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        try: await db.execute("ALTER TABLE transfers ADD COLUMN bonus_used REAL DEFAULT 0.0")
        except: pass
        try: await db.execute("ALTER TABLE transfers ADD COLUMN pay_method TEXT DEFAULT 'MANUAL'")
        except: pass

        await db.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('receive_card', '2200 3204 4647 4787')")
        await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect('koropay.db') as db:
        async with db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as cursor: return await cursor.fetchone()

async def add_strike(user_id):
    async with aiosqlite.connect('koropay.db') as db:
        await db.execute("UPDATE users SET strikes = strikes + 1 WHERE user_id=?", (user_id,))
        await db.execute("UPDATE users SET is_banned = 1 WHERE user_id=? AND strikes >= 3", (user_id,))
        await db.commit()

async def get_active_card():
    async with aiosqlite.connect('koropay.db') as db:
        async with db.execute("SELECT value FROM settings WHERE key='receive_card'") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else "2200 3204 4647 4787"

# --- ФОНОВЫЕ ЗАДАЧИ ---
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
                            for cur in EXCHANGE_RATES.keys():
                                if cur in rates: EXCHANGE_RATES[cur] = rates[cur] * COMMISSION_MARGIN
        except Exception: pass
        await asyncio.sleep(3600)

def generate_receipt_image(tx_id, rub, local, currency, name, bank, card):
    font_path = "Roboto-Medium.ttf"
    if not os.path.exists(font_path): urllib.request.urlretrieve("https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Medium.ttf", font_path)
    font_value = ImageFont.truetype(font_path, 18)
    font_label = ImageFont.truetype(font_path, 16)
    font_small = ImageFont.truetype(font_path, 14)
    img = Image.new('RGB', (600, 750), color='#05050C')
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([(20, 20), (580, 730)], radius=24, fill='#121322', outline='#1C1D33', width=2)
    
    try:
        logo = Image.open("logo.png").convert("RGBA")
        logo.thumbnail((80, 80))
        img.paste(logo, (260, 50), logo)
    except:
        font_logo = ImageFont.truetype(font_path, 36)
        draw.text((300, 90), "Koro Pay", font=font_logo, fill='#9667E0', anchor="mm")

    draw.text((300, 160), "ОФИЦИАЛЬНЫЙ ЧЕК ПЕРЕВОДА", font=font_small, fill='#8A8E9E', anchor="mm")
    draw.line((60, 190, 540, 190), fill='#1C1D33', width=2)

    y, spacing = 220, 48 
    details = [
        ("Статус:", "УСПЕШНО (ДОСТАВЛЕН)", '#30D158'), ("Код транзакции:", tx_id, '#FFFFFF'),
        ("Дата и время:", datetime.now().strftime("%d.%m.%Y %H:%M"), '#FFFFFF'),
        ("Сумма списания:", f"{rub}", '#FFFFFF'), ("Сумма зачисления:", f"{local} {currency}", '#7C83FD'),
        ("Банк получателя:", bank, '#FFFFFF'), ("Получатель:", name.title(), '#FFFFFF'), ("Счет / Карта:", card, '#FFFFFF')
    ]
    for label, val, color in details:
        draw.text((60, y), label, font=font_label, fill='#8A8E9E')
        draw.text((540, y), val, font=font_value, fill=color, anchor="ra")
        y += spacing

    draw.line((60, y + 10, 540, y + 10), fill='#1C1D33', width=2)
    draw.text((300, y + 45), "Платежи. Переводы. Больше.", font=font_small, fill='#8A8E9E', anchor="mm")
    bio = BytesIO()
    img.save(bio, 'PNG')
    bio.seek(0)
    return bio

async def execute_capitalist_payout(card_number, amount, currency, tx_id):
    API_KEY = "Y8ynGmekbgaSTxEqM2mvgGd9XxWJeafU"
    API_SECRET = "PHmGJkeeM1TpWhJrGzYHt66wM5Z9fPga"
    auth_url = "https://api.capitalist.net/api/v1/token"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(auth_url, json={"login": API_KEY, "password": API_SECRET}) as auth_resp:
                auth_result = await auth_resp.json()
                if auth_resp.status != 200 or "data" not in auth_result: return False
                token = auth_result["data"]["token"]
                
            headers = {"Authorization": f"Bearer {token}"}
            payout_payload = {"account_type": "card", "account": card_number, "amount": amount, "currency": currency, "comment": f"Koro Pay {tx_id}"}
            async with session.post("https://api.capitalist.net/api/v1/payout", json=payout_payload, headers=headers) as payout_resp:
                payout_result = await payout_resp.json()
                if payout_resp.status == 200 and payout_result.get("code") == 0: return True
                return False
        except: return False

# --- BOT HANDLERS & CRM ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "Аноним"
    args = message.text.split()
    referrer_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
    
    async with aiosqlite.connect('koropay.db') as db:
        async with db.execute("SELECT user_id, is_banned FROM users WHERE user_id=?", (user_id,)) as cursor:
            existing_user = await cursor.fetchone()
            
        if not existing_user:
            if referrer_id and referrer_id != user_id:
                await db.execute("INSERT INTO users (user_id, username, referrer_id, bonus_balance) VALUES (?, ?, ?, ?)", (user_id, username, referrer_id, 0.0))
                try: await bot.send_message(referrer_id, f"🎉 <b>Новый реферал!</b>\nК сервису присоединился @{username}. Вы получите 50 ₽ после его первого перевода.", parse_mode="HTML")
                except: pass
            else: await db.execute("INSERT INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
            await db.commit()
        elif existing_user[1] == 1:
            return await message.answer("🚫 Ваш аккаунт заблокирован за нарушение правил сервиса.")

    web_app_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📱 Открыть Koro Pay", web_app=WebAppInfo(url=WEBAPP_URL))]])
    await message.answer("<b>🌐 Koro Pay — Международные переводы</b>\n\nЛимит перевода: до 25 000 ₽ за раз.\n<i>Нажмите кнопку ниже, чтобы войти.</i>", reply_markup=web_app_kb, parse_mode="HTML")

@dp.message(Command("setcard"))
async def cmd_setcard(message: types.Message):
    if message.from_user.id != ADMIN_CHAT_ID: return
    new_card = message.text.replace("/setcard", "").strip()
    if not new_card:
        await message.answer("Использование: /setcard 1111 2222 3333 4444")
        return
    async with aiosqlite.connect('koropay.db') as db:
        await db.execute("UPDATE settings SET value=? WHERE key='receive_card'", (new_card,))
        await db.commit()
    await message.answer(f"✅ Реквизиты обновлены:\n<code>{new_card}</code>", parse_mode="HTML")

@dp.message(Command("user"))
async def cmd_user(message: types.Message):
    if message.from_user.id != ADMIN_CHAT_ID: return
    try:
        target_id = int(message.text.split()[1])
        async with aiosqlite.connect('koropay.db') as db:
            async with db.execute("SELECT username, strikes, is_banned, bonus_balance, referrer_id FROM users WHERE user_id=?", (target_id,)) as cursor:
                u_data = await cursor.fetchone()
        if not u_data: return await message.answer("Пользователь не найден.")
            
        async with aiosqlite.connect('koropay.db') as db:
            async with db.execute("SELECT COUNT(*), status, SUM(CAST(REPLACE(rub_amount, ' ₽', '') AS REAL)) FROM transfers WHERE user_id=? GROUP BY status", (target_id,)) as cursor:
                stats = await cursor.fetchall()
                
        stat_text, ltv = "", 0.0
        for s in stats:
            stat_text += f"{s[1]}: {s[0]} шт.\n"
            if s[1] == 'SUCCESS': ltv = s[2] or 0.0
            
        ban_status = "ДА 🔴" if u_data[2] else "НЕТ 🟢"
        ref_text = f"Приглашен: {u_data[4]}" if u_data[4] else "Органика"
        await message.answer(f"👤 <b>CRM Досье:</b> <code>{target_id}</code> (@{u_data[0]})\nБан: {ban_status} | Страйков: {u_data[1]}/3\n🔗 Источник: {ref_text}\n🎁 <b>Бонусы:</b> {u_data[3]} ₽\n💎 <b>LTV:</b> {ltv:,.2f} ₽\n\n<b>Статистика:</b>\n{stat_text if stat_text else 'Нет операций'}", parse_mode="HTML")
    except: await message.answer("Использование: /user 123456789")

@dp.message(Command("export"))
async def cmd_export(message: types.Message):
    if message.from_user.id != ADMIN_CHAT_ID: return
    csv_file = StringIO()
    writer = csv.writer(csv_file)
    writer.writerow(["TX_ID", "USER_ID", "COUNTRY", "RUB", "LOCAL", "CURRENCY", "STATUS", "DATE", "BONUS_USED", "METHOD"])
    async with aiosqlite.connect('koropay.db') as db:
        async with db.execute("SELECT tx_id, user_id, country, rub_amount, local_amount, currency, status, created_at, bonus_used, pay_method FROM transfers ORDER BY ROWID DESC") as cursor:
            for row in await cursor.fetchall(): writer.writerow(row)
    file = BufferedInputFile(BytesIO(csv_file.getvalue().encode('utf-8')).getvalue(), filename=f"KoroPay_Export_{datetime.now().strftime('%Y%m%d')}.csv")
    await message.answer_document(document=file, caption="📊 Реестр всех переводов выгружен.")

# --- API ШЛЮЗЫ ---
async def api_profile_handler(request):
    try:
        user_id, init_data = int(request.rel_url.query.get('user_id', 0)), request.rel_url.query.get('initData', '')
        if not validate_webapp_data(init_data, TOKEN): return web.json_response({"status": "error"}, status=403)
        async with aiosqlite.connect('koropay.db') as db:
            async with db.execute("SELECT bonus_balance FROM users WHERE user_id=?", (user_id,)) as cursor: row = await cursor.fetchone()
        return web.json_response({"status": "success", "balance": row[0] if row else 0.0})
    except: return web.json_response({"status": "error"}, status=400)

async def api_history_handler(request):
    try:
        user_id, init_data = int(request.rel_url.query.get('user_id', 0)), request.rel_url.query.get('initData', '')
        if not validate_webapp_data(init_data, TOKEN): return web.json_response({"status": "error"}, status=403)
        async with aiosqlite.connect('koropay.db') as db:
            async with db.execute("SELECT tx_id, country, rub_amount, local_amount, currency, status FROM transfers WHERE user_id=? ORDER BY ROWID DESC LIMIT 15", (user_id,)) as cursor:
                history = await cursor.fetchall()
        result = [{"tx_id": tx[0], "country": tx[1], "rub": tx[2], "local": tx[3], "currency": tx[4], "status": tx[5]} for tx in history]
        return web.json_response({"status": "success", "data": result})
    except Exception as e: return web.json_response({"status": "error", "message": str(e)}, status=400)

async def api_request_receipt(request):
    try:
        data = await request.json()
        if not validate_webapp_data(data.get("initData", ""), TOKEN): return web.json_response({"status": "error"}, status=403)
        tx_id, user_id = data.get("tx_id"), data.get("user_id")
        
        async with aiosqlite.connect('koropay.db') as db:
            async with db.execute("SELECT rub_amount, local_amount, currency FROM transfers WHERE tx_id=? AND status='SUCCESS'", (tx_id,)) as cursor:
                tx_data = await cursor.fetchone()
                
        if not tx_data: return web.json_response({"status": "error", "message": "Чек недоступен или транзакция не успешна"})
        
        image_buffer = generate_receipt_image(tx_id, tx_data[0], tx_data[1], tx_data[2], "Клиент Сервиса", "Банк Получателя", "**** **** **** ****")
        photo = BufferedInputFile(image_buffer.getvalue(), filename=f"KoroPay_{tx_id}.png")
        await bot.send_photo(user_id, photo=photo, caption=f"📄 <b>Дубликат чека</b>\n🆔 <code>{tx_id}</code>", parse_mode="HTML")
        return web.json_response({"status": "success"})
    except Exception: return web.json_response({"status": "error"}, status=400)

async def api_support_handler(request):
    try:
        data = await request.json()
        if not validate_webapp_data(data.get("initData", ""), TOKEN): return web.json_response({"status": "error"}, status=403)
        user_id, username, message_text = data.get("user_id"), data.get("username", "Аноним"), data.get("message", "")

        support_msg = (
            f"🆘 <b>ТИКЕТ В ПОДДЕРЖКУ (ИЗ WEBAPP)</b>\n\n"
            f"👤 От: @{username} (ID: <code>{user_id}</code>)\n\n"
            f"📝 <b>Сообщение клиента:</b>\n{message_text}"
        )
        if ADMIN_CHAT_ID: await bot.send_message(ADMIN_CHAT_ID, support_msg, parse_mode="HTML")
        return web.json_response({"status": "success"})
    except Exception: return web.json_response({"status": "error"}, status=400)

async def api_crypto_create(request):
    try:
        data = await request.json()
        if not validate_webapp_data(data.get("initData", ""), TOKEN): return web.json_response({"status": "error"}, status=403)
        
        amount_rub = float(data.get("rub_amount", 0))
        tx_id = data.get("tx_id")
        usdt_amount = round(amount_rub / 100, 2)
        
        headers = {"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN}
        payload = {"asset": "USDT", "amount": usdt_amount, "description": f"Koro Pay {tx_id}", "payload": tx_id}
        
        async with aiohttp.ClientSession() as session:
            async with session.post("https://pay.crypt.bot/api/createInvoice", json=payload, headers=headers) as resp:
                result = await resp.json()
                if result.get("ok"):
                    inv = result['result']
                    active_crypto_invoices[inv['invoice_id']] = tx_id
                    return web.json_response({"status": "success", "pay_url": inv['pay_url'], "invoice_id": inv['invoice_id']})
                return web.json_response({"status": "error", "message": "Токен CryptoBot не настроен администратором."})
    except Exception as e: return web.json_response({"status": "error", "message": str(e)})

async def api_crypto_check(request):
    try:
        data = await request.json()
        invoice_id = data.get("invoice_id")
        tx_id = data.get("tx_id")
        
        headers = {"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN}
        async with aiohttp.ClientSession() as session:
            async with session.post("https://pay.crypt.bot/api/getInvoices", json={"invoice_ids": invoice_id}, headers=headers) as resp:
                result = await resp.json()
                if result.get("ok") and len(result['result']['items']) > 0:
                    status = result['result']['items'][0]['status']
                    if status == 'paid':
                        async with aiosqlite.connect('koropay.db') as db:
                            async with db.execute("SELECT user_id, rub_amount, local_amount, currency, status FROM transfers WHERE tx_id=?", (tx_id,)) as cursor:
                                tx_data = await cursor.fetchone()
                        
                        if tx_data and tx_data[4] == 'PENDING':
                            await execute_capitalist_payout("**** AUTOMATED ****", tx_data[2], tx_data[3], tx_id)
                            async with aiosqlite.connect('koropay.db') as db:
                                await db.execute("UPDATE transfers SET status='SUCCESS', pay_method='CRYPTO' WHERE tx_id=?", (tx_id,))
                                await db.commit()
                            
                            try: await bot.send_message(tx_data[0], f"🎉 <b>Крипто-платеж подтвержден!</b>\nДеньги автоматически отправлены получателю. 🆔 <code>{tx_id}</code>", parse_mode="HTML")
                            except: pass
                        return web.json_response({"status": "paid"})
                return web.json_response({"status": "pending"})
    except: return web.json_response({"status": "error"})

async def api_order_handler(request):
    try:
        data = await request.json()
        if not validate_webapp_data(data.get("initData", ""), TOKEN): return web.json_response({"status": "error"}, status=403)

        user_id = data.get("user_id", 0)
        user_data = await get_user(user_id)
        if user_data and user_data[3] == 1: return web.json_response({"status": "error", "message": "Аккаунт заблокирован."}, status=403)

        country, currency = data.get("country", "СНГ"), data.get("currency", "VAL")
        rub_amount, local_received = data.get("rub_amount", "0"), data.get("local_received", "0")
        recipient_bank, recipient_card, recipient_name = data.get("recipient_bank", ""), data.get("recipient_card", ""), data.get("recipient_name", "")
        tx_id, promo, bonus_used = data.get("transfer_comment", ""), data.get("promo", "Нет"), float(data.get("bonus_used", 0))

        if bonus_used > 0:
            async with aiosqlite.connect("koropay.db") as db:
                async with db.execute("SELECT bonus_balance FROM users WHERE user_id=?", (user_id,)) as cursor:
                    bal = await cursor.fetchone()
                if bal and bal[0] >= bonus_used:
                    await db.execute("UPDATE users SET bonus_balance = bonus_balance - ? WHERE user_id=?", (bonus_used, user_id))
                else: bonus_used = 0.0

        async with aiosqlite.connect("koropay.db") as db:
            await db.execute(
                "INSERT INTO transfers (tx_id, user_id, country, rub_amount, local_amount, currency, status, bonus_used) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (tx_id, user_id, country, rub_amount, local_received, currency, "PENDING", bonus_used)
            )
            await db.commit()

        active_card = await get_active_card()
        admin_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Выполнен", callback_data=f"approve_{user_id}_{tx_id}")],
            [InlineKeyboardButton(text="❌ Отмена: Нет платежа", callback_data=f"rej_fake_{user_id}_{tx_id}")],
            [InlineKeyboardButton(text="❌ Отмена: AML", callback_data=f"rej_aml_{user_id}_{tx_id}")]
        ])
        
        actual_rub_to_pay = float(rub_amount.replace(" ₽", "")) - bonus_used
        admin_message = (
            f"🚨 <b>НОВАЯ ЗАЯВКА!</b>\n\n👤 Клиент: @{data.get('username', 'Аноним')} (ID: <code>{user_id}</code>)\n🆔 Транзакция: <code>{tx_id}</code>\n"
            f"🎟 Промокод: <b>{promo}</b> | 💎 Бонусов списано: <b>{bonus_used} ₽</b>\n\n"
            f"1️⃣ Проверь поступление <b>{actual_rub_to_pay} ₽</b> на реквизиты:\n<code>{active_card}</code>\n"
            f"2️⃣ Переведи <b>{local_received} {currency}</b>:\n   🏦 Банк: <b>{recipient_bank}</b>\n   💳 Карта: <code>{recipient_card}</code>\n   👤 ФИО: <b>{recipient_name}</b>\n"
        )
        if ADMIN_CHAT_ID: await bot.send_message(ADMIN_CHAT_ID, admin_message, parse_mode="HTML", reply_markup=admin_kb)
        return web.json_response({"status": "success", "tx_id": tx_id, "actual_pay": actual_rub_to_pay})
    except Exception as e: return web.json_response({"status": "error", "message": str(e)}, status=400)


@dp.callback_query(F.data.startswith("approve_"))
async def process_approve(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    target_user_id, tx_id = int(parts[1]), parts[2]
    async with aiosqlite.connect('koropay.db') as db:
        async with db.execute("SELECT rub_amount, local_amount, currency FROM transfers WHERE tx_id=?", (tx_id,)) as cursor: tx_data = await cursor.fetchone()
            
    if not tx_data: return await callback.answer("Транзакция не найдена!", show_alert=True)
    msg_text = callback.message.text
    try: card = msg_text.split("Карта: ")[1].split("\n")[0].replace("<code>", "").replace("</code>", "").strip()
    except: card = ""

    await callback.message.edit_text(callback.message.text + "\n\n⏳ <b>ОТПРАВЛЯЮ СРЕДСТВА ЧЕРЕЗ CAPITALIST...</b>", parse_mode="HTML")
    is_payout_success = await execute_capitalist_payout(card, tx_data[1], tx_data[2], tx_id)

    if is_payout_success:
        async with aiosqlite.connect('koropay.db') as db:
            await db.execute("UPDATE transfers SET status='SUCCESS' WHERE tx_id=?", (tx_id,))
            async with db.execute("SELECT referrer_id FROM users WHERE user_id=?", (target_user_id,)) as cursor: u_data = await cursor.fetchone()
            if u_data and u_data[0]:
                await db.execute("UPDATE users SET bonus_balance = bonus_balance + 50.0 WHERE user_id=?", (u_data[0],))
                try: await bot.send_message(u_data[0], f"🎁 <b>Вам начислен бонус 50 ₽!</b>\nВаш реферал успешно совершил перевод.", parse_mode="HTML")
                except: pass
            await db.commit()

        await callback.message.edit_text(msg_text + f"\n\n✅ <b>ЗАВЕРШЕН И ЧЕК ОТПРАВЛЕН!</b>", parse_mode="HTML")
        try:
            bank = msg_text.split("Банк: ")[1].split("\n")[0].replace("<b>", "").replace("</b>", "")
            name = msg_text.split("ФИО: ")[1].split("\n")[0].replace("<b>", "").replace("</b>", "")
            await bot.send_photo(target_user_id, photo=BufferedInputFile(generate_receipt_image(tx_id, tx_data[0], tx_data[1], tx_data[2], name, bank, card).getvalue(), filename=f"KoroPay_{tx_id}.png"), caption=f"🎉 <b>Перевод успешно доставлен!</b>\n🆔 <code>{tx_id}</code>", parse_mode="HTML")
        except: pass
        await callback.answer("Успешно отправлено!")
    else:
        await callback.message.edit_text(msg_text + "\n\n❌ <b>ОШИБКА API CAPITALIST. ПЕРЕВОД НЕ ВЫПОЛНЕН.</b>", parse_mode="HTML")
        await callback.answer("Ошибка шлюза.", show_alert=True)

@dp.callback_query(F.data.startswith("rej_"))
async def process_reject(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    reason_type, target_user_id, tx_id = parts[1], int(parts[2]), parts[3]
    reason_text = "сработал AML-контроль" if reason_type == "aml" else "платеж не поступил"
    async with aiosqlite.connect('koropay.db') as db:
        await db.execute("UPDATE transfers SET status='REJECTED' WHERE tx_id=?", (tx_id,))
        await db.commit()
    await add_strike(target_user_id)
    await callback.message.edit_text(callback.message.text + f"\n\n❌ <b>ОТМЕНЕНО: {reason_text.upper()}</b>", parse_mode="HTML")
    try: await bot.send_message(target_user_id, f"❌ Ваш перевод <code>{tx_id}</code> отменен.\nПричина: {reason_text}.", parse_mode="HTML")
    except: pass
    await callback.answer("Отклонено.")

async def webapp_handler(request):
    current_card = await get_active_card()
    html_content = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>Koro Pay</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
        <style>
            :root {
                --bg: var(--tg-theme-bg-color, #05050C); 
                --surface: var(--tg-theme-secondary-bg-color, #121322); 
                --surface-hover: rgba(150, 103, 224, 0.1);
                --primary: #9667E0;
                --primary-light: #7C83FD;
                --primary-grad: linear-gradient(135deg, #7C83FD 0%, #9667E0 100%);
                --text: var(--tg-theme-text-color, #FFFFFF); 
                --text-sec: var(--tg-theme-hint-color, #8A8E9E); 
                --border: rgba(124, 131, 253, 0.15);
                --success: #30D158; --danger: #FF453A; --warning: #FF9F0A;
            }
            * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
            body { background: var(--bg); color: var(--text); font-family: 'Inter', sans-serif; margin: 0; padding: 0; display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
            
            #biometricLock { position: fixed; top:0; left:0; width:100%; height:100%; background: var(--bg); z-index: 9999; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; }
            #mainAppContent { display: none; height: 100%; width: 100%; flex-direction: column; }
            
            .header { padding: 20px 20px 15px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); background: var(--bg); }
            .logo-container { display: flex; align-items: center; gap: 12px; }
            .logo-img { width: 42px; height: 42px; border-radius: 10px; object-fit: cover; background: var(--surface); }
            .header-title { font-size: 24px; font-weight: 800; letter-spacing: -0.5px; }
            .header-title span { color: #9667E0; }
            .tagline { font-size: 11px; color: var(--text-sec); letter-spacing: 0.5px; text-transform: uppercase; margin-top: 2px; }
            
            .content { flex: 1; overflow-y: auto; padding: 15px 20px 80px; }
            .screen { display: none; animation: fadeIn 0.3s ease; }
            .screen.active { display: block; }
            @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

            .card-panel { background: var(--surface); border-radius: 16px; padding: 18px; margin-bottom: 16px; border: 1px solid var(--border); box-shadow: 0 4px 20px rgba(0,0,0,0.1); }
            .input-group { margin-bottom: 16px; }
            .input-group:last-child { margin-bottom: 0; }
            label { display: block; font-size: 11px; font-weight: 600; color: var(--text-sec); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; }
            
            input, select, textarea { width: 100%; padding: 14px; background: rgba(124, 131, 253, 0.03); border: 1px solid var(--border); border-radius: 12px; color: var(--text); font-size: 16px; font-family: 'Inter', sans-serif; transition: border-color 0.2s; outline: none; font-weight: 500; }
            input:focus, select:focus, textarea:focus { border-color: var(--primary); background: rgba(124, 131, 253, 0.05); }
            
            .address-book { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 8px; margin-bottom: 12px; scrollbar-width: none; }
            .address-book::-webkit-scrollbar { display: none; }
            .address-chip { flex-shrink: 0; padding: 8px 12px; background: var(--surface-hover); border: 1px solid var(--border); border-radius: 20px; font-size: 12px; font-weight: 600; color: var(--primary); cursor: pointer; display: flex; align-items: center; gap: 6px; }
            
            .two-way-calc { display: flex; gap: 10px; align-items: center; }
            .two-way-calc .calc-col { flex: 1; }
            .two-way-calc .calc-eq { font-size: 20px; color: var(--text-sec); font-weight: 600; margin-top: 15px;}
            
            .quick-amounts { display: flex; gap: 8px; margin-top: 10px; }
            .quick-btn { flex: 1; padding: 10px 0; background: var(--surface-hover); color: var(--primary); border: 1px solid var(--border); border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; transition: 0.2s; }
            
            .receipt-row { display: flex; justify-content: space-between; font-size: 14px; margin-bottom: 10px; color: var(--text-sec); align-items: center; }
            .receipt-row.total { font-size: 18px; font-weight: 800; color: var(--text); margin-top: 14px; padding-top: 14px; border-top: 1px dashed var(--border); margin-bottom: 0; }
            
            .btn-primary { width: 100%; padding: 16px; background: var(--primary-grad); color: #fff; border: none; border-radius: 14px; font-size: 16px; font-weight: 700; cursor: pointer; display: flex; justify-content: center; align-items: center; box-shadow: 0 4px 15px rgba(150, 103, 224, 0.3); transition: opacity 0.2s; }
            .btn-primary:active { opacity: 0.8; }
            .btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
            .btn-crypto { background: #2AABEE; color: #fff; box-shadow: 0 4px 15px rgba(42, 171, 238, 0.3); margin-top: 12px;}
            .btn-secondary { background: transparent; color: var(--primary); padding: 8px 12px; border: 1px solid var(--primary); border-radius: 8px; font-size: 12px; font-weight: 600; cursor: pointer; }
            .btn-copy { background: var(--surface-hover); color: var(--primary); padding: 12px; border: 1px solid var(--border); border-radius: 10px; font-size: 14px; font-weight: 600; width: 100%; margin-top: 12px; cursor: pointer; }

            .checkbox-wrapper { display: flex; align-items: center; gap: 10px; font-size: 12px; color: var(--text-sec); margin-bottom: 20px; }
            .checkbox-wrapper input { width: 22px; height: 22px; accent-color: var(--primary); }
            
            /* --- НАВИГАЦИОННАЯ ПАНЕЛЬ С КАРТИНКАМИ --- */
            .bottom-nav { position: fixed; bottom: 0; left: 0; width: 100%; background: var(--bg); border-top: 1px solid var(--border); display: flex; justify-content: space-around; padding: 12px 0 24px; z-index: 50; }
            .nav-item { display: flex; flex-direction: column; align-items: center; color: var(--text-sec); font-size: 10px; cursor: pointer; font-weight: 600; transition: color 0.2s; width: 25%; text-align: center; }
            .nav-item.active { color: var(--primary); }
            .nav-icon-img { width: 28px; height: 28px; margin-bottom: 4px; object-fit: contain; transition: filter 0.2s; opacity: 0.7; }
            .nav-item.active .nav-icon-img { opacity: 1; filter: drop-shadow(0 0 6px rgba(150, 103, 224, 0.8)); }
            /* ----------------------------------------- */
            
            .history-card { display: flex; justify-content: space-between; align-items: center; padding: 14px 0; border-bottom: 1px solid var(--border); }
            .history-card:last-child { border-bottom: none; padding-bottom: 0; }
            .h-left .h-title { font-size: 15px; font-weight: 600; margin-bottom: 4px; color: var(--text); }
            .h-left .h-desc { font-size: 12px; color: var(--text-sec); }
            .h-right { text-align: right; }
            .h-right .h-amount { font-size: 15px; font-weight: 700; margin-bottom: 4px; color: var(--text); }
            .badge { font-size: 10px; font-weight: 800; padding: 4px 8px; border-radius: 6px; display: inline-block; text-transform: uppercase; }
            .b-pending { background: rgba(255, 159, 10, 0.15); color: var(--warning); }
            .b-success { background: rgba(48, 209, 88, 0.15); color: var(--success); }
            .b-reject { background: rgba(255, 69, 58, 0.15); color: var(--danger); }

            .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); z-index: 100; justify-content: center; align-items: flex-end; }
            .modal-content { background: var(--surface); width: 100%; border-radius: 24px 24px 0 0; padding: 24px; max-height: 85vh; overflow-y: auto; animation: slideUp 0.3s; border-top: 1px solid var(--border); }
            @keyframes slideUp { from { transform: translateY(100%); } to { transform: translateY(0); } }
            .modal-close { width: 40px; height: 5px; background: var(--border); border-radius: 3px; margin: 0 auto 20px; }
            .legal-text h3 { margin-top: 0; font-size: 18px; font-weight: 800; color: var(--text); margin-bottom: 16px; }
            .legal-text p { font-size: 13px; color: var(--text-sec); line-height: 1.6; margin-bottom: 12px; }
        </style>
    </head>
    <body>
        
        <div id="biometricLock">
            <div style="font-size: 60px; margin-bottom: 20px;">🛡</div>
            <h2 style="margin-bottom: 10px; font-weight: 800;">Вход в Koro Pay</h2>
            <p style="color: var(--text-sec); font-size: 14px; max-width: 80%;">Запрашиваем биометрию устройства для безопасности ваших финансов.</p>
        </div>

        <div id="mainAppContent">
            <div class="header">
                <div class="logo-container">
                    <img src="https://raw.githubusercontent.com/Kwiz2005/koropay/main/logo.png" alt="Logo" class="logo-img" onerror="this.style.display='none'">
                    <div>
                        <div class="header-title">Koro<span>Pay</span></div>
                        <div class="tagline">Платежи. Переводы. Больше.</div>
                    </div>
                </div>
            </div>

            <div class="content">
                <div id="tab-transfer" class="screen active">
                    <div class="address-book" id="addressBook" style="display: none;"></div>

                    <div class="card-panel">
                        <div class="input-group">
                            <label>Страна зачисления</label>
                            <select id="country" onchange="onCountryChange()">
                                <option value="Uzbekistan|UZS|135.00">🇺🇿 Узбекистан (UZS)</option>
                                <option value="Tajikistan|TJS|0.115">🇹🇯 Таджикистан (TJS)</option>
                                <option value="Kyrgyzstan|KGS|0.95">🇰🇬 Киргизия (KGS)</option>
                                <option value="Azerbaijan|AZN|0.018">🇦🇿 Азербайджан (AZN)</option>
                                <option value="Kazakhstan|KZT|5.15">🇰🇿 Казахстан (KZT)</option>
                                <option value="Armenia|AMD|4.15">🇦🇲 Армения (AMD)</option>
                                <option value="Georgia|GEL|0.028">🇬🇪 Грузия (GEL)</option>
                                <option value="Moldova|MDL|0.18">🇲🇩 Молдова (MDL)</option>
                                <option value="Europe|EUR|0.0095">🇪🇺 Европа (EUR)</option>
                                <option value="Worldwide|USD|0.01">🌍 Весь мир (USD)</option>
                            </select>
                        </div>
                        <div class="input-group">
                            <label>Банк получателя</label>
                            <select id="recipientBank" onchange="saveDraft()"></select>
                        </div>
                        
                        <div class="two-way-calc">
                            <div class="calc-col">
                                <label>Спишем (₽)</label>
                                <input type="number" id="amount" placeholder="0" oninput="calcMode='rub'; calculateParams();">
                            </div>
                            <div class="calc-eq">≈</div>
                            <div class="calc-col">
                                <label>Зачислим (<span id="localCurrLabel">UZS</span>)</label>
                                <input type="number" id="amountLocal" placeholder="0" oninput="calcMode='local'; calculateParams();">
                            </div>
                        </div>
                        <div class="quick-amounts">
                            <button class="quick-btn" onclick="setAmount(1000)">1 000 ₽</button>
                            <button class="quick-btn" onclick="setAmount(5000)">5 000 ₽</button>
                            <button class="quick-btn" onclick="setAmount(15000)">15 000 ₽</button>
                            <button class="quick-btn" onclick="setAmount(25000)">MAX</button>
                        </div>
                    </div>

                    <div class="card-panel">
                        <div class="input-group">
                            <label>Номер карты / счета</label>
                            <input type="tel" id="recCard" placeholder="0000 0000 0000 0000" maxlength="23" pattern="[0-9 ]*" oninput="formatCard(this)">
                        </div>
                        <div class="input-group">
                            <label>ФИО получателя</label>
                            <input type="text" id="recName" placeholder="Иванов Иван Иванович" oninput="saveDraft()">
                        </div>
                    </div>

                    <div class="card-panel">
                        <div class="input-group" style="margin-bottom: 12px;">
                            <label>Промокод (Если есть)</label>
                            <input type="text" id="promoCode" placeholder="Например: KORO2026" oninput="calculateParams()" style="text-transform: uppercase;">
                        </div>
                        
                        <div id="bonusBlock" style="display: none; justify-content: space-between; align-items: center; padding: 12px; background: rgba(150,103,224,0.1); border-radius: 12px; margin-bottom: 16px;">
                            <div>
                                <div style="font-weight: 600; font-size: 13px; color: var(--text);">Списать бонусы</div>
                                <div style="font-size: 11px; color: var(--text-sec);">Доступно: <span id="maxBonusVal">0</span> ₽</div>
                            </div>
                            <input type="checkbox" id="useBonusCheck" style="width: 24px; height: 24px; accent-color: var(--primary);" onchange="calculateParams()">
                        </div>

                        <div class="receipt-row">
                            <span>Актуальный курс <span id="promoBadge" style="display:none; color:var(--success); font-size:10px;">(БЕЗ КОМИССИИ)</span></span>
                            <span id="rateDisplay" style="color: var(--primary); font-weight: 600;">0.00</span>
                        </div>
                        <div class="receipt-row total">
                            <span>К оплате с учетом скидок</span>
                            <span id="totalRub" style="color: var(--text);">0 ₽</span>
                        </div>
                        <div class="receipt-row total" style="border:none; padding-top:4px; margin-top:0;">
                            <span style="font-size: 14px; font-weight: 500;">Сумма к зачислению</span>
                            <span id="totalLocal" style="color: var(--primary);">0.00 UZS</span>
                        </div>
                    </div>

                    <div class="checkbox-wrapper">
                        <input type="checkbox" id="termsCheck">
                        <label for="termsCheck" style="margin: 0; text-transform: none; letter-spacing: 0;">Я согласен с <span class="link" onclick="openModal('ofertaModal')">Офертой сервиса</span>.</label>
                    </div>

                    <button class="btn-primary" onclick="initiateTransfer()">Продолжить к Оплате</button>
                </div>

                <div id="tab-payment" class="screen">
                    <div style="text-align: center; margin-bottom: 24px;">
                        <div style="font-size: 48px; margin-bottom: 10px;">💳</div>
                        <h2 style="margin:0; font-weight: 800;">Методы оплаты</h2>
                        <div style="color: var(--warning); font-weight: 700; margin-top: 10px; font-size: 18px;" id="timerDisplay">15:00</div>
                    </div>

                    <div class="card-panel" style="text-align: center;">
                        <label style="text-align: center;">К оплате</label>
                        <div id="payRubSum" style="font-size: 32px; font-weight: 800; color: var(--text);">0 ₽</div>
                    </div>

                    <button id="btnCryptoPay" class="btn-primary btn-crypto" onclick="startCryptoPay()">💎 Оплатить криптой (Автоматически)</button>
                    
                    <div style="text-align: center; margin: 16px 0; color: var(--text-sec); font-size: 12px; font-weight: 600; text-transform: uppercase;">или ручной перевод</div>
                    
                    <div class="card-panel" style="border-color: var(--primary); background: var(--surface-hover);">
                        <label style="color: var(--primary);">Обязательный комментарий (СБП/Карта)</label>
                        <div id="transferCommentText" style="font-size: 24px; font-weight: 800; color: var(--text);">KORO-0000</div>
                        <button class="btn-copy" id="btnCopyComment" onclick="copyText(currentOrderCode, 'btnCopyComment')" style="background: var(--primary-grad); color: #fff; border: none;">Скопировать код</button>
                    </div>

                    <div class="card-panel">
                        <label>Реквизиты для оплаты (СБП/Карта)</label>
                        <div style="font-size: 22px; font-weight: 800; letter-spacing: 1px; margin-bottom: 4px;">ACTUAL_SYSTEM_CARD</div>
                        <div style="font-size: 14px; color: var(--text-sec); font-weight: 500;">Озон Банк (Mirelem Ismailzade)</div>
                        <button class="btn-copy" id="btnCopyCard" onclick="copyText('ACTUAL_SYSTEM_CARD', 'btnCopyCard')">Скопировать реквизиты</button>
                    </div>

                    <button id="btnConfirmPay" class="btn-primary" onclick="confirmPayment()" style="background: var(--success); box-shadow: 0 4px 15px rgba(48, 209, 88, 0.2);">Я перевел(а) на Озон Банк</button>
                </div>
                
                <div id="tab-history" class="screen">
                    <h2 style="margin-bottom: 20px; font-weight: 800;">История операций</h2>
                    <div class="card-panel" id="historyContainer">
                        <div style="text-align:center; padding: 20px; color: var(--text-sec);">⏳ Загрузка данных...</div>
                    </div>
                </div>

                <div id="tab-support" class="screen">
                    <h2 style="margin-bottom: 20px; font-weight: 800;">Техподдержка</h2>
                    <div class="card-panel" style="margin-bottom: 16px;">
                        <label>Написать в поддержку</label>
                        <textarea id="supportMessage" rows="4" placeholder="Опишите вашу проблему с переводом..."></textarea>
                        <button class="btn-primary" onclick="sendSupportMessage()" style="font-size: 14px; padding: 12px; margin-top: 12px;">Отправить обращение</button>
                    </div>
                    
                    <div class="card-panel" style="text-align: center; padding: 24px 18px;">
                        <h3 style="margin: 0 0 8px 0; font-size: 16px;">Альтернативный способ</h3>
                        <p style="color: var(--text-sec); font-size: 12px; line-height: 1.5; margin-bottom: 16px;">
                            Вы также можете написать нашему оператору напрямую в Telegram.
                        </p>
                        <button class="btn-copy" onclick="tg.openTelegramLink('https://t.me/koropay_support')" style="margin-top:0;">Открыть чат с оператором</button>
                    </div>
                </div>

                <div id="tab-profile" class="screen">
                    <h2 style="margin-bottom: 20px; font-weight: 800;">Мой Профиль</h2>
                    
                    <div class="card-panel">
                        <label style="margin-bottom: 12px;">🎁 Пригласить друга</label>
                        <p style="font-size: 12px; color: var(--text-sec); line-height: 1.4; margin: 0 0 12px 0;">Ваш баланс: <b id="bonusBalanceDisplay" style="color: var(--success);">0.00 ₽</b><br>Получайте 50 ₽ за каждый успешный перевод друга. Вы можете списать их при следующем переводе.</p>
                        <div style="display: flex; gap: 8px;">
                            <input type="text" id="refLink" readonly style="font-size: 12px; padding: 10px;">
                            <button class="btn-secondary" id="btnCopyRef" onclick="copyText(document.getElementById('refLink').value, 'btnCopyRef')" style="width: auto;">Копия</button>
                        </div>
                    </div>
                    
                    <div class="card-panel">
                        <div class="receipt-row" style="padding: 14px 0; border-bottom: 1px solid var(--border); margin:0; cursor:pointer;" onclick="openModal('ofertaModal')">
                            <span style="font-weight:600; color:var(--text);">📄 Договор Оферты</span><span style="color:var(--primary);">›</span>
                        </div>
                        <div class="receipt-row" style="padding: 14px 0; margin:0;">
                            <span style="font-weight:600; color:var(--text);">Версия системы</span><span style="color:var(--text-sec); font-family:monospace;">Koro Pay v1.0.0.0</span>
                        </div>
                    </div>
                </div>

                <div id="tab-success" class="screen" style="text-align: center; padding-top: 40px;">
                    <div style="font-size: 70px; margin-bottom: 20px;">⏳</div>
                    <h2 style="margin-bottom: 12px; font-weight: 800;" id="successTitle">Ожидание перевода</h2>
                    <p style="color: var(--text-sec); font-size: 15px; line-height: 1.6; margin-bottom: 32px; background: var(--surface); padding: 20px; border-radius: 16px; border: 1px solid var(--border);" id="successDesc">
                        Мы проверяем поступление вашего платежа. <br><br>
                        Как только средства будут подтверждены, <b>перевод будет осуществлен получателю</b>. Вы получите чек в этот чат.
                    </p>
                    <button id="btnCheckCrypto" class="btn-primary btn-crypto" style="display:none; margin-bottom:12px;" onclick="checkCryptoPayment()">Обновить статус оплаты</button>
                    <button class="btn-primary" onclick="tg.close()">Вернуться в чат</button>
                </div>
            </div>

            <!-- ИКОНКИ НАВИГАЦИОННОЙ ПАНЕЛИ С GITHUB -->
            <div class="bottom-nav" id="bottomNav">
                <div class="nav-item active" onclick="switchTab('tab-transfer', this)">
                    <img src="https://raw.githubusercontent.com/Kwiz2005/koropay/main/icon_transfer.png" class="nav-icon-img" onerror="this.style.display='none'">
                    <div>Перевод</div>
                </div>
                <div class="nav-item" onclick="switchTab('tab-history', this); loadHistory();">
                    <img src="https://raw.githubusercontent.com/Kwiz2005/koropay/main/icon_history.png" class="nav-icon-img" onerror="this.style.display='none'">
                    <div>История</div>
                </div>
                <div class="nav-item" onclick="switchTab('tab-support', this)">
                    <img src="https://raw.githubusercontent.com/Kwiz2005/koropay/main/icon_support.png" class="nav-icon-img" onerror="this.style.display='none'">
                    <div>Помощь</div>
                </div>
                <div class="nav-item" onclick="switchTab('tab-profile', this); loadProfile();">
                    <img src="https://raw.githubusercontent.com/Kwiz2005/koropay/main/icon_profile.png" class="nav-icon-img" onerror="this.style.display='none'">
                    <div>Профиль</div>
                </div>
            </div>
        </div>

        <div id="ofertaModal" class="modal" onclick="if(event.target==this) closeModal('ofertaModal')">
            <div class="modal-content legal-text">
                <div class="modal-close"></div>
                <h3>Договор публичной оферты Koro Pay</h3>
                <p><b>1. Общие положения.</b> Настоящий договор является публичной офертой в соответствии со ст. 437 ГК РФ. Использование сервиса Koro Pay (включая Telegram WebApp) означает безоговорочное принятие пользователем условий настоящего договора (акцепт).</p>
                <p><b>2. Предмет соглашения.</b> Сервис предоставляет услуги информационно-технического сопровождения международных P2P-переводов. Сервис не является кредитной организацией и функционирует исключительно как агрегатор платежных шлюзов.</p>
                <p><b>3. Финансовые условия и расчеты.</b> Итоговая сумма к зачислению фиксируется на момент создания заявки и отображается в интерфейсе. Оплата осуществляется пользователем в рублях или криптовалюте. Сервисная комиссия интегрирована в итоговый курс. Пользователь вправе применять бонусные рубли (в рамках программы лояльности) для частичной или полной компенсации комиссии.</p>
                <p><b>4. Политика AML и KYC.</b> Пользователь подтверждает исключительно легальное происхождение переводимых средств. Категорически запрещено использование реквизитов третьих лиц и анонимных платежных инструментов. При выявлении транзакций, вызывающих подозрения, Сервис оставляет за собой право приостановить операцию, запросить документы, подтверждающие личность (KYC), либо осуществить возврат средств отправителю за вычетом комиссий шлюзов.</p>
                <p><b>5. Ответственность сторон.</b> Сервис не несет финансовой ответственности за возможные задержки на стороне банков-эмитентов, ошибки пользователя при указании реквизитов, а также блокировки карт получателей местными органами финансового мониторинга. Обязательства Сервиса считаются выполненными в момент успешной передачи средств локальному провайдеру (выдача чека).</p>
                <button class="btn-primary" style="margin-top: 24px;" onclick="closeModal('ofertaModal')">Я ознакомлен и согласен</button>
            </div>
        </div>

        <script>
            let tg = window.Telegram.WebApp;
            tg.expand();
            
            // --- NATIVE BIOMETRY INTEGRATION ---
            let bm = tg.BiometricManager;
            bm.init(() => {
                if (bm.isBiometricAvailable) {
                    if (!bm.isAccessGranted) {
                        bm.requestAccess({reason: 'Защита финансовых операций Koro Pay'}, (granted) => {
                            if (granted) authenticateBiometry();
                            else unlockApp(); 
                        });
                    } else authenticateBiometry();
                } else unlockApp(); 
            });
            function authenticateBiometry() {
                bm.authenticate({reason: 'Вход в Koro Pay'}, (success) => {
                    if (success) unlockApp();
                    else tg.close();
                });
            }
            function unlockApp() {
                document.getElementById('biometricLock').style.display = 'none';
                document.getElementById('mainAppContent').style.display = 'flex';
                tg.ready();
                initApp();
            }

            const banksData = {
                "Uzbekistan": ["UzCard / Humo (Любой банк)", "Kapital Bank", "NBU", "SQB"],
                "Tajikistan": ["Корти Милли (Любой банк)", "Alif Bank", "Dushanbe City"],
                "Kyrgyzstan": ["Элкарт (Любой банк)", "MBank (МБанк)", "Optima Bank"],
                "Azerbaijan": ["Visa / Mastercard (Любой банк)", "Kapital Bank", "Leobank"],
                "Kazakhstan": ["Любой банк (Kaspi, Halyk, Jusan)", "Kaspi Bank", "Halyk Bank"],
                "Armenia": ["Любой банк (ArCa / Visa / MC)", "Ameriabank", "Inecobank"],
                "Georgia": ["Любой банк (Visa / MC)", "TBC Bank", "Bank of Georgia (BOG)"],
                "Moldova": ["Любой банк (Visa / MC)", "maib", "Moldindconbank"],
                "Europe": ["Любой банк (SEPA / Visa / MC)"],
                "Worldwide": ["Любой банк (Visa / Mastercard)"]
            };

            let currentMultiplier = 135, currentCurr = 'UZS', enteredRub = 0, calculatedLocal = 0, currentOrderCode = '', timerInterval;
            let calcMode = 'rub'; 
            let userBonusBalance = 0.0;
            let appliedBonus = 0.0;
            let currentInvoiceId = null;
            let savedRecipients = JSON.parse(localStorage.getItem('koro_recipients') || '[]');

            async function initApp() { 
                document.getElementById('refLink').value = `https://t.me/koropay_bot?start=${tg.initDataUnsafe?.user?.id || 'ref'}`;
                
                try {
                    let response = await fetch(`/api/profile?user_id=${tg.initDataUnsafe?.user?.id || 0}&initData=${encodeURIComponent(tg.initData)}`);
                    let res = await response.json();
                    if(res.status === 'success') {
                        userBonusBalance = res.balance;
                        if(userBonusBalance > 0) {
                            document.getElementById('bonusBlock').style.display = 'flex';
                            document.getElementById('maxBonusVal').textContent = userBonusBalance.toFixed(2);
                        }
                    }
                } catch(e) {}

                initAddressBook();
                if (localStorage.getItem('koro_country')) document.getElementById('country').value = localStorage.getItem('koro_country');
                updateBanks(true); 
                if (localStorage.getItem('koro_bank')) document.getElementById('recipientBank').value = localStorage.getItem('koro_bank');
                if (localStorage.getItem('koro_amount')) document.getElementById('amount').value = localStorage.getItem('koro_amount');
                if (localStorage.getItem('koro_card')) document.getElementById('recCard').value = localStorage.getItem('koro_card');
                if (localStorage.getItem('koro_name')) document.getElementById('recName').value = localStorage.getItem('koro_name');
                calculateParams(); 
            }

            function initAddressBook() {
                let ab = document.getElementById('addressBook');
                if(savedRecipients.length > 0) {
                    ab.style.display = 'flex';
                    ab.innerHTML = '';
                    savedRecipients.forEach((rec, idx) => {
                        ab.innerHTML += `<div class="address-chip" onclick="applyTemplate(${idx})">👤 ${rec.name.split(' ')[0]}</div>`;
                    });
                }
            }

            function applyTemplate(idx) {
                haptic();
                let rec = savedRecipients[idx];
                document.getElementById('recName').value = rec.name;
                document.getElementById('recCard').value = rec.card;
                saveDraft();
            }

            function saveNewRecipient(name, card, bank) {
                if(!savedRecipients.find(r => r.card === card)) {
                    savedRecipients.unshift({name, card, bank});
                    if(savedRecipients.length > 5) savedRecipients.pop();
                    localStorage.setItem('koro_recipients', JSON.stringify(savedRecipients));
                }
            }

            function saveDraft() {
                localStorage.setItem('koro_country', document.getElementById('country').value);
                localStorage.setItem('koro_bank', document.getElementById('recipientBank').value);
                localStorage.setItem('koro_amount', document.getElementById('amount').value);
                localStorage.setItem('koro_card', document.getElementById('recCard').value);
                localStorage.setItem('koro_name', document.getElementById('recName').value);
            }

            function haptic() { if (tg.HapticFeedback) tg.HapticFeedback.impactOccurred('light'); }

            function switchTab(tabId, el) {
                haptic();
                document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
                document.getElementById(tabId).classList.add('active');
                if(el) {
                    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
                    el.classList.add('active');
                }
            }

            function openModal(id) { haptic(); document.getElementById(id).style.display = 'flex'; }
            function closeModal(id) { haptic(); document.getElementById(id).style.display = 'none'; }
            function formatCard(input) { let val = input.value.replace(/\D/g, ''); input.value = val.match(/.{1,4}/g)?.join(' ') || ''; saveDraft(); }
            function setAmount(val) { haptic(); calcMode = 'rub'; document.getElementById('amount').value = val; calculateParams(); }
            function onCountryChange() { updateBanks(false); calculateParams(); }

            function updateBanks(isInit) {
                let countrySelectVal = document.getElementById('country').value;
                let countryKey = countrySelectVal.split('|')[0];
                let bankSelect = document.getElementById('recipientBank');
                if (!bankSelect) return;
                bankSelect.innerHTML = '';
                let availableBanks = banksData[countryKey] || ["Любой банк"];
                availableBanks.forEach(bank => {
                    let opt = document.createElement('option');
                    opt.value = bank;
                    opt.textContent = bank;
                    bankSelect.appendChild(opt);
                });
                if(!isInit) { bankSelect.selectedIndex = 0; saveDraft(); }
            }

            function calculateParams() {
                let val = document.getElementById('country').value.split('|');
                currentCurr = val[1]; currentMultiplier = parseFloat(val[2]);
                document.getElementById('localCurrLabel').textContent = currentCurr;
                
                let promo = document.getElementById('promoCode').value.trim().toUpperCase();
                let isPromoActive = (promo === 'KORO2026');
                let effectiveRate = isPromoActive ? (currentMultiplier / 0.95) : currentMultiplier;
                
                document.getElementById('promoBadge').style.display = isPromoActive ? 'inline' : 'none';
                document.getElementById('rateDisplay').textContent = `1 ₽ = ${effectiveRate.toFixed(2)} ${currentCurr}`;
                
                if(calcMode === 'rub') {
                    enteredRub = parseFloat(document.getElementById('amount').value) || 0;
                    calculatedLocal = enteredRub * effectiveRate;
                    document.getElementById('amountLocal').value = enteredRub > 0 ? calculatedLocal.toFixed(2) : '';
                } else {
                    calculatedLocal = parseFloat(document.getElementById('amountLocal').value) || 0;
                    enteredRub = calculatedLocal / effectiveRate;
                    document.getElementById('amount').value = calculatedLocal > 0 ? enteredRub.toFixed(2) : '';
                }
                
                appliedBonus = 0;
                let bonusCheck = document.getElementById('useBonusCheck');
                if(bonusCheck && bonusCheck.checked) {
                    appliedBonus = Math.min(enteredRub, userBonusBalance);
                }
                
                let actualRubToPay = Math.max(0, enteredRub - appliedBonus);
                
                document.getElementById('totalRub').textContent = actualRubToPay.toLocaleString('ru-RU', {minimumFractionDigits: 0, maximumFractionDigits: 2}) + ' ₽';
                document.getElementById('totalLocal').textContent = calculatedLocal.toLocaleString('ru-RU', {minimumFractionDigits: 2, maximumFractionDigits: 2}) + ' ' + currentCurr;
                saveDraft();
            }

            function copyText(text, btnId) {
                haptic(); navigator.clipboard.writeText(text.replace(/\s+/g, ''));
                let btn = document.getElementById(btnId); let origText = btn.textContent;
                btn.textContent = '✅ Скопировано!'; setTimeout(() => { btn.textContent = origText; }, 2000);
            }

            async function loadProfile() {
                let user_id = tg.initDataUnsafe?.user?.id || 0;
                try {
                    let response = await fetch(`/api/profile?user_id=${user_id}&initData=${encodeURIComponent(tg.initData)}`);
                    let res = await response.json();
                    if(res.status === 'success') { document.getElementById('bonusBalanceDisplay').textContent = res.balance.toFixed(2) + ' ₽'; }
                } catch(e) {}
            }
            
            async function loadHistory() {
                let user_id = tg.initDataUnsafe?.user?.id || 0;
                let container = document.getElementById('historyContainer');
                try {
                    let response = await fetch(`/api/history?user_id=${user_id}&initData=${encodeURIComponent(tg.initData)}`);
                    let res = await response.json();
                    if(res.status !== 'success') throw new Error();
                    
                    if(res.data.length === 0) {
                        container.innerHTML = '<div style="text-align:center; padding: 20px; color: var(--text-sec); font-weight: 500;">У вас пока нет операций</div>';
                        return;
                    }
                    container.innerHTML = '';
                    res.data.forEach(tx => {
                        let bClass = tx.status === 'SUCCESS' ? 'b-success' : (tx.status === 'REJECTED' ? 'b-reject' : 'b-pending');
                        let bText = tx.status === 'SUCCESS' ? 'Успешно' : (tx.status === 'REJECTED' ? 'Отклонено' : 'В обработке');
                        let btnHtml = tx.status === 'SUCCESS' ? `<button class="btn-secondary" onclick="requestReceipt('${tx.tx_id}')" style="margin-top:8px;">Скачать чек</button>` : '';
                        
                        container.innerHTML += `
                            <div class="history-card">
                                <div class="h-left">
                                    <div class="h-title">${tx.country}</div>
                                    <div class="h-desc">Код: ${tx.tx_id}</div>
                                    ${btnHtml}
                                </div>
                                <div class="h-right">
                                    <div class="h-amount">${tx.rub} ₽</div>
                                    <div class="badge ${bClass}">${bText}</div>
                                </div>
                            </div>
                        `;
                    });
                } catch(e) { container.innerHTML = '<div style="text-align:center; padding: 20px; color: var(--danger);">Ошибка загрузки</div>'; }
            }

            async function requestReceipt(tx_id) {
                haptic();
                let user_id = tg.initDataUnsafe?.user?.id || 0;
                try {
                    let response = await fetch('/api/receipt', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ initData: tg.initData, tx_id: tx_id, user_id: user_id })
                    });
                    let res = await response.json();
                    if(res.status === 'success') { tg.showAlert('Чек успешно сгенерирован и отправлен вам в чат бота!'); tg.close(); }
                    else { tg.showAlert('Не удалось получить чек.'); }
                } catch(e) { tg.showAlert('Ошибка связи с сервером.'); }
            }

            async function sendSupportMessage() {
                haptic();
                let msg = document.getElementById('supportMessage').value.trim();
                if(!msg) { tg.showAlert('Пожалуйста, опишите вашу проблему.'); return; }
                
                let user = tg.initDataUnsafe?.user || {};
                try {
                    let response = await fetch('/api/support', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ initData: tg.initData, message: msg, username: user.username, user_id: user.id })
                    });
                    let result = await response.json();
                    if(result.status === 'success') {
                        tg.showAlert('Обращение отправлено! Мы ответим в ближайшее время.');
                        document.getElementById('supportMessage').value = '';
                    } else tg.showAlert('Ошибка отправки.');
                } catch(e) { tg.showAlert('Ошибка связи.'); }
            }

            function startTimer(duration) {
                let timer = duration, minutes, seconds;
                clearInterval(timerInterval);
                timerInterval = setInterval(function () {
                    minutes = parseInt(timer / 60, 10); seconds = parseInt(timer % 60, 10);
                    minutes = minutes < 10 ? "0" + minutes : minutes; seconds = seconds < 10 ? "0" + seconds : seconds;
                    document.getElementById('timerDisplay').textContent = minutes + ":" + seconds;
                    if (--timer < 0) { clearInterval(timerInterval); alert('Сессия истекла.'); location.reload(); }
                }, 1000);
            }

            async function initiateTransfer() {
                haptic();
                enteredRub = parseFloat(document.getElementById('amount').value) || 0;
                let card = document.getElementById('recCard').value.replace(/\s+/g, '');
                let minLimit = (currentCurr === 'EUR' || currentCurr === 'USD') ? 5000 : 1000;
                
                if (enteredRub < minLimit || enteredRub > 25000) { tg.showAlert(`Сумма от ${minLimit.toLocaleString('ru-RU')} до 25 000 ₽`); return; }
                if (card.length < 12) { tg.showAlert('Проверьте номер карты'); return; }
                let recNameInput = document.getElementById('recName').value.trim();
                if (!recNameInput) { tg.showAlert('Укажите ФИО получателя'); return; }
                if (!document.getElementById('termsCheck').checked) { tg.showAlert('Необходимо согласиться с Офертой'); return; }

                currentOrderCode = 'KORO-' + Math.floor(1000 + Math.random() * 9000);
                document.getElementById('transferCommentText').textContent = currentOrderCode;
                
                let actualRubToPay = Math.max(0, enteredRub - appliedBonus);
                document.getElementById('payRubSum').textContent = actualRubToPay.toLocaleString('ru-RU') + ' ₽';
                
                saveNewRecipient(recNameInput, document.getElementById('recCard').value, document.getElementById('recipientBank').value);
                localStorage.removeItem('koro_amount');

                document.getElementById('bottomNav').style.display = 'none';
                switchTab('tab-payment', null);
                startTimer(900);
            }

            async function startCryptoPay() {
                haptic();
                let btn = document.getElementById('btnCryptoPay');
                btn.disabled = true; btn.textContent = 'Создаем счет...';
                
                let user = tg.initDataUnsafe?.user || {};
                let actualRubToPay = Math.max(0, enteredRub - appliedBonus);

                try {
                    let response = await fetch('/api/crypto/create', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ initData: tg.initData, rub_amount: actualRubToPay, tx_id: currentOrderCode })
                    });
                    let result = await response.json();
                    
                    if (result.status === 'success') {
                        currentInvoiceId = result.invoice_id;
                        await registerOrderInDB('CRYPTO');
                        
                        tg.openTelegramLink(result.pay_url);
                        
                        document.getElementById('successTitle').textContent = "Ожидание CryptoPay";
                        document.getElementById('successDesc').innerHTML = "Мы создали счет в крипте.<br>Оплатите его в боте CryptoBot, затем нажмите кнопку ниже, чтобы деньги автоматически улетели получателю.";
                        document.getElementById('btnCheckCrypto').style.display = "block";
                        switchTab('tab-success', null);
                    } else {
                        tg.showAlert(result.message || 'Ошибка крипто-шлюза.');
                        btn.disabled = false; btn.textContent = '💎 Оплатить криптой (Автоматически)';
                    }
                } catch (e) { tg.showAlert('Ошибка связи с сервером.'); btn.disabled = false; }
            }

            async function checkCryptoPayment() {
                haptic();
                let btn = document.getElementById('btnCheckCrypto');
                btn.disabled = true; btn.textContent = 'Проверка...';
                try {
                    let response = await fetch('/api/crypto/check', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ invoice_id: currentInvoiceId, tx_id: currentOrderCode })
                    });
                    let result = await response.json();
                    if (result.status === 'paid') {
                        tg.showAlert('Оплата найдена! Средства автоматически отправлены получателю.');
                        tg.close();
                    } else {
                        tg.showAlert('Счет еще не оплачен. Если вы уже перевели крипту, подождите 30 секунд и нажмите снова.');
                        btn.disabled = false; btn.textContent = 'Обновить статус оплаты';
                    }
                } catch (e) { btn.disabled = false; btn.textContent = 'Обновить статус оплаты'; }
            }

            async function confirmPayment() {
                haptic();
                let btn = document.getElementById('btnConfirmPay');
                btn.disabled = true; btn.textContent = 'Обработка...';
                let success = await registerOrderInDB('MANUAL');
                if (success) switchTab('tab-success', null);
                else { btn.disabled = false; btn.textContent = 'Я перевел(а) на Озон Банк'; }
            }

            async function registerOrderInDB(method) {
                let user = tg.initDataUnsafe?.user || {};
                clearInterval(timerInterval);
                try {
                    let response = await fetch('/api/order', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            initData: tg.initData,
                            country: document.getElementById('country').value.split('|')[0],
                            recipient_bank: document.getElementById('recipientBank').value,
                            rub_amount: enteredRub + ' ₽',
                            local_received: calculatedLocal.toFixed(2),
                            currency: currentCurr,
                            recipient_name: document.getElementById('recName').value.trim(),
                            recipient_card: document.getElementById('recCard').value,
                            transfer_comment: currentOrderCode,
                            promo: document.getElementById('promoCode').value.trim().toUpperCase() || 'Нет',
                            bonus_used: appliedBonus,
                            username: user.username || 'Аноним', user_id: user.id || 0
                        })
                    });
                    return response.ok;
                } catch (e) { tg.showAlert('Ошибка связи с сервером.'); return false; }
            }
        </script>
    </body>
    </html>
    """.replace("ACTUAL_SYSTEM_CARD", current_card)
    return web.Response(text=html_content, content_type="text/html")


async def main():
    await init_db()
    app = web.Application()
    app.router.add_get("/", webapp_handler)
    app.router.add_get("/api/profile", api_profile_handler)
    app.router.add_get("/api/history", api_history_handler)
    app.router.add_post("/api/order", api_order_handler)
    
    app.router.add_post("/api/receipt", api_request_receipt)
    app.router.add_post("/api/support", api_support_handler)
    
    app.router.add_post("/api/crypto/create", api_crypto_create)
    app.router.add_post("/api/crypto/check", api_crypto_check)
    
    runner = web.AppRunner(app)
    await setup_runner(runner)

async def setup_runner(runner):
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 8080)))
    await site.start()
    asyncio.create_task(update_rates())
    logging.info(f"Сервер Koro Pay запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())