
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
- Нейронные сети: **YOLOv8** / **YOLOv9** (Ultralytics)
- Хранилище файлов: **Файловая система**
- Аутентификация: **Flask-Login**
- Прочее: **Jinja2**, **Flask-WTF**, **WTForms**

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

5. Запустить приложение:

```bash
flask run
```

---

## 📂 Структура проекта

```plaintext
vga/
├── app/
│   ├── static/
│   │   ├── css/
│   │   └── img/
│   ├── templates/
│   ├── routes/
│   ├── models/
│   └── detector.py
├── requirements.txt
├── config.py
├── run.py
└── README.md
```

---

## ✨ Скриншоты

| Главная страница | Страница детекции |
|:----------------:|:-----------------:|
| ![](static/img/home_screenshot.png) | ![](static/img/detection_screenshot.png) |

---

## 🔒 Авторизация

- Зарегистрируйтесь для доступа к функции детекции.
- Только авторизованные пользователи могут загружать видео и просматривать результаты.

---

## 📑 Лицензия

Этот проект лицензирован под лицензией MIT.

---

## 🤝 Контакты

Если есть вопросы или предложения:
- 📧 Почта: flyiq440464@gmail.com
- 🌐 Сайт: [Video Segmentation Analytics](Пока пусто)

---
