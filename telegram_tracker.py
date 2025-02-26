import os
import time
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler,ContextTypes
from gps_ble_tracker import CombinedTracker
import threading
import queue

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("No telegram token found")

logging.basicConfig(
    format = "",
    level =logging.INFO
)
