import asyncio
import sqlite3
import random
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.bot import DefaultBotProperties
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

API_TOKEN = "7586567791:AAFPFlu8mswOMARiV01wsGEuTtGXCB_sjBE"


# --- FSM ---
class DictFSM(StatesGroup):
    waiting_for_dict_name = State()
    waiting_for_word_eng = State()
    waiting_for_word_rus = State()


# --- Init ---
dp = Dispatcher(storage=MemoryStorage())
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


# --- DB ---
def init_db():
    with sqlite3.connect("words.db") as conn:
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
        c.execute("""CREATE TABLE IF NOT EXISTS dictionaries (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        name TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS words (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        dict_id INTEGER,
                        eng TEXT,
                        rus TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS ratings (
                        user_id INTEGER,
                        dict_id INTEGER,
                        last_score INTEGER,
                        best_score INTEGER,
                        total_words INTEGER,
                        PRIMARY KEY (user_id, dict_id))""")
        conn.commit()


init_db()


# --- DB helpers ---
def get_dicts(user_id):
    with sqlite3.connect("words.db") as conn:
        c = conn.cursor()
        c.execute("SELECT name FROM dictionaries WHERE user_id = ?", (user_id,))
        return [row[0] for row in c.fetchall()]


def get_dict_id(user_id, dict_name):
    with sqlite3.connect("words.db") as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM dictionaries WHERE user_id = ? AND name = ?", (user_id, dict_name))
        row = c.fetchone()
        return row[0] if row else None


# --- Handlers ---
@dp.message(Command("start"))
async def start(message: Message):
    with sqlite3.connect("words.db") as conn:
        conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Мои словари", callback_data="list_dicts")],
        [InlineKeyboardButton(text="➕ Создать словарь", callback_data="create_dict")]
    ])
    await message.answer("👋 Добро пожаловать! Выберите действие:", reply_markup=kb)


@dp.callback_query(F.data == "create_dict")
async def create_dict(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите название нового словаря:")
    await state.set_state(DictFSM.waiting_for_dict_name)


@dp.message(DictFSM.waiting_for_dict_name)
async def save_dict(message: Message, state: FSMContext):
    name = message.text.strip()
    with sqlite3.connect("words.db") as conn:
        conn.execute("INSERT INTO dictionaries (user_id, name) VALUES (?, ?)", (message.from_user.id, name))
    await message.answer(f"✅ Словарь <b>{name}</b> создан.")
    await state.clear()


@dp.callback_query(F.data == "list_dicts")
async def list_dicts(callback: CallbackQuery):
    dicts = get_dicts(callback.from_user.id)
    if not dicts:
        await callback.message.answer("У вас пока нет словарей.")
        return
    builder = InlineKeyboardBuilder()
    for name in dicts:
        builder.button(text=name, callback_data=f"dict:{name}")
    await callback.message.answer("Выберите словарь:", reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("dict:"))
async def dict_menu(callback: CallbackQuery):
    name = callback.data.split(":")[1]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить слово", callback_data=f"add:{name}")],
        [InlineKeyboardButton(text="🧠 Тренировка", callback_data=f"train:{name}")],
        [InlineKeyboardButton(text="📈 Рейтинг", callback_data=f"rate:{name}")]
    ])
    await callback.message.answer(f"📘 Словарь <b>{name}</b>:", reply_markup=kb)


@dp.callback_query(F.data.startswith("add:"))
async def add_word(callback: CallbackQuery, state: FSMContext):
    dict_name = callback.data.split(":")[1]
    await state.update_data(dict=dict_name)
    await callback.message.answer("Введите английское слово:")
    await state.set_state(DictFSM.waiting_for_word_eng)


@dp.message(DictFSM.waiting_for_word_eng)
async def input_translation(message: Message, state: FSMContext):
    await state.update_data(eng=message.text.strip())
    await message.answer("Введите перевод:")
    await state.set_state(DictFSM.waiting_for_word_rus)


@dp.message(DictFSM.waiting_for_word_rus)
async def save_word(message: Message, state: FSMContext):
    data = await state.get_data()
    dict_id = get_dict_id(message.from_user.id, data["dict"])
    eng, rus = data["eng"], message.text.strip()
    with sqlite3.connect("words.db") as conn:
        c = conn.cursor()
        c.execute("INSERT INTO words (dict_id, eng, rus) VALUES (?, ?, ?)", (dict_id, eng.lower(), rus.lower()))
        c.execute("DELETE FROM ratings WHERE user_id = ? AND dict_id = ?", (message.from_user.id, dict_id))
    await message.answer(f"✅ Слово <b>{eng}</b> — <b>{rus}</b> добавлено. Рейтинг сброшен.")
    await state.clear()


# --- Тренировка ---
user_sessions = {}


@dp.callback_query(F.data.startswith("train:"))
async def train(callback: CallbackQuery):
    name = callback.data.split(":")[1]
    dict_id = get_dict_id(callback.from_user.id, name)
    with sqlite3.connect("words.db") as conn:
        c = conn.cursor()
        c.execute("SELECT eng, rus FROM words WHERE dict_id = ?", (dict_id,))
        words = c.fetchall()
    if not words:
        await callback.message.answer("❗ В словаре нет слов.")
        return
    random.shuffle(words)
    user_sessions[callback.from_user.id] = {
        "words": words, "index": 0, "correct": 0, "mistakes": [], "dict_id": dict_id
    }
    await callback.message.answer(f"Как переводится: <b>{words[0][0]}</b>?")


@dp.message()
async def answer_check(message: Message):
    if message.from_user.id not in user_sessions:
        return
    session = user_sessions[message.from_user.id]
    eng, rus = session["words"][session["index"]]
    if message.text.strip().lower() == rus.lower():
        session["correct"] += 1
    else:
        session["mistakes"].append((eng, rus))
    session["index"] += 1
    if session["index"] < len(session["words"]):
        next_word = session["words"][session["index"]][0]
        await message.answer(f"Как переводится: <b>{next_word}</b>?")
    else:
        total, correct = len(session["words"]), session["correct"]
        dict_id = session["dict_id"]
        with sqlite3.connect("words.db") as conn:
            c = conn.cursor()
            c.execute(
                "INSERT OR IGNORE INTO ratings (user_id, dict_id, last_score, best_score, total_words) VALUES (?, ?, 0, 0, ?)",
                (message.from_user.id, dict_id, total))
            c.execute(
                "UPDATE ratings SET last_score = ?, best_score = MAX(best_score, ?), total_words = ? WHERE user_id = ? AND dict_id = ?",
                (correct, correct, total, message.from_user.id, dict_id))
        response = f"✅ Правильно: <b>{correct}/{total}</b>\n"
        if session["mistakes"]:
            response += "\n❌ Ошибки:\n" + "\n".join([f"{e} — {r}" for e, r in session["mistakes"]])
        await message.answer(response)
        user_sessions.pop(message.from_user.id)


# --- Рейтинг ---
@dp.callback_query(F.data.startswith("rate:"))
async def show_rating(callback: CallbackQuery):
    name = callback.data.split(":")[1]
    dict_id = get_dict_id(callback.from_user.id, name)
    with sqlite3.connect("words.db") as conn:
        c = conn.cursor()
        c.execute("SELECT last_score, best_score, total_words FROM ratings WHERE user_id = ? AND dict_id = ?",
                  (callback.from_user.id, dict_id))
        row = c.fetchone()
    if row:
        last, best, total = row
        await callback.message.answer(
            f"📈 Рейтинг для <b>{name}</b>\n"
            f"Последняя попытка: {last}/{total}\n"
            f"Лучшая попытка: {best}/{total}"
        )
    else:
        await callback.message.answer("Нет данных о рейтинге для этого словаря.")


# --- Run ---
if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))
