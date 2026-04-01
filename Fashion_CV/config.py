import os
from dotenv import load_dotenv

load_dotenv()


API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError("Переменная GEMINI_API_KEY не найдена в файле .env!")