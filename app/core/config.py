from dotenv import load_dotenv
import os

load_dotenv()

APP_NAME = os.getenv("APP_NAME", "Legal Lens")
ENV = os.getenv("ENV", "development")
