from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from config import BOT_TOKEN, ADMIN_IDS, logger
from user_handlers import UserHandlers
from admin_handlers import AdminHandlers
import os

def main():
    """Main bot application using webhook"""
    # Build application
    app = Application.builder().token(BOT_TOKEN).build()
    
    # User Handlers
    app.add_handler(CommandHandler("start", UserHandlers.start))
    app.add_handler(CallbackQueryHandler(UserHandlers.handle_callback))
    
    # Admin Handlers
    app.add_handler(CommandHandler("admin", AdminHandlers.admin_command))
    app.add_handler(CommandHandler("add_task", AdminHandlers.add_task_command))
    app.add_handler(CommandHandler("send_broadcast", AdminHandlers.broadcast_message))
    app.add_handler(CommandHandler("add_id", AdminHandlers.add_id_command))
    app.add_handler(CommandHandler("remove_id", AdminHandlers.remove_id_command))
    app.add_handler(CommandHandler("set_withdraw", AdminHandlers.set_withdraw_settings))
    
    # Admin Callback Handlers
    app.add_handler(CallbackQueryHandler(AdminHandlers.handle_admin_callback, pattern="^(admin_|approve_withdraw_|reject_withdraw_|add_task_)"))
    
    # Back to menu handler
    app.add_handler(CallbackQueryHandler(UserHandlers.show_main_menu, pattern="^back_to_menu$"))
    
    # Admin back handler
    app.add_handler(CallbackQueryHandler(AdminHandlers.admin_command, pattern="^admin_back$"))
    
    logger.info("🚀 Bot started successfully!")
    logger.info(f"👥 Admin IDs: {ADMIN_IDS}")
    logger.info("📊 Bot is running...")
    
    # Use webhook instead of polling
    # Get port from environment variable (Render sets this)
    port = int(os.environ.get('PORT', 8443))
    
    # Start webhook
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=BOT_TOKEN,
        webhook_url=f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'your-app.onrender.com')}/{BOT_TOKEN}"
    )

if __name__ == "__main__":
    main()
