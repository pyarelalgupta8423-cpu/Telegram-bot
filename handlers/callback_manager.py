from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from handlers.user_handlers import *
from handlers.task_handlers import *
from handlers.admin_handlers import *
from database import *
from ..utils.helpers import create_main_menu_keyboard

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main callback router - handles ALL callbacks properly"""
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    
    # ============ MAIN MENU CALLBACKS ============
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
    
    # ============ VERIFICATION CALLBACKS ============
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
                keyboard.append([
                    InlineKeyboardButton(f"📢 Join {ch['channel_name']}", url=ch['invite_link'])
                ])
            keyboard.append([
                InlineKeyboardButton("✅ Check & Continue", callback_data="check_join")
            ])
            await query.message.edit_text(
                "⚠️ *Join Required Channels:*",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        else:
            await handle_force_join_complete(update, context)
    
    elif data == "ext_tasks_complete":
        await handle_external_tasks_complete(update, context)
    
    # ============ TASK CALLBACKS ============
    elif data.startswith("task_do_"):
        task_id = data.replace("task_do_", "")
        await handle_specific_task(update, context, task_id)
    
    elif data.startswith("task_verify_"):
        task_id = data.replace("task_verify_", "")
        await verify_task_completion(update, context, task_id)
    
    # ============ ADMIN CALLBACKS ============
    elif data == "admin_panel" or data.startswith("admin_"):
        await handle_admin_callbacks(update, context)
    
    else:
        await query.answer("❓ Unknown command", show_alert=True)
