from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from config import BOT_TOKEN, ADMIN_IDS, logger
from user_handlers import UserHandlers
from admin_handlers import AdminHandlers

def main():
    """Main bot application"""
    # Build application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # User Handlers
    application.add_handler(CommandHandler("start", UserHandlers.start))
    application.add_handler(CallbackQueryHandler(UserHandlers.handle_callback))
    
    # Admin Handlers
    application.add_handler(CommandHandler("admin", AdminHandlers.admin_command))
    application.add_handler(CommandHandler("add_task", AdminHandlers.add_task_command))
    application.add_handler(CommandHandler("send_broadcast", AdminHandlers.broadcast_message))
    application.add_handler(CommandHandler("add_id", AdminHandlers.add_id_command))
    application.add_handler(CommandHandler("remove_id", AdminHandlers.remove_id_command))
    application.add_handler(CommandHandler("set_withdraw", AdminHandlers.set_withdraw_settings))
    
    # Admin Callback Handlers
    application.add_handler(CallbackQueryHandler(
        AdminHandlers.handle_admin_callback,
        pattern="^(admin_|approve_withdraw_|reject_withdraw_|add_task_)"
    ))
    
    # Back to menu handler
    application.add_handler(CallbackQueryHandler(
        UserHandlers.show_main_menu,
        pattern="^back_to_menu$"
    ))
    
    # Admin back handler
    application.add_handler(CallbackQueryHandler(
        AdminHandlers.admin_command,
        pattern="^admin_back$"
    ))
    
    # Start the bot
    logger.info("🚀 Bot started successfully!")
    logger.info(f"👥 Admin IDs: {ADMIN_IDS}")
    logger.info("📊 Bot is running...")
    
    # Run the bot
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()    application.add_handler(CallbackQueryHandler(
        AdminHandlers.admin_command,
        pattern="^admin_back$"
    ))
    
    # Start the bot
    logger.info("🚀 Bot started successfully!")
    logger.info(f"👥 Admin IDs: {ADMIN_IDS}")
    logger.info("📊 Bot is running...")
    
    # Run the bot
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()        
        # Admin Callback Handlers
        application.add_handler(CallbackQueryHandler(
            AdminHandlers.handle_admin_callback,
            pattern="^(admin_|approve_withdraw_|reject_withdraw_|add_task_)"
        ))
        
        # Back to menu handler
        application.add_handler(CallbackQueryHandler(
            UserHandlers.show_main_menu,
            pattern="^back_to_menu$"
        ))
        
        # Admin back handler
        application.add_handler(CallbackQueryHandler(
            AdminHandlers.admin_command,
            pattern="^admin_back$"
        ))
        
        # Start the bot
        logger.info("🚀 Bot started successfully!")
        logger.info(f"👥 Admin IDs: {ADMIN_IDS}")
        logger.info("📊 Bot is running...")
        
        # Run the bot
        application.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"❌ Error starting bot: {e}")
        raise

if __name__ == "__main__":
    main()        
        # Admin Callback Handlers
        application.add_handler(CallbackQueryHandler(
            AdminHandlers.handle_admin_callback,
            pattern="^(admin_|approve_withdraw_|reject_withdraw_|add_task_)"
        ))
        
        # Back to menu handler
        application.add_handler(CallbackQueryHandler(
            UserHandlers.show_main_menu,
            pattern="^back_to_menu$"
        ))
        
        # Admin back handler
        application.add_handler(CallbackQueryHandler(
            AdminHandlers.admin_command,
            pattern="^admin_back$"
        ))
        
        # Start the bot
        logger.info("🚀 Bot started successfully!")
        logger.info(f"👥 Admin IDs: {ADMIN_IDS}")
        logger.info("📊 Bot is running...")
        
        # Run the bot
        application.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"❌ Error starting bot: {e}")
        raise

if __name__ == "__main__":
    main()            pattern="^(admin_|approve_withdraw_|reject_withdraw_|add_task_)"
        ))
        
        # Back to menu handler
        application.add_handler(CallbackQueryHandler(
            UserHandlers.show_main_menu,
            pattern="^back_to_menu$"
        ))
        
        # Admin back handler
        application.add_handler(CallbackQueryHandler(
            AdminHandlers.admin_command,
            pattern="^admin_back$"
        ))
        
        # Start the bot
        logger.info("🚀 Bot started successfully!")
        logger.info(f"👥 Admin IDs: {ADMIN_IDS}")
        logger.info("📊 Bot is running...")
        
        # Run the bot with error handling
        try:
            application.run_polling(drop_pending_updates=True)
        except AttributeError as e:
            if "_Updater__polling_cleanup_cb" in str(e):
                logger.warning("Handling polling cleanup error...")
                application.run_polling()
            else:
                raise
        
    except Exception as e:
        logger.error(f"❌ Error starting bot: {e}")
        raise

if __name__ == "__main__":
    main()
