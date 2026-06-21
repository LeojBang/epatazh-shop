# Чеклист развёртывания на сервере

Пошаговая инструкция для развёртывания магазина «Эпатаж» на production-сервере.
Выполнять по порядку. Отмечай галочками по мере выполнения.

---

## 0. Что понадобится заранее

- [ ] Арендованный VPS (Ubuntu 22.04+), минимум 2 ГБ RAM
- [ ] Доменное имя, направленное на IP сервера (A-запись)
- [ ] Боевой магазин в YooKassa с реальными ключами (shopId + секретный ключ)
- [ ] Доступ к серверу по SSH

> **Важно про секреты:** все боевые пароли и ключи генерируются заново
> и хранятся только в файле `.env` на сервере. Никогда не коммить их в git
> и не передавать в переписке.

---

## 1. Подготовка сервера

- [ ] Подключиться по SSH:
  ```bash
  ssh root@IP_СЕРВЕРА
  ```

- [ ] Обновить систему:
  ```bash
  apt update && apt upgrade -y
  ```

- [ ] Установить Docker и Docker Compose:
  ```bash
  curl -fsSL https://get.docker.com | sh
  ```

- [ ] Создать отдельного пользователя (не работать под root):
  ```bash
  adduser deploy
  usermod -aG docker,sudo deploy
  su - deploy
  ```

---

## 2. Загрузка кода

- [ ] Склонировать репозиторий (или загрузить код):
  ```bash
  git clone <адрес-репозитория> shop
  cd shop
  ```

---

## 3. Настройка переменных окружения

- [ ] Создать `.env` на основе шаблона:
  ```bash
  cp .env.example .env
  ```

- [ ] Сгенерировать новый секретный ключ:
  ```bash
  python3 -c "import secrets; print(secrets.token_urlsafe(48))"
  ```

- [ ] Заполнить `.env` боевыми значениями:
  - `ENVIRONMENT=production`
  - `DEBUG=False`
  - `SECRET_KEY=` — сгенерированный выше ключ
  - `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` — новый надёжный пароль БД
  - `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY` — боевые ключи из ЛК YooKassa
  - `DATABASE_URL` и `REDIS_URL` — как в шаблоне (внутренние адреса Docker)

---

## 4. Запуск контейнеров

- [ ] Собрать и поднять production-конфигурацию:
  ```bash
  docker compose -f docker-compose.prod.yml up -d --build
  ```

- [ ] Проверить, что все контейнеры поднялись:
  ```bash
  docker compose -f docker-compose.prod.yml ps
  ```

---

## 5. Инициализация базы данных

- [ ] Применить миграции:
  ```bash
  docker compose -f docker-compose.prod.yml exec app alembic upgrade head
  ```

- [ ] Создать стартовые категории (безопасный seed, не удаляет данные):
  ```bash
  docker compose -f docker-compose.prod.yml exec app python3 seed_prod.py
  ```

- [ ] Создать администратора:
  ```bash
  docker compose -f docker-compose.prod.yml exec app python3 create_admin.py
  ```

> Тестовый `seed.py` на проде запускать НЕЛЬЗЯ — он удаляет данные
> и защищён предохранителем (`ENVIRONMENT=production`).

---

## 6. Nginx + HTTPS

Приложение слушает только `127.0.0.1:8000`. Наружу его отдаёт nginx с HTTPS.

- [ ] Установить nginx и certbot:
  ```bash
  sudo apt install -y nginx certbot python3-certbot-nginx
  ```

- [ ] Создать конфиг nginx для домена (проксирование на 127.0.0.1:8000),
  указать `client_max_body_size` для загрузки фото (например 10M),
  и передавать заголовки `X-Forwarded-For` и `X-Forwarded-Proto`.

- [ ] Получить SSL-сертификат:
  ```bash
  sudo certbot --nginx -d вашдомен.ru -d www.вашдомен.ru
  ```

- [ ] Проверить автопродление сертификата:
  ```bash
  sudo certbot renew --dry-run
  ```

---

## 7. Настройка YooKassa

- [ ] В личном кабинете YooKassa указать URL для webhook:
  ```
  https://вашдомен.ru/payments/webhook
  ```

- [ ] Проверить, что в `.env` боевые ключи (не тестовые `test_...`).

---

## 8. Важные доработки под прод

Эти изменения в коде нужно внести перед боевым запуском:

- [ ] **Чтение реального IP за nginx.** В роуте логина (`app/users/router.py`)
  для rate limiting сейчас используется `request.client.host`. За nginx все
  запросы придут с одного IP. Нужно читать IP из заголовка `X-Forwarded-For`,
  иначе блокировка одного перебора заблокирует всех пользователей.

- [ ] **Том для загруженных фото.** Папка `app/static/uploads/` должна
  переживать пересборку образа. Добавить именованный том для неё
  в `docker-compose.prod.yml`, иначе при обновлении кода фото пропадут.

- [ ] **Sentry (опционально).** Подключить отлов ошибок для мониторинга
  на проде — узнавать о сбоях до того, как пожалуется покупатель.

---

## 9. Проверка после запуска

- [ ] Сайт открывается по HTTPS, замок в браузере зелёный
- [ ] Главная, каталог, страница товара загружаются
- [ ] Регистрация и вход работают
- [ ] Добавление в корзину и оформление заказа проходят
- [ ] Тестовая оплата проходит, webhook возвращает статус «Оплачен»
- [ ] Админ-панель доступна, вход только для суперпользователя
- [ ] Загрузка фото товара работает
- [ ] Healthcheck отвечает: `https://вашдомен.ru/health`

---

## 10. Обслуживание

```bash
# Логи приложения
docker compose -f docker-compose.prod.yml logs --since 10m app

# Перезапуск после обновления кода
git pull
docker compose -f docker-compose.prod.yml up -d --build

# Резервная копия базы данных
docker compose -f docker-compose.prod.yml exec db \
  pg_dump -U ПОЛЬЗОВАТЕЛЬ ИМЯ_БД > backup_$(date +%F).sql
```

- [ ] Настроить регулярные резервные копии базы данных
- [ ] Настроить мониторинг доступности сайта