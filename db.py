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
            """
        )
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


async def complete_crypto_payment(payment_id: int, username: str, order_status: str) -> dict | None:
    with get_conn() as conn:
        payment = conn.execute(
            "SELECT * FROM crypto_payments WHERE id = %s FOR UPDATE",
            (payment_id,),
        ).fetchone()
        if not payment:
            return None
        if payment["status"] == "paid":
            return payment

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


async def admin_stats() -> dict:
    with get_conn() as conn:
        users = conn.execute("SELECT count(*) AS count FROM users").fetchone()["count"]
        orders = conn.execute("SELECT count(*) AS count FROM orders").fetchone()["count"]
        links = conn.execute("SELECT count(*) AS count FROM links WHERE is_issued = FALSE").fetchone()["count"]
    return {"users": users, "orders": orders, "links": links}


async def recent_orders(limit: int = 20) -> list[dict]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT %s", (limit,)).fetchall()


async def list_users(limit: int = 100) -> list[dict]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT id, username, first_name, balance, language, ref_code, created_at
            FROM users
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
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
