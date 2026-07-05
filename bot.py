import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    ChatMemberHandler, ContextTypes
)
from telegram.constants import ParseMode
from config import BOT_TOKEN, ADMIN_IDS
from database import *
from reward_service import (
    credit_group_reward_atomic,
    create_group_pending_reward
)
from handlers.callback_manager import callback_router
from handlers.user_handlers import (
    check_force_join,
    handle_referral_points,
    ensure_user_verified,
    process_pending_group_rewards
)
from handlers.task_handlers import complete_verification
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    
    user_data = get_user(user.id)
    
    get_collection("users").update_one(
        {"user_id": user.id},
        {"$set": {
            "username": user.username or "",
            "full_name": user.full_name
        }}
    )
    
    # Handle referral link
    if args and args[0].startswith("ref_"):
        try:
            referrer_id = int(args[0].replace("ref_", ""))
            if referrer_id != user.id:
                referrer = get_collection("users").find_one({"user_id": referrer_id})
                if referrer and not user_data.get("referred_by") and not user_data.get("referral_rewarded"):
                    get_collection("users").update_one(
                        {"user_id": user.id},
                        {"$set": {"pending_referrer": referrer_id}}
                    )
        except ValueError:
            pass
    
    # Check force join
    not_joined = await check_force_join(user.id, context)
    
    if not_joined:
        keyboard = []
        for ch in not_joined:
            keyboard.append([
                InlineKeyboardButton(f"📢 Join {ch['channel_name']}", url=ch['invite_link'])
            ])
        keyboard.append([
            InlineKeyboardButton("✅ Check & Continue", callback_data="check_join")
        ])
        
        await update.message.reply_text(
            "👋 *Welcome!*\n\n"
            "⚠️ *Join all required channels to continue:*\n\n"
            "Click 'Check & Continue' after joining",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Check verification version
    current_version = get_verification_version()
    if user_data.get("verification_version", 0) != current_version:
        get_collection("users").update_one(
            {"user_id": user.id},
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
        user_data = get_user(user.id)
    
    # Already fully verified
    if user_data.get("force_join_completed") and user_data.get("external_tasks_completed"):
        from utils.helpers import create_main_menu_keyboard
        await update.message.reply_text(
            "👋 *Welcome Back!*\n\n✅ All verifications complete\nChoose an option:",
            reply_markup=create_main_menu_keyboard(user.id),
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        get_collection("users").update_one(
            {"user_id": user.id},
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
            
            await update.message.reply_text(
                "✅ *Channels Joined!*\n\n"
                "📋 *Now Complete External Tasks:*\n\n"
                "• Click each link and complete\n"
                "• Then click 'I've Completed All'\n\n"
                "⚠️ Multiple confirmations required",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            current_ver = get_verification_version()
            get_collection("users").update_one(
                {"user_id": user.id},
                {
                    "$set": {
                        "external_tasks_completed": True,
                        "verification_version": current_ver
                    },
                    "$unset": {
                        "verification.external_required": "",
                        "verification.external_attempts": ""
                    }
                }
            )
            
            await process_pending_group_rewards(user.id, context)
            
            updated_user = get_user(user.id)
            pending_referrer = updated_user.get("pending_referrer")
            if pending_referrer:
                await handle_referral_points(user.id, pending_referrer, context)
            
            from utils.helpers import create_main_menu_keyboard
            await update.message.reply_text(
                "🎉 *All Verifications Complete!*\n\nChoose an option:",
                reply_markup=create_main_menu_keyboard(user.id),
                parse_mode=ParseMode.MARKDOWN
            )

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    from utils.helpers import create_admin_keyboard
    
    await update.message.reply_text(
        "🔐 *Admin Panel*\n\nSelect an option:",
        reply_markup=create_admin_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

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
            await status_msg.edit_text(
                f"📢 Broadcasting...\n✅ {success} | ❌ {failed} | 📊 {i}/{total}"
            )
        
        await asyncio.sleep(0.05)
    
    await status_msg.edit_text(
        f"✅ Broadcast Complete!\n✅ {success} | ❌ {failed} | 📊 {total}"
    )

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
            await status_msg.edit_text(
                f"📢 Broadcasting...\n✅ {success} | ❌ {failed} | 📊 {i}/{len(groups)}"
            )
        
        await asyncio.sleep(0.1)
    
    await status_msg.edit_text(
        f"✅ Broadcast to Groups Complete!\n✅ {success} | ❌ {failed}"
    )

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
            "channel_id": channel_id,
            "channel_name": channel_name,
            "invite_link": invite_link,
            "active": True,
            "added_date": datetime.now()
        })
        
        await update.message.reply_text(f"✅ Channel {channel_name} added successfully!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}\n\nFormat: /addchannel channel_id | @name | link")

async def add_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    try:
        text = update.message.text.replace("/addlink ", "")
        parts = text.split("|")
        name = parts[0].strip()
        url = parts[1].strip()
        
        get_collection("external_links").insert_one({
            "name": name,
            "url": url,
            "active": True,
            "added_date": datetime.now()
        })
        
        increment_verification_version()
        
        await update.message.reply_text(
            f"✅ External link '{name}' added!\n"
            "🔄 Verification version updated - all users must re-verify."
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}\n\nFormat: /addlink name | url")

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
            "name": name,
            "points": points,
            "type": task_type,
            "url": url,
            "active": True,
            "created_date": datetime.now()
        })
        
        await update.message.reply_text(f"✅ Task '{name}' added! ({points} pts)")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}\n\nFormat: /addtask name | points | type | url")

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
            await update.message.reply_text(f"✅ {key} updated to {value} points!")
        else:
            await update.message.reply_text(f"❌ Invalid key! Available: {', '.join(points.keys())}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}\n\nFormat: /setpoints key value")

async def handle_bot_added_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Secure group reward handler using atomic transactions."""
    chat_member_update = update.my_chat_member
    
    if chat_member_update.new_chat_member.status != "administrator":
        return
    
    chat = chat_member_update.chat
    added_by = chat_member_update.from_user
    
    if not added_by:
        logger.warning(f"Bot added to {chat.id} but from_user is None")
        return
    
    try:
        member_count = await context.bot.get_chat_member_count(chat.id)
    except Exception:
        member_count = 0
    
    points_config = get_points_config()
    points = 0
    
    if member_count < 100:
        points = points_config["group_add_small"]
    elif member_count <= 1000:
        points = points_config["group_add_medium"]
    elif member_count <= 2000:
        points = points_config["group_add_m2"]
    elif member_count <= 3000:
        points = points_config["group_add_m3"]
    elif member_count <= 5000:
        points = points_config["group_add_m4"]
    else:
        points = points_config["group_add_big"]
    
    # Register group first (idempotent)
    try:
        get_collection("groups").update_one(
            {"chat_id": chat.id},
            {
                "$setOnInsert": {
                    "chat_id": chat.id,
                    "reward_given": False,
                    "added_at": datetime.now()
                },
                "$set": {
                    "title": chat.title or "Unknown",
                    "member_count": member_count,
                    "added_by": added_by.id,
                    "reward_points": points
                }
            },
            upsert=True
        )
    except Exception as e:
        if "duplicate key" in str(e).lower() or "E11000" in str(e):
            logger.info(f"Group {chat.id} already registered")
        else:
            raise
    
    # Check if user is verified
    is_verified = await ensure_user_verified(added_by.id, context)
    
    if is_verified:
        result = credit_group_reward_atomic(
            chat.id, added_by.id, chat.title, member_count, points
        )
        
        if result:
            try:
                await context.bot.send_message(
                    added_by.id,
                    f"✅ *Group Reward Earned!*\n\n"
                    f"📱 Group: {chat.title}\n"
                    f"👥 Members: {member_count}\n"
                    f"💰 Points: *{points}*\n\n"
                    f"Thank you for adding the bot!",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Failed to notify user {added_by.id}: {e}")
            
            logger.info(f"Group reward credited: {chat.id} by {added_by.id}, {points} pts")
        else:
            logger.info(f"Group {chat.id} already rewarded or transaction failed")
    else:
        success = create_group_pending_reward(
            chat.id, added_by.id, chat.title, member_count, points
        )
        
        if success:
            try:
                await context.bot.send_message(
                    added_by.id,
                    "⚠️ *Group Reward Pending!*\n\n"
                    f"📱 Group: {chat.title}\n"
                    f"💰 Potential Reward: *{points}* points\n\n"
                    "❌ You must complete bot verification first!\n"
                    "Use /start and complete all requirements.\n"
                    "Your reward will be credited automatically after verification.",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Failed to notify unverified user {added_by.id}: {e}")
            
            logger.info(f"Pending reward created: {chat.id} by {added_by.id}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

def main():
    init_db()
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("broadcastgroups", broadcast_groups_command))
    application.add_handler(CommandHandler("addchannel", add_channel_command))
    application.add_handler(CommandHandler("addlink", add_link_command))
    application.add_handler(CommandHandler("addtask", add_task_command))
    application.add_handler(CommandHandler("setpoints", set_points_command))
    
    # ChatMemberHandler for bot being added to groups
    application.add_handler(
        ChatMemberHandler(handle_bot_added_to_group, ChatMemberHandler.MY_CHAT_MEMBER)
    )
    
    # Callback query handler - all callbacks routed here
    application.add_handler(CallbackQueryHandler(callback_router))
    
    # Error handler
    application.add_error_handler(error_handler)
    
    logger.info("Bot started successfully!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
