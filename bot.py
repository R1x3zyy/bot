import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
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
from dotenv import load_dotenv

from db import (
    add_links,
    count_available_links,
    create_order,
    ensure_schema,
    ensure_user,
    get_transactions,
    get_product_config,
    get_user,
    get_user_orders,
)


load_dotenv()


BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")


PRODUCT_CODE = "gemini_link_18_month"


class OrderState(StatesGroup):
    waiting_for_contact = State()


router = Router()


def is_admin(user_id: int) -> bool:
    return bool(ADMIN_ID and ADMIN_ID.isdigit() and int(ADMIN_ID) == user_id)


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Каталог"), KeyboardButton(text="Профиль")],
            [KeyboardButton(text="Поддержка")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите раздел",
    )


async def catalog_keyboard() -> InlineKeyboardMarkup:
    product = await get_product_config(PRODUCT_CODE)
    stock = await count_available_links()
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{product['title']} | {stock} шт.",
                    callback_data=f"product:{PRODUCT_CODE}",
                )
            ],
            [InlineKeyboardButton(text="Назад", callback_data="menu:home")],
        ]
    )


def product_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Оформить заказ", callback_data="order:start")],
            [InlineKeyboardButton(text="Назад в каталог", callback_data="catalog:open")],
        ]
    )


def profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="profile:topup")],
            [InlineKeyboardButton(text="🙋‍♀️ Мои покупки", callback_data="profile:purchases")],
            [InlineKeyboardButton(text="🎟 Промокод", callback_data="profile:promo")],
            [InlineKeyboardButton(text="📈 Транзакции", callback_data="profile:transactions")],
            [InlineKeyboardButton(text="👥 Реф. система", callback_data="profile:ref")],
            [InlineKeyboardButton(text="🌐 Язык / Language", callback_data="profile:language")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="menu:home")],
        ]
    )


def profile_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Назад в профиль", callback_data="profile:open")],
            [InlineKeyboardButton(text="Главное меню", callback_data="menu:home")],
        ]
    )


async def home_text() -> str:
    product = await get_product_config(PRODUCT_CODE)
    stock = await count_available_links()
    return (
        "👋 <b>Добро пожаловать в магазин!</b>\n\n"
        "🛒 <b>В нашем магазине вы можете приобрести:</b>\n"
        "<blockquote>"
        f"🔗 {product['title']}\n"
        "🤖 Google AI Pro на 18 месяцев\n"
        "💾 Google Drive 5 ТБ\n"
        "⚡ Активация по персональной ссылке"
        "</blockquote>\n\n"
        "✨ <b>Наши преимущества:</b>\n"
        "<blockquote>"
        "⚡ Быстрая выдача\n"
        "💳 Удобное пополнение баланса\n"
        "✅ Гарантия на активацию\n"
        "💬 Поддержка по заказам"
        "</blockquote>\n\n"
        f"📦 <b>Сейчас в наличии:</b> {stock}\n\n"
        "Выберите действие ниже:"
    )


def support_text() -> str:
    return (
        "Напишите ваш вопрос одним сообщением. Если хотите оформить покупку, "
        "откройте каталог и нажмите кнопку заказа в карточке товара."
    )


async def product_text() -> str:
    product = await get_product_config(PRODUCT_CODE)
    stock = await count_available_links()
    price_rub = int(product["price_rub"])
    price_usd = float(product["price_usd"])
    return (
        f"<b>{product['title']}</b>\n\n"
        f"{product['description']}\n\n"
        f"<b>Цена:</b> {price_rub} ₽ / {price_usd:g} $\n"
        f"<b>Количество:</b> {stock}\n"
        "<b>Выдача:</b> моментально после подтверждения заказа.\n\n"
        "Если ссылки закончились, заказ можно зарезервировать: он будет обработан после пополнения наличия."
    )


async def profile_text(user_id: int) -> str:
    user = await get_user(user_id)
    orders = await get_user_orders(user_id)
    balance = int(user["balance"]) if user else 0
    ref_code = user["ref_code"] if user else f"ref{user_id}"
    return (
        "<b>Профиль</b>\n\n"
        f"ID: <code>{user_id}</code>\n"
        f"Баланс: <b>{balance} ₽</b>\n"
        f"Покупок оформлено: <b>{len(orders)}</b>\n"
        f"Реф. код: <code>{ref_code}</code>"
    )


def format_orders(orders: list) -> str:
    if not orders:
        return "У вас пока нет оформленных покупок."

    lines = ["<b>Мои покупки</b>"]
    for order in orders[-10:]:
        lines.append(
            "\n"
            f"#{order['id']} - {order['product_title']}\n"
            f"Статус: {order['status']}\n"
            f"Дата: {order['created_at']:%Y-%m-%d %H:%M}"
        )
    return "\n".join(lines)


def format_transactions(transactions: list) -> str:
    if not transactions:
        return "Транзакций пока нет."

    lines = ["<b>Транзакции</b>"]
    for tx in transactions[-10:]:
        lines.append(
            "\n"
            f"{tx['created_at']:%Y-%m-%d %H:%M} - {tx['type']}\n"
            f"Сумма: {int(tx['amount'])} ₽\n"
            f"Описание: {tx['description']}"
        )
    return "\n".join(lines)


@router.message(CommandStart())
async def start(message: Message) -> None:
    await ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    await message.answer(await home_text(), reply_markup=main_menu())


@router.message(Command("myid"))
async def my_id(message: Message) -> None:
    await message.answer(f"Ваш Telegram ID: <code>{message.from_user.id}</code>")


@router.message(Command("stock"))
async def stock(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только администратору.")
        return

    await message.answer(f"Сейчас в наличии ссылок: <b>{await count_available_links()}</b>")


@router.message(Command("addlinks"))
async def add_links_command(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer(
            "Добавлять ссылки может только администратор. "
            "Укажите свой Telegram ID в ADMIN_ID в файле .env. Узнать ID: /myid"
        )
        return

    raw_text = message.text or ""
    links = [line.strip() for line in raw_text.splitlines()[1:] if line.strip()]
    if not links:
        await message.answer(
            "Отправьте ссылки так:\n\n"
            "/addlinks\n"
            "https://example.com/link-1\n"
            "https://example.com/link-2"
        )
        return

    added = await add_links(links)
    await message.answer(
        f"Добавлено ссылок: <b>{added}</b>\n"
        f"Теперь в наличии: <b>{await count_available_links()}</b>"
    )


@router.message(F.text.casefold() == "каталог")
async def show_catalog(message: Message) -> None:
    await message.answer("Каталог:", reply_markup=await catalog_keyboard())


@router.message(F.text.casefold() == "профиль")
async def show_profile(message: Message) -> None:
    await ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    await message.answer(await profile_text(message.from_user.id), reply_markup=profile_keyboard())


@router.message(F.text.casefold() == "поддержка")
async def show_support(message: Message) -> None:
    await message.answer(support_text())


@router.callback_query(F.data == "menu:home")
async def open_home(callback: CallbackQuery) -> None:
    await callback.message.answer(await home_text(), reply_markup=main_menu())
    await callback.answer()


@router.callback_query(F.data == "catalog:open")
async def open_catalog(callback: CallbackQuery) -> None:
    await callback.message.edit_text("Каталог:", reply_markup=await catalog_keyboard())
    await callback.answer()


@router.callback_query(F.data == f"product:{PRODUCT_CODE}")
async def open_product(callback: CallbackQuery) -> None:
    await callback.message.edit_text(await product_text(), reply_markup=product_keyboard())
    await callback.answer()


@router.callback_query(F.data == "profile:open")
async def open_profile(callback: CallbackQuery) -> None:
    await ensure_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
    await callback.message.edit_text(await profile_text(callback.from_user.id), reply_markup=profile_keyboard())
    await callback.answer()


@router.callback_query(F.data == "profile:topup")
async def profile_topup(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "Пополнение баланса пока проходит через администратора. Напишите сумму и удобный способ оплаты в поддержку.",
        reply_markup=profile_back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "profile:purchases")
async def profile_purchases(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        format_orders(await get_user_orders(callback.from_user.id)),
        reply_markup=profile_back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "profile:promo")
async def profile_promo(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "Раздел промокодов подготовлен. Сейчас активных промокодов нет.",
        reply_markup=profile_back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "profile:transactions")
async def profile_transactions(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        format_transactions(await get_transactions(callback.from_user.id)),
        reply_markup=profile_back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "profile:ref")
async def profile_ref(callback: CallbackQuery, bot: Bot) -> None:
    user = await ensure_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user['ref_code']}"
    await callback.message.edit_text(
        "<b>Реферальная система</b>\n\n"
        f"Ваш код: <code>{user['ref_code']}</code>\n"
        f"Ваша ссылка: {ref_link}\n\n"
        "Начисления за приглашения можно подключить отдельными правилами.",
        reply_markup=profile_back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "profile:language")
async def profile_language(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "Сейчас выбран язык: Русский.\n\nПереключение языка можно расширить, когда появятся тексты для других языков.",
        reply_markup=profile_back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "order:start")
async def start_order(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(OrderState.waiting_for_contact)
    await callback.message.answer(
        "Отправьте контакт для связи одним сообщением: username, номер телефона или другой удобный способ."
    )
    await callback.answer()


@router.message(OrderState.waiting_for_contact)
async def receive_order_contact(message: Message, state: FSMContext, bot: Bot) -> None:
    await ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    product = await get_product_config(PRODUCT_CODE)
    stock = await count_available_links()
    contact = message.text or "Пользователь отправил сообщение без текста."
    username = f"@{message.from_user.username}" if message.from_user.username else "username не указан"
    status = "Ожидает обработки" if stock else "Резерв, нет в наличии"

    order = await create_order(
        user_id=message.from_user.id,
        username=username,
        product_code=PRODUCT_CODE,
        product_title=product["title"],
        price_rub=int(product["price_rub"]),
        contact=contact,
        status=status,
    )

    admin_message = (
        "<b>Новый заказ</b>\n\n"
        f"Заказ: #{order['id']}\n"
        f"Товар: {product['title']}\n"
        f"Цена: {int(product['price_rub'])} ₽\n"
        f"Наличие ссылок: {stock}\n"
        f"Покупатель: {username}\n"
        f"ID: <code>{message.from_user.id}</code>\n"
        f"Контакт: {contact}"
    )

    if ADMIN_ID:
        try:
            await bot.send_message(int(ADMIN_ID), admin_message)
        except ValueError:
            logging.exception("ADMIN_ID must be a number")
        except Exception:
            logging.exception("Could not send order to admin")

    await state.clear()
    await message.answer(
        "Заказ оформлен. Он появился в разделе «Мои покупки». Администратор свяжется с вами для оплаты и выдачи.",
        reply_markup=main_menu(),
    )


@router.message()
async def fallback(message: Message) -> None:
    await message.answer("Выберите действие в меню.", reply_markup=main_menu())


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set. Add it to the .env file.")

    logging.basicConfig(level=logging.INFO)
    await ensure_schema()

    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
