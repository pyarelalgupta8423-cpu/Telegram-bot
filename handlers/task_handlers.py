from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from database import *
from handlers.user_handlers import (
    handle_referral_points,
    ensure_user_verified,
    ensure_force_join_verified,
    process_pending_group_rewards
)
from bson import ObjectId
import random
import logging

logger = logging.getLogger(__name__)

async def tasks_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    if not await ensure_user_verified(query.from_user.id, context):
        await query.answer(
            "❌ Complete all requirements first!\nUse /start to verify.",
            show_alert=True
        )
        await query.message.edit_text(
            "⚠️ *Verification Required!*\n\n"
            "You need to complete all requirements:\n"
            "1. Join required channels\n"
            "2. Complete external tasks\n\n"
            "Use /start to check again.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Start Verification", callback_data="start_verify")]
            ]),
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    tasks_list = list(get_collection("tasks").find({"active": True}))
    
    keyboard = []
    for task in tasks_list:
        task_id = str(task["_id"])
        keyboard.append([
            InlineKeyboardButton(
                f"📌 {task['name']} (+{task['points']} pts)",
                callback_data=f"task_do_{task_id}"
            )
        ])
    keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")])
    
    await query.message.edit_text(
        "📋 *Available Tasks*\n\n"
        "Complete tasks to earn points!\n"
        "Points can be withdrawn for Telegram IDs.\n\n"
        "*Select a task to begin:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_specific_task(update: Update, context: ContextTypes.DEFAULT_TYPE, task_id: str):
    query = update.callback_query
    task = get_task_by_id(task_id)
    
    if not task:
        await query.answer("❌ Task not found!", show_alert=True)
        return
    
    if not await ensure_user_verified(query.from_user.id, context):
        await query.answer("❌ Complete verification first! Use /start", show_alert=True)
        return
    
    user_data = get_user(query.from_user.id)
    
    if task_id in [str(t) for t in user_data.get("completed_tasks", [])]:
        await query.answer("✅ Already completed!", show_alert=True)
        return
    
    if task["type"] == "add_to_group":
        bot_username = context.bot.username
        await query.message.edit_text(
            "📋 *Task: Add Bot to Group/Channel*\n\n"
            "📌 *Instructions:*\n"
            f"1. Add @{bot_username} to your group/channel\n"
            "2. Make bot admin with message permissions\n"
            "3. Bot will auto-detect and credit points\n\n"
            "💰 *Reward:* Based on group member count\n\n"
            "*Points credited automatically!*",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Tasks", callback_data="main_tasks")]
            ]),
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        user_data = get_user(query.from_user.id)
        claim_attempts = user_data.get("task_attempts", {}).get(task_id, 0)
        
        await query.message.edit_text(
            f"📋 *Task: {task['name']}*\n\n"
            f"💰 *Reward:* {task['points']} points\n\n"
            "📌 *Steps:*\n"
            f"1. Click 'Open Link' below\n"
            "2. Complete the required action\n"
            "3. Return here and click 'Claim Points'\n\n"
            f"⏳ *Confirmations needed:* {claim_attempts}/2\n"
            "ℹ️ Multiple confirmations prevent abuse",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Open Link", url=task['url'])],
                [InlineKeyboardButton("🎯 Claim Points", callback_data=f"task_verify_{task_id}")],
                [InlineKeyboardButton("🔙 Back", callback_data="main_tasks")]
            ]),
            parse_mode=ParseMode.MARKDOWN
        )

async def verify_task_completion(update: Update, context: ContextTypes.DEFAULT_TYPE, task_id: str):
    """Task claim with confirmation gate."""
    query = update.callback_query
    task = get_task_by_id(task_id)
    
    if not task:
        await query.answer("❌ Task not found!", show_alert=True)
        return
    
    if not await ensure_user_verified(query.from_user.id, context):
        await query.answer("❌ Complete verification first! Use /start", show_alert=True)
        return
    
    user_id = query.from_user.id
    user_data = get_user(user_id)
    claim_attempts = user_data.get("task_attempts", {}).get(task_id, 0)
    
    REQUIRED_CLAIMS = 2
    new_attempts = claim_attempts + 1
    
    if new_attempts < REQUIRED_CLAIMS:
        get_collection("users").update_one(
            {"user_id": user_id},
            {"$set": {f"task_attempts.{task_id}": new_attempts}}
        )
        
        remaining = REQUIRED_CLAIMS - new_attempts
        await query.answer(
            f"⚠️ Complete the task first! {remaining} more confirmation needed.",
            show_alert=True
        )
        return
    
    result = get_collection("users").update_one(
        {
            "user_id": user_id,
            "completed_tasks": {"$ne": ObjectId(task_id)}
        },
        {
            "$inc": {"points": task["points"]},
            "$addToSet": {"completed_tasks": ObjectId(task_id)},
            "$set": {f"task_attempts.{task_id}": new_attempts}
        }
    )
    
    if result.modified_count == 0:
        await query.answer("✅ Points already claimed!", show_alert=True)
        return
    
    await query.answer(f"✅ Points claimed! +{task['points']} points!", show_alert=True)
    await tasks_menu_handler(update, context)

async def handle_force_join_complete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Called when user passes force join check"""
    query = update.callback_query
    user_id = query.from_user.id
    
    get_collection("users").update_one(
        {"user_id": user_id},
        {"$set": {"force_join_completed": True}}
    )
    
    ext_links = list(get_collection("external_links").find({"active": True}))
    
    if ext_links:
        keyboard = []
        for link in ext_links:
            keyboard.append([
                InlineKeyboardButton(f"🔗 {link['name']}", url=link['url'])
            ])
        keyboard.append([
            InlineKeyboardButton("✅ I've Completed All", callback_data="ext_tasks_complete")
        ])
        
        await query.message.edit_text(
            "✅ *Channels Joined!*\n\n"
            "📋 *Complete External Tasks:*\n\n"
            "• Click each link below\n"
            "• Complete the required actions\n"
            "• Click 'I've Completed All' when done\n\n"
            "⚠️ *Note:* Multiple confirmations required",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await complete_verification(update, context, user_id)

async def handle_external_tasks_complete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle external tasks with fixed confirmation gate."""
    query = update.callback_query
    user_id = query.from_user.id
    
    if not await ensure_force_join_verified(user_id, context):
        await query.answer(
            "❌ Please join all required channels first!",
            show_alert=True
        )
        return
    
    user_data = get_user(user_id)
    verification = user_data.get("verification", {})
    required_confirmations = verification.get("external_required")
    
    if not required_confirmations:
        required_confirmations = random.randint(2, 3)
        get_collection("users").update_one(
            {"user_id": user_id},
            {"$set": {
                "verification.external_required": required_confirmations,
                "verification.external_attempts": 1
            }}
        )
        await query.answer(
            f"⚠️ Complete all external tasks! Confirmation 1/{required_confirmations}",
            show_alert=True
        )
        return
    
    current_attempts = verification.get("external_attempts", 0) + 1
    get_collection("users").update_one(
        {"user_id": user_id},
        {"$set": {"verification.external_attempts": current_attempts}}
    )
    
    if current_attempts < required_confirmations:
        await query.answer(
            f"⚠️ Keep confirming... {current_attempts}/{required_confirmations}",
            show_alert=True
        )
        return
    
    await complete_verification(update, context, user_id)

async def complete_verification(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Mark verification complete with version tracking and process rewards."""
    query = update.callback_query
    
    if not await ensure_force_join_verified(user_id, context):
        await query.answer(
            "❌ Verification failed! Stay in all required channels.",
            show_alert=True
        )
        return
    
    users = get_collection("users")
    current_version = get_verification_version()
    
    users.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "external_tasks_completed": True,
                "verification_version": current_version
            },
            "$unset": {
                "verification.external_required": "",
                "verification.external_attempts": ""
            }
        }
    )
    
    await process_pending_group_rewards(user_id, context)
    
    user_data = get_user(user_id)
    pending_referrer = user_data.get("pending_referrer")
    
    if pending_referrer:
        await handle_referral_points(user_id, pending_referrer, context)
    
    from utils.helpers import create_main_menu_keyboard
    
    await query.message.edit_text(
        "🎉 *Verification Complete!*\n\n"
        "✅ Required channels verified\n"
        "✅ External task confirmations done\n"
        "✅ Pending rewards processed\n"
        "✅ Referral processed (if applicable)\n\n"
        "*Welcome to Main Menu:*",
        reply_markup=create_main_menu_keyboard(user_id),
        parse_mode=ParseMode.MARKDOWN
    )
