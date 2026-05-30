import asyncio
import html
import logging
import os
import re
from typing import Any, Awaitable, Callable

import aiohttp
from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
    TelegramObject,
)
from dotenv import load_dotenv

from db import (
    add_links,
    admin_stats,
    complete_platega_payment,
    complete_crypto_payment,
    count_available_links,
    create_balance_order,
    create_crypto_payment,
    create_platega_payment,
    create_review,
    ensure_schema,
    ensure_user,
    get_crypto_payment,
    get_platega_payment,
    get_product_config,
    get_transactions,
    get_user,
    get_user_orders,
    issue_links_to_order,
    list_active_crypto_payments,
    list_pending_platega_payments,
    list_users,
    record_bot_visit,
    update_user_language,
)


load_dotenv()


BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
REVIEWS_CHANNEL_ID = os.getenv("REVIEWS_CHANNEL_ID")
REQUIRED_CHANNEL_ID = os.getenv("REQUIRED_CHANNEL_ID", "@r1x3zyyshop")
REQUIRED_CHANNEL_URL = os.getenv("REQUIRED_CHANNEL_URL", "https://t.me/r1x3zyyshop")
CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN")
CRYPTOBOT_API_URL = os.getenv("CRYPTOBOT_API_URL", "https://pay.crypt.bot/api")
PLATEGA_MERCHANT_ID = os.getenv("PLATEGA_MERCHANT_ID")
PLATEGA_SECRET = os.getenv("PLATEGA_SECRET")
PLATEGA_API_URL = os.getenv("PLATEGA_API_URL", "https://app.platega.io")
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
    "news_catalog": ("5229064374403998351", "🛍"),
    "news_bolt": ("5456140674028019486", "⚡️"),
    "news_money": ("5409048419211682843", "💵"),
    "news_chat": ("5443038326535759644", "💬"),
    "news_announce": ("5424818078833715060", "📣"),
    "news_question": ("5436113877181941026", "❓"),
    "news_shield": ("5251203410396458957", "🛡"),
    "news_gear": ("5341715473882955310", "⚙️"),
    "news_pencil": ("5395444784611480792", "✏️"),
    "news_info": ("5334544901428229844", "ℹ️"),
}


def ce(name: str) -> str:
    emoji_id, fallback = CE[name]
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


def format_price(product: dict) -> str:
    price_rub = int(product["price_rub"])
    price_usd = float(product["price_usd"])
    return f"{price_rub} ₽ / {price_usd:g} $"


def balance_topup_text(balance: int, required: int, lang: str = "ru") -> str:
    missing = max(required - balance, 0)
    if lang == "en":
        return (
            f"{ce('news_money')} <b>Not enough balance</b>\n\n"
            f"Your balance: <b>{balance} ₽</b>\n"
            f"Required: <b>{required} ₽</b>\n"
            f"Missing: <b>{missing} ₽</b>\n\n"
            f"Choose a top-up method:"
        )

    return (
        f"{ce('news_money')} <b>Недостаточно средств на балансе</b>\n\n"
        f"Ваш баланс: <b>{balance} ₽</b>\n"
        f"Нужно: <b>{required} ₽</b>\n"
        f"Не хватает: <b>{missing} ₽</b>\n\n"
        f"Выберите способ пополнения:"
    )


async def cryptobot_request(method: str, payload: dict | None = None) -> dict:
    if not CRYPTOBOT_TOKEN:
        raise RuntimeError("CRYPTOBOT_TOKEN is not set")

    url = f"{CRYPTOBOT_API_URL.rstrip('/')}/{method}"
    headers = {"Crypto-Pay-API-Token": CRYPTOBOT_TOKEN}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.post(url, json=payload or {}) as response:
            data = await response.json(content_type=None)

    if not data.get("ok"):
        raise RuntimeError(data.get("error") or "CryptoBot API error")
    return data["result"]


async def create_cryptobot_invoice(amount_rub: int, description: str, payload: str) -> dict:
    return await cryptobot_request(
        "createInvoice",
        {
            "currency_type": "fiat",
            "fiat": "RUB",
            "amount": str(amount_rub),
            "accepted_assets": "USDT,TON,BTC,ETH,LTC,BNB,TRX,USDC",
            "description": description[:1024],
            "payload": payload,
            "allow_comments": False,
            "allow_anonymous": False,
            "expires_in": 3600,
        },
    )


async def get_cryptobot_invoice(invoice_id: int) -> dict | None:
    result = await cryptobot_request("getInvoices", {"invoice_ids": str(invoice_id)})
    if isinstance(result, list):
        return result[0] if result else None
    if isinstance(result, dict):
        items = result.get("items") or result.get("invoices") or []
        return items[0] if items else None
    return None


async def platega_request(method: str, path: str, payload: dict | None = None) -> dict:
    if not PLATEGA_MERCHANT_ID or not PLATEGA_SECRET:
        raise RuntimeError("PLATEGA_MERCHANT_ID or PLATEGA_SECRET is not set")

    url = f"{PLATEGA_API_URL.rstrip('/')}/{path.lstrip('/')}"
    headers = {
        "X-MerchantId": PLATEGA_MERCHANT_ID,
        "X-Secret": PLATEGA_SECRET,
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        if method == "GET":
            async with session.get(url) as response:
                data = await response.json(content_type=None)
        else:
            async with session.post(url, json=payload or {}) as response:
                data = await response.json(content_type=None)

    if isinstance(data, dict) and (data.get("error") or data.get("statusCode", 200) >= 400):
        raise RuntimeError(str(data.get("message") or data.get("error") or data))
    return data


async def create_platega_invoice(amount_rub: int, description: str, payload: str) -> dict:
    return await platega_request(
        "POST",
        "v2/transaction/process",
        {
            "paymentDetails": {
                "amount": amount_rub,
                "currency": "RUB",
            },
            "description": description[:255],
            "return": REQUIRED_CHANNEL_URL,
            "failedUrl": REQUIRED_CHANNEL_URL,
            "payload": payload,
        },
    )


async def get_platega_transaction(transaction_id: str) -> dict:
    return await platega_request("GET", f"transaction/{transaction_id}")


class OrderState(StatesGroup):
    waiting_for_contact = State()


class BulkOrderState(StatesGroup):
    waiting_for_quantity = State()
    waiting_for_payment = State()
    waiting_for_contact = State()


class CryptoOrderState(StatesGroup):
    waiting_for_contact = State()


class TopUpState(StatesGroup):
    waiting_for_amount = State()


class ReviewState(StatesGroup):
    waiting_for_comment = State()


class AdminState(StatesGroup):
    waiting_for_links = State()


class BroadcastState(StatesGroup):
    waiting_for_text = State()


router = Router()


def is_admin(user_id: int) -> bool:
    return bool(ADMIN_ID and ADMIN_ID.isdigit() and int(ADMIN_ID) == user_id)


def subscription_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    subscribe_text = "📣 Subscribe" if lang == "en" else "📣 Подписаться"
    check_text = "✅ Check subscription" if lang == "en" else "✅ Проверить подписку"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=subscribe_text, url=REQUIRED_CHANNEL_URL)],
            [InlineKeyboardButton(text=check_text, callback_data="subscription:check")],
        ]
    )


def broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Отправить всем", callback_data="broadcast:send"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast:cancel"),
            ],
        ]
    )


def subscription_text(lang: str = "ru") -> str:
    if lang == "en":
        return (
            f"{ce('news_announce')} <b>Subscribe to the channel first</b>\n\n"
            "After subscribing, press <b>Check subscription</b>."
        )

    return (
        f"{ce('news_announce')} <b>Сначала подпишитесь на канал</b>\n\n"
        "После подписки нажмите <b>Проверить подписку</b>."
    )


async def is_subscribed(bot: Bot, user_id: int) -> bool:
    if not REQUIRED_CHANNEL_ID or is_admin(user_id):
        return True

    try:
        member = await bot.get_chat_member(REQUIRED_CHANNEL_ID, user_id)
    except Exception:
        logging.exception("Could not check required channel subscription")
        return False

    status = getattr(member.status, "value", str(member.status))
    return status not in {"left", "kicked"}


class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        bot = data.get("bot")
        if not user or not bot or not REQUIRED_CHANNEL_ID:
            return await handler(event, data)

        await record_bot_visit(user.id)

        if isinstance(event, CallbackQuery) and event.data == "subscription:check":
            return await handler(event, data)

        if await is_subscribed(bot, user.id):
            return await handler(event, data)

        lang = await get_lang(user.id)
        if isinstance(event, CallbackQuery):
            await event.answer("Подпишитесь на канал, чтобы продолжить.", show_alert=True)
            await event.message.answer(subscription_text(lang), reply_markup=subscription_keyboard(lang))
        elif isinstance(event, Message):
            await event.answer(subscription_text(lang), reply_markup=subscription_keyboard(lang))
        return None


async def get_lang(user_id: int) -> str:
    user = await get_user(user_id)
    lang = user["language"] if user else "ru"
    return lang if lang in {"ru", "en"} else "ru"


def display_user_name(user: object) -> str:
    username = getattr(user, "username", None)
    first_name = getattr(user, "first_name", None)
    if username:
        return f"@{username}"
    return first_name or ""


def start_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    if lang == "en":
        buttons = [
            [
                InlineKeyboardButton(text="🛍 Catalog", callback_data="catalog:open"),
                InlineKeyboardButton(text="👤 Profile", callback_data="profile:open"),
            ],
            [InlineKeyboardButton(text="⚙️ Other", callback_data="misc:open")],
        ]
    else:
        buttons = [
            [
                InlineKeyboardButton(text="🛍 Каталог", callback_data="catalog:open"),
                InlineKeyboardButton(text="👤 Профиль", callback_data="profile:open"),
            ],
            [InlineKeyboardButton(text="⚙️ Прочее", callback_data="misc:open")],
        ]

    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )


async def catalog_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    product = await get_product_config(PRODUCT_CODE)
    stock = await count_available_links()
    price = format_price(product)
    back = "⬅️ Back" if lang == "en" else "⬅️ Назад"
    item_suffix = "pcs" if lang == "en" else "шт."
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🛍 {product['title']} | {price} | {stock} {item_suffix}",
                    callback_data=f"product:{PRODUCT_CODE}",
                )
            ],
            [InlineKeyboardButton(text=back, callback_data="menu:home")],
        ]
    )


def product_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    if lang == "en":
        buttons = [
            [InlineKeyboardButton(text="🛒 Buy", callback_data="buy:start")],
        ]
    else:
        buttons = [
            [InlineKeyboardButton(text="🛒 Купить", callback_data="buy:start")],
        ]

    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )


def topup_payment_keyboard(amount: int, lang: str = "ru") -> InlineKeyboardMarkup:
    if lang == "en":
        buttons = [
            [InlineKeyboardButton(text=f"Platega · {amount} ₽", callback_data="topup:method:platega")],
            [InlineKeyboardButton(text=f"Crypto Bot · {amount} ₽", callback_data="topup:method:cryptobot")],
            [InlineKeyboardButton(text=f"BEP20 USDT · {amount} ₽", callback_data="topup:method:bep20")],
            [InlineKeyboardButton(text="Cancel", callback_data="topup:cancel")],
        ]
    else:
        buttons = [
            [InlineKeyboardButton(text=f"Platega · {amount} ₽", callback_data="topup:method:platega")],
            [InlineKeyboardButton(text=f"Crypto Bot · {amount} ₽", callback_data="topup:method:cryptobot")],
            [InlineKeyboardButton(text=f"BEP20 USDT · {amount} ₽", callback_data="topup:method:bep20")],
            [InlineKeyboardButton(text="Отмена", callback_data="topup:cancel")],
        ]

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def quantity_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    custom_text = "✍️ Custom quantity" if lang == "en" else "✍️ Своё количество"
    back_text = "⬅️ Product" if lang == "en" else "⬅️ Тарифы"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="1", callback_data="buy:qty:1"),
                InlineKeyboardButton(text="2", callback_data="buy:qty:2"),
                InlineKeyboardButton(text="5", callback_data="buy:qty:5"),
            ],
            [
                InlineKeyboardButton(text="10", callback_data="buy:qty:10"),
                InlineKeyboardButton(text="20", callback_data="buy:qty:20"),
            ],
            [InlineKeyboardButton(text=custom_text, callback_data="buy:custom")],
            [InlineKeyboardButton(text=back_text, callback_data=f"product:{PRODUCT_CODE}")],
        ]
    )


def bulk_payment_keyboard(quantity: int, lang: str = "ru") -> InlineKeyboardMarkup:
    if lang == "en":
        buttons = [
            [InlineKeyboardButton(text=f"Balance ×{quantity}", callback_data="bulk:pay:balance")],
            [
                InlineKeyboardButton(text=f"Platega ×{quantity}", callback_data="bulk:pay:platega"),
                InlineKeyboardButton(text=f"Crypto ×{quantity}", callback_data="bulk:pay:cryptobot"),
            ],
            [InlineKeyboardButton(text="Cancel", callback_data="bulk:cancel")],
        ]
    else:
        buttons = [
            [InlineKeyboardButton(text=f"Баланс ×{quantity}", callback_data="bulk:pay:balance")],
            [
                InlineKeyboardButton(text=f"Platega ×{quantity}", callback_data="bulk:pay:platega"),
                InlineKeyboardButton(text=f"Crypto ×{quantity}", callback_data="bulk:pay:cryptobot"),
            ],
            [InlineKeyboardButton(text="Отмена", callback_data="bulk:cancel")],
        ]

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def cryptobot_invoice_keyboard(payment_id: int, invoice_url: str, lang: str = "ru") -> InlineKeyboardMarkup:
    pay_text = "💵 Pay invoice" if lang == "en" else "💵 Оплатить счет"
    check_text = "✅ Check payment" if lang == "en" else "✅ Проверить оплату"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=pay_text, url=invoice_url)],
            [InlineKeyboardButton(text=check_text, callback_data=f"cryptobot:check:{payment_id}")],
        ]
    )


def platega_invoice_keyboard(payment_id: int, payment_url: str, lang: str = "ru") -> InlineKeyboardMarkup:
    pay_text = "💵 Pay Platega" if lang == "en" else "💵 Оплатить Platega"
    check_text = "✅ Check payment" if lang == "en" else "✅ Проверить оплату"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=pay_text, url=payment_url)],
            [InlineKeyboardButton(text=check_text, callback_data=f"platega:check:{payment_id}")],
        ]
    )


def review_prompt_keyboard(order_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    text = "⭐ Leave a review" if lang == "en" else "⭐ Оставить отзыв"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=f"review:start:{order_id}")],
        ]
    )


def review_rating_keyboard(order_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    cancel_text = "Cancel" if lang == "en" else "Отмена"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=f"{rating} ⭐", callback_data=f"review:rating:{order_id}:{rating}")
                for rating in range(1, 6)
            ],
            [InlineKeyboardButton(text=cancel_text, callback_data="review:cancel")],
        ]
    )


def help_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    home_text = "🏠 Home" if lang == "en" else "🏠 На главную"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Поддержка", url="https://t.me/R1x3zyy")],
            [InlineKeyboardButton(text=home_text, callback_data="menu:home")],
        ]
    )


def misc_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    back_text = "🔙 Back" if lang == "en" else "🔙 Назад"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Тех поддержка", url="https://t.me/R1x3zyy")],
            [
                InlineKeyboardButton(text="📣 Наш канал", url="https://t.me/r1x3zyyshop"),
                InlineKeyboardButton(text="✏️ Отзывы", callback_data="misc:reviews"),
            ],
            [InlineKeyboardButton(text="❓ FAQ", callback_data="misc:faq")],
            [InlineKeyboardButton(text="🛡 Политика конфид.", callback_data="misc:privacy")],
            [InlineKeyboardButton(text="⚙️ Польз. соглашение", callback_data="misc:terms")],
            [InlineKeyboardButton(text=back_text, callback_data="menu:home")],
        ]
    )


def profile_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    if lang == "en":
        buttons = [
            ("💵 Top up balance", "profile:topup"),
            ("🙋 My purchases", "profile:purchases"),
            ("🎟 Promo code", "profile:promo"),
            ("📈 Transactions", "profile:transactions"),
            ("👥 Referral system", "profile:ref"),
            ("🌐 Language", "profile:language"),
            ("🔙 Back", "menu:home"),
        ]
    else:
        buttons = [
            ("💵 Пополнить баланс", "profile:topup"),
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


async def home_text(lang: str = "ru", user_name: str | None = None) -> str:
    product = await get_product_config(PRODUCT_CODE)
    stock = await count_available_links()
    price = format_price(product)
    greeting_name = f", {html.escape(user_name)}" if user_name else ""

    if lang == "en":
        return (
            f"{ce('spark')} <b>Welcome to the store{greeting_name}!</b>\n\n"
            f"{ce('gemini')} <b>Available product:</b>\n"
            "<blockquote>"
            f"{ce('gemini')} {product['title']} | {price}\n"
            f"{ce('link')} Activation via personal link"
            "</blockquote>\n\n"
            f"{ce('fire')} <b>Why choose us:</b>\n"
            "<blockquote>"
            f"{ce('news_bolt')} Fast delivery\n"
            f"{ce('news_money')} Easy balance top-up\n"
            f"{ce('ok')} Activation warranty\n"
            f"{ce('support')} Support: {SUPPORT_USERNAME}"
            "</blockquote>\n\n"
            f"{ce('stock')} <b>In stock:</b> {stock}\n\n"
            "Choose an action below:"
        )

    return (
        f"{ce('spark')} <b>Добро пожаловать в магазин{greeting_name}!</b>\n\n"
        f"{ce('shop')} <b>В нашем магазине вы можете приобрести:</b>\n"
        "<blockquote>"
        f"{ce('gemini')} {product['title']} | {price}\n"
        f"{ce('link')} Активация по персональной ссылке"
        "</blockquote>\n\n"
        f"{ce('fire')} <b>Наши преимущества:</b>\n"
        "<blockquote>"
        f"{ce('news_bolt')} Быстрая выдача\n"
        f"{ce('news_money')} Удобное пополнение баланса\n"
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
    price = format_price(product)

    if lang == "en":
        return (
            f"{ce('gemini')} <b>{product['title']}</b>\n\n"
            f"{product['description']}\n\n"
            f"{ce('news_money')} <b>Price:</b> {price}\n"
            f"{ce('stock')} <b>Stock:</b> {stock}\n"
            f"{ce('news_bolt')} <b>Delivery:</b> after order confirmation.\n\n"
            "If links are temporarily out of stock, your order can be reserved and processed after restock."
        )

    return (
        f"{ce('gemini')} <b>{product['title']}</b>\n\n"
        f"{product['description']}\n\n"
        f"{ce('news_money')} <b>Цена:</b> {price}\n"
        f"{ce('stock')} <b>Количество:</b> {stock}\n"
        f"{ce('news_bolt')} <b>Выдача:</b> после подтверждения заказа.\n\n"
        "Если ссылки временно закончились, заказ можно зарезервировать и обработать после пополнения наличия."
    )


def help_text(lang: str = "ru") -> str:
    if lang == "en":
        return (
            f"{ce('support')} <b>Help</b>\n\n"
            "Privacy Policy:\n"
            "https://telegra.ph/Politika-konfidencialnosti-04-01-26\n\n"
            "User Agreement:\n"
            "https://telegra.ph/Polzovatelskoe-soglashenie-04-01-19"
        )

    return (
        f"{ce('support')} <b>Справка</b>\n\n"
        "Политика конфиденциальности:\n"
        "https://telegra.ph/Politika-konfidencialnosti-04-01-26\n\n"
        "Пользовательское соглашение:\n"
        "https://telegra.ph/Polzovatelskoe-soglashenie-04-01-19"
    )


def misc_text(lang: str = "ru") -> str:
    if lang == "en":
        return (
            f"{ce('news_gear')} <b>Other</b>\n\n"
            "Additional sections are collected here."
        )

    return (
        f"{ce('news_gear')} <b>Прочее</b>\n\n"
        "Тут собраны дополнительные разделы."
    )


def faq_text(lang: str = "ru") -> str:
    if lang == "en":
        return (
            f"{ce('news_question')} <b>FAQ</b>\n\n"
            "After placing an order, send your Telegram username in the <b>@username</b> format.\n\n"
            "Delivery is processed after order confirmation. If links are out of stock, the order can be reserved."
        )

    return (
        f"{ce('news_question')} <b>FAQ</b>\n\n"
        "После оформления заказа отправьте свой Telegram юзернейм в формате <b>@username</b>.\n\n"
        "Выдача проходит после подтверждения заказа. Если ссылок временно нет, заказ можно зарезервировать."
    )


def privacy_text(lang: str = "ru") -> str:
    if lang == "en":
        return (
            f"{ce('news_shield')} <b>Privacy Policy</b>\n\n"
            "https://telegra.ph/Politika-konfidencialnosti-04-01-26"
        )

    return (
        f"{ce('news_shield')} <b>Политика конфиденциальности</b>\n\n"
        "https://telegra.ph/Politika-konfidencialnosti-04-01-26"
    )


def terms_text(lang: str = "ru") -> str:
    if lang == "en":
        return (
            f"{ce('news_gear')} <b>User Agreement</b>\n\n"
            "https://telegra.ph/Polzovatelskoe-soglashenie-04-01-19"
        )

    return (
        f"{ce('news_gear')} <b>Пользовательское соглашение</b>\n\n"
        "https://telegra.ph/Polzovatelskoe-soglashenie-04-01-19"
    )


def reviews_text(lang: str = "ru") -> str:
    return (
        f"{ce('news_pencil')} After a completed purchase, the bot will offer you to rate the order from 1 to 5 stars and add a comment."
        if lang == "en"
        else f"{ce('news_pencil')} После выполненной покупки бот предложит оценить заказ от 1 до 5 звезд и написать комментарий."
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
            f"{ce('news_money')} Balance: <b>{balance} ₽</b>\n"
            f"Orders: <b>{len(orders)}</b>\n"
            f"Referral code: <code>{ref_code}</code>"
        )

    return (
        f"{ce('gemini')} <b>Профиль</b>\n\n"
        f"ID: <code>{user_id}</code>\n"
        f"{ce('news_money')} Баланс: <b>{balance} ₽</b>\n"
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


async def send_cryptobot_invoice(
    message: Message,
    user_id: int,
    amount_rub: int,
    purpose: str,
    lang: str,
    product_code: str = "",
    product_title: str = "",
    quantity: int = 0,
    contact: str = "",
) -> None:
    description = (
        f"Balance top-up: {amount_rub} RUB"
        if purpose == "topup"
        else f"{product_title} - {quantity or 1} pcs"
    )
    invoice = await create_cryptobot_invoice(amount_rub, description, f"{purpose}:{user_id}:{amount_rub}")
    payment = await create_crypto_payment(
        user_id=user_id,
        invoice_id=int(invoice["invoice_id"]),
        purpose=purpose,
        amount_rub=amount_rub,
        product_code=product_code,
        product_title=product_title,
        quantity=quantity,
        contact=contact,
    )
    invoice_url = invoice.get("bot_invoice_url") or invoice.get("pay_url")
    if not invoice_url:
        raise RuntimeError("CryptoBot invoice URL is missing")
    text = (
        f"{ce('news_money')} <b>Crypto Bot invoice</b>\n\n"
        f"Amount: <b>{amount_rub} ₽</b>\n\n"
        "Pay the invoice, then press <b>Check payment</b>."
        if lang == "en"
        else f"{ce('news_money')} <b>Счет Crypto Bot</b>\n\n"
        f"Сумма: <b>{amount_rub} ₽</b>\n\n"
        "Оплатите счет, затем нажмите <b>Проверить оплату</b>."
    )
    await message.answer(text, reply_markup=cryptobot_invoice_keyboard(payment["id"], invoice_url, lang))


async def send_platega_invoice(
    message: Message,
    user_id: int,
    amount_rub: int,
    purpose: str,
    lang: str,
    product_code: str = "",
    product_title: str = "",
    quantity: int = 0,
    contact: str = "",
) -> None:
    description = (
        f"Balance top-up: {amount_rub} RUB"
        if purpose == "topup"
        else f"{product_title} - {quantity or 1} pcs"
    )
    invoice = await create_platega_invoice(amount_rub, description, f"{purpose}:{user_id}:{amount_rub}")
    transaction_id = invoice.get("transactionId") or invoice.get("id")
    payment_url = invoice.get("url") or invoice.get("redirect")
    if not transaction_id or not payment_url:
        raise RuntimeError("Platega transaction id or payment URL is missing")

    payment = await create_platega_payment(
        user_id=user_id,
        transaction_id=str(transaction_id),
        purpose=purpose,
        amount_rub=amount_rub,
        product_code=product_code,
        product_title=product_title,
        quantity=quantity,
        contact=contact,
    )
    text = (
        f"{ce('news_money')} <b>Platega invoice</b>\n\n"
        f"Amount: <b>{amount_rub} ₽</b>\n\n"
        "Pay the invoice, then press <b>Check payment</b>."
        if lang == "en"
        else f"{ce('news_money')} <b>Счет Platega</b>\n\n"
        f"Сумма: <b>{amount_rub} ₽</b>\n\n"
        "Оплатите счет, затем нажмите <b>Проверить оплату</b>."
    )
    await message.answer(text, reply_markup=platega_invoice_keyboard(payment["id"], payment_url, lang))


def delivery_text(links: list[dict], lang: str = "ru") -> str:
    if len(links) == 1:
        url = html.escape(str(links[0]["url"]))
        return (
            f"{ce('ok')} <b>Your link</b>\n\n<code>{url}</code>"
            if lang == "en"
            else f"{ce('ok')} <b>Ваша ссылка</b>\n\n<code>{url}</code>"
        )

    lines = [f"{index}. <code>{html.escape(str(link['url']))}</code>" for index, link in enumerate(links, start=1)]
    return (
        f"{ce('ok')} <b>Your links</b>\n\n" + "\n".join(lines)
        if lang == "en"
        else f"{ce('ok')} <b>Ваши ссылки</b>\n\n" + "\n".join(lines)
    )


def reserved_text(lang: str = "ru") -> str:
    return (
        f"{ce('stock')} The order is paid, but there are not enough links in stock. "
        "It is reserved and will be delivered after restock."
        if lang == "en"
        else f"{ce('stock')} Заказ оплачен, но сейчас не хватает ссылок в наличии. "
        "Он зарезервирован и будет выдан после пополнения."
    )


async def deliver_order_links(message: Message, order_id: int, user_id: int, quantity: int, lang: str) -> list[dict]:
    links = await issue_links_to_order(order_id, user_id, quantity, "Выдан автоматически")
    if links is None:
        return []
    if links:
        await message.answer(delivery_text(links, lang))
        review_text = (
            f"{ce('news_pencil')} How was your purchase? You can leave a review."
            if lang == "en"
            else f"{ce('news_pencil')} Как прошла покупка? Можете оставить отзыв."
        )
        await message.answer(review_text, reply_markup=review_prompt_keyboard(order_id, lang))
    else:
        await message.answer(reserved_text(lang))
    return links


async def deliver_order_links_to_user(bot: Bot, chat_id: int, order_id: int, quantity: int, lang: str) -> list[dict]:
    links = await issue_links_to_order(order_id, chat_id, quantity, "Выдан автоматически")
    if links is None:
        return []
    if links:
        await bot.send_message(chat_id, delivery_text(links, lang))
        review_text = (
            f"{ce('news_pencil')} How was your purchase? You can leave a review."
            if lang == "en"
            else f"{ce('news_pencil')} Как прошла покупка? Можете оставить отзыв."
        )
        await bot.send_message(chat_id, review_text, reply_markup=review_prompt_keyboard(order_id, lang))
    else:
        await bot.send_message(chat_id, reserved_text(lang))
    return links


async def payment_username(user_id: int) -> str:
    user = await get_user(user_id)
    username = user["username"] if user else ""
    if username:
        return f"@{username}"
    return "username не указан"


async def notify_paid_payment(bot: Bot, payment: dict, provider: str) -> None:
    lang = await get_lang(int(payment["user_id"]))
    amount = int(payment["amount_rub"])
    if payment["purpose"] == "topup":
        text = (
            f"{ce('ok')} Balance topped up by <b>{amount} ₽</b>."
            if lang == "en"
            else f"{ce('ok')} Баланс пополнен на <b>{amount} ₽</b>."
        )
        await bot.send_message(int(payment["user_id"]), text, reply_markup=start_keyboard(lang))
        return

    quantity = int(payment["quantity"] or 1)
    issued_links = []
    if payment["order_id"]:
        issued_links = await deliver_order_links_to_user(
            bot,
            int(payment["user_id"]),
            int(payment["order_id"]),
            quantity,
            lang,
        )

    text = (
        f"{ce('ok')} Payment received. Order created and is visible in My purchases."
        if lang == "en"
        else f"{ce('ok')} Оплата получена. Заказ создан и появился в разделе «Мои покупки»."
    )
    if issued_links:
        text = (
            f"{ce('ok')} Payment received. Order created and delivered."
            if lang == "en"
            else f"{ce('ok')} Оплата получена. Заказ создан и выдан."
        )
    await bot.send_message(int(payment["user_id"]), text, reply_markup=start_keyboard(lang))

    if ADMIN_ID:
        username = await payment_username(int(payment["user_id"]))
        admin_message = (
            f"{ce('cart')} <b>Новый заказ {provider}</b>\n\n"
            f"Товар: {payment['product_title']}\n"
            f"Выдано ссылок: {len(issued_links)}\n"
            f"Сумма: {amount} ₽\n"
            f"Оплата: {provider}\n"
            f"Покупатель: {username}\n"
            f"ID: <code>{payment['user_id']}</code>\n"
            f"Контакт: {payment['contact']}"
        )
        try:
            await bot.send_message(int(ADMIN_ID), admin_message)
        except ValueError:
            logging.exception("ADMIN_ID must be a number")
        except Exception:
            logging.exception("Could not send paid order to admin")


async def auto_payment_watcher(bot: Bot) -> None:
    while True:
        try:
            for payment in await list_active_crypto_payments():
                try:
                    invoice = await get_cryptobot_invoice(int(payment["invoice_id"]))
                    if not invoice or invoice.get("status") != "paid":
                        continue
                    username = await payment_username(int(payment["user_id"]))
                    completed = await complete_crypto_payment(
                        int(payment["id"]),
                        username,
                        "Оплачен Crypto Bot, ожидает обработки",
                    )
                    if completed:
                        await notify_paid_payment(bot, completed, "Crypto Bot")
                except Exception:
                    logging.exception("Could not auto-check Crypto Bot payment %s", payment.get("id"))

            for payment in await list_pending_platega_payments():
                try:
                    transaction = await get_platega_transaction(str(payment["transaction_id"]))
                    status = str(transaction.get("status", "")).upper()
                    if status != "CONFIRMED":
                        continue
                    username = await payment_username(int(payment["user_id"]))
                    completed = await complete_platega_payment(int(payment["id"]), username, status)
                    if completed:
                        await notify_paid_payment(bot, completed, "Platega")
                except Exception:
                    logging.exception("Could not auto-check Platega payment %s", payment.get("id"))
        except Exception:
            logging.exception("Payment watcher failed")

        await asyncio.sleep(5)


async def quantity_text(lang: str = "ru") -> str:
    product = await get_product_config(PRODUCT_CODE)
    stock = await count_available_links()
    price = int(product["price_rub"])
    if lang == "en":
        return (
            f"🔢 <b>Choose quantity</b>\n\n"
            f"{ce('gemini')} Product: <b>{product['title']}</b>\n"
            f"{ce('news_money')} Price per item: <b>{price} ₽</b>\n"
            f"{ce('stock')} In stock: <b>{stock} pcs.</b>\n\n"
            "Choose quantity below or press <b>Custom quantity</b>."
        )

    return (
        f"🔢 <b>Выберите количество</b>\n\n"
        f"{ce('gemini')} Товар: <b>{product['title']}</b>\n"
        f"{ce('news_money')} Цена за 1 шт.: <b>{price} ₽</b>\n"
        f"{ce('stock')} В наличии: <b>{stock} шт.</b>\n\n"
        "Выберите количество ниже или нажмите <b>Своё количество</b>."
    )


async def process_balance_quantity_order(
    message: Message,
    state: FSMContext,
    bot: Bot,
    quantity: int,
) -> None:
    await ensure_user(message.chat.id, message.chat.username, message.chat.first_name)
    lang = await get_lang(message.chat.id)
    product = await get_product_config(PRODUCT_CODE)
    stock = await count_available_links()

    if quantity <= 0:
        text = "Quantity must be at least 1." if lang == "en" else "Количество должно быть от 1."
        await message.answer(text)
        return

    if stock and quantity > stock:
        text = (
            f"Only <b>{stock}</b> pcs are available. Choose a smaller quantity."
            if lang == "en"
            else f"Сейчас в наличии только <b>{stock}</b> шт. Выберите количество поменьше."
        )
        await message.answer(text, reply_markup=quantity_keyboard(lang))
        return

    user = await get_user(message.chat.id)
    balance = int(user["balance"]) if user else 0
    total = int(product["price_rub"]) * quantity
    if balance < total:
        missing = total - balance
        await state.set_state(TopUpState.waiting_for_amount)
        await state.update_data(topup_amount=missing)
        await message.answer(
            balance_topup_text(balance, total, lang),
            reply_markup=topup_payment_keyboard(missing, lang),
        )
        return

    username = f"@{message.chat.username}" if message.chat.username else "username не указан"
    contact = f"@{message.chat.username}" if message.chat.username else f"id:{message.chat.id}"
    order_title = product["title"] if quantity == 1 else f"{product['title']} ×{quantity}"
    status = "Ожидает обработки" if stock >= quantity else "Резерв, нет в наличии"

    order = await create_balance_order(
        user_id=message.chat.id,
        username=username,
        product_code=PRODUCT_CODE,
        product_title=order_title,
        price_rub=total,
        contact=contact,
        status=status,
    )
    if not order:
        user = await get_user(message.chat.id)
        balance = int(user["balance"]) if user else 0
        missing = max(total - balance, 1)
        await state.set_state(TopUpState.waiting_for_amount)
        await state.update_data(topup_amount=missing)
        await message.answer(
            balance_topup_text(balance, total, lang),
            reply_markup=topup_payment_keyboard(missing, lang),
        )
        return

    admin_message = (
        f"{ce('cart')} <b>Новый заказ</b>\n\n"
        f"Заказ: #{order['id']}\n"
        f"Товар: {order_title}\n"
        f"Количество: {quantity}\n"
        f"Сумма: {total} ₽\n"
        f"Оплата: баланс\n"
        f"Наличие ссылок: {stock}\n"
        f"Покупатель: {username}\n"
        f"ID: <code>{message.chat.id}</code>\n"
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
    issued_links = await deliver_order_links(message, order["id"], message.chat.id, quantity, lang)
    done_text = (
        f"{ce('ok')} Order created and delivered."
        if issued_links and lang == "en"
        else f"{ce('ok')} Заказ оформлен и выдан."
        if issued_links
        else f"{ce('ok')} Order created. It is visible in My purchases."
        if lang == "en"
        else f"{ce('ok')} Заказ оформлен. Он появился в разделе «Мои покупки»."
    )
    await message.answer(done_text, reply_markup=start_keyboard(lang))


async def show_payment_methods_for_quantity(message: Message, state: FSMContext, quantity: int, lang: str) -> None:
    stock = await count_available_links()
    if quantity <= 0:
        text = "Quantity must be at least 1." if lang == "en" else "Количество должно быть от 1."
        await message.answer(text, reply_markup=quantity_keyboard(lang))
        return

    if stock and quantity > stock:
        text = (
            f"Only <b>{stock}</b> pcs are available now. Choose a smaller quantity."
            if lang == "en"
            else f"Сейчас в наличии только <b>{stock}</b> шт. Выберите количество поменьше."
        )
        await message.answer(text, reply_markup=quantity_keyboard(lang))
        return

    product = await get_product_config(PRODUCT_CODE)
    total = int(product["price_rub"]) * quantity
    await state.update_data(bulk_quantity=quantity)
    await state.set_state(BulkOrderState.waiting_for_payment)
    text = (
        f"{ce('news_money')} Choose how to pay for the order.\n\n"
        f"Quantity: <b>{quantity}</b>\n"
        f"Amount: <b>{total} ₽</b>"
        if lang == "en"
        else f"{ce('news_money')} Выберите способ оплаты заказа.\n\n"
        f"Количество: <b>{quantity}</b>\n"
        f"Сумма: <b>{total} ₽</b>"
    )
    await message.answer(text, reply_markup=bulk_payment_keyboard(quantity, lang))


@router.message(CommandStart())
async def start(message: Message) -> None:
    user = await ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    lang = user["language"] if user["language"] in {"ru", "en"} else "ru"
    cleanup = await message.answer("Меню обновлено.", reply_markup=ReplyKeyboardRemove())
    try:
        await cleanup.delete()
    except Exception:
        logging.exception("Could not delete reply keyboard cleanup message")
    await message.answer(await home_text(lang, display_user_name(message.from_user)), reply_markup=start_keyboard(lang))


@router.callback_query(F.data == "subscription:check")
async def check_subscription(callback: CallbackQuery, bot: Bot) -> None:
    user = await ensure_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
    lang = user["language"] if user["language"] in {"ru", "en"} else "ru"
    if not await is_subscribed(bot, callback.from_user.id):
        await callback.answer("Подписка не найдена.", show_alert=True)
        await callback.message.answer(subscription_text(lang), reply_markup=subscription_keyboard(lang))
        return

    text = f"{ce('ok')} Subscription confirmed." if lang == "en" else f"{ce('ok')} Подписка подтверждена."
    await callback.message.answer(text)
    await callback.message.answer(await home_text(lang, display_user_name(callback.from_user)), reply_markup=start_keyboard(lang))
    await callback.answer()


@router.message(Command("myid"))
async def my_id(message: Message) -> None:
    await message.answer(f"Ваш Telegram ID: <code>{message.from_user.id}</code>")


@router.message(Command("stock"))
async def stock(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только администратору.")
        return

    await message.answer(f"Сейчас в наличии ссылок: <b>{await count_available_links()}</b>")


@router.message(Command("stats"))
async def stats(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только администратору.")
        return

    data = await admin_stats()
    await message.answer(
        f"{ce('chart')} <b>Статистика бота</b>\n\n"
        f"Пользователей: <b>{data['users']}</b>\n"
        f"Заказов: <b>{data['orders']}</b>\n"
        f"Ссылок в наличии: <b>{data['links']}</b>"
    )


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


@router.message(Command("broadcast"))
async def start_broadcast(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только администратору.")
        return

    await state.set_state(BroadcastState.waiting_for_text)
    await message.answer(
        f"{ce('news_announce')} <b>Рассылка всем пользователям</b>\n\n"
        "Отправьте текст сообщения. После этого я покажу предпросмотр и попрошу подтверждение."
    )


@router.message(BroadcastState.waiting_for_text)
async def receive_broadcast_text(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        await message.answer("Эта команда доступна только администратору.")
        return

    text = (message.html_text or message.text or "").strip()
    if not text:
        await message.answer("Отправьте текст для рассылки.")
        return

    if len(text) > 3500:
        await message.answer("Текст слишком длинный. Отправьте сообщение до 3500 символов.")
        return

    await state.update_data(broadcast_text=text)
    users = await list_users(None)
    await message.answer(
        f"{ce('news_announce')} <b>Предпросмотр рассылки</b>\n\n"
        f"{text}\n\n"
        f"Получателей: <b>{len(users)}</b>",
        reply_markup=broadcast_confirm_keyboard(),
    )


@router.callback_query(F.data == "broadcast:cancel")
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Недоступно.", show_alert=True)
        return

    await state.clear()
    await callback.message.answer("Рассылка отменена.")
    await callback.answer()


@router.callback_query(F.data == "broadcast:send")
async def send_broadcast(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Недоступно.", show_alert=True)
        return

    data = await state.get_data()
    text = data.get("broadcast_text")
    if not text:
        await callback.message.answer("Текст рассылки не найден. Запустите /broadcast заново.")
        await callback.answer()
        return

    users = await list_users(None)
    sent = 0
    failed = 0
    await callback.message.answer(f"Начинаю рассылку для <b>{len(users)}</b> пользователей.")
    for user in users:
        if user["id"] == callback.from_user.id:
            continue
        try:
            await bot.send_message(user["id"], text)
            sent += 1
            await asyncio.sleep(0.04)
        except Exception:
            failed += 1
            logging.exception("Could not send broadcast to user %s", user["id"])

    await state.clear()
    await callback.message.answer(
        f"{ce('ok')} <b>Рассылка завершена</b>\n\n"
        f"Отправлено: <b>{sent}</b>\n"
        f"Не удалось: <b>{failed}</b>"
    )
    await callback.answer()


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
    title = f"{ce('news_catalog')} Catalog:" if lang == "en" else f"{ce('news_catalog')} Каталог:"
    await message.answer(title, reply_markup=await catalog_keyboard(lang))


@router.message(F.text.casefold().in_({"профиль", "profile"}))
async def show_profile(message: Message) -> None:
    await ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    lang = await get_lang(message.from_user.id)
    await message.answer(await profile_text(message.from_user.id, lang), reply_markup=profile_keyboard(lang))


@router.message(F.text.casefold().in_({"поддержка", "support"}))
async def show_support(message: Message) -> None:
    lang = await get_lang(message.from_user.id)
    await message.answer(support_text(lang), reply_markup=help_keyboard(lang))


@router.message(F.text.casefold().in_({"❓ справка", "справка", "help"}))
async def show_help(message: Message) -> None:
    lang = await get_lang(message.from_user.id)
    await message.answer(help_text(lang), reply_markup=help_keyboard(lang))


@router.callback_query(F.data == "help:open")
async def open_help(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    await callback.message.edit_text(help_text(lang), reply_markup=help_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "support:open")
async def open_support(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    await callback.message.edit_text(support_text(lang), reply_markup=help_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "misc:open")
async def open_misc(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    await callback.message.edit_text(misc_text(lang), reply_markup=misc_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "misc:faq")
async def open_faq(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    await callback.message.edit_text(faq_text(lang), reply_markup=misc_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "misc:privacy")
async def open_privacy(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    await callback.message.edit_text(privacy_text(lang), reply_markup=misc_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "misc:terms")
async def open_terms(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    await callback.message.edit_text(terms_text(lang), reply_markup=misc_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "misc:reviews")
async def open_reviews(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    await callback.message.edit_text(reviews_text(lang), reply_markup=misc_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data.startswith("review:start:"))
async def start_review(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    order_id = int(callback.data.split(":")[-1])
    text = (
        f"{ce('news_pencil')} Rate your purchase from 1 to 5 stars."
        if lang == "en"
        else f"{ce('news_pencil')} Оцените покупку от 1 до 5 звезд."
    )
    await callback.message.answer(text, reply_markup=review_rating_keyboard(order_id, lang))
    await callback.answer()


@router.callback_query(F.data.startswith("review:rating:"))
async def choose_review_rating(callback: CallbackQuery, state: FSMContext) -> None:
    lang = await get_lang(callback.from_user.id)
    _, _, order_id, rating = callback.data.split(":")
    await state.set_state(ReviewState.waiting_for_comment)
    await state.update_data(review_order_id=int(order_id), review_rating=int(rating))
    text = (
        f"{ce('news_pencil')} Rating: <b>{rating} ⭐</b>\n\nSend a short comment about your purchase."
        if lang == "en"
        else f"{ce('news_pencil')} Оценка: <b>{rating} ⭐</b>\n\nНапишите короткий комментарий о покупке."
    )
    await callback.message.answer(text)
    await callback.answer()


@router.message(ReviewState.waiting_for_comment)
async def receive_review_comment(message: Message, state: FSMContext, bot: Bot) -> None:
    await ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    lang = await get_lang(message.from_user.id)
    data = await state.get_data()
    order_id = int(data.get("review_order_id") or 0)
    rating = int(data.get("review_rating") or 0)
    comment = (message.text or "").strip()

    if not comment:
        await message.answer("Send a text comment." if lang == "en" else "Отправьте текстовый комментарий.")
        return

    if len(comment) > 1000:
        await message.answer(
            "Comment is too long. Send up to 1000 characters."
            if lang == "en"
            else "Комментарий слишком длинный. Отправьте до 1000 символов."
        )
        return

    review = await create_review(message.from_user.id, order_id, rating, comment)
    if not review:
        await state.clear()
        text = (
            "Could not save the review. It may already exist for this order."
            if lang == "en"
            else "Не удалось сохранить отзыв. Возможно, по этому заказу отзыв уже оставлен."
        )
        await message.answer(text, reply_markup=start_keyboard(lang))
        return

    username = f"@{message.from_user.username}" if message.from_user.username else f"id:{message.from_user.id}"
    stars = "⭐" * rating
    channel_text = (
        f"{ce('news_pencil')} <b>Новый отзыв</b>\n\n"
        f"Товар: {html.escape(str(review['product_title']))}\n"
        f"Оценка: {stars}\n"
        f"Покупатель: {html.escape(username)}\n\n"
        f"{html.escape(comment)}"
    )

    if REVIEWS_CHANNEL_ID:
        try:
            await bot.send_message(REVIEWS_CHANNEL_ID, channel_text)
        except Exception:
            logging.exception("Could not send review to channel")
            if ADMIN_ID:
                try:
                    await bot.send_message(int(ADMIN_ID), "Не удалось отправить отзыв в канал. Проверьте REVIEWS_CHANNEL_ID и права бота.")
                except Exception:
                    logging.exception("Could not notify admin about review channel error")

    await state.clear()
    text = (
        f"{ce('ok')} Thank you. Your review has been saved."
        if lang == "en"
        else f"{ce('ok')} Спасибо. Ваш отзыв сохранен."
    )
    await message.answer(text, reply_markup=start_keyboard(lang))


@router.callback_query(F.data == "review:cancel")
async def cancel_review(callback: CallbackQuery, state: FSMContext) -> None:
    lang = await get_lang(callback.from_user.id)
    await state.clear()
    text = "Review cancelled." if lang == "en" else "Отзыв отменен."
    await callback.message.answer(text, reply_markup=start_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "menu:home")
async def open_home(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    lang = await get_lang(callback.from_user.id)
    await callback.message.edit_text(await home_text(lang, display_user_name(callback.from_user)), reply_markup=start_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "catalog:open")
async def open_catalog(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    title = f"{ce('news_catalog')} Catalog:" if lang == "en" else f"{ce('news_catalog')} Каталог:"
    await callback.message.edit_text(title, reply_markup=await catalog_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == f"product:{PRODUCT_CODE}")
async def open_product(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    await callback.message.edit_text(await product_text(lang), reply_markup=product_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "profile:open")
async def open_profile(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await ensure_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
    lang = await get_lang(callback.from_user.id)
    await callback.message.edit_text(await profile_text(callback.from_user.id, lang), reply_markup=profile_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "profile:topup")
async def profile_topup(callback: CallbackQuery, state: FSMContext) -> None:
    lang = await get_lang(callback.from_user.id)
    await state.set_state(TopUpState.waiting_for_amount)
    text = (
        "<b>Balance top-up</b>\n\n"
        "Send the amount in rubles. If Platega and Crypto Bot are configured, you will choose a payment method next."
        if lang == "en"
        else "<b>Пополнение баланса</b>\n\n"
        "Отправьте сумму в рублях. Если настроены Platega и Crypto Bot, дальше выберете способ оплаты."
    )
    await callback.message.edit_text(text, reply_markup=profile_back_keyboard(lang))
    await callback.answer()


@router.message(TopUpState.waiting_for_amount)
async def receive_topup_amount(message: Message, state: FSMContext) -> None:
    lang = await get_lang(message.from_user.id)
    raw_amount = (message.text or "").strip().replace(" ", "").replace(",", ".")

    if not raw_amount.replace(".", "", 1).isdigit():
        text = (
            "Please send only the amount in rubles, for example: <b>1500</b>"
            if lang == "en"
            else "Отправьте только сумму в рублях, например: <b>1500</b>"
        )
        await message.answer(text)
        return

    amount = int(float(raw_amount))
    if amount <= 0:
        text = "Amount must be greater than zero." if lang == "en" else "Сумма должна быть больше нуля."
        await message.answer(text)
        return

    await state.update_data(topup_amount=amount)
    text = (
        f"<b>Balance top-up</b>\n\n"
        f"Amount: <b>{amount} ₽</b>\n\n"
        "Choose a payment method:"
        if lang == "en"
        else f"<b>Пополнение баланса</b>\n\n"
        f"Сумма: <b>{amount} ₽</b>\n\n"
        "Выберите способ оплаты:"
    )
    await message.answer(text, reply_markup=topup_payment_keyboard(amount, lang))


@router.callback_query(F.data.startswith("topup:method:"))
async def topup_method_placeholder(callback: CallbackQuery, state: FSMContext) -> None:
    lang = await get_lang(callback.from_user.id)
    data = await state.get_data()
    amount = int(data.get("topup_amount", 0))
    method = callback.data.split(":")[-1]
    if method == "platega":
        if amount <= 0:
            await callback.message.answer(
                "Send the top-up amount again." if lang == "en" else "Отправьте сумму пополнения еще раз."
            )
            await callback.answer()
            return
        try:
            await send_platega_invoice(callback.message, callback.from_user.id, amount, "topup", lang)
            await state.clear()
        except Exception:
            logging.exception("Could not create Platega top-up invoice")
            text = (
                "Could not create Platega invoice. Please try again later."
                if lang == "en"
                else "Не удалось создать счет Platega. Попробуйте позже."
            )
            await callback.message.answer(text)
        await callback.answer()
        return

    if method == "cryptobot":
        if amount <= 0:
            await callback.message.answer(
                "Send the top-up amount again." if lang == "en" else "Отправьте сумму пополнения еще раз."
            )
            await callback.answer()
            return
        try:
            await send_cryptobot_invoice(
                callback.message,
                callback.from_user.id,
                amount,
                "topup",
                lang,
            )
            await state.clear()
        except Exception:
            logging.exception("Could not create Crypto Bot top-up invoice")
            text = (
                "Could not create Crypto Bot invoice. Please try again later."
                if lang == "en"
                else "Не удалось создать счет Crypto Bot. Попробуйте позже."
            )
            await callback.message.answer(text)
        await callback.answer()
        return

    names = {
        "platega": "Platega",
        "cryptobot": "Crypto Bot",
        "bep20": "BEP20 USDT",
    }
    method_name = names.get(method, "payment")
    text = (
        f"{ce('news_money')} <b>{method_name}</b>\n\n"
        f"Amount: <b>{amount} ₽</b>\n\n"
        "This payment API will be connected later."
        if lang == "en"
        else f"{ce('news_money')} <b>{method_name}</b>\n\n"
        f"Сумма: <b>{amount} ₽</b>\n\n"
        "API этого способа оплаты будет подключен позже."
    )
    await callback.message.edit_text(text, reply_markup=topup_payment_keyboard(amount, lang))
    await callback.answer()


@router.callback_query(F.data == "topup:cancel")
async def cancel_topup(callback: CallbackQuery, state: FSMContext) -> None:
    lang = await get_lang(callback.from_user.id)
    await state.clear()
    text = "Top-up cancelled." if lang == "en" else "Пополнение отменено."
    await callback.message.edit_text(text, reply_markup=profile_back_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data.startswith("platega:check:"))
async def check_platega_payment(callback: CallbackQuery, bot: Bot) -> None:
    lang = await get_lang(callback.from_user.id)
    payment_id = int(callback.data.split(":")[-1])
    payment = await get_platega_payment(payment_id)
    if not payment or payment["user_id"] != callback.from_user.id:
        await callback.answer("Payment not found." if lang == "en" else "Платеж не найден.", show_alert=True)
        return

    if payment["status"] == "CONFIRMED":
        text = (
            f"{ce('ok')} This payment has already been credited."
            if lang == "en"
            else f"{ce('ok')} Этот платеж уже был зачислен."
        )
        await callback.message.answer(text)
        await callback.answer()
        return

    try:
        transaction = await get_platega_transaction(str(payment["transaction_id"]))
    except Exception:
        logging.exception("Could not check Platega transaction")
        await callback.answer(
            "Could not check payment. Try again later." if lang == "en" else "Не удалось проверить оплату. Попробуйте позже.",
            show_alert=True,
        )
        return

    status = str(transaction.get("status", "")).upper()
    if status != "CONFIRMED":
        await callback.answer("Payment has not arrived yet." if lang == "en" else "Оплата еще не поступила.", show_alert=True)
        return

    username = await payment_username(callback.from_user.id)
    completed = await complete_platega_payment(payment_id, username, status)
    if not completed:
        await callback.answer("Payment not found." if lang == "en" else "Платеж не найден.", show_alert=True)
        return

    await notify_paid_payment(bot, completed, "Platega")
    await callback.answer()
    return

    text = (
        f"{ce('ok')} Balance topped up by <b>{int(completed['amount_rub'])} ₽</b>."
        if lang == "en"
        else f"{ce('ok')} Баланс пополнен на <b>{int(completed['amount_rub'])} ₽</b>."
    )
    await callback.message.answer(text, reply_markup=start_keyboard(lang))
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


@router.callback_query(F.data == "payment:cryptobot")
async def start_crypto_order(callback: CallbackQuery, state: FSMContext) -> None:
    lang = await get_lang(callback.from_user.id)
    await state.clear()
    await ensure_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
    product = await get_product_config(PRODUCT_CODE)
    price = int(product["price_rub"])
    contact = f"@{callback.from_user.username}" if callback.from_user.username else f"id:{callback.from_user.id}"
    try:
        await send_cryptobot_invoice(
            callback.message,
            callback.from_user.id,
            price,
            "order",
            lang,
            product_code=PRODUCT_CODE,
            product_title=product["title"],
            quantity=1,
            contact=contact,
        )
    except Exception:
        logging.exception("Could not create Crypto Bot order invoice")
        text = (
            "Could not create Crypto Bot invoice. Please try again later."
            if lang == "en"
            else "Не удалось создать счет Crypto Bot. Попробуйте позже."
        )
        await callback.message.answer(text, reply_markup=product_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data.startswith("payment:"))
async def payment_placeholder(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    method = callback.data.split(":", 1)[1]
    names = {
        "promo": "промокоды",
        "platega": "Platega",
        "cryptobot": "Crypto Bot",
        "bep20": "BEP20 USDT",
    }
    method_name = names.get(method, "оплата")
    if lang == "en":
        text = (
            f"{ce('spark')} <b>{method_name}</b>\n\n"
            "This payment option will be connected later. For now, use balance payment or contact support."
        )
    else:
        text = (
            f"{ce('spark')} <b>{method_name}</b>\n\n"
            "Этот способ оплаты будет подключен позже. Пока можно оплатить балансом или написать в поддержку."
        )
    await callback.message.edit_text(text, reply_markup=product_keyboard(lang))
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
            "Invite users with your link. For every 5 invited users who make at least one purchase, "
            "you receive 1 Gemini Link as a gift."
        )
    else:
        text = (
            "<b>👥 Реферальная система</b>\n\n"
            f"Ваш код: <code>{user['ref_code']}</code>\n"
            f"Ваша ссылка: {ref_link}\n\n"
            "Приглашайте пользователей по своей ссылке. За каждых 5 приглашенных, "
            "которые сделают хотя бы одну покупку, вы получаете 1 Gemini Link в подарок."
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
    await callback.message.answer(await home_text(lang, display_user_name(callback.from_user)), reply_markup=start_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data.in_({"buy:start", "bulk:start"}))
async def start_bulk_order(callback: CallbackQuery, state: FSMContext) -> None:
    lang = await get_lang(callback.from_user.id)
    await state.clear()
    await callback.message.answer(await quantity_text(lang), reply_markup=quantity_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data.startswith("buy:qty:"))
async def select_quantity(callback: CallbackQuery, state: FSMContext) -> None:
    lang = await get_lang(callback.from_user.id)
    quantity = int(callback.data.split(":")[-1])
    await show_payment_methods_for_quantity(callback.message, state, quantity, lang)
    await callback.answer()


@router.callback_query(F.data == "buy:custom")
async def ask_custom_quantity(callback: CallbackQuery, state: FSMContext) -> None:
    lang = await get_lang(callback.from_user.id)
    await state.set_state(BulkOrderState.waiting_for_quantity)
    text = (
        f"{ce('cart')} Send a number with how many items you want to buy."
        if lang == "en"
        else f"{ce('cart')} Отправьте числом, сколько штук хотите купить."
    )
    await callback.message.answer(text)
    await callback.answer()


@router.message(BulkOrderState.waiting_for_quantity)
async def receive_bulk_quantity(message: Message, state: FSMContext, bot: Bot) -> None:
    await ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    lang = await get_lang(message.from_user.id)
    raw_quantity = (message.text or "").strip()

    if not raw_quantity.isdigit():
        text = (
            "Send only a whole number, for example: <b>2</b>."
            if lang == "en"
            else "Отправьте только целое число, например: <b>2</b>."
        )
        await message.answer(text)
        return

    quantity = int(raw_quantity)
    await show_payment_methods_for_quantity(message, state, quantity, lang)


@router.callback_query(F.data.startswith("bulk:pay:"))
async def choose_bulk_payment(callback: CallbackQuery, state: FSMContext) -> None:
    lang = await get_lang(callback.from_user.id)
    data = await state.get_data()
    quantity = int(data.get("bulk_quantity") or 0)
    method = callback.data.split(":")[-1]

    if quantity <= 0:
        await state.set_state(BulkOrderState.waiting_for_quantity)
        text = "Send the quantity again." if lang == "en" else "Отправьте количество еще раз."
        await callback.message.answer(text)
        await callback.answer()
        return

    stock = await count_available_links()
    if stock and quantity > stock:
        await state.set_state(BulkOrderState.waiting_for_quantity)
        text = (
            f"Only <b>{stock}</b> pcs are available now. Send a smaller quantity."
            if lang == "en"
            else f"Сейчас в наличии только <b>{stock}</b> шт. Отправьте количество поменьше."
        )
        await callback.message.answer(text)
        await callback.answer()
        return

    if method != "balance":
        product = await get_product_config(PRODUCT_CODE)
        total = int(product["price_rub"]) * quantity
        if method in {"cryptobot", "platega"}:
            await ensure_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
            contact = f"@{callback.from_user.username}" if callback.from_user.username else f"id:{callback.from_user.id}"
            title = product["title"] if quantity == 1 else f"{product['title']} ×{quantity}"
            try:
                if method == "cryptobot":
                    await send_cryptobot_invoice(
                        callback.message,
                        callback.from_user.id,
                        total,
                        "bulk_order",
                        lang,
                        product_code=PRODUCT_CODE,
                        product_title=title,
                        quantity=quantity,
                        contact=contact,
                    )
                else:
                    await send_platega_invoice(
                        callback.message,
                        callback.from_user.id,
                        total,
                        "bulk_order",
                        lang,
                        product_code=PRODUCT_CODE,
                        product_title=title,
                        quantity=quantity,
                        contact=contact,
                    )
                await state.clear()
            except Exception:
                logging.exception("Could not create %s bulk invoice", method)
                text = (
                    "Could not create Crypto Bot invoice. Please try again later."
                    if lang == "en"
                    else "Не удалось создать счет Crypto Bot. Попробуйте позже."
                )
                await callback.message.answer(text, reply_markup=bulk_payment_keyboard(quantity, lang))
            await callback.answer()
            return

        method_names = {"platega": "Platega", "cryptobot": "Crypto Bot"}
        method_name = method_names.get(method, method)
        text = (
            f"{ce('news_money')} Payment via <b>{method_name}</b> will be connected later.\n\n"
            f"Quantity: <b>{quantity}</b>\n"
            f"Amount: <b>{total} ₽</b>"
            if lang == "en"
            else f"{ce('news_money')} Оплата через <b>{method_name}</b> будет подключена позже.\n\n"
            f"Количество: <b>{quantity}</b>\n"
            f"Сумма: <b>{total} ₽</b>"
        )
        await callback.message.answer(text, reply_markup=bulk_payment_keyboard(quantity, lang))
        await callback.answer()
        return

    user = await ensure_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
    product = await get_product_config(PRODUCT_CODE)
    total = int(product["price_rub"]) * quantity
    balance = int(user["balance"])
    if balance < total:
        missing = total - balance
        await state.update_data(bulk_quantity=quantity)
        await state.set_state(BulkOrderState.waiting_for_payment)
        text = (
            f"{ce('news_money')} Not enough balance to pay from balance.\n\n"
            f"Balance: <b>{balance} ₽</b>\n"
            f"Order amount: <b>{total} ₽</b>\n"
            f"Missing: <b>{missing} ₽</b>\n\n"
            "To buy the link now, choose <b>Platega</b> or <b>Crypto</b> below."
            if lang == "en"
            else f"{ce('news_money')} На балансе не хватает денег для оплаты балансом.\n\n"
            f"Баланс: <b>{balance} ₽</b>\n"
            f"Сумма заказа: <b>{total} ₽</b>\n"
            f"Не хватает: <b>{missing} ₽</b>\n\n"
            "Чтобы купить ссылку сейчас, выберите ниже <b>Platega</b> или <b>Crypto</b>."
        )
        await callback.message.answer(
            text,
            reply_markup=bulk_payment_keyboard(quantity, lang),
        )
        await callback.answer()
        return

    await state.update_data(bulk_payment_method=method)
    await state.set_state(BulkOrderState.waiting_for_contact)
    text = (
        f"{ce('support')} Send your Telegram username in this format: <b>@username</b>"
        if lang == "en"
        else f"{ce('support')} Напишите ваш Telegram юзернейм в таком формате: <b>@username</b>"
    )
    await callback.message.answer(text)
    await callback.answer()


@router.message(BulkOrderState.waiting_for_contact)
async def receive_bulk_contact(message: Message, state: FSMContext, bot: Bot) -> None:
    await ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    lang = await get_lang(message.from_user.id)
    product = await get_product_config(PRODUCT_CODE)
    data = await state.get_data()
    quantity = int(data.get("bulk_quantity") or 0)
    stock = await count_available_links()
    contact = (message.text or "").strip()

    if quantity <= 0:
        await state.set_state(BulkOrderState.waiting_for_quantity)
        text = "Send the quantity again." if lang == "en" else "Отправьте количество еще раз."
        await message.answer(text)
        return

    if not TELEGRAM_USERNAME_RE.fullmatch(contact):
        error_text = (
            f"{ce('support')} Please send only your Telegram username in this format: <b>@username</b>"
            if lang == "en"
            else f"{ce('support')} Пожалуйста, отправьте только ваш Telegram юзернейм в формате: <b>@username</b>"
        )
        await message.answer(error_text)
        return

    if stock and quantity > stock:
        await state.set_state(BulkOrderState.waiting_for_quantity)
        text = (
            f"Only <b>{stock}</b> pcs are available now. Send a smaller quantity."
            if lang == "en"
            else f"Сейчас в наличии только <b>{stock}</b> шт. Отправьте количество поменьше."
        )
        await message.answer(text)
        return

    username = f"@{message.from_user.username}" if message.from_user.username else "username не указан"
    total = int(product["price_rub"]) * quantity
    order_title = f"{product['title']} ×{quantity}"
    status = "Ожидает обработки" if stock >= quantity else "Резерв, нет в наличии"

    order = await create_balance_order(
        user_id=message.from_user.id,
        username=username,
        product_code=PRODUCT_CODE,
        product_title=order_title,
        price_rub=total,
        contact=contact,
        status=status,
    )
    if not order:
        user = await get_user(message.from_user.id)
        balance = int(user["balance"]) if user else 0
        missing = max(total - balance, 1)
        await state.set_state(TopUpState.waiting_for_amount)
        await state.update_data(topup_amount=missing)
        await message.answer(
            balance_topup_text(balance, total, lang),
            reply_markup=topup_payment_keyboard(missing, lang),
        )
        return

    admin_message = (
        f"{ce('cart')} <b>Новый заказ на несколько товаров</b>\n\n"
        f"Заказ: #{order['id']}\n"
        f"Товар: {product['title']}\n"
        f"Количество: {quantity}\n"
        f"Сумма: {total} ₽\n"
        f"Оплата: баланс\n"
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
            logging.exception("Could not send bulk order to admin")

    await state.clear()
    issued_links = await deliver_order_links(message, order["id"], message.from_user.id, quantity, lang)
    done_text = (
        f"{ce('ok')} Order for <b>{quantity}</b> items created. It is now visible in My purchases."
        if lang == "en"
        else f"{ce('ok')} Заказ на <b>{quantity}</b> шт. оформлен. Он появился в разделе «Мои покупки»."
    )
    if issued_links:
        done_text = (
            f"{ce('ok')} Order created and delivered. It is visible in My purchases."
            if lang == "en"
            else f"{ce('ok')} Заказ оформлен и выдан. Он появился в разделе «Мои покупки»."
        )
    await message.answer(done_text, reply_markup=start_keyboard(lang))


@router.callback_query(F.data == "bulk:cancel")
async def cancel_bulk_order(callback: CallbackQuery, state: FSMContext) -> None:
    lang = await get_lang(callback.from_user.id)
    await state.clear()
    text = "Bulk purchase cancelled." if lang == "en" else "Покупка нескольких товаров отменена."
    await callback.message.answer(text, reply_markup=product_keyboard(lang))
    await callback.answer()


@router.message(CryptoOrderState.waiting_for_contact)
async def receive_crypto_order_contact(message: Message, state: FSMContext) -> None:
    await ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    lang = await get_lang(message.from_user.id)
    contact = (message.text or "").strip()
    if not TELEGRAM_USERNAME_RE.fullmatch(contact):
        error_text = (
            f"{ce('support')} Please send only your Telegram username in this format: <b>@username</b>"
            if lang == "en"
            else f"{ce('support')} Пожалуйста, отправьте только ваш Telegram юзернейм в формате: <b>@username</b>"
        )
        await message.answer(error_text)
        return

    data = await state.get_data()
    quantity = int(data.get("crypto_quantity") or 1)
    purpose = data.get("crypto_purpose") or "order"
    product = await get_product_config(PRODUCT_CODE)
    total = int(product["price_rub"]) * quantity
    title = product["title"] if quantity == 1 else f"{product['title']} ×{quantity}"

    try:
        await send_cryptobot_invoice(
            message,
            message.from_user.id,
            total,
            purpose,
            lang,
            product_code=PRODUCT_CODE,
            product_title=title,
            quantity=quantity,
            contact=contact,
        )
        await state.clear()
    except Exception:
        logging.exception("Could not create Crypto Bot order invoice")
        text = (
            "Could not create Crypto Bot invoice. Please try again later."
            if lang == "en"
            else "Не удалось создать счет Crypto Bot. Попробуйте позже."
        )
        await message.answer(text, reply_markup=product_keyboard(lang))


@router.callback_query(F.data.startswith("cryptobot:check:"))
async def check_cryptobot_payment(callback: CallbackQuery, bot: Bot) -> None:
    lang = await get_lang(callback.from_user.id)
    payment_id = int(callback.data.split(":")[-1])
    payment = await get_crypto_payment(payment_id)
    if not payment or payment["user_id"] != callback.from_user.id:
        await callback.answer("Payment not found." if lang == "en" else "Платеж не найден.", show_alert=True)
        return

    if payment["status"] == "paid":
        if payment["purpose"] != "topup" and payment["order_id"]:
            quantity = int(payment["quantity"] or 1)
            issued_links = await deliver_order_links(
                callback.message,
                int(payment["order_id"]),
                callback.from_user.id,
                quantity,
                lang,
            )
            if issued_links:
                text = (
                    f"{ce('ok')} This payment was already credited. Links delivered now."
                    if lang == "en"
                    else f"{ce('ok')} Этот платеж уже был зачислен. Ссылки выданы сейчас."
                )
                await callback.message.answer(text, reply_markup=start_keyboard(lang))
                await callback.answer()
                return

        text = (
            f"{ce('ok')} This payment has already been credited."
            if lang == "en"
            else f"{ce('ok')} Этот платеж уже был зачислен."
        )
        await callback.message.answer(text)
        await callback.answer()
        return

    try:
        invoice = await get_cryptobot_invoice(int(payment["invoice_id"]))
    except Exception:
        logging.exception("Could not check Crypto Bot invoice")
        await callback.answer(
            "Could not check payment. Try again later." if lang == "en" else "Не удалось проверить оплату. Попробуйте позже.",
            show_alert=True,
        )
        return

    if not invoice or invoice.get("status") != "paid":
        await callback.answer("Payment has not arrived yet." if lang == "en" else "Оплата еще не поступила.", show_alert=True)
        return

    username = f"@{callback.from_user.username}" if callback.from_user.username else "username не указан"
    order_status = "Оплачен Crypto Bot, ожидает обработки"
    completed = await complete_crypto_payment(payment_id, username, order_status)
    if not completed:
        await callback.answer("Payment not found." if lang == "en" else "Платеж не найден.", show_alert=True)
        return

    if completed["purpose"] == "topup":
        text = (
            f"{ce('ok')} Balance topped up by <b>{int(completed['amount_rub'])} ₽</b>."
            if lang == "en"
            else f"{ce('ok')} Баланс пополнен на <b>{int(completed['amount_rub'])} ₽</b>."
        )
    else:
        quantity = int(completed["quantity"] or 1)
        issued_links = []
        if completed["order_id"]:
            issued_links = await deliver_order_links(
                callback.message,
                int(completed["order_id"]),
                callback.from_user.id,
                quantity,
                lang,
            )
        text = (
            f"{ce('ok')} Payment received. Order created and is visible in My purchases."
            if lang == "en"
            else f"{ce('ok')} Оплата получена. Заказ создан и появился в разделе «Мои покупки»."
        )
        if issued_links:
            text = (
                f"{ce('ok')} Payment received. Order created and delivered."
                if lang == "en"
                else f"{ce('ok')} Оплата получена. Заказ создан и выдан."
            )
        if ADMIN_ID:
            admin_message = (
                f"{ce('cart')} <b>Новый заказ Crypto Bot</b>\n\n"
                f"Товар: {completed['product_title']}\n"
                f"Выдано ссылок: {len(issued_links)}\n"
                f"Сумма: {int(completed['amount_rub'])} ₽\n"
                f"Оплата: Crypto Bot\n"
                f"Покупатель: {username}\n"
                f"ID: <code>{callback.from_user.id}</code>\n"
                f"Контакт: {completed['contact']}"
            )
            try:
                await bot.send_message(int(ADMIN_ID), admin_message)
            except ValueError:
                logging.exception("ADMIN_ID must be a number")
            except Exception:
                logging.exception("Could not send Crypto Bot order to admin")

    await callback.message.answer(text, reply_markup=start_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "order:start")
async def start_order(callback: CallbackQuery, state: FSMContext) -> None:
    lang = await get_lang(callback.from_user.id)
    user = await ensure_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
    product = await get_product_config(PRODUCT_CODE)
    price = int(product["price_rub"])
    balance = int(user["balance"])
    if balance < price:
        missing = price - balance
        await state.set_state(TopUpState.waiting_for_amount)
        await state.update_data(topup_amount=missing)
        await callback.message.answer(
            balance_topup_text(balance, price, lang),
            reply_markup=topup_payment_keyboard(missing, lang),
        )
        await callback.answer()
        return

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

    price = int(product["price_rub"])
    order = await create_balance_order(
        user_id=message.from_user.id,
        username=username,
        product_code=PRODUCT_CODE,
        product_title=product["title"],
        price_rub=price,
        contact=contact,
        status=status,
    )
    if not order:
        user = await get_user(message.from_user.id)
        balance = int(user["balance"]) if user else 0
        missing = max(price - balance, 1)
        await state.set_state(TopUpState.waiting_for_amount)
        await state.update_data(topup_amount=missing)
        await message.answer(
            balance_topup_text(balance, price, lang),
            reply_markup=topup_payment_keyboard(missing, lang),
        )
        return

    admin_message = (
        f"{ce('cart')} <b>Новый заказ</b>\n\n"
        f"Заказ: #{order['id']}\n"
        f"Товар: {product['title']}\n"
        f"Цена: {price} ₽\n"
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
    issued_links = await deliver_order_links(message, order["id"], message.from_user.id, 1, lang)
    done_text = (
        f"{ce('ok')} Order created. It is now visible in My purchases. The administrator will contact you."
        if lang == "en"
        else f"{ce('ok')} Заказ оформлен. Он появился в разделе «Мои покупки». Администратор свяжется с вами."
    )
    if issued_links:
        done_text = (
            f"{ce('ok')} Order created and delivered. It is now visible in My purchases."
            if lang == "en"
            else f"{ce('ok')} Заказ оформлен и выдан. Он появился в разделе «Мои покупки»."
        )
    await message.answer(done_text, reply_markup=start_keyboard(lang))


@router.message()
async def fallback(message: Message) -> None:
    lang = await get_lang(message.from_user.id)
    text = "Choose an action from the menu." if lang == "en" else "Выберите действие в меню."
    await message.answer(text, reply_markup=start_keyboard(lang))


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set. Add it to the .env file.")

    logging.basicConfig(level=logging.INFO)
    await ensure_schema()

    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Открыть магазин"),
        ]
    )

    dispatcher = Dispatcher()
    dispatcher.message.middleware(SubscriptionMiddleware())
    dispatcher.callback_query.middleware(SubscriptionMiddleware())
    dispatcher.include_router(router)

    asyncio.create_task(auto_payment_watcher(bot))
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
