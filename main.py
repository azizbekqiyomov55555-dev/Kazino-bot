import random
import sqlite3
import time
import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor

# ================= CONFIG =================
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

if not TOKEN:
    raise ValueError("BOT_TOKEN topilmadi!")

if not ADMIN_ID:
    raise ValueError("ADMIN_ID topilmadi!")

ADMIN_ID = int(ADMIN_ID)

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# ================= DATABASE =================
conn = sqlite3.connect("casino.db")
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

# ================= MENU =================
def main_menu(user_id):
    keyboard = [
        [KeyboardButton("🎮 O‘yinlar")],
        [KeyboardButton("🎁 Bonus"), KeyboardButton("🎟 Promo kod")],
        [KeyboardButton("👥 Referal"), KeyboardButton("👤 Profil")],
        [KeyboardButton("💸 Withdraw")]
    ]

    if user_id == ADMIN_ID:
        keyboard.append([KeyboardButton("👑 Admin Panel")])

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

games_list = ["🎲 Dice","🪙 Coin Flip","🎯 Lucky Shot","🎰 Slot"]

withdraw_data = {}
awaiting_promo = set()
awaiting_bet = set()

# ================= START =================
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    args = message.get_args()

    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)",
                   (message.from_user.id,))

    if args and args.isdigit():
        ref_id = int(args)
        if ref_id != message.from_user.id:
            cursor.execute("UPDATE users SET referred_by=? WHERE user_id=? AND referred_by IS NULL",
                           (ref_id, message.from_user.id))
            cursor.execute("UPDATE users SET balance=balance+50 WHERE user_id=?",
                           (ref_id,))
    conn.commit()

    await message.answer("🎰 Casino Bot", reply_markup=main_menu(message.from_user.id))

# ================= PROFIL =================
@dp.message_handler(lambda m: m.text == "👤 Profil")
async def profile(message: types.Message):
    cursor.execute("SELECT balance,total_bet FROM users WHERE user_id=?",
                   (message.from_user.id,))
    row = cursor.fetchone()

    if row:
        bal, total = row
        await message.answer(
            f"💰 Balans: {bal}\n"
            f"🎯 Umumiy tikilgan: {total}"
        )

# ================= BONUS =================
@dp.message_handler(lambda m: m.text == "🎁 Bonus")
async def bonus(message: types.Message):
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

# ================= PROMO =================
@dp.message_handler(lambda m: m.text == "🎟 Promo kod")
async def promo_start(message: types.Message):
    awaiting_promo.add(message.from_user.id)
    await message.answer("Promo kodni kiriting:")

# ================= GAMES =================
@dp.message_handler(lambda m: m.text == "🎮 O‘yinlar")
async def games(message: types.Message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for g in games_list:
        kb.add(KeyboardButton(g))
    kb.add(KeyboardButton("🔙 Orqaga"))
    await message.answer("O‘yinni tanlang:", reply_markup=kb)

@dp.message_handler(lambda m: m.text in games_list)
async def game_start(message: types.Message):
    awaiting_bet.add(message.from_user.id)
    await message.answer("💵 Stavka kiriting (min 10):")

# ================= UNIVERSAL =================
@dp.message_handler()
async def universal(message: types.Message):
    uid = message.from_user.id
    text = message.text

    # PROMO
    if uid in awaiting_promo:
        awaiting_promo.remove(uid)
        cursor.execute("SELECT reward FROM promocodes WHERE code=?", (text.upper(),))
        row = cursor.fetchone()
        if row:
            reward = row[0]
            cursor.execute("UPDATE users SET balance=balance+? WHERE user_id=?",
                           (reward, uid))
            cursor.execute("DELETE FROM promocodes WHERE code=?", (text.upper(),))
            conn.commit()
            await message.answer(f"🎁 {reward} coin qo‘shildi!")
        else:
            await message.answer("❌ Promo kod xato")
        return

    # BET
    if uid in awaiting_bet and text.isdigit():
        awaiting_bet.remove(uid)
        bet = int(text)

        cursor.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
        row = cursor.fetchone()
        if not row:
            return

        bal = row[0]

        if bet < 10 or bet > bal:
            await message.answer("❌ Stavka xato")
            return

        win = random.random() < 0.3

        if win:
            cursor.execute("UPDATE users SET balance=balance+? WHERE user_id=?",
                           (bet, uid))
            result = f"🎉 YUTDINGIZ! +{bet}"
        else:
            cursor.execute("UPDATE users SET balance=balance-? WHERE user_id=?",
                           (bet, uid))
            result = f"😢 YUTQAZDINGIZ! -{bet}"

        conn.commit()
        await message.answer(result)
        return

# ================= RUN =================
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
