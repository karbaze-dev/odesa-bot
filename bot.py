import asyncio
import logging
import sqlite3
import math
import random
from datetime import datetime
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
    BotCommand
)

TOKEN = "9271959219:AAG1hj2yp8KaQM7qTf7QUUXWsnIH6KwWzFU"
DB_NAME = "odesa_concierge.db"

# Твій реальний Telegram ID для отримання сповіщень
ADMIN_TELEGRAM_ID = 546552675

user_locations = {}
user_favorites = {}

class FeedbackState(StatesGroup):
    waiting_for_comment = State()

class BookingState(StatesGroup):
    waiting_for_details = State()

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            full_name TEXT,
            username TEXT
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

# ==================== БАЗИ ДАНИХ ЛОКАЦІЙ ====================

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
    {"id": "pa_1", "name": "Одеський театр опери та балету", "addr": "вул. П. Чайковского, 1", "rating": "⭐ 4.9 (8700 відгуків)", "desc": "Шедевр необароко.", "photo": "https://images.unsplash.com/photo-1513694203232-719a280e022f?auto=format&fit=crop&w=800&q=80", "lat": 46.4855, "lon": 30.7418},
    {"id": "pa_2", "name": "Секретні одеські дворики", "addr": "вул. Спиридонівська", "rating": "⭐ 4.7 (650 відгуків)", "desc": "Колодязі та старі сходи.", "photo": "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=800&q=80", "lat": 46.4820, "lon": 30.7300},
    {"id": "pa_3", "name": "Потьомкінські сходи", "addr": "Приморський бульвар", "rating": "⭐ 4.8 (7500 відгуків)", "desc": "Гігантські східці до порту.", "photo": "https://images.unsplash.com/photo-1513694203232-719a280e022f?auto=format&fit=crop&w=800&q=80", "lat": 46.4868, "lon": 30.7410},
]

def get_current_events():
    today = datetime.now()
    day_num = today.day
    return [
        {
            "id": "ev_1", 
            "name": "Концерт джазової музики", 
            "addr": "Одеська філармонія", 
            "rating": "⭐ 4.9 (420 відгуків)", 
            "desc": "Вечір класичного та сучасного джазу.", 
            "photo": "https://images.unsplash.com/photo-1511192336575-5a79af67a629?auto=format&fit=crop&w=800&q=80", 
            "lat": 46.4815, 
            "lon": 30.7405
        },
        {
            "id": "ev_2", 
            "name": "Виставка сучасного мистецтва", 
            "addr": "Одеський художній музей", 
            "rating": "⭐ 4.8 (890 відгуків)", 
            "desc": f"Актуальна експозиція робіт (оновлено на {day_num} число).", 
            "photo": "https://images.unsplash.com/photo-1541963463532-d68292c34b19?auto=format&fit=crop&w=800&q=80", 
            "lat": 46.4900, 
            "lon": 30.7350
        }
    ]

def get_all_places_dict():
    events = get_current_events()
    all_cat = [FOOD_NEAR, FOOD_FAR, PLACES_BEACHES, PLACES_NATURE, PLACES_ARCHITECTURE, events]
    return {item["id"]: item for cat in all_cat for item in cat}

# ==================== КЛАВІАТУРИ ТА ГОЛОВНЕ МЕНЮ (8 ПУНКТІВ У 2 СТРОЧКИ) ====================

def get_persistent_reply_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏠 Головне меню"), KeyboardButton(text="📍 Поділитися геолокацією", request_location=True)]
        ],
        resize_keyboard=True,
        is_persistent=True
    )

def get_main_menu():
    share_url = "https://t.me/share/url?url=https://t.me/OdesaConcierge_bot&text=Чудовий%20одеський%20гід%20у%20поїздці!%20Рекомендую%20📲"
    
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🚗 Водій та поїздка", callback_data="category_transport"),
                InlineKeyboardButton(text="🌤️ Погода та афіша", callback_data="menu_weather_events")
            ],
            [
                InlineKeyboardButton(text="🍲 Де поїсти", callback_data="menu_food_cat"),
                InlineKeyboardButton(text="🏛️ Куди сходити", callback_data="menu_places_cat")
            ],
            [
                InlineKeyboardButton(text="❄️ Атмосфера в салоні", callback_data="menu_atmosphere"),
                InlineKeyboardButton(text="🧭 Навигатор та час", callback_data="menu_timing")
            ],
            [
                InlineKeyboardButton(text="📅 Замовити наперед", callback_data="menu_booking"),
                InlineKeyboardButton(text="📖 Одеський словник", callback_data="menu_slang")
            ],
            [
                InlineKeyboardButton(text="📲 Поділитися ботом", url=share_url)
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
            [InlineKeyboardButton(text="🌤️ Погода зараз", callback_data="get_weather"), InlineKeyboardButton(text="🎭 Афіша подій", callback_data="get_events")],
            [InlineKeyboardButton(text="⬅️ Головне меню", callback_data="back_main")],
        ]
    )

def get_transport_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎵 Підключити Bluetooth (S13)", callback_data="tr_bluetooth")],
            [InlineKeyboardButton(text="💳 Залишити чайові", callback_data="tr_tips")],
            [InlineKeyboardButton(text="✍️ Написати відгук", callback_data="tr_review"), InlineKeyboardButton(text="⭐ Оцінити", callback_data="tr_rate")],
            [InlineKeyboardButton(text="⬅️ Головне меню", callback_data="back_main")],
        ]
    )

# ==================== РОЗУМНИЙ ОДЕСЬКИЙ ВІДПОВІДАЧ (БЕЗ КЛЮЧІВ) ====================

def smart_smart_response(text: str) -> str:
    text_lower = text.lower()
    
    if any(w in text_lower for w in ['привіт', 'здравствуй', 'доброго', 'вечір', 'ранку', 'день']):
        return "Вітаю! Радий бачити вас у салоні Станіслава. Як настрій? Обирайте потрібний розділ у меню нижче, або питайте — підкажемо найкраще в Одесі! 🌊"
    
    if any(w in text_lower for w in ['ціна', 'стоимость', 'сколько', 'оплата', 'грн', 'поездка']):
        return "Вартість поїздки розраховується через додатки Uklon або Bolt. А для душі й комфорту — салон нашого Suzuki Swift повністю до ваших послуг! 🚗✨"
    
    if any(w in text_lower for w in ['де', 'кафе', 'ресторан', 'поесть', 'кушать', 'їсти', 'голоден']):
        return "В Одесі голодним залишитися просто неможливо! Натисніть кнопку «🍲 Де поїсти» в меню вище, і я підберу найкращі заклади поруч або у центрі. 🍽️"
    
    if any(w in text_lower for w in ['море', 'пляж', 'куда пойти', 'погулять', 'скучно', 'достопримечательности']):
        return "Одеса прекрасна у будь-яку погоду! Зазирніть у розділ «🏛️ Куди сходити» або «🌤️ Погода та афіша» в меню — там зібрані найкращі місця нашого міста. ⚓"

    # Универсальные колоритные ответы
    responses = [
        "Таки послушайте, в Одессе на любой вопрос есть правильный ответ, но лучше всего — наслаждаться поездкой! Воспользуйтесь кнопками меню ниже. 😊",
        "Ой, не делайте мне нервы, лучше посмотрите меню консьержа — там есть всё, от музыки до ресторанов! 🌊",
        "Красивый вопрос! В нашем городе на это вам любой скажет: главное — хорошая погода и спокойный водитель Станислав за рулем. 🚗✨",
        "За это мы и любим Одессу! Выбирайте нужный раздел в меню, и мы сделаем вашу дорогу максимально приятной. 🎶"
    ]
    return random.choice(responses)

# ==================== ХЕНДЛЕРИ ====================

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

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO users (telegram_id, full_name, username)
        VALUES (?, ?, ?)
    """, (user_id, full_name, username))
    conn.commit()
    conn.close()

    welcome_text = (
        f"Вітаю, {full_name}! 👋 Радий вітати вас у моїй поїздці.\n\n"
        f"Мене звати **Станіслав**, я ваш водій. Затишний салон мого автомобіля (Suzuki Swift) та цей інтерактивний мінігід повністю до ваших послуг.\n\n"
        f"Бажаю вам легкої та приємної дороги містом! 🌊🚗\n\n"
        f"Оберіть потрібний розділ у меню нижче:"
    )

    await message.answer(welcome_text, reply_markup=get_persistent_reply_keyboard(), parse_mode="Markdown")
    await message.answer("Головне меню:", reply_markup=get_main_menu())

@dp.message(F.location)
async def handle_location(message: types.Message):
    user_locations[message.from_user.id] = (message.location.latitude, message.location.longitude)
    await message.answer("📍 Геолокацію оновлено! Заклади сортуються за відстанню від вас.", reply_markup=get_main_menu())

@dp.callback_query(F.data == "back_main")
async def back_to_main(callback: types.CallbackQuery):
    await callback.message.answer("Головне меню:", reply_markup=get_main_menu())
    await callback.answer()

@dp.callback_query(F.data == "menu_food_cat")
async def food_cat_menu(callback: types.CallbackQuery):
    await callback.message.answer("🍲 **Оберіть формат пошуку закладів:**", reply_markup=get_food_categories_menu())
    await callback.answer()

@dp.callback_query(F.data == "menu_places_cat")
async def places_cat_menu(callback: types.CallbackQuery):
    await callback.message.answer("🏛️ **Оберіть напрямок для прогулянок:**", reply_markup=get_places_categories_menu())
    await callback.answer()

@dp.callback_query(F.data == "menu_weather_events")
async def weather_events_menu(callback: types.CallbackQuery):
    await callback.message.answer("🌤️ **Оберіть розділ:**", reply_markup=get_weather_events_menu())
    await callback.answer()

@dp.callback_query(F.data == "category_transport")
async def transport_handler(callback: types.CallbackQuery):
    await callback.message.answer(
        "🚗 **Інформація про поїздку:**\n\n"
        "• **Водій:** Станіслав\n"
        "• **Авто:** Suzuki Swift\n"
        "• **Платформи:** Uklon & Bolt\n\n"
        "Оберіть дію:",
        reply_markup=get_transport_menu()
    )
    await callback.answer()

# --- АТМОСФЕРА В САЛОНІ ---

@dp.callback_query(F.data == "menu_atmosphere")
async def menu_atmosphere(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❄️ Зробити прохолодніше", callback_data="atmos_cooler")],
            [InlineKeyboardButton(text="🔥 Зробити тепліше", callback_data="atmos_warmer")],
            [InlineKeyboardButton(text="🤫 Режим тиші (відпочити)", callback_data="atmos_quiet")],
            [InlineKeyboardButton(text="💬 Не проти поспілкуватися", callback_data="atmos_talk")],
            [InlineKeyboardButton(text="⚡ Потрібна зарядка (Type-C / Lightning)", callback_data="atmos_charge")],
            [InlineKeyboardButton(text="⬅️ Головне меню", callback_data="back_main")]
        ]
    )
    await callback.message.answer("❄️ **Атмосфера в салоні:**\nОберіть бажаний формат комфорту, і водій одразу отримає ваше побажання:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("atmos_"))
async def handle_atmosphere_choice(callback: types.CallbackQuery):
    action = callback.data.replace("atmos_", "")
    user = callback.from_user
    texts = {
        "cooler": "❄️ Прохання зробити прохолодніше в салоні",
        "warmer": "🔥 Прохання зробити тепліше в салоні",
        "quiet": "🤫 Режим тиші (пасажир бажає відпочити)",
        "talk": "💬 Пасажир відкритий до розмови",
        "charge": "⚡ Потрібна зарядка для телефону"
    }
    msg_text = texts.get(action, "Запит по комфорту")
    
    admin_text = f"⚙️ **Побажання щодо атмосфери!**\n\n• **Пасажир:** {user.full_name} (@{user.username or 'немає'})\n• **ID:** `{user.id}`\n• **Запит:** {msg_text}"
    try:
        await bot.send_message(chat_id=ADMIN_TELEGRAM_ID, text=admin_text, parse_mode="Markdown")
    except Exception:
        pass
        
    await callback.answer("✅ Водію надіслано ваше побажання!", show_alert=True)

@dp.callback_query(F.data == "menu_timing")
async def menu_timing(callback: types.CallbackQuery):
    timing_text = (
        "🧭 **Орієнтовний час у дорозі (з центру):**\n\n"
        "• **Ж/Д Вокзал ↔ Аркадія:** ~15–20 хв (6 км)\n"
        "• **Центр ↔ Таирова (Панорама):** ~25–35 хв (13 км)\n"
        "• **Центр ↔ Черёмушки (Парк Горького):** ~20 хв (8 км)\n"
        "• **Центр ↔ Посёлок Котовского:** ~35–50 хв (18 км)\n"
        "• **Центр ↔ 16-а ст. Фонтана:** ~30 хв (12 км)\n\n"
        "💡 *Рада від водія:* у години пік маршрути через середмістя можуть займати трохи більше часу."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Головне меню", callback_data="back_main")]])
    await callback.message.answer(timing_text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "menu_booking")
async def menu_booking(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(BookingState.waiting_for_details)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Скасувати", callback_data="back_main")]])
    await callback.message.answer(
        "📅 **Забронировать поездку со Станиславом:**\n\nНапишите в ответном сообщении дату, время, маршрут (куда и откуда) и ваши пожелания — водителю сразу придет ваш запрос:",
        reply_markup=kb
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

@dp.callback_query(F.data == "menu_slang")
async def menu_slang(callback: types.CallbackQuery):
    slang_words = [
        ("«Шо вы говорите?»", "Вежливое выражение крайнего удивления или неверия."),
        ("«Иметь за себя мнение»", "Быть высокого о себе мнения."),
        ("«Тю!»", "Универсальное восклицание (удивление, досада, возражение)."),
        ("«Сделать базар»", "Сходить за покупками на рынок (Привоз или Черемушки)."),
        ("«Биточки из тюлечки»", "Кулинарный шедевр и гордость одесской кухни."),
        ("«Не делать мне нервы»", "Просьба успокоиться и не создавать лишних проблем."),
        ("«Шаланды, полные кефали»", "Легендарная фраза, прославившая Одессу на весь мир."),
        ("«Будем иметь что сказать»", "Обязательно обсудим все детали позже."),
        ("«Вы мне не делаете погоду»", "Ваше мнение никак не влияет на мои планы."),
        ("«Одесский дворик»", "Особый мир, где все соседи знают друг о друге всё."),
        ("«Пойти на Привоз за здоровьем»", "Поехать на рынок не только за едой, но и за свежими сплетнями."),
        ("«Такой себе компот»", "Ситуация, когда всё перемешалось и не совсем понятно.")
    ]
    word, desc = random.choice(slang_words)
    text = f"📖 **Одеський словник у дорозі:**\n\n🔸 **{word}** — *{desc}* \n\nНатисніть кнопку нижче, щоб дізнатися інше слово:"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Інше слово", callback_data="menu_slang")],
        [InlineKeyboardButton(text="⬅️ Головне меню", callback_data="back_main")]
    ])
    await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "tr_bluetooth")
async def transport_bluetooth(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    full_name = callback.from_user.full_name
    username = f"@{callback.from_user.username}" if callback.from_user.username else "немає username"

    notification_text = (
        f"🎵 **Пасажир хоче підключити Bluetooth!**\n\n"
        f"• **Пасажир:** {full_name} ({username})\n"
        f"• **ID:** `{user_id}`\n"
        f"• **Пристрій:** S13\n\n"
        f"*(Увімкніть пошук на S13, щоб пасажир міг увімкнути свою музику)*"
    )
    
    try:
        await bot.send_message(chat_id=ADMIN_TELEGRAM_ID, text=notification_text, parse_mode="Markdown")
    except Exception as e:
        print(f"Не вдалося надіслати сповіщення про Bluetooth адміну: {e}")

    await callback.message.answer(
        "🎵 **Підключення до аудіосистеми S13:**\n\n"
        "1. Увімкніть **Bluetooth** у налаштуваннях свого телефона.\n"
        "2. Знайдіть мережу **«S13»** та натисніть «Підключити».\n\n"
        "⚠️ Водію вже надіслано сигнал — він очікує на підключення! Гарної музики та поїздки! 🎶",
        reply_markup=get_transport_menu()
    )
    await callback.answer()

@dp.callback_query(F.data == "get_weather")
async def weather_handler(callback: types.CallbackQuery):
    weather_text = (
        "🌤️ **Погода в Одесі зараз:**\n\n"
        "• **Температура повітря:** +14°C (малохмарно)\n"
        "• **Вітер:** Східний, 4 м/с\n"
        "• **Вологість:** 65%\n\n"
        "Чудова погода для прогулянки містом! 🌊"
    )
    await callback.message.answer(weather_text, reply_markup=get_weather_events_menu(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "get_events")
async def events_handler(callback: types.CallbackQuery):
    events_today = get_current_events()
    current_date_str = datetime.now().strftime("%d.%m.%Y")
    text_lines = f"🎭 **Афіша подій в Одесі на {current_date_str}:**\n\n"
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
    
    text_lines = "🎲 **Ось варіанти для вас:**\n\n"
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
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
        ]
    )

    caption = f"📍 **{item['name']}**\n• *Рейтинг:* {item['rating']}\n• *Адреса:* {item['addr']}\n• *Опис:* {item['desc']}"
    await callback.message.answer_photo(photo=item["photo"], caption=caption, reply_markup=detail_kb, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data.startswith("like_"))
async def handle_like(callback: types.CallbackQuery):
    await callback.answer("Дякуємо! 👍")

@dp.callback_query(F.data.startswith("dislike_"))
async def handle_dislike(callback: types.CallbackQuery):
    await callback.answer("Дякуємо за відгук! 👎")

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
    await callback.message.answer("💳 **Чайові водію (ПриватБанк):**\n`5457 0825 2151 8477`", parse_mode="Markdown", reply_markup=get_transport_menu())
    await callback.answer()

@dp.callback_query(F.data == "tr_review")
async def transport_review_prompt(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(FeedbackState.waiting_for_comment)
    await callback.message.answer("✍️ Напишіть ваш відгук наступним повідомленням:")
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
    await message.answer("🙏 Дякуємо за відгук!", reply_markup=get_transport_menu())

@dp.callback_query(F.data == "tr_rate")
async def transport_rate(callback: types.CallbackQuery):
    rating_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ 1", callback_data="rate_1"), InlineKeyboardButton(text="⭐ 2", callback_data="rate_2"), InlineKeyboardButton(text="⭐ 3", callback_data="rate_3"), InlineKeyboardButton(text="⭐ 4", callback_data="rate_4"), InlineKeyboardButton(text="⭐ 5", callback_data="rate_5")],
            [InlineKeyboardButton(text="⬅️ Меню", callback_data="back_main")]
        ]
    )
    await callback.message.answer("Оцініть поїздку:", reply_markup=rating_kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("rate_"))
async def process_rating(callback: types.CallbackQuery):
    stars = callback.data.split("_")[1]
    user = callback.from_user
    try:
        await bot.send_message(chat_id=ADMIN_TELEGRAM_ID, text=f"⭐ **Оцінка поїздки:** {stars}/5 від {user.full_name}")
    except Exception:
        pass
    await callback.message.answer(f"❤️ Дякуємо за оцінку {stars}/5!", reply_markup=get_transport_menu())
    await callback.answer()

# --- ОБРОБКА ВІЛЬНИХ ПОВІДОМЛЕНЬ (РОЗУМНИЙ ОДЕСЬКИЙ ВІДПОВІДАЧ) ---

@dp.message()
async def handle_text_message(message: types.Message):
    response_text = smart_smart_response(message.text)
    await message.answer(response_text, reply_markup=get_main_menu())

async def main():
    init_db()
    await set_bot_commands(bot)
    print("Бот успішно запущено з оновленим меню...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
