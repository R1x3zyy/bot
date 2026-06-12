import asyncio
import html
import json
import logging
import os
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Awaitable, Callable

import aiohttp
from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    BufferedInputFile,
    CallbackQuery,
    ChatMemberUpdated,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
)
from dotenv import load_dotenv

from db import (
    add_links,
    add_user_balance,
    admin_stats,
    cancel_crypto_payment,
    cancel_platega_payment,
    complete_platega_payment,
    complete_crypto_payment,
    count_available_links,
    create_reseller_api_key,
    create_order,
    create_balance_order,
    create_crypto_payment,
    create_platega_payment,
    daily_business_stats,
    create_review,
    ensure_schema,
    ensure_user,
    get_bot_setting,
    get_crypto_payment,
    get_order,
    get_platega_payment,
    get_product_config,
    list_product_configs,
    get_transactions,
    get_user,
    get_user_by_username,
    get_user_orders,
    get_order_issued_links,
    issue_links_to_order,
    list_active_crypto_payments,
    list_pending_platega_payments,
    list_reserved_orders,
    list_users,
    record_channel_membership_event,
    record_bot_visit,
    set_bot_setting,
    update_user_language,
    update_purchase_cost,
    update_product_config,
    update_order_status,
)


load_dotenv()


BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
REVIEWS_CHANNEL_ID = os.getenv("REVIEWS_CHANNEL_ID")
REVIEWS_CHANNEL_URL = os.getenv("REVIEWS_CHANNEL_URL", "https://t.me/+97u-tZJLgE5jZjNi")
REQUIRED_CHANNEL_ID = os.getenv("REQUIRED_CHANNEL_ID", "@r1x3zyyshop")
REQUIRED_CHANNEL_URL = os.getenv("REQUIRED_CHANNEL_URL", "https://t.me/r1x3zyyshop")
CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN")
CRYPTOBOT_API_URL = os.getenv("CRYPTOBOT_API_URL", "https://pay.crypt.bot/api")
PLATEGA_MERCHANT_ID = os.getenv("PLATEGA_MERCHANT_ID")
PLATEGA_SECRET = os.getenv("PLATEGA_SECRET")
PLATEGA_API_URL = os.getenv("PLATEGA_API_URL", "https://app.platega.io")
PRODUCT_CODE = "gemini_link_18_month"
GPT_ACCOUNT_PRODUCT_CODE = "gpt_account_full_warranty"
GEMINI_ACCOUNT_PRODUCT_CODE = "gemini_account_12_month"
SUPERGROK_PRODUCT_CODE = "supergrok_1_month"
GROK_3D_PRODUCT_CODE = "grok_3d_full_warranty"
CLAUDE_MAX_X5_PRODUCT_CODE = "claude_max_x5_cdk"
CLAUDE_MAX_X20_PRODUCT_CODE = "claude_max_x20_cdk"
SUPPORT_ONLY_PRODUCT_CODES = {CLAUDE_MAX_X5_PRODUCT_CODE, CLAUDE_MAX_X20_PRODUCT_CODE}
LINK_WHOLESALE_MIN_QUANTITY = 10
LINK_WHOLESALE_UNIT_USD = Decimal("1.5")
GPT_WHOLESALE_MIN_QUANTITY = 10
GPT_WHOLESALE_UNIT_USD = Decimal("3.5")
GROK_WHOLESALE_MIN_QUANTITY = 5
GROK_WHOLESALE_UNIT_USD = Decimal("5.5")
WHOLESALE_TIERS = {
    PRODUCT_CODE: [(LINK_WHOLESALE_MIN_QUANTITY, LINK_WHOLESALE_UNIT_USD)],
    GPT_ACCOUNT_PRODUCT_CODE: [(GPT_WHOLESALE_MIN_QUANTITY, GPT_WHOLESALE_UNIT_USD)],
    SUPERGROK_PRODUCT_CODE: [(GROK_WHOLESALE_MIN_QUANTITY, GROK_WHOLESALE_UNIT_USD)],
}
HIDDEN_CATALOG_PRODUCT_CODES = {GEMINI_ACCOUNT_PRODUCT_CODE, GROK_3D_PRODUCT_CODE}
SUPPORT_USERNAME = "@AutoGeminiSupport"
SUPPORT_URL = "https://t.me/AutoGeminiSupport"
TELEGRAM_USERNAME_RE = re.compile(r"^@[A-Za-z0-9_]{5,32}$")
CUSTOM_EMOJI_RE = re.compile(r'<tg-emoji emoji-id="[^"]+">(.*?)</tg-emoji>')
PROFILE_BANNER_PATH = os.path.join(os.path.dirname(__file__), "assets", "profile_banner.png")
PRODUCT_ALIASES = {
    "link": PRODUCT_CODE,
    "links": PRODUCT_CODE,
    "geminilink": PRODUCT_CODE,
    "gemini_link": PRODUCT_CODE,
    "gpt": GPT_ACCOUNT_PRODUCT_CODE,
    "chatgpt": GPT_ACCOUNT_PRODUCT_CODE,
    "gptaccount": GPT_ACCOUNT_PRODUCT_CODE,
    "gemini12": GEMINI_ACCOUNT_PRODUCT_CODE,
    "gemini_account": GEMINI_ACCOUNT_PRODUCT_CODE,
    "geminiacc": GEMINI_ACCOUNT_PRODUCT_CODE,
    "grok": SUPERGROK_PRODUCT_CODE,
    "supergrok": SUPERGROK_PRODUCT_CODE,
    "super_grok": SUPERGROK_PRODUCT_CODE,
    "supergrok_account": SUPERGROK_PRODUCT_CODE,
    "grok3d": GROK_3D_PRODUCT_CODE,
    "grok_3d": GROK_3D_PRODUCT_CODE,
    "grok3": GROK_3D_PRODUCT_CODE,
    "grok_3d_full": GROK_3D_PRODUCT_CODE,
    "claude5": CLAUDE_MAX_X5_PRODUCT_CODE,
    "claude_x5": CLAUDE_MAX_X5_PRODUCT_CODE,
    "claudemax5": CLAUDE_MAX_X5_PRODUCT_CODE,
    "claude20": CLAUDE_MAX_X20_PRODUCT_CODE,
    "claude_x20": CLAUDE_MAX_X20_PRODUCT_CODE,
    "claudemax20": CLAUDE_MAX_X20_PRODUCT_CODE,
}
CE = {
    "gemini": ("5321197740800120767", "💠"),
    "shop": ("5229064374403998351", "🛍"),
    "planet": ("5332586662629227075", "🗂"),
    "link": ("5271604874419647061", "🔗"),
    "stock": ("5348149223223211884", "📦"),
    "cart": ("5319204558147188648", "🛒"),
    "card": ("5389078268689265131", "💳"),
    "support": ("5443038326535759644", "💬"),
    "fire": ("5424972470023104089", "🔥"),
    "bolt": ("5456140674028019486", "⚡️"),
    "ok": ("5206607081334906820", "✅"),
    "cross": ("5210952531676504517", "❌"),
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
    "news_pencil": ("5334544901428229844", "ℹ️"),
    "news_info": ("5332679880599418983", "ℹ️"),
    "app": ("5323379047315555501", "📱"),
    "grok": ("5319288443153445517", "✦"),
    "gpt": ("5310259124817134249", "🤖"),
    "claude": ("5321196473784773037", "✳️"),
}


def ce(name: str) -> str:
    emoji_id, fallback = CE[name]
    if not emoji_id:
        return fallback
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


def plain_custom_emoji(text: str) -> str:
    return CUSTOM_EMOJI_RE.sub(lambda match: match.group(1), text)


def plain_telegram_text(text: str) -> str:
    text = plain_custom_emoji(text)
    text = re.sub(r"</?(?:b|i|u|s|code|pre|blockquote)>", "", text)
    return html.unescape(text)


def format_price(product: dict) -> str:
    price_rub = int(product["price_rub"])
    price_usd = float(product["price_usd"])
    return f"{price_rub} ₽ / {price_usd:g} $"


def format_usd_price(product: dict) -> str:
    return f"{float(product['price_usd']):g} USD"


def product_description(product: dict, lang: str = "ru") -> str:
    description = str(product["description"])
    price_line = (
        f"{ce('news_money')} Price: {format_usd_price(product)}"
        if lang == "en"
        else f"{ce('news_money')} Цена: {format_usd_price(product)}"
    )
    return re.sub(
        r"(?m)^[^\n]*(?:Цена|Price):\s*\d+(?:[.,]\d+)?\s*(?:USD|\$).*$",
        price_line,
        description,
        count=1,
    )


def product_icon(product_code: str) -> str:
    if "claude" in product_code:
        return ce("claude")
    if "grok" in product_code:
        return ce("grok")
    if "gpt" in product_code:
        return ce("gpt")
    return ce("gemini")


def product_button_icon(product_code: str) -> str:
    if "claude" in product_code:
        return "✳️"
    if "grok" in product_code:
        return "✦"
    if "gpt" in product_code:
        return "🤖"
    return "💠"


def resolve_product_code(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    normalized = normalized.replace(" ", "_")
    return PRODUCT_ALIASES.get(normalized, normalized)


async def visible_catalog_products() -> list[dict]:
    products = await list_product_configs()
    return [product for product in products if product["code"] not in HIDDEN_CATALOG_PRODUCT_CODES]


async def get_reviews_channel_id() -> str:
    return await get_bot_setting("reviews_channel_id", REVIEWS_CHANNEL_ID or "")


def forwarded_chat_id(message: Message) -> str:
    source = message.reply_to_message or message
    forward_from_chat = getattr(source, "forward_from_chat", None)
    if forward_from_chat and getattr(forward_from_chat, "id", None):
        return str(forward_from_chat.id)

    forward_origin = getattr(source, "forward_origin", None)
    origin_chat = getattr(forward_origin, "chat", None)
    if origin_chat and getattr(origin_chat, "id", None):
        return str(origin_chat.id)

    return ""


def quantity_from_order_title(title: str) -> int:
    match = re.search(r"[×xX]\s*(\d+)", title)
    if match:
        return max(int(match.group(1)), 1)
    return 1


async def answer_with_banner(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    if os.path.exists(PROFILE_BANNER_PATH):
        try:
            await message.answer_photo(FSInputFile(PROFILE_BANNER_PATH), caption=text, reply_markup=reply_markup)
        except TelegramBadRequest as exc:
            error_text = str(exc)
            if "DOCUMENT_INVALID" in error_text:
                await message.answer_photo(
                    FSInputFile(PROFILE_BANNER_PATH),
                    caption=plain_custom_emoji(text),
                    reply_markup=reply_markup,
                )
                return
            if "ENTITY_TEXT_INVALID" in error_text:
                await message.answer_photo(
                    FSInputFile(PROFILE_BANNER_PATH),
                    caption=plain_custom_emoji(text),
                    reply_markup=reply_markup,
                )
                return
            if "DOCUMENT_INVALID" not in error_text:
                raise
        return

    await safe_answer(message, text, reply_markup=reply_markup)


async def safe_answer(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    try:
        await message.answer(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        error_text = str(exc)
        if "DOCUMENT_INVALID" in error_text:
            await message.answer(plain_custom_emoji(text), reply_markup=reply_markup)
            return
        if "ENTITY_TEXT_INVALID" in error_text:
            await message.answer(plain_telegram_text(text), reply_markup=reply_markup, parse_mode=None)
            return
        if "can't parse entities" in error_text:
            await message.answer(plain_telegram_text(text), reply_markup=reply_markup, parse_mode=None)
            return
        else:
            raise


async def safe_bot_send_message(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: ParseMode | str | None = None,
) -> None:
    kwargs: dict[str, Any] = {"reply_markup": reply_markup}
    if parse_mode is not None:
        kwargs["parse_mode"] = parse_mode
    try:
        await bot.send_message(chat_id, text, **kwargs)
    except TelegramBadRequest as exc:
        error_text = str(exc)
        if "DOCUMENT_INVALID" in error_text:
            await bot.send_message(chat_id, plain_custom_emoji(text), **kwargs)
            return
        if "ENTITY_TEXT_INVALID" in error_text or "can't parse entities" in error_text:
            kwargs["parse_mode"] = None
            await bot.send_message(chat_id, plain_telegram_text(text), **kwargs)
            return
        else:
            raise


async def edit_or_answer(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    if message.photo:
        await safe_answer(message, text, reply_markup=reply_markup)
        return

    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        try:
            await safe_answer(message, text, reply_markup=reply_markup)
        except TelegramBadRequest as exc:
            if "DOCUMENT_INVALID" not in str(exc):
                raise
            await safe_answer(message, plain_custom_emoji(text), reply_markup=reply_markup)


def format_usd(value: Decimal) -> str:
    return f"{value.normalize():f}"


def wholesale_tiers(product_code: str) -> list[tuple[int, Decimal]]:
    return sorted(WHOLESALE_TIERS.get(product_code, []), key=lambda tier: tier[0])


def wholesale_unit_usd(product_code: str, quantity: int, base_usd: Decimal) -> Decimal:
    unit_usd = base_usd
    for min_quantity, tier_unit_usd in wholesale_tiers(product_code):
        if quantity >= min_quantity:
            unit_usd = tier_unit_usd
    return unit_usd


def calculate_order_price(product: dict, quantity: int) -> dict[str, Decimal | int]:
    base_rub = Decimal(str(product["price_rub"]))
    base_usd = Decimal(str(product["price_usd"]))
    unit_usd = wholesale_unit_usd(str(product.get("code") or ""), quantity, base_usd)

    if base_usd > 0:
        unit_rub = (base_rub / base_usd * unit_usd).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    else:
        unit_rub = base_rub.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    return {
        "unit_rub": int(unit_rub),
        "unit_usd": unit_usd,
        "total_rub": int(unit_rub) * quantity,
    }


def wholesale_text(product: dict, lang: str = "ru") -> str:
    lines = []
    for min_quantity, _unit_usd in wholesale_tiers(str(product.get("code") or "")):
        tier_price = calculate_order_price(product, min_quantity)
        if lang == "en":
            lines.append(
                f"{ce('fire')} From <b>{min_quantity} pcs.</b>: "
                f"<b>{tier_price['unit_rub']} ₽ / {format_usd(tier_price['unit_usd'])}$</b> per item"
            )
        else:
            lines.append(
                f"{ce('fire')} Опт от <b>{min_quantity} шт.</b>: "
                f"<b>{tier_price['unit_rub']} ₽ / {format_usd(tier_price['unit_usd'])}$</b> за 1 шт."
            )
    if not lines:
        return ""
    title = "Wholesale price:" if lang == "en" else "Оптовая цена:"
    return f"{ce('news_money')} <b>{title}</b>\n" + "\n".join(lines) + "\n"


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
            raw_text = await response.text()

    try:
        data = json.loads(raw_text) if raw_text else {}
    except json.JSONDecodeError as exc:
        snippet = raw_text[:200].replace("\n", " ").replace("\r", " ")
        raise RuntimeError(
            f"CryptoBot API returned non-JSON response for {method}: "
            f"status={response.status}, body={snippet!r}"
        ) from exc

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


class PriceState(StatesGroup):
    waiting_for_price = State()


router = Router()


def is_admin(user_id: int) -> bool:
    return bool(ADMIN_ID and ADMIN_ID.isdigit() and int(ADMIN_ID) == user_id)


def status_value(status: object) -> str:
    return str(getattr(status, "value", status))


def is_required_channel(chat: object) -> bool:
    if not REQUIRED_CHANNEL_ID:
        return False
    required = REQUIRED_CHANNEL_ID.lower()
    username = (getattr(chat, "username", None) or "").lower()
    chat_id = str(getattr(chat, "id", ""))
    return required in {chat_id, f"@{username}"}


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
            try:
                await event.answer("Подпишитесь на канал, чтобы продолжить.", show_alert=True)
            except TelegramBadRequest:
                logging.exception("Could not answer old subscription callback")
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
            [InlineKeyboardButton(text="✏️ Reviews", url=REVIEWS_CHANNEL_URL)],
            [InlineKeyboardButton(text="⚙️ Other", callback_data="misc:open")],
            [InlineKeyboardButton(text="🌐 Language", callback_data="profile:language")],
        ]
    else:
        buttons = [
            [
                InlineKeyboardButton(text="🛍 Каталог", callback_data="catalog:open"),
                InlineKeyboardButton(text="👤 Профиль", callback_data="profile:open"),
            ],
            [InlineKeyboardButton(text="✏️ Отзывы", url=REVIEWS_CHANNEL_URL)],
            [InlineKeyboardButton(text="⚙️ Прочее", callback_data="misc:open")],
            [InlineKeyboardButton(text="🌐 Язык / Language", callback_data="profile:language")],
        ]

    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )


async def catalog_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    back = "⬅️ Back" if lang == "en" else "⬅️ Назад"
    item_suffix = "pcs" if lang == "en" else "шт."
    products = await visible_catalog_products()
    rows = []
    for product in products:
        stock = await count_available_links(product["code"])
        price = format_price(product)
        rows.append([
            InlineKeyboardButton(
                text=f"{product_button_icon(product['code'])} {product['title']} | {price} | {stock} {item_suffix}",
                callback_data=f"product:{product['code']}",
            )
        ])
    rows.append([InlineKeyboardButton(text=back, callback_data="menu:home")])
    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def product_keyboard(lang: str = "ru", product_code: str = PRODUCT_CODE) -> InlineKeyboardMarkup:
    if product_code in SUPPORT_ONLY_PRODUCT_CODES:
        if lang == "en":
            buttons = [
                [InlineKeyboardButton(text="💬 Contact support", url=SUPPORT_URL)],
                [InlineKeyboardButton(text="⬅️ Back to catalog", callback_data="catalog:open")],
                [InlineKeyboardButton(text="🏠 Main menu", callback_data="menu:home")],
            ]
        else:
            buttons = [
                [InlineKeyboardButton(text="💬 Написать в поддержку", url=SUPPORT_URL)],
                [InlineKeyboardButton(text="⬅️ Назад в каталог", callback_data="catalog:open")],
                [InlineKeyboardButton(text="🏠 В меню", callback_data="menu:home")],
            ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    if lang == "en":
        buttons = [
            [InlineKeyboardButton(text="🛒 Buy", callback_data=f"buy:start:{product_code}")],
            [InlineKeyboardButton(text="⬅️ Back to catalog", callback_data="catalog:open")],
            [InlineKeyboardButton(text="🏠 Main menu", callback_data="menu:home")],
        ]
    else:
        buttons = [
            [InlineKeyboardButton(text="🛒 Купить", callback_data=f"buy:start:{product_code}")],
            [InlineKeyboardButton(text="⬅️ Назад в каталог", callback_data="catalog:open")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu:home")],
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


def quantity_keyboard(lang: str = "ru", product_code: str = PRODUCT_CODE) -> InlineKeyboardMarkup:
    custom_text = "✍️ Custom quantity" if lang == "en" else "✍️ Своё количество"
    back_text = "⬅️ Product" if lang == "en" else "⬅️ Товар"
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
            [InlineKeyboardButton(text=back_text, callback_data=f"product:{product_code}")],
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


async def admin_price_products_keyboard() -> InlineKeyboardMarkup:
    products = await list_product_configs()
    buttons = [
        [
            InlineKeyboardButton(
                text=f"{product_button_icon(product['code'])} {product['title']} | {format_price(product)}",
                callback_data=f"admin:price:{product['code']}",
            )
        ]
        for product in products
    ]
    buttons.append([InlineKeyboardButton(text="Отмена", callback_data="admin:price:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def cryptobot_invoice_keyboard(payment_id: int, invoice_url: str, lang: str = "ru") -> InlineKeyboardMarkup:
    pay_text = "💵 Pay invoice" if lang == "en" else "💵 Оплатить счет"
    check_text = "✅ Check payment" if lang == "en" else "✅ Проверить оплату"
    cancel_text = "❌ Cancel payment" if lang == "en" else "❌ Отменить оплату"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=pay_text, url=invoice_url)],
            [InlineKeyboardButton(text=check_text, callback_data=f"cryptobot:check:{payment_id}")],
            [InlineKeyboardButton(text=cancel_text, callback_data=f"cryptobot:cancel:{payment_id}")],
        ]
    )


def platega_invoice_keyboard(payment_id: int, payment_url: str, lang: str = "ru") -> InlineKeyboardMarkup:
    pay_text = "💵 Pay Platega" if lang == "en" else "💵 Оплатить Platega"
    check_text = "✅ Check payment" if lang == "en" else "✅ Проверить оплату"
    cancel_text = "❌ Cancel payment" if lang == "en" else "❌ Отменить оплату"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=pay_text, url=payment_url)],
            [InlineKeyboardButton(text=check_text, callback_data=f"platega:check:{payment_id}")],
            [InlineKeyboardButton(text=cancel_text, callback_data=f"platega:cancel:{payment_id}")],
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
            [InlineKeyboardButton(text="💬 Поддержка", url=SUPPORT_URL)],
            [InlineKeyboardButton(text=home_text, callback_data="menu:home")],
        ]
    )


def misc_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    if lang == "en":
        support_text = "💬 Support"
        channel_text = "📣 Our channel"
        privacy_text = "🛡 Privacy policy"
        terms_text = "⚙️ User agreement"
        back_text = "🔙 Back"
    else:
        support_text = "💬 Тех поддержка"
        channel_text = "📣 Наш канал"
        privacy_text = "🛡 Политика конфид."
        terms_text = "⚙️ Польз. соглашение"
        back_text = "🔙 Назад"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=support_text, url=SUPPORT_URL)],
            [InlineKeyboardButton(text=channel_text, url="https://t.me/r1x3zyyshop")],
            [InlineKeyboardButton(text=privacy_text, callback_data="misc:privacy")],
            [InlineKeyboardButton(text=terms_text, callback_data="misc:terms")],
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
    products = await visible_catalog_products()
    product_lines = []
    total_stock = 0
    item_suffix = "pcs" if lang == "en" else "шт."
    for product in products:
        stock = await count_available_links(product["code"])
        total_stock += stock
        title = html.escape(str(product["title"]))
        product_lines.append(f"{product_icon(product['code'])} {title} | {format_price(product)} | {stock} {item_suffix}")
    greeting_name = f", {html.escape(user_name)}" if user_name else ""

    if lang == "en":
        return (
            f"{ce('spark')} <b>Welcome to the store{greeting_name}!</b>\n\n"
            f"{ce('gemini')} <b>Products:</b>\n"
            "<blockquote>"
            + "\n".join(product_lines) +
            "\n</blockquote>\n\n"
            f"{ce('fire')} <b>Benefits:</b>\n"
            "<blockquote>"
            f"{ce('news_bolt')} Fast delivery\n"
            f"{ce('news_money')} Easy payment\n"
            f"{ce('ok')} Warranty\n"
            f"{ce('support')} Fast support: {SUPPORT_USERNAME}"
            "\n</blockquote>\n\n"
            f"{ce('stock')} <b>In stock:</b> {total_stock}"
        )

    return (
        f"{ce('spark')} <b>Добро пожаловать в магазин{greeting_name}!</b>\n\n"
        f"{ce('shop')} <b>Товары:</b>\n"
        "<blockquote>"
        + "\n".join(product_lines) +
        "\n</blockquote>\n\n"
        f"{ce('fire')} <b>Плюсы:</b>\n"
        "<blockquote>"
        f"{ce('news_bolt')} Быстрая выдача\n"
        f"{ce('news_money')} Удобная оплата\n"
        f"{ce('ok')} Гарантия\n"
        f"{ce('support')} Быстрая поддержка: {SUPPORT_USERNAME}"
        "\n</blockquote>\n\n"
        f"{ce('stock')} <b>Сейчас в наличии:</b> {total_stock}"
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


async def product_text(lang: str = "ru", product_code: str = PRODUCT_CODE) -> str:
    product = await get_product_config(product_code)
    stock = await count_available_links(product_code)
    price = format_price(product)
    wholesale = wholesale_text(product, lang)
    if wholesale:
        price = f"{price}\n{wholesale}".rstrip()

    if product_code in SUPPORT_ONLY_PRODUCT_CODES:
        if lang == "en":
            return (
                f"{product_icon(product_code)} <b>{product['title']}</b>\n\n"
                f"{product_description(product, lang)}\n\n"
                f"{ce('news_money')} <b>Price:</b> {price}\n"
                f"{ce('support')} To order, contact support: {SUPPORT_USERNAME}"
            )

        return (
            f"{product_icon(product_code)} <b>{product['title']}</b>\n\n"
            f"{product_description(product, lang)}\n\n"
            f"{ce('news_money')} <b>Цена:</b> {price}\n"
            f"{ce('support')} Для заказа напишите в поддержку: {SUPPORT_USERNAME}"
        )

    if lang == "en":
        return (
            f"{product_icon(product_code)} <b>{product['title']}</b>\n\n"
            f"{product_description(product, lang)}\n\n"
            f"{ce('news_money')} <b>Price:</b> {price}\n"
            f"{ce('stock')} <b>Stock:</b> {stock}\n"
            f"{ce('news_bolt')} <b>Delivery:</b> after order confirmation.\n\n"
            "If the item is temporarily out of stock, your order can be reserved and processed after restock."
        )

    return (
        f"{product_icon(product_code)} <b>{product['title']}</b>\n\n"
        f"{product_description(product, lang)}\n\n"
        f"{ce('news_money')} <b>Цена:</b> {price}\n"
        f"{ce('stock')} <b>Количество:</b> {stock}\n"
        f"{ce('news_bolt')} <b>Выдача:</b> после подтверждения заказа.\n\n"
        "Если товар временно закончился, заказ можно зарезервировать и обработать после пополнения наличия."
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
    amount_usd: Decimal | None = None,
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
        amount_usd=amount_usd,
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
    amount_usd: Decimal | None = None,
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
        amount_usd=amount_usd,
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


def gpt_account_notice(lang: str = "ru") -> str:
    if lang == "en":
        return (
            f"\n\n{ce('news_shield')} <b>Recommendations after receiving the account:</b>\n"
            "• You may change the password and other account details at your discretion.\n"
            "• Do not use the account on more than 2 devices. 2 devices is the maximum.\n"
            "• Use a reliable proxy or a good VPN for stable access.\n"
            "• If you have any login issue, contact support first."
        )

    return (
        f"\n\n{ce('news_shield')} <b>Рекомендации после получения аккаунта:</b>\n"
        "• Вы можете менять пароль и другие данные аккаунта на свое усмотрение.\n"
        "• Не входите в аккаунт больше чем на 2 устройствах, 2 устройства — максимум.\n"
        "• Для стабильного входа используйте хороший прокси или хороший VPN.\n"
        "• Если возникла проблема со входом, сначала напишите в поддержку."
    )


def supergrok_account_notice(lang: str = "ru") -> str:
    if lang == "en":
        return (
            f"\n\n{ce('grok')} <b>SUPERGROK instructions:</b>\n"
            "Use the email and password exactly as provided. Do not change the email, password, or enable 2FA. "
            "If you have any login issue, contact support before making changes."
        )

    return (
        f"\n\n{ce('grok')} <b>Инструкция SUPERGROK:</b>\n"
        "Используйте email и пароль строго в том виде, в котором они выданы. Не меняйте email, пароль и не включайте 2FA. "
        "Если возникла проблема со входом, сначала напишите в поддержку и не вносите изменения самостоятельно."
    )


def delivery_text(links: list[dict], lang: str = "ru", product_code: str = "") -> str:
    if product_code == GPT_ACCOUNT_PRODUCT_CODE:
        notice = gpt_account_notice(lang)
    elif product_code == SUPERGROK_PRODUCT_CODE:
        notice = supergrok_account_notice(lang)
    else:
        notice = ""
    if len(links) == 1:
        url = html.escape(str(links[0]["url"]))
        return (
            f"{ce('ok')} <b>Your item</b>\n\n<code>{url}</code>{notice}"
            if lang == "en"
            else f"{ce('ok')} <b>Ваш товар</b>\n\n<code>{url}</code>{notice}"
        )

    lines = [f"{index}. <code>{html.escape(str(link['url']))}</code>" for index, link in enumerate(links, start=1)]
    return (
        f"{ce('ok')} <b>Your items</b>\n\n" + "\n".join(lines) + notice
        if lang == "en"
        else f"{ce('ok')} <b>Ваши товары</b>\n\n" + "\n".join(lines) + notice
    )


def delivery_text_chunks(links: list[dict], lang: str = "ru", product_code: str = "") -> list[str]:
    if len(delivery_text(links, lang, product_code)) <= 3500:
        return [delivery_text(links, lang, product_code)]

    if product_code == GPT_ACCOUNT_PRODUCT_CODE:
        notice = gpt_account_notice(lang)
    elif product_code == SUPERGROK_PRODUCT_CODE:
        notice = supergrok_account_notice(lang)
    else:
        notice = ""

    title = f"{ce('ok')} <b>Your items</b>" if lang == "en" else f"{ce('ok')} <b>Ваши товары</b>"
    chunks: list[str] = []
    current_lines: list[str] = []

    for index, link in enumerate(links, start=1):
        line = f"{index}. <code>{html.escape(str(link['url']))}</code>"
        candidate = f"{title}\n\n" + "\n".join(current_lines + [line])
        if current_lines and len(candidate) > 3500:
            chunks.append(f"{title}\n\n" + "\n".join(current_lines))
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        last = f"{title}\n\n" + "\n".join(current_lines)
        if notice and len(last + notice) <= 3500:
            last += notice
        else:
            if notice:
                chunks.append(last)
                last = notice.strip()
        chunks.append(last)

    return chunks


def delivery_file(order_id: int, links: list[dict]) -> BufferedInputFile:
    content = "\n".join(str(link["url"]) for link in links)
    filename = f"order_{order_id}_items.txt"
    return BufferedInputFile(content.encode("utf-8"), filename=filename)


async def send_with_retry(send_call: Callable[[], Awaitable[Any]], attempts: int = 3) -> Any:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return await send_call()
        except TelegramNetworkError as exc:
            last_error = exc
            await asyncio.sleep(2 + attempt)
    if last_error:
        raise last_error
    return None


def reserved_text(lang: str = "ru") -> str:
    return (
        f"{ce('stock')} The order is paid, but there are not enough links in stock. "
        "It is reserved and will be delivered after restock."
        if lang == "en"
        else f"{ce('stock')} Заказ оплачен, но сейчас не хватает ссылок в наличии. "
        "Он зарезервирован и будет выдан после пополнения."
    )


async def deliver_order_links(
    message: Message,
    order_id: int,
    user_id: int,
    quantity: int,
    lang: str,
    with_review: bool = True,
) -> list[dict]:
    links = await issue_links_to_order(order_id, user_id, quantity, "Выдан автоматически")
    if links is None:
        return []
    if links:
        product_code = str(links[0].get("product_code") or "")
        try:
            for text in delivery_text_chunks(links, lang, product_code):
                await send_with_retry(lambda text=text: safe_answer(message, text))
            caption = "Items as a file" if lang == "en" else "Товар файлом"
            await send_with_retry(lambda: message.answer_document(delivery_file(order_id, links), caption=caption))
        except Exception:
            await update_order_status(order_id, "Выдан, нужна повторная отправка")
            logging.exception("Could not send delivered order %s to user %s", order_id, user_id)
            raise
        if with_review:
            review_text = (
                f"{ce('news_pencil')} How was your purchase? You can leave a review."
                if lang == "en"
                else f"{ce('news_pencil')} Как прошла покупка? Можете оставить отзыв."
            )
            await message.answer(review_text, reply_markup=review_prompt_keyboard(order_id, lang))
    else:
        await message.answer(reserved_text(lang))
    return links


async def deliver_order_links_to_user(
    bot: Bot,
    chat_id: int,
    order_id: int,
    quantity: int,
    lang: str,
    with_review: bool = True,
) -> list[dict]:
    links = await issue_links_to_order(order_id, chat_id, quantity, "Выдан автоматически")
    if links is None:
        return []
    if links:
        product_code = str(links[0].get("product_code") or "")
        try:
            for text in delivery_text_chunks(links, lang, product_code):
                await send_with_retry(lambda text=text: safe_bot_send_message(bot, chat_id, text))
            caption = "Items as a file" if lang == "en" else "Товар файлом"
            await send_with_retry(lambda: bot.send_document(chat_id, delivery_file(order_id, links), caption=caption))
        except Exception:
            await update_order_status(order_id, "Выдан, нужна повторная отправка")
            logging.exception("Could not send delivered order %s to user %s", order_id, chat_id)
            if ADMIN_ID and ADMIN_ID.isdigit():
                try:
                    await safe_bot_send_message(
                        bot,
                        int(ADMIN_ID),
                        f"⚠️ Заказ <b>#{order_id}</b> выдан в базе, но Telegram не отправил товар пользователю <code>{chat_id}</code>.\n"
                        f"Повторить: <code>/resendorder {order_id}</code>",
                    )
                except Exception:
                    logging.exception("Could not notify admin about failed delivery")
            return []
        if with_review:
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
        await safe_bot_send_message(
            bot,
            int(payment["user_id"]),
            text,
            reply_markup=start_keyboard(lang),
            parse_mode=ParseMode.HTML,
        )
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
    await safe_bot_send_message(
        bot,
        int(payment["user_id"]),
        text,
        reply_markup=start_keyboard(lang),
        parse_mode=ParseMode.HTML,
    )

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
            await safe_bot_send_message(bot, int(ADMIN_ID), admin_message, parse_mode=ParseMode.HTML)
        except ValueError:
            logging.exception("ADMIN_ID must be a number")
        except Exception:
            logging.exception("Could not send paid order to admin")


async def process_reserved_orders(bot: Bot, product_code: str | None = None) -> int:
    processed = 0
    for order in await list_reserved_orders(product_code, 100):
        quantity = quantity_from_order_title(str(order["product_title"]))
        if await count_available_links(str(order["product_code"])) < quantity:
            continue

        lang = await get_lang(int(order["user_id"]))
        issued = await deliver_order_links_to_user(
            bot,
            int(order["user_id"]),
            int(order["id"]),
            quantity,
            lang,
        )
        if issued:
            processed += 1
            if ADMIN_ID and ADMIN_ID.isdigit():
                try:
                    await safe_bot_send_message(
                        bot,
                        int(ADMIN_ID),
                        f"{ce('ok')} Резерв <b>#{order['id']}</b> автоматически выдан после пополнения склада.\n"
                        f"Товар: <b>{html.escape(str(order['product_title']))}</b>\n"
                        f"Пользователь: <code>{order['user_id']}</code>",
                    )
                except Exception:
                    logging.exception("Could not notify admin about processed reserve %s", order["id"])
    return processed


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
            try:
                await process_reserved_orders(bot)
            except Exception:
                logging.exception("Could not process reserved orders")
        except Exception:
            logging.exception("Payment watcher failed")

        await asyncio.sleep(5)


async def quantity_text(lang: str = "ru", product_code: str = PRODUCT_CODE) -> str:
    product = await get_product_config(product_code)
    stock = await count_available_links(product_code)
    pricing = calculate_order_price(product, 1)
    wholesale = wholesale_text(product, lang)
    if lang == "en":
        return (
            f"🔢 <b>Choose quantity</b>\n\n"
            f"{product_icon(product_code)} Product: <b>{product['title']}</b>\n"
            f"{ce('news_money')} Price per item: <b>{pricing['unit_rub']} ₽ / {format_usd(pricing['unit_usd'])}$</b>\n"
            f"{wholesale}"
            f"{ce('stock')} In stock: <b>{stock} pcs.</b>\n\n"
            "Choose quantity below or press <b>Custom quantity</b>."
        )

    return (
        f"🔢 <b>Выберите количество</b>\n\n"
        f"{product_icon(product_code)} Товар: <b>{product['title']}</b>\n"
        f"{ce('news_money')} Цена за 1 шт.: <b>{pricing['unit_rub']} ₽ / {format_usd(pricing['unit_usd'])}$</b>\n"
        f"{wholesale}"
        f"{ce('stock')} В наличии: <b>{stock} шт.</b>\n\n"
        "Выберите количество ниже или нажмите <b>Своё количество</b>."
    )


async def process_balance_quantity_order(
    message: Message,
    state: FSMContext,
    bot: Bot,
    quantity: int,
    product_code: str = PRODUCT_CODE,
) -> None:
    await ensure_user(message.chat.id, message.chat.username, message.chat.first_name)
    lang = await get_lang(message.chat.id)
    product = await get_product_config(product_code)
    stock = await count_available_links(product_code)

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
        await message.answer(text, reply_markup=quantity_keyboard(lang, product_code))
        return

    user = await get_user(message.chat.id)
    balance = int(user["balance"]) if user else 0
    pricing = calculate_order_price(product, quantity)
    total = int(pricing["total_rub"])
    sale_usd = Decimal(pricing["unit_usd"]) * quantity
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
        product_code=product_code,
        product_title=order_title,
        price_rub=total,
        contact=contact,
        status=status,
        sale_usd=sale_usd,
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
    data = await state.get_data()
    product_code = data.get("bulk_product_code") or PRODUCT_CODE
    stock = await count_available_links(product_code)
    if quantity <= 0:
        text = "Quantity must be at least 1." if lang == "en" else "Количество должно быть от 1."
        await message.answer(text, reply_markup=quantity_keyboard(lang, product_code))
        return

    if stock and quantity > stock:
        text = (
            f"Only <b>{stock}</b> pcs are available now. Choose a smaller quantity."
            if lang == "en"
            else f"Сейчас в наличии только <b>{stock}</b> шт. Выберите количество поменьше."
        )
        await message.answer(text, reply_markup=quantity_keyboard(lang, product_code))
        return

    product = await get_product_config(product_code)
    pricing = calculate_order_price(product, quantity)
    total = int(pricing["total_rub"])
    await state.update_data(bulk_quantity=quantity, bulk_product_code=product_code)
    await state.set_state(BulkOrderState.waiting_for_payment)
    text = (
        f"{ce('news_money')} Choose how to pay for the order.\n\n"
        f"Quantity: <b>{quantity}</b>\n"
        f"Price per item: <b>{pricing['unit_rub']} ₽ / {format_usd(pricing['unit_usd'])}$</b>\n"
        f"Amount: <b>{total} ₽</b>"
        if lang == "en"
        else f"{ce('news_money')} Выберите способ оплаты заказа.\n\n"
        f"Количество: <b>{quantity}</b>\n"
        f"Цена за 1 шт.: <b>{pricing['unit_rub']} ₽ / {format_usd(pricing['unit_usd'])}$</b>\n"
        f"Сумма: <b>{total} ₽</b>"
    )
    await safe_answer(message, text, reply_markup=bulk_payment_keyboard(quantity, lang))


@router.message(CommandStart())
async def start(message: Message) -> None:
    user = await ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    lang = user["language"] if user["language"] in {"ru", "en"} else "ru"
    await answer_with_banner(
        message,
        await home_text(lang, display_user_name(message.from_user)),
        reply_markup=start_keyboard(lang),
    )


@router.chat_member()
async def track_required_channel_member(event: ChatMemberUpdated) -> None:
    if not is_required_channel(event.chat):
        return

    user = event.new_chat_member.user
    if user.is_bot:
        return

    old_status = status_value(event.old_chat_member.status)
    new_status = status_value(event.new_chat_member.status)
    if old_status == new_status:
        return

    inactive = {"left", "kicked"}
    event_type = ""
    if new_status in inactive and old_status not in inactive:
        event_type = "left"
    elif old_status in inactive and new_status not in inactive:
        event_type = "joined"

    if not event_type:
        return

    await record_channel_membership_event(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        event_type=event_type,
        old_status=old_status,
        new_status=new_status,
    )


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
    await answer_with_banner(
        callback.message,
        await home_text(lang, display_user_name(callback.from_user)),
        reply_markup=start_keyboard(lang),
    )
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


@router.message(Command("daystats"))
async def day_stats(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только администратору.")
        return

    data = await daily_business_stats()
    await message.answer(
        f"{ce('chart')} <b>Статистика за день</b>\n\n"
        f"Дата: <b>{data['date']}</b>\n"
        f"Заказов: <b>{data['orders_count']}</b>\n"
        f"Оборот: <b>{int(data['revenue_rub'])} ₽</b>\n"
        f"Выдано ссылок: <b>{data['issued_links']}</b>\n\n"
        f"Цена продажи: <b>{data['price_usd']}$</b>\n"
        f"Закуп за 1 ссылку: <b>{data['cost_per_link_usd']}$</b>\n"
        f"Оборот в $ по выданным: <b>{data['revenue_usd']}$</b>\n"
        f"Закуп всего: <b>{data['cost_usd']}$</b>\n"
        f"Прибыль: <b>{data['profit_usd']}$</b>"
    )


@router.message(Command("giveitem"))
async def give_item_command(message: Message, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только администратору.")
        return

    parts = (message.text or "").split()
    if len(parts) < 4:
        await message.answer(
            "Формат:\n"
            "<code>/giveitem user_id товар количество</code>\n"
            "<code>/giveitem @username товар количество</code>\n\n"
            "Товары: <code>link</code>, <code>gpt</code>, <code>gemini12</code>, <code>grok</code>, <code>grok3d</code>\n"
            "Пример: <code>/giveitem @username link 1</code>"
        )
        return

    try:
        quantity = int(parts[3])
    except ValueError:
        await message.answer("Количество должно быть числом.")
        return

    target = parts[1].strip()
    target_username = ""
    if target.startswith("@"):
        target_user = await get_user_by_username(target)
        if not target_user:
            await message.answer(
                "Пользователь не найден в базе бота.\n\n"
                "Он должен хотя бы один раз написать /start боту, после этого можно выдавать по @username."
            )
            return
        target_user_id = int(target_user["id"])
        target_username = f"@{target_user['username']}" if target_user["username"] else target
    else:
        try:
            target_user_id = int(target)
        except ValueError:
            await message.answer("Укажите пользователя как ID или @username.")
            return
        target_user = await get_user(target_user_id)
        if target_user and target_user["username"]:
            target_username = f"@{target_user['username']}"

    if quantity <= 0:
        await message.answer("Количество должно быть больше 0.")
        return

    product_code = resolve_product_code(parts[2])
    product = await get_product_config(product_code)
    if not product:
        await message.answer("Товар не найден. Используй: link, gpt, gemini12, grok или grok3d.")
        return

    stock = await count_available_links(product_code)
    if stock < quantity:
        await message.answer(f"Не хватает наличия. Сейчас доступно: <b>{stock}</b>.")
        return

    if target_username:
        await ensure_user(target_user_id, target_username.lstrip("@"), "")
    else:
        await ensure_user(target_user_id, "", "")
    order_title = product["title"] if quantity == 1 else f"{product['title']} ×{quantity}"
    pricing = calculate_order_price(product, quantity)
    sale_usd = Decimal(pricing["unit_usd"]) * quantity
    order = await create_order(
        user_id=target_user_id,
        username=target_username or "manual_admin_issue",
        product_code=product_code,
        product_title=order_title,
        price_rub=int(pricing["total_rub"]),
        contact=f"manual:{message.from_user.id}",
        status="Ожидает ручной выдачи",
        sale_usd=sale_usd,
    )

    target_lang = await get_lang(target_user_id)
    try:
        issued = await deliver_order_links_to_user(bot, target_user_id, order["id"], quantity, target_lang, with_review=False)
    except Exception:
        logging.exception("Could not manually deliver order %s to user %s", order["id"], target_user_id)
        await message.answer(
            f"Заказ #{order['id']} создан, но отправить пользователю не удалось. "
            "Скорее всего, пользователь еще не писал боту или заблокировал его."
        )
        return

    await message.answer(
        f"{ce('ok')} Выдано пользователю <code>{target_username or target_user_id}</code>.\n"
        f"Заказ: <b>#{order['id']}</b>\n"
        f"Товар: <b>{product['title']}</b>\n"
        f"Количество: <b>{len(issued)}</b>\n"
        f"Сумма в статистике: <b>{int(pricing['total_rub'])} ₽</b>"
    )


@router.message(Command("addbalance"))
async def add_balance_command(message: Message, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только администратору.")
        return

    parts = (message.text or "").split(maxsplit=3)
    if len(parts) < 3:
        await message.answer(
            "Формат:\n"
            "<code>/addbalance user_id сумма</code>\n"
            "<code>/addbalance @username сумма</code>\n\n"
            "Примеры:\n"
            "<code>/addbalance @username 500</code>\n"
            "<code>/addbalance 123456789 500</code>"
        )
        return

    target = parts[1].strip()
    try:
        amount_rub = int(parts[2])
    except ValueError:
        await message.answer("Сумма должна быть числом в рублях.")
        return

    if amount_rub <= 0:
        await message.answer("Сумма должна быть больше 0.")
        return

    target_label = target
    if target.startswith("@"):
        target_user = await get_user_by_username(target)
        if not target_user:
            await message.answer(
                "Пользователь не найден в базе бота.\n\n"
                "Он должен хотя бы один раз написать /start боту, после этого можно пополнять баланс по @username."
            )
            return
        target_user_id = int(target_user["id"])
        target_label = f"@{target_user['username']}" if target_user["username"] else str(target_user_id)
    else:
        try:
            target_user_id = int(target)
        except ValueError:
            await message.answer("Укажите пользователя как ID или @username.")
            return
        target_user = await get_user(target_user_id)
        if not target_user:
            await message.answer(
                "Пользователь не найден в базе бота.\n\n"
                "Он должен хотя бы один раз написать /start боту."
            )
            return
        if target_user["username"]:
            target_label = f"@{target_user['username']}"

    note = parts[3].strip() if len(parts) >= 4 else ""
    description = f"Admin top-up by {message.from_user.id}"
    if note:
        description = f"{description}: {note[:200]}"

    await add_user_balance(target_user_id, amount_rub, description)
    updated_user = await get_user(target_user_id)
    new_balance = int(updated_user["balance"]) if updated_user else 0

    await message.answer(
        f"{ce('ok')} Баланс пополнен.\n\n"
        f"Пользователь: <code>{html.escape(str(target_label))}</code>\n"
        f"Сумма: <b>{amount_rub} ₽</b>\n"
        f"Новый баланс: <b>{new_balance} ₽</b>"
    )

    try:
        await safe_bot_send_message(
            bot,
            target_user_id,
            f"{ce('news_money')} <b>Баланс пополнен</b>\n\n"
            f"Сумма: <b>{amount_rub} ₽</b>\n"
            f"Ваш баланс: <b>{new_balance} ₽</b>",
        )
    except Exception:
        logging.exception("Could not notify user %s about admin balance top-up", target_user_id)


@router.message(Command("removebalance"))
async def remove_balance_command(message: Message, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только администратору.")
        return

    parts = (message.text or "").split(maxsplit=3)
    if len(parts) < 3:
        await message.answer(
            "Формат:\n"
            "<code>/removebalance user_id сумма</code>\n"
            "<code>/removebalance @username сумма</code>\n\n"
            "Примеры:\n"
            "<code>/removebalance @username 500</code>\n"
            "<code>/removebalance 123456789 500</code>"
        )
        return

    target = parts[1].strip()
    try:
        amount_rub = int(parts[2])
    except ValueError:
        await message.answer("Сумма должна быть числом в рублях.")
        return

    if amount_rub <= 0:
        await message.answer("Сумма должна быть больше 0.")
        return

    target_label = target
    if target.startswith("@"):
        target_user = await get_user_by_username(target)
        if not target_user:
            await message.answer(
                "Пользователь не найден в базе бота.\n\n"
                "Он должен хотя бы один раз написать /start боту, после этого можно списывать баланс по @username."
            )
            return
        target_user_id = int(target_user["id"])
        target_label = f"@{target_user['username']}" if target_user["username"] else str(target_user_id)
    else:
        try:
            target_user_id = int(target)
        except ValueError:
            await message.answer("Укажите пользователя как ID или @username.")
            return
        target_user = await get_user(target_user_id)
        if not target_user:
            await message.answer(
                "Пользователь не найден в базе бота.\n\n"
                "Он должен хотя бы один раз написать /start боту."
            )
            return
        if target_user["username"]:
            target_label = f"@{target_user['username']}"

    current_balance = int(target_user["balance"])
    if amount_rub > current_balance:
        await message.answer(
            f"Нельзя списать больше текущего баланса.\n\n"
            f"Пользователь: <code>{html.escape(str(target_label))}</code>\n"
            f"Баланс сейчас: <b>{current_balance} ₽</b>\n"
            f"Вы пытаетесь списать: <b>{amount_rub} ₽</b>"
        )
        return

    note = parts[3].strip() if len(parts) >= 4 else ""
    description = f"Admin balance withdrawal by {message.from_user.id}"
    if note:
        description = f"{description}: {note[:200]}"

    await add_user_balance(target_user_id, -amount_rub, description)
    updated_user = await get_user(target_user_id)
    new_balance = int(updated_user["balance"]) if updated_user else 0

    await message.answer(
        f"{ce('ok')} Баланс списан.\n\n"
        f"Пользователь: <code>{html.escape(str(target_label))}</code>\n"
        f"Сумма: <b>{amount_rub} ₽</b>\n"
        f"Новый баланс: <b>{new_balance} ₽</b>"
    )

    try:
        await safe_bot_send_message(
            bot,
            target_user_id,
            f"{ce('news_money')} <b>Баланс изменен</b>\n\n"
            f"Списано: <b>{amount_rub} ₽</b>\n"
            f"Ваш баланс: <b>{new_balance} ₽</b>",
        )
    except Exception:
        logging.exception("Could not notify user %s about admin balance withdrawal", target_user_id)


@router.message(Command("createapikey"))
async def create_api_key_command(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только администратору.")
        return

    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 2:
        await message.answer(
            "Формат:\n"
            "<code>/createapikey user_id</code>\n"
            "<code>/createapikey @username</code>\n\n"
            "Пользователь должен хотя бы один раз написать /start боту."
        )
        return

    target = parts[1].strip()
    if target.startswith("@"):
        target_user = await get_user_by_username(target)
        if not target_user:
            await message.answer("Пользователь не найден. Он должен хотя бы один раз написать /start боту.")
            return
    else:
        try:
            target_user = await get_user(int(target))
        except ValueError:
            await message.answer("Укажите пользователя как ID или @username.")
            return
        if not target_user:
            await message.answer("Пользователь не найден. Он должен хотя бы один раз написать /start боту.")
            return

    label = f"@{target_user['username']}" if target_user["username"] else str(target_user["id"])
    key = await create_reseller_api_key(int(target_user["id"]), f"telegram:{label}")
    await message.answer(
        f"{ce('ok')} API-ключ создан для <code>{html.escape(label)}</code>.\n\n"
        "Покажите ключ покупателю только один раз:\n"
        f"<code>{html.escape(key['api_key'])}</code>\n\n"
        "Этим ключом его бот сможет покупать товары с баланса этого пользователя через reseller API."
    )


@router.message(Command("takeitem"))
async def take_item_command(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только администратору.")
        return

    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer(
            "Формат:\n"
            "<code>/takeitem товар количество</code>\n\n"
            "Товары: <code>link</code>, <code>gpt</code>, <code>gemini12</code>, <code>grok</code>, <code>grok3d</code>\n"
            "Пример: <code>/takeitem link 1</code>"
        )
        return

    product_code = resolve_product_code(parts[1])
    quantity = 1
    if len(parts) >= 3:
        try:
            quantity = int(parts[2])
        except ValueError:
            await message.answer("Количество должно быть числом.")
            return

    if quantity <= 0:
        await message.answer("Количество должно быть больше 0.")
        return

    product = await get_product_config(product_code)
    if not product:
        await message.answer("Товар не найден. Используй: link, gpt, gemini12, grok или grok3d.")
        return

    stock = await count_available_links(product_code)
    if stock < quantity:
        await message.answer(f"Не хватает наличия. Сейчас доступно: <b>{stock}</b>.")
        return

    await ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    username = f"@{message.from_user.username}" if message.from_user.username else "admin"
    order_title = product["title"] if quantity == 1 else f"{product['title']} ×{quantity}"
    order = await create_order(
        user_id=message.from_user.id,
        username=username,
        product_code=product_code,
        product_title=order_title,
        price_rub=0,
        contact=f"admin_take:{message.from_user.id}",
        status="Админ забрал товар",
    )

    lang = await get_lang(message.from_user.id)
    issued = await deliver_order_links(message, order["id"], message.from_user.id, quantity, lang, with_review=False)
    await message.answer(
        f"{ce('ok')} Забрал из наличия: <b>{len(issued)}</b>\n"
        f"Товар: <b>{product['title']}</b>\n"
        f"Заказ: <b>#{order['id']}</b>"
    )


@router.message(F.text.regexp(r"(?i)^выдать\s+снова\s+\d+"))
@router.message(F.text.regexp(r"(?i)^повторно\s+\d+"))
@router.message(Command("resendorder", "resend"))
async def resend_order_command(message: Message, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        await safe_answer(message, "Эта команда доступна только администратору.")
        return

    match = re.search(r"\d+", message.text or "")
    if not match:
        await safe_answer(
            message,
            "Формат:\n"
            "<code>/resendorder order_id</code>\n\n"
            "Примеры:\n"
            "<code>/resendorder 126</code>\n"
            "<code>/resend 126</code>\n"
            "<code>выдать снова 126</code>"
        )
        return

    order_id = int(match.group(0))
    order = await get_order(order_id)
    if not order:
        await safe_answer(message, "Заказ не найден.")
        return

    quantity = quantity_from_order_title(str(order["product_title"]))
    links = await get_order_issued_links(order_id, quantity)
    if not links:
        await safe_answer(message, "У этого заказа нет уже выданного товара для повторной отправки.")
        return

    lang = await get_lang(int(order["user_id"]))
    try:
        for text in delivery_text_chunks(links, lang, str(order["product_code"])):
            await send_with_retry(lambda text=text: safe_bot_send_message(bot, int(order["user_id"]), text))
        caption = "Items as a file" if lang == "en" else "Товар файлом"
        await send_with_retry(lambda: bot.send_document(int(order["user_id"]), delivery_file(order_id, links), caption=caption))
    except Exception as exc:
        await update_order_status(order_id, "Выдан, нужна повторная отправка")
        logging.exception("Could not resend order %s to user %s", order_id, order["user_id"])
        await safe_answer(
            message,
            f"Не удалось повторно отправить заказ <b>#{order_id}</b> пользователю <code>{order['user_id']}</code>.\n"
            f"Ошибка: <code>{html.escape(str(exc))[:500]}</code>"
        )
        return

    await update_order_status(order_id, "Выдан автоматически")
    await safe_answer(
        message,
        f"{ce('ok')} Заказ <b>#{order_id}</b> повторно отправлен пользователю <code>{order['user_id']}</code>.\n"
        f"Позиций: <b>{len(links)}</b>"
    )


@router.message(Command("setreviews"))
async def set_reviews_channel_command(message: Message, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        await safe_answer(message, "Эта команда доступна только администратору.")
        return

    args = (message.text or "").split(maxsplit=1)
    channel_id = args[1].strip() if len(args) > 1 else forwarded_chat_id(message)

    if channel_id.startswith("https://t.me/+") or channel_id.startswith("http://t.me/+"):
        await safe_answer(
            message,
            "По invite-ссылке приватный канал привязать нельзя.\n\n"
            "Сделайте так:\n"
            "1. Добавьте бота админом в канал.\n"
            "2. Опубликуйте любой пост в канале.\n"
            "3. Перешлите этот пост мне в личку и ответьте на него командой <code>/setreviews</code>.\n\n"
            "Или пришлите числовой ID канала вида <code>-100...</code>."
        )
        return

    if not channel_id:
        await safe_answer(
            message,
            "Формат:\n"
            "<code>/setreviews @channel_username</code>\n"
            "<code>/setreviews -1001234567890</code>\n\n"
            "Для приватного канала: добавьте бота админом, перешлите пост из канала и ответьте на него командой <code>/setreviews</code>."
        )
        return

    chat_id: int | str = int(channel_id) if re.fullmatch(r"-?\d+", channel_id) else channel_id
    try:
        chat = await bot.get_chat(chat_id)
        await bot.send_message(chat_id, f"{ce('ok')} Канал отзывов подключен.")
    except Exception as exc:
        logging.exception("Could not connect reviews channel %s", channel_id)
        await safe_answer(
            message,
            "Не удалось подключить канал отзывов.\n\n"
            "Проверьте, что бот добавлен в канал администратором и у него есть право публиковать сообщения.\n"
            f"Ошибка: <code>{html.escape(str(exc))[:500]}</code>"
        )
        return

    saved = await set_bot_setting("reviews_channel_id", str(chat.id))
    title = html.escape(getattr(chat, "title", "") or str(saved))
    await safe_answer(
        message,
        f"{ce('ok')} Канал отзывов привязан: <b>{title}</b>\n"
        f"ID: <code>{saved}</code>"
    )


@router.message(Command("setprice"))
async def set_price_command(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только администратору.")
        return

    await state.clear()
    await message.answer(
        "Выберите товар, у которого нужно поменять цену:",
        reply_markup=await admin_price_products_keyboard(),
    )


@router.callback_query(F.data == "admin:price:cancel")
async def cancel_set_price(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Недоступно", show_alert=True)
        return

    await state.clear()
    await callback.message.answer("Изменение цены отменено.")
    await callback.answer()


@router.callback_query(F.data.startswith("admin:price:"))
async def choose_product_price(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Недоступно", show_alert=True)
        return

    product_code = callback.data.split(":", 2)[2]
    product = await get_product_config(product_code)
    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return

    await state.set_state(PriceState.waiting_for_price)
    await state.update_data(price_product_code=product_code)
    await callback.message.answer(
        f"Товар: <b>{product['title']}</b>\n"
        f"Сейчас: <b>{format_price(product)}</b>\n\n"
        "Отправьте новую цену в формате:\n"
        "<code>116 1.6</code>\n\n"
        "Где первое число — цена в рублях, второе — цена в долларах."
    )
    await callback.answer()


@router.message(PriceState.waiting_for_price)
async def receive_product_price(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        await message.answer("Эта команда доступна только администратору.")
        return

    data = await state.get_data()
    product_code = data.get("price_product_code")
    product = await get_product_config(product_code)
    if not product:
        await state.clear()
        await message.answer("Товар не найден. Запустите /setprice заново.")
        return

    raw = (message.text or "").strip().replace(",", ".")
    parts = [part for part in re.split(r"[\s/|;]+", raw) if part]
    if len(parts) != 2:
        await message.answer(
            "Нужно отправить две цены: рубли и доллары.\n"
            "Пример: <code>116 1.6</code>"
        )
        return

    try:
        price_rub = Decimal(parts[0]).quantize(Decimal("0.01"))
        price_usd = Decimal(parts[1]).quantize(Decimal("0.01"))
    except Exception:
        await message.answer("Не получилось прочитать цену. Пример: <code>116 1.6</code>")
        return

    if price_rub <= 0 or price_usd <= 0:
        await message.answer("Цена должна быть больше нуля.")
        return

    updated = await update_product_config(
        code=product["code"],
        title=product["title"],
        price_rub=price_rub,
        price_usd=price_usd,
        description=product["description"],
    )
    await state.clear()
    await message.answer(
        f"{ce('ok')} Цена обновлена.\n\n"
        f"Товар: <b>{updated['title']}</b>\n"
        f"Новая цена: <b>{format_price(updated)}</b>"
    )


@router.message(Command("setcost"))
async def set_purchase_cost_command(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только администратору.")
        return

    parts = (message.text or "").strip().replace(",", ".").split()
    if len(parts) < 3:
        await message.answer(
            "Формат:\n"
            "<code>/setcost товар закуп_в_$</code>\n\n"
            "Товары: <code>link</code>, <code>gpt</code>, <code>gemini12</code>, <code>grok</code>, <code>grok3d</code>\n"
            "Пример: <code>/setcost gpt 2</code>"
        )
        return

    product_code = resolve_product_code(parts[1])
    product = await get_product_config(product_code)
    if not product:
        await message.answer("Товар не найден. Используй: link, gpt, gemini12, grok или grok3d.")
        return

    try:
        cost_usd = Decimal(parts[2]).quantize(Decimal("0.01"))
    except Exception:
        await message.answer("Закупочная цена должна быть числом. Пример: <code>/setcost gpt 2</code>")
        return

    if cost_usd <= 0:
        await message.answer("Закупочная цена должна быть больше 0.")
        return

    result = await update_purchase_cost(product_code, cost_usd, update_available=True)
    await message.answer(
        f"{ce('ok')} Закупочная цена обновлена.\n\n"
        f"Товар: <b>{product['title']}</b>\n"
        f"Новая себестоимость: <b>{result['cost_usd']}$</b>\n"
        f"Обновлено невыданных позиций: <b>{result['updated_available']}</b>\n\n"
        "Уже выданные заказы не изменялись, чтобы старая статистика не ломалась."
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
        await state.update_data(add_product_code=PRODUCT_CODE, add_item_name="ссылок")
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

    added = await add_links(links, PRODUCT_CODE)
    processed = await process_reserved_orders(message.bot, PRODUCT_CODE) if added else 0
    await message.answer(
        f"Добавлено ссылок: <b>{added}</b>\n"
        f"Теперь в наличии: <b>{await count_available_links(PRODUCT_CODE)}</b>\n"
        f"Выдано резервов: <b>{processed}</b>"
    )


async def add_accounts_command(
    message: Message,
    state: FSMContext,
    product_code: str,
    item_name: str,
    example: str,
) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Добавлять аккаунты может только администратор. Узнать ID: /myid")
        return

    raw_text = message.text or ""
    accounts = [line.strip() for line in raw_text.splitlines()[1:] if line.strip()]
    if not accounts:
        await state.set_state(AdminState.waiting_for_links)
        await state.update_data(add_product_code=product_code, add_item_name=item_name)
        await message.answer(
            f"Отправьте {item_name} следующим сообщением или сразу после команды:\n\n"
            f"{message.text.split()[0]}\n"
            f"{example}\n"
            f"{example.replace('1@', '2@')}"
        )
        return

    added = await add_links(accounts, product_code)
    processed = await process_reserved_orders(message.bot, product_code) if added else 0
    await message.answer(
        f"Добавлено {item_name}: <b>{added}</b>\n"
        f"Теперь в наличии: <b>{await count_available_links(product_code)}</b>\n"
        f"Выдано резервов: <b>{processed}</b>"
    )


@router.message(Command("addgptaccounts"))
async def add_gpt_accounts_command(message: Message, state: FSMContext) -> None:
    await add_accounts_command(
        message,
        state,
        GPT_ACCOUNT_PRODUCT_CODE,
        "GPT-аккаунтов",
        "mail1@hotmail.com:password",
    )


@router.message(Command("addgeminiaccounts"))
async def add_gemini_accounts_command(message: Message, state: FSMContext) -> None:
    await add_accounts_command(
        message,
        state,
        GEMINI_ACCOUNT_PRODUCT_CODE,
        "Gemini-аккаунтов",
        "mail1@gmail.com:password",
    )


@router.message(Command("addgrokaccounts"))
async def add_grok_accounts_command(message: Message, state: FSMContext) -> None:
    await add_accounts_command(
        message,
        state,
        SUPERGROK_PRODUCT_CODE,
        "SUPERGROK-аккаунтов",
        "mail1@hotmail.com:password",
    )


@router.message(Command("addgrok3daccounts"))
async def add_grok_3d_accounts_command(message: Message, state: FSMContext) -> None:
    await add_accounts_command(
        message,
        state,
        GROK_3D_PRODUCT_CODE,
        "Grok 3d-аккаунтов",
        "mail1@hotmail.com:mail_password:grok_password",
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

    data = await state.get_data()
    product_code = data.get("add_product_code") or PRODUCT_CODE
    item_name = data.get("add_item_name") or "позиций"
    items = (message.text or "").splitlines()
    added = await add_links(items, product_code)
    processed = await process_reserved_orders(message.bot, product_code) if added else 0
    await state.clear()

    if not added:
        await message.answer(
            "Я не нашел товарных позиций в сообщении. Отправьте каждую позицию с новой строки:\n\n"
            "mail@gmail.com:password\n"
            "https://example.com/link"
        )
        return

    await message.answer(
        f"Добавлено {item_name}: <b>{added}</b>\n"
        f"Теперь в наличии: <b>{await count_available_links(product_code)}</b>\n"
        f"Выдано резервов: <b>{processed}</b>"
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
    await answer_with_banner(message, await profile_text(message.from_user.id, lang), reply_markup=profile_keyboard(lang))


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
    await edit_or_answer(callback.message, help_text(lang), reply_markup=help_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "support:open")
async def open_support(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    await edit_or_answer(callback.message, support_text(lang), reply_markup=help_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "misc:open")
async def open_misc(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    await edit_or_answer(callback.message, misc_text(lang), reply_markup=misc_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "misc:faq")
async def open_faq(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    await edit_or_answer(callback.message, faq_text(lang), reply_markup=misc_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "misc:privacy")
async def open_privacy(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    await edit_or_answer(callback.message, privacy_text(lang), reply_markup=misc_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "misc:terms")
async def open_terms(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    await edit_or_answer(callback.message, terms_text(lang), reply_markup=misc_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "misc:reviews")
async def open_reviews(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    await edit_or_answer(callback.message, reviews_text(lang), reply_markup=misc_keyboard(lang))
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

    reviews_channel_id = await get_reviews_channel_id()
    if reviews_channel_id:
        try:
            chat_id: int | str = int(reviews_channel_id) if re.fullmatch(r"-?\d+", reviews_channel_id) else reviews_channel_id
            await bot.send_message(chat_id, channel_text)
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
    await answer_with_banner(
        callback.message,
        await home_text(lang, display_user_name(callback.from_user)),
        reply_markup=start_keyboard(lang),
    )
    await callback.answer()


@router.callback_query(F.data == "catalog:open")
async def open_catalog(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    title = f"{ce('news_catalog')} Catalog:" if lang == "en" else f"{ce('news_catalog')} Каталог:"
    await edit_or_answer(callback.message, title, reply_markup=await catalog_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data.startswith("product:"))
async def open_product(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(selected_product_code=callback.data.split(":", 1)[1])
    lang = await get_lang(callback.from_user.id)
    product_code = callback.data.split(":", 1)[1]
    await edit_or_answer(callback.message, await product_text(lang, product_code), reply_markup=product_keyboard(lang, product_code))
    await callback.answer()


@router.callback_query(F.data == "profile:open")
async def open_profile(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await ensure_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
    lang = await get_lang(callback.from_user.id)
    await answer_with_banner(
        callback.message,
        await profile_text(callback.from_user.id, lang),
        reply_markup=profile_keyboard(lang),
    )
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
    await edit_or_answer(callback.message, text, reply_markup=profile_back_keyboard(lang))
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
    await edit_or_answer(callback.message, text, reply_markup=topup_payment_keyboard(amount, lang))
    await callback.answer()


@router.callback_query(F.data == "topup:cancel")
async def cancel_topup(callback: CallbackQuery, state: FSMContext) -> None:
    lang = await get_lang(callback.from_user.id)
    await state.clear()
    text = "Top-up cancelled." if lang == "en" else "Пополнение отменено."
    await edit_or_answer(callback.message, text, reply_markup=profile_back_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data.startswith("platega:check:"))
async def check_platega_payment(callback: CallbackQuery, bot: Bot) -> None:
    lang = await get_lang(callback.from_user.id)
    payment_id = int(callback.data.split(":")[-1])
    payment = await get_platega_payment(payment_id)
    if not payment or payment["user_id"] != callback.from_user.id:
        await callback.answer("Payment not found." if lang == "en" else "Платеж не найден.", show_alert=True)
        return

    if payment["status"] == "CANCELLED":
        await callback.answer("Payment was cancelled." if lang == "en" else "Оплата отменена.", show_alert=True)
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


@router.callback_query(F.data.startswith("platega:cancel:"))
async def cancel_platega_invoice(callback: CallbackQuery, bot: Bot) -> None:
    lang = await get_lang(callback.from_user.id)
    payment_id = int(callback.data.split(":")[-1])
    payment = await get_platega_payment(payment_id)
    if not payment or payment["user_id"] != callback.from_user.id:
        await callback.answer("Payment not found." if lang == "en" else "Платеж не найден.", show_alert=True)
        return

    if payment["status"] == "CONFIRMED":
        await callback.answer("Payment has already been credited." if lang == "en" else "Платеж уже зачислен.", show_alert=True)
        return

    try:
        transaction = await get_platega_transaction(str(payment["transaction_id"]))
    except Exception:
        transaction = None

    if str((transaction or {}).get("status", "")).upper() == "CONFIRMED":
        username = await payment_username(callback.from_user.id)
        completed = await complete_platega_payment(payment_id, username, "CONFIRMED")
        if completed:
            await notify_paid_payment(bot, completed, "Platega")
            await callback.answer()
            return

    cancelled = await cancel_platega_payment(payment_id, callback.from_user.id)
    text = (
        f"{ce('cross')} Payment cancelled. You can create a new payment anytime."
        if lang == "en"
        else f"{ce('cross')} Оплата отменена. Вы можете создать новый счет в любой момент."
    )
    await edit_or_answer(callback.message, text, reply_markup=start_keyboard(lang))
    await callback.answer("Cancelled." if cancelled and lang == "en" else "Отменено.")


@router.callback_query(F.data == "profile:purchases")
async def profile_purchases(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    await edit_or_answer(callback.message,
        format_orders(await get_user_orders(callback.from_user.id), lang),
        reply_markup=profile_back_keyboard(lang),
    )
    await callback.answer()


@router.callback_query(F.data == "profile:promo")
async def profile_promo(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    text = f"{ce('fire')} No active promo codes right now." if lang == "en" else f"{ce('fire')} Сейчас активных промокодов нет."
    await edit_or_answer(callback.message, text, reply_markup=profile_back_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "payment:cryptobot")
async def start_crypto_order(callback: CallbackQuery, state: FSMContext) -> None:
    lang = await get_lang(callback.from_user.id)
    await state.clear()
    await ensure_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
    product = await get_product_config(PRODUCT_CODE)
    price = int(product["price_rub"])
    sale_usd = Decimal(str(product["price_usd"]))
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
            amount_usd=sale_usd,
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
    await edit_or_answer(callback.message, text, reply_markup=product_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "profile:transactions")
async def profile_transactions(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    await edit_or_answer(callback.message,
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
    await edit_or_answer(callback.message, text, reply_markup=profile_back_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "profile:language")
async def profile_language(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    current = "English" if lang == "en" else "Русский"
    await edit_or_answer(callback.message,
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
    await edit_or_answer(callback.message, text, reply_markup=profile_back_keyboard(lang))
    await callback.message.answer(await home_text(lang, display_user_name(callback.from_user)), reply_markup=start_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data.startswith("buy:start") | (F.data == "bulk:start"))
async def start_bulk_order(callback: CallbackQuery, state: FSMContext) -> None:
    lang = await get_lang(callback.from_user.id)
    parts = callback.data.split(":")
    product_code = parts[2] if len(parts) > 2 else PRODUCT_CODE
    if product_code in SUPPORT_ONLY_PRODUCT_CODES:
        text = (
            f"{ce('support')} This product is ordered through support: {SUPPORT_USERNAME}"
            if lang == "en"
            else f"{ce('support')} Этот товар оформляется через поддержку: {SUPPORT_USERNAME}"
        )
        await safe_answer(callback.message, text, reply_markup=product_keyboard(lang, product_code))
        await callback.answer()
        return
    await state.clear()
    await state.update_data(bulk_product_code=product_code)
    await safe_answer(callback.message, await quantity_text(lang, product_code), reply_markup=quantity_keyboard(lang, product_code))
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
    data = await state.get_data()
    product_code = data.get("bulk_product_code") or PRODUCT_CODE
    await state.set_state(BulkOrderState.waiting_for_quantity)
    text = (
        f"{product_icon(product_code)} Send a number with how many items you want to buy."
        if lang == "en"
        else f"{product_icon(product_code)} Отправьте числом, сколько штук хотите купить."
    )
    await safe_answer(callback.message, text)
    await callback.answer()


@router.message(BulkOrderState.waiting_for_quantity)
async def receive_bulk_quantity(message: Message, state: FSMContext, bot: Bot) -> None:
    await ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    lang = await get_lang(message.from_user.id)
    raw_quantity = (message.text or "").strip()

    if not raw_quantity.isdigit():
        data = await state.get_data()
        product_code = data.get("bulk_product_code") or PRODUCT_CODE
        text = (
            "Send only a whole number, for example: <b>2</b>."
            if lang == "en"
            else "Отправьте только целое число, например: <b>2</b>."
        )
        await message.answer(text, reply_markup=quantity_keyboard(lang, product_code))
        return

    quantity = int(raw_quantity)
    await show_payment_methods_for_quantity(message, state, quantity, lang)


@router.callback_query(F.data.startswith("bulk:pay:"))
async def choose_bulk_payment(callback: CallbackQuery, state: FSMContext) -> None:
    lang = await get_lang(callback.from_user.id)
    data = await state.get_data()
    quantity = int(data.get("bulk_quantity") or 0)
    product_code = data.get("bulk_product_code") or PRODUCT_CODE
    method = callback.data.split(":")[-1]

    if quantity <= 0:
        await state.set_state(BulkOrderState.waiting_for_quantity)
        text = "Send the quantity again." if lang == "en" else "Отправьте количество еще раз."
        await callback.message.answer(text)
        await callback.answer()
        return

    stock = await count_available_links(product_code)
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
        product = await get_product_config(product_code)
        pricing = calculate_order_price(product, quantity)
        total = int(pricing["total_rub"])
        if method in {"cryptobot", "platega"}:
            sale_usd = Decimal(pricing["unit_usd"]) * quantity
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
                        product_code=product_code,
                        product_title=title,
                        quantity=quantity,
                        contact=contact,
                        amount_usd=sale_usd,
                    )
                else:
                    await send_platega_invoice(
                        callback.message,
                        callback.from_user.id,
                        total,
                        "bulk_order",
                        lang,
                        product_code=product_code,
                        product_title=title,
                        quantity=quantity,
                        contact=contact,
                        amount_usd=sale_usd,
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
            f"Price per item: <b>{pricing['unit_rub']} ₽ / {format_usd(pricing['unit_usd'])}$</b>\n"
            f"Amount: <b>{total} ₽</b>"
            if lang == "en"
            else f"{ce('news_money')} Оплата через <b>{method_name}</b> будет подключена позже.\n\n"
            f"Количество: <b>{quantity}</b>\n"
            f"Цена за 1 шт.: <b>{pricing['unit_rub']} ₽ / {format_usd(pricing['unit_usd'])}$</b>\n"
            f"Сумма: <b>{total} ₽</b>"
        )
        await callback.message.answer(text, reply_markup=bulk_payment_keyboard(quantity, lang))
        await callback.answer()
        return

    user = await ensure_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
    product = await get_product_config(product_code)
    pricing = calculate_order_price(product, quantity)
    total = int(pricing["total_rub"])
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
    data = await state.get_data()
    quantity = int(data.get("bulk_quantity") or 0)
    product_code = data.get("bulk_product_code") or PRODUCT_CODE
    product = await get_product_config(product_code)
    stock = await count_available_links(product_code)
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
    pricing = calculate_order_price(product, quantity)
    total = int(pricing["total_rub"])
    sale_usd = Decimal(pricing["unit_usd"]) * quantity
    order_title = f"{product['title']} ×{quantity}"
    status = "Ожидает обработки" if stock >= quantity else "Резерв, нет в наличии"

    order = await create_balance_order(
        user_id=message.from_user.id,
        username=username,
        product_code=product_code,
        product_title=order_title,
        price_rub=total,
        contact=contact,
        status=status,
        sale_usd=sale_usd,
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
        f"Цена за 1 шт.: {pricing['unit_rub']} ₽ / {format_usd(pricing['unit_usd'])}$\n"
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
    pricing = calculate_order_price(product, quantity)
    total = int(pricing["total_rub"])
    sale_usd = Decimal(pricing["unit_usd"]) * quantity
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
            amount_usd=sale_usd,
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

    if payment["status"] == "cancelled":
        await callback.answer("Payment was cancelled." if lang == "en" else "Оплата отменена.", show_alert=True)
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


@router.callback_query(F.data.startswith("cryptobot:cancel:"))
async def cancel_cryptobot_invoice(callback: CallbackQuery, bot: Bot) -> None:
    lang = await get_lang(callback.from_user.id)
    payment_id = int(callback.data.split(":")[-1])
    payment = await get_crypto_payment(payment_id)
    if not payment or payment["user_id"] != callback.from_user.id:
        await callback.answer("Payment not found." if lang == "en" else "Платеж не найден.", show_alert=True)
        return

    if payment["status"] == "paid":
        await callback.answer("Payment has already been credited." if lang == "en" else "Платеж уже зачислен.", show_alert=True)
        return

    try:
        invoice = await get_cryptobot_invoice(int(payment["invoice_id"]))
    except Exception:
        invoice = None

    if invoice and invoice.get("status") == "paid":
        username = await payment_username(callback.from_user.id)
        completed = await complete_crypto_payment(payment_id, username, "Оплачен Crypto Bot, ожидает обработки")
        if completed:
            await notify_paid_payment(bot, completed, "Crypto Bot")
            await callback.answer()
            return

    cancelled = await cancel_crypto_payment(payment_id, callback.from_user.id)
    text = (
        f"{ce('cross')} Payment cancelled. You can create a new payment anytime."
        if lang == "en"
        else f"{ce('cross')} Оплата отменена. Вы можете создать новый счет в любой момент."
    )
    await edit_or_answer(callback.message, text, reply_markup=start_keyboard(lang))
    await callback.answer("Cancelled." if cancelled and lang == "en" else "Отменено.")


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
    sale_usd = Decimal(str(product["price_usd"]))
    order = await create_balance_order(
        user_id=message.from_user.id,
        username=username,
        product_code=PRODUCT_CODE,
        product_title=product["title"],
        price_rub=price,
        contact=contact,
        status=status,
        sale_usd=sale_usd,
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
        ],
        scope=BotCommandScopeDefault(),
    )
    if ADMIN_ID and ADMIN_ID.isdigit():
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Открыть магазин"),
                BotCommand(command="stock", description="Остаток ссылок"),
                BotCommand(command="stats", description="Статистика бота"),
                BotCommand(command="daystats", description="Статистика за день"),
                BotCommand(command="giveitem", description="Выдать товар пользователю"),
                BotCommand(command="addbalance", description="Пополнить баланс пользователю"),
                BotCommand(command="removebalance", description="Списать баланс у пользователя"),
                BotCommand(command="createapikey", description="Создать API-ключ покупателю"),
                BotCommand(command="takeitem", description="Забрать товар себе"),
                BotCommand(command="resendorder", description="Повторно отправить заказ"),
                BotCommand(command="resend", description="Повторно отправить заказ"),
                BotCommand(command="setreviews", description="Set reviews channel"),
                BotCommand(command="setprice", description="Поменять цену товара"),
                BotCommand(command="setcost", description="Поменять закуп товара"),
                BotCommand(command="addlinks", description="Добавить ссылки"),
                BotCommand(command="addgptaccounts", description="Добавить GPT аккаунты"),
                BotCommand(command="addgeminiaccounts", description="Добавить Gemini аккаунты"),
                BotCommand(command="addgrokaccounts", description="Добавить SUPERGROK аккаунты"),
                BotCommand(command="addgrok3daccounts", description="Добавить Grok 3d аккаунты"),
                BotCommand(command="broadcast", description="Рассылка"),
            ],
            scope=BotCommandScopeChat(chat_id=int(ADMIN_ID)),
        )

    dispatcher = Dispatcher()
    dispatcher.message.middleware(SubscriptionMiddleware())
    dispatcher.callback_query.middleware(SubscriptionMiddleware())
    dispatcher.include_router(router)

    asyncio.create_task(auto_payment_watcher(bot))
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
