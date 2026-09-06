# 🛡️ NEONDROP — РУКОВОДСТВО ПО BACKUP, RESTORE И БЕЗОПАСНОЙ МИГРАЦИИ

> **Главная цель**: Гарантия **100% сохранения данных (Zero Data Loss)** при смене домена, сервера, хостинга (Render, VPS, Railway, Hetzner, AWS) или провайдера базы данных (PostgreSQL / SQLite).

---

## 📋 Содержание
1. [Что входит в полный бэкап](#1-что-входит-в-полный-бэкап)
2. [Где физически хранятся данные](#2-где-физически-хранятся-данные)
3. [Как создать Backup базы данных и медиа](#3-как-создать-backup)
4. [Как восстановить данные (Restore)](#4-как-восстановить-данные-restore)
5. [Верификация целостности данных (0 Data Loss)](#5-верификация-целостности-данных)
6. [Пошаговый перенос проекта на новый хостинг / VPS / Render](#6-пошаговый-перенос-на-новый-хостинг)
7. [Безопасная смена домена](#7-безопасная-смена-домена)
8. [Безопасность паролей и секретных ключей](#8-безопасность-паролей-и-секретов)

---

## 1. Что входит в полный бэкап

При экспорте и миграции полностью сохраняются все таблицы и связи:

| Категория | Модели Django | Сохраняемые данные |
|---|---|---|
| **Пользователи** | `auth.User`, `users.Profile` | ID, логины, email, **хэши паролей (PBKDF2)**, балансы `$`, выигрыши, аватары, Telegram-аккаунты, даты регистрации. |
| **Каталог кейсов** | `cases.Category`, `cases.Item`, `cases.Case`, `cases.CaseItem` | Все скины (редкость, цвет, цены, SVG/PNG ID), кейсы (темы, цены, баннеры, статус активности), веса и вероятности дропа (`CaseItem`). |
| **Инвентарь** | `inventory.InventoryItem` | Владелец, предмет, статус (в наличии / продан), цена продажи, дата продажи, источник получения (кейс, апгрейд, контракт, битва). |
| **Финансовый Ledger** | `payments.Transaction` | Депозиты, открытия кейсов, продажи предметов, апгрейды, контракты, промо-бонусы, баланс до/после, статусы, IP-адреса, idempotency keys. |
| **История дропов** | `cases.Opening` | Все открытия, выпавшие предметы, цены, Provably Fair хэши (Server Seed, Client Seed, Nonce). |
| **Промокоды & Бонусы** | `cases.PromoCode`, `cases.PromoCodeUse`, `cases.UserFreeOpening` | Коды, лимиты, счетчики использований (например, 50/100), сроки действия, история активаций конкретными пользователями, начисленные бесплатные открытия. |
| **Персональные шансы** | `cases.PersonalCaseChance` | Персональные подкрутки/бонусы для конкретных пользователей, даты активности, процент шанса. |
| **Мини-игры** | `upgrades.UpgradeAttempt`, `contracts.Contract`, `contracts.ContractInputItem`, `battles.Battle`, `battles.BattlePlayer`, `battles.BattleRound` | История апгрейдов, контрактов крафта и битв кейсов с раундами и победителями. |
| **Медиафайлы** | `MEDIA_ROOT` (`media/`) | Загруженные аватары (`avatars/`), изображения кейсов (`cases/`), пользовательские загрузки. |

---

## 2. Где физически хранятся данные

1. **База данных**:
   - **Production (Render / VPS)**: PostgreSQL через переменную `DATABASE_URL`.
   - **Development (локально)**: SQLite (`db.sqlite3`).
2. **Медиафайлы**:
   - Каталог `media/` в корне проекта (или постоянный диск Render Persistent Disk / AWS S3 / Cloudflare R2).
3. **Резервные копии**:
   - Каталог `backups/database/` — JSON-дампы и PostgreSQL `.dump` файлы.
   - Каталог `backups/media/` — `.tar.gz` архивы медиафайлов.
   - *Каталог `backups/` и `.env` автоматически исключены из Git через `.gitignore`.*

---

## 3. Как создать Backup

### Вариант А. Через Django Management Commands (Универсально: Windows / Linux / Render)

#### 1. Бэкап базы данных (JSON со всеми связями и SHA256):
```bash
python manage.py backup_data
```
*Сжатый вариант (.json.gz):*
```bash
python manage.py backup_data --compress
```

#### 2. Бэкап медиафайлов:
```bash
python manage.py backup_media
```

---

### Вариант Б. Через готовые скрипты

#### В Linux / macOS / Render Web Shell:
```bash
# Бэкап базы:
./scripts/backup_database.sh

# Бэкап медиа:
./scripts/backup_media.sh

# Нативный PostgreSQL pg_dump (если задан DATABASE_URL):
./scripts/export_pg_dump.sh
```

#### В Windows PowerShell:
```powershell
# Бэкап базы:
.\scripts\backup_database.ps1

# Бэкап медиа:
.\scripts\backup_media.ps1
```

---

## 4. Как восстановить данные (Restore)

### 1. Восстановление базы данных:
```bash
python manage.py restore_data backups/database/neondrop_db_YYYYMMDD_HHMMSS.json --clean
```
*Что делает флаг `--clean`*: безопасным образом очищает существующие таблицы в обратном порядке внешних ключей и загружает точную копию из бэкапа. Во время восстановления сигналы создания профилей автоматически отключаются для исключения дубликатов.

### 2. Восстановление медиафайлов:
```bash
python manage.py restore_media backups/media/neondrop_media_YYYYMMDD_HHMMSS.tar.gz
```

---

## 5. Верификация целостности данных

После любого восстановления или перед переключением DNS выполните команду аудита:

```bash
python manage.py verify_migration --compare backups/database/neondrop_db_YYYYMMDD_HHMMSS.json
```

Команда сверит количество записей в каждой таблице и выведет статус:
```text
======================================================================
 [COMPARISON AUDIT] Validating against: neondrop_db_20260906.json
======================================================================
 MODEL                          |   BACKUP | CURRENT DB | STATUS    
----------------------------------------------------------------------
 auth.User                      |      250 |        250 | MATCH [OK]
 users.Profile                  |      250 |        250 | MATCH [OK]
 cases.Item                     |       27 |         27 | MATCH [OK]
 cases.Case                     |        8 |          8 | MATCH [OK]
 inventory.InventoryItem        |     1240 |       1240 | MATCH [OK]
 payments.Transaction           |     3100 |       3100 | MATCH [OK]
 cases.PromoCode                |       15 |         15 | MATCH [OK]
======================================================================
 [VERIFICATION PASSED] ZERO DATA LOSS CONFIRMED: 100% Records Match!
```

---

## 6. Пошаговый перенос на новый хостинг

### Этап 1: На СТАРОМ сервере
1. Приостановите внесение изменений (или включите Maintenance Mode).
2. Создайте свежие копии базы и медиа:
   ```bash
   python manage.py backup_data --output backups/database/final_migration_db.json
   python manage.py backup_media --output backups/media/final_migration_media.tar.gz
   ```
3. Скачайте эти 2 файла на свой компьютер через SCP / SFTP / Render Shell.

### Этап 2: На НОВОМ сервере (VPS / Railway / Hetzner / Новый Render)
1. Склонируйте репозиторий:
   ```bash
   git clone https://github.com/hayotbek003/neondrop.git
   cd neondrop
   ```
2. Создайте и заполните `.env` файл из `.env.example`:
   ```bash
   cp .env.example .env
   nano .env
   ```
   *Укажите новый `DATABASE_URL`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`.*
3. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```
4. Примените базовые миграции структуры:
   ```bash
   python manage.py migrate
   ```
5. Загрузите файлы `final_migration_db.json` и `final_migration_media.tar.gz` на новый сервер и выполните restore:
   ```bash
   python manage.py restore_data final_migration_db.json --clean
   python manage.py restore_media final_migration_media.tar.gz
   ```
6. Проверьте целостность переноса:
   ```bash
   python manage.py verify_migration --compare final_migration_db.json
   ```
7. Соберите статику:
   ```bash
   python manage.py collectstatic --noinput
   ```
8. Запустите production-сервер (Gunicorn / Uvicorn):
   ```bash
   gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 4
   ```

---

## 7. Безопасная смена домена

Модели NEONDROP (`User`, `InventoryItem`, `Case`, `Transaction`) **не содержат жестко зашитых доменов** в базе данных.

Для смены домена (например, с `neondrop-ujly.onrender.com` на `neondrop.gg`):

1. В `.env` на новом/текущем сервере обновите 2 переменные:
   ```env
   DJANGO_ALLOWED_HOSTS=neondrop.gg,www.neondrop.gg,localhost,127.0.0.1
   DJANGO_CSRF_TRUSTED_ORIGINS=https://neondrop.gg,https://www.neondrop.gg
   ```
2. Перезапустите приложение (`gunicorn` / перезапуск сервиса Render).
3. Привяжите домен в DNS (`A` запись на IP сервера или `CNAME` на хостинг).
4. Выпустите SSL сертификат (Let's Encrypt / Cloudflare SSL).

Все пользователи останутся в системе, балансы и инвентари сохранятся на 100%.

---

## 8. Безопасность паролей и секретов

- **Пароли пользователей**: Хранятся исключительно в виде стандартных хэшей Django (`pbkdf2_sha256$...`). При экспорте в JSON переносится хэш строки, поэтому **открытые пароли нигде не фигурируют**, а старые пароли пользователей продолжают работать сразу после восстановления на новом сервере.
- **Секретные ключи**: Никогда не сохраняются в Git и дампы. Все секреты (`DJANGO_SECRET_KEY`, пароли от БД, API токены) передаются строго через переменные окружения `.env`.
