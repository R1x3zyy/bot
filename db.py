import os
from contextlib import contextmanager
from decimal import Decimal

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row


load_dotenv()


DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/gemini_store")


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
                Decimal("2.10"),
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


async def add_links(links: list[str]) -> int:
    clean_links = [link.strip() for link in links if link.strip()]
    if not clean_links:
        return 0

    with get_conn() as conn:
        conn.executemany("INSERT INTO links (url) VALUES (%s)", [(link,) for link in clean_links])
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


async def count_available_links() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT count(*) AS count FROM links WHERE is_issued = FALSE").fetchone()["count"]


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


async def update_order_status(order_id: int, status: str) -> dict | None:
    with get_conn() as conn:
        return conn.execute(
            "UPDATE orders SET status = %s WHERE id = %s RETURNING *",
            (status, order_id),
        ).fetchone()


async def get_user_orders(user_id: int) -> list[dict]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM orders WHERE user_id = %s ORDER BY created_at", (user_id,)).fetchall()


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
