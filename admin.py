import os
import secrets
import hmac
import hashlib
from decimal import Decimal
from typing import Any

from dotenv import load_dotenv
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from bot import notify_paid_payment, payment_username, process_reserved_orders
from db import (
    add_links,
    admin_stats,
    business_stats_by_days,
    complete_crypto_payment,
    complete_platega_payment,
    channel_leave_stats,
    daily_unique_visits,
    daily_business_stats,
    delete_available_links,
    delete_link,
    ensure_schema,
    get_crypto_payment_by_invoice,
    get_platega_payment_by_transaction,
    get_product_config,
    get_reseller_api_client,
    list_product_configs,
    list_links,
    list_users,
    count_available_links,
    create_reseller_api_order,
    recent_orders,
    update_platega_payment_status,
    update_order_status,
    update_product_config,
)


load_dotenv()

ADMIN_LOGIN = os.getenv("ADMIN_LOGIN", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change_me")
ADMIN_CORS_ORIGINS = os.getenv("ADMIN_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN")
PLATEGA_MERCHANT_ID = os.getenv("PLATEGA_MERCHANT_ID", "")
PLATEGA_SECRET = os.getenv("PLATEGA_SECRET", "")

app = FastAPI(title="Gemini Store Admin API")
security = HTTPBasic()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in ADMIN_CORS_ORIGINS.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LinksPayload(BaseModel):
    links: str
    product_code: str = "gemini_link_18_month"


class ProductPayload(BaseModel):
    code: str = "gemini_link_18_month"
    title: str
    price_rub: Decimal
    price_usd: Decimal
    description: str


class OrderStatusPayload(BaseModel):
    status: str


class ResellerOrderPayload(BaseModel):
    product_code: str
    quantity: int = 1
    request_id: str = ""


PRODUCT_ALIASES = {
    "link": "gemini_link_18_month",
    "links": "gemini_link_18_month",
    "gpt": "gpt_account_full_warranty",
    "chatgpt": "gpt_account_full_warranty",
    "grok": "supergrok_1_month",
    "supergrok": "supergrok_1_month",
    "grok3d": "grok_3d_full_warranty",
    "gemini12": "gemini_account_12_month",
}
SUPPORT_ONLY_PRODUCT_CODES = {"claude_max_x5_cdk", "claude_max_x20_cdk"}


def resolve_product_code(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    return PRODUCT_ALIASES.get(normalized, normalized)


def check_auth(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    if credentials.username != ADMIN_LOGIN or credentials.password != ADMIN_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect login or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


async def check_reseller_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict:
    client = await get_reseller_api_client(x_api_key or "")
    if not client:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return client


def check_platega_headers(merchant_id: str | None, secret: str | None) -> None:
    valid_merchant = bool(PLATEGA_MERCHANT_ID) and secrets.compare_digest(merchant_id or "", PLATEGA_MERCHANT_ID)
    valid_secret = bool(PLATEGA_SECRET) and secrets.compare_digest(secret or "", PLATEGA_SECRET)
    if not valid_merchant or not valid_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")


def check_cryptobot_signature(body: bytes, signature: str | None) -> None:
    if not CRYPTOBOT_TOKEN or not signature:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")
    secret = hashlib.sha256(CRYPTOBOT_TOKEN.encode("utf-8")).digest()
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    if not secrets.compare_digest(expected, signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")


def clean_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def clean_row(row: dict) -> dict:
    return {key: clean_value(value) for key, value in row.items()}


@app.on_event("startup")
async def startup() -> None:
    await ensure_schema()


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True}


@app.post("/api/webhooks/platega")
async def platega_webhook(
    request: Request,
    x_merchantid: str | None = Header(default=None, alias="X-MerchantId"),
    x_secret: str | None = Header(default=None, alias="X-Secret"),
) -> dict:
    check_platega_headers(x_merchantid, x_secret)
    payload = await request.json()
    transaction_id = str(payload.get("id") or payload.get("transactionId") or "").strip()
    payment_status = str(payload.get("status") or "").upper()

    if not transaction_id or not payment_status:
        raise HTTPException(status_code=400, detail="Invalid webhook payload")

    payment = await get_platega_payment_by_transaction(transaction_id)
    if not payment:
        return {"ok": True, "ignored": "unknown_transaction"}

    if payment_status != "CONFIRMED":
        await update_platega_payment_status(transaction_id, payment_status)
        return {"ok": True, "status": payment_status}

    username = await payment_username(int(payment["user_id"]))
    completed = await complete_platega_payment(int(payment["id"]), username, payment_status)
    if completed and BOT_TOKEN:
        telegram_bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        try:
            await notify_paid_payment(telegram_bot, completed, "Platega")
        finally:
            await telegram_bot.session.close()

    return {"ok": True, "status": payment_status}


@app.post("/api/webhooks/cryptobot")
async def cryptobot_webhook(
    request: Request,
    crypto_pay_api_signature: str | None = Header(default=None, alias="crypto-pay-api-signature"),
) -> dict:
    body = await request.body()
    check_cryptobot_signature(body, crypto_pay_api_signature)
    payload = await request.json()

    if payload.get("update_type") != "invoice_paid":
        return {"ok": True, "ignored": "unsupported_update"}

    invoice = payload.get("payload") or {}
    invoice_id = invoice.get("invoice_id")
    if not invoice_id:
        raise HTTPException(status_code=400, detail="Invalid webhook payload")

    payment = await get_crypto_payment_by_invoice(int(invoice_id))
    if not payment:
        return {"ok": True, "ignored": "unknown_invoice"}

    username = await payment_username(int(payment["user_id"]))
    completed = await complete_crypto_payment(
        int(payment["id"]),
        username,
        "Оплачен Crypto Bot, ожидает обработки",
    )
    if completed and BOT_TOKEN:
        telegram_bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        try:
            await notify_paid_payment(telegram_bot, completed, "Crypto Bot")
        finally:
            await telegram_bot.session.close()

    return {"ok": True, "status": "paid"}


@app.get("/api/stats")
async def stats(_: str = Depends(check_auth)) -> dict:
    return await admin_stats()


@app.get("/api/business/day")
async def business_day(_: str = Depends(check_auth)) -> dict:
    return clean_row(await daily_business_stats())


@app.get("/api/business/days")
async def business_days(days: int = 30, _: str = Depends(check_auth)) -> list[dict]:
    safe_days = max(1, min(days, 90))
    return [clean_row(row) for row in await business_stats_by_days(safe_days)]


@app.get("/api/visits")
async def visits(days: int = 14, _: str = Depends(check_auth)) -> list[dict]:
    safe_days = max(1, min(days, 60))
    return [clean_row(row) for row in await daily_unique_visits(safe_days)]


@app.get("/api/channel/leaves")
async def channel_leaves(days: int = 14, _: str = Depends(check_auth)) -> dict:
    safe_days = max(1, min(days, 60))
    data = await channel_leave_stats(safe_days, 50)
    return {
        "today_leaves": data["today_leaves"],
        "total_leaves": data["total_leaves"],
        "chart": [clean_row(row) for row in data["chart"]],
        "recent": [clean_row(row) for row in data["recent"]],
    }


@app.get("/api/orders")
async def orders(_: str = Depends(check_auth)) -> list[dict]:
    return [clean_row(order) for order in await recent_orders(100)]


@app.patch("/api/orders/{order_id}/status")
async def change_order_status(
    order_id: int,
    payload: OrderStatusPayload,
    _: str = Depends(check_auth),
) -> dict:
    order = await update_order_status(order_id, payload.status.strip())
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return clean_row(order)


@app.get("/api/users")
async def users(_: str = Depends(check_auth)) -> list[dict]:
    return [clean_row(user) for user in await list_users(100)]


@app.get("/api/links")
async def links(product_code: str = "gemini_link_18_month", _: str = Depends(check_auth)) -> list[dict]:
    return [clean_row(link) for link in await list_links(200, product_code)]


@app.get("/api/links/summary")
async def links_summary(product_code: str = "gemini_link_18_month", _: str = Depends(check_auth)) -> dict:
    rows = await list_links(10000, product_code)
    total = len(rows)
    issued = sum(1 for row in rows if row["is_issued"])
    return {"total": total, "available": total - issued, "issued": issued}


@app.post("/api/links")
async def create_links(payload: LinksPayload, _: str = Depends(check_auth)) -> dict:
    added = await add_links(payload.links.splitlines(), payload.product_code)
    processed = 0
    if added and BOT_TOKEN:
        telegram_bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        try:
            processed = await process_reserved_orders(telegram_bot, payload.product_code)
        finally:
            await telegram_bot.session.close()
    return {"added": added, "processed_reserves": processed}


@app.delete("/api/links/available")
async def remove_available_links(product_code: str = "gemini_link_18_month", _: str = Depends(check_auth)) -> dict:
    deleted = await delete_available_links(product_code)
    return {"deleted": deleted}


@app.delete("/api/links/{link_id}")
async def remove_link(link_id: int, _: str = Depends(check_auth)) -> dict:
    deleted = await delete_link(link_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Link not found")
    return {"deleted": 1}


@app.get("/api/product")
async def product(code: str = "gemini_link_18_month", _: str = Depends(check_auth)) -> dict:
    return clean_row(await get_product_config(code))


@app.get("/api/products")
async def products(_: str = Depends(check_auth)) -> list[dict]:
    return [clean_row(product) for product in await list_product_configs()]


@app.get("/api/reseller/products")
async def reseller_products(client: dict = Depends(check_reseller_api_key)) -> dict:
    products_rows = []
    for product in await list_product_configs():
        if product["code"] in SUPPORT_ONLY_PRODUCT_CODES:
            continue
        products_rows.append(
            {
                **clean_row(product),
                "stock": await count_available_links(product["code"]),
            }
        )
    return {
        "ok": True,
        "user_id": client["user_id"],
        "balance": clean_value(client["balance"]),
        "products": products_rows,
    }


@app.post("/api/reseller/order")
async def reseller_order(payload: ResellerOrderPayload, client: dict = Depends(check_reseller_api_key)) -> dict:
    quantity = max(1, min(int(payload.quantity or 1), 100))
    product_code = resolve_product_code(payload.product_code)
    result = await create_reseller_api_order(
        user_id=int(client["user_id"]),
        key_id=int(client["key_id"]),
        product_code=product_code,
        quantity=quantity,
        request_id=payload.request_id.strip(),
    )
    if not result.get("ok"):
        error = result.get("error", "unknown_error")
        status_code = 400
        if error == "insufficient_balance":
            status_code = 402
        elif error in {"unknown_product", "not_enough_stock"}:
            status_code = 409
        raise HTTPException(status_code=status_code, detail=result)

    order = clean_row(result["order"])
    items = [{"id": item["id"], "product_code": item["product_code"], "value": item["url"]} for item in result["items"]]
    return {
        "ok": True,
        "order_id": order["id"],
        "product_code": order["product_code"],
        "product_title": order["product_title"],
        "quantity": result["quantity"],
        "unit_rub": result["unit_rub"],
        "unit_usd": clean_value(result["unit_usd"]),
        "total_rub": result["total_rub"],
        "total_usd": clean_value(result["total_usd"]),
        "balance": clean_value(result["balance"]),
        "items": items,
    }


@app.put("/api/product")
async def save_product(payload: ProductPayload, _: str = Depends(check_auth)) -> dict:
    product_row = await update_product_config(
        code=payload.code.strip(),
        title=payload.title.strip(),
        price_rub=payload.price_rub,
        price_usd=payload.price_usd,
        description=payload.description.strip(),
    )
    return clean_row(product_row)
