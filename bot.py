from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from config import BOT_TOKEN, ADMIN_IDS, logger
from user_handlers import UserHandlers
from admin_handlers import AdminHandlers
import asyncio
import nest_asyncio

# Apply nest_asyncio to fix event loop issues
nest_asyncio.apply()

def main():
    """Main bot application"""
    # Create event loop if not exists
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
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
    
    # Start the bot
    logger.info("🚀 Bot started successfully!")
    logger.info(f"👥 Admin IDs: {ADMIN_IDS}")
    logger.info("📊 Bot is running...")
    
    # Run the bot with event loop fix
    try:
        app.run_polling(drop_pending_updates=True)
    except RuntimeError as e:
        if "no current event loop" in str(e):
            # Create new event loop and try again
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            app.run_polling(drop_pending_updates=True)
        else:
            raise

if __name__ == "__main__":
    main()
