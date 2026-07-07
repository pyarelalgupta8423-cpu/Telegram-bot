from pymongo import MongoClient, ReturnDocument
from datetime import datetime
from config import MONGO_URI, DEFAULT_POINTS, COLLECTIONS
import logging

logger = logging.getLogger(__name__)

client = MongoClient(MONGO_URI)
db = client["referral_bot"]


def get_collection(name):
    """
    Get MongoDB collection using strict collection mapping.

    Raises KeyError if an unknown logical collection name is used.
    This helps catch typos instead of silently creating wrong collections.
    """
    return db[COLLECTIONS[name]]


def init_db():
    settings = get_collection("settings")

    if not settings.find_one({"type": "points"}):
        settings.insert_one({
            "type": "points",
            "data": DEFAULT_POINTS,
            "updated_at": datetime.now()
        })

    if not settings.find_one({"type": "bot_stats"}):
        settings.insert_one({
            "type": "bot_stats",
            "total_users": 0,
            "total_groups": 0,
            "updated_at": datetime.now()
        })

    if not settings.find_one({"type": "verification"}):
        settings.insert_one({
            "type": "verification",
            "version": 1,
            "updated_at": datetime.now()
        })

    # Core indexes
    get_collection("users").create_index(
        "user_id",
        unique=True
    )

    get_collection("groups").create_index(
        "chat_id",
        unique=True
    )

    get_collection("tasks").create_index(
        "name"
    )

    get_collection("withdraw_requests").create_index(
        [
            ("user_id", 1),
            ("status", 1)
        ]
    )

    get_collection("withdraw_requests").create_index(
        "serial_no",
        unique=True
    )

    get_collection("counters").create_index(
        "_id"
    )

    # CMS indexes
    get_collection("ui_screens").create_index(
        "screen_id",
        unique=True
    )

    get_collection("ui_buttons").create_index(
        [
            ("screen_id", 1),
            ("order", 1)
        ]
    )

    get_collection("ui_services").create_index(
        "active"
    )

    logger.info("Database initialized with all indexes")


def get_next_sequence(name):
    """Atomic counter for unique serial numbers."""

    counter = get_collection("counters").find_one_and_update(
        {"_id": name},
        {
            "$inc": {
                "sequence": 1
            }
        },
        upsert=True,
        return_document=ReturnDocument.AFTER
    )

    return counter["sequence"]


def get_verification_version():
    """Get current verification version."""

    config = get_collection("settings").find_one({
        "type": "verification"
    })

    return config.get("version", 1) if config else 1


def increment_verification_version():
    """Increment verification version when requirements change."""

    get_collection("settings").update_one(
        {
            "type": "verification"
        },
        {
            "$inc": {
                "version": 1
            },
            "$set": {
                "updated_at": datetime.now()
            }
        },
        upsert=True
    )


def get_user(user_id):
    users = get_collection("users")

    user = users.find_one({
        "user_id": user_id
    })

    if not user:
        user = {
            "user_id": user_id,
            "username": "",
            "full_name": "",
            "points": 0,
            "refer_code": str(user_id),
            "referred_by": None,
            "pending_referrer": None,
            "referral_rewarded": False,
            "referred_by_level2": None,
            "referrals": [],
            "level2_referrals": [],
            "completed_tasks": [],
            "task_attempts": {},
            "verification": {},
            "force_join_completed": False,
            "external_tasks_completed": False,
            "verification_version": 0,
            "join_date": datetime.now(),
            "is_banned": False
        }

        try:
            users.insert_one(user)

            get_collection("settings").update_one(
                {
                    "type": "bot_stats"
                },
                {
                    "$inc": {
                        "total_users": 1
                    },
                    "$set": {
                        "updated_at": datetime.now()
                    }
                }
            )

        except Exception:
            # Handles possible concurrent user creation.
            user = users.find_one({
                "user_id": user_id
            })

            if not user:
                raise

    return user


def get_points_config():
    config = get_collection("settings").find_one({
        "type": "points"
    })

    return config["data"] if config else DEFAULT_POINTS


def update_points_config(new_config):
    get_collection("settings").update_one(
        {
            "type": "points"
        },
        {
            "$set": {
                "data": new_config,
                "updated_at": datetime.now()
            }
        },
        upsert=True
    )


def get_task_by_id(task_id):
    try:
        from bson import ObjectId

        return get_collection("tasks").find_one({
            "_id": ObjectId(task_id)
        })

    except Exception:
        return None
