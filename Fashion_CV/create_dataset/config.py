import os
from dotenv import load_dotenv

load_dotenv()


API_KEY = os.getenv("API_KEY")
API_URL = os.getenv("API_URL")

if not API_KEY:
    raise ValueError("Переменная API_KEY не найдена в файле .env!")
elif not API_URL:
    raise ValueError("Переменная API_URL не найдена в файле .env!")