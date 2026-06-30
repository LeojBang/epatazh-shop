# Деплой магазина «Эпатаж» на сервер

Пошаговая инструкция по развёртыванию магазина на отдельном VPS под
поддоменом `shop.epatajextra.ru`. Лендинг (`epatajextra.ru`) остаётся
на своём сервере и не затрагивается — сайты связываются ссылками.

> **Время на весь деплой:** ориентировочно 1–2 часа.
> Делайте по шагам сверху вниз, не пропуская.

---

## Содержание

1. [Что понадобится](#1-что-понадобится)
2. [Аренда и подготовка сервера](#2-аренда-и-подготовка-сервера)
3. [Установка Docker](#3-установка-docker)
4. [Загрузка кода](#4-загрузка-кода)
5. [Настройка .env (боевые ключи)](#5-настройка-env-боевые-ключи)
6. [Чек-лист безопасности перед запуском](#6-чек-лист-безопасности-перед-запуском)
7. [Запуск приложения](#7-запуск-приложения)
8. [Настройка поддомена (DNS)](#8-настройка-поддомена-dns)
9. [Nginx + SSL-сертификат + рейт-лимит](#9-nginx--ssl-сертификат--рейт-лимит)
10. [Финальная проверка](#10-финальная-проверка)
11. [Обновление сайта в будущем](#11-обновление-сайта-в-будущем)
12. [Резервные копии](#12-резервные-копии)

---

## 1. Что понадобится

- **VPS** с Ubuntu 22.04 или новее, минимум **2 ГБ RAM** (магазину нужно
  держать PostgreSQL + Redis + приложение + воркер). Бесплатный VPS не подойдёт.
  Подойдёт, например, тариф у reg.ru, Timeweb или Selectel (~300–500 ₽/мес).
- **Доступ к DNS** домена `epatajextra.ru` (там, где он зарегистрирован).
- **Боевые ключи:** ЮKassa (рабочий магазин), СДЭК (после договора),
  пароль почтового ящика `info@epatajextra.ru`.

---

## 2. Аренда и подготовка сервера

1. Арендуйте VPS (Ubuntu, ≥2 ГБ RAM). Провайдер пришлёт IP-адрес и пароль root.

2. Подключитесь по SSH (замените `123.45.67.89` на ваш IP):
   ```bash
   ssh root@123.45.67.89
   ```

3. Обновите систему:
   ```bash
   apt update && apt upgrade -y
   ```

4. (Рекомендуется) Создайте отдельного пользователя вместо root:
   ```bash
   adduser deploy
   usermod -aG sudo deploy
   su - deploy
   ```

---

## 3. Установка Docker

```bash
# Установка Docker + compose-плагина
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER

# Перелогиньтесь, чтобы группа docker применилась
exit
# затем снова: ssh deploy@123.45.67.89

# Проверка
docker --version
docker compose version
```

---

## 4. Загрузка кода

```bash
sudo apt install -y git

git clone https://github.com/ВАШ_АККАУНТ/ВАШ_РЕПОЗИТОРИЙ.git shop
cd shop
```

> Если репозиторий приватный — настройте SSH-ключ или используйте токен доступа.

---

## 5. Настройка .env (боевые ключи)

```bash
cp .env.example .env
nano .env
```

Обязательно укажите для продакшена:

```ini
ENVIRONMENT=production
DEBUG=False

# Сгенерируйте НОВЫЙ секретный ключ:
#   python3 -c "import secrets; print(secrets.token_urlsafe(48))"
SECRET_KEY=<новый_сгенерированный_ключ>

# База данных (пароль придумайте надёжный)
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<надёжный_пароль>
POSTGRES_DB=shop
DATABASE_URL=postgresql+asyncpg://postgres:<надёжный_пароль>@db:5432/shop

# ЮKassa — БОЕВЫЕ ключи рабочего магазина
YOOKASSA_SHOP_ID=<боевой_shop_id>
YOOKASSA_SECRET_KEY=<боевой_секретный_ключ>

# Система налогообложения: 1 = без НДС (УСН), 3 = НДС 10%, 4 = НДС 20%
RECEIPT_VAT_CODE=1

# СДЭК — БОЕВОЙ режим
CDEK_API_URL=https://api.cdek.ru
CDEK_ACCOUNT=<боевой_account>
CDEK_SECURE_PASSWORD=<боевой_password>

# Почта
EMAILS_ENABLED=True
SMTP_USER=info@epatajextra.ru
SMTP_FROM=info@epatajextra.ru
SMTP_PASSWORD=<пароль_ящика>
```

> **Важно:** в `DATABASE_URL` хост — `db` (имя сервиса в compose), не `localhost`.

Сохраните: `Ctrl+O`, `Enter`, `Ctrl+X`.

---

## 6. Чек-лист безопасности перед запуском

- [ ] `DEBUG=False` в `.env`
- [ ] `ENVIRONMENT=production` (включает secure-cookie по HTTPS и валидацию конфига при старте)
- [ ] `SECRET_KEY` — новый, сгенерированный (минимум 32 символа, не из разработки)
- [ ] Пароль БД — надёжный, не из примеров
- [ ] Ключи ЮKassa — боевые (не тестовые `test_…`)
- [ ] `RECEIPT_VAT_CODE` уточнён (УСН → 1)
- [ ] Ключи СДЭК — боевые, `CDEK_API_URL=https://api.cdek.ru`
- [ ] `EMAILS_ENABLED=True`, SMTP-пароль заполнен
- [ ] Файл `.env` не попадёт в git (он уже в `.gitignore`)

---

## 7. Запуск приложения

```bash
# Собрать образы и поднять все сервисы
docker compose -f docker-compose.prod.yml up -d --build
```

**Миграции запускаются автоматически** — сервис `migrate` прогонит
`alembic upgrade head` и создаст все таблицы перед стартом приложения.
`app` и `worker` стартуют только после успешного завершения миграций.

Проверьте что всё поднялось:
```bash
docker compose -f docker-compose.prod.yml ps
```

Должны быть запущены: `app` (healthy), `worker`, `db`, `redis`.
Сервис `migrate` завершится с кодом 0 — это нормально.

**Создание первого администратора** (один раз):
```bash
docker compose -f docker-compose.prod.yml exec app python create_admin.py
```

---

## 8. Настройка поддомена (DNS)

В панели управления доменом `epatajextra.ru` добавьте **A-запись**:

| Тип | Имя (host) | Значение |
|-----|-----------|----------|
| A   | `shop`    | IP вашего VPS |

Проверить:
```bash
ping shop.epatajextra.ru
# должен отвечать IP вашего VPS
```

Обновление DNS занимает от нескольких минут до пары часов.

---

## 9. Nginx + SSL-сертификат + рейт-лимит

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

### 9.1 Зоны рейт-лимита

```bash
sudo nano /etc/nginx/conf.d/rate_limits.conf
```

Вставьте:
```nginx
# 5 запросов/минуту с IP — для регистрации и входа
limit_req_zone $binary_remote_addr zone=auth:1m rate=5r/m;

# 30 запросов/минуту с IP — для вебхуков (ЮKassa и СДЭК шлют повторы)
limit_req_zone $binary_remote_addr zone=webhooks:1m rate=30r/m;
```

### 9.2 Конфиг сайта

```bash
sudo nano /etc/nginx/sites-available/shop
```

Вставьте:
```nginx
server {
    listen 80;
    server_name shop.epatajextra.ru;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name shop.epatajextra.ru;

    # SSL — certbot пропишет эти строки сам (шаг 9.3)
    # ssl_certificate     /etc/letsencrypt/live/shop.epatajextra.ru/fullchain.pem;
    # ssl_certificate_key /etc/letsencrypt/live/shop.epatajextra.ru/privkey.pem;

    client_max_body_size 50M;

    # Регистрация и вход: 5 запросов/минуту с IP
    location ~ ^/(register|login) {
        limit_req zone=auth burst=5 nodelay;
        limit_req_status 429;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Вебхук ЮKassa
    location /payments/webhook {
        limit_req zone=webhooks burst=10 nodelay;
        limit_req_status 429;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Вебхук СДЭК
    location /api/cdek/webhook {
        limit_req zone=webhooks burst=10 nodelay;
        limit_req_status 429;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Все остальные запросы
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 9.3 Активация и SSL

```bash
sudo ln -s /etc/nginx/sites-available/shop /etc/nginx/sites-enabled/
sudo nginx -t          # должно быть "syntax is ok"
sudo systemctl reload nginx

# SSL-сертификат (certbot сам пропишет https в конфиг и настроит автопродление)
sudo certbot --nginx -d shop.epatajextra.ru
```

---

## 10. Финальная проверка

### Подключите ЮKassa-вебхук

В ЛК ЮKassa (раздел «Интеграция → HTTP-уведомления»):
```
https://shop.epatajextra.ru/payments/webhook
```

### Зарегистрируйте вебхук СДЭК (один раз)

```bash
docker compose -f docker-compose.prod.yml exec app \
    python -m app.scripts.register_cdek_webhook
```

Проверить что подписка создана:
```bash
docker compose -f docker-compose.prod.yml exec app \
    python -m app.scripts.register_cdek_webhook --list
```

Если нужно отключить автоматические статусы:
```bash
# Узнать UUID подписки
docker compose -f docker-compose.prod.yml exec app \
    python -m app.scripts.register_cdek_webhook --list

# Удалить подписку
docker compose -f docker-compose.prod.yml exec app \
    python -m app.scripts.register_cdek_webhook --delete <uuid>

# В .env поменять и перезапустить
CDEK_AUTO_STATUS=false
docker compose -f docker-compose.prod.yml restart app
```

### Тестовый заказ

- [ ] Сайт открывается по **https** (замок в адресной строке)
- [ ] Каталог, карточки товаров, корзина работают
- [ ] Выбор города и ПВЗ СДЭК на карте работает
- [ ] Оформить заказ → оплатить тестовой картой ЮKassa
- [ ] Пришло письмо «заказ оплачен»
- [ ] В БД у заказа появился `cdek_order_uuid` (заказ создался в СДЭК)
- [ ] **Отменить тестовый заказ в ЛК СДЭК** (`lk.cdek.ru` → Заказы → Отмена)
- [ ] Админка `/admin` открывается и требует вход
- [ ] `https://shop.epatajextra.ru/robots.txt` отдаётся
- [ ] `https://shop.epatajextra.ru/sitemap.xml` отдаётся

### Свяжите с лендингом

На лендинге кнопки «Каталог / Магазин» направьте на `https://shop.epatajextra.ru`.

### SEO

Добавьте сайт в Яндекс.Вебмастер и Google Search Console, укажите адрес sitemap.

---

## 11. Обновление сайта в будущем

```bash
cd ~/shop
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

Миграции (если есть новые) применятся автоматически через сервис `migrate`.

> Если добавились новые переменные окружения — добавьте их в `.env` на сервере
> перед пересборкой, иначе приложение не запустится.

---

## 12. Резервные копии

```bash
# Создать дамп базы
docker compose -f docker-compose.prod.yml exec db \
  pg_dump -U postgres shop > backup_$(date +%F).sql
```

Храните дампы вне сервера (скачивайте к себе).

**Восстановление из дампа:**
```bash
cat backup_2026-07-01.sql | docker compose -f docker-compose.prod.yml exec -T db \
  psql -U postgres shop
```

---

## Если что-то пошло не так

```bash
# Логи приложения
docker compose -f docker-compose.prod.yml logs app --tail 100

# Логи миграций (если app не стартует)
docker compose -f docker-compose.prod.yml logs migrate --tail 50

# Логи воркера
docker compose -f docker-compose.prod.yml logs worker --tail 100

# Логи nginx
sudo tail -50 /var/log/nginx/error.log

# Перезапустить приложение
docker compose -f docker-compose.prod.yml restart app
```

Частые причины проблем: незаполненный `.env`, ошибка в миграциях (смотрите
`logs migrate`), DNS ещё не обновился, забыли открыть порты 80/443 в файрволе VPS.

---

## Изменения по сравнению с разработкой

- **CSRF-защита включена для всей админки** — все POST-формы защищены токеном
- **Ключи СДЭК** убраны из хардкода — теперь обязательны через `.env`
- **Slug товара** — дублирование показывает ошибку вместо 500
- **Удаление товара с отзывами** — отзывы удаляются автоматически (CASCADE)
- **Верификация СДЭК-вебхука** — статус перепроверяется через API СДЭК
- **Рейт-лимит** — nginx защищает `/register`, `/login`, `/payments/webhook`, `/api/cdek/webhook`
- **Миграции автоматические** — сервис `migrate` в compose прогоняет `alembic upgrade head` перед стартом
- **Продовый Docker-образ** — отдельный `Dockerfile.prod` с `requirements.prod.txt` без dev-зависимостей