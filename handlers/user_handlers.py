from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from database import *
from reward_service import (
    credit_referral_atomic,
    process_pending_group_rewards_atomic,
    create_withdrawal_atomic
)
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

async def check_force_join(user_id, context):
    """Check if user has joined all required channels"""
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
    """LIVE force-join verification ONLY. Does NOT check external tasks."""
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
    """FULL live verification (channels + external tasks + version check)."""
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

async def verify_user_completion(user_id):
    """Check stored completion status (for UI display only)"""
    user = get_user(user_id)
    return user.get("force_join_completed", False) and user.get("external_tasks_completed", False)

async def process_pending_group_rewards(user_id, context):
    """Process pending group rewards and send notifications."""
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
    """Credit referral points using atomic transaction."""
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

async def refer_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_data = get_user(query.from_user.id)
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

async def get_id_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Withdrawal handler using atomic transaction."""
    query = update.callback_query
    points_config = get_points_config()
    withdraw_amount = points_config["min_withdraw"]
    
    if not await ensure_user_verified(query.from_user.id, context):
        await query.answer(
            "❌ Verification failed! Complete all requirements first.\nUse /start to re-verify.",
            show_alert=True
        )
        return
    
    result = create_withdrawal_atomic(
        user_id=query.from_user.id,
        withdraw_amount=withdraw_amount,
        username=query.from_user.username or "N/A",
        full_name=query.from_user.full_name
    )
    
    if not result:
        await query.answer(
            f"❌ Insufficient balance! Need {withdraw_amount} points.\n"
            f"Your balance: {get_user(query.from_user.id)['points']}",
            show_alert=True
        )
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

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    await query.message.edit_text(
        stats_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def available_ids_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
