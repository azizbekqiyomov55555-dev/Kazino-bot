import asyncio
import random
import sqlite3
import time
import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
Message, ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.filters import CommandStart

================= CONFIG =================

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

if not TOKEN:
raise ValueError("BOT_TOKEN topilmadi! Railway Variables ga qo‘shing.")

if not ADMIN_ID:
raise ValueError("ADMIN_ID topilmadi! Railway Variables ga qo‘shing.")

ADMIN_ID = int(ADMIN_ID)

bot = Bot(token=TOKEN)
dp = Dispatcher()

================= DATABASE =================

conn = sqlite3.connect("casino.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
user_id INTEGER PRIMARY KEY,
balance INTEGER DEFAULT 1000,
last_bonus INTEGER DEFAULT 0,
referred_by INTEGER,
total_bet INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS withdraws (
id INTEGER PRIMARY KEY AUTOINCREMENT,
user_id INTEGER,
amount INTEGER,
card TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS promocodes (
code TEXT PRIMARY KEY,
reward INTEGER
)
""")

conn.commit()
cursor.execute("INSERT OR IGNORE INTO promocodes VALUES ('BONUS100', 100)")
conn.commit()

================= VIP =================

def get_vip(total_bet):
if total_bet >= 100000:
return "💎 VIP 3"
elif total_bet >= 50000:
return "🥇 VIP 2"
elif total_bet >= 10000:
return "🥈 VIP 1"
else:
return "👤 Oddiy"

================= MENU =================

def main_menu(user_id):
keyboard = [
[KeyboardButton(text="🎮 O‘yinlar")],
[KeyboardButton(text="🎁 Bonus"), KeyboardButton(text="🎟 Promo kod")],
[KeyboardButton(text="👥 Referal"), KeyboardButton(text="👤 Profil")],
[KeyboardButton(text="💸 Withdraw")]
]

if user_id == ADMIN_ID:  
    keyboard.append([KeyboardButton(text="👑 Admin Panel")])  

return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

games_list = [
"🎲 Dice","🪙 Coin Flip","🎯 Lucky Shot",
"🎰 Slot","⚡ Crash","🎴 Card",
"🎱 8 Ball","🎳 Bowling","🎮 Mini Game","🎯 Sniper"
]

withdraw_data = {}
awaiting_promo = set()
awaiting_bet = set()

================= START =================

@dp.message(CommandStart(deep_link=True))
async def start(message: Message, command: CommandStart):
ref_id = command.args

cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)",  
               (message.from_user.id,))  

if ref_id and ref_id.isdigit():  
    ref_id = int(ref_id)  
    if ref_id != message.from_user.id:  
        cursor.execute("UPDATE users SET referred_by=? WHERE user_id=? AND referred_by IS NULL",  
                       (ref_id, message.from_user.id))  
        cursor.execute("UPDATE users SET balance=balance+50 WHERE user_id=?",  
                       (ref_id,))  
conn.commit()  

await message.answer("🎰 Casino Bot", reply_markup=main_menu(message.from_user.id))

================= PROFIL =================

@dp.message(F.text == "👤 Profil")
async def profile(message: Message):
cursor.execute("SELECT balance,total_bet FROM users WHERE user_id=?",
(message.from_user.id,))
row = cursor.fetchone()

if not row:  
    return  

bal, total = row  
vip = get_vip(total)  

await message.answer(  
    f"💰 Balans: {bal} coin\n"  
    f"🎯 Umumiy tikilgan: {total}\n"  
    f"{vip}"  
)

================= BONUS =================

@dp.message(F.text == "🎁 Bonus")
async def bonus(message: Message):
cursor.execute("SELECT last_bonus FROM users WHERE user_id=?",
(message.from_user.id,))
row = cursor.fetchone()

if not row:  
    return  

last = row[0]  
now = int(time.time())  

if now - last < 86400:  
    await message.answer("⏳ 24 soatda 1 marta!")  
    return  

cursor.execute("UPDATE users SET balance=balance+100, last_bonus=? WHERE user_id=?",  
               (now, message.from_user.id))  
conn.commit()  

await message.answer("🎁 +100 coin qo‘shildi!")

================= PROMO =================

@dp.message(F.text == "🎟 Promo kod")
async def promo_start(message: Message):
awaiting_promo.add(message.from_user.id)
await message.answer("Promo kodni kiriting:")

================= GAMES =================

@dp.message(F.text == "🎮 O‘yinlar")
async def games(message: Message):
kb = ReplyKeyboardMarkup(
keyboard=[[KeyboardButton(text=g)] for g in games_list] + [[KeyboardButton(text="🔙 Orqaga")]],
resize_keyboard=True
)
await message.answer("O‘yinni tanlang:", reply_markup=kb)

@dp.message(F.text.in_(games_list))
async def game_start(message: Message):
awaiting_bet.add(message.from_user.id)
await message.answer("💵 Stavka kiriting (min 10 coin):")

================= WITHDRAW =================

@dp.message(F.text == "💸 Withdraw")
async def withdraw_start(message: Message):
withdraw_data[message.from_user.id] = {"step": "amount"}
await message.answer("💰 Qancha coin?")

================= UNIVERSAL HANDLER =================

@dp.message()
async def universal_handler(message: Message):
uid = message.from_user.id
text = message.text

# PROMO  
if uid in awaiting_promo:  
    awaiting_promo.remove(uid)  
    code = text.upper()  
    cursor.execute("SELECT reward FROM promocodes WHERE code=?", (code,))  
    row = cursor.fetchone()  
    if row:  
        reward = row[0]  
        cursor.execute("UPDATE users SET balance=balance+? WHERE user_id=?",  
                       (reward, uid))  
        cursor.execute("DELETE FROM promocodes WHERE code=?", (code,))  
        conn.commit()  
        await message.answer(f"🎁 {reward} coin qo‘shildi!")  
    else:  
        await message.answer("❌ Promo kod noto‘g‘ri")  
    return  

# BET  
if uid in awaiting_bet and text.isdigit():  
    awaiting_bet.remove(uid)  
    bet = int(text)  

    cursor.execute("SELECT balance,total_bet FROM users WHERE user_id=?", (uid,))  
    row = cursor.fetchone()  
    if not row:  
        return  

    bal, total = row  

    if bet < 10 or bet > bal:  
        await message.answer("❌ Stavka xato")  
        return  

    msg = await message.answer("🎰 Aylanmoqda...")  
    await asyncio.sleep(2)  

    win = random.random() < 0.30  

    cursor.execute("UPDATE users SET total_bet=total_bet+? WHERE user_id=?",  
                   (bet, uid))  

    if win:  
        cursor.execute("UPDATE users SET balance=balance+? WHERE user_id=?",  
                       (bet, uid))  
        result_text = f"🎉 YUTDINGIZ! +{bet}"  
    else:  
        cursor.execute("UPDATE users SET balance=balance-? WHERE user_id=?",  
                       (bet, uid))  
        result_text = f"😢 YUTQAZDINGIZ! -{bet}"  

    conn.commit()  
    await msg.edit_text(result_text)  
    return  

# WITHDRAW  
if uid in withdraw_data:  
    step = withdraw_data[uid]["step"]  

    if step == "amount" and text.isdigit():  
        withdraw_data[uid]["amount"] = int(text)  
        withdraw_data[uid]["step"] = "card"  
        await message.answer("💳 Karta raqami:")  
        return  

    if step == "card":  
        withdraw_data[uid]["card"] = text  
        amount = withdraw_data[uid]["amount"]  

        cursor.execute("SELECT balance FROM users WHERE user_id=?", (uid,))  
        row = cursor.fetchone()  
        if not row:  
            return  

        bal = row[0]  

        if amount > bal:  
            await message.answer("❌ Balans yetarli emas!")  
            withdraw_data.pop(uid)  
            return  

        cursor.execute("UPDATE users SET balance=balance-? WHERE user_id=?",  
                       (amount, uid))  
        cursor.execute("INSERT INTO withdraws (user_id,amount,card) VALUES (?,?,?)",  
                       (uid, amount, text))  
        conn.commit()  

        withdraw_data.pop(uid)  

        await bot.send_message(  
            ADMIN_ID,  
            f"💸 Withdraw\nUser: {uid}\nSumma: {amount}\nKarta: {text}"  
        )  

        await message.answer("✅ So‘rov yuborildi!")  
        return

================= RUN =================

async def main():
await dp.start_polling(bot)

if name == "main":
asyncio.run(main())

Kutubxona ber
