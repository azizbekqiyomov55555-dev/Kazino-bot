import os
import random
import time
import psycopg2
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor

# ================= CONFIG =================
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
DATABASE_URL = os.getenv("DATABASE_URL")

if not TOKEN or not ADMIN_ID or not DATABASE_URL:
    raise ValueError("ENV o'zgaruvchilar to'liq emas!")

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# ================= DATABASE =================
conn = psycopg2.connect(DATABASE_URL, sslmode="require")
conn.autocommit = True
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    balance INTEGER DEFAULT 1000,
    last_bonus BIGINT DEFAULT 0,
    referred_by BIGINT,
    total_bet INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS promocodes (
    code TEXT PRIMARY KEY,
    reward INTEGER
)
""")

cursor.execute("INSERT INTO promocodes (code, reward) VALUES ('BONUS100', 100) ON CONFLICT DO NOTHING")

# ================= MENU =================
def main_menu(user_id):
    keyboard = [
        [KeyboardButton("🎮 O‘yinlar")],
        [KeyboardButton("🎁 Bonus"), KeyboardButton("🎟 Promo kod")],
        [KeyboardButton("👥 Referal"), KeyboardButton("👤 Profil")],
        [KeyboardButton("💸 Pul chiqarish")]
    ]

    if user_id == ADMIN_ID:
        keyboard.append([KeyboardButton("👑 Admin Panel")])

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

games_list = ["🎲 Dice", "🪙 Coin Flip", "🎰 Slot"]
awaiting_bet = {}
awaiting_promo = set()
withdraw_state = {}

# ================= START =================
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user_id = message.from_user.id
    args = message.get_args()

    cursor.execute("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))

    # REFERRAL
    if args and args.isdigit():
        ref_id = int(args)
        if ref_id != user_id:
            cursor.execute("SELECT referred_by FROM users WHERE user_id=%s", (user_id,))
            if cursor.fetchone()[0] is None:
                cursor.execute("UPDATE users SET referred_by=%s WHERE user_id=%s", (ref_id, user_id))
                cursor.execute("UPDATE users SET balance=balance+50 WHERE user_id=%s", (ref_id,))

    await message.answer("🎰 Casino botga xush kelibsiz!", reply_markup=main_menu(user_id))

# ================= PROFIL =================
@dp.message_handler(lambda m: m.text == "👤 Profil")
async def profile(message: types.Message):
    cursor.execute("SELECT balance, total_bet FROM users WHERE user_id=%s", (message.from_user.id,))
    row = cursor.fetchone()

    if row:
        bal, total = row
        await message.answer(f"💰 Balans: {bal}\n🎯 Umumiy tikilgan: {total}")

# ================= REFERAL =================
@dp.message_handler(lambda m: m.text == "👥 Referal")
async def referal(message: types.Message):
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start={message.from_user.id}"
    await message.answer(f"👥 Referal linkingiz:\n{link}\n\nHar taklif uchun +50 coin")

# ================= BONUS =================
@dp.message_handler(lambda m: m.text == "🎁 Bonus")
async def bonus(message: types.Message):
    cursor.execute("SELECT last_bonus FROM users WHERE user_id=%s", (message.from_user.id,))
    last = cursor.fetchone()[0]
    now = int(time.time())

    if now - last < 86400:
        await message.answer("⏳ 24 soatda 1 marta bonus!")
        return

    cursor.execute("UPDATE users SET balance=balance+100, last_bonus=%s WHERE user_id=%s", (now, message.from_user.id))
    await message.answer("🎁 +100 coin qo‘shildi!")

# ================= PROMO =================
@dp.message_handler(lambda m: m.text == "🎟 Promo kod")
async def promo_start(message: types.Message):
    awaiting_promo.add(message.from_user.id)
    await message.answer("Promo kodni kiriting:")

# ================= O‘YINLAR =================
@dp.message_handler(lambda m: m.text == "🎮 O‘yinlar")
async def games(message: types.Message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for g in games_list:
        kb.add(KeyboardButton(g))
    kb.add(KeyboardButton("🔙 Orqaga"))
    await message.answer("O‘yinni tanlang:", reply_markup=kb)

@dp.message_handler(lambda m: m.text in games_list)
async def choose_game(message: types.Message):
    awaiting_bet[message.from_user.id] = message.text
    await message.answer("💵 Stavka kiriting (min 10):")

# ================= WITHDRAW =================
@dp.message_handler(lambda m: m.text == "💸 Pul chiqarish")
async def withdraw(message: types.Message):
    withdraw_state[message.from_user.id] = "amount"
    await message.answer("Necha coin chiqarasiz? (min 100)")

# ================= UNIVERSAL =================
@dp.message_handler()
async def universal(message: types.Message):
    uid = message.from_user.id
    text = message.text

    # PROMO
    if uid in awaiting_promo:
        awaiting_promo.remove(uid)
        cursor.execute("SELECT reward FROM promocodes WHERE code=%s", (text.upper(),))
        row = cursor.fetchone()
        if row:
            reward = row[0]
            cursor.execute("UPDATE users SET balance=balance+%s WHERE user_id=%s", (reward, uid))
            await message.answer(f"🎁 {reward} coin qo‘shildi!")
        else:
            await message.answer("❌ Promo kod xato")
        return

    # BET
    if uid in awaiting_bet and text.isdigit():
        bet = int(text)
        cursor.execute("SELECT balance FROM users WHERE user_id=%s", (uid,))
        bal = cursor.fetchone()[0]

        if bet < 10 or bet > bal:
            await message.answer("❌ Stavka xato")
            return

        win = random.random() < 0.3

        if win:
            cursor.execute("UPDATE users SET balance=balance+%s WHERE user_id=%s", (bet, uid))
            result = f"🎉 Yutdingiz +{bet}"
        else:
            cursor.execute("UPDATE users SET balance=balance-%s WHERE user_id=%s", (bet, uid))
            result = f"😢 Yutqazdingiz -{bet}"

        cursor.execute("UPDATE users SET total_bet=total_bet+%s WHERE user_id=%s", (bet, uid))
        del awaiting_bet[uid]

        await message.answer(result)
        return

    # WITHDRAW STEPS
    if uid in withdraw_state:

        if withdraw_state[uid] == "amount" and text.isdigit():
            amount = int(text)

            cursor.execute("SELECT balance FROM users WHERE user_id=%s", (uid,))
            bal = cursor.fetchone()[0]

            if amount < 100 or amount > bal:
                await message.answer("❌ Balans yetarli emas yoki min 100")
                return

            withdraw_state[uid] = amount
            await message.answer("Karta raqamini kiriting:")
            return

        if isinstance(withdraw_state[uid], int):
            amount = withdraw_state[uid]
            card = text

            cursor.execute("UPDATE users SET balance=balance-%s WHERE user_id=%s", (amount, uid))

            kb = InlineKeyboardMarkup()
            kb.add(
                InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"ok_{uid}_{amount}"),
                InlineKeyboardButton("❌ Bekor qilish", callback_data=f"no_{uid}_{amount}")
            )

            await bot.send_message(
                ADMIN_ID,
                f"💸 Yangi withdraw\nUser: {uid}\nSumma: {amount}\nKarta: {card}",
                reply_markup=kb
            )

            await message.answer("⏳ So‘rov yuborildi!")
            del withdraw_state[uid]
            return

# ================= CALLBACK =================
@dp.callback_query_handler(lambda c: c.data.startswith(("ok_", "no_")))
async def callback_handler(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    action, uid, amount = callback.data.split("_")
    uid = int(uid)
    amount = int(amount)

    if action == "ok":
        await bot.send_message(uid, "✅ Pul chiqarish tasdiqlandi!")
        await callback.message.edit_text("✅ Tasdiqlandi")
    else:
        cursor.execute("UPDATE users SET balance=balance+%s WHERE user_id=%s", (amount, uid))
        await bot.send_message(uid, "❌ Bekor qilindi")
        await callback.message.edit_text("❌ Bekor qilindi")

# ================= RUN =================
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
