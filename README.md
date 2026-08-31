# ⚡ NEONDROP — Full-Stack Django Gaming & Case Opening Platform

NEONDROP is a gaming platform inspired by CS:GO case opening platforms. Built with **Python 3.12+**, **Django 5+**, vanilla JavaScript, responsive CSS3 with cyberpunk neon aesthetics, and cryptographic Provably Fair algorithms.

---

## 📸 Features & Pages

1. **Главная страница (Home)**:
   - Неоновый интерактивный баннер и 3D арт кейса
   - Живая статистика платформы (124M+ кейсов, 1.35M+ пользователей, 258K+ контрактов, онлайн)
   - Популярные кейсы со светящимися градиентами
   - Таблица лидеров Top Winners
   - Блок «Как это работает?» из 4 шагов
   - Live Drops бегущая строка недавних выпадений
2. **Каталог кейсов (Cases)**:
   - Фильтрация по категориям (Все, Популярные, Новые, Доступные мне, Дорогие)
   - Поиск и диапазон цен
   - 8 уровней кейсов (Neon, Cyber, Galaxy, Frost, Demon, Godlike, Luxury, Supreme)
3. **Открытие кейса (CS:GO Roulette)**:
   - Реалистичная горизонтальная рулетка с лентой предметов и центральным указателем
   - Плавное замедление (cubic-bezier) и звуковые эффекты через Web Audio API
   - Определение выигрыша **строго на сервере** с защитой от накрутки
   - Модальное окно победы с возможностью моментально продать скин или забрать в инвентарь
4. **Инвентарь пользователя (Inventory)**:
   - Сетка выигранных скинов с цветовыми градиентами редкостей CS:GO
   - Кнопка моментальной продажи отдельных предметов или «Продать всё» с зачислением на баланс
5. **Профиль игрока (Profile)**:
   - Отображение ID, даты регистрации, баланса и аватара
   - История открытий с ценами и хэшами
6. **Апгрейды скинов (Upgrades)**:
   - Выбор исходного предмета из инвентаря и целевого скина из каталога
   - Динамический расчет шанса победы и анимация кругового спиннера
7. **Контракты обмена (Trade-Up Contracts)**:
   - Выбор от 3 до 10 скинов из инвентаря
   - Подсчет суммарной стоимости и крафт скина более высокой ценности
8. **Сражения кейсов (Case Battles)**:
   - 1v1 PvP против реальных игроков или мгновенная симуляция против NeonBot AI
9. **Пополнение баланса (Deposit)**:
   - Выбор суммы ($5, $10, $25, $50, $100, $250, $500)
   - Генерация ссылки на Telegram менеджера с предзаполненным сообщением
   - Административное подтверждение транзакций через Django Admin
10. **Доказуемая честность (Provably Fair)**:
    - Проверка хэша SHA-256 (Server Seed + Client Seed + Nonce)
11. **Мобильная версия (Mobile Responsive)**:
    - Фиксированная нижняя навигационная панель (`[Кейсы] [Апгрейд] [Контракты] [Инвентарь] [Профиль]`)
    - Адаптивная рулетка и сенсорные карточки скинов

---

## 🛠️ Стек технологий

- **Backend**: Python 3.12+, Django 5+
- **Database**: SQLite (для локальной разработки) / PostgreSQL (для production)
- **Frontend**: Django Templates, HTML5, CSS3 Glassmorphism/Neon UI, Vanilla JavaScript ES6+
- **Audio**: Web Audio API Synthesizer (без внешних аудио-файлов)
- **Security**: Django Auth, CSRF Protection, Atomic Transactions (`select_for_update`)

---

## 🚀 Быстрый старт и запуск

### 1. Клонирование / Переход в папку проекта

```bash
cd C:\Users\User\.gemini\antigravity\scratch\neondrop
```

### 2. Создание и активация виртуального окружения

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Windows (CMD):**
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

**Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 4. Применение миграций базы данных

```bash
python manage.py makemigrations users cases inventory payments upgrades contracts battles
python manage.py migrate
```

### 5. Заполнение демонстрационными данными (Кейсы, скины, пользователь Smoke)

```bash
python manage.py setup_demo_data
```

### 6. Запуск локального сервера разработки

```bash
python manage.py runserver
```

Сайт будет доступен по адресу:
👉 **http://127.0.0.1:8000/**

Панель администратора:
👉 **http://127.0.0.1:8000/admin/**

---

## 🔑 Учетные данные для входа (Demo Superuser)

Команда `setup_demo_data` автоматически создает суперпользователя со стартовым балансом из референса:

- **Логин**: `Smoke`
- **Пароль**: `neondrop123`
- **Баланс**: `$1243.56`
- **Статус**: Администратор / Суперпользователь

Вы также можете зарегистрировать любого нового пользователя через форму `/users/register/` — каждому новому пользователю автоматически начисляется приветственный баланс **$100.00** для тестирования всех кейсов и механик.

---

## ⚙️ Настройка Telegram для пополнений

В файле `config/settings.py` укажите свой Telegram-юзернейм:

```python
TELEGRAM_BOT_USERNAME = 'neondrop_admin'
```

При нажатии «Пополнить через Telegram» формируется ссылка:
`https://t.me/neondrop_admin?text=...`

Администратор может подтвердить платеж в админке Django:
- Перейти в **Админ-панель -> Транзакции / Пополнения**
- Выбрать нужные транзакции
- В выпадающем меню действий выбрать **«✓ Подтвердить выбранные транзакции (Зачислить баланс)»** -> Нажать «Выполнить».

---

## 🗄️ Подключение PostgreSQL для Production

В файле `config/settings.py` раскомментируйте секцию PostgreSQL:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'neondrop'),
        'USER': os.environ.get('DB_USER', 'postgres'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'postgres'),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}
```
