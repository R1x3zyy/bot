# Telegram store bot

Магазин в Telegram для товара `Gemini Link 18 months`.

## Состав проекта

- `bot.py` - Telegram-бот;
- `db.py` - подключение PostgreSQL и запросы;
- `admin.py` - FastAPI API для админки;
- `admin_frontend` - React-админка;
- `docker-compose.yml` - локальный PostgreSQL;
- `DEPLOYMENT.md` - GitLab, Vercel, Postgres и подключение к Telegram.

## Локальный запуск

1. Установи PostgreSQL или Docker Desktop.

```powershell
docker compose up -d
```

2. Создай `.env` по примеру `.env.example`.

3. Установи Python-зависимости:

```powershell
python -m pip install -r requirements.txt
```

4. Запусти API:

```powershell
uvicorn admin:app --host 127.0.0.1 --port 8000
```

5. В другом терминале запусти бота:

```powershell
python bot.py
```

6. Запусти React-админку:

```powershell
cd admin_frontend
npm install
npm run dev
```

Админка будет открываться на:

```text
http://127.0.0.1:5173
```

Подробная инструкция по деплою: [DEPLOYMENT.md](./DEPLOYMENT.md).

## CI/CD

В проект добавлены:

- GitHub Actions: `.github/workflows/deploy.yml`;
- GitLab CI: `.gitlab-ci.yml`;
- серверный deploy-скрипт: `scripts/deploy.sh`.

Для автодеплоя нужны secrets/variables:

```env
SERVER_HOST=194.154.27.196
SERVER_USER=root
SERVER_PASSWORD=пароль_сервера
SERVER_PORT=22
```
