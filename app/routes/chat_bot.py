import google.generativeai as genai
from flask import Blueprint, request, jsonify
import os
from dotenv import load_dotenv

load_dotenv()

bp = Blueprint("chatbot", __name__)

api_key = os.getenv("gemini_api_key")

genai.configure(api_key=api_key)

system_prompt = """
Ты — встроенный чат-помощник приложения Video Segmentation Analytics (VGA).
Отвечай кратко и по делу. Помогаешь пользователям понять:

1. Как работает детекция объектов в VGA.
2. Как запустить анализ видео/изображений.
3. Что нужно делать, если пользователь не авторизован.
4. Как выбрать модель (например YOLOv8).
5. Как загрузить файл для обработки.
6. Какие форматы поддерживает сервис.
7. Общие вопросы по функционалу сайта.

Если пользователь не авторизован, говори:

"Для продолжения авторизуйтесь на сайте, затем перейдите на страницу Детекции."

Если пользователь пишет что-то вроде: 
- "детекция"
- "как работает?"
- "как загрузить?"
- "анализ видео"
- "сегментация"
- даже просто "??"

— ты обязан ответить полезным объяснением или предложить варианты:
"Вы хотите узнать, как начать детекцию, какие модели доступны или как работает система?"

Не давай технических деталей кода, только пользовательские инструкции.
"""

model = genai.GenerativeModel(model_name="models/gemini-2.5-flash", system_instruction=system_prompt)


@bp.route("/chatbot", methods=["POST"])
def chatbot():
    user_message = request.json.get("message", "")

    # ТУТ ПОКА ПРОСТО ЗАГЛУШКА
    try:
        response = model.generate_content(user_message)
        answer = response.text
    except Exception as e:
        answer = "Ошибка подключения к AI: " + str(e)

    return jsonify({"answer": answer})
