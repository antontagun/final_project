import asyncio
import sqlite3
import random
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.client.bot import DefaultBotProperties
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
import os
from googletrans import Translator

API_TOKEN = "BOT_API_TOKEN"


# --- FSM ---
class DictFSM(StatesGroup):
    waiting_for_dict_name = State()
    waiting_for_word_eng = State()
    waiting_for_word_rus = State()


class DeleteWordFSM(StatesGroup):
    waiting_for_eng_word = State()
    waiting_for_rus_word = State()


class TestFSM(StatesGroup):
    waiting_for_answer = State()


class TranslateFSM(StatesGroup):
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


translator = Translator()


async def translate_and_add(message: Message, direction: str, state: FSMContext):
    text = message.text.strip()
    if not text:
        await message.answer("❌ Пожалуйста, введи слово для перевода.")
        return

    src, dest = ('ru', 'en') if direction == 'to_en' else ('en', 'ru')

    try:
        result = translator.translate(text, src=src, dest=dest)
        await state.update_data(eng=result.text.lower() if dest == 'en' else text.lower(),
                                rus=text.lower() if dest == 'en' else result.text.lower())
        dicts = get_dicts(message.from_user.id)
        if not dicts:
            await message.answer("❤️У тебя ещё нет словарей, создай сначала словарь!❤️")
            await state.clear()
            return

        builder = InlineKeyboardBuilder()

        for name in dicts:
            builder.button(text=name, callback_data=f"save_trans:{name}")
        await message.answer(f"❤️Перевод: <b>{text}</b> ➡ <b>{result.text}</b>\n\nВыбери словарь для добавления:",
                             reply_markup=builder.as_markup())
    except Exception as e:
        await message.answer(f"❌ Ошибка перевода: {e}")
        await state.clear()


# --- Главный экран ---
@dp.message(Command("start"))
async def start(message: Message):
    with sqlite3.connect("words.db") as conn:
        conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Словари", callback_data="menu_dicts")],
        [InlineKeyboardButton(text="🧪 Тесты", callback_data="menu_tests")],
        [InlineKeyboardButton(text="🌍 Перевести", callback_data="menu_translate")]
    ])
    await message.answer("❤️Привет пупсик!❤️ 🐾 Выбери, что хочешь делать, пупсик:", reply_markup=kb)


# --- Словари ---
@dp.callback_query(F.data == "menu_dicts")
async def menu_dicts(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Мои словари", callback_data="list_dicts")],
        [InlineKeyboardButton(text="➕ Создать словарь", callback_data="create_dict")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])
    await callback.message.answer("❤️Зай, в разделе 'Словари' тебе доступны такие штуки:", reply_markup=kb)


@dp.callback_query(F.data == "main_menu")
async def back_to_main(callback: CallbackQuery):
    await start(callback.message)


@dp.callback_query(F.data == "create_dict")
async def create_dict(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("❤️Пупсик, напиши название нового словаря, пожалуйста~❤️")
    await state.set_state(DictFSM.waiting_for_dict_name)


@dp.message(DictFSM.waiting_for_dict_name)
async def save_dict(message: Message, state: FSMContext):
    name = message.text.strip()
    with sqlite3.connect("words.db") as conn:
        conn.execute("INSERT INTO dictionaries (user_id, name) VALUES (?, ?)", (message.from_user.id, name))
    await message.answer(f"❤️Заюшь, словарь <b>{name}</b> создан! 🐾")
    await state.clear()


@dp.callback_query(F.data == "list_dicts")
async def list_dicts(callback: CallbackQuery):
    dicts = get_dicts(callback.from_user.id)
    if not dicts:
        await callback.message.answer("❤️Ой, у тебя пока нет словарей, зайчонок.❤️")
        return
    builder = InlineKeyboardBuilder()
    for name in dicts:
        builder.button(text=name, callback_data=f"dict:{name}")
    builder.button(text="🔙 Назад", callback_data="menu_dicts")
    await callback.message.answer("❤️Зай, выбери словарик, пожалуйста:", reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("dict:"))
async def dict_menu(callback: CallbackQuery):
    name = callback.data.split(":")[1]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить слово", callback_data=f"add:{name}")],
        [InlineKeyboardButton(text="🧠 Тренировка", callback_data=f"train:{name}")],
        [InlineKeyboardButton(text="📄 Показать слова", callback_data=f"show:{name}")],
        [InlineKeyboardButton(text="📈 Рейтинг", callback_data=f"rate:{name}")],
        [InlineKeyboardButton(text="🗑️ Удалить перевод", callback_data=f"del:{name}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="list_dicts")]
    ])
    await callback.message.answer(f"❤️Заюшь, ты в словаре <b>{name}</b>: что хочешь сделать?❤️", reply_markup=kb)


@dp.callback_query(F.data.startswith("add:"))
async def add_word(callback: CallbackQuery, state: FSMContext):
    dict_name = callback.data.split(":")[1]
    await state.update_data(dict=dict_name)
    await callback.message.answer("❤️Пупсик, напиши, пожалуйста, английское слово для добавления!❤️")
    await state.set_state(DictFSM.waiting_for_word_eng)


@dp.callback_query(F.data.startswith("show:"))
async def show_words(callback: CallbackQuery):
    dict_name = callback.data.split(":")[1]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_dicts")]
    ])
    dict_id = get_dict_id(callback.from_user.id, dict_name)
    with sqlite3.connect("words.db") as conn:
        c = conn.cursor()
        c.execute("SELECT eng, rus FROM words WHERE dict_id = ?", (dict_id,))
        words = c.fetchall()

    if not words:
        await callback.message.answer("❤️Слов в этом словаре пока нет, зайчик!❤️")
        return

    message_text = f"<b>📄 Слова из словаря {dict_name}:</b>\n\n"
    for eng, rus in words:
        message_text += f"🔹 <b>{eng}</b> — {rus}\n"

    await callback.message.answer(message_text, reply_markup=kb)


@dp.message(DictFSM.waiting_for_word_eng)
async def input_translation(message: Message, state: FSMContext):
    await state.update_data(eng=message.text.strip())
    await message.answer("❤️Теперь пиши перевод этого слова, пупсик!❤️")
    await state.set_state(DictFSM.waiting_for_word_rus)


@dp.message(DictFSM.waiting_for_word_rus)
async def save_word(message: Message, state: FSMContext):
    data = await state.get_data()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="list_dicts")]
    ])
    dict_id = get_dict_id(message.from_user.id, data["dict"])
    eng = data["eng"].strip().lower()
    new_rus = message.text.strip().lower()

    with sqlite3.connect("words.db") as conn:
        c = conn.cursor()
        # Проверка, есть ли слово уже
        c.execute("SELECT id, rus FROM words WHERE dict_id = ? AND eng = ?", (dict_id, eng))
        row = c.fetchone()
        if row:
            word_id, existing_rus = row
            existing_set = set(map(str.strip, existing_rus.split(";")))
            new_set = set(map(str.strip, new_rus.split(";")))
            combined = sorted(existing_set.union(new_set))
            updated_rus = ";".join(combined)
            c.execute("UPDATE words SET rus = ? WHERE id = ?", (updated_rus, word_id))
        else:
            c.execute("INSERT INTO words (dict_id, eng, rus) VALUES (?, ?, ?)", (dict_id, eng, new_rus))

        c.execute("DELETE FROM ratings WHERE user_id = ? AND dict_id = ?", (message.from_user.id, dict_id))

    await message.answer(
        f"❤️Заюшь, слово <b>{eng}</b> — <b>{new_rus}</b> добавлено или обновлено, пупсик! Рейтинг сброшен.❤️",
        reply_markup=kb)
    await state.clear()


@dp.callback_query(F.data.startswith("del:"))
async def start_delete_word(callback: CallbackQuery, state: FSMContext):
    dict_name = callback.data.split(":")[1]
    await state.update_data(dict=dict_name)
    await state.set_state(DeleteWordFSM.waiting_for_eng_word)
    await callback.message.answer("❤️Зай, напиши английское слово, у которое хочешь удалить.")


@dp.message(DeleteWordFSM.waiting_for_eng_word)
async def delete_translation_fsm(message: Message, state: FSMContext):
    await state.update_data(eng=message.text.strip().lower())
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_dicts")]
    ])
    data = await state.get_data()
    dict_name = data["dict"]
    eng = data["eng"]
    dict_id = get_dict_id(message.from_user.id, dict_name)

    with sqlite3.connect("words.db") as conn:
        c = conn.cursor()
        c.execute("SELECT id, rus FROM words WHERE dict_id = ? AND eng = ?", (dict_id, eng))
        row = c.fetchone()

        if not row:
            await message.answer("❌ Слово не найдено в этом словаре.", reply_markup=kb)
            await state.clear()
            return

        c = conn.cursor()
        c.execute("DELETE FROM words WHERE dict_id = ? AND eng = ?", (dict_id, eng))
        row = c.fetchone()
    await message.answer("❤️Зай, слово удаленно.", reply_markup=kb)

    await state.clear()


# --- Тесты ---
@dp.callback_query(F.data == "menu_tests")
async def menu_tests(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎧 Listening tests", callback_data="test_listen")],
        [InlineKeyboardButton(text="✍️ Writing tests", callback_data="test_writ")],
        [InlineKeyboardButton(text="📖 Reading tests", callback_data="test_read")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])
    await callback.message.answer("❤️Пупсик, выбери, что хочешь потестить:", reply_markup=kb)


@dp.callback_query(F.data.in_(["test_listen", "test_writ", "test_read"]))
async def variant_menu(callback: CallbackQuery, state: FSMContext):
    test_type = callback.data.replace("test_", "")  # listen, write, read
    await state.update_data(test_type=test_type + "ing")  # listening, writing, reading
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Вариант 1", callback_data="var1")],
        [InlineKeyboardButton(text="Вариант 2", callback_data="var2")],
        [InlineKeyboardButton(text="Вариант 3", callback_data="var3")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_tests")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    await callback.message.answer("❤️Зайчонок, выбери вариант теста, пожалуйста!❤️", reply_markup=kb)


@dp.callback_query(F.data.in_(["var1", "var2", "var3"]))
async def start_test(callback: CallbackQuery, state: FSMContext):
    variant = callback.data[-1]  # "1", "2" или "3"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_tests")]
    ])
    user_data = await state.get_data()
    test_type = user_data.get("test_type")  # слушай / пиши / читай

    base_dir = test_type.lower()  # listening, writing, reading
    question_path = os.path.join(base_dir, "questions", variant)
    answer_path = os.path.join(base_dir, "answers", f"{variant}.txt")

    # Сохраняем для дальнейшей проверки
    await state.update_data(variant=variant, test_type=base_dir)

    if base_dir == "listening":
        # отправка аудио
        audio_file = os.path.join(question_path, "audio.mp3")
        questions_file = os.path.join(question_path, "questions.txt")
        if not os.path.exists(audio_file) or not os.path.exists(questions_file):
            await callback.message.answer("❌ Не удалось найти файлы теста.", reply_markup=kb)
            return
        audio = FSInputFile(audio_file)
        await callback.message.answer_audio(audio=audio)
        with open(questions_file, "r", encoding="utf-8") as f:
            text = f.read()
        await callback.message.answer(f"<b>Вопросы:</b>\n{text}")

    else:
        # Writing/Reading
        question_file = os.path.join(base_dir, "questions", f"{variant}.txt")
        if not os.path.exists(question_file):
            await callback.message.answer("❌ Не удалось найти файлы теста.", reply_markup=kb)
            return
        with open(question_file, "r", encoding="utf-8") as f:
            text = f.read()
        await callback.message.answer(f"<b>Вопросы:</b>\n{text}")

    await callback.message.answer("📝 Напиши свой ответ сообщением.")
    await state.set_state(TestFSM.waiting_for_answer)


@dp.message(TestFSM.waiting_for_answer)
async def check_test_answer(message: Message, state: FSMContext):
    data = await state.get_data()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_tests")]
    ])
    variant = data["variant"]
    base_dir = data["test_type"]
    answer_file = os.path.join(base_dir, "answers", f"{variant}.txt")

    if not os.path.exists(answer_file):
        await message.answer("❌ Ответ не найден.", reply_markup=kb)
        await state.clear()
        return

    with open(answer_file, "r", encoding="utf-8") as f:
        correct_answer = f.read().strip().lower()

    user_answer = message.text.strip().lower()

    if user_answer == correct_answer:
        result = "✅ <b>Верно!</b> Молодец, пупсик!"
    else:
        result = f"❌ <b>Неверно.</b>\nОжидалось:\n{correct_answer}"

    await message.answer(result, parse_mode="HTML", reply_markup=kb)
    await state.clear()


@dp.callback_query(F.data == "menu_translate")
async def translate_menu(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 ➡ 🇬🇧 На английский", callback_data="to_en")],
        [InlineKeyboardButton(text="🇬🇧 ➡ 🇷🇺 На русский", callback_data="to_ru")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])
    await callback.message.answer("❤️Выбери направление перевода, пупсик:", reply_markup=kb)


@dp.callback_query(F.data.in_(["to_en", "to_ru"]))
async def ask_word_to_translate(callback: CallbackQuery, state: FSMContext):
    direction = callback.data
    await state.update_data(translate_direction=direction)
    await callback.message.answer("❤️Введи слово для перевода:")
    await state.set_state(TranslateFSM.waiting_for_word_eng)  # Переиспользуем это состояние


@dp.message(TranslateFSM.waiting_for_word_eng)
async def handle_translation_input(message: Message, state: FSMContext):
    data = await state.get_data()
    if "translate_direction" in data:
        await translate_and_add(message, data["translate_direction"], state)
    else:
        await input_translation(message, state)  # стандартное поведение


@dp.callback_query(F.data.startswith("save_trans:"))
async def save_translated_word(callback: CallbackQuery, state: FSMContext):
    dict_name = callback.data.split(":")[1]
    data = await state.get_data()
    dict_id = get_dict_id(callback.from_user.id, dict_name)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])

    eng = data["eng"]
    rus = data["rus"]

    with sqlite3.connect("words.db") as conn:
        c = conn.cursor()
        c.execute("SELECT id, rus FROM words WHERE dict_id = ? AND eng = ?", (dict_id, eng))
        row = c.fetchone()
        if row:
            word_id, existing_rus = row
            existing_set = set(map(str.strip, existing_rus.split(";")))
            new_set = set(map(str.strip, rus.split(";")))
            combined = sorted(existing_set.union(new_set))
            updated_rus = ";".join(combined)
            c.execute("UPDATE words SET rus = ? WHERE id = ?", (updated_rus, word_id))
        else:
            c.execute("INSERT INTO words (dict_id, eng, rus) VALUES (?, ?, ?)", (dict_id, eng, rus))
        c.execute("DELETE FROM ratings WHERE user_id = ? AND dict_id = ?", (callback.from_user.id, dict_id))

    await callback.message.answer(f"❤️Слово <b>{eng}</b> — <b>{rus}</b> добавлено в словарь <b>{dict_name}</b>!",
                                  reply_markup=kb)
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
        await callback.message.answer("❤️Ой, зайчонок, в словаре нет слов для тренировки!❤️")
        return
    random.shuffle(words)
    user_sessions[callback.from_user.id] = {
        "words": words, "index": 0, "correct": 0, "mistakes": [], "dict_id": dict_id
    }
    await callback.message.answer(f"❤️Как переводится: <b>{words[0][0]}</b>? Умничка!")


@dp.message()
async def answer_check(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_dicts")]
    ])
    if message.from_user.id not in user_sessions:
        return
    session = user_sessions[message.from_user.id]
    eng, rus = session["words"][session["index"]]
    user_answer = message.text.strip().lower()

    # Подсказка, если пользователь не может ответить
    if user_answer == "помощь":
        correct_translation = " / ".join(rus.split(";"))
        await message.answer(f"Подсказка: правильный ответ: {correct_translation}")
        return
    if message.from_user.id not in user_sessions:
        return
    session = user_sessions[message.from_user.id]
    eng, rus = session["words"][session["index"]]
    user_answer = message.text.strip().lower()
    valid_answers = [r.strip() for r in rus.split(";")]
    if user_answer in valid_answers:
        session["correct"] += 1
    else:
        session["mistakes"].append((eng, rus))
    session["index"] += 1
    if session["index"] < len(session["words"]):
        next_word = session["words"][session["index"]][0]
        await message.answer(f"❤️Как переводится: <b>{next_word}</b>? Зай, давай ещё!")
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
        response = f"✅ Правильно, зайчонок: <b>{correct}/{total}</b>\n"
        if session["mistakes"]:
            response += "\n❌ Ошибки:\n" + "\n".join([f"{e} — {r}" for e, r in session["mistakes"]])
        await message.answer(response, reply_markup=kb)
        user_sessions.pop(message.from_user.id)


# --- Рейтинг ---
@dp.callback_query(F.data.startswith("rate:"))
async def show_rating(callback: CallbackQuery):
    name = callback.data.split(":")[1]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_dicts")]
    ])
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
            f"❤️Лучшая❤️ попытка: {best}/{total}", reply_markup=kb
        )
    else:
        await callback.message.answer("❤️Пупсик, нет данных о рейтинге для этого словаря!❤️", reply_markup=kb)


# --- Run ---
if __name__ == "__main__":
    print("bot is started")
    asyncio.run(dp.start_polling(bot))
