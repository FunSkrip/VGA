
---

# Video Segmentation Analytics (VGA)

**Video Segmentation Analytics (VGA)** — это веб-приложение для детекции и аналитики объектов на видео с использованием нейронных сетей **YOLOv8**.

---

## 🚀 Возможности

- Загрузка видео для анализа
- Детекция объектов на видео с помощью модели YOLO
- Отображение результатов в браузере
- Аутентификация пользователей (регистрация/вход/выход)
- Удобный адаптивный интерфейс на **Bootstrap 5.3**
- Сообщения об ошибках и уведомления для пользователей

---

## 🛠️ Стек технологий

- Backend: **Python**, **Flask**
- Frontend: **HTML5**, **CSS3**, **Bootstrap 5.3**
- Нейронные сети: **YOLOv8** (Ultralytics)
- Хранилище файлов: **Файловая система**
- Аутентификация: **Flask-Login**
- Прочее: **Flask-WTF**, **WTForms**

---

## 📦 Установка проекта

1. Клонировать репозиторий:

```bash
git clone https://github.com/FunSkrip/vga.git
cd vga
```

2. Создать виртуальное окружение:

```bash
python -m venv venv
source venv/bin/activate  # Linux / macOS
venv\Scripts\activate     # Windows
```

3. Установить зависимости:

```bash
pip install -r requirements.txt
```

4. Скачать веса модели YOLO:

- Для YOLOv8:

```python
from ultralytics import YOLO
model = YOLO('yolov8n.pt')  # или yolov8s.pt / yolov8m.pt / yolov8l.pt
```

5. Применить миграции БД:

```bash
flask --app run.py db upgrade
```

6. Запустить приложение:

```bash
flask --app run.py run
```

---

## 📂 Структура проекта

```plaintext
vga/
├── app/
│   ├── static/
│   │   ├── css/
│   │   ├── img/
│   │   └── js/
│   ├── templates/
│   ├── routes/
│   ├── models/
│   ├── forms/
│   ├── detector.py
│   └── extensions.py
├── requirements.txt
├── config.py
├── run.py
└── README.md
```

---

## ✨ Скриншоты

| Главная страница | Страница детекции |
|:----------------:|:-----------------:|
| ![](app/static/img/home_screenshot.png) | ![](app/static/img/detection_screenshot.png) |

---

## 🔒 Авторизация

- Зарегистрируйтесь для доступа к функции детекции.
- Только авторизованные пользователи могут загружать видео и просматривать результаты.

---


## 🗄️ Миграции БД

Схема управляется Alembic/Flask-Migrate:

```bash
flask --app run.py db upgrade
flask --app run.py db current
```

Перед изменением схемы сделайте backup:

```bash
python tools/backup_db.py
```

Существующая база уже помечена baseline-ревизией. Для новой базы достаточно
`flask --app run.py db upgrade`.

---

## 🔐 Безопасность и конфигурация

Скопируйте `.env.example` в `.env` и задайте значения:

```bash
APP_ENV=development
SECRET_KEY=<случайная строка не короче 32 байт>
GEMINI_API_KEY=<ключ Gemini, необязательно>
```

- В `APP_ENV=production` приложение не запустится без `SECRET_KEY`, с коротким ключом или с `SESSION_COOKIE_SECURE=0`.
- Сессия и CSRF-токен действуют 30 минут неактивности; параметры меняются через `SESSION_LIFETIME_MINUTES` и `CSRF_TIME_LIMIT_MINUTES`.
- Cookie сессии: `HttpOnly`, `SameSite=Lax`, в production — `Secure`.
- Выход из системы выполняется только через POST с CSRF-токеном.
- В production Flask слушает только `127.0.0.1`, TLS 1.3 и HSTS завершает reverse proxy. Шаблоны nginx и systemd — в `deploy/`.
- Для production используйте `wsgi.py` и настоящий WSGI-сервер, а не `python run.py`.
- Локальный HTTPS-стенд с Caddy: `deploy/windows/https-demo.md`.

### Модели YOLO

- Эталонные SHA-256 и официальные URL лежат в `app/model_hashes.json`.
- Файл весов проверяется до передачи в Ultralytics/PyTorch; непроверенная модель не загружается.
- Список доступных моделей хранится в `app/instance/models_registry.json` и не меняет схему SQLite.
- Проверить локальные веса:

```bash
python tools/model_manifest.py --check
python tools/model_manifest.py --hash models/yolov8n.pt
```

Если файла модели нет, она не появится у пользователя. Автоматическая загрузка весов из интернета отключена.

### Резервные копии

База данных резервируется в зашифрованном виде (AES-256-GCM):

```powershell
.\venv\Scripts\python.exe tools\backup_db.py --init-keyring
.\venv\Scripts\python.exe tools\backup_db.py
.\venv\Scripts\python.exe tools\verify_backup.py
```

Ключ хранится вне проекта: `D:\VKR_key_backup\backup-keyring.json`.
Копии — в `D:\VKR_YOLO_backups`, по умолчанию хранятся 15 дней.
Восстановление и расписание Task Scheduler описаны в `deploy/backup.md`.

### Аудит

- Каждому запросу присваивается `X-Request-ID`; он попадает в журнал аудита.
- В журнале можно фильтровать события по `request_id`.
- Экспорт доступен администратору и аудитору:
  ```text
  /audit/export?format=csv
  /audit/export?format=json
  ```
- Экспорт учитывает фильтры `action`, `actor`, `request_id` и ограничен 10 000 событий.

Администратор управляет моделями на странице `/admin/models`:

- скачать официальную модель из манифеста;
- проверить SHA-256;
- включить или выключить модель для пользователей;
- восстановить отсутствующий или повреждённый файл.

Удаление моделей и загрузка произвольных `.pt` через веб-интерфейс запрещены.

### Проверка загружаемых файлов

Перед обработкой проверяется реальный формат по сигнатуре, а не только расширение:

- JPEG, PNG, GIF, MP4/MOV, AVI;
- содержимое должно соответствовать расширению;
- ограничиваются разрешение изображений, размер GIF и длительность/разрешение видео.

Файл с подменённым расширением или слишком большими параметрами отклоняется до передачи в OpenCV/ffmpeg.

---

## 🤝 Контакты

Если есть вопросы или предложения:
- 📧 Почта: flyiq440464@gmail.com

---
