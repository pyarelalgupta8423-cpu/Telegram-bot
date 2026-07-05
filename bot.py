import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    ChatMemberHandler, ContextTypes
)
from telegram.constants import ParseMode
from config import BOT_TOKEN, ADMIN_IDS
from database import *
from reward_service import *
from datetime import datetime
from bson import ObjectId
import random
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============ HELPERS ============
def create_main_menu_keyboard(user_id):
    user_data = get_user(user_id)
    keyboard = [
        [InlineKeyboardButton("🆔 Get ID (Withdraw)", callback_data="main_get_id")],
        [InlineKeyboardButton("🔗 Refer & Earn", callback_data="main_refer")],
        [InlineKeyboardButton("📊 Available IDs Status", callback_data="main_available_ids")],
        [InlineKeyboardButton("📋 Tasks", callback_data="main_tasks")],
        [InlineKeyboardButton(f"💰 Balance: {user_data['points']} Points", callback_data="main_balance")],
        [InlineKeyboardButton("📈 My Stats", callback_data="main_stats")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_admin_keyboard():
    keyboard = [
        [InlineKeyboardButton("📢 Broadcast to Users", callback_data="admin_broadcast_menu")],
        [InlineKeyboardButton("📊 Bot Statistics", callback_data="admin_stats")],
        [InlineKeyboardButton("🔗 Force Join Channels", callback_data="admin_manage_channels")],
        [InlineKeyboardButton("🔗 External Links", callback_data="admin_manage_links")],
        [InlineKeyboardButton("📋 Manage Tasks", callback_data="admin_manage_tasks")],
        [InlineKeyboardButton("💎 Points Configuration", callback_data="admin_points_config")],
        [InlineKeyboardButton("👥 Groups Management", callback_data="admin_groups_menu")],
        [InlineKeyboardButton("💰 Withdrawal Requests", callback_data="admin_withdrawals")]
    ]
    return InlineKeyboardMarkup(keyboard)

def format_points_message():
    points = get_points_config()
    return (
        "💎 *Current Points Configuration*\n\n"
        f"👥 *Referral System:*\n"
        f"• Level 1: {points['refer_level_1']} points\n"
        f"• Level 2: {points['refer_level_2']} points\n\n"
        f"📱 *Group Addition Rewards:*\n"
        f"• <100 members: {points['group_add_small']} points\n"
        f"• 101-1K members: {points['group_add_medium']} points\n"
        f"• 1K-2K members: {points['group_add_m2']} points\n"
        f"• 2K-3K members: {points['group_add_m3']} points\n"
        f"• 3K-5K members: {points['group_add_m4']} points\n"
        f"• >5K members: {points['group_add_big']} points\n\n"
        f"🎯 *Minimum Withdrawal:* {points['min_withdraw']} points"
    )

# ============ USER HANDLERS ============
async def check_force_join(user_id, context):
    channels_col = get_collection("channels")
    force_channels = list(channels_col.find({"active": True}))
    not_joined = []
    for ch in force_channels:
        try:
            member = await context.bot.get_chat_member(ch["channel_id"], user_id)
            if member.status in ['left', 'kicked']:
                not_joined.append(ch)
        except Exception:
            not_joined.append(ch)
    return not_joined

async def ensure_force_join_verified(user_id, context):
    not_joined = await check_force_join(user_id, context)
    if not_joined:
        get_collection("users").update_one(
            {"user_id": user_id},
            {"$set": {"force_join_completed": False}}
        )
        return False
    get_collection("users").update_one(
        {"user_id": user_id},
        {"$set": {"force_join_completed": True}}
    )
    return True

async def ensure_user_verified(user_id, context):
    user = get_user(user_id)
    if not user.get("external_tasks_completed", False):
        return False
    current_version = get_verification_version()
    if user.get("verification_version", 0) != current_version:
        get_collection("users").update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "external_tasks_completed": False,
                    "verification_version": 0
                },
                "$unset": {
                    "verification.external_required": "",
                    "verification.external_attempts": ""
                }
            }
        )
        return False
    return await ensure_force_join_verified(user_id, context)

async def process_pending_group_rewards(user_id, context):
    processed = process_pending_group_rewards_atomic(user_id)
    for reward in processed:
        try:
            await context.bot.send_message(
                user_id,
                "🎉 *Pending Group Reward Credited!*\n\n"
                f"📱 Group: {reward['title']}\n"
                f"💰 Points: *{reward['points']}*\n\n"
                "Reward for previously added group!",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Failed to notify group reward: {e}")

async def handle_referral_points(user_id, referrer_id, context):
    if not await ensure_user_verified(user_id, context):
        return False
    if referrer_id == user_id:
        return False
    result = credit_referral_atomic(user_id, referrer_id)
    if not result:
        return False
    points_config = get_points_config()
    try:
        await context.bot.send_message(
            result["referrer_id"],
            f"🎉 *New Verified Referral!*\n\n"
            f"✅ User completed all requirements\n"
            f"💰 You earned: *{result['level1_points']}* points\n"
            f"👤 Referral ID: `{user_id}`",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Failed to notify referrer: {e}")
    if result.get("level2_id"):
        try:
            await context.bot.send_message(
                result["level2_id"],
                f"🎉 *Level 2 Referral Bonus!*\n\n"
                f"💰 You earned: *{result['level2_points']}* points\n"
                f"From your referral's network!",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Failed to notify level2: {e}")
    return True

# ============ TASK HANDLERS ============
async def handle_force_join_complete(update, context):
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

async def handle_external_tasks_complete(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    if not await ensure_force_join_verified(user_id, context):
        await query.answer("❌ Please join all required channels first!", show_alert=True)
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

async def complete_verification(update, context, user_id):
    query = update.callback_query
    if not await ensure_force_join_verified(user_id, context):
        await query.answer("❌ Verification failed! Stay in all required channels.", show_alert=True)
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

# ============ CALLBACK ROUTER ============
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    
    if data == "main_menu":
        user_data = get_user(user_id)
        if user_data.get("force_join_completed") and user_data.get("external_tasks_completed"):
            await query.message.edit_text(
                "📱 *Main Menu*\nChoose an option:",
                reply_markup=create_main_menu_keyboard(user_id),
                parse_mode="Markdown"
            )
        else:
            await query.message.edit_text(
                "⚠️ Complete verification first!\nUse /start",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Start Verification", callback_data="start_verify")]
                ]),
                parse_mode="Markdown"
            )
    elif data == "main_get_id":
        await get_id_handler(update, context)
    elif data == "main_refer":
        await refer_menu_handler(update, context)
    elif data == "main_available_ids":
        await available_ids_handler(update, context)
    elif data == "main_tasks":
        await tasks_menu_handler(update, context)
    elif data == "main_balance":
        user_data = get_user(user_id)
        await query.answer(f"💰 Balance: {user_data['points']} Points", show_alert=True)
    elif data == "main_stats":
        await show_stats(update, context)
    elif data == "check_join":
        not_joined = await check_force_join(user_id, context)
        if not_joined:
            await query.answer("❌ Please join all channels first!", show_alert=True)
        else:
            await query.answer("✅ Verified! Loading tasks...")
            await handle_force_join_complete(update, context)
    elif data == "start_verify":
        not_joined = await check_force_join(user_id, context)
        if not_joined:
            keyboard = []
            for ch in not_joined:
                keyboard.append([InlineKeyboardButton(f"📢 Join {ch['channel_name']}", url=ch['invite_link'])])
            keyboard.append([InlineKeyboardButton("✅ Check & Continue", callback_data="check_join")])
            await query.message.edit_text(
                "⚠️ *Join Required Channels:*",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        else:
            await handle_force_join_complete(update, context)
    elif data == "ext_tasks_complete":
        await handle_external_tasks_complete(update, context)
    elif data.startswith("task_do_"):
        task_id = data.replace("task_do_", "")
        await handle_specific_task(update, context, task_id)
    elif data.startswith("task_verify_"):
        task_id = data.replace("task_verify_", "")
        await verify_task_completion(update, context, task_id)
    elif data == "admin_panel" or data.startswith("admin_"):
        await handle_admin_callbacks(update, context)
    else:
        await query.answer("❓ Unknown command", show_alert=True)

# ============ MENU HANDLERS ============
async def refer_menu_handler(update, context):
    query = update.callback_query
    bot_username = context.bot.username
    referral_link = f"https://t.me/{bot_username}?start=ref_{query.from_user.id}"
    points = get_points_config()
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh Link", callback_data="main_refer")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]
    ]
    await query.message.edit_text(
        "🔗 *Your Referral Program*\n\n"
        f"🔹 *Your Link:*\n`{referral_link}`\n\n"
        "📊 *Earning Structure:*\n"
        f"• Direct Referral: *{points['refer_level_1']}* points\n"
        f"• Referral's Referral: *{points['refer_level_2']}* points\n\n"
        "⚠️ *Requirements for Referral Credit:*\n"
        "• User must join all required channels\n"
        "• User must complete external tasks\n"
        "• User must remain in channels\n\n"
        "*Share your link and start earning!*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def get_id_handler(update, context):
    query = update.callback_query
    points_config = get_points_config()
    withdraw_amount = points_config["min_withdraw"]
    if not await ensure_user_verified(query.from_user.id, context):
        await query.answer("❌ Verification failed! Complete all requirements first.\nUse /start to re-verify.", show_alert=True)
        return
    result = create_withdrawal_atomic(
        user_id=query.from_user.id,
        withdraw_amount=withdraw_amount,
        username=query.from_user.username or "N/A",
        full_name=query.from_user.full_name
    )
    if not result:
        await query.answer(f"❌ Insufficient balance! Need {withdraw_amount} points.\nYour balance: {get_user(query.from_user.id)['points']}", show_alert=True)
        return
    keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]]
    await query.message.edit_text(
        "✅ *Withdrawal Request Submitted!*\n\n"
        f"🔢 *Token Number:* `{result['serial_no']}`\n"
        f"💰 *Points Deducted:* {result['withdraw_amount']}\n"
        f"💎 *Remaining Balance:* {result['new_balance']}\n\n"
        "📋 *Next Steps:*\n"
        "1. Copy your token number\n"
        "2. Contact admin with this token\n"
        "3. Admin will verify and send you ID\n\n"
        "⏳ *Processing Time:* Usually within 24 hours",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def show_stats(update, context):
    query = update.callback_query
    user_data = get_user(query.from_user.id)
    stats_text = (
        "📊 *Your Statistics*\n\n"
        f"💰 *Balance:* {user_data['points']} Points\n"
        f"👥 *Direct Referrals:* {len(user_data.get('referrals', []))}\n"
        f"👥 *Level 2 Referrals:* {len(user_data.get('level2_referrals', []))}\n"
        f"✅ *Tasks Completed:* {len(user_data.get('completed_tasks', []))}\n"
        f"📅 *Joined:* {user_data['join_date'].strftime('%Y-%m-%d')}"
    )
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]
    await query.message.edit_text(stats_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def available_ids_handler(update, context):
    query = update.callback_query
    total_withdraws = get_collection("withdraw_requests").count_documents({})
    pending = get_collection("withdraw_requests").count_documents({"status": "pending"})
    completed = get_collection("withdraw_requests").count_documents({"status": "completed"})
    points_config = get_points_config()
    keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]]
    await query.message.edit_text(
        "🆔 *ID Withdrawal Status*\n\n"
        f"📊 *Total Requests:* {total_withdraws}\n"
        f"⏳ *Pending:* {pending}\n"
        f"✅ *Completed:* {completed}\n"
        f"💎 *Cost per ID:* {points_config['min_withdraw']} points\n\n"
        "💡 *To get an ID:*\n"
        "• Complete all verification tasks\n"
        "• Earn required points\n"
        "• Use 'Get ID' option in menu",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def tasks_menu_handler(update, context):
    query = update.callback_query
    if not await ensure_user_verified(query.from_user.id, context):
        await query.answer("❌ Complete all requirements first!\nUse /start to verify.", show_alert=True)
        await query.message.edit_text(
            "⚠️ *Verification Required!*\n\n"
            "You need to complete all requirements:\n"
            "1. Join required channels\n"
            "2. Complete external tasks\n\n"
            "Use /start to check again.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Start Verification", callback_data="start_verify")]]),
            parse_mode=ParseMode.MARKDOWN
        )
        return
    tasks_list = list(get_collection("tasks").find({"active": True}))
    keyboard = []
    for task in tasks_list:
        task_id = str(task["_id"])
        keyboard.append([InlineKeyboardButton(f"📌 {task['name']} (+{task['points']} pts)", callback_data=f"task_do_{task_id}")])
    keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")])
    await query.message.edit_text(
        "📋 *Available Tasks*\n\n"
        "Complete tasks to earn points!\n"
        "Points can be withdrawn for Telegram IDs.\n\n"
        "*Select a task to begin:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_specific_task(update, context, task_id):
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
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Tasks", callback_data="main_tasks")]]),
            parse_mode=ParseMode.MARKDOWN
        )
    else:
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

async def verify_task_completion(update, context, task_id):
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
        await query.answer(f"⚠️ Complete the task first! {remaining} more confirmation needed.", show_alert=True)
        return
    result = get_collection("users").update_one(
        {"user_id": user_id, "completed_tasks": {"$ne": ObjectId(task_id)}},
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

# ============ ADMIN HANDLERS ============
async def handle_admin_callbacks(update, context):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Unauthorized!", show_alert=True)
        return
    
    if data == "admin_stats":
        total_users = get_collection("users").count_documents({})
        stats = get_collection("settings").find_one({"type": "bot_stats"})
        total_groups = stats.get("total_groups", 0) if stats else 0
        total_withdraws = get_collection("withdraw_requests").count_documents({})
        pending_withdraws = get_collection("withdraw_requests").count_documents({"status": "pending"})
        keyboard = [[InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]]
        await query.message.edit_text(
            "📊 *Bot Statistics*\n\n"
            f"👥 Total Users: *{total_users}*\n"
            f"📱 Groups/Channels: *{total_groups}*\n"
            f"💰 Total Withdrawals: *{total_withdraws}*\n"
            f"⏳ Pending: *{pending_withdraws}*\n"
            f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif data == "admin_manage_channels":
        channels_list = list(get_collection("channels").find({"active": True}))
        keyboard = []
        for ch in channels_list:
            keyboard.append([InlineKeyboardButton(f"❌ {ch['channel_name']}", callback_data=f"admin_remove_ch_{ch['_id']}")])
        keyboard.append([InlineKeyboardButton("➕ Add Channel", callback_data="admin_add_channel")])
        keyboard.append([InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")])
        await query.message.edit_text(
            "🔗 *Force Join Channels*\n\n" f"Active: *{len(channels_list)}*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif data == "admin_add_channel":
        await query.message.edit_text(
            "➕ *Add Force Join Channel*\n\n"
            "Use: `/addchannel channel_id | @channel_name | invite_link`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_manage_channels")]]),
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif data.startswith("admin_remove_ch_"):
        channel_id = data.replace("admin_remove_ch_", "")
        get_collection("channels").delete_one({"_id": ObjectId(channel_id)})
        await query.answer("✅ Channel removed!", show_alert=True)
        await handle_admin_callbacks(update, context)
    
    elif data == "admin_manage_links":
        links = list(get_collection("external_links").find({"active": True}))
        keyboard = []
        for link in links:
            keyboard.append([InlineKeyboardButton(f"❌ {link['name']}", callback_data=f"admin_remove_link_{link['_id']}")])
        keyboard.append([InlineKeyboardButton("➕ Add Link", callback_data="admin_add_link")])
        keyboard.append([InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")])
        await query.message.edit_text(
            "🔗 *External Links*\n\n" f"Active: *{len(links)}*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif data == "admin_add_link":
        await query.message.edit_text(
            "➕ *Add External Link*\n\nUse: `/addlink name | url`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_manage_links")]]),
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif data.startswith("admin_remove_link_"):
        link_id = data.replace("admin_remove_link_", "")
        get_collection("external_links").delete_one({"_id": ObjectId(link_id)})
        await query.answer("✅ Link removed!", show_alert=True)
        await handle_admin_callbacks(update, context)
    
    elif data == "admin_points_config":
        keyboard = [
            [InlineKeyboardButton("✏️ Edit Points", callback_data="admin_edit_points")],
            [InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]
        ]
        await query.message.edit_text(
            format_points_message(),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif data == "admin_edit_points":
        await query.message.edit_text(
            "✏️ *Edit Points*\n\nUse: `/setpoints key value`\n\n"
            "Keys: `refer_level_1`, `refer_level_2`, `group_add_small`, `group_add_medium`, `group_add_m2`, `group_add_m3`, `group_add_m4`, `group_add_big`, `min_withdraw`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_points_config")]]),
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif data == "admin_withdrawals":
        pending = list(get_collection("withdraw_requests").find({"status": "pending"}).limit(5))
        if not pending:
            text = "✅ No pending withdrawals!"
            keyboard = [[InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]]
        else:
            text = "💰 *Pending Withdrawals:*\n\n"
            keyboard = []
            for req in pending:
                text += f"🔢 *#{req['serial_no']}*\n👤 {req.get('full_name', 'N/A')}\n💰 Points: {req['points']}\n📅 {req['request_date'].strftime('%Y-%m-%d')}\n\n"
                keyboard.append([InlineKeyboardButton(f"✅ Approve #{req['serial_no']}", callback_data=f"admin_approve_{req['_id']}")])
            keyboard.append([InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")])
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    
    elif data.startswith("admin_approve_"):
        withdrawal_id = data.replace("admin_approve_", "")
        req = get_collection("withdraw_requests").find_one_and_update(
            {"_id": ObjectId(withdrawal_id), "status": "pending"},
            {"$set": {"status": "completed", "processed_date": datetime.now()}},
            return_document=ReturnDocument.BEFORE
        )
        if not req:
            await query.answer("⚠️ Request already processed!", show_alert=True)
        else:
            try:
                await context.bot.send_message(req["user_id"], f"✅ *Withdrawal Approved!*\n\n🔢 Token: #{req['serial_no']}\n💰 Points: {req['points']}", parse_mode=ParseMode.MARKDOWN)
            except: pass
            await query.answer("✅ Approved!", show_alert=True)
        await handle_admin_callbacks(update, context)
    
    elif data.startswith("admin_reject_"):
        withdrawal_id = data.replace("admin_reject_", "")
        req = get_collection("withdraw_requests").find_one_and_update(
            {"_id": ObjectId(withdrawal_id), "status": "pending"},
            {"$set": {"status": "rejected", "processed_date": datetime.now()}},
            return_document=ReturnDocument.BEFORE
        )
        if not req:
            await query.answer("⚠️ Request already processed!", show_alert=True)
        else:
            get_collection("users").update_one({"user_id": req["user_id"]}, {"$inc": {"points": req["points"]}})
            try:
                await context.bot.send_message(req["user_id"], f"❌ *Withdrawal Rejected*\n\n🔢 Token: #{req['serial_no']}\n💰 Points refunded: {req['points']}", parse_mode=ParseMode.MARKDOWN)
            except: pass
            await query.answer("❌ Rejected & refunded!", show_alert=True)
        await handle_admin_callbacks(update, context)
    
    elif data == "admin_panel":
        await query.message.edit_text("🔐 *Admin Panel*", reply_markup=create_admin_keyboard(), parse_mode=ParseMode.MARKDOWN)
    
    elif data == "admin_broadcast_menu":
        await query.message.edit_text(
            "📢 *Broadcast*\n\nReply to a message with `/broadcast`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]]),
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif data == "admin_groups_menu":
        total_groups = get_collection("groups").count_documents({})
        keyboard = [
            [InlineKeyboardButton("📊 Group Statistics", callback_data="admin_group_stats")],
            [InlineKeyboardButton("📢 Broadcast to Groups", callback_data="admin_broadcast_groups")],
            [InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]
        ]
        await query.message.edit_text(f"👥 *Groups Management*\n\nTotal Groups: *{total_groups}*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    
    elif data == "admin_group_stats":
        groups = list(get_collection("groups").find({}).limit(10))
        text = "No groups yet!" if not groups else "📊 *Recent Groups:*\n\n"
        if groups:
            for g in groups:
                text += f"📱 *{g.get('title', 'N/A')}*\n👥 Members: {g.get('member_count', 0)}\n💰 Reward: {g.get('reward_points', 0)} pts\n\n"
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_groups_menu")]]), parse_mode=ParseMode.MARKDOWN)
    
    elif data == "admin_broadcast_groups":
        await query.message.edit_text(
            "📢 Reply to a message with `/broadcastgroups`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_groups_menu")]]),
            parse_mode=ParseMode.MARKDOWN
        )
    
    else:
        await query.answer("Feature coming soon!", show_alert=True)

# ============ BOT COMMANDS ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    user_data = get_user(user.id)
    
    get_collection("users").update_one(
        {"user_id": user.id},
        {"$set": {"username": user.username or "", "full_name": user.full_name}}
    )
    
    if args and args[0].startswith("ref_"):
        try:
            referrer_id = int(args[0].replace("ref_", ""))
            if referrer_id != user.id:
                referrer = get_collection("users").find_one({"user_id": referrer_id})
                if referrer and not user_data.get("referred_by") and not user_data.get("referral_rewarded"):
                    get_collection("users").update_one({"user_id": user.id}, {"$set": {"pending_referrer": referrer_id}})
        except ValueError:
            pass
    
    not_joined = await check_force_join(user.id, context)
    
    if not_joined:
        keyboard = []
        for ch in not_joined:
            keyboard.append([InlineKeyboardButton(f"📢 Join {ch['channel_name']}", url=ch['invite_link'])])
        keyboard.append([InlineKeyboardButton("✅ Check & Continue", callback_data="check_join")])
        await update.message.reply_text(
            "👋 *Welcome!*\n\n⚠️ *Join all required channels to continue:*\n\nClick 'Check & Continue' after joining",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    current_version = get_verification_version()
    if user_data.get("verification_version", 0) != current_version:
        get_collection("users").update_one(
            {"user_id": user.id},
            {"$set": {"external_tasks_completed": False, "verification_version": 0},
             "$unset": {"verification.external_required": "", "verification.external_attempts": ""}}
        )
        user_data = get_user(user.id)
    
    if user_data.get("force_join_completed") and user_data.get("external_tasks_completed"):
        await update.message.reply_text(
            "👋 *Welcome Back!*\n\n✅ All verifications complete\nChoose an option:",
            reply_markup=create_main_menu_keyboard(user.id),
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        get_collection("users").update_one({"user_id": user.id}, {"$set": {"force_join_completed": True}})
        ext_links = list(get_collection("external_links").find({"active": True}))
        
        if ext_links:
            keyboard = []
            for link in ext_links:
                keyboard.append([InlineKeyboardButton(f"🔗 {link['name']}", url=link['url'])])
            keyboard.append([InlineKeyboardButton("✅ I've Completed All", callback_data="ext_tasks_complete")])
            await update.message.reply_text(
                "✅ *Channels Joined!*\n\n📋 *Now Complete External Tasks:*\n\n• Click each link and complete\n• Then click 'I've Completed All'\n\n⚠️ Multiple confirmations required",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            current_ver = get_verification_version()
            get_collection("users").update_one(
                {"user_id": user.id},
                {"$set": {"external_tasks_completed": True, "verification_version": current_ver},
                 "$unset": {"verification.external_required": "", "verification.external_attempts": ""}}
            )
            await process_pending_group_rewards(user.id, context)
            updated_user = get_user(user.id)
            if updated_user.get("pending_referrer"):
                await handle_referral_points(user.id, updated_user["pending_referrer"], context)
            await update.message.reply_text(
                "🎉 *All Verifications Complete!*\n\nChoose an option:",
                reply_markup=create_main_menu_keyboard(user.id),
                parse_mode=ParseMode.MARKDOWN
            )

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Unauthorized!")
        return
    await update.message.reply_text("🔐 *Admin Panel*\n\nSelect an option:", reply_markup=create_admin_keyboard(), parse_mode=ParseMode.MARKDOWN)

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Reply to a message with /broadcast")
        return
    message = update.message.reply_to_message
    all_users = get_collection("users").find({})
    total = get_collection("users").count_documents({})
    status_msg = await update.message.reply_text(f"📢 Broadcasting... 0/{total}")
    success, failed = 0, 0
    for i, user in enumerate(all_users, 1):
        try:
            await message.copy(chat_id=user["user_id"])
            success += 1
        except:
            failed += 1
        if i % 20 == 0:
            await status_msg.edit_text(f"📢 Broadcasting...\n✅ {success} | ❌ {failed} | 📊 {i}/{total}")
        await asyncio.sleep(0.05)
    await status_msg.edit_text(f"✅ Broadcast Complete!\n✅ {success} | ❌ {failed} | 📊 {total}")

async def broadcast_groups_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Reply to a message with /broadcastgroups")
        return
    message = update.message.reply_to_message
    groups = list(get_collection("groups").find({"reward_given": True}))
    status_msg = await update.message.reply_text(f"📢 Broadcasting to groups... 0/{len(groups)}")
    success, failed = 0, 0
    for i, group in enumerate(groups, 1):
        try:
            await message.copy(chat_id=group["chat_id"])
            success += 1
        except:
            failed += 1
        if i % 5 == 0:
            await status_msg.edit_text(f"📢 Broadcasting...\n✅ {success} | ❌ {failed} | 📊 {i}/{len(groups)}")
        await asyncio.sleep(0.1)
    await status_msg.edit_text(f"✅ Broadcast to Groups Complete!\n✅ {success} | ❌ {failed}")

async def add_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    try:
        text = update.message.text.replace("/addchannel ", "")
        parts = text.split("|")
        channel_id = int(parts[0].strip())
        channel_name = parts[1].strip()
        invite_link = parts[2].strip()
        get_collection("channels").insert_one({
            "channel_id": channel_id, "channel_name": channel_name,
            "invite_link": invite_link, "active": True, "added_date": datetime.now()
        })
        await update.message.reply_text(f"✅ Channel {channel_name} added!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def add_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    try:
        text = update.message.text.replace("/addlink ", "")
        parts = text.split("|")
        name = parts[0].strip()
        url = parts[1].strip()
        get_collection("external_links").insert_one({
            "name": name, "url": url, "active": True, "added_date": datetime.now()
        })
        increment_verification_version()
        await update.message.reply_text(f"✅ Link '{name}' added!\n🔄 Verification version updated.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def add_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    try:
        text = update.message.text.replace("/addtask ", "")
        parts = text.split("|")
        name = parts[0].strip()
        points = int(parts[1].strip())
        task_type = parts[2].strip()
        url = parts[3].strip() if len(parts) > 3 else ""
        get_collection("tasks").insert_one({
            "name": name, "points": points, "type": task_type,
            "url": url, "active": True, "created_date": datetime.now()
        })
        await update.message.reply_text(f"✅ Task '{name}' added! ({points} pts)")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def set_points_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    try:
        text = update.message.text.replace("/setpoints ", "")
        parts = text.split()
        key = parts[0].strip()
        value = int(parts[1].strip())
        points = get_points_config()
        if key in points:
            points[key] = value
            update_points_config(points)
            await update.message.reply_text(f"✅ {key} = {value} points!")
        else:
            await update.message.reply_text(f"❌ Invalid key!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def handle_bot_added_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_member_update = update.my_chat_member
    if chat_member_update.new_chat_member.status != "administrator":
        return
    chat = chat_member_update.chat
    added_by = chat_member_update.from_user
    if not added_by:
        return
    try:
        member_count = await context.bot.get_chat_member_count(chat.id)
    except:
        member_count = 0
    
    points_config = get_points_config()
    points = 0
    if member_count < 100: points = points_config["group_add_small"]
    elif member_count <= 1000: points = points_config["group_add_medium"]
    elif member_count <= 2000: points = points_config["group_add_m2"]
    elif member_count <= 3000: points = points_config["group_add_m3"]
    elif member_count <= 5000: points = points_config["group_add_m4"]
    else: points = points_config["group_add_big"]
    
    try:
        get_collection("groups").update_one(
            {"chat_id": chat.id},
            {"$setOnInsert": {"chat_id": chat.id, "reward_given": False, "added_at": datetime.now()},
             "$set": {"title": chat.title or "Unknown", "member_count": member_count, "added_by": added_by.id, "reward_points": points}},
            upsert=True
        )
    except Exception as e:
        if "duplicate key" in str(e).lower() or "E11000" in str(e):
            pass
        else:
            raise
    
    is_verified = await ensure_user_verified(added_by.id, context)
    
    if is_verified:
        result = credit_group_reward_atomic(chat.id, added_by.id, chat.title, member_count, points)
        if result:
            try:
                await context.bot.send_message(added_by.id, f"✅ *Group Reward!*\n\n📱 {chat.title}\n👥 {member_count}\n💰 *{points}* points", parse_mode=ParseMode.MARKDOWN)
            except: pass
    else:
        create_group_pending_reward(chat.id, added_by.id, chat.title, member_count, points)
        try:
            await context.bot.send_message(added_by.id, f"⚠️ *Reward Pending!*\n\n📱 {chat.title}\n💰 *{points}* points\n\nComplete verification with /start", parse_mode=ParseMode.MARKDOWN)
        except: pass

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

def main():
    init_db()
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("broadcastgroups", broadcast_groups_command))
    application.add_handler(CommandHandler("addchannel", add_channel_command))
    application.add_handler(CommandHandler("addlink", add_link_command))
    application.add_handler(CommandHandler("addtask", add_task_command))
    application.add_handler(CommandHandler("setpoints", set_points_command))
    application.add_handler(ChatMemberHandler(handle_bot_added_to_group, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(CallbackQueryHandler(callback_router))
    application.add_error_handler(error_handler)
    
    logger.info("Bot started!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
