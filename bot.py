import asyncio
import json
import logging
import math
import os
import random
import re
import sqlite3
from datetime import datetime
from html import unescape

import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN", "").strip() or "9271959219:AAG1hj2yp8KaQM7qTf7QUUXWsnIH6KwWzFU"
DB_NAME = "odesa_concierge.db"
EVENTS_CACHE_FILE = "events_cache.json"
DRIVER_PHOTO_PATH = "driver.jpg"

_admin_env = os.getenv("ADMIN_ID", "").strip()
ADMIN_TELEGRAM_ID = int(_admin_env) if _admin_env.isdigit() else 546552675
MY_TELEGRAM_USERNAME = os.getenv("DRIVER_USERNAME", "").strip().lstrip("@") or "karbaze_dev"

ODESA_LAT = 46.4845
ODESA_LON = 30.7385

user_locations = {}
weather_cache = {"text": None, "updated_at": 0.0}
events_cache = {"items": [], "updated_at": ""}


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
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
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
    {"name": "Укриття у парку Шевченка", "addr": "парк ім. Шевченка (біля стадіону)", "lat": 46.4775, "lon": 30.7490},
]

QUIZ_QUESTIONS = [
    {
        "q": "Питання 1: Що робить справжній одесит, коли не повівся на розмову?",
        "options": [
            ("А) Сходити на Привоз", False),
            ("Б) Сказати «Шо?» у відповідь", True),
            ("В) Поїхати в Аркадію", False),
        ],
    },
    {
        "q": "Питання 2: Як в Одесі правильно називають традиційні маленькі рибні котлетки?",
        "options": [
            ("А) Биточки з тюлечки", True),
            ("Б) Звичайні нагетси", False),
            ("В) Котлети по-київськи", False),
        ],
    },
    {
        "q": "Питання 3: Що зазвичай означає фраза «Не робіть мені нерви»?",
        "options": [
            ("А) Час пити чай", False),
            ("Б) Прохання заспокоїтися і не створювати проблем", True),
            ("В) Поїхати на море", False),
        ],
    },
    {
        "q": "Питання 4: Що означає в Одесі вислів «зробити базар»?",
        "options": [
            ("А) Влаштувати гучну суперечку", False),
            ("Б) Сходити за покупками на ринок", True),
            ("В) Помити машину на мийці", False),
        ],
    },
    {
        "q": "Питання 5: Що зазвичай відповідає одесит на запитання «Як справи?»?",
        "options": [
            ("А) «Не дочекаєтесь!» або «Таки краще за всіх!»", True),
            ("Б) «Згідно з інструкцією»", False),
            ("В) «Погода мінлива»", False),
        ],
    },
    {
        "q": "Питання 6: Що означає фраза «Ви мені не робите погоду»?",
        "options": [
            ("А) На вулиці буде дощ", False),
            ("Б) Ваша думка не змінить моїх планів", True),
            ("В) Потрібно взяти парасолю", False),
        ],
    },
    {
        "q": "Питання 7: Як часто в Одесі звучить слово «Тю!»?",
        "options": [
            ("А) Коли щось дивує, смішить або викликає легке здивування", True),
            ("Б) Тільки під час морської бурі", False),
            ("В) Лише на вокзалі", False),
        ],
    },
    {
        "q": "Питання 8: Що означає вислів «мати за себе думку»?",
        "options": [
            ("А) Бути високої думки про себе та знати собі ціну", True),
            ("Б) Забути парасольку вдома", False),
            ("В) Переплутати зупинку", False),
        ],
    },
]

FALLBACK_EVENTS = [
    {
        "id": "ev_1",
        "name": "Опера «Травіата» Дж. Верді",
        "date": "Найближчі покази — дивіться на сайті",
        "addr": "Одеський театр опери та балету (пров. Чайковського, 1)",
        "rating": "🎟️ Подія в Одесі",
        "desc": "Відкрийте подію та перейдіть за посиланням, щоб переглянути точний розклад і квитки.",
        "photo": "https://images.unsplash.com/photo-1513694203232-719a280e022f?auto=format&fit=crop&w=800&q=80",
        "lat": 46.4855,
        "lon": 30.7418,
        "url": "https://operahouse.od.ua/afisha/",
    },
    {
        "id": "ev_2",
        "name": "Симфонічний вечір у філармонії",
        "date": "Найближчі концерти — дивіться на сайті",
        "addr": "Одеська обласна філармонія (вул. Ніни Строкатої / Буніна, 15)",
        "rating": "🎟️ Подія в Одесі",
        "desc": "Концертна програма в Одесі. Точну дату, час та квитки дивіться за посиланням.",
        "photo": "https://images.unsplash.com/photo-1511192336575-5a79af67a629?auto=format&fit=crop&w=800&q=80",
        "lat": 46.4815,
        "lon": 30.7405,
        "url": "https://filarmonia.odessa.ua/afisha/",
    },
    {
        "id": "ev_3",
        "name": "Екскурсії та виставки в Одеському художньому музеї",
        "date": "За графіком роботи музею",
        "addr": "Одеський художній музей (вул. Софіївська, 5А)",
        "rating": "🎟️ Подія в Одесі",
        "desc": "Актуальні експозиції та події музею. Деталі та розклад — за посиланням.",
        "photo": "https://images.unsplash.com/photo-1541963463532-d68292c34b19?auto=format&fit=crop&w=800&q=80",
        "lat": 46.4900,
        "lon": 30.7350,
        "url": "https://www.ofam.org.ua/",
    },
    {
        "id": "ev_4",
        "name": "Музичні вистави та комедії",
        "date": "Найближчі покази — дивіться на сайті",
        "addr": "Театр музкомедії ім. М. Водяного (вул. Пантелеймонівська, 3)",
        "rating": "🎟️ Подія в Одесі",
        "desc": "Театральна подія в Одесі. Точну дату, час та квитки дивіться за посиланням.",
        "photo": "https://images.unsplash.com/photo-1503095396549-807759245b35?auto=format&fit=crop&w=800&q=80",
        "lat": 46.4730,
        "lon": 30.7440,
        "url": "https://muzkomediya.com/repertoire",
    },
]

EVENT_PHOTOS = [
    "https://images.unsplash.com/photo-1513694203232-719a280e022f?auto=format&fit=crop&w=800&q=80",
    "https://images.unsplash.com/photo-1511192336575-5a79af67a629?auto=format&fit=crop&w=800&q=80",
    "https://images.unsplash.com/photo-1503095396549-807759245b35?auto=format&fit=crop&w=800&q=80",
    "https://images.unsplash.com/photo-1541963463532-d68292c34b19?auto=format&fit=crop&w=800&q=80",
    "https://images.unsplash.com/photo-1492684223066-81342ee5ff30?auto=format&fit=crop&w=800&q=80",
    "https://images.unsplash.com/photo-1514525253161-7a46d19cd819?auto=format&fit=crop&w=800&q=80",
]


# ==================== АВТОНОМНА ПОГОДА ТА АФІША ПОДІЙ ====================

def weather_code_to_ua(code: int) -> str:
    mapping = {
        0: "☀️ Ясно, безхмарно",
        1: "🌤️ Переважно ясно",
        2: "⛅ Мінлива хмарність",
        3: "☁️ Хмарно",
        45: "🌫️ Туман",
        48: "🌫️ Паморозь / туман",
        51: "🌦️ Легка мряка",
        53: "🌦️ Помірна мряка",
        55: "🌧️ Густа мряка",
        61: "🌧️ Невеликий дощ",
        63: "🌧️ Помірний дощ",
        65: "🌧️ Сильний дощ",
        71: "🌨️ Невеликий сніг",
        73: "🌨️ Сніг",
        75: "❄️ Сильний сніг",
        80: "🌦️ Короткочасний дощ",
        81: "🌧️ Злива",
        82: "⛈️ Сильна злива",
        95: "⛈️ Гроза",
    }
    return mapping.get(code, "🌤️ Свіже морське повітря")


async def fetch_live_weather() -> str:
    now_ts = datetime.now().timestamp()
    if weather_cache["text"] and (now_ts - weather_cache["updated_at"]) < 900:
        return weather_cache["text"]

    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={ODESA_LAT}&longitude={ODESA_LON}"
        f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m"
        f"&wind_speed_unit=ms&timezone=Europe%2FKyiv"
    )
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    cur = data.get("current", {})
                    temp = round(cur.get("temperature_2m", 12))
                    feels = round(cur.get("apparent_temperature", temp))
                    humidity = cur.get("relative_humidity_2m", 65)
                    wind = round(cur.get("wind_speed_10m", 4), 1)
                    w_code = int(cur.get("weather_code", 1))
                    desc = weather_code_to_ua(w_code)
                    updated_str = datetime.now().strftime("%H:%M")

                    text = (
                        f"🌤️ **Погода в Одесі зараз** *(оновлено о {updated_str})*:\n\n"
                        f"• **Стан неба:** {desc}\n"
                        f"• **Температура повітря:** {temp:+d}°C (відчувається як {feels:+d}°C)\n"
                        f"• **Вітер:** {wind} м/с\n"
                        f"• **Вологість:** {humidity}%\n\n"
                        f"Комфортної поїздки містом біля моря! 🌊"
                    )
                    weather_cache["text"] = text
                    weather_cache["updated_at"] = now_ts
                    return text
    except Exception as exc:
        logging.warning("Не вдалося оновити погоду Open-Meteo: %s", exc)

    if weather_cache["text"]:
        return weather_cache["text"]

    return (
        "🌤️ **Погода в Одесі:**\n\n"
        "• **Температура повітря:** +12°C (малохмарно)\n"
        "• **Вітер:** 4 м/с\n"
        "• **Вологість:** 65%\n\n"
        "Чудова погода для прогулянки Одесою! 🌊"
    )


def _clean_html_text(raw: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", raw or "")
    return re.sub(r"\s+", " ", unescape(no_tags)).strip()


def _is_venue_or_noise_title(title: str) -> bool:
    low = (title or "").strip().lower()
    if len(low) < 4 or len(low) > 110:
        return True
    forbidden_substrings = [
        "репертуар",
        "афіша",
        "квитки",
        "сьогодні",
        "детальніше",
        "чорна п'ятниця",
        "черная пятница",
        "купити квитки",
        "купить билеты",
        "google tag manager",
        "kontramarka",
        "театр в одесі",
        "театрі в одесі",
        "філармонія у одесі",
        "будинок клоунів у одесі",
        "концерт-хол «одеса»",
        "концерт-хол \"одеса\"",
        "міжнародний культурний центр",
    ]
    if any(p in low for p in forbidden_substrings):
        return True
    if low.startswith(("одеський ", "театр ", "філармонія", "будинок клоунів")) and (
        "театр" in low or "філармонія" in low or "будинок" in low
    ) and not any(k in low for k in ["вистава", "концерт", "шоу", "балет", "опера", "комедія", "мюзикл", "казка", "virsky", "stand up", "стендап"]):
        return True
    return False


def _extract_event_date(context_html: str) -> str:
    clean_ctx = _clean_html_text(context_html)
    date_match = re.search(
        r"\b(\d{1,2}\s+(?:січня|лютого|березня|квітня|травня|червня|липня|серпня|вересня|жовтня|листопада|грудня)|\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?)(?:\s*,?\s*(\d{1,2}:\d{2}))?",
        clean_ctx,
        flags=re.IGNORECASE,
    )
    if date_match:
        d_part = date_match.group(1).strip()
        t_part = date_match.group(2).strip() if date_match.group(2) else ""
        return f"{d_part}, {t_part}" if t_part else d_part
    return "Дата та час за посиланням"


def _guess_venue_coords(title_and_place: str):
    low = (title_and_place or "").lower()
    if "опер" in low:
        return "Одеський театр опери та балету (пров. Чайковського, 1)", 46.4855, 30.7418
    if "філармон" in low or "филармон" in low:
        return "Одеська обласна філармонія (вул. Буніна, 15)", 46.4815, 30.7405
    if "музкомед" in low:
        return "Театр музкомедії ім. М. Водяного (вул. Пантелеймонівська, 3)", 46.4730, 30.7440
    if "василька" in low or ("українськ" in low and "театр" in low):
        return "Український театр ім. В. Василька (вул. Пастера, 15)", 46.4878, 30.7315
    if "клоун" in low:
        return "Будинок клоунів (вул. Ольгіївська, 23)", 46.4865, 30.7270
    if "художн" in low and "музей" in low:
        return "Одеський художній музей (вул. Софіївська, 5А)", 46.4900, 30.7350
    if "аркад" in low or "ibiza" in low or "itaka" in low:
        return "Аркадія, Одеса", 46.4420, 30.7635
    if "юніон" in low or "union" in low:
        return "МЦК «УНІОН» (вул. Троїцька, 43)", 46.4785, 30.7320
    return "Локація події в Одесі (уточнюйте за посиланням)", ODESA_LAT, ODESA_LON


async def _enrich_event_from_page(session: aiohttp.ClientSession, event_item: dict):
    url = event_item.get("url")
    if not url:
        return
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status != 200:
                return
            page_html = await resp.text()

        h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", page_html, flags=re.IGNORECASE | re.DOTALL)
        if h1_match:
            h1_clean = _clean_html_text(h1_match.group(1))
            if h1_clean and not _is_venue_or_noise_title(h1_clean):
                event_item["name"] = h1_clean[:100]

        parsed_date = _extract_event_date(page_html)
        if parsed_date != "Дата та час за посиланням":
            event_item["date"] = parsed_date

        page_text = _clean_html_text(page_html)
        venue_match = re.search(
            r"(?:Місце проведення|Локація|Майданчик|Театр|Філармонія|Будинок клоунів|Клуб|Палац)[^.:|▷]{0,80}",
            page_text,
            flags=re.IGNORECASE,
        )
        if venue_match:
            venue_str = _clean_html_text(venue_match.group(0))
            if 6 <= len(venue_str) <= 100 and "google tag manager" not in venue_str.lower() and "kontramarka" not in venue_str.lower():
                event_item["addr"] = venue_str
                _, lat, lon = _guess_venue_coords(f"{event_item['name']} {venue_str}")
                event_item["lat"], event_item["lon"] = lat, lon
        else:
            addr, lat, lon = _guess_venue_coords(f"{event_item['name']} {page_text[:400]}")
            event_item["addr"], event_item["lat"], event_item["lon"] = addr, lat, lon
    except Exception:
        pass


async def scrape_odesa_events() -> list:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
        "Accept-Language": "uk-UA,uk;q=0.9,ru;q=0.8",
    }
    collected = []
    seen_urls = set()
    seen_titles = set()

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get("https://concert.ua/uk/odesa", timeout=aiohttp.ClientTimeout(total=12)) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    blocks = re.findall(
                        r'(.{0,260}<a[^>]+href="(/uk/event/odesa/[^"]+)"[^>]*>.*?</a>.{0,260})',
                        html,
                        flags=re.IGNORECASE | re.DOTALL,
                    )
                    for block_html, href in blocks:
                        full_url = f"https://concert.ua{href}"
                        if full_url in seen_urls:
                            continue
                        m_link = re.search(
                            r'<a[^>]+href="(/uk/event/odesa/[^"]+)"[^>]*>(.*?)</a>',
                            block_html,
                            flags=re.IGNORECASE | re.DOTALL,
                        )
                        if not m_link:
                            continue
                        clean = _clean_html_text(m_link.group(2))
                        if _is_venue_or_noise_title(clean):
                            continue
                        key = clean.lower()
                        if key in seen_titles:
                            continue

                        seen_urls.add(full_url)
                        seen_titles.add(key)

                        event_date = _extract_event_date(block_html)
                        idx = len(collected) + 1
                        addr, lat, lon = _guess_venue_coords(f"{clean} {block_html}")
                        collected.append(
                            {
                                "id": f"ev_{idx}",
                                "name": clean,
                                "date": event_date,
                                "addr": addr,
                                "rating": "🎟️ Подія в Одесі",
                                "desc": "Натисніть кнопку нижче, щоб відкрити сторінку події, уточнити розклад та придбати квитки.",
                                "photo": EVENT_PHOTOS[(idx - 1) % len(EVENT_PHOTOS)],
                                "lat": lat,
                                "lon": lon,
                                "url": full_url,
                            }
                        )
                        if len(collected) >= 6:
                            break

            if len(collected) < 4:
                async with session.get("https://odesa.kontramarka.ua/uk", timeout=aiohttp.ClientTimeout(total=12)) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        blocks = re.findall(
                            r'(.{0,260}<a[^>]+href="(https://odesa\.kontramarka\.ua/uk/[^"]+\.html)"[^>]*>.*?</a>.{0,260})',
                            html,
                            flags=re.IGNORECASE | re.DOTALL,
                        )
                        for block_html, href in blocks:
                            if href in seen_urls:
                                continue
                            m_link = re.search(
                                r'<a[^>]+href="(https://odesa\.kontramarka\.ua/uk/[^"]+\.html)"[^>]*>(.*?)</a>',
                                block_html,
                                flags=re.IGNORECASE | re.DOTALL,
                            )
                            if not m_link:
                                continue
                            clean = _clean_html_text(m_link.group(2))
                            if _is_venue_or_noise_title(clean):
                                continue
                            key = clean.lower()
                            if key in seen_titles:
                                continue

                            seen_urls.add(href)
                            seen_titles.add(key)

                            event_date = _extract_event_date(block_html)
                            idx = len(collected) + 1
                            addr, lat, lon = _guess_venue_coords(f"{clean} {block_html}")
                            collected.append(
                                {
                                    "id": f"ev_{idx}",
                                    "name": clean,
                                    "date": event_date,
                                    "addr": addr,
                                    "rating": "🎟️ Подія в Одесі",
                                    "desc": "Натисніть кнопку нижче, щоб переглянути дату, час та наявність квитків.",
                                    "photo": EVENT_PHOTOS[(idx - 1) % len(EVENT_PHOTOS)],
                                    "lat": lat,
                                    "lon": lon,
                                    "url": href,
                                }
                            )
                            if len(collected) >= 6:
                                break

            if collected:
                await asyncio.gather(*(_enrich_event_from_page(session, item) for item in collected))
    except Exception as exc:
        logging.warning("Парсер афіші тимчасово недоступний: %s", exc)

    return collected


def load_events_from_disk():
    if os.path.exists(EVENTS_CACHE_FILE):
        try:
            with open(EVENTS_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and data.get("items"):
                    filtered = [x for x in data["items"] if not _is_venue_or_noise_title(x.get("name", ""))]
                    if filtered:
                        events_cache["items"] = filtered
                        events_cache["updated_at"] = data.get("updated_at", "")
        except Exception as exc:
            logging.warning("Не вдалося прочитати events_cache.json: %s", exc)


def save_events_to_disk(items: list, updated_at: str):
    try:
        with open(EVENTS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"items": items, "updated_at": updated_at}, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        logging.warning("Не вдалося зберегти events_cache.json: %s", exc)


async def refresh_events_cache():
    fresh = await scrape_odesa_events()
    if fresh:
        now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
        events_cache["items"] = fresh
        events_cache["updated_at"] = now_str
        save_events_to_disk(fresh, now_str)
        logging.info("Афішу Одеси успішно оновлено (%s подій).", len(fresh))


def get_current_events() -> list:
    if events_cache["items"]:
        return events_cache["items"]
    return FALLBACK_EVENTS


def get_all_places_dict():
    events = get_current_events()
    all_cat = [FOOD_NEAR, FOOD_FAR, PLACES_BEACHES, PLACES_NATURE, PLACES_ARCHITECTURE, events]
    return {item["id"]: item for cat in all_cat for item in cat}


# ==================== ГОЛОВНЕ МЕНЮ ТА ІНЛАЙН КНОПКИ ====================

def get_persistent_reply_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🏠 Головне меню"),
                KeyboardButton(text="📍 Поділитися геолокацією", request_location=True),
            ]
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def get_main_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🚗 Водій, поїздка та клімат", callback_data="category_transport_climate"),
                InlineKeyboardButton(text="🌤️ Погода та афіша", callback_data="menu_weather_events"),
            ],
            [
                InlineKeyboardButton(text="🍲 Де поїсти", callback_data="menu_food_cat"),
                InlineKeyboardButton(text="🏛️ Куди сходити", callback_data="menu_places_cat"),
            ],
            [
                InlineKeyboardButton(text="🇺🇦 Одесське пророцтво", callback_data="menu_fortune"),
                InlineKeyboardButton(text="🧠 Ти Одесит?", callback_data="menu_odessa_quiz"),
            ],
            [
                InlineKeyboardButton(text="💼 Бізнес та партнери (B2B)", callback_data="menu_business"),
                InlineKeyboardButton(text="🛡️ Карта укриттів", callback_data="menu_shelters"),
            ],
            [
                InlineKeyboardButton(text="📅 Замовити наперед", callback_data="menu_booking"),
                InlineKeyboardButton(text="📖 Одеський словник", callback_data="menu_slang"),
            ],
        ]
    )


def get_food_categories_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📍 Поруч зі мною", callback_data="f_near"),
                InlineKeyboardButton(text="🚗 У центрі", callback_data="f_far"),
            ],
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
            [
                InlineKeyboardButton(text="🌤️ Погода зараз", callback_data="get_weather"),
                InlineKeyboardButton(text="🎭 Велика афіша подій", callback_data="get_events"),
            ],
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
            [InlineKeyboardButton(text="📶 Wi-Fi у салоні", callback_data="menu_wifi")],
            [InlineKeyboardButton(text="💳 Залишити чайові", callback_data="tr_tips")],
            [
                InlineKeyboardButton(text="✍️ Написати відгук", callback_data="tr_review"),
                InlineKeyboardButton(text="⭐ Оцінити", callback_data="tr_rate"),
            ],
            [InlineKeyboardButton(text="⬅️ Головне меню", callback_data="back_main")],
        ]
    )


# ==================== РОЗУМНИЙ ОДЕСЬКИЙ ВІДПОВІДАЧ ====================

def smart_smart_response(text: str) -> str:
    text_lower = (text or "").lower()
    if any(w in text_lower for w in ["привіт", "здравствуй", "доброго", "вечір", "ранку", "день"]):
        return "Вітаю! Радий бачити вас у салоні Станіслава. Обирайте потрібний розділ у меню нижче, або питайте — підкажемо найкраще в Одесі! 🌊"
    if any(w in text_lower for w in ["ціна", "стоимость", "сколько", "оплата", "грн", "поездка"]):
        return "Вартість поїздки розраховується через додатки Uklon або Bolt. А для комфорту в дорозі — салон Suzuki Swift повністю до ваших послуг! 🚗✨"
    if any(w in text_lower for w in ["де", "кафе", "ресторан", "поесть", "кушать", "їсти", "голоден"]):
        return "В Одесі голодним залишитися неможливо! Натисніть кнопку «🍲 Де поїсти» в меню, і я підберу чудові заклади. 🍽️"
    if any(w in text_lower for w in ["море", "пляж", "куда пойти", "погулять", "скучно"]):
        return "Одеса прекрасна! Зазирніть у розділ «🏛️ Куди сходити» або «🎭 Велика афіша подій» в меню. ⚓"

    responses = [
        "Таки послушайте, в Одессе на любой вопрос есть правильный ответ! Воспользуйтесь кнопками меню ниже. 😊",
        "Ой, не делайте мне нервы, лучше посмотрите меню консьержа — там есть всё, от афиши до ресторанов! 🌊",
        "Главное в дороге — хорошая погода и спокойный водитель Станислав за рулем. 🚗✨",
        "За это мы и любим Одессу! Выбирайте нужный раздел в меню, и мы сделаем вашу поездку незабываемой. 🎶",
    ]
    return random.choice(responses)


# ==================== ХЕНДЛЕРИ ТА ЛОГІКА БОТА ====================

async def set_bot_commands(bot_instance: Bot):
    commands = [
        BotCommand(command="start", description="Головне меню / Перезапуск")
    ]
    await bot_instance.set_my_commands(commands)


@dp.message(Command("start"))
@dp.message(F.text == "🏠 Головне меню")
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    username = message.from_user.username or ""

    args = (message.text or "").split()
    if len(args) > 1 and args[1].startswith("ref"):
        try:
            referrer_id = int(args[1].replace("ref", ""))
            if referrer_id != user_id:
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET ref_count = ref_count + 1 WHERE telegram_id = ?", (referrer_id,))
                conn.commit()
                conn.close()
                await bot.send_message(referrer_id, "🎉 За вашим посиланням долучився новий пасажир! Вам нараховано бонус.")
        except Exception:
            pass

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR IGNORE INTO users (telegram_id, full_name, username)
        VALUES (?, ?, ?)
        """,
        (user_id, full_name, username),
    )
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
        try:
            photo = FSInputFile(DRIVER_PHOTO_PATH)
            await message.answer_photo(
                photo=photo,
                caption=welcome_caption,
                reply_markup=get_main_menu(),
                parse_mode="Markdown",
            )
            return
        except Exception as exc:
            logging.warning("Не вдалося відправити driver.jpg: %s", exc)

    await message.answer(
        welcome_caption,
        reply_markup=get_main_menu(),
        parse_mode="Markdown",
    )


@dp.message(F.location)
async def handle_location(message: types.Message):
    user_locations[message.from_user.id] = (message.location.latitude, message.location.longitude)
    await message.answer(
        "📍 Геолокацію успішно оновлено! Заклади та найближчі укриття сортуються відносно вас.",
        reply_markup=get_main_menu(),
    )


@dp.callback_query(F.data == "back_main")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("Головне меню:", reply_markup=get_main_menu())
    await callback.answer()


@dp.callback_query(F.data == "menu_food_cat")
async def food_cat_menu(callback: types.CallbackQuery):
    await callback.message.answer(
        "🍲 **Оберіть формат пошуку закладів:**",
        reply_markup=get_food_categories_menu(),
        parse_mode="Markdown",
    )
    await callback.answer()


@dp.callback_query(F.data == "menu_places_cat")
async def places_cat_menu(callback: types.CallbackQuery):
    await callback.message.answer(
        "🏛️ **Оберіть напрямок для прогулянок:**",
        reply_markup=get_places_categories_menu(),
        parse_mode="Markdown",
    )
    await callback.answer()


@dp.callback_query(F.data == "menu_weather_events")
async def weather_events_menu(callback: types.CallbackQuery):
    await callback.message.answer(
        "🌤️ **Оберіть розділ:**",
        reply_markup=get_weather_events_menu(),
        parse_mode="Markdown",
    )
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
        parse_mode="Markdown",
    )
    await callback.answer()


@dp.callback_query(F.data == "menu_fortune")
async def menu_fortune_handler(callback: types.CallbackQuery):
    fortunes = [
        "✨ Сьогодні вам посміхнеться така удача, шо навіть на Привозі вам зроблять знижку без торга!",
        "🇺🇦 Завжди майте за себе гордість — ви знаходитесь у найколоритнішому місті світу, і все буде Україна!",
        "☕️ На вас чекає день, повний приємних несподінок та смачної кави на Дерибасівській.",
        "🌊 Чорне море змиє всі турботи, а поїздка зі Станіславом зарядить енергією на увесь тиждень!",
        "💰 Фінансовий успіх уже на підході — готуйтеся приймати приємні новини та прибуток.",
        "🚗 Ваша дорога сьогодні буде легкою, зелені світлофори супроводжуватимуть усюди!",
        "⚓️ Сьогодні в Одесі навіть вітер дує у ваш бік — сміливо беріться за задумане!",
        "🍋 Настрій буде легким, як морський бриз біля Ланжерону, а справи підуть як по маслу.",
        "🎭 День обіцяє яскраву подію або приємну зустріч, про яку ще буде що згадати.",
        "🌟 Якщо сьогодні виникне питання — правильна відповідь сама знайде вас ще до обіду.",
        "🐟 Достаток любить тих, хто не робить собі нерви — тримайте спокій і приймайте бонуси долі.",
        "🎶 Сьогодні у вас буде чудовий привід усміхнутися та сказати: «Таки гарний день!»",
    ]
    chosen_fortune = random.choice(fortunes)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Ще одне пророцтво", callback_data="menu_fortune")],
            [InlineKeyboardButton(text="⬅️ Головне меню", callback_data="back_main")],
        ]
    )
    await callback.message.answer(
        f"🇺🇦 **Одесське пророцтво:**\n\n{chosen_fortune}",
        reply_markup=kb,
        parse_mode="Markdown",
    )
    await callback.answer()


@dp.callback_query(F.data == "menu_odessa_quiz")
async def menu_quiz_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(QuizState.active_question)
    await state.update_data(current_q=0, score=0)
    await send_quiz_question(callback.message, state, 0, 0)
    await callback.answer()


async def send_quiz_question(message: types.Message, state: FSMContext, q_index: int, score: int):
    if q_index >= len(QUIZ_QUESTIONS):
        await state.clear()
        if score >= 7:
            rank = "👑 Головний магістр одеського гумору та колориту!"
        elif score >= 4:
            rank = "⚓ Свій хлопець / Корінний одесит!"
        elif score >= 1:
            rank = "🌊 Впевнений гість, який уже ловить одеську хвилю!"
        else:
            rank = "🚶 Турист, який тільки вчиться говорити «Тю!»"

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Пройти тест знову", callback_data="menu_odessa_quiz")],
                [InlineKeyboardButton(text="⬅️ Головне меню", callback_data="back_main")],
            ]
        )
        await message.answer(
            f"🏁 **Тест «Ти Одесит?» завершено!**\n\nВаш результат: **{score} з {len(QUIZ_QUESTIONS)}** правильних відповідей.\nВаш одеський ранг: *{rank}*",
            reply_markup=kb,
            parse_mode="Markdown",
        )
        return

    q_data = QUIZ_QUESTIONS[q_index]
    inline_rows = []
    for idx, (opt_text, _) in enumerate(q_data["options"]):
        inline_rows.append([InlineKeyboardButton(text=opt_text, callback_data=f"quiz_ans_{q_index}_{idx}")])

    inline_rows.append([InlineKeyboardButton(text="❌ Перервати тест", callback_data="back_main")])
    kb = InlineKeyboardMarkup(inline_keyboard=inline_rows)

    await message.answer(
        f"🧠 **Ти Одесит?**\n\n(Питання {q_index + 1} з {len(QUIZ_QUESTIONS)})\n\n{q_data['q']}",
        reply_markup=kb,
        parse_mode="Markdown",
    )


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


@dp.callback_query(F.data == "menu_business")
async def menu_business_handler(callback: types.CallbackQuery):
    business_text = (
        "💼 **B2B послуги та партнерство для бізнесу:**\n\n"
        "• **Корпоративні поїздки:** Комфортний трансфер керівництва, зустріч ділових партнерів.\n"
        "• **Експрес-доставка:** Конфіденційна та пунктуальна доставка важливих документів чи посилок.\n"
        "• **Реклама у боті:** Можливість розміщення інформації про ваш заклад чи послуги для пасажирів.\n"
        "• **Довгострокова співпраця:** Закріплення авто за вашою компанією.\n\n"
        "Обирайте дію нижче або відкрийте розділ **«🤝 Свої люди»**:"
    )
    direct_chat_url = f"https://t.me/{MY_TELEGRAM_USERNAME}"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Залишити заявку для бізнесу", callback_data="business_request_start")],
            [InlineKeyboardButton(text="🤝 Свої люди (Реферальна програма)", callback_data="menu_referral")],
            [InlineKeyboardButton(text="💬 Написати напряму", url=direct_chat_url)],
            [InlineKeyboardButton(text="⬅️ Головне меню", callback_data="back_main")],
        ]
    )
    await callback.message.answer(business_text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()


@dp.callback_query(F.data == "business_request_start")
async def business_request_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(BusinessPartnerState.waiting_for_request)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Скасувати", callback_data="back_main")]])
    await callback.message.answer(
        "📝 Напишіть у наступному повідомленні ваші контакти, назву компанії та суть запиту (реклама, доставка чи корпоративні поїздки):",
        reply_markup=kb,
    )
    await callback.answer()


@dp.message(BusinessPartnerState.waiting_for_request)
async def process_business_request(message: types.Message, state: FSMContext):
    user = message.from_user
    text = message.text or "[медіа/вкладення — дивіться нижче]"
    await state.clear()

    admin_text = (
        f"💼 **Нова B2B заявка / партнерство!**\n\n"
        f"• **Клієнт:** {user.full_name} (@{user.username or 'немає'})\n"
        f"• **ID:** `{user.id}`\n"
        f"• **Запит:** {text}"
    )
    try:
        await bot.send_message(chat_id=ADMIN_TELEGRAM_ID, text=admin_text, parse_mode="Markdown")
        if not message.text:
            await message.copy_to(chat_id=ADMIN_TELEGRAM_ID)
    except Exception:
        pass

    await message.answer(
        "✅ Вашу заявку успішно надіслано Станіславу! Він зв'яжеться з вами найближчим часом для обговорення деталей.",
        reply_markup=get_main_menu(),
    )


@dp.callback_query(F.data == "menu_shelters")
async def menu_shelters_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_lat, user_lon = user_locations.get(user_id, (ODESA_LAT, ODESA_LON))

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


@dp.callback_query(F.data == "menu_wifi")
async def menu_wifi_handler(callback: types.CallbackQuery):
    wifi_text = (
        "📶 **Wi-Fi у салоні автомобіля:**\n\n"
        "• **Назва мережі (SSID):** `Pixel`\n"
        "• **Пароль:** `12345678`\n\n"
        "Користуйтеся інтернетом без обмежень під час поїздки! 🌐"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ До розділу водія", callback_data="category_transport_climate")],
            [InlineKeyboardButton(text="🏠 Головне меню", callback_data="back_main")],
        ]
    )
    await callback.message.answer(wifi_text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()


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

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Поділитися посиланням", url=share_url)],
            [InlineKeyboardButton(text="⬅️ До бізнесу та партнерів", callback_data="menu_business")],
            [InlineKeyboardButton(text="🏠 Головне меню", callback_data="back_main")],
        ]
    )
    await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")
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
    }
    msg_text = texts.get(action, "Запит по комфорту")

    admin_text = (
        f"⚙️ **Побажання щодо атмосфери!**\n\n"
        f"• **Пасажир:** {user.full_name} (@{user.username or 'немає'})\n"
        f"• **ID:** `{user.id}`\n"
        f"• **Запит:** {msg_text}"
    )
    try:
        await bot.send_message(chat_id=ADMIN_TELEGRAM_ID, text=admin_text, parse_mode="Markdown")
    except Exception:
        pass

    await callback.answer("✅ Водію надіслано ваше побажання!", show_alert=True)


@dp.callback_query(F.data == "menu_booking")
async def menu_booking(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(BookingState.waiting_for_details)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Скасувати", callback_data="back_main")]])
    await callback.message.answer(
        "📅 **Замовити поїздку зі Станіславом наперед:**\n\nНапишіть у наступному повідомленні дату, час, маршрут (звідки і куди) та ваші побажання:",
        reply_markup=kb,
        parse_mode="Markdown",
    )
    await callback.answer()


@dp.message(BookingState.waiting_for_details)
async def process_booking(message: types.Message, state: FSMContext):
    user = message.from_user
    text = message.text or "[медіа/вкладення — дивіться нижче]"
    await state.clear()

    admin_text = (
        f"📅 **Заявка на попереднє замовлення!**\n\n"
        f"• **Клієнт:** {user.full_name} (@{user.username or 'немає'})\n"
        f"• **ID:** `{user.id}`\n"
        f"• **Деталі:** {text}"
    )
    try:
        await bot.send_message(chat_id=ADMIN_TELEGRAM_ID, text=admin_text, parse_mode="Markdown")
        if not message.text:
            await message.copy_to(chat_id=ADMIN_TELEGRAM_ID)
    except Exception:
        pass

    await message.answer(
        "✅ Вашу заявку успішно надіслано водію! Він зв'яжеться з вами найближчим часом.",
        reply_markup=get_main_menu(),
    )


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
        ("«Вы мне не делаете погоду»", "Ваша думка ніяк не впливає на мої плани."),
    ]
    word, desc = random.choice(slang_words)
    text = (
        f"📖 **Одеський словник у дорозі:**\n\n"
        f"🔸 **{word}** — *{desc}*\n\n"
        f"Натисніть кнопку нижче, щоб дізнатися інше слово:"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Інше слово", callback_data="menu_slang")],
            [InlineKeyboardButton(text="⬅️ Головне меню", callback_data="back_main")],
        ]
    )
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
        parse_mode="Markdown",
    )
    await callback.answer()


# --- ЖИВА ПОГОДА ТА АВТОНОМНА АФІША ПОДІЙ ---
@dp.callback_query(F.data == "get_weather")
async def weather_handler(callback: types.CallbackQuery):
    weather_text = await fetch_live_weather()
    await callback.message.answer(weather_text, reply_markup=get_weather_events_menu(), parse_mode="Markdown")
    await callback.answer()


@dp.callback_query(F.data == "get_events")
async def events_handler(callback: types.CallbackQuery):
    events_today = get_current_events()
    current_date_str = datetime.now().strftime("%d.%m.%Y")
    updated_note = f"\n*(оновлено: {events_cache['updated_at']})*" if events_cache["updated_at"] else ""
    text_lines = f"🎭 **Актуальні події в Одесі на {current_date_str}:**{updated_note}\n\n"
    inline_rows = []
    for i, item in enumerate(events_today, 1):
        date_str = item.get("date") or "Дата та час за посиланням"
        text_lines += (
            f"{i}. **{item['name']}**\n"
            f"   🗓️ *Дата / час:* {date_str}\n\n"
        )
        inline_rows.append([InlineKeyboardButton(text=f"👉 {item['name'][:36]}", callback_data=f"show_place_{item['id']}")])

    inline_rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_weather_events")])
    kb = InlineKeyboardMarkup(inline_keyboard=inline_rows)
    await callback.message.answer(text_lines, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()


async def send_random_closest_items(callback: types.CallbackQuery, data_list: list, keyboard_to_return):
    user_id = callback.from_user.id
    user_lat, user_lon = user_locations.get(user_id, (ODESA_LAT, ODESA_LON))
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
    rows = []
    if item.get("url"):
        rows.append([InlineKeyboardButton(text="🎟️ Деталі, дати та квитки", url=item["url"])])
    rows.append([InlineKeyboardButton(text="🗺️ На мапі Google", url=maps_url)])
    rows.append(
        [
            InlineKeyboardButton(text="👍 Лайк", callback_data=f"like_{item['id']}"),
            InlineKeyboardButton(text="👎 Дизлайк", callback_data=f"dislike_{item['id']}"),
        ]
    )
    rows.append([InlineKeyboardButton(text="⬅️ Головне меню", callback_data="back_main")])
    detail_kb = InlineKeyboardMarkup(inline_keyboard=rows)

    date_line = f"\n• *Дата / час:* {item['date']}" if item.get("date") else ""
    venue_label = "Де проходить" if item.get("url") else "Адреса"
    caption = (
        f"📍 **{item['name']}**{date_line}\n"
        f"• *{venue_label}:* {item['addr']}\n"
        f"• *Опис:* {item['desc']}"
    )
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
    await callback.message.answer(
        "💳 **Чайові водію (ПриватБанк):**\n`5457 0825 2151 8477`",
        parse_mode="Markdown",
        reply_markup=get_transport_climate_menu(),
    )
    await callback.answer()


@dp.callback_query(F.data == "tr_review")
async def transport_review_prompt(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(FeedbackState.waiting_for_comment)
    await callback.message.answer("✍️ Напишіть ваш відгук або пропозицію наступним повідомленням:")
    await callback.answer()


@dp.message(FeedbackState.waiting_for_comment)
async def save_user_review(message: types.Message, state: FSMContext):
    user = message.from_user
    comment = message.text or "[медіа/вкладення — дивіться нижче]"
    await state.clear()

    admin_text = f"📩 **Новий відгук!**\n• **Від:** {user.full_name} (@{user.username or 'немає'})\n• **Текст:** {comment}"
    try:
        await bot.send_message(chat_id=ADMIN_TELEGRAM_ID, text=admin_text, parse_mode="Markdown")
        if not message.text:
            await message.copy_to(chat_id=ADMIN_TELEGRAM_ID)
    except Exception:
        pass
    await message.answer("🙏 Щиро дякуємо за ваш відгук!", reply_markup=get_transport_climate_menu())


@dp.callback_query(F.data == "tr_rate")
async def transport_rate(callback: types.CallbackQuery):
    rating_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⭐ 1", callback_data="rate_1"),
                InlineKeyboardButton(text="⭐ 2", callback_data="rate_2"),
                InlineKeyboardButton(text="⭐ 3", callback_data="rate_3"),
                InlineKeyboardButton(text="⭐ 4", callback_data="rate_4"),
                InlineKeyboardButton(text="⭐ 5", callback_data="rate_5"),
            ],
            [InlineKeyboardButton(text="⬅️ Меню", callback_data="back_main")],
        ]
    )
    await callback.message.answer("Оцініть якість поїздки:", reply_markup=rating_kb)
    await callback.answer()


@dp.callback_query(F.data.startswith("rate_"))
async def process_rating(callback: types.CallbackQuery):
    stars = callback.data.split("_")[1]
    user = callback.from_user
    try:
        await bot.send_message(chat_id=ADMIN_TELEGRAM_ID, text=f"⭐ **Оцінка поїздки:** {stars}/5 від {user.full_name}", parse_mode="Markdown")
    except Exception:
        pass
    await callback.message.answer(f"❤️ Дякуємо за оцінку {stars}/5!", reply_markup=get_transport_climate_menu())
    await callback.answer()


@dp.message()
async def handle_text_message(message: types.Message):
    response_text = smart_smart_response(message.text or "")
    await message.answer(response_text, reply_markup=get_main_menu())


# ==================== ВЕБСЕРВЕР, АВТО-ПІНГ ТА ФОНОВЕ ОНОВЛЕННЯ АФІШІ ====================

async def handle(request):
    return web.Response(text="I am alive!")


async def web_server():
    app = web.Application()
    app.add_routes([web.get("/", handle), web.get("/health", handle)])
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    return runner


async def keep_alive_ping():
    base_url = (os.getenv("RENDER_EXTERNAL_URL") or "https://odesa-bot-1.onrender.com").rstrip("/")
    ping_url = f"{base_url}/health"
    await asyncio.sleep(30)

    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(ping_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    logging.info("Keep-alive ping -> %s [%s]", ping_url, resp.status)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logging.warning("Keep-alive ping не вдався: %s", exc)

        await asyncio.sleep(600)


async def events_auto_updater():
    await asyncio.sleep(5)
    while True:
        try:
            await refresh_events_cache()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logging.warning("Помилка фонового оновлення афіші: %s", exc)

        await asyncio.sleep(21600)


async def main():
    init_db()
    load_events_from_disk()
    runner = await web_server()
    ping_task = asyncio.create_task(keep_alive_ping())
    events_task = asyncio.create_task(events_auto_updater())
    print("Бот успішно запущено разом із вебсервером на Render...")

    try:
        await set_bot_commands(bot)
    except Exception as e:
        print(f"Попередження при встановленні команд: {e}")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        for task in (ping_task, events_task):
            task.cancel()
        await asyncio.gather(ping_task, events_task, return_exceptions=True)
        await bot.session.close()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())