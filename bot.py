import asyncio
import logging
import os
import random
from aiohttp import web

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "").strip()
DRIVER_USERNAME = os.getenv("DRIVER_USERNAME", "").strip().lstrip("@")

if not BOT_TOKEN:
    raise RuntimeError("Не задана переменная окружения BOT_TOKEN")

ADMIN_ID = int(ADMIN_ID_RAW) if ADMIN_ID_RAW.isdigit() else 0

router = Router()


class ContactDriverState(StatesGroup):
    waiting_message = State()


class QuizState(StatesGroup):
    question_idx = State()
    score = State()


# --- ДАННЫЕ РАЗДЕЛОВ ---

PROPHECIES = [
    "🔮 <b>Одеське пророцтво:</b> Сьогодні поїздка складеться так легко, наче спуститися сходами до моря без черги. Усе встигнете!",
    "🔮 <b>Одеське пророцтво:</b> Чекайте на приємну новину або смачну каву там, де ви зовсім не планували зупинятися.",
    "🔮 <b>Одеське пророцтво:</b> Якщо сьогодні й сперечатися — то лише про те, де смачніше: на Привозі чи біля моря. У решті справ — повний штиль.",
    "🔮 <b>Одеське пророцтво:</b> Не поспішайте робити висновки до вечора — головний козир дня ще ховається в кишені.",
    "🔮 <b>Одеське пророцтво:</b> Сьогодні вас супроводжує одеський фарт: світлофори будуть зеленими, а люди — адекватними.",
    "🔮 <b>Одеське пророцтво:</b> Дозвольте собі хоча б годину спокою без зайвої метушні — це найкраща інвестиція на найближчі дні.",
    "🔮 <b>Одеське пророцтво:</b> Хтось сьогодні згадає вас добрим словом і принесе корисний контакт або вигідну ідею.",
    "🔮 <b>Одеське пророцтво:</b> Найкращий маршрут сьогодні — той, де є трохи повітря, гарна музика і жодного нервового поспіху.",
    "🔮 <b>Одеське пророцтво:</b> Фінанси люблять акуратність: сьогодні вдалий момент навести лад у планах і не витрачати зайве на дрібниці.",
    "🔮 <b>Одеське пророцтво:</b> Сьогоднішній день дасть відповідь на питання, яке ви крутили в голові останні кілька днів.",
    "🔮 <b>Одеське пророцтво:</b> Посміхніться — в Одесі це працює краще за будь-який талісман і відкриває правильні двері.",
    "🔮 <b>Одеське пророцтво:</b> Чекає несподівана зустріч або теплий дзвінок, який підніме настрій краще за будь-який еспресо.",
]

QUIZ_QUESTIONS = [
    {
        "q": "Питання 1/6. Що для справжнього одесита означає фраза «піти на базар»?",
        "options": [
            ("Поспіхом купити пакет яблук і втекти", 0),
            ("Прогулятися, поговорити за життя, скуштувати і піти з повними руками", 2),
            ("Замовити доставку, не виходячи з дому", 0),
        ],
    },
    {
        "q": "Питання 2/6. Як правильно реагувати, коли на вулиці йде дощ, а парасольки немає?",
        "options": [
            ("Влаштувати драму на пів кварталу", 0),
            ("Зайти в затишне місце на каву й перечекати з гумором", 2),
            ("Образитися на погоду", 0),
        ],
    },
    {
        "q": "Питання 3/6. Що в Одесі найважливіше в будь-якій розмові?",
        "options": [
            ("Сухі звіти без емоцій", 0),
            ("Інтонація, жива мова і влучний жарт", 2),
            ("Мовчання до кінця поїздки", 0),
        ],
    },
    {
        "q": "Питання 4/6. Якщо вам кажуть: «Та ви не переживайте, воно якось буде» — це...",
        "options": [
            ("Повна байдужість", 0),
            ("Фірмовий спокій і віра в те, що все владнається", 2),
            ("Попередження про біду", 0),
        ],
    },
    {
        "q": "Питання 5/6. Який найкращий вечір біля моря?",
        "options": [
            ("Коли телефон не випускаєш із рук навіть на хвилю", 0),
            ("Коли дивишся на воду, дихаєш вітром і нікуди не біжиш", 2),
            ("Коли шукаєш, на кого поскаржитися", 0),
        ],
    },
    {
        "q": "Питання 6/6. Що для вас «свої люди»?",
        "options": [
            ("Випадкові знайомі на один раз", 0),
            ("Ті, з ким можна говорити прямо, надійно і по-людськи", 2),
            ("Люди лише заради вигоди", 0),
        ],
    },
]


# --- КЛАВІАТУРИ ---

def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🚗 Водій, поїздка та клімат"),
                KeyboardButton(text="☀️ Погода та афіша"),
            ],
            [
                KeyboardButton(text="🍲 Де поїсти"),
                KeyboardButton(text="🏛 Куди сходити"),
            ],
            [
                KeyboardButton(text="🔮 Одеське пророцтво"),
                KeyboardButton(text="🧠 Ти одесит?"),
            ],
            [
                KeyboardButton(text="💼 Бізнес та партнери"),
                KeyboardButton(text="🛡 Карта укриттів"),
            ],
            [
                KeyboardButton(text="📅 Замовити наперед"),
                KeyboardButton(text="📖 Одеський словник"),
            ],
            [
                KeyboardButton(text="🏠 Головне меню"),
                KeyboardButton(text="📍 Поділитися геолокацією"),
            ],
        ],
        resize_keyboard=True,
    )


def business_partners_keyboard() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="✉️ Написати водію через бота",
            callback_data="write_driver_bot",
        )
    )
    if DRIVER_USERNAME:
        kb.row(
            InlineKeyboardButton(
                text=f"💬 Відкрити чат (@{DRIVER_USERNAME})",
                url=f"https://t.me/{DRIVER_USERNAME}",
            )
        )
    kb.row(
        InlineKeyboardButton(
            text="🤝 Свої люди",
            callback_data="open_svoi_lyudy",
        )
    )
    return kb


# --- ХЕНДЛЕРИ ---

@router.message(CommandStart())
@router.message(F.text == "🏠 Головне меню")
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    user_name = message.from_user.first_name if message.from_user else "друже"
    text = (
        f"Шалом і здрастуйте, {user_name}! ⚓️ Вітаю у найзатишнішому екіпажі Одеси.\n\n"
        "Мене звати Станіслав, ваш персональний водій (Suzuki Swift). "
        "Цей інтерактивний мінігід допоможе зробити вашу поїздку максимально комфортною, "
        "цікавою та корисною.\n\n"
        "Оберіть потрібний розділ у меню нижче 👇"
    )
    await message.answer(text, reply_markup=main_menu_keyboard())


@router.message(F.text == "🚗 Водій, поїздка та клімат")
async def driver_and_comfort(message: Message) -> None:
    text = (
        "🚗 <b>Водій, поїздка та комфорт у салоні</b>\n\n"
        "• <b>Водій:</b> Станіслав (Suzuki Swift)\n"
        "• <b>Клімат і атмосфера:</b> скажіть, якщо потрібно тепліше/прохолодніше або змінити музику.\n"
        "• <b>Аудіо / Bluetooth:</b> підключення через <code>Bluetooth S13</code> (за погодженням з водієм).\n\n"
        "📶 <b>Wi-Fi у салоні:</b>\n"
        "• Мережа: <code>Pixel</code>\n"
        "• Пароль: <code>12345678</code>"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(F.text == "🔮 Одеське пророцтво")
async def odesa_prophecy(message: Message) -> None:
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎲 Ще одне пророцтво",
                    callback_data="more_prophecy",
                )
            ]
        ]
    )
    await message.answer(
        random.choice(PROPHECIES),
        parse_mode="HTML",
        reply_markup=kb,
    )


@router.callback_query(F.data == "more_prophecy")
async def more_prophecy_cb(callback: CallbackQuery) -> None:
    await callback.answer()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎲 Ще одне пророцтво",
                    callback_data="more_prophecy",
                )
            ]
        ]
    )
    await callback.message.answer(
        random.choice(PROPHECIES),
        parse_mode="HTML",
        reply_markup=kb,
    )


# --- ТЕСТ «ТИ ОДЕСИТ?» ---

async def send_quiz_question(target_message: Message, idx: int) -> None:
    item = QUIZ_QUESTIONS[idx]
    builder = InlineKeyboardBuilder()
    for opt_idx, (label, _) in enumerate(item["options"]):
        builder.row(
            InlineKeyboardButton(
                text=label,
                callback_data=f"quiz_ans:{idx}:{opt_idx}",
            )
        )
    await target_message.answer(
        f"🧠 <b>Тест «Ти одесит?»</b>\n\n{item['q']}",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )


@router.message(F.text == "🧠 Ти одесит?")
async def start_quiz(message: Message, state: FSMContext) -> None:
    await state.set_state(QuizState.question_idx)
    await state.update_data(question_idx=0, score=0)
    await send_quiz_question(message, 0)


@router.callback_query(F.data.startswith("quiz_ans:"))
async def handle_quiz_answer(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    _, q_idx_str, opt_idx_str = callback.data.split(":")
    q_idx = int(q_idx_str)
    opt_idx = int(opt_idx_str)

    if q_idx < 0 or q_idx >= len(QUIZ_QUESTIONS):
        return

    points = QUIZ_QUESTIONS[q_idx]["options"][opt_idx][1]
    data = await state.get_data()
    score = int(data.get("score", 0)) + points
    next_idx = q_idx + 1

    if next_idx < len(QUIZ_QUESTIONS):
        await state.update_data(question_idx=next_idx, score=score)
        await send_quiz_question(callback.message, next_idx)
    else:
        await state.clear()
        max_score = len(QUIZ_QUESTIONS) * 2
        if score >= 10:
            verdict = "Ви — стовідсотковий одесит (або душа Одеси)! Можна сміливо торгуватися на Привозі та вести філософські розмови біля моря."
        elif score >= 6:
            verdict = "Майже свій в дошку: одеський настрій уже відчувається, ще пара прогулянок біля моря — і буде повний дзен."
        else:
            verdict = "Ви — гість із характером: усе попереду, Одеса швидко навчить дивитися на життя легше і з посмішкою."

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔄 Пройти ще раз",
                        callback_data="restart_quiz",
                    )
                ]
            ]
        )
        await callback.message.answer(
            f"🏁 <b>Результат тесту «Ти одесит?»</b>\n\n"
            f"Ваш результат: <b>{score} з {max_score}</b> балів.\n\n"
            f"{verdict}",
            parse_mode="HTML",
            reply_markup=kb,
        )


@router.callback_query(F.data == "restart_quiz")
async def restart_quiz_cb(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(QuizState.question_idx)
    await state.update_data(question_idx=0, score=0)
    await send_quiz_question(callback.message, 0)


# --- БІЗНЕС ТА ПАРТНЕРИ + СВОЇ ЛЮДИ ---

@router.message(F.text == "💼 Бізнес та партнери")
async def business_and_partners(message: Message) -> None:
    contact_line = (
        f"• Прямий контакт у Telegram: @{DRIVER_USERNAME}\n"
        if DRIVER_USERNAME
        else "• Прямий зв'язок: натисніть кнопку нижче, щоб надіслати повідомлення напряму водію через бота.\n"
    )
    text = (
        "💼 <b>Бізнес та партнери</b>\n\n"
        "Відкритий до співпраці, локальних проєктів, трансферів і корисних партнерств в Одесі.\n\n"
        f"{contact_line}"
        "Також у цьому розділі зібрано блок <b>«Свої люди»</b> — перевірені контакти та дружні сервіси."
    )
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=business_partners_keyboard().as_markup(),
    )


@router.callback_query(F.data == "open_svoi_lyudy")
async def open_svoi_lyudy_cb(callback: CallbackQuery) -> None:
    await callback.answer()
    text = (
        "🤝 <b>Свої люди</b>\n\n"
        "Тут зібрані контакти та рекомендації «своїх» — без випадкових посередників.\n"
        "Якщо вам потрібен надійний контакт чи рекомендація в Одесі — напишіть водію через кнопку нижче."
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✉️ Написати водію через бота",
                    callback_data="write_driver_bot",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад до «Бізнес та партнери»",
                    callback_data="back_to_business",
                )
            ],
        ]
    )
    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "back_to_business")
async def back_to_business_cb(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        "💼 <b>Бізнес та партнери</b>\n\nОберіть потрібну дію нижче:",
        parse_mode="HTML",
        reply_markup=business_partners_keyboard().as_markup(),
    )


@router.callback_query(F.data == "write_driver_bot")
async def write_driver_bot_cb(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not ADMIN_ID:
        await callback.message.answer(
            "Зв'язок через бота тимчасово не налаштовано (не вказано ADMIN_ID у змінних середовища)."
        )
        return
    await state.set_state(ContactDriverState.waiting_message)
    await callback.message.answer(
        "✍️ Напишіть ваше повідомлення одним текстом — я передам його Станіславу.\n"
        "Щоб скасувати, натисніть «🏠 Головне меню»."
    )


@router.message(ContactDriverState.waiting_message)
async def forward_to_driver(message: Message, state: FSMContext, bot: Bot) -> None:
    if message.text == "🏠 Головне меню":
        await cmd_start(message, state)
        return

    await state.clear()
    sender = message.from_user
    sender_info = f"{sender.full_name}" if sender else "Пасажир"
    if sender and sender.username:
        sender_info += f" (@{sender.username})"
    if sender:
        sender_info += f" [ID: <code>{sender.id}</code>]"

    try:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"📩 <b>Нове повідомлення з бота пасажиру/партнеру</b>\n"
                f"Від: {sender_info}\n\n"
                f"{message.text or '[медіа/вкладення]'}"
            ),
            parse_mode="HTML",
        )
        await message.answer(
            "✅ Повідомлення надіслано! Дякую, що звернулися.",
            reply_markup=main_menu_keyboard(),
        )
    except Exception as exc:
        logging.exception("Не удалось отправить сообщение админу: %s", exc)
        await message.answer(
            "Не вдалося надіслати повідомлення автоматично. Спробуйте ще раз трохи пізніше.",
            reply_markup=main_menu_keyboard(),
        )


# --- ІНШІ РОЗДІЛИ МЕНЮ ---

@router.message(F.text == "☀️ Погода та афіша")
async def weather_and_afisha(message: Message) -> None:
    await message.answer(
        "☀️ <b>Погода та афіша — Одеса</b>\n\n"
        "Актуальну погоду за вікном і події на сьогодні підкажу під час поїздки — "
        "просто скажіть, який настрій (прогулянка, театр, кава чи море).",
        parse_mode="HTML",
    )


@router.message(F.text == "🍲 Де поїсти")
async def where_to_eat(message: Message) -> None:
    await message.answer(
        "🍲 <b>Де поїсти в Одесі</b>\n\n"
        "Підкажу перевірені місця під ваш запит: сніданок, обід у центрі, "
        "риба/морепродукти чи затишна кав'ярня по маршруту.",
        parse_mode="HTML",
    )


@router.message(F.text == "🏛 Куди сходити")
async def where_to_go(message: Message) -> None:
    await message.answer(
        "🏛 <b>Куди сходити в Одесі</b>\n\n"
        "Історичний центр, Приморський бульвар, Театральна площа, морське узбережжя або тихі дворики — "
        "підберемо локацію під час і вільний час.",
        parse_mode="HTML",
    )


@router.message(F.text == "🛡 Карта укриттів")
async def shelters_map(message: Message) -> None:
    await message.answer(
        "🛡 <b>Карта укриттів та безпека</b>\n\n"
        "Натисніть <b>«📍 Поділитися геолокацією»</b> внизу, щоб зорієнтуватися поруч із вашою точкою, "
        "або зверніться до водія щодо найближчих укриттів по маршруту.",
        parse_mode="HTML",
    )


@router.message(F.text == "📅 Замовити наперед")
async def book_ahead(message: Message) -> None:
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📝 Залишити заявку на поїздку",
                    callback_data="write_driver_bot",
                )
            ]
        ]
    )
    await message.answer(
        "📅 <b>Замовити поїздку наперед</b>\n\n"
        "Натисніть кнопку нижче та вкажіть дату, час, звідки і куди їхати — "
        "повідомлення одразу прийде водію.",
        parse_mode="HTML",
        reply_markup=kb,
    )


@router.message(F.text == "📖 Одеський словник")
async def odesa_dictionary(message: Message) -> None:
    await message.answer(
        "📖 <b>Одеський словник</b>\n\n"
        "• <b>Шо?</b> — універсальне питання, яке не завжди вимагає відповіді.\n"
        "• <b>Тю!</b> — легке здивування або іронія.\n"
        "• <b>Гешефт</b> — вигідна справа або вдалий результат.\n"
        "• <b>Розміняти полтинник</b> — побутовий квест із дрібними грошима.",
        parse_mode="HTML",
    )


@router.message(F.location)
async def handle_location(message: Message) -> None:
    lat = message.location.latitude
    lon = message.location.longitude
    await message.answer(
        f"📍 <b>Геолокацію отримано:</b> <code>{lat:.5f}, {lon:.5f}</code>\n\n"
        "Орієнтуємося за поточною точкою. Якщо потрібно підказати найближче укриття чи локацію поруч — напишіть.",
        parse_mode="HTML",
    )


# --- ВЕБ-СЕРВЕР ДЛЯ RENDER ---

async def healthcheck(request: web.Request) -> web.Response:
    return web.Response(text="OK")


async def start_web_server() -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/", healthcheck)
    app.router.add_get("/health", healthcheck)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info("HTTP-сервер запущен на порту %s", port)
    return runner


async def main() -> None:
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    runner = await start_web_server()
    try:
        # drop_pending_updates=True помогает избежать зависших старых апдейтов при рестарте
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
