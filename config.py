import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))

DEFAULT_POINTS = {
    "refer_level_1": 50,
    "refer_level_2": 25,
    "group_add_small": 100,
    "group_add_medium": 250,
    "group_add_m2": 500,
    "group_add_m3": 750,
    "group_add_m4": 1000,
    "group_add_big": 2000,
    "min_withdraw": 500,
}

COLLECTIONS = {
    "users": "users",
    "channels": "force_join_channels",
    "external_links": "external_links",
    "tasks": "tasks",
    "withdraw_requests": "withdraw_requests",
    "settings": "settings",
    "groups": "groups",
    "counters": "counters"
}
