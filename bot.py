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
    FSInputFile,
)

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN", "").strip() or "9271959219:AAG1hj2yp8KaQM7qTf7QUUXWsnIH6KwWzFU"
DB_NAME = "odesa_concierge.db"
DRIVER_PHOTO_PATH = "driver.jpg"  # Фото водія у корені репозиторію

_admin_env = os.getenv("ADMIN_ID", "").strip()
ADMIN_TELEGRAM_ID = int(_admin_env) if _admin_env.isdigit() else 546552675
MY_TELEGRAM_USERNAME = os.getenv("DRIVER_USERNAME", "").strip().lstrip("@") or "karbaze_dev"

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
