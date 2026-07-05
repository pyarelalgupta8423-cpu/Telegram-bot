from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from database import *
from bson import ObjectId
from datetime import datetime
import asyncio
import logging

logger = logging.getLogger(__name__)

async def handle_admin_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route all admin callbacks to appropriate handlers"""
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Unauthorized!", show_alert=True)
        return
    
    if data == "admin_stats":
        await show_admin_stats(update, context)
    elif data == "admin_manage_channels":
        await manage_channels_menu(update, context)
    elif data == "admin_add_channel":
        await prompt_add_channel(update, context)
    elif data.startswith("admin_remove_ch_"):
        channel_id = data.replace("admin_remove_ch_", "")
        await remove_channel(update, context, channel_id)
    elif data == "admin_manage_links":
        await manage_links_menu(update, context)
    elif data == "admin_add_link":
        await prompt_add_link(update, context)
    elif data.startswith("admin_remove_link_"):
        link_id = data.replace("admin_remove_link_", "")
        await remove_link(update, context, link_id)
    elif data == "admin_manage_tasks":
        await manage_tasks_menu(update, context)
    elif data == "admin_add_task":
        await prompt_add_task(update, context)
    elif data.startswith("admin_remove_task_"):
        task_id = data.replace("admin_remove_task_", "")
        await remove_task(update, context, task_id)
    elif data.startswith("admin_toggle_task_"):
        task_id = data.replace("admin_toggle_task_", "")
        await toggle_task(update, context, task_id)
    elif data == "admin_points_config":
        await show_points_config(update, context)
    elif data == "admin_edit_points":
        await prompt_edit_points(update, context)
    elif data == "admin_groups_menu":
        await groups_management(update, context)
    elif data == "admin_group_stats":
        await show_group_stats(update, context)
    elif data == "admin_broadcast_groups":
        await broadcast_to_groups_prompt(update, context)
    elif data == "admin_withdrawals":
        await view_withdrawals(update, context)
    elif data.startswith("admin_approve_"):
        withdrawal_id = data.replace("admin_approve_", "")
        await approve_withdrawal(update, context, withdrawal_id)
    elif data.startswith("admin_reject_"):
        withdrawal_id = data.replace("admin_reject_", "")
        await reject_withdrawal(update, context, withdrawal_id)
    elif data == "admin_broadcast_menu":
        await broadcast_menu(update, context)
    elif data == "admin_panel":
        from ..utils.helpers import create_admin_keyboard
        await query.message.edit_text(
            "🔐 *Admin Panel*",
            reply_markup=create_admin_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await query.answer("Feature coming soon!", show_alert=True)

async def show_admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
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

async def manage_channels_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    channels_list = list(get_collection("channels").find({"active": True}))
    
    keyboard = []
    for ch in channels_list:
        keyboard.append([
            InlineKeyboardButton(
                f"❌ {ch['channel_name']}", 
                callback_data=f"admin_remove_ch_{ch['_id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("➕ Add Channel", callback_data="admin_add_channel")])
    keyboard.append([InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")])
    
    await query.message.edit_text(
        "🔗 *Force Join Channels*\n\n"
        f"Active: *{len(channels_list)}*\n\n"
        "Click ❌ to remove\n"
        "Click ➕ to add new",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def prompt_add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.message.edit_text(
        "➕ *Add Force Join Channel*\n\n"
        "Send channel details in format:\n"
        "`/addchannel channel_id | @channel_name | invite_link`\n\n"
        "Example:\n"
        "`/addchannel -100123456 | @MyChannel | https://t.me/+abc123`",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="admin_manage_channels")]
        ]),
        parse_mode=ParseMode.MARKDOWN
    )

async def remove_channel(update: Update, context: ContextTypes.DEFAULT_TYPE, channel_id: str):
    query = update.callback_query
    get_collection("channels").delete_one({"_id": ObjectId(channel_id)})
    await query.answer("✅ Channel removed!", show_alert=True)
    await manage_channels_menu(update, context)

async def manage_links_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    links = list(get_collection("external_links").find({"active": True}))
    
    keyboard = []
    for link in links:
        keyboard.append([
            InlineKeyboardButton(
                f"❌ {link['name']}", 
                callback_data=f"admin_remove_link_{link['_id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("➕ Add Link", callback_data="admin_add_link")])
    keyboard.append([InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")])
    
    await query.message.edit_text(
        "🔗 *External Links*\n\n"
        f"Active: *{len(links)}*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def prompt_add_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.message.edit_text(
        "➕ *Add External Link*\n\n"
        "Use command:\n"
        "`/addlink name | url`\n\n"
        "Example:\n"
        "`/addlink Watch Video | https://youtube.com/...`",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="admin_manage_links")]
        ]),
        parse_mode=ParseMode.MARKDOWN
    )

async def remove_link(update: Update, context: ContextTypes.DEFAULT_TYPE, link_id: str):
    query = update.callback_query
    get_collection("external_links").delete_one({"_id": ObjectId(link_id)})
    await query.answer("✅ Link removed!", show_alert=True)
    await manage_links_menu(update, context)

async def manage_tasks_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    tasks_list = list(get_collection("tasks").find({}))
    
    keyboard = []
    for task in tasks_list:
        status = "✅" if task.get("active", True) else "❌"
        keyboard.append([
            InlineKeyboardButton(
                f"{status} {task['name']} ({task['points']}pts)", 
                callback_data=f"admin_toggle_task_{task['_id']}"
            ),
            InlineKeyboardButton(
                "🗑", 
                callback_data=f"admin_remove_task_{task['_id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("➕ Add Task", callback_data="admin_add_task")])
    keyboard.append([InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")])
    
    await query.message.edit_text(
        "📋 *Tasks Management*\n\n"
        f"Total: *{len(tasks_list)}*\n"
        "Click task to toggle active/inactive\n"
        "Click 🗑 to remove",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def prompt_add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.message.edit_text(
        "➕ *Add Task*\n\n"
        "Use command:\n"
        "`/addtask name | points | type | url`\n\n"
        "Types: `external`, `add_to_group`\n\n"
        "Example:\n"
        "`/addtask Watch Video | 50 | external | https://...`",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="admin_manage_tasks")]
        ]),
        parse_mode=ParseMode.MARKDOWN
    )

async def remove_task(update: Update, context: ContextTypes.DEFAULT_TYPE, task_id: str):
    query = update.callback_query
    get_collection("tasks").delete_one({"_id": ObjectId(task_id)})
    await query.answer("✅ Task removed!", show_alert=True)
    await manage_tasks_menu(update, context)

async def toggle_task(update: Update, context: ContextTypes.DEFAULT_TYPE, task_id: str):
    query = update.callback_query
    task = get_collection("tasks").find_one({"_id": ObjectId(task_id)})
    if task:
        new_status = not task.get("active", True)
        get_collection("tasks").update_one(
            {"_id": ObjectId(task_id)},
            {"$set": {"active": new_status}}
        )
        status_text = "activated" if new_status else "deactivated"
        await query.answer(f"✅ Task {status_text}!", show_alert=True)
    await manage_tasks_menu(update, context)

async def show_points_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    from ..utils.helpers import format_points_message
    
    keyboard = [
        [InlineKeyboardButton("✏️ Edit Points", callback_data="admin_edit_points")],
        [InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]
    ]
    
    await query.message.edit_text(
        format_points_message(),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def prompt_edit_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.message.edit_text(
        "✏️ *Edit Points*\n\n"
        "Use command:\n"
        "`/setpoints key value`\n\n"
        "Available keys:\n"
        "`refer_level_1`, `refer_level_2`,\n"
        "`group_add_small`, `group_add_medium`,\n"
        "`group_add_m2`, `group_add_m3`,\n"
        "`group_add_m4`, `group_add_big`,\n"
        "`min_withdraw`\n\n"
        "Example:\n"
        "`/setpoints refer_level_1 100`",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="admin_points_config")]
        ]),
        parse_mode=ParseMode.MARKDOWN
    )

async def groups_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    total_groups = get_collection("groups").count_documents({})
    
    keyboard = [
        [InlineKeyboardButton("📊 Group Statistics", callback_data="admin_group_stats")],
        [InlineKeyboardButton("📢 Broadcast to Groups", callback_data="admin_broadcast_groups")],
        [InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]
    ]
    
    await query.message.edit_text(
        "👥 *Groups Management*\n\n"
        f"Total Groups: *{total_groups}*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def show_group_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    groups = list(get_collection("groups").find({}).limit(10))
    
    if not groups:
        text = "No groups yet!"
    else:
        text = "📊 *Recent Groups:*\n\n"
        for g in groups:
            text += (
                f"📱 *{g.get('title', 'N/A')}*\n"
                f"👥 Members: {g.get('member_count', 0)}\n"
                f"💰 Reward: {g.get('reward_points', 0)} pts\n"
                f"📅 {g.get('added_at', 'N/A')}\n\n"
            )
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_groups_menu")]]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def broadcast_to_groups_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.message.edit_text(
        "📢 *Broadcast to Groups*\n\n"
        "Reply to a message with `/broadcastgroups`\n"
        "to send it to all groups where bot is admin.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="admin_groups_menu")]
        ]),
        parse_mode=ParseMode.MARKDOWN
    )

async def view_withdrawals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    pending = list(get_collection("withdraw_requests").find({"status": "pending"}).limit(5))
    
    if not pending:
        text = "✅ No pending withdrawals!"
        keyboard = [[InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]]
    else:
        text = "💰 *Pending Withdrawals:*\n\n"
        keyboard = []
        for req in pending:
            text += (
                f"🔢 *#{req['serial_no']}*\n"
                f"👤 {req.get('full_name', 'N/A')}\n"
                f"🆔 User ID: `{req['user_id']}`\n"
                f"💰 Points: {req['points']}\n"
                f"📅 {req['request_date'].strftime('%Y-%m-%d')}\n\n"
            )
            keyboard.append([
                InlineKeyboardButton(
                    f"✅ Approve #{req['serial_no']}", 
                    callback_data=f"admin_approve_{req['_id']}"
                )
            ])
        keyboard.append([InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")])
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def approve_withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE, withdrawal_id: str):
    """Atomic approval with status check to prevent double-processing."""
    query = update.callback_query
    
    req = get_collection("withdraw_requests").find_one_and_update(
        {
            "_id": ObjectId(withdrawal_id),
            "status": "pending"
        },
        {
            "$set": {
                "status": "completed",
                "processed_date": datetime.now()
            }
        },
        return_document=ReturnDocument.BEFORE
    )
    
    if not req:
        await query.answer("⚠️ Request already processed!", show_alert=True)
        await view_withdrawals(update, context)
        return
    
    try:
        await context.bot.send_message(
            req["user_id"],
            f"✅ *Withdrawal Approved!*\n\n"
            f"🔢 Token: #{req['serial_no']}\n"
            f"💰 Points: {req['points']}\n\n"
            f"Your ID will be sent shortly.",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Failed to notify user {req['user_id']}: {e}")
    
    await query.answer("✅ Withdrawal approved!", show_alert=True)
    await view_withdrawals(update, context)

async def reject_withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE, withdrawal_id: str):
    """Atomic rejection with one-time point refund."""
    query = update.callback_query
    
    req = get_collection("withdraw_requests").find_one_and_update(
        {
            "_id": ObjectId(withdrawal_id),
            "status": "pending"
        },
        {
            "$set": {
                "status": "rejected",
                "processed_date": datetime.now()
            }
        },
        return_document=ReturnDocument.BEFORE
    )
    
    if not req:
        await query.answer("⚠️ Request already processed!", show_alert=True)
        await view_withdrawals(update, context)
        return
    
    get_collection("users").update_one(
        {"user_id": req["user_id"]},
        {"$inc": {"points": req["points"]}}
    )
    
    try:
        await context.bot.send_message(
            req["user_id"],
            f"❌ *Withdrawal Rejected*\n\n"
            f"🔢 Token: #{req['serial_no']}\n"
            f"💰 Points refunded: {req['points']}",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Failed to notify user {req['user_id']}: {e}")
    
    await query.answer("❌ Rejected & points refunded!", show_alert=True)
    await view_withdrawals(update, context)

async def broadcast_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    await query.message.edit_text(
        "📢 *Broadcast to Users*\n\n"
        "1. Send your message here\n"
        "2. Reply with `/broadcast`\n\n"
        "⚠️ Rate limit: 30 msg/sec",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]
        ]),
        parse_mode=ParseMode.MARKDOWN
    )
