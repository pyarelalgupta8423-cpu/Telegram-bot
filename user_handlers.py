from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from models import User, Task, WithdrawRequest, WithdrawSettings
from utils import check_force_join, process_referral, generate_progress_keyboard, get_main_menu_keyboard
from config import FORCE_JOIN_CHANNELS, EXTERNAL_LINKS, ADMIN_IDS, logger, DEFAULT_POINTS
import random

class UserHandlers:
    
    @staticmethod
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler"""
        user = update.effective_user
        user_id = user.id
        
        # Create or get user
        db_user = User.get_or_create(user_id, user.username, user.first_name)
        
        # Check for referral code
        if context.args:
            try:
                referrer_id = int(context.args[0])
                if referrer_id != user_id and not db_user.get('referred_by'):
                    # Process referral
                    success = await process_referral(referrer_id, user_id, context)
                    if success:
                        User.collection.update_one(
                            {'user_id': user_id},
                            {'$set': {'referred_by': referrer_id}}
                        )
                        
                        await update.message.reply_text(
                            f"🎉 **You were referred!**\n\n"
                            f"Referrer ID: `{referrer_id}`\n"
                            f"✨ You received 0 points (referrer gets bonus)\n"
                            f"📝 Complete tasks to earn points!",
                            parse_mode='Markdown'
                        )
            except ValueError:
                pass
        
        # Check force join
        if not await check_force_join(update, context):
            keyboard = []
            for channel in FORCE_JOIN_CHANNELS:
                keyboard.append([InlineKeyboardButton(
                    f"📢 Join Channel", 
                    url=f"https://t.me/{channel}" if isinstance(channel, str) else f"https://t.me/c/{channel}"
                )])
            keyboard.append([InlineKeyboardButton("✅ Check Again", callback_data="check_join")])
            
            await update.message.reply_text(
                "⚠️ **Please join our channels to continue:**\n\n"
                "1️⃣ Join all channels below\n"
                "2️⃣ Click Check Again after joining\n\n"
                "🔗 **Required Channels:**",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return
        
        # Show main menu
        await UserHandlers.show_main_menu(update, context)
    
    @staticmethod
    async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show main menu"""
        user_id = update.effective_user.id
        user = User.collection.find_one({'user_id': user_id})
        
        message_text = f"""
🤖 **Welcome to the ID Bot!**

📊 **Your Stats:**
💰 Points: {user.get('points', 0)}
👥 Referrals: {len(user.get('referrals', []))}
📝 Tasks Completed: {len(user.get('completed_tasks', []))}

🎯 **Choose an option below:**
        """
        
        if update.callback_query:
            await update.callback_query.message.edit_text(
                message_text,
                reply_markup=get_main_menu_keyboard(),
                parse_mode='Markdown'
            )
            await update.callback_query.answer()
        else:
            await update.message.reply_text(
                message_text,
                reply_markup=get_main_menu_keyboard(),
                parse_mode='Markdown'
            )
    
    @staticmethod
    async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        data = query.data
        
        if data == "check_join":
            if await check_force_join(update, context):
                await query.message.delete()
                await UserHandlers.show_main_menu(update, context)
            else:
                await query.message.reply_text("❌ You haven't joined all channels yet. Please join and try again.")
        
        elif data == "get_id":
            await UserHandlers.get_id_menu(update, context)
        
        elif data == "withdraw_request":
            await UserHandlers.withdraw_request(update, context)
        
        elif data == "withdraw_history":
            await UserHandlers.withdraw_history(update, context)
        
        elif data == "withdraw_info":
            await UserHandlers.withdraw_info(update, context)
        
        elif data == "refer_to_get":
            await UserHandlers.refer_to_get(update, context)
        
        elif data == "available_ids":
            await UserHandlers.available_ids(update, context)
        
        elif data == "tasks":
            await UserHandlers.show_tasks(update, context)
        
        elif data == "referral_system":
            await UserHandlers.show_referral_system(update, context)
        
        elif data == "my_stats":
            await UserHandlers.show_stats(update, context)
        
        elif data == "task_continue" or data == "task_complete":
            await UserHandlers.handle_task_progress(update, context)
    
    @staticmethod
    async def get_id_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get ID (Withdraw) menu"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        user = User.collection.find_one({'user_id': user_id})
        settings = WithdrawSettings.get_settings()
        
        # Check if withdraw is active
        if not settings.get('is_active', True):
            await query.message.reply_text(
                "⚠️ ID withdrawal is currently disabled by admin."
            )
            return
        
        # Check minimum points
        if user.get('points', 0) < settings.get('min_points', 100):
            await query.message.reply_text(
                f"❌ **Insufficient points!**\n\n"
                f"Minimum points required: {settings.get('min_points')}\n"
                f"Your points: {user.get('points', 0)}\n\n"
                f"Complete more tasks to earn points!",
                parse_mode='Markdown'
            )
            return
        
        # Show withdraw options
        keyboard = [
            [InlineKeyboardButton("🎯 Request New ID", callback_data="withdraw_request")],
            [InlineKeyboardButton("📋 My Requests", callback_data="withdraw_history")],
            [InlineKeyboardButton("ℹ️ Withdraw Info", callback_data="withdraw_info")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")]
        ]
        
        available_count = len(settings.get('available_ids', []))
        
        await query.message.edit_text(
            f"🎯 **ID Withdrawal System**\n\n"
            f"💰 Your Points: {user.get('points', 0)}\n"
            f"📊 Minimum Points: {settings.get('min_points')}\n"
            f"💎 Points per ID: {settings.get('points_per_id', 50)}\n"
            f"📦 Available IDs: {available_count}\n\n"
            f"Select an option:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    @staticmethod
    async def withdraw_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Request a new ID withdrawal"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        user = User.collection.find_one({'user_id': user_id})
        settings = WithdrawSettings.get_settings()
        
        # Check conditions
        if user.get('points', 0) < settings.get('min_points', 100):
            await query.message.reply_text(
                f"❌ Insufficient points!\n"
                f"Required: {settings.get('min_points')}, Your: {user.get('points', 0)}"
            )
            return
        
        # Check available IDs
        available_ids = settings.get('available_ids', [])
        if not available_ids:
            await query.message.reply_text(
                "❌ No IDs available!\n"
                "Admin will add IDs soon. Please try again later."
            )
            return
        
        # Create withdraw request
        points_to_use = settings.get('points_per_id', 50)
        request_id = WithdrawRequest.create_request(user_id, points_to_use)
        
        # Deduct points
        User.update_points(user_id, -points_to_use)
        
        # Remove ID from available pool
        id_to_provide = available_ids[0]
        WithdrawSettings.remove_available_id(id_to_provide)
        
        # Get request details
        request = WithdrawRequest.collection.find_one({'_id': request_id})
        
        # Notify admins
        for admin_id in ADMIN_IDS:
            try:
                keyboard = [
                    [InlineKeyboardButton("✅ Approve", callback_data=f"approve_withdraw_{request_id}")],
                    [InlineKeyboardButton("❌ Reject", callback_data=f"reject_withdraw_{request_id}")]
                ]
                
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"🔔 **New Withdraw Request!**\n\n"
                         f"👤 User: {query.from_user.username or query.from_user.first_name}\n"
                         f"🆔 User ID: `{user_id}`\n"
                         f"🔢 Serial Number: `{request['serial_number']}`\n"
                         f"🔑 Token: `{request['token']}`\n"
                         f"💰 Points Used: {points_to_use}\n"
                         f"📦 ID to Provide: `{id_to_provide}`\n"
                         f"📅 Requested: {request['created_at'].strftime('%Y-%m-%d %H:%M')}\n\n"
                         f"⚠️ Provide this ID to user and click Approve",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Could not notify admin {admin_id}: {e}")
        
        # Show user confirmation
        await query.message.edit_text(
            f"✅ **Withdraw Request Submitted!**\n\n"
            f"🔢 Serial Number: `{request['serial_number']}`\n"
            f"🔑 Your Token: `{request['token']}`\n"
            f"💰 Points Deducted: {points_to_use}\n"
            f"📅 Request Time: {request['created_at'].strftime('%Y-%m-%d %H:%M')}\n\n"
            f"📝 **Next Steps:**\n"
            f"1️⃣ Copy your token number\n"
            f"2️⃣ Send this token to admin\n"
            f"3️⃣ Admin will verify and provide your ID\n"
            f"4️⃣ You'll receive notification when approved\n\n"
            f"⚠️ Keep your token safe! Don't share it with anyone.",
            parse_mode='Markdown'
        )
    
    @staticmethod
    async def withdraw_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user's withdraw history"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        requests = WithdrawRequest.get_user_requests(user_id)
        
        if not requests:
            await query.message.reply_text(
                "📋 No withdrawal requests found.\n"
                "Use 'Request New ID' to get started."
            )
            return
        
        message = "📋 **Your Withdrawal History**\n\n"
        for req in requests[:10]:
            status_emoji = {
                'pending': '⏳',
                'approved': '✅',
                'rejected': '❌',
                'completed': '🎉'
            }.get(req.get('status'), '❓')
            
            message += f"{status_emoji} **#{req.get('serial_number')}**\n"
            message += f"   💰 Points: {req.get('points_used')}\n"
            message += f"   📊 Status: {req.get('status').title()}\n"
            message += f"   📅 Date: {req.get('created_at').strftime('%Y-%m-%d %H:%M')}\n"
            
            if req.get('provided_id'):
                message += f"   🆔 ID: `{req.get('provided_id')}`\n"
            if req.get('rejection_reason'):
                message += f"   📝 Reason: {req.get('rejection_reason')}\n"
            message += "\n"
        
        if len(requests) > 10:
            message += f"... and {len(requests)-10} more"
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="get_id")]]
        await query.message.edit_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    @staticmethod
    async def withdraw_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show withdraw system information"""
        query = update.callback_query
        await query.answer()
        
        settings = WithdrawSettings.get_settings()
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="get_id")]]
        
        await query.message.edit_text(
            f"ℹ️ **ID Withdrawal System**\n\n"
            f"**How it works:**\n"
            f"1️⃣ Earn points by completing tasks\n"
            f"2️⃣ Request ID when you have minimum points\n"
            f"3️⃣ Points will be deducted from your balance\n"
            f"4️⃣ You'll receive a unique token number\n"
            f"5️⃣ Send token to admin to get your ID\n\n"
            f"**Current Settings:**\n"
            f"💰 Minimum Points: {settings.get('min_points', 100)}\n"
            f"💎 Points per ID: {settings.get('points_per_id', 50)}\n"
            f"📦 Available IDs: {len(settings.get('available_ids', []))}\n\n"
            f"⚠️ Once approved, ID is final and cannot be changed.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    @staticmethod
    async def refer_to_get(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show referral system to get IDs"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        user = User.collection.find_one({'user_id': user_id})
        referrals = user.get('referrals', [])
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")]]
        
        if referrals:
            ref_list = "\n".join([f"• User `{ref}`" for ref in referrals[:10]])
            if len(referrals) > 10:
                ref_list += f"\n... and {len(referrals)-10} more"
        else:
            ref_list = "No referrals yet"
        
        await query.message.edit_text(
            f"👥 **Your Referrals**\n\n"
            f"📊 Total Referrals: {len(referrals)}\n"
            f"📋 List:\n{ref_list}\n\n"
            f"🔗 **Your Referral Link:**\n"
            f"`https://t.me/{context.bot.username}?start={user_id}`\n\n"
            f"📝 Share this link with others to earn points!\n"
            f"Each successful referral gives you {DEFAULT_POINTS['refer_level1']} points!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    @staticmethod
    async def available_ids(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show available IDs count"""
        query = update.callback_query
        await query.answer()
        
        settings = WithdrawSettings.get_settings()
        available_ids = settings.get('available_ids', [])
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")]]
        
        await query.message.edit_text(
            f"📊 **Available IDs**\n\n"
            f"📦 Total Available: {len(available_ids)}\n"
            f"🔢 IDs: {', '.join(available_ids[:20]) if available_ids else 'None'}\n\n"
            f"💡 Use 'Get ID' option to withdraw an ID using your points.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    @staticmethod
    async def show_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show tasks with progress simulation"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        user = User.collection.find_one({'user_id': user_id})
        
        tasks = Task.get_active_tasks()
        completed_tasks = user.get('completed_tasks', [])
        
        if not tasks:
            await query.message.reply_text("📝 No tasks available currently.")
            return
        
        message = "📝 **Available Tasks**\n\n"
        for task in tasks:
            status = "✅" if str(task['_id']) in completed_tasks else "⏳"
            message += f"{status} **{task['title']}** - {task['points']} points\n"
            message += f"   {task['description']}\n\n"
        
        # Random task with progress simulation
        pending_tasks = [t for t in tasks if str(t['_id']) not in completed_tasks]
        if pending_tasks:
            random_task = random.choice(pending_tasks)
            message += f"\n🎯 **Current Task:** {random_task['title']}"
            message += f"\nComplete this task to earn {random_task['points']} points!"
            
            context.user_data['current_task'] = str(random_task['_id'])
            keyboard = generate_progress_keyboard()
            keyboard.inline_keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")])
        else:
            message += "\n✅ You've completed all tasks!"
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")]]
        
        await query.message.edit_text(
            message,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    
    @staticmethod
    async def show_referral_system(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show referral system information"""
        query = update.callback_query
        await query.answer()
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")]]
        
        await query.message.edit_text(
            f"🏆 **Referral System**\n\n"
            f"💰 Level 1 Bonus: {DEFAULT_POINTS['refer_level1']} points\n"
            f"💰 Level 2 Bonus: {DEFAULT_POINTS['refer_level2']} points\n\n"
            f"**How it works:**\n"
            f"1️⃣ Share your referral link\n"
            f"2️⃣ When someone joins with your link, you get Level 1 bonus\n"
            f"3️⃣ If they refer someone, you get Level 2 bonus\n"
            f"4️⃣ Referral must complete force join to count\n\n"
            f"**Your Referral Link:**\n"
            f"`https://t.me/{context.bot.username}?start={update.effective_user.id}`",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    @staticmethod
    async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user statistics"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        user = User.collection.find_one({'user_id': user_id})
        settings = WithdrawSettings.get_settings()
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")]]
        
        next_level = settings.get('min_points', 100) - user.get('points', 0)
        next_level = max(0, next_level)
        
        await query.message.edit_text(
            f"📈 **Your Statistics**\n\n"
            f"👤 User ID: `{user_id}`\n"
            f"👤 Name: {user.get('first_name', 'N/A')}\n"
            f"💰 Points: {user.get('points', 0)}\n"
            f"👥 Referrals: {len(user.get('referrals', []))}\n"
            f"📝 Tasks Completed: {len(user.get('completed_tasks', []))}\n"
            f"📅 Joined: {user.get('join_date', 'N/A').strftime('%Y-%m-%d %H:%M') if user.get('join_date') else 'N/A'}\n\n"
            f"🎯 Next Withdraw: {next_level} points needed\n"
            f"💎 Points per ID: {settings.get('points_per_id', 50)}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    @staticmethod
    async def handle_task_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle task progress with simulated tracking"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        
        if 'task_attempts' not in context.user_data:
            context.user_data['task_attempts'] = 0
        
        context.user_data['task_attempts'] += 1
        
        # Randomly decide when to complete (2-3 attempts)
        if context.user_data['task_attempts'] >= random.randint(2, 3):
            # Task completed
            if 'current_task' in context.user_data:
                task_id = context.user_data['current_task']
                task = Task.collection.find_one({'_id': task_id})
                if task:
                    User.update_points(user_id, task['points'])
                    User.collection.update_one(
                        {'user_id': user_id},
                        {'$push': {'completed_tasks': str(task_id)}}
                    )
                    
                    await query.message.edit_text(
                        f"✅ **Task Completed!**\n\n"
                        f"🎉 You earned {task['points']} points!\n"
                        f"💰 Total Points: {User.collection.find_one({'user_id': user_id}).get('points', 0)}\n\n"
                        f"Keep completing tasks to earn more points!",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📝 View Tasks", callback_data="tasks")]])
                    )
                else:
                    await query.message.edit_text("❌ Task not found.")
            
            context.user_data['task_attempts'] = 0
        else:
            # Simulate incomplete
            messages = [
                "⏳ Please complete the task properly.",
                "⚠️ You haven't completed all requirements yet.",
                "🔄 Please try again after completing the task.",
                "📝 Make sure you've done everything required."
            ]
            await query.message.edit_text(
                f"{random.choice(messages)}\n\n"
                f"🔄 Attempt {context.user_data['task_attempts']} of 3"
          )
