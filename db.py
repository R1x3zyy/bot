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
REPORT_TZ = os.getenv("REPORT_TZ", "Europe/Moscow")


@contextmanager
def get_conn():
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        yield conn


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
                is_issued BOOLEAN NOT NULL DEFAULT FALSE,
                issued_to BIGINT REFERENCES users(id) ON DELETE SET NULL,
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

            CREATE TABLE IF NOT EXISTS platega_payments (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                transaction_id TEXT NOT NULL UNIQUE,
                purpose TEXT NOT NULL,
                amount_rub NUMERIC(12, 2) NOT NULL,
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
        conn.execute(
            """
            INSERT INTO product_settings (code, title, price_rub, price_usd, description)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (code) DO NOTHING
            """,
            (
                "gemini_link_18_month",
                "Gemini Link 18 months",
                Decimal("145.00"),
                Decimal("2.00"),
                (
                    "Гарантийная поддержка распространяется на момент активации персональной ссылки.\n\n"
                    "Google AI Pro на 18 месяцев с доступом к возможностям Gemini, Veo, генерации изображений, "
                    "работе с документами, облачному хранилищу Google Drive 5 ТБ и расширенным лимитам.\n\n"
                    "Подписка подключается к вашему аккаунту по индивидуальной ссылке. "
                    "Логин и пароль передавать не нужно."
                ),
            ),
        )


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


async def add_links(links: list[str]) -> int:
    clean_links = []
    for line in links:
        match = URL_RE.search(line.strip())
        if match:
            clean_links.append(match.group(0))

    if not clean_links:
        return 0

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO links (url) VALUES (%s)", [(link,) for link in clean_links])
    return len(clean_links)


async def list_links(limit: int = 100) -> list[dict]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT id, url, is_issued, issued_to, created_at, issued_at
            FROM links
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()


async def delete_link(link_id: int) -> dict | None:
    with get_conn() as conn:
        return conn.execute("DELETE FROM links WHERE id = %s RETURNING *", (link_id,)).fetchone()


async def delete_available_links() -> int:
    with get_conn() as conn:
        rows = conn.execute("DELETE FROM links WHERE is_issued = FALSE RETURNING id").fetchall()
        return len(rows)


async def count_available_links() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT count(*) AS count FROM links WHERE is_issued = FALSE").fetchone()["count"]


async def issue_links_to_order(order_id: int, user_id: int, quantity: int, status: str = "Выдан") -> list[dict] | None:
    with get_conn() as conn:
        order = conn.execute(
            "SELECT issued_link_id FROM orders WHERE id = %s FOR UPDATE",
            (order_id,),
        ).fetchone()
        if not order or order["issued_link_id"]:
            return None

        links = conn.execute(
            """
            SELECT id, url
            FROM links
            WHERE is_issued = FALSE
            ORDER BY id
            LIMIT %s
            FOR UPDATE SKIP LOCKED
            """,
            (quantity,),
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
                issued_at = now()
            WHERE id = ANY(%s::bigint[])
            """,
            (user_id, link_ids),
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


async def create_order(
    user_id: int,
    username: str,
    product_code: str,
    product_title: str,
    price_rub: int,
    contact: str,
    status: str,
) -> dict:
    with get_conn() as conn:
        return conn.execute(
            """
            INSERT INTO orders (user_id, username, product_code, product_title, price_rub, contact, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (user_id, username, product_code, product_title, price_rub, contact, status),
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

        order = conn.execute(
            """
            INSERT INTO orders (user_id, username, product_code, product_title, price_rub, contact, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (user_id, username, product_code, product_title, price_rub, contact, status),
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
    product_code: str = "",
    product_title: str = "",
    quantity: int = 0,
    contact: str = "",
) -> dict:
    with get_conn() as conn:
        return conn.execute(
            """
            INSERT INTO crypto_payments (
                user_id, invoice_id, purpose, amount_rub, product_code, product_title, quantity, contact
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (user_id, invoice_id, purpose, amount_rub, product_code, product_title, quantity, contact),
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
            order = conn.execute(
                """
                INSERT INTO orders (user_id, username, product_code, product_title, price_rub, contact, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    payment["user_id"],
                    username,
                    payment["product_code"],
                    payment["product_title"],
                    payment["amount_rub"],
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


async def get_user_orders(user_id: int) -> list[dict]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM orders WHERE user_id = %s ORDER BY created_at", (user_id,)).fetchall()


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
    product_code: str = "",
    product_title: str = "",
    quantity: int = 0,
    contact: str = "",
) -> dict:
    with get_conn() as conn:
        return conn.execute(
            """
            INSERT INTO platega_payments (
                user_id, transaction_id, purpose, amount_rub, product_code, product_title, quantity, contact
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (user_id, transaction_id, purpose, amount_rub, product_code, product_title, quantity, contact),
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
            WHERE transaction_id = %s AND status <> 'CONFIRMED'
            RETURNING *
            """,
            (status, transaction_id),
        ).fetchone()


async def list_active_crypto_payments(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT *
            FROM crypto_payments
            WHERE status <> 'paid'
            ORDER BY created_at
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
            WHERE status <> 'CONFIRMED'
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
            order = conn.execute(
                """
                INSERT INTO orders (user_id, username, product_code, product_title, price_rub, contact, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    payment["user_id"],
                    username,
                    payment["product_code"],
                    payment["product_title"],
                    payment["amount_rub"],
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
        product = await get_product_config()
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
            GROUP BY today.day
            """,
            (REPORT_TZ, REPORT_TZ),
        ).fetchone()
        orders = conn.execute(
            """
            SELECT price_rub
            FROM orders
            WHERE (created_at AT TIME ZONE %s)::date = (now() AT TIME ZONE %s)::date
                AND status <> 'Отменен'
            """,
            (REPORT_TZ, REPORT_TZ),
        ).fetchall()
        issued_links = conn.execute(
            """
            SELECT count(*)::int AS count
            FROM links
            WHERE is_issued = TRUE
                AND issued_at IS NOT NULL
                AND (issued_at AT TIME ZONE %s)::date = (now() AT TIME ZONE %s)::date
            """,
            (REPORT_TZ, REPORT_TZ),
        ).fetchone()["count"]

    price_usd = Decimal(product["price_usd"])
    price_rub = Decimal(product["price_rub"])
    revenue_usd = Decimal("0")
    if price_rub > 0:
        for order in orders:
            quantity = Decimal(order["price_rub"]) / price_rub
            revenue_usd += quantity * price_usd
    cost_usd = PRODUCT_COST_USD * issued_links
    profit_usd = revenue_usd - cost_usd
    return {
        "date": row["day"],
        "orders_count": row["orders_count"],
        "revenue_rub": row["revenue_rub"],
        "issued_links": issued_links,
        "price_usd": price_usd,
        "cost_per_link_usd": PRODUCT_COST_USD,
        "revenue_usd": revenue_usd,
        "cost_usd": cost_usd,
        "profit_usd": profit_usd,
    }


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
