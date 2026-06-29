import os
from dotenv import load_dotenv
import logging

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
MONGO_URI = os.getenv('MONGO_URI')
DATABASE_NAME = os.getenv('DATABASE_NAME', 'telegram_bot')

ADMIN_IDS = []
admin_ids_str = os.getenv('ADMIN_IDS', '')
if admin_ids_str:
    ADMIN_IDS = [int(id.strip()) for id in admin_ids_str.split(',') if id.strip()]

DEFAULT_POINTS = {
    'refer_level1': 10,
    'refer_level2': 5,
    'task_points': {
        'group_channel': 20,
        'small': 5,
        'medium': 10,
        'm2': 15,
        'm3': 20,
        'm4': 25,
        'big': 30
    }
}

FORCE_JOIN_CHANNELS = []
EXTERNAL_LINKS = []

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
