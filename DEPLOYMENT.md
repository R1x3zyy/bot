# Deployment guide

## 1. PostgreSQL

Для продакшена лучше использовать hosted Postgres:

- Neon;
- Supabase;
- Railway Postgres;
- Render PostgreSQL.

После создания базы скопируй connection string в переменную:

```env
DATABASE_URL=postgresql://user:password@host:5432/database
```

Эту же строку нужно указать и для бота/API, и для админки API.

## 2. Backend API и бот

Бот сейчас работает через long polling:

```powershell
python bot.py
```

Такой процесс должен работать постоянно. Vercel для этого не подходит, потому что Vercel запускает serverless-функции на короткое время.

Нормальные варианты:

- Railway;
- Render Background Worker;
- VPS;
- Fly.io.

Переменные окружения для backend:

```env
BOT_TOKEN=токен_из_BotFather
ADMIN_ID=твой_telegram_id
DATABASE_URL=postgresql://user:password@host:5432/database
ADMIN_LOGIN=admin
ADMIN_PASSWORD=сложный_пароль
ADMIN_CORS_ORIGINS=https://твой-домен-на-vercel.vercel.app
```

API для React-админки запускается отдельно:

```powershell
uvicorn admin:app --host 0.0.0.0 --port 8000
```

Если хостинг поддерживает несколько процессов, запускай и `python bot.py`, и `uvicorn admin:app`.
Если нет, делай два сервиса: один для бота, второй для API.

## 3. React-админка на Vercel

Админка лежит в папке:

```text
admin_frontend
```

Локальный запуск:

```powershell
cd admin_frontend
npm install
npm run dev
```

Перед деплоем на Vercel укажи переменную:

```env
VITE_API_URL=https://адрес-твоего-backend-api
```

В Vercel:

1. New Project.
2. Import Git repository.
3. Root Directory: `admin_frontend`.
4. Framework Preset: Vite.
5. Build Command: `npm run build`.
6. Output Directory: `dist`.
7. Environment Variables: `VITE_API_URL`.
8. Deploy.

После деплоя скопируй Vercel-домен и добавь его в backend:

```env
ADMIN_CORS_ORIGINS=https://твой-домен-на-vercel.vercel.app
```

## 4. GitHub / GitLab

Перед загрузкой убедись, что `.env` не попадет в репозиторий. Он уже добавлен в `.gitignore`.

Для твоего GitHub-репозитория:

```powershell
git init
git add .
git commit -m "Add Telegram store bot with Postgres and React admin"
git branch -M main
git remote add origin https://github.com/R1x3zyy/bot.git
git push -u origin main
```

Если Git попросит логин и пароль:

- логин: `R1x3zyy`;
- пароль: GitHub personal access token, не обычный пароль от GitHub.

Для GitLab команды такие же, меняется только URL:

Команды:

```powershell
git init
git add .
git commit -m "Add Telegram store bot with Postgres and React admin"
git branch -M main
git remote add origin https://gitlab.com/USERNAME/REPOSITORY.git
git push -u origin main
```

Если хочешь, чтобы я сам залил проект, пришли:

- ссылку на пустой GitLab-репозиторий;
- GitLab personal access token с правом `write_repository`.

Токен лучше после загрузки удалить или перевыпустить.

## 5. Подключение к Telegram

1. Открой `@BotFather`.
2. Создай бота или выбери существующего.
3. Скопируй токен.
4. Укажи токен в переменной:

```env
BOT_TOKEN=токен_из_BotFather
```

5. Узнай свой Telegram ID командой `/myid` в боте.
6. Укажи:

```env
ADMIN_ID=твой_id
```

7. Запусти backend:

```powershell
python bot.py
```

После этого пользователь пишет боту `/start`, а данные пользователей, заказов, ссылок и профиля сохраняются в PostgreSQL.
