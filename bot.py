from telegram.ext import Updater, CommandHandler, CallbackQueryHandler
from config import BOT_TOKEN, ADMIN_IDS, logger
from user_handlers import UserHandlers
from admin_handlers import AdminHandlers
import os
import sys

def main():
    """Main bot application using Updater (sync)"""
    # Create updater
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    
    # User Handlers
    dp.add_handler(CommandHandler("start", UserHandlers.start))
    dp.add_handler(CallbackQueryHandler(UserHandlers.handle_callback))
    
    # Admin Handlers
    dp.add_handler(CommandHandler("admin", AdminHandlers.admin_command))
    dp.add_handler(CommandHandler("add_task", AdminHandlers.add_task_command))
    dp.add_handler(CommandHandler("send_broadcast", AdminHandlers.broadcast_message))
    dp.add_handler(CommandHandler("add_id", AdminHandlers.add_id_command))
    dp.add_handler(CommandHandler("remove_id", AdminHandlers.remove_id_command))
    dp.add_handler(CommandHandler("set_withdraw", AdminHandlers.set_withdraw_settings))
    
    # Admin Callback Handlers
    dp.add_handler(CallbackQueryHandler(AdminHandlers.handle_admin_callback, pattern="^(admin_|approve_withdraw_|reject_withdraw_|add_task_)"))
    
    # Back to menu handler
    dp.add_handler(CallbackQueryHandler(UserHandlers.show_main_menu, pattern="^back_to_menu$"))
    
    # Admin back handler
    dp.add_handler(CallbackQueryHandler(AdminHandlers.admin_command, pattern="^admin_back$"))
    
    logger.info("🚀 Bot started successfully!")
    logger.info(f"👥 Admin IDs: {ADMIN_IDS}")
    logger.info("📊 Bot is running...")
    
    # Start polling (not webhook)
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
