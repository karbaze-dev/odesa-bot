import asyncio
import logging
import sqlite3
import math
import random
import os
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    ReplyKeyboardMarkup, 
    KeyboardButton,
    BotCommand,
    FSInputFile
)

TOKEN = "9271959219:AAG1hj2yp8KaQM7qTf7QUUXWsnIH6KwWzFU"
DB_NAME = "odesa_concierge.db"
DRIVER_PHOTO_PATH = "driver.jpg"  # Ваше фото водія у коріні репозиторію

ADMIN_TELEGRAM_ID = 546552675
MY_TELEGRAM_USERNAME = "karbaze_dev"  # Ваш актуальний нікнейм для зв'язку

user_locations = {}

class FeedbackState(StatesGroup):
    waiting_for_comment = State()

class BookingState(StatesGroup):
    waiting_for_details = State()

class BusinessPartnerState(StatesGroup):
    waiting_for_request = State()

class QuizState(StatesGroup):
    active_question = State()
    score = State()

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            full_name TEXT,
            username TEXT,
            ref_count INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            rating TEXT,
            comment TEXT
        )
    """)
    conn.commit()
    conn.close()

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# ==================== БАЗИ ДАНИХ (ЗАКЛАДИ, ПОДІЇ, УКРИТТЯ) ====================

FOOD_NEAR = [
    {"id": "fn_1", "name": "Кафе «Гоголь-Моголь»", "addr": "вул. Грецька, 8", "rating": "⭐ 4.6 (820 відгуків)", "desc": "Затишна атмосфера, домашня випічка та одеський затишок.", "photo": "https://images.unsplash.com/photo-1554118811-1e0d58224f24?auto=format&fit=crop&w=800&q=80", "lat": 46.4825, "lon": 30.7350},
    {"id": "fn_2", "name": "Кав'ярня «Foundation Coffee Roasters»", "addr": "вул. Жуковського, 19", "rating": "⭐ 4.8 (1450 відгуків)", "desc": "Спешелті кава власного обсмаження та чудові сніданки.", "photo": "https://images.unsplash.com/photo-1555396273-367ea4eb4db5?auto=format&fit=crop&w=800&q=80", "lat": 46.4802, "lon": 30.7412},
    {"id": "fn_3", "name": "Піцерія «Monella»", "addr": "вул. Ланжеронівська, 13", "rating": "⭐ 4.5 (610 відгуків)", "desc": "Справжня неаполітанська піца з печі.", "photo": "https://images.unsplash.com/photo-1559339352-11d035aa65de?auto=format&fit=crop&w=800&q=80", "lat": 46.4855, "lon": 30.7425},
    {"id": "fn_4", "name": "Кафе «Компот»", "addr": "вул. Рішельєвська, 14", "rating": "⭐ 4.4 (2100 відгуків)", "desc": "Фірмові котлетки, свіжий хліб та домашні компоти.", "photo": "https://images.unsplash.com/photo-1550966871-3ed3cdb5ed0c?auto=format&fit=crop&w=800&q=80", "lat": 46.4815, "lon": 30.7390},
    {"id": "fn_5", "name": "«Міський ринок їжі»", "addr": "вул. Рішельєвська, 9", "rating": "⭐ 4.7 (3400 відгуків)", "desc": "Великий вибір локальних фуд-кортів та напоїв під одним дахом.", "photo": "https://images.unsplash.com/photo-1514933651103-005eec06c04b?auto=format&fit=crop&w=800&q=80", "lat": 46.4827, "lon": 30.7383},
]

FOOD_FAR = [
    {"id": "ff_1", "name": "Ресторан «Дача»", "addr": "Французький бульвар, 85", "rating": "⭐ 4.7 (2800 відгуків)", "desc": "Колоритна одеська дача минулого століття.", "photo": "https://images.unsplash.com/photo-1555396273-367ea4eb4db5?auto=format&fit=crop&w=800&q=80", "lat": 46.4485, "lon": 30.7580},
    {"id": "ff_2", "name": "«Риба в огні»", "addr": "Червоний провулок, 1", "rating": "⭐ 4.6 (1300 відгуків)", "desc": "Свіжа морська риба та морепродукти.", "photo": "https://images.unsplash.com/photo-1544025162-d76694265947?auto=format&fit=crop&w=800&q=80", "lat": 46.4870, "lon": 30.7400},
    {"id": "ff_3", "name": "Ресторан «Бабель FISH»", "addr": "вул. Жуковського, 15", "rating": "⭐ 4.7 (940 відгуків)", "desc": "Рибні страви у сучасному виконанні.", "photo": "https://images.unsplash.com/photo-1537047902294-62a40c20a6ae?auto=format&fit=crop&w=800&q=80", "lat": 46.4805, "lon": 30.7410},
    {"id": "ff_4", "name": "Стейк-хаус «М'ясо і Вино»", "addr": "вул. Дерибасівська, 20", "rating": "⭐ 4.6 (1750 відгуків)", "desc": "Найкращі стейки у центрі Одеси.", "photo": "https://images.unsplash.com/photo-1504674900247-0877df9cc836?auto=format&fit=crop&w=800&q=80", "lat": 46.4848, "lon": 30.7370},
    {"id": "ff_5", "name": "Ресторан «Maman»", "addr": "вул. Ланжеронівська, 18", "rating": "⭐ 4.6 (1600 відгуків)", "desc": "Домашня кухня з одеським колоритом.", "photo": "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=800&q=80", "lat": 46.4852, "lon": 30.7430},
]

PLACES_BEACHES = [
    {"id": "pb_1", "name": "Пляж та набережна Ланжерон", "addr": "Ланжерон", "rating": "⭐ 4.6 (4300 відгуків)", "desc": "Найближчий до центру пляж, дельфінарій «Немо».", "photo": "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=800&q=80", "lat": 46.4780, "lon": 30.7540},
    {"id": "pb_2", "name": "Пляж Отрада і Жовтий камінь", "addr": "Отрада", "rating": "⭐ 4.5 (2100 відгуків)", "desc": "Тихий мальовничий район зі старою канатною дорогою.", "photo": "https://images.unsplash.com/photo-1519046904884-53103b34b206?auto=format&fit=crop&w=800&q=80", "lat": 46.4630, "lon": 30.7575},
    {"id": "pb_3", "name": "Аркадія та алея", "addr": "Аркадія", "rating": "⭐ 4.7 (5200 відгуків)", "desc": "Головний курортний центр міста з клубами.", "photo": "https://images.unsplash.com/photo-1519046904884-53103b34b206?auto=format&fit=crop&w=800&q=80", "lat": 46.4420, "lon": 30.7635},
]

PLACES_NATURE = [
    {"id": "pn_1", "name": "Куяльницький лиман", "addr": "Околиця міста", "rating": "⭐ 4.7 (1200 відгуків)", "desc": "Лікувальні грязі та соляні пейзажі.", "photo": "https://images.unsplash.com/photo-1448375240586-882707db888b?auto=format&fit=crop&w=800&q=80", "lat": 46.5600, "lon": 30.7100},
    {"id": "pn_2", "name": "Парк імені Тараса Шевченка", "addr": "Центр / Порт", "rating": "⭐ 4.8 (4900 відгуків)", "desc": "Зелене серце біля центру та стадіон.", "photo": "https://images.unsplash.com/photo-1513836279014-a89f7a76ae86?auto=format&fit=crop&w=800&q=80", "lat": 46.4790, "lon": 30.7480},
    {"id": "pn_3", "name": "Міський сад", "addr": "вул. Дерибасівська", "rating": "⭐ 4.8 (6100 відгуків)", "desc": "Найстаріший парк з музичним фонтаном.", "photo": "https://images.unsplash.com/photo-1513836279014-a89f7a76ae86?auto=format&fit=crop&w=800&q=80", "lat": 46.4845, "lon": 30.7385},
]

PLACES_ARCHITECTURE = [
    {"id": "pa_1", "name": "Одеський театр опери та балету", "addr": "вул. П. Чайковського, 1", "rating": "⭐ 4.9 (8700 відгуків)", "desc": "Шедевр світової архітектури та необароко.", "photo": "https://images.unsplash.com/photo-1513694203232-719a280e022f?auto=format&fit=crop&w=800&q=80", "lat": 46.4855, "lon": 30.7418},
    {"id": "pa_2", "name": "Секретні одеські дворики", "addr": "вул. Спиридонівська / Пастера", "rating": "⭐ 4.7 (650 відгуків)", "desc": "Колодязі, старі галереї та унікальна атмосфера.", "photo": "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=800&q=80", "lat": 46.4820, "lon": 30.7300},
    {"id": "pa_3", "name": "Потьомкінські сходи", "addr": "Приморський бульвар", "rating": "⭐ 4.8 (7500 відгуків)", "desc": "Гігантські східці, що з'єднують місто з портом.", "photo": "https://images.unsplash.com/photo-1513694203232-719a280e022f?auto=format&fit=crop&w=800&q=80", "lat": 46.4868, "lon": 30.7410},
]

SHELTERS_DB = [
    {"name": "Захисна споруда біля Ж/Д Вокзалу", "addr": "Привокзальна площа, 2", "lat": 46.4695, "lon": 30.7415},
    {"name": "Підземний простір / Паркінг (центр)", "addr": "вул. Пушкінська, 35", "lat": 46.4810, "lon": 30.7420},
    {"name": "Пункт незламності (Приморська райадміністрація)", "addr": "вул. Канатна, 134", "lat": 46.4590, "lon": 30.7510},
    {"name": "Укриття у парку Шевченка", "addr": "парк ім. Шевченка (біля стадіону)", "lat": 46.4775, "lon": 30.7490}
]

QUIZ_QUESTIONS = [
    {
        "q": "Питання 1: Що робить справжній одесит, коли не повівся на розмову?",
        "options": [
            ("А) Сходити на Привоз", False),
            ("Б) Сказати «Шо?» у відповідь", True),
            ("В) Поїхати в Аркадію", False)
        ]
    },
    {
        "q": "Питання 2: Як в Одесі правильно називають традиційні маленькі рибні котлетки?",
        "options": [
            ("А) Биточки з тюлечки", True),
            ("Б) Звичайні нагетси", False),
            ("В) Котлети по-київськи", False)
        ]
    },
    {
        "q": "Питання 3: Що зазвичай означає фраза «Не робіть мені нерви»?",
        "options": [
            ("А) Час пити чай", False),
            ("Б) Прохання заспокоїтися і не створювати проблем", True),
            ("В) Поїхати на море", False)
        ]
    }
]

def get_current_events():
    return [
        {
            "id": "ev_1", 
            "name": "Опера «Травіата» Дж. Верді", 
            "addr": "Одеський національний театр опери та балету", 
            "rating": "⭐ 4.9 (950 відгуків)", 
            "desc": "Видатна класична постановка на легендарній сцені.", 
            "photo": "https://images.unsplash.com/photo-1513694203232-719a280e022f?auto=format&fit=crop&w=800&q=80", 
            "lat": 46.4855, "lon": 30.7418
        },
        {
            "id": "ev_2", 
            "name": "Симфонічний концерт при свічках", 
            "addr": "Одеська обласна філармонія (вул. Буніна, 15)", 
            "rating": "⭐ 4.9 (620 відгуків)", 
            "desc": "Світові шедеври кіномузики у виконанні симфонічного оркестру.", 
            "photo": "https://images.unsplash.com/photo-1511192336575-5a79af67a629?auto=format&fit=crop&w=800&q=80", 
            "lat": 46.4815, "lon": 30.7405
        },
        {
            "id": "ev_3", 
            "name": "Виставка українського авангарду", 
            "addr": "Одеський художній музей (вул. Софіївська, 5А)", 
            "rating": "⭐ 4.8 (890 відгуків)", 
            "desc": "Унікальна колекція творів мистецтва початку XX століття.", 
            "photo": "https://images.unsplash.com/photo-1541963463532-d68292c34b19?auto=format&fit=crop&w=800&q=80", 
            "lat": 46.4900, "lon": 30.7350
        },
        {
            "id": "ev_4", 
            "name": "Комедійна вистава «Одеське застілля»", 
            "addr": "Одеський театр музкомедії (вул. Пантелеймонівська, 3)", 
            "rating": "⭐ 4.7 (1100 відгуків)", 
            "desc": "Живий гумор, знайомі життєві ситуації та море сміху.", 
            "photo": "https://images.unsplash.com/photo-1503095396549-807759245b35?auto=format&fit=crop&w=800&q=80", 
            "lat": 46.4730, "lon": 30.7440
        }
    ]

def get_all_places_dict():
    events = get_current_events()
    all_cat = [FOOD_NEAR, FOOD_FAR, PLACES_BEACHES, PLACES_NATURE, PLACES_ARCHITECTURE, events]
    return {item["id"]: item for cat in all_cat for item in cat}

# ==================== ГОЛОВНЕ МЕНЮ ТА ІНЛАЙН КНОПКИ ====================

def get_persistent_reply_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏠 Головне меню"), KeyboardButton(text="📍 Поділитися геолокацією", request_location=True)]
        ],
        resize_keyboard=True,
        is_persistent=True
    )

def get_main_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🚗 Водій, поїздка та клімат", callback_data="category_transport_climate"),
                InlineKeyboardButton(text="🌤️ Погода та афіша", callback_data="menu_weather_events")
            ],
            [
                InlineKeyboardButton(text="🍲 Де поїсти", callback_data="menu_food_cat"),
                InlineKeyboardButton(text="🏛️ Куди сходити", callback_data="menu_places_cat")
            ],
            [
                InlineKeyboardButton(text="🇺🇦 Колесо фортуни (Пророцтва)", callback_data="menu_fortune"),
                InlineKeyboardButton(text="🧠 Тест «Наскільки ти одесит?»", callback_data="menu_odessa_quiz")
            ],
            [
                InlineKeyboardButton(text="💼 Бізнес та партнери (B2B)", callback_data="menu_business"),
                InlineKeyboardButton(text="🛡️ Карта укриттів", callback_data="menu_shelters")
            ],
            [
                InlineKeyboardButton(text="📶 Wi-Fi у салоні", callback_data="menu_wifi"),
                InlineKeyboardButton(text="🤝 Свої люди", callback_data="menu_referral")
            ],
            [
                InlineKeyboardButton(text="📅 Замовити наперед", callback_data="menu_booking"),
                InlineKeyboardButton(text="📖 Одеський словник", callback_data="menu_slang")
            ]
        ]
    )

def get_food_categories_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📍 Поруч зі мною", callback_data="f_near"), InlineKeyboardButton(text="🚗 У центрі", callback_data="f_far")],
            [InlineKeyboardButton(text="⬅️ Головне меню", callback_data="back_main")],
        ]
    )

def get_places_categories_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌊 Пляжі та море", callback_data="p_beaches")],
            [InlineKeyboardButton(text="🌳 Парки та лимани", callback_data="p_nature")],
            [InlineKeyboardButton(text="🏛️ Стара Одеса", callback_data="p_arch")],
            [InlineKeyboardButton(text="⬅️ Головне меню", callback_data="back_main")],
        ]
    )

def get_weather_events_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌤️ Погода зараз", callback_data="get_weather"), InlineKeyboardButton(text="🎭 Велика афіша подій", callback_data="get_events")],
            [InlineKeyboardButton(text="⬅️ Головне меню", callback_data="back_main")],
        ]
    )

def get_transport_climate_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❄️ Зробити прохолодніше", callback_data="atmos_cooler")],
            [InlineKeyboardButton(text="🔥 Зробити тепліше", callback_data="atmos_warmer")],
            [InlineKeyboardButton(text="🤫 Режим тиші (відпочити)", callback_data="atmos_quiet")],
            [InlineKeyboardButton(text="💬 Не проти поспілкуватися", callback_data="atmos_talk")],
            [InlineKeyboardButton(text="🎵 Підключити Bluetooth (S13)", callback_data="tr_bluetooth")],
            [InlineKeyboardButton(text="💳 Залишити чайові", callback_data="tr_tips")],
            [InlineKeyboardButton(text="✍️ Написати відгук", callback_data="tr_review"), InlineKeyboardButton(text="⭐ Оцінити", callback_data="tr_rate")],
            [InlineKeyboardButton(text="⬅️ Головне меню", callback_data="back_main")],
        ]
    )

# ==================== РОЗУМНИЙ ОДЕСЬКИЙ ВІДПОВІДАЧ ====================

def smart_smart_response(text: str) -> str:
    text_lower = text.lower()
    if any(w in text_lower for w in ['привіт', 'здравствуй', 'доброго', 'вечір', 'ранку', 'день']):
        return "Вітаю! Радий бачити вас у салоні Станіслава. Обирайте потрібний розділ у меню нижче, або питайте — підкажемо найкраще в Одесі! 🌊"
    if any(w in text_lower for w in ['ціна', 'стоимость', 'сколько', 'оплата', 'грн', 'поездка']):
        return "Вартість поїздки розраховується через додатки Uklon або Bolt. А для комфорту в дорозі — салон Suzuki Swift повністю до ваших послуг! 🚗✨"
    if any(w in text_lower for w in ['де', 'кафе', 'ресторан', 'поесть', 'кушать', 'їсти', 'голоден']):
        return "В Одесі голодним залишитися неможливо! Натисніть кнопку «🍲 Де поїсти» в меню, і я підберу чудові заклади. 🍽️"
    if any(w in text_lower for w in ['море', 'пляж', 'куда пойти', 'погулять', 'скучно']):
        return "Одеса прекрасна! Зазирніть у розділ «🏛️ Куди сходити» або «🎭 Велика афіша подій» в меню. ⚓"

    responses = [
        "Таки послушайте, в Одессе на любой вопрос есть правильный ответ! Воспользуйтесь кнопками меню ниже. 😊",
        "Ой, не делайте мне нервы, лучше посмотрите меню консьержа — там есть всё, от афиши до ресторанов! 🌊",
        "Главное в дороге — хорошая погода и спокойный водитель Станислав за рулем. 🚗✨",
        "За это мы и любим Одессу! Выбирайте нужный раздел в меню, и мы сделаем вашу поездку незабываемой. 🎶"
    ]
    return random.choice(responses)

# ==================== ХЕНДЛЕРИ ТА ЛОГІКА БОТА ====================

async def set_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Головне меню / Перезапуск")
    ]
    await bot.set_my_commands(commands)

@dp.message(Command("start"))
@dp.message(F.text == "🏠 Головне меню")
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    username = message.from_user.username or ""

    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref"):
        try:
            referrer_id = int(args[1].replace("ref", ""))
            if referrer_id != user_id:
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET ref_count = ref_count + 1 WHERE telegram_id = ?", (referrer_id,))
                conn.commit()
                conn.close()
                await bot.send_message(referrer_id, f"🎉 За вашим посиланням долучився новий пасажир! Вам нараховано бонус.")
        except Exception:
            pass

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO users (telegram_id, full_name, username)
        VALUES (?, ?, ?)
    """, (user_id, full_name, username))
    conn.commit()
    conn.close()

    welcome_caption = (
        f"Шалом і здрастуйте, {full_name}! ⚓️ Вітаю у найзатишнішому екіпажі Одеси.\n\n"
        f"Мене звати **Станіслав**, ваш персональний водій (Suzuki Swift). "
        f"Цей інтерактивний мінігід допоможе зробити вашу поїздку максимально комфортною, цікавою та корисною.\n\n"
        f"Оберіть потрібний розділ у меню нижче 👇"
    )

    await message.answer("👋 Ласкаво просимо на борт!", reply_markup=get_persistent_reply_keyboard())

    if os.path.exists(DRIVER_PHOTO_PATH):
        photo = FSInputFile(DRIVER_PHOTO_PATH)
        await message.answer_photo(
            photo=photo,
            caption=welcome_caption,
            reply_markup=get_main_menu(),
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            welcome_caption,
            reply_markup=get_main_menu(),
            parse_mode="Markdown"
        )

@dp.message(F.location)
async def handle_location(message: types.Message):
    user_locations[message.from_user.id] = (message.location.latitude, message.location.longitude)
    await message.answer("📍 Геолокацію успішно оновлено! Заклади та найближчі укриття сортуються відносно вас.", reply_markup=get_main_menu())

@dp.callback_query(F.data == "back_main")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("Головне меню:", reply_markup=get_main_menu())
    await callback.answer()

@dp.callback_query(F.data == "menu_food_cat")
async def food_cat_menu(callback: types.CallbackQuery):
    await callback.message.answer("🍲 **Оберіть формат пошуку закладів:**", reply_markup=get_food_categories_menu(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "menu_places_cat")
async def places_cat_menu(callback: types.CallbackQuery):
    await callback.message.answer("🏛️ **Оберіть напрямок для прогулянок:**", reply_markup=get_places_categories_menu(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "menu_weather_events")
async def weather_events_menu(callback: types.CallbackQuery):
    await callback.message.answer("🌤️ **Оберіть розділ:**", reply_markup=get_weather_events_menu(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "category_transport_climate")
async def transport_climate_handler(callback: types.CallbackQuery):
    await callback.message.answer(
        "🚗 **Водій, поїздка та клімат в салоні:**\n\n"
        "• **Водій:** Станіслав\n"
        "• **Авто:** Suzuki Swift\n"
        "• **Платформи:** Uklon & Bolt\n\n"
        "Налаштуйте комфорт або оберіть потрібну дію нижче:",
        reply_markup=get_transport_climate_menu(),
        parse_mode="Markdown"
    )
    await callback.answer()

# --- КОЛЕСО ФОРТУНИ / ОДЕСЬКІ ПРОРОЦТВА ---
@dp.callback_query(F.data == "menu_fortune")
async def menu_fortune_handler(callback: types.CallbackQuery):
    fortunes = [
        "✨ Сьогодні вам посміхнеться така удача, шо навіть на Привозі вам зроблять знижку без торга!",
        "🇺🇦 Завжди майте за себе гордість — ви знаходитесь у найколоритнішому місті світу, і все буде Україна!",
        "☕️ На вас чекає день, повний приємних несподінок та смачної кави на Дерибасівській.",
        "🌊 Чорне море змиє всі турботи, а поїздка зі Станіславом зарядить енергією на увесь тиждень!",
        "💰 Фінансовий успіх уже на підході — готуйтеся приймати приємні новини та прибуток.",
        "🚗 Ваша дорога сьогодні буде легкою, зелені світлофори супроводжуватимуть усюди!"
    ]
    chosen_fortune = random.choice(fortunes)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Крутити колесо ще", callback_data="menu_fortune")],
        [InlineKeyboardButton(text="⬅️ Головне меню", callback_data="back_main")]
    ])
    await callback.message.answer(f"🇺🇦 **Колесо фортуни (Одеське пророцтво):**\n\n{chosen_fortune}", reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

# --- МІНІ-ГРА «НАСКІЛЬКИ ТИ ОДЕСИТ?» ---
@dp.callback_query(F.data == "menu_odessa_quiz")
async def menu_quiz_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(QuizState.active_question)
    await state.update_data(current_q=0, score=0)
    await send_quiz_question(callback.message, state, 0, 0)
    await callback.answer()

async def send_quiz_question(message: types.Message, state: FSMContext, q_index: int, score: int):
    if q_index >= len(QUIZ_QUESTIONS):
        await state.clear()
        if score == len(QUIZ_QUESTIONS):
            rank = "👑 Головний магістр одеського гумору та колориту!"
        elif score > 0:
            rank = "⚓ Свій хлопець / Корінний одесит!"
        else:
            rank = "🚶 Турист, який тільки вчиться говорити «Тю!»"
            
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Пройти тест знову", callback_data="menu_odessa_quiz")],
            [InlineKeyboardButton(text="⬅️ Головне меню", callback_data="back_main")]
        ])
        await message.answer(f"🏁 **Тест завершено!**\n\nВаш результат: **{score} з {len(QUIZ_QUESTIONS)}** правильних відповідей.\nВаш одеський ранг: *{rank}*", reply_markup=kb, parse_mode="Markdown")
        return

    q_data = QUIZ_QUESTIONS[q_index]
    inline_rows = []
    for idx, (opt_text, is_correct) in enumerate(q_data["options"]):
        inline_rows.append([InlineKeyboardButton(text=opt_text, callback_data=f"quiz_ans_{q_index}_{idx}")])
    
    inline_rows.append([InlineKeyboardButton(text="❌ Перервати тест", callback_data="back_main")])
    kb = InlineKeyboardMarkup(inline_keyboard=inline_rows)
    
    await message.answer(f"🧠 **Міні-гра: Тест на знання одеської душі**\n\n(Питання {q_index + 1} з {len(QUIZ_QUESTIONS)})\n\n{q_data['q']}", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("quiz_ans_"))
async def process_quiz_answer(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data.split("_")
    q_index = int(data[2])
    opt_index = int(data[3])
    
    user_data = await state.get_data()
    current_q = user_data.get("current_q", 0)
    score = user_data.get("score", 0)
    
    if q_index != current_q:
        await callback.answer("Це питання вже минуло.", show_alert=True)
        return
        
    is_correct = QUIZ_QUESTIONS[q_index]["options"][opt_index][1]
    if is_correct:
        score += 1
        
    next_q = q_index + 1
    await state.update_data(current_q=next_q, score=score)
    
    try:
        await callback.message.delete()
    except Exception:
        pass
        
    await send_quiz_question(callback.message, state, next_q, score)
    await callback.answer()

# --- B2B / ДЛЯ БІЗНЕСУ ТА ПАРТНЕРІВ ---
@dp.callback_query(F.data == "menu_business")
async def menu_business_handler(callback: types.CallbackQuery):
    business_text = (
        "💼 **B2B послуги та партнерство для бізнесу:**\n\n"
        "• **Корпоративні поїздки:** Комфортний трансфер керівництва, зустріч ділових партнерів.\n"
        "• **Експрес-доставка:** Конфіденційна та пунктуальна доставка важливих документів чи посилок.\n"
        "• **Реклама у боті:** Можливість розміщення інформації про ваш заклад чи послуги для пасажирів.\n"
        "• **Довгострокова співпраця:** Закріплення авто за вашою компанією.\n\n"
        "Бажаєте обговорити індивідуальні умови співпраці? Натисніть кнопку нижче:"
    )
    direct_chat_url = f"https://t.me/{MY_TELEGRAM_USERNAME}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Залишити заявку для бізнесу", callback_data="business_request_start")],
        [InlineKeyboardButton(text="💬 Написати напряму", url=direct_chat_url)],
        [InlineKeyboardButton(text="⬅️ Головне меню", callback_data="back_main")]
    ])
    await callback.message.answer(business_text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "business_request_start")
async def business_request_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(BusinessPartnerState.waiting_for_request)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Скасувати", callback_data="back_main")]])
    await callback.message.answer("📝 Напишіть у наступному повідомленні ваші контакти, назву компанії та суть запиту (реклама, доставка чи корпоративні поїздки):", reply_markup=kb)
    await callback.answer()

@dp.message(BusinessPartnerState.waiting_for_request)
async def process_business_request(message: types.Message, state: FSMContext):
    user = message.from_user
    text = message.text
    await state.clear()
    
    admin_text = f"💼 **Нова B2B заявка / партнерство!**\n\n• **Клієнт:** {user.full_name} (@{user.username or 'немає'})\n• **ID:** `{user.id}`\n• **Запит:** {text}"
    try:
        await bot.send_message(chat_id=ADMIN_TELEGRAM_ID, text=admin_text, parse_mode="Markdown")
    except Exception:
        pass
        
    await message.answer("✅ Вашу заявку успішно надіслано Станіславу! Він зв'яжеться з вами найближчим часом для обговорення деталей.", reply_markup=get_main_menu())

# --- КАРТА УКРИТТІВ ЗА ГЕОЛОКАЦІЄЮ ---
@dp.callback_query(F.data == "menu_shelters")
async def menu_shelters_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_lat, user_lon = user_locations.get(user_id, (46.4845, 30.7385))
    
    sorted_shelters = sorted(SHELTERS_DB, key=lambda x: calculate_distance(user_lat, user_lon, x["lat"], x["lon"]))
    closest = sorted_shelters[:3]
    
    text = "🛡️ **Найближчі укриття та пункти незламності:**\n*(відсортовано за вашою геолокацією)*\n\n"
    inline_rows = []
    for i, item in enumerate(closest, 1):
        maps_url = f"https://www.google.com/maps/search/?api=1&query={item['lat']},{item['lon']}"
        text += f"{i}. **{item['name']}**\n   📍 {item['addr']}\n\n"
        inline_rows.append([InlineKeyboardButton(text=f"🗺️ Маршрут до: {item['name']}", url=maps_url)])
        
    inline_rows.append([InlineKeyboardButton(text="⬅️ Головне меню", callback_data="back_main")])
    kb = InlineKeyboardMarkup(inline_keyboard=inline_rows)
    
    await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

# --- WI-FI НА БОРТУ ---
@dp.callback_query(F.data == "menu_wifi")
async def menu_wifi_handler(callback: types.CallbackQuery):
    wifi_text = (
        "📶 **Wi-Fi у салоні автомобіля:**\n\n"
        "• **Назва мережі (SSID):** `Pixel`\n"
        "• **Пароль:** `12345678`\n\n"
        "Користуйтеся інтернетом без обмежень під час поїздки! 🌐"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Головне меню", callback_data="back_main")]])
    await callback.message.answer(wifi_text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

# --- РЕФЕРАЛЬНА ПРОГРАМА ---
@dp.callback_query(F.data == "menu_referral")
async def menu_referral_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref{user_id}"
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT ref_count FROM users WHERE telegram_id = ?", (user_id,))
    row = cursor.fetchone()
    ref_count = row[0] if row else 0
    conn.close()
    
    text = (
        f"🤝 **Система «Свої люди» (Реферальна програма):**\n\n"
        f"Порекомендуйте наш одеський консьєрж-сервіс друзям або колегам!\n"
        f"За кожного запрошеного друга ви отримуєте приємні бонуси та знижки на наступні поїздки.\n\n"
        f"📊 **Запрошених вами друзів:** {ref_count}\n\n"
        f"🔗 **Ваше особисте реферальне посилання:**\n`{ref_link}`"
    )
    
    share_url = f"https://t.me/share/url?url={ref_link}&text=Найкращий%20одеський%20гід%20та%20персональний%20водій!%20Рекомендую%20📲"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поділитися посиланням", url=share_url)],
        [InlineKeyboardButton(text="⬅️ Головне меню", callback_data="back_main")]
    ])
    await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

# --- АТМОСФЕРА В САЛОНІ / КЛІМАТ ---
@dp.callback_query(F.data.startswith("atmos_"))
async def handle_atmosphere_choice(callback: types.CallbackQuery):
    action = callback.data.replace("atmos_", "")
    user = callback.from_user
    texts = {
        "cooler": "❄️ Прохання зробити прохолодніше в салоні",
        "warmer": "🔥 Прохання зробити тепліше в салоні",
        "quiet": "🤫 Режим тиші (пасажир бажає відпочити)",
        "talk": "💬 Пасажир відкритий до розмови"
    }
    msg_text = texts.get(action, "Запит по комфорту")
    
    admin_text = f"⚙️ **Побажання щодо атмосфери!**\n\n• **Пасажир:** {user.full_name} (@{user.username or 'немає'})\n• **ID:** `{user.id}`\n• **Запит:** {msg_text}"
    try:
        await bot.send_message(chat_id=ADMIN_TELEGRAM_ID, text=admin_text, parse_mode="Markdown")
    except Exception:
        pass
        
    await callback.answer("✅ Водію надіслано ваше побажання!", show_alert=True)

# --- БРОНЮВАННЯ НАПЕРЕД ---
@dp.callback_query(F.data == "menu_booking")
async def menu_booking(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(BookingState.waiting_for_details)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Скасувати", callback_data="back_main")]])
    await callback.message.answer(
        "📅 **Замовити поїздку зі Станіславом наперед:**\n\nНапишіть у наступному повідомленні дату, час, маршрут (звідки і куди) та ваші побажання:",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.message(BookingState.waiting_for_details)
async def process_booking(message: types.Message, state: FSMContext):
    user = message.from_user
    text = message.text
    await state.clear()
    
    admin_text = f"📅 **Заявка на попереднє замовлення!**\n\n• **Клієнт:** {user.full_name} (@{user.username or 'немає'})\n• **ID:** `{user.id}`\n• **Деталі:** {text}"
    try:
        await bot.send_message(chat_id=ADMIN_TELEGRAM_ID, text=admin_text, parse_mode="Markdown")
    except Exception:
        pass
        
    await message.answer("✅ Вашу заявку успішно надіслано водію! Він зв'яжеться з вами найближчим часом.", reply_markup=get_main_menu())

# --- ОДЕСЬКИЙ СЛОВНИК ---
@dp.callback_query(F.data == "menu_slang")
async def menu_slang(callback: types.CallbackQuery):
    slang_words = [
        ("«Шо вы говорите?»", "Ввічливий вираз крайнього здивування або невіри."),
        ("«Иметь за себя мнение»", "Бути високої думки про себе."),
        ("«Тю!»", "Універсальний вигук (здивування, досада, заперечення)."),
        ("«Сделать базар»", "Сходити за покупками на ринок (Привоз або Черемушки)."),
        ("«Биточки из тюлечки»", "Кулінарний шедевр і гордість одеської кухні."),
        ("«Не делать мне нервы»", "Прохання заспокоїтися і не створювати зайвих проблем."),
        ("«Шаланды, полные кефали»", "Легендарна фраза, що прославила Одесу на весь світ."),
        ("«Будем иметь что сказать»", "Обов'язково обговоримо всі деталі пізніше."),
        ("«Вы мне не делаете погоду»", "Ваша думка ніяк не впливає на мої плани.")
    ]
    word, desc = random.choice(slang_words)
    text = f"📖 **Одеський словник у дорозі:**\n\n🔸 **{word}** — *{desc}* \n\nНатисніть кнопку нижче, щоб дізнатися інше слово:"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Інше слово", callback_data="menu_slang")],
        [InlineKeyboardButton(text="⬅️ Головне меню", callback_data="back_main")]
    ])
    await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

# --- BLUETOOTH S13 ---
@dp.callback_query(F.data == "tr_bluetooth")
async def transport_bluetooth(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    full_name = callback.from_user.full_name
    username = f"@{callback.from_user.username}" if callback.from_user.username else "немає username"

    notification_text = (
        f"🎵 **Пасажир хоче підключити Bluetooth!**\n\n"
        f"• **Пасажир:** {full_name} ({username})\n"
        f"• **ID:** `{user_id}`\n"
        f"• **Пристрій:** S13"
    )
    try:
        await bot.send_message(chat_id=ADMIN_TELEGRAM_ID, text=notification_text, parse_mode="Markdown")
    except Exception:
        pass

    await callback.message.answer(
        "🎵 **Підключення до аудіосистеми S13:**\n\n"
        "1. Увімкніть **Bluetooth** у налаштуваннях свого телефона.\n"
        "2. Знайдіть мережу **«S13»** та натисніть «Підключити».\n\n"
        "⚠️ Водію вже надіслано сигнал! Гарної музики та поїздки! 🎶",
        reply_markup=get_transport_climate_menu(),
        parse_mode="Markdown"
    )
    await callback.answer()

# --- ПОГОДА ТА АФІША ПОДІЙ ---
@dp.callback_query(F.data == "get_weather")
async def weather_handler(callback: types.CallbackQuery):
    weather_text = (
        "🌤️ **Погода в Одесі зараз:**\n\n"
        "• **Температура повітря:** +14°C (малохмарно)\n"
        "• **Вітер:** Східний, 4 м/с\n"
        "• **Вологість:** 65%\n\n"
        "Чудова погода для прогулянки містом біля моря! 🌊"
    )
    await callback.message.answer(weather_text, reply_markup=get_weather_events_menu(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "get_events")
async def events_handler(callback: types.CallbackQuery):
    events_today = get_current_events()
    current_date_str = datetime.now().strftime("%d.%m.%Y")
    text_lines = f"🎭 **Велика афіша культурних подій в Одесі на {current_date_str}:**\n\n"
    inline_rows = []
    for i, item in enumerate(events_today, 1):
        text_lines += f"{i}. **{item['name']}** {item['rating']}\n   📍 *{item['addr']}*\n\n"
        inline_rows.append([InlineKeyboardButton(text=f"👉 {item['name']}", callback_data=f"show_place_{item['id']}")])

    inline_rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_weather_events")])
    kb = InlineKeyboardMarkup(inline_keyboard=inline_rows)
    await callback.message.answer(text_lines, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

async def send_random_closest_items(callback: types.CallbackQuery, data_list: list, keyboard_to_return):
    user_id = callback.from_user.id
    user_lat, user_lon = user_locations.get(user_id, (46.4845, 30.7385))
    sorted_items = sorted(data_list, key=lambda x: calculate_distance(user_lat, user_lon, x["lat"], x["lon"]))
    selected = random.sample(sorted_items, min(3, len(sorted_items)))
    
    text_lines = "🎲 **Ось найкращі варіанти для вас:**\n\n"
    inline_rows = []
    for i, item in enumerate(selected, 1):
        text_lines += f"{i}. **{item['name']}** {item['rating']}\n   📍 *{item['addr']}*\n\n"
        inline_rows.append([InlineKeyboardButton(text=f"👉 {item['name']}", callback_data=f"show_place_{item['id']}")])

    inline_rows.append([InlineKeyboardButton(text="🎲 Ще варіанти", callback_data=callback.data)])
    inline_rows.append(keyboard_to_return.inline_keyboard[-1])
    list_kb = InlineKeyboardMarkup(inline_keyboard=inline_rows)

    await callback.message.answer(text_lines, reply_markup=list_kb, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data.startswith("show_place_"))
async def show_place_detail(callback: types.CallbackQuery):
    place_id = callback.data.replace("show_place_", "")
    all_places = get_all_places_dict()
    item = all_places.get(place_id)
    if not item:
        await callback.answer("Місце не знайдено.", show_alert=True)
        return

    maps_url = f"https://www.google.com/maps/search/?api=1&query={item['lat']},{item['lon']}"
    detail_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗺️ На мапі Google", url=maps_url)],
            [InlineKeyboardButton(text="👍 Лайк", callback_data=f"like_{item['id']}"), InlineKeyboardButton(text="👎 Дизлайк", callback_data=f"dislike_{item['id']}")],
            [InlineKeyboardButton(text="⬅️ Головне меню", callback_data="back_main")]
        ]
    )

    caption = f"📍 **{item['name']}**\n• *Рейтинг:* {item['rating']}\n• *Адреса:* {item['addr']}\n• *Опис:* {item['desc']}"
    await callback.message.answer_photo(photo=item["photo"], caption=caption, reply_markup=detail_kb, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data.startswith("like_"))
async def handle_like(callback: types.CallbackQuery):
    await callback.answer("Дякуємо за оцінку! 👍")

@dp.callback_query(F.data.startswith("dislike_"))
async def handle_dislike(callback: types.CallbackQuery):
    await callback.answer("Дякуємо за відгук! Врахуємо. 👎")

@dp.callback_query(F.data == "f_near")
async def f_near_handler(callback: types.CallbackQuery):
    await send_random_closest_items(callback, FOOD_NEAR, get_food_categories_menu())

@dp.callback_query(F.data == "f_far")
async def f_far_handler(callback: types.CallbackQuery):
    await send_random_closest_items(callback, FOOD_FAR, get_food_categories_menu())

@dp.callback_query(F.data == "p_beaches")
async def p_beaches_handler(callback: types.CallbackQuery):
    await send_random_closest_items(callback, PLACES_BEACHES, get_places_categories_menu())

@dp.callback_query(F.data == "p_nature")
async def p_nature_handler(callback: types.CallbackQuery):
    await send_random_closest_items(callback, PLACES_NATURE, get_places_categories_menu())

@dp.callback_query(F.data == "p_arch")
async def p_arch_handler(callback: types.CallbackQuery):
    await send_random_closest_items(callback, PLACES_ARCHITECTURE, get_places_categories_menu())

@dp.callback_query(F.data == "tr_tips")
async def transport_tips(callback: types.CallbackQuery):
    await callback.message.answer("💳 **Чайові водію (ПриватБанк):**\n`5457 0825 2151 8477`", parse_mode="Markdown", reply_markup=get_transport_climate_menu())
    await callback.answer()

@dp.callback_query(F.data == "tr_review")
async def transport_review_prompt(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(FeedbackState.waiting_for_comment)
    await callback.message.answer("✍️ Напишіть ваш відгук або пропозицію наступним повідомленням:")
    await callback.answer()

@dp.message(FeedbackState.waiting_for_comment)
async def save_user_review(message: types.Message, state: FSMContext):
    user = message.from_user
    comment = message.text
    await state.clear()
    
    admin_text = f"📩 **Новий відгук!**\n• **Від:** {user.full_name} (@{user.username or 'немає'})\n• **Текст:** {comment}"
    try:
        await bot.send_message(chat_id=ADMIN_TELEGRAM_ID, text=admin_text)
    except Exception:
        pass
    await message.answer("🙏 Щиро дякуємо за ваш відгук!", reply_markup=get_transport_climate_menu())

@dp.callback_query(F.data == "tr_rate")
async def transport_rate(callback: types.CallbackQuery):
    rating_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ 1", callback_data="rate_1"), InlineKeyboardButton(text="⭐ 2", callback_data="rate_2"), InlineKeyboardButton(text="⭐ 3", callback_data="rate_3"), InlineKeyboardButton(text="⭐ 4", callback_data="rate_4"), InlineKeyboardButton(text="⭐ 5", callback_data="rate_5")],
            [InlineKeyboardButton(text="⬅️ Меню", callback_data="back_main")]
        ]
    )
    await callback.message.answer("Оцініть якість поїздки:", reply_markup=rating_kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("rate_"))
async def process_rating(callback: types.CallbackQuery):
    stars = callback.data.split("_")[1]
    user = callback.from_user
    try:
        await bot.send_message(chat_id=ADMIN_TELEGRAM_ID, text=f"⭐ **Оцінка поїздки:** {stars}/5 від {user.full_name}")
    except Exception:
        pass
    await callback.message.answer(f"❤️ Дякуємо за оцінку {stars}/5!", reply_markup=get_transport_climate_menu())
    await callback.answer()

@dp.message()
async def handle_text_message(message: types.Message):
    response_text = smart_smart_response(message.text)
    await message.answer(response_text, reply_markup=get_main_menu())

# ==================== ВЕБСЕРВЕР ДЛЯ RENDER ТА ЗАПУСК ====================

async def handle(request):
    return web.Response(text="I am alive!")

async def web_server():
    app = web.Application()
    app.add_routes([web.get('/', handle)])
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def main():
    init_db()
    
    # Запускаємо локальний вебсервер та поллінг бота паралельно
    await web_server()
    print("Бот успішно запущено разом із вебсервером на Render...")
    
    # Безпечно встановлюємо команди з обробкою помилок мережі
    try:
        await set_bot_commands(bot)
    except Exception as e:
        print(f"Попередження при встановленні команд: {e}")

    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())