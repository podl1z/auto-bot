# auto-bot на Cloudflare Workers

Тот же бот, переписанный на TypeScript под Cloudflare Workers + D1. Бесплатный тариф, работает без своего компа и без VPS.

## Чем отличается от Python-версии

| | Python (`../bot/`) | Worker (эта папка) |
|---|---|---|
| Как получает сообщения | **Long polling** — сам дёргает Telegram | **Вебхук** — Telegram стучится к нам |
| Где живёт | Твой комп или VPS | Cloudflare, бесплатно |
| База | Файл `data/bot.db` | Cloudflare D1 |
| Язык | Python + aiogram | TypeScript + grammY |

Логика, команды и поведение — один в один. Мемы так же хранятся как `file_id` Telegram.

## ⚠️ Одновременно работать может только одна версия

Telegram отдаёт апдейты **либо** через polling, **либо** через вебхук. Как только ты сделаешь `/setup`, Python-версия перестанет получать сообщения (и начнёт сыпать `Conflict` в логи).

Перед деплоем **останови Python-бота** (Ctrl+C в его окне).

Вернуться обратно на Python: `curl "https://api.telegram.org/bot<ТОКЕН>/deleteWebhook"`, потом снова `python -m bot`.

## Деплой: по шагам

Всё делается из папки `worker/`.

### 1. Поставить зависимости

```bash
cd worker
npm install
```

### 2. Завести аккаунт Cloudflare и войти

```bash
npx wrangler login
```

Откроется браузер. Регистрация бесплатная, карта не нужна.

### 3. Создать базу D1

```bash
npx wrangler d1 create auto-bot
```

Команда напечатает блок с `database_id = "..."`. **Скопируй этот id в `wrangler.toml`** вместо `ЗАПОЛНИ_ПОСЛЕ_d1_create`.

### 4. Создать таблицы

```bash
npm run db:remote
```

### 5. Прописать секреты

```bash
npx wrangler secret put BOT_TOKEN        # токен от @BotFather
npx wrangler secret put ADMIN_IDS        # твой ID, например 12345678
npx wrangler secret put WEBHOOK_SECRET   # любая случайная строка, придумай сам
```

`WEBHOOK_SECRET` — это пароль, по которому воркер отличает запросы от Telegram от чужих. Сгенерировать можно так:

```bash
node -e "console.log(crypto.randomUUID())"
```

Секреты хранятся у Cloudflare и в репозиторий не попадают.

### 6. Задеплоить

```bash
npm run deploy
```

В конце получишь адрес вида `https://auto-bot.ТВОЙ-НИК.workers.dev`.

### 7. Включить вебхук

Открой в браузере (подставь свой адрес и свой `WEBHOOK_SECRET`):

```
https://auto-bot.ТВОЙ-НИК.workers.dev/setup?secret=ТВОЙ_WEBHOOK_SECRET
```

Должен ответить JSON вида `{"ok":true,"bot":"...","webhook":"..."}`. Это разом прописывает вебхук и меню команд.

### 8. Проверить

Напиши боту `/start` в Телеграме.

## Перенести мемы из Python-версии

Пул в D1 пустой — мемы, добавленные в локального бота, туда сами не переедут.

```bash
node tools/export-from-python.mjs
npx wrangler d1 execute auto-bot --remote --file=migrate.sql
```

Скрипт читает `../data/bot.db` и делает `migrate.sql` с мемами, настройками и триггерами.

## Полезное

```bash
npm test              # тесты (матчинг триггеров, подстановки в приветствии)
npm run typecheck     # проверка типов
npm run dev           # локальный запуск
npx wrangler tail     # живые логи задеплоенного воркера
```

## Если что-то не работает

- **Бот молчит.** Открой `https://api.telegram.org/bot<ТОКЕН>/getWebhookInfo` — там будет `last_error_message`, если Telegram не смог достучаться.
- **403 на `/setup`.** Секрет в ссылке не совпадает с тем, что положил в `wrangler secret put WEBHOOK_SECRET`.
- **Ошибки в работе.** `npx wrangler tail` показывает логи воркера в реальном времени.
- **Команд нет в меню.** Меню админа ставится при первом твоём сообщении боту — просто напиши ему что-нибудь.
