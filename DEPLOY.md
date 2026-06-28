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
9. [Nginx + SSL-сертификат](#9-nginx--ssl-сертификат)
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

Вариант через git (рекомендуется):

```bash
# Установите git, если нужно
sudo apt install -y git

# Склонируйте репозиторий магазина
git clone https://github.com/ВАШ_АККАУНТ/ВАШ_РЕПОЗИТОРИЙ.git shop
cd shop
```

> Если репозиторий приватный — настройте SSH-ключ или используйте токен доступа.

---

## 5. Настройка .env (боевые ключи)

Создайте `.env` из шаблона и заполните **боевыми** значениями:

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
POSTGRES_PASSWORD=<надёжный_пароль>
DATABASE_URL=postgresql+asyncpg://postgres:<надёжный_пароль>@db:5432/shop

# ЮKassa — БОЕВЫЕ ключи рабочего магазина
YOOKASSA_SHOP_ID=<боевой_shop_id>
YOOKASSA_SECRET_KEY=<боевой_секретный_ключ>

# СДЭК — БОЕВОЙ режим
CDEK_API_URL=https://api.cdek.ru
CDEK_ACCOUNT=<боевой_account>
CDEK_SECURE_PASSWORD=<боевой_password>

# Почта
EMAILS_ENABLED=True
SMTP_PASSWORD=<пароль_ящика_info@epatajextra.ru>
```

> **Важно:** в `DATABASE_URL` для прода хост — `db` (имя сервиса в compose),
> а не `localhost`.

Сохраните: `Ctrl+O`, `Enter`, `Ctrl+X`.

---

## 6. Чек-лист безопасности перед запуском

Проверьте перед первым стартом — это критично для боевого сайта:

- [ ] `DEBUG=False` в `.env` (скрывает трейсбэки от посторонних)
- [ ] `ENVIRONMENT=production` (включает secure-cookie по HTTPS)
- [ ] `SECRET_KEY` — **новый**, сгенерированный (не из разработки)
- [ ] Пароль БД — надёжный, не из примеров
- [ ] Ключи ЮKassa — боевые (не тестовые `test_…`)
- [ ] Ключи СДЭК — боевые, `CDEK_API_URL=https://api.cdek.ru`
- [ ] Файл `.env` не попадёт в git (он уже в `.gitignore`)

---

## 7. Запуск приложения

Запускаем через продакшен-конфиг `docker-compose.prod.yml`:

```bash
# Собрать и поднять контейнеры в фоне
docker compose -f docker-compose.prod.yml up -d --build

# Применить миграции базы
docker compose -f docker-compose.prod.yml exec app alembic upgrade head

# Проверить, что всё поднялось
docker compose -f docker-compose.prod.yml ps
```

Приложение слушает `127.0.0.1:8000` (только локально — наружу его отдаст nginx).

**Создание первого администратора** — если в проекте есть скрипт создания
суперпользователя, выполните его; иначе зарегистрируйтесь на сайте и выдайте
себе права через базу (`is_superuser = true` для вашего пользователя).

---

## 8. Настройка поддомена (DNS)

В панели управления доменом `epatajextra.ru` (там, где он зарегистрирован)
добавьте **A-запись**:

| Тип | Имя (host) | Значение |
|-----|-----------|----------|
| A   | `shop`    | IP вашего VPS (например `123.45.67.89`) |

После этого `shop.epatajextra.ru` будет указывать на сервер магазина.
Обновление DNS занимает от нескольких минут до пары часов.

Проверить можно так:
```bash
ping shop.epatajextra.ru
```
(должен отвечать IP вашего VPS)

---

## 9. Nginx + SSL-сертификат

Nginx принимает запросы из интернета и передаёт их приложению на порт 8000.
SSL-сертификат (бесплатный, Let's Encrypt) включает https.

```bash
# Установка nginx и certbot
sudo apt install -y nginx certbot python3-certbot-nginx
```

Создайте конфиг сайта:
```bash
sudo nano /etc/nginx/sites-available/shop
```

Вставьте (домен уже подставлен):
```nginx
server {
    listen 80;
    server_name shop.epatajextra.ru;

    client_max_body_size 50M;  # для загрузки фото товаров

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Активируйте конфиг и получите SSL:
```bash
# Включить сайт
sudo ln -s /etc/nginx/sites-available/shop /etc/nginx/sites-enabled/
sudo nginx -t          # проверка конфига
sudo systemctl reload nginx

# Получить SSL-сертификат (certbot сам пропишет https в конфиг)
sudo certbot --nginx -d shop.epatajextra.ru
```

Certbot спросит email и согласие — ответьте, выберите редирект на https.
Сертификат продлевается автоматически.

---

## 10. Финальная проверка

Откройте в браузере `https://shop.epatajextra.ru` и проверьте:

- [ ] Сайт открывается по **https** (замок в адресной строке)
- [ ] Каталог, карточки товаров, корзина работают
- [ ] Оформление заказа: выбор города и пункта СДЭК на карте
- [ ] Тестовый заказ → оплата → приходит письмо «оплачен»
- [ ] Отслеживание заказа показывает статус СДЭК
- [ ] `https://shop.epatajextra.ru/robots.txt` отдаётся
- [ ] `https://shop.epatajextra.ru/sitemap.xml` отдаётся
- [ ] Админка `/admin` открывается и требует вход

**Подключите ЮKassa-вебхук:** в личном кабинете ЮKassa укажите URL для
уведомлений: `https://shop.epatajextra.ru/payments/webhook`
(точный путь — как настроен в коде платежей).

**Свяжите с лендингом:** на лендинге кнопки «Каталог / Магазин» направьте
на `https://shop.epatajextra.ru`.

**SEO:** добавьте сайт в Яндекс.Вебмастер и Google Search Console, укажите
адрес sitemap — поисковики начнут индексацию.

---

## 11. Обновление сайта в будущем

Когда вносите изменения в код (через git):

```bash
cd ~/shop
git pull                                            # забрать новый код
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec app alembic upgrade head
```

Если менялись только шаблоны/CSS — пересборка не обязательна, но не повредит.

---

## 12. Резервные копии

Регулярно делайте бэкап базы данных (заказы, товары, пользователи):

```bash
# Создать дамп базы
docker compose -f docker-compose.prod.yml exec db \
  pg_dump -U postgres shop > backup_$(date +%F).sql
```

Храните дампы вне сервера (скачивайте к себе). Можно настроить
автоматический бэкап по расписанию через cron.

**Восстановление из дампа:**
```bash
cat backup_2026-06-29.sql | docker compose -f docker-compose.prod.yml exec -T db \
  psql -U postgres shop
```

---

## Если что-то пошло не так

```bash
# Логи приложения
docker compose -f docker-compose.prod.yml logs app --tail 100

# Логи воркера (письма, фоновые задачи)
docker compose -f docker-compose.prod.yml logs worker --tail 100

# Логи nginx
sudo tail -50 /var/log/nginx/error.log

# Перезапустить приложение
docker compose -f docker-compose.prod.yml restart app
```

Частые причины проблем: незаполненный `.env`, не применены миграции,
DNS ещё не обновился, забыли открыть порты 80/443 в файрволе VPS.