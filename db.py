import os
import re
from contextlib import contextmanager
from decimal import Decimal

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row


load_dotenv()


DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/gemini_store")
URL_RE = re.compile(r"https?://\S+")
PRODUCT_COST_USD = Decimal(os.getenv("PRODUCT_COST_USD", "1.50"))
NEW_LINK_COST_USD = Decimal(os.getenv("NEW_LINK_COST_USD", "1.10"))
REPORT_TZ = os.getenv("REPORT_TZ", "Europe/Moscow")
ADMIN_ID = os.getenv("ADMIN_ID", "")
if not ADMIN_ID.isdigit():
    ADMIN_ID = ""
DEFAULT_PRODUCT_CODE = "gemini_link_18_month"
GPT_ACCOUNT_PRODUCT_CODE = "gpt_account_full_warranty"
SUPERGROK_PRODUCT_CODE = "supergrok_1_month"


@contextmanager
def get_conn():
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        yield conn


def snapshot_sale_usd(conn, product_code: str, price_rub: int | Decimal, fallback: Decimal | None = None) -> Decimal:
    if fallback is not None:
        return Decimal(fallback)
    product = conn.execute(
        "SELECT price_rub, price_usd FROM product_settings WHERE code = %s",
        (product_code,),
    ).fetchone()
    if not product:
        return Decimal("0")
    product_rub = Decimal(product["price_rub"] or 0)
    product_usd = Decimal(product["price_usd"] or 0)
    if product_rub <= 0:
        return Decimal("0")
    return (Decimal(price_rub or 0) / product_rub) * product_usd


async def ensure_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                username TEXT NOT NULL DEFAULT '',
                first_name TEXT NOT NULL DEFAULT '',
                balance NUMERIC(12, 2) NOT NULL DEFAULT 0,
                language TEXT NOT NULL DEFAULT 'ru',
                ref_code TEXT NOT NULL UNIQUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            CREATE TABLE IF NOT EXISTS links (
                id BIGSERIAL PRIMARY KEY,
                url TEXT NOT NULL,
                product_code TEXT NOT NULL DEFAULT 'gemini_link_18_month',
                purchase_cost_usd NUMERIC(12, 2) NOT NULL DEFAULT 1.50,
                is_issued BOOLEAN NOT NULL DEFAULT FALSE,
                issued_to BIGINT REFERENCES users(id) ON DELETE SET NULL,
                order_id BIGINT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                issued_at TIMESTAMPTZ
            );

            CREATE TABLE IF NOT EXISTS orders (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                username TEXT NOT NULL DEFAULT '',
                product_code TEXT NOT NULL,
                product_title TEXT NOT NULL,
                price_rub NUMERIC(12, 2) NOT NULL,
                sale_usd NUMERIC(12, 2),
                contact TEXT NOT NULL,
                status TEXT NOT NULL,
                issued_link_id BIGINT REFERENCES links(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                type TEXT NOT NULL,
                amount NUMERIC(12, 2) NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            CREATE TABLE IF NOT EXISTS product_settings (
                code TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                price_rub NUMERIC(12, 2) NOT NULL,
                price_usd NUMERIC(12, 2) NOT NULL,
                description TEXT NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            CREATE TABLE IF NOT EXISTS crypto_payments (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                invoice_id BIGINT NOT NULL UNIQUE,
                purpose TEXT NOT NULL,
                amount_rub NUMERIC(12, 2) NOT NULL,
                amount_usd NUMERIC(12, 2),
                status TEXT NOT NULL DEFAULT 'active',
                product_code TEXT NOT NULL DEFAULT '',
                product_title TEXT NOT NULL DEFAULT '',
                quantity INTEGER NOT NULL DEFAULT 0,
                contact TEXT NOT NULL DEFAULT '',
                order_id BIGINT REFERENCES orders(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                paid_at TIMESTAMPTZ
            );

            CREATE TABLE IF NOT EXISTS reviews (
                id BIGSERIAL PRIMARY KEY,
                order_id BIGINT NOT NULL UNIQUE REFERENCES orders(id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
                comment TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            CREATE TABLE IF NOT EXISTS bot_visits (
                visit_date DATE NOT NULL DEFAULT CURRENT_DATE,
                user_id BIGINT NOT NULL,
                first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (visit_date, user_id)
            );

            CREATE TABLE IF NOT EXISTS channel_membership_events (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                username TEXT NOT NULL DEFAULT '',
                first_name TEXT NOT NULL DEFAULT '',
                event_type TEXT NOT NULL,
                old_status TEXT NOT NULL DEFAULT '',
                new_status TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT '',
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            CREATE TABLE IF NOT EXISTS platega_payments (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                transaction_id TEXT NOT NULL UNIQUE,
                purpose TEXT NOT NULL,
                amount_rub NUMERIC(12, 2) NOT NULL,
                amount_usd NUMERIC(12, 2),
                status TEXT NOT NULL DEFAULT 'PENDING',
                product_code TEXT NOT NULL DEFAULT '',
                product_title TEXT NOT NULL DEFAULT '',
                quantity INTEGER NOT NULL DEFAULT 0,
                contact TEXT NOT NULL DEFAULT '',
                order_id BIGINT REFERENCES orders(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                paid_at TIMESTAMPTZ
            );
            """
        )
        conn.execute("ALTER TABLE platega_payments ADD COLUMN IF NOT EXISTS product_code TEXT NOT NULL DEFAULT ''")
        conn.execute("ALTER TABLE platega_payments ADD COLUMN IF NOT EXISTS product_title TEXT NOT NULL DEFAULT ''")
        conn.execute("ALTER TABLE platega_payments ADD COLUMN IF NOT EXISTS quantity INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE platega_payments ADD COLUMN IF NOT EXISTS contact TEXT NOT NULL DEFAULT ''")
        conn.execute("ALTER TABLE platega_payments ADD COLUMN IF NOT EXISTS order_id BIGINT REFERENCES orders(id) ON DELETE SET NULL")
        conn.execute("ALTER TABLE crypto_payments ADD COLUMN IF NOT EXISTS amount_usd NUMERIC(12, 2)")
        conn.execute("ALTER TABLE platega_payments ADD COLUMN IF NOT EXISTS amount_usd NUMERIC(12, 2)")
        conn.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS sale_usd NUMERIC(12, 2)")
        conn.execute(
            "ALTER TABLE links ADD COLUMN IF NOT EXISTS purchase_cost_usd NUMERIC(12, 2) NOT NULL DEFAULT 1.50"
        )
        conn.execute(
            "ALTER TABLE links ADD COLUMN IF NOT EXISTS product_code TEXT NOT NULL DEFAULT 'gemini_link_18_month'"
        )
        conn.execute("ALTER TABLE links ADD COLUMN IF NOT EXISTS order_id BIGINT REFERENCES orders(id) ON DELETE SET NULL")
        conn.execute(
            """
            INSERT INTO product_settings (code, title, price_rub, price_usd, description)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (code) DO NOTHING
            """,
            (
                "gemini_link_18_month",
                "Gemini Link 18 months",
                Decimal("116.00"),
                Decimal("1.60"),
                (
                    "Гарантийная поддержка распространяется на момент активации персональной ссылки.\n\n"
                    "Google AI Pro на 18 месяцев с доступом к возможностям Gemini, Veo, генерации изображений, "
                    "работе с документами, облачному хранилищу Google Drive 5 ТБ и расширенным лимитам.\n\n"
                    "Подписка подключается к вашему аккаунту по индивидуальной ссылке. "
                    "Логин и пароль передавать не нужно."
                ),
            ),
        )
        default_products = [
            (
                "gpt_account_full_warranty",
                "GPT account full warranty",
                Decimal("290.00"),
                Decimal("4.00"),
                (
                    f"{'💰'} Цена: 4.00 USD\n"
                    f"{'⏳'} Срок действия: 30 дней\n"
                    f"{'🛡️'} Гарантия: 30 дней (1 замена)\n"
                    f"{'📦'} Доставка: READY_ACCOUNT\n\n"
                    "Готовый аккаунт ChatGPT Plus на 1 месяц. После оплаты вы получите данные для входа: "
                    "email и пароль от ChatGPT.\n\n"
                    "Аккаунты высокого качества, на Hotmail-почтах. Данные выдаются в готовом для использования формате: почта:пароль.\n\n"
                    "Рекомендации после получения:\n"
                    "- оставьте все данные аккаунта как есть;\n"
                    "- не меняйте email, пароль, резервные данные и не включайте 2FA;\n"
                    "- для стабильного входа используйте хороший прокси или хороший VPN;\n"
                    "- если вы измените любые данные аккаунта, гарантия слетает;\n"
                    "- если возникла проблема со входом, сначала напишите в поддержку."
                ),
            ),
            (
                "gemini_account_12_month",
                "Gemini account 12 month",
                Decimal("250.00"),
                Decimal("3.50"),
                (
                    f"{'💰'} Цена: 3.50 USD\n"
                    f"{'⏳'} Срок действия: 12 месяцев\n"
                    f"{'🛡️'} Гарантия: на момент выдачи и входа\n"
                    f"{'📦'} Доставка: READY_ACCOUNT\n\n"
                    "Готовый аккаунт Gemini с активным доступом на 12 месяцев. После оплаты выдаются данные для входа "
                    "и вся информация, которая нужна для использования аккаунта."
                ),
            ),
            (
                SUPERGROK_PRODUCT_CODE,
                "SUPERGROK 1 month [30 дней ГАРАНТИЯ]",
                Decimal("290.00"),
                Decimal("4.00"),
                (
                    f"{'💰'} Цена: 4.00 USD\n"
                    f"{'⏳'} Срок действия: 1 месяц\n"
                    f"{'🛡️'} Гарантия: 30 дней\n"
                    f"{'📦'} Доставка: READY_ACCOUNT\n\n"
                    "Что входит в комплект:\n"
                    "- email для входа;\n"
                    "- пароль;\n"
                    "- мгновенная выдача после покупки;\n"
                    "- готовый доступ к аккаунту.\n\n"
                    "Важные инструкции:\n"
                    "- используйте email и пароль строго в том виде, в котором они выданы;\n"
                    "- не меняйте email;\n"
                    "- не меняйте пароль;\n"
                    "- не добавляйте и не включайте 2FA;\n"
                    "- если возникла проблема со входом или аккаунтом, сначала напишите в поддержку и не вносите изменения самостоятельно."
                ),
            ),
        ]
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO product_settings (code, title, price_rub, price_usd, description)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (code) DO NOTHING
                """,
                default_products,
            )
        conn.execute(
            """
            UPDATE orders
            SET sale_usd = CASE
                WHEN product_settings.price_rub > 0
                    THEN (orders.price_rub / product_settings.price_rub) * product_settings.price_usd
                ELSE 0
            END
            FROM product_settings
            WHERE orders.product_code = product_settings.code
                AND orders.sale_usd IS NULL
                AND orders.price_rub > 0
            """
        )
        conn.execute("UPDATE orders SET sale_usd = 0 WHERE sale_usd IS NULL")


async def ensure_user(user_id: int, username: str | None, first_name: str | None) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO users (id, username, first_name, ref_code)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE
            SET username = EXCLUDED.username,
                first_name = EXCLUDED.first_name
            RETURNING *
            """,
            (user_id, username or "", first_name or "", f"ref{user_id}"),
        ).fetchone()
        return row


async def get_user(user_id: int) -> dict | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()


async def get_user_by_username(username: str) -> dict | None:
    normalized = username.strip().lstrip("@").lower()
    if not normalized:
        return None

    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE lower(username) = %s ORDER BY created_at DESC LIMIT 1",
            (normalized,),
        ).fetchone()


async def update_user_language(user_id: int, language: str) -> dict | None:
    with get_conn() as conn:
        return conn.execute(
            "UPDATE users SET language = %s WHERE id = %s RETURNING *",
            (language, user_id),
        ).fetchone()


async def record_bot_visit(user_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO bot_visits (visit_date, user_id)
            VALUES (CURRENT_DATE, %s)
            ON CONFLICT (visit_date, user_id) DO NOTHING
            """,
            (user_id,),
        )


async def daily_unique_visits(days: int = 14) -> list[dict]:
    with get_conn() as conn:
        return conn.execute(
            """
            WITH dates AS (
                SELECT generate_series(
                    CURRENT_DATE - (%s::int - 1),
                    CURRENT_DATE,
                    INTERVAL '1 day'
                )::date AS visit_date
            )
            SELECT
                dates.visit_date,
                COALESCE(count(bot_visits.user_id), 0)::int AS visits
            FROM dates
            LEFT JOIN bot_visits ON bot_visits.visit_date = dates.visit_date
            GROUP BY dates.visit_date
            ORDER BY dates.visit_date
            """,
            (days,),
        ).fetchall()


async def record_channel_membership_event(
    user_id: int,
    username: str | None,
    first_name: str | None,
    event_type: str,
    old_status: str,
    new_status: str,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO channel_membership_events (
                user_id, username, first_name, event_type, old_status, new_status
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (user_id, username or "", first_name or "", event_type, old_status, new_status),
        )


async def channel_leave_stats(days: int = 14, limit: int = 50) -> dict:
    with get_conn() as conn:
        today_leaves = conn.execute(
            """
            SELECT count(*)::int AS count
            FROM channel_membership_events
            WHERE event_type = 'left'
                AND (created_at AT TIME ZONE %s)::date = (now() AT TIME ZONE %s)::date
            """,
            (REPORT_TZ, REPORT_TZ),
        ).fetchone()["count"]
        total_leaves = conn.execute(
            """
            SELECT count(*)::int AS count
            FROM channel_membership_events
            WHERE event_type = 'left'
            """,
        ).fetchone()["count"]
        chart = conn.execute(
            """
            WITH dates AS (
                SELECT generate_series(
                    CURRENT_DATE - (%s::int - 1),
                    CURRENT_DATE,
                    INTERVAL '1 day'
                )::date AS event_date
            )
            SELECT
                dates.event_date,
                COALESCE(count(events.id), 0)::int AS leaves
            FROM dates
            LEFT JOIN channel_membership_events AS events
                ON events.event_type = 'left'
                AND (events.created_at AT TIME ZONE %s)::date = dates.event_date
            GROUP BY dates.event_date
            ORDER BY dates.event_date
            """,
            (days, REPORT_TZ),
        ).fetchall()
        recent = conn.execute(
            """
            SELECT user_id, username, first_name, old_status, new_status, created_at
            FROM channel_membership_events
            WHERE event_type = 'left'
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return {
        "today_leaves": today_leaves,
        "total_leaves": total_leaves,
        "chart": chart,
        "recent": recent,
    }


def purchase_cost_for_product(product_code: str) -> Decimal:
    if product_code == GPT_ACCOUNT_PRODUCT_CODE:
        return Decimal("1.50")
    if product_code == SUPERGROK_PRODUCT_CODE:
        return Decimal("4.00")
    return NEW_LINK_COST_USD


async def add_links(links: list[str], product_code: str = DEFAULT_PRODUCT_CODE) -> int:
    clean_links = []
    for line in links:
        clean_line = line.strip()
        match = URL_RE.search(clean_line)
        if match:
            clean_links.append(match.group(0))
        elif clean_line:
            clean_links.append(clean_line)

    if not clean_links:
        return 0

    with get_conn() as conn:
        with conn.cursor() as cur:
            purchase_cost = purchase_cost_for_product(product_code)
            cur.executemany(
                "INSERT INTO links (url, product_code, purchase_cost_usd) VALUES (%s, %s, %s)",
                [(link, product_code, purchase_cost) for link in clean_links],
            )
    return len(clean_links)


async def list_links(limit: int = 100, product_code: str | None = None) -> list[dict]:
    with get_conn() as conn:
        where = "WHERE product_code = %s" if product_code else ""
        params: tuple = (product_code, limit) if product_code else (limit,)
        return conn.execute(
            f"""
            SELECT id, url, product_code, purchase_cost_usd, is_issued, issued_to, created_at, issued_at
            FROM links
            {where}
            ORDER BY created_at DESC
            LIMIT %s
            """,
            params,
        ).fetchall()


async def delete_link(link_id: int) -> dict | None:
    with get_conn() as conn:
        return conn.execute("DELETE FROM links WHERE id = %s RETURNING *", (link_id,)).fetchone()


async def delete_available_links(product_code: str | None = None) -> int:
    with get_conn() as conn:
        if product_code:
            rows = conn.execute(
                "DELETE FROM links WHERE is_issued = FALSE AND product_code = %s RETURNING id",
                (product_code,),
            ).fetchall()
        else:
            rows = conn.execute("DELETE FROM links WHERE is_issued = FALSE RETURNING id").fetchall()
        return len(rows)


async def count_available_links(product_code: str = DEFAULT_PRODUCT_CODE) -> int:
    with get_conn() as conn:
        return conn.execute(
            "SELECT count(*) AS count FROM links WHERE is_issued = FALSE AND product_code = %s",
            (product_code,),
        ).fetchone()["count"]


async def issue_links_to_order(order_id: int, user_id: int, quantity: int, status: str = "Выдан") -> list[dict] | None:
    with get_conn() as conn:
        order = conn.execute(
            "SELECT issued_link_id, product_code FROM orders WHERE id = %s FOR UPDATE",
            (order_id,),
        ).fetchone()
        if not order:
            return None
        if order["issued_link_id"]:
            return await get_order_issued_links(order_id, quantity)

        links = conn.execute(
            """
            SELECT id, url, product_code
            FROM links
            WHERE is_issued = FALSE
                AND product_code = %s
            ORDER BY id
            LIMIT %s
            FOR UPDATE SKIP LOCKED
            """,
            (order["product_code"], quantity),
        ).fetchall()
        if len(links) < quantity:
            conn.execute(
                "UPDATE orders SET status = %s WHERE id = %s",
                ("Резерв, нет в наличии", order_id),
            )
            return []

        link_ids = [link["id"] for link in links]
        conn.execute(
            """
            UPDATE links
            SET is_issued = TRUE,
                issued_to = %s,
                order_id = %s,
                issued_at = now()
            WHERE id = ANY(%s::bigint[])
            """,
            (user_id, order_id, link_ids),
        )
        conn.execute(
            """
            UPDATE orders
            SET issued_link_id = %s,
                status = %s
            WHERE id = %s
            """,
            (link_ids[0], status, order_id),
        )
        return links


async def get_order_issued_links(order_id: int, quantity: int | None = None) -> list[dict]:
    with get_conn() as conn:
        order = conn.execute(
            "SELECT id, user_id, product_code, issued_link_id FROM orders WHERE id = %s",
            (order_id,),
        ).fetchone()
        if not order or not order["issued_link_id"]:
            return []

        links = conn.execute(
            """
            SELECT id, url, product_code
            FROM links
            WHERE order_id = %s
            ORDER BY id
            """,
            (order_id,),
        ).fetchall()
        if links:
            return links

        limit = quantity or 1
        return conn.execute(
            """
            SELECT id, url, product_code
            FROM links
            WHERE is_issued = TRUE
                AND issued_to = %s
                AND product_code = %s
                AND id >= %s
            ORDER BY id
            LIMIT %s
            """,
            (order["user_id"], order["product_code"], order["issued_link_id"], limit),
        ).fetchall()


async def create_order(
    user_id: int,
    username: str,
    product_code: str,
    product_title: str,
    price_rub: int,
    contact: str,
    status: str,
    sale_usd: Decimal | None = None,
) -> dict:
    with get_conn() as conn:
        sale_usd = snapshot_sale_usd(conn, product_code, price_rub, sale_usd)
        return conn.execute(
            """
            INSERT INTO orders (user_id, username, product_code, product_title, price_rub, sale_usd, contact, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (user_id, username, product_code, product_title, price_rub, sale_usd, contact, status),
        ).fetchone()


async def add_user_balance(user_id: int, amount_rub: int, description: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (amount_rub, user_id))
        conn.execute(
            """
            INSERT INTO transactions (user_id, type, amount, description)
            VALUES (%s, %s, %s, %s)
            """,
            (user_id, "topup", amount_rub, description),
        )


async def create_balance_order(
    user_id: int,
    username: str,
    product_code: str,
    product_title: str,
    price_rub: int,
    contact: str,
    status: str,
    sale_usd: Decimal | None = None,
) -> dict | None:
    with get_conn() as conn:
        charged_user = conn.execute(
            """
            UPDATE users
            SET balance = balance - %s
            WHERE id = %s AND balance >= %s
            RETURNING balance
            """,
            (price_rub, user_id, price_rub),
        ).fetchone()
        if not charged_user:
            return None

        sale_usd = snapshot_sale_usd(conn, product_code, price_rub, sale_usd)
        order = conn.execute(
            """
            INSERT INTO orders (user_id, username, product_code, product_title, price_rub, sale_usd, contact, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (user_id, username, product_code, product_title, price_rub, sale_usd, contact, status),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO transactions (user_id, type, amount, description)
            VALUES (%s, %s, %s, %s)
            """,
            (user_id, "purchase", -price_rub, f"Balance payment: {product_title}"),
        )
        return order


async def create_crypto_payment(
    user_id: int,
    invoice_id: int,
    purpose: str,
    amount_rub: int,
    amount_usd: Decimal | None = None,
    product_code: str = "",
    product_title: str = "",
    quantity: int = 0,
    contact: str = "",
) -> dict:
    with get_conn() as conn:
        return conn.execute(
            """
            INSERT INTO crypto_payments (
                user_id, invoice_id, purpose, amount_rub, amount_usd, product_code, product_title, quantity, contact
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (user_id, invoice_id, purpose, amount_rub, amount_usd, product_code, product_title, quantity, contact),
        ).fetchone()


async def get_crypto_payment(payment_id: int) -> dict | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM crypto_payments WHERE id = %s", (payment_id,)).fetchone()


async def get_crypto_payment_by_invoice(invoice_id: int) -> dict | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM crypto_payments WHERE invoice_id = %s",
            (invoice_id,),
        ).fetchone()


async def cancel_crypto_payment(payment_id: int, user_id: int) -> dict | None:
    with get_conn() as conn:
        return conn.execute(
            """
            UPDATE crypto_payments
            SET status = 'cancelled'
            WHERE id = %s
              AND user_id = %s
              AND status <> 'paid'
              AND status <> 'cancelled'
            RETURNING *
            """,
            (payment_id, user_id),
        ).fetchone()


async def complete_crypto_payment(payment_id: int, username: str, order_status: str) -> dict | None:
    with get_conn() as conn:
        payment = conn.execute(
            "SELECT * FROM crypto_payments WHERE id = %s FOR UPDATE",
            (payment_id,),
        ).fetchone()
        if not payment:
            return None
        if payment["status"] == "paid":
            return None

        order_id = None
        if payment["purpose"] == "topup":
            conn.execute(
                "UPDATE users SET balance = balance + %s WHERE id = %s",
                (payment["amount_rub"], payment["user_id"]),
            )
            conn.execute(
                """
                INSERT INTO transactions (user_id, type, amount, description)
                VALUES (%s, %s, %s, %s)
                """,
                (payment["user_id"], "topup", payment["amount_rub"], "Crypto Bot top-up"),
            )
        elif payment["purpose"] in {"order", "bulk_order"}:
            sale_usd = snapshot_sale_usd(conn, payment["product_code"], payment["amount_rub"], payment["amount_usd"])
            order = conn.execute(
                """
                INSERT INTO orders (user_id, username, product_code, product_title, price_rub, sale_usd, contact, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    payment["user_id"],
                    username,
                    payment["product_code"],
                    payment["product_title"],
                    payment["amount_rub"],
                    sale_usd,
                    payment["contact"],
                    order_status,
                ),
            ).fetchone()
            order_id = order["id"]
            conn.execute(
                """
                INSERT INTO transactions (user_id, type, amount, description)
                VALUES (%s, %s, %s, %s)
                """,
                (payment["user_id"], "crypto_payment", payment["amount_rub"], f"Crypto Bot: {payment['product_title']}"),
            )

        return conn.execute(
            """
            UPDATE crypto_payments
            SET status = 'paid', paid_at = now(), order_id = COALESCE(%s, order_id)
            WHERE id = %s
            RETURNING *
            """,
            (order_id, payment_id),
        ).fetchone()


async def update_order_status(order_id: int, status: str) -> dict | None:
    with get_conn() as conn:
        return conn.execute(
            "UPDATE orders SET status = %s WHERE id = %s RETURNING *",
            (status, order_id),
        ).fetchone()


async def get_order(order_id: int) -> dict | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM orders WHERE id = %s", (order_id,)).fetchone()


async def get_user_orders(user_id: int) -> list[dict]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM orders WHERE user_id = %s ORDER BY created_at", (user_id,)).fetchall()


async def list_reserved_orders(product_code: str | None = None, limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        product_filter = "AND product_code = %s" if product_code else ""
        params: tuple = (product_code, limit) if product_code else (limit,)
        return conn.execute(
            f"""
            SELECT *
            FROM orders
            WHERE status = 'Резерв, нет в наличии'
              {product_filter}
            ORDER BY created_at
            LIMIT %s
            """,
            params,
        ).fetchall()


async def create_review(user_id: int, order_id: int, rating: int, comment: str) -> dict | None:
    with get_conn() as conn:
        order = conn.execute(
            "SELECT id, product_title FROM orders WHERE id = %s AND user_id = %s",
            (order_id, user_id),
        ).fetchone()
        if not order:
            return None

        review = conn.execute(
            """
            INSERT INTO reviews (order_id, user_id, rating, comment)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (order_id) DO NOTHING
            RETURNING *
            """,
            (order_id, user_id, rating, comment),
        ).fetchone()
        if not review:
            return None

        return {**review, "product_title": order["product_title"]}


async def get_transactions(user_id: int) -> list[dict]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM transactions WHERE user_id = %s ORDER BY created_at", (user_id,)).fetchall()


async def create_platega_payment(
    user_id: int,
    transaction_id: str,
    purpose: str,
    amount_rub: int,
    amount_usd: Decimal | None = None,
    product_code: str = "",
    product_title: str = "",
    quantity: int = 0,
    contact: str = "",
) -> dict:
    with get_conn() as conn:
        return conn.execute(
            """
            INSERT INTO platega_payments (
                user_id, transaction_id, purpose, amount_rub, amount_usd, product_code, product_title, quantity, contact
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (user_id, transaction_id, purpose, amount_rub, amount_usd, product_code, product_title, quantity, contact),
        ).fetchone()


async def get_platega_payment(payment_id: int) -> dict | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM platega_payments WHERE id = %s", (payment_id,)).fetchone()


async def get_platega_payment_by_transaction(transaction_id: str) -> dict | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM platega_payments WHERE transaction_id = %s",
            (transaction_id,),
        ).fetchone()


async def update_platega_payment_status(transaction_id: str, status: str) -> dict | None:
    with get_conn() as conn:
        return conn.execute(
            """
            UPDATE platega_payments
            SET status = %s
            WHERE transaction_id = %s
              AND status <> 'CONFIRMED'
              AND status <> 'CANCELLED'
            RETURNING *
            """,
            (status, transaction_id),
        ).fetchone()


async def cancel_platega_payment(payment_id: int, user_id: int) -> dict | None:
    with get_conn() as conn:
        return conn.execute(
            """
            UPDATE platega_payments
            SET status = 'CANCELLED'
            WHERE id = %s
              AND user_id = %s
              AND status <> 'CONFIRMED'
              AND status <> 'CANCELLED'
            RETURNING *
            """,
            (payment_id, user_id),
        ).fetchone()


async def list_active_crypto_payments(limit: int = 200) -> list[dict]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT *
            FROM crypto_payments
            WHERE status NOT IN ('paid', 'cancelled')
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()


async def list_pending_platega_payments(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT *
            FROM platega_payments
            WHERE status NOT IN ('CONFIRMED', 'CANCELLED')
            ORDER BY created_at
            LIMIT %s
            """,
            (limit,),
        ).fetchall()


async def complete_platega_payment(payment_id: int, username: str = "", status: str = "CONFIRMED") -> dict | None:
    with get_conn() as conn:
        payment = conn.execute(
            "SELECT * FROM platega_payments WHERE id = %s FOR UPDATE",
            (payment_id,),
        ).fetchone()
        if not payment:
            return None
        if payment["status"] == "CONFIRMED":
            return None

        if payment["purpose"] == "topup":
            conn.execute(
                "UPDATE users SET balance = balance + %s WHERE id = %s",
                (payment["amount_rub"], payment["user_id"]),
            )
            conn.execute(
                """
                INSERT INTO transactions (user_id, type, amount, description)
                VALUES (%s, %s, %s, %s)
                """,
                (payment["user_id"], "topup", payment["amount_rub"], "Platega top-up"),
            )
        elif payment["purpose"] in {"order", "bulk_order"}:
            sale_usd = snapshot_sale_usd(conn, payment["product_code"], payment["amount_rub"], payment["amount_usd"])
            order = conn.execute(
                """
                INSERT INTO orders (user_id, username, product_code, product_title, price_rub, sale_usd, contact, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    payment["user_id"],
                    username,
                    payment["product_code"],
                    payment["product_title"],
                    payment["amount_rub"],
                    sale_usd,
                    payment["contact"],
                    "Оплачен Platega, ожидает обработки",
                ),
            ).fetchone()
            order_id = order["id"]
            conn.execute(
                """
                INSERT INTO transactions (user_id, type, amount, description)
                VALUES (%s, %s, %s, %s)
                """,
                (payment["user_id"], "platega_payment", payment["amount_rub"], f"Platega: {payment['product_title']}"),
            )
        else:
            order_id = payment["order_id"]

        return conn.execute(
            """
            UPDATE platega_payments
            SET status = %s,
                paid_at = now(),
                order_id = COALESCE(%s, order_id)
            WHERE id = %s
            RETURNING *
            """,
            (status, order_id if "order_id" in locals() else None, payment_id),
        ).fetchone()


async def admin_stats() -> dict:
    with get_conn() as conn:
        users = conn.execute("SELECT count(*) AS count FROM users").fetchone()["count"]
        orders = conn.execute("SELECT count(*) AS count FROM orders").fetchone()["count"]
        links = conn.execute("SELECT count(*) AS count FROM links WHERE is_issued = FALSE").fetchone()["count"]
    return {"users": users, "orders": orders, "links": links}


async def daily_business_stats() -> dict:
    with get_conn() as conn:
        row = conn.execute(
            """
            WITH today AS (
                SELECT (now() AT TIME ZONE %s)::date AS day
            )
            SELECT
                today.day,
                COALESCE(count(orders.id), 0)::int AS orders_count,
                COALESCE(sum(orders.price_rub), 0) AS revenue_rub
            FROM today
            LEFT JOIN orders
                ON (orders.created_at AT TIME ZONE %s)::date = today.day
                AND orders.status <> 'Отменен'
                AND orders.price_rub > 0
                AND (%s = '' OR orders.user_id IS DISTINCT FROM %s::bigint)
            GROUP BY today.day
            """,
            (REPORT_TZ, REPORT_TZ, ADMIN_ID, ADMIN_ID or "0"),
        ).fetchone()
        orders = conn.execute(
            """
            SELECT
                orders.price_rub,
                orders.sale_usd,
                product_settings.price_rub AS product_price_rub,
                product_settings.price_usd AS product_price_usd
            FROM orders
            LEFT JOIN product_settings ON product_settings.code = orders.product_code
            WHERE (orders.created_at AT TIME ZONE %s)::date = (now() AT TIME ZONE %s)::date
                AND orders.status <> 'Отменен'
                AND orders.price_rub > 0
                AND (%s = '' OR orders.user_id IS DISTINCT FROM %s::bigint)
            """,
            (REPORT_TZ, REPORT_TZ, ADMIN_ID, ADMIN_ID or "0"),
        ).fetchall()
        issued_summary = conn.execute(
            """
            SELECT
                count(*)::int AS count,
                COALESCE(sum(purchase_cost_usd), 0) AS cost_usd
            FROM links
            LEFT JOIN orders ON orders.id = links.order_id
            WHERE is_issued = TRUE
                AND issued_at IS NOT NULL
                AND (%s = '' OR issued_to IS DISTINCT FROM %s::bigint)
                AND (COALESCE(orders.created_at, issued_at) AT TIME ZONE %s)::date = (now() AT TIME ZONE %s)::date
            """,
            (ADMIN_ID, ADMIN_ID or "0", REPORT_TZ, REPORT_TZ),
        ).fetchone()

    revenue_usd = Decimal("0")
    for order in orders:
        if order["sale_usd"] is not None:
            revenue_usd += Decimal(order["sale_usd"] or 0)
        else:
            price_rub = Decimal(order["product_price_rub"] or 0)
            price_usd = Decimal(order["product_price_usd"] or 0)
            if price_rub > 0:
                quantity = Decimal(order["price_rub"]) / price_rub
                revenue_usd += quantity * price_usd
    issued_links = issued_summary["count"]
    cost_usd = Decimal(issued_summary["cost_usd"])
    average_cost_usd = cost_usd / issued_links if issued_links else Decimal("0")
    profit_usd = revenue_usd - cost_usd
    return {
        "date": row["day"],
        "orders_count": row["orders_count"],
        "revenue_rub": row["revenue_rub"],
        "issued_links": issued_links,
        "price_usd": Decimal("0"),
        "cost_per_link_usd": average_cost_usd,
        "revenue_usd": revenue_usd,
        "cost_usd": cost_usd,
        "profit_usd": profit_usd,
    }


async def business_stats_by_days(days: int = 30) -> list[dict]:
    safe_days = max(1, min(days, 90))
    with get_conn() as conn:
        date_rows = conn.execute(
            """
            SELECT generate_series(
                (now() AT TIME ZONE %s)::date - (%s::int - 1),
                (now() AT TIME ZONE %s)::date,
                INTERVAL '1 day'
            )::date AS day
            ORDER BY day DESC
            """,
            (REPORT_TZ, safe_days, REPORT_TZ),
        ).fetchall()
        order_rows = conn.execute(
            """
            SELECT
                (orders.created_at AT TIME ZONE %s)::date AS day,
                orders.price_rub,
                orders.sale_usd,
                product_settings.price_rub AS product_price_rub,
                product_settings.price_usd AS product_price_usd
            FROM orders
            LEFT JOIN product_settings ON product_settings.code = orders.product_code
            WHERE (orders.created_at AT TIME ZONE %s)::date >= (now() AT TIME ZONE %s)::date - (%s::int - 1)
                AND orders.status <> 'Отменен'
                AND orders.price_rub > 0
                AND (%s = '' OR orders.user_id IS DISTINCT FROM %s::bigint)
            """,
            (REPORT_TZ, REPORT_TZ, REPORT_TZ, safe_days, ADMIN_ID, ADMIN_ID or "0"),
        ).fetchall()
        issued_rows = conn.execute(
            """
            SELECT
                (COALESCE(orders.created_at, links.issued_at) AT TIME ZONE %s)::date AS day,
                count(*)::int AS count,
                COALESCE(sum(links.purchase_cost_usd), 0) AS cost_usd
            FROM links
            LEFT JOIN orders ON orders.id = links.order_id
            WHERE is_issued = TRUE
                AND issued_at IS NOT NULL
                AND (COALESCE(orders.created_at, links.issued_at) AT TIME ZONE %s)::date >= (now() AT TIME ZONE %s)::date - (%s::int - 1)
                AND (%s = '' OR issued_to IS DISTINCT FROM %s::bigint)
            GROUP BY day
            """,
            (REPORT_TZ, REPORT_TZ, REPORT_TZ, safe_days, ADMIN_ID, ADMIN_ID or "0"),
        ).fetchall()

    stats = {
        row["day"]: {
            "date": row["day"],
            "orders_count": 0,
            "revenue_rub": Decimal("0"),
            "issued_links": 0,
            "revenue_usd": Decimal("0"),
            "cost_usd": Decimal("0"),
            "profit_usd": Decimal("0"),
            "cost_per_link_usd": Decimal("0"),
        }
        for row in date_rows
    }

    for order in order_rows:
        day = order["day"]
        if day not in stats:
            continue
        price_rub = Decimal(order["product_price_rub"] or 0)
        price_usd = Decimal(order["product_price_usd"] or 0)
        revenue_rub = Decimal(order["price_rub"] or 0)
        stats[day]["orders_count"] += 1
        stats[day]["revenue_rub"] += revenue_rub
        if order["sale_usd"] is not None:
            stats[day]["revenue_usd"] += Decimal(order["sale_usd"] or 0)
        elif price_rub > 0:
            stats[day]["revenue_usd"] += (revenue_rub / price_rub) * price_usd

    for issued in issued_rows:
        day = issued["day"]
        if day not in stats:
            continue
        stats[day]["issued_links"] = issued["count"]
        stats[day]["cost_usd"] = Decimal(issued["cost_usd"] or 0)

    for day_stats in stats.values():
        issued_links = day_stats["issued_links"]
        cost_usd = day_stats["cost_usd"]
        day_stats["profit_usd"] = day_stats["revenue_usd"] - cost_usd
        day_stats["cost_per_link_usd"] = cost_usd / issued_links if issued_links else Decimal("0")

    return list(stats.values())


async def recent_orders(limit: int = 20) -> list[dict]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT %s", (limit,)).fetchall()


async def list_users(limit: int | None = 100) -> list[dict]:
    with get_conn() as conn:
        limit_clause = "" if limit is None else "LIMIT %s"
        params = () if limit is None else (limit,)
        return conn.execute(
            f"""
            SELECT id, username, first_name, balance, language, ref_code, created_at
            FROM users
            ORDER BY created_at DESC
            {limit_clause}
            """,
            params,
        ).fetchall()


async def get_product_config(code: str = "gemini_link_18_month") -> dict:
    await ensure_schema()
    with get_conn() as conn:
        return conn.execute("SELECT * FROM product_settings WHERE code = %s", (code,)).fetchone()


async def list_product_configs() -> list[dict]:
    await ensure_schema()
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT *
            FROM product_settings
            ORDER BY
                CASE code
                    WHEN 'gemini_link_18_month' THEN 1
                    WHEN 'gpt_account_full_warranty' THEN 2
                    WHEN 'gemini_account_12_month' THEN 3
                    WHEN 'supergrok_1_month' THEN 4
                    ELSE 10
                END,
                title
            """
        ).fetchall()


async def update_product_config(
    code: str,
    title: str,
    price_rub: Decimal,
    price_usd: Decimal,
    description: str,
) -> dict:
    with get_conn() as conn:
        return conn.execute(
            """
            INSERT INTO product_settings (code, title, price_rub, price_usd, description, updated_at)
            VALUES (%s, %s, %s, %s, %s, now())
            ON CONFLICT (code) DO UPDATE
            SET title = EXCLUDED.title,
                price_rub = EXCLUDED.price_rub,
                price_usd = EXCLUDED.price_usd,
                description = EXCLUDED.description,
                updated_at = now()
            RETURNING *
            """,
            (code, title, price_rub, price_usd, description),
        ).fetchone()


async def get_bot_setting(key: str, default: str = "") -> str:
    await ensure_schema()
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM bot_settings WHERE key = %s", (key,)).fetchone()
        return str(row["value"]) if row else default


async def set_bot_setting(key: str, value: str) -> str:
    await ensure_schema()
    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO bot_settings (key, value, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value,
                updated_at = now()
            RETURNING value
            """,
            (key, value),
        ).fetchone()
        return str(row["value"])
