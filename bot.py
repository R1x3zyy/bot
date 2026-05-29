import asyncio
import logging
import os
import re

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
    get_product_config,
    get_transactions,
    get_user,
    get_user_orders,
    update_user_language,
)


load_dotenv()


BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
PRODUCT_CODE = "gemini_link_18_month"
SUPPORT_USERNAME = "@R1x3zyy"
TELEGRAM_USERNAME_RE = re.compile(r"^@[A-Za-z0-9_]{5,32}$")
CE = {
    "gemini": ("5321197740800120767", "🤖"),
    "shop": ("5309801015015405183", "🎁"),
    "planet": ("5454102570312166471", "🪐"),
    "link": ("5454068128969417666", "🔗"),
    "stock": ("5348149223223211884", "📦"),
    "cart": ("5319204558147188648", "🛒"),
    "card": ("5454134258580877567", "💳"),
    "support": ("5453952087543015968", "💬"),
    "fire": ("5454182246250474905", "🔥"),
    "bolt": ("5458746443571421160", "⚡️"),
    "ok": ("5273806972871787310", "✅"),
    "globe": ("5447410659077661506", "🌐"),
    "chart": ("5244837092042750681", "📈"),
    "spark": ("5325547803936572038", "✨"),
}


def ce(name: str) -> str:
    emoji_id, fallback = CE[name]
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


class OrderState(StatesGroup):
    waiting_for_contact = State()


class AdminState(StatesGroup):
    waiting_for_links = State()


router = Router()


def is_admin(user_id: int) -> bool:
    return bool(ADMIN_ID and ADMIN_ID.isdigit() and int(ADMIN_ID) == user_id)


async def get_lang(user_id: int) -> str:
    user = await get_user(user_id)
    lang = user["language"] if user else "ru"
    return lang if lang in {"ru", "en"} else "ru"


def main_menu(lang: str = "ru") -> ReplyKeyboardMarkup:
    if lang == "en":
        keyboard = [["Catalog", "Profile"], ["Support"]]
        placeholder = "Choose a section"
    else:
        keyboard = [["Каталог", "Профиль"], ["Поддержка"]]
        placeholder = "Выберите раздел"

    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=item) for item in row] for row in keyboard],
        resize_keyboard=True,
        input_field_placeholder=placeholder,
    )


async def catalog_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    product = await get_product_config(PRODUCT_CODE)
    stock = await count_available_links()
    back = "⬅️ Back" if lang == "en" else "⬅️ Назад"
    item_suffix = "pcs" if lang == "en" else "шт."
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🤖 {product['title']} | {stock} {item_suffix}",
                    callback_data=f"product:{PRODUCT_CODE}",
                )
            ],
            [InlineKeyboardButton(text=back, callback_data="menu:home")],
        ]
    )


def product_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    if lang == "en":
        order_text = "🛒 Place order"
        back_text = "⬅️ Back to catalog"
    else:
        order_text = "🛒 Оформить заказ"
        back_text = "⬅️ Назад в каталог"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=order_text, callback_data="order:start")],
            [InlineKeyboardButton(text=back_text, callback_data="catalog:open")],
        ]
    )


def profile_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    if lang == "en":
        buttons = [
            ("💳 Top up balance", "profile:topup"),
            ("🙋 My purchases", "profile:purchases"),
            ("🎟 Promo code", "profile:promo"),
            ("📈 Transactions", "profile:transactions"),
            ("👥 Referral system", "profile:ref"),
            ("🌐 Language", "profile:language"),
            ("🔙 Back", "menu:home"),
        ]
    else:
        buttons = [
            ("💳 Пополнить баланс", "profile:topup"),
            ("🙋 Мои покупки", "profile:purchases"),
            ("🎟 Промокод", "profile:promo"),
            ("📈 Транзакции", "profile:transactions"),
            ("👥 Реф. система", "profile:ref"),
            ("🌐 Язык / Language", "profile:language"),
            ("🔙 Назад", "menu:home"),
        ]

    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=data)] for text, data in buttons]
    )


def profile_back_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    if lang == "en":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Back to profile", callback_data="profile:open")],
                [InlineKeyboardButton(text="🏠 Main menu", callback_data="menu:home")],
            ]
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад в профиль", callback_data="profile:open")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:home")],
        ]
    )


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="language:set:ru")],
            [InlineKeyboardButton(text="🇬🇧 English", callback_data="language:set:en")],
            [InlineKeyboardButton(text="⬅️ Назад / Back", callback_data="profile:open")],
        ]
    )


async def home_text(lang: str = "ru") -> str:
    product = await get_product_config(PRODUCT_CODE)
    stock = await count_available_links()

    if lang == "en":
        return (
            f"{ce('spark')} <b>Welcome to the store!</b>\n\n"
            f"{ce('gemini')} <b>Available product:</b>\n"
            "<blockquote>"
            f"{ce('gemini')} {product['title']}\n"
            f"{ce('link')} Activation via personal link"
            "</blockquote>\n\n"
            f"{ce('fire')} <b>Why choose us:</b>\n"
            "<blockquote>"
            f"{ce('bolt')} Fast delivery\n"
            f"{ce('card')} Easy balance top-up\n"
            f"{ce('ok')} Activation warranty\n"
            f"{ce('support')} Support: {SUPPORT_USERNAME}"
            "</blockquote>\n\n"
            f"{ce('stock')} <b>In stock:</b> {stock}\n\n"
            "Choose an action below:"
        )

    return (
        f"{ce('spark')} <b>Добро пожаловать в магазин!</b>\n\n"
        f"{ce('shop')} <b>В нашем магазине вы можете приобрести:</b>\n"
        "<blockquote>"
        f"{ce('gemini')} {product['title']}\n"
        f"{ce('link')} Активация по персональной ссылке"
        "</blockquote>\n\n"
        f"{ce('fire')} <b>Наши преимущества:</b>\n"
        "<blockquote>"
        f"{ce('bolt')} Быстрая выдача\n"
        f"{ce('card')} Удобное пополнение баланса\n"
        f"{ce('ok')} Гарантия на активацию\n"
        f"{ce('support')} Поддержка: {SUPPORT_USERNAME}"
        "</blockquote>\n\n"
        f"{ce('stock')} <b>Сейчас в наличии:</b> {stock}\n\n"
        "Выберите действие ниже:"
    )


def support_text(lang: str = "ru") -> str:
    if lang == "en":
        return (
            f"{ce('support')} <b>Support center</b>\n\n"
            "If you have a question about payment, delivery, activation or your order, "
            "message our support directly.\n\n"
            f"{ce('ok')} Support username: {SUPPORT_USERNAME}\n\n"
            f"We will help you as soon as possible. {ce('spark')}"
        )

    return (
        f"{ce('support')} <b>Центр поддержки</b>\n\n"
        "Если у вас вопрос по оплате, выдаче, активации или заказу, "
        "напишите в поддержку напрямую.\n\n"
        f"{ce('ok')} Юзернейм поддержки: {SUPPORT_USERNAME}\n\n"
        f"Поможем разобраться как можно быстрее. {ce('spark')}"
    )


async def product_text(lang: str = "ru") -> str:
    product = await get_product_config(PRODUCT_CODE)
    stock = await count_available_links()
    price_rub = int(product["price_rub"])
    price_usd = float(product["price_usd"])

    if lang == "en":
        return (
            f"{ce('gemini')} <b>{product['title']}</b>\n\n"
            f"{product['description']}\n\n"
            f"{ce('card')} <b>Price:</b> {price_rub} ₽ / {price_usd:g} $\n"
            f"{ce('stock')} <b>Stock:</b> {stock}\n"
            f"{ce('bolt')} <b>Delivery:</b> after order confirmation.\n\n"
            "If links are temporarily out of stock, your order can be reserved and processed after restock."
        )

    return (
        f"{ce('gemini')} <b>{product['title']}</b>\n\n"
        f"{product['description']}\n\n"
        f"{ce('card')} <b>Цена:</b> {price_rub} ₽ / {price_usd:g} $\n"
        f"{ce('stock')} <b>Количество:</b> {stock}\n"
        f"{ce('bolt')} <b>Выдача:</b> после подтверждения заказа.\n\n"
        "Если ссылки временно закончились, заказ можно зарезервировать и обработать после пополнения наличия."
    )


async def profile_text(user_id: int, lang: str = "ru") -> str:
    user = await get_user(user_id)
    orders = await get_user_orders(user_id)
    balance = int(user["balance"]) if user else 0
    ref_code = user["ref_code"] if user else f"ref{user_id}"

    if lang == "en":
        return (
            f"{ce('gemini')} <b>Profile</b>\n\n"
            f"ID: <code>{user_id}</code>\n"
            f"{ce('card')} Balance: <b>{balance} ₽</b>\n"
            f"Orders: <b>{len(orders)}</b>\n"
            f"Referral code: <code>{ref_code}</code>"
        )

    return (
        f"{ce('gemini')} <b>Профиль</b>\n\n"
        f"ID: <code>{user_id}</code>\n"
        f"{ce('card')} Баланс: <b>{balance} ₽</b>\n"
        f"Покупок оформлено: <b>{len(orders)}</b>\n"
        f"Реф. код: <code>{ref_code}</code>"
    )


def format_orders(orders: list, lang: str = "ru") -> str:
    if not orders:
        return "You have no purchases yet." if lang == "en" else "У вас пока нет оформленных покупок."

    lines = ["<b>🙋 My purchases</b>" if lang == "en" else "<b>🙋 Мои покупки</b>"]
    for order in orders[-10:]:
        if lang == "en":
            lines.append(
                "\n"
                f"#{order['id']} - {order['product_title']}\n"
                f"Status: {order['status']}\n"
                f"Date: {order['created_at']:%Y-%m-%d %H:%M}"
            )
        else:
            lines.append(
                "\n"
                f"#{order['id']} - {order['product_title']}\n"
                f"Статус: {order['status']}\n"
                f"Дата: {order['created_at']:%Y-%m-%d %H:%M}"
            )
    return "\n".join(lines)


def format_transactions(transactions: list, lang: str = "ru") -> str:
    if not transactions:
        return "No transactions yet." if lang == "en" else "Транзакций пока нет."

    lines = ["<b>📈 Transactions</b>" if lang == "en" else "<b>📈 Транзакции</b>"]
    for tx in transactions[-10:]:
        if lang == "en":
            lines.append(
                "\n"
                f"{tx['created_at']:%Y-%m-%d %H:%M} - {tx['type']}\n"
                f"Amount: {int(tx['amount'])} ₽\n"
                f"Description: {tx['description']}"
            )
        else:
            lines.append(
                "\n"
                f"{tx['created_at']:%Y-%m-%d %H:%M} - {tx['type']}\n"
                f"Сумма: {int(tx['amount'])} ₽\n"
                f"Описание: {tx['description']}"
            )
    return "\n".join(lines)


@router.message(CommandStart())
async def start(message: Message) -> None:
    user = await ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    lang = user["language"] if user["language"] in {"ru", "en"} else "ru"
    await message.answer(await home_text(lang), reply_markup=main_menu(lang))


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
async def add_links_command(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Добавлять ссылки может только администратор. Узнать ID: /myid")
        return

    raw_text = message.text or ""
    links = [line.strip() for line in raw_text.splitlines()[1:] if line.strip()]
    if not links:
        await state.set_state(AdminState.waiting_for_links)
        await message.answer(
            "Отправьте ссылки следующим сообщением или сразу после команды:\n\n"
            "/addlinks\n"
            "976 https://example.com/link-1\n"
            "977 https://example.com/link-2\n\n"
            "Также подойдет формат без номеров:\n"
            "https://example.com/link-1\n"
            "https://example.com/link-2"
        )
        return

    added = await add_links(links)
    await message.answer(
        f"Добавлено ссылок: <b>{added}</b>\n"
        f"Теперь в наличии: <b>{await count_available_links()}</b>"
    )


@router.message(AdminState.waiting_for_links)
async def add_links_from_next_message(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        await message.answer("Добавлять ссылки может только администратор. Узнать ID: /myid")
        return

    links = (message.text or "").splitlines()
    added = await add_links(links)
    await state.clear()

    if not added:
        await message.answer(
            "Я не нашел ссылок в сообщении. Отправьте строки вида:\n\n"
            "976 https://example.com/link-1\n"
            "977 https://example.com/link-2"
        )
        return

    await message.answer(
        f"Добавлено ссылок: <b>{added}</b>\n"
        f"Теперь в наличии: <b>{await count_available_links()}</b>"
    )


@router.message(F.text.casefold().in_({"каталог", "catalog"}))
async def show_catalog(message: Message) -> None:
    lang = await get_lang(message.from_user.id)
    await message.answer("Catalog:" if lang == "en" else "Каталог:", reply_markup=await catalog_keyboard(lang))


@router.message(F.text.casefold().in_({"профиль", "profile"}))
async def show_profile(message: Message) -> None:
    await ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    lang = await get_lang(message.from_user.id)
    await message.answer(await profile_text(message.from_user.id, lang), reply_markup=profile_keyboard(lang))


@router.message(F.text.casefold().in_({"поддержка", "support"}))
async def show_support(message: Message) -> None:
    lang = await get_lang(message.from_user.id)
    await message.answer(support_text(lang), reply_markup=main_menu(lang))


@router.callback_query(F.data == "menu:home")
async def open_home(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    await callback.message.answer(await home_text(lang), reply_markup=main_menu(lang))
    await callback.answer()


@router.callback_query(F.data == "catalog:open")
async def open_catalog(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    await callback.message.edit_text("Catalog:" if lang == "en" else "Каталог:", reply_markup=await catalog_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == f"product:{PRODUCT_CODE}")
async def open_product(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    await callback.message.edit_text(await product_text(lang), reply_markup=product_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "profile:open")
async def open_profile(callback: CallbackQuery) -> None:
    await ensure_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
    lang = await get_lang(callback.from_user.id)
    await callback.message.edit_text(await profile_text(callback.from_user.id, lang), reply_markup=profile_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "profile:topup")
async def profile_topup(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    text = (
        "💳 Balance top-up is handled by the administrator for now. Message support with the amount and payment method."
        if lang == "en"
        else "💳 Пополнение баланса пока проходит через администратора. Напишите сумму и способ оплаты в поддержку."
    )
    await callback.message.edit_text(text, reply_markup=profile_back_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "profile:purchases")
async def profile_purchases(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    await callback.message.edit_text(
        format_orders(await get_user_orders(callback.from_user.id), lang),
        reply_markup=profile_back_keyboard(lang),
    )
    await callback.answer()


@router.callback_query(F.data == "profile:promo")
async def profile_promo(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    text = f"{ce('fire')} No active promo codes right now." if lang == "en" else f"{ce('fire')} Сейчас активных промокодов нет."
    await callback.message.edit_text(text, reply_markup=profile_back_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "profile:transactions")
async def profile_transactions(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    await callback.message.edit_text(
        format_transactions(await get_transactions(callback.from_user.id), lang),
        reply_markup=profile_back_keyboard(lang),
    )
    await callback.answer()


@router.callback_query(F.data == "profile:ref")
async def profile_ref(callback: CallbackQuery, bot: Bot) -> None:
    user = await ensure_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
    lang = await get_lang(callback.from_user.id)
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user['ref_code']}"
    if lang == "en":
        text = (
            "<b>👥 Referral system</b>\n\n"
            f"Your code: <code>{user['ref_code']}</code>\n"
            f"Your link: {ref_link}\n\n"
            "Referral rewards can be configured later."
        )
    else:
        text = (
            "<b>👥 Реферальная система</b>\n\n"
            f"Ваш код: <code>{user['ref_code']}</code>\n"
            f"Ваша ссылка: {ref_link}\n\n"
            "Начисления за приглашения можно подключить отдельными правилами."
        )
    await callback.message.edit_text(text, reply_markup=profile_back_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "profile:language")
async def profile_language(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    current = "English" if lang == "en" else "Русский"
    await callback.message.edit_text(
        f"{ce('globe')} <b>Language / Язык</b>\n\nCurrent: <b>{current}</b>\n\nChoose language:",
        reply_markup=language_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("language:set:"))
async def set_language(callback: CallbackQuery) -> None:
    lang = callback.data.split(":")[-1]
    if lang not in {"ru", "en"}:
        await callback.answer()
        return

    await ensure_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
    await update_user_language(callback.from_user.id, lang)
    text = f"{ce('ok')} Language changed to English." if lang == "en" else f"{ce('ok')} Язык изменён на русский."
    await callback.message.edit_text(text, reply_markup=profile_back_keyboard(lang))
    await callback.message.answer(await home_text(lang), reply_markup=main_menu(lang))
    await callback.answer()


@router.callback_query(F.data == "order:start")
async def start_order(callback: CallbackQuery, state: FSMContext) -> None:
    lang = await get_lang(callback.from_user.id)
    await state.set_state(OrderState.waiting_for_contact)
    text = (
        f"{ce('support')} Send your Telegram username in this format: <b>@username</b>"
        if lang == "en"
        else f"{ce('support')} Напишите ваш Telegram юзернейм в таком формате: <b>@username</b>"
    )
    await callback.message.answer(text)
    await callback.answer()


@router.message(OrderState.waiting_for_contact)
async def receive_order_contact(message: Message, state: FSMContext, bot: Bot) -> None:
    await ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    lang = await get_lang(message.from_user.id)
    product = await get_product_config(PRODUCT_CODE)
    stock = await count_available_links()
    contact = (message.text or "").strip()
    if not TELEGRAM_USERNAME_RE.fullmatch(contact):
        error_text = (
            f"{ce('support')} Please send only your Telegram username in this format: <b>@username</b>"
            if lang == "en"
            else f"{ce('support')} Пожалуйста, отправьте только ваш Telegram юзернейм в формате: <b>@username</b>"
        )
        await message.answer(error_text)
        return

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
        f"{ce('cart')} <b>Новый заказ</b>\n\n"
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
    done_text = (
        f"{ce('ok')} Order created. It is now visible in My purchases. The administrator will contact you."
        if lang == "en"
        else f"{ce('ok')} Заказ оформлен. Он появился в разделе «Мои покупки». Администратор свяжется с вами."
    )
    await message.answer(done_text, reply_markup=main_menu(lang))


@router.message()
async def fallback(message: Message) -> None:
    lang = await get_lang(message.from_user.id)
    text = "Choose an action from the menu." if lang == "en" else "Выберите действие в меню."
    await message.answer(text, reply_markup=main_menu(lang))


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
