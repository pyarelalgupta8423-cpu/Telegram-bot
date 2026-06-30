from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from config import BOT_TOKEN, ADMIN_IDS, logger
from user_handlers import UserHandlers
from admin_handlers import AdminHandlers
import asyncio

async def run_bot():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", UserHandlers.start))
    app.add_handler(CallbackQueryHandler(UserHandlers.handle_callback))
    app.add_handler(CommandHandler("admin", AdminHandlers.admin_command))
    app.add_handler(CommandHandler("add_task", AdminHandlers.add_task_command))
    app.add_handler(CommandHandler("send_broadcast", AdminHandlers.broadcast_message))
    app.add_handler(CommandHandler("add_id", AdminHandlers.add_id_command))
    app.add_handler(CommandHandler("remove_id", AdminHandlers.remove_id_command))
    app.add_handler(CommandHandler("set_withdraw", AdminHandlers.set_withdraw_settings))
    app.add_handler(CallbackQueryHandler(AdminHandlers.handle_admin_callback, pattern="^(admin_|approve_withdraw_|reject_withdraw_|add_task_)"))
    app.add_handler(CallbackQueryHandler(UserHandlers.show_main_menu, pattern="^back_to_menu$"))
    app.add_handler(CallbackQueryHandler(AdminHandlers.admin_command, pattern="^admin_back$"))
    
    logger.info("🚀 Bot started successfully!")
    logger.info(f"👥 Admin IDs: {ADMIN_IDS}")
    logger.info("📊 Bot is running...")
    
    await app.run_polling(drop_pending_updates=True)

def main():
    try:
        asyncio.run(run_bot())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_bot())

if __name__ == "__main__":
    main()
