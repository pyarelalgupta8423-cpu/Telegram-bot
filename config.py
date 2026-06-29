import os
from dotenv import load_dotenv
import logging

load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
MONGO_URI = os.getenv('MONGO_URI')
DATABASE_NAME = os.getenv('DATABASE_NAME', 'telegram_bot')

# Admin IDs
ADMIN_IDS = [int(id.strip()) for id in os.getenv('ADMIN_IDS', '').split(',') if id.strip()]

# Default Points Configuration
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

# Force Join Channels (Store as list of channel usernames or IDs)
FORCE_JOIN_CHANNELS = []  # Will be managed via admin commands

# External Links for tasks
EXTERNAL_LINKS = []  # Will be managed via admin commands

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
