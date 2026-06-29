from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from models import User, Task, Channel, Broadcast, WithdrawRequest, WithdrawSettings
from config import ADMIN_IDS, DEFAULT_POINTS, FORCE_JOIN_CHANNELS, EXTERNAL_LINKS, logger
import asyncio
from datetime import datetime

class AdminHandlers:
    
    @staticmethod
    async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin panel"""
        user_id = update.effective_user.id
        
        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ You are not authorized to use this command.")
            return
        
        keyboard = [
            [InlineKeyboardButton("👥 Total Users", callback_data="admin_total_users")],
            [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
            [InlineKeyboardButton("📚 Tasks", callback_data="admin_tasks")],
            [InlineKeyboardButton("📺 Channels/Groups", callback_data="admin_channels")],
            [InlineKeyboardButton("🎯 Withdraw Requests", callback_data="admin_withdraw_requests")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings")],
            [InlineKeyboardButton("📊 Analytics", callback_data="admin_analytics")]
        ]
        
        await update.message.reply_text(
            "🔐 **Admin Panel**\n\n"
            "Select an option:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    @staticmethod
    async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle admin callback queries"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        if user_id not in ADMIN_IDS:
            await query.message.reply_text("❌ Unauthorized access.")
            return
        
        data = query.data
        
        if data == "admin_total_users":
            await AdminHandlers.show_total_users(update, context)
        
        elif data == "admin_broadcast":
            await AdminHandlers.show_broadcast_menu(update, context)
        
        elif data == "admin_tasks":
            await AdminHandlers.show_task_menu(update, context)
        
        elif data == "admin_channels":
            await AdminHandlers.show_channel_management(update, context)
        
        elif data == "admin_withdraw_requests":
            await AdminHandlers.show_withdraw_requests(update, context)
        
        elif data == "admin_settings":
            await AdminHandlers.show_settings(update, context)
        
        elif data == "admin_analytics":
            await AdminHandlers.show_analytics(update, context)
        
        elif data.startswith("approve_withdraw_"):
            request_id = data.replace("approve_withdraw_", "")
            await AdminHandlers.approve_withdraw(update, context, request_id)
        
        elif data.startswith("reject_withdraw_"):
            request_id = data.replace("reject_withdraw_", "")
            await AdminHandlers.reject_withdraw(update, context, request_id)
        
        elif data.startswith("add_task_"):
            task_type = data.replace("add_task_", "")
            context.user_data['adding_task'] = task_type
            await query.message.reply_text(
                f"📝 Adding new task of type: {task_type}\n"
                f"Please send: /add_task <title> <points> <description>"
            )
    
    @staticmethod
    async def show_total_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show total users and stats"""
        stats = User.get_user_stats()
        channels = Channel.get_all_channels()
        pending_withdraw = len(WithdrawRequest.get_pending_requests())
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_back")]]
        
        await update.callback_query.message.edit_text(
            f"👥 **User Statistics**\n\n"
            f"📊 Total Users: {stats['total_users']}\n"
            f"💰 Total Points: {stats['total_points']}\n"
            f"📺 Channels/Group: {len(channels)}\n"
            f"🎯 Pending Withdrawals: {pending_withdraw}\n"
            f"📈 Avg Points/User: {stats['total_points']/stats['total_users'] if stats['total_users'] > 0 else 0:.2f}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    @staticmethod
    async def show_broadcast_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show broadcast menu"""
        keyboard = [
            [InlineKeyboardButton("📝 Text Broadcast", callback_data="broadcast_text")],
            [InlineKeyboardButton("🖼️ Media Broadcast", callback_data="broadcast_media")],
            [InlineKeyboardButton("🔙 Back", callback_data="admin_back")]
        ]
        
        await update.callback_query.message.edit_text(
            "📢 **Broadcast Menu**\n\n"
            "Select broadcast type:\n"
            "⚠️ Telegram spam limits apply (30 messages/second)",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    @staticmethod
    async def show_task_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show task management menu"""
        tasks = Task.get_active_tasks()
        
        message = "📚 **Task Management**\n\n"
        if tasks:
            for idx, task in enumerate(tasks, 1):
                message += f"{idx}. **{task['title']}** - {task['points']} pts\n"
                message += f"   Type: {task['type']}\n"
                message += f"   {task['description']}\n\n"
        else:
            message += "No active tasks.\n\n"
        
        keyboard = [
            [InlineKeyboardButton("➕ Add Force Join Task", callback_data="add_task_force_join")],
            [InlineKeyboardButton("➕ Add External Link Task", callback_data="add_task_external_link")],
            [InlineKeyboardButton("➕ Add Group/Channel Task", callback_data="add_task_group_channel")],
            [InlineKeyboardButton("🔙 Back", callback_data="admin_back")]
        ]
        
        await update.callback_query.message.edit_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    @staticmethod
    async def show_channel_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show channel management"""
        channels = Channel.get_all_channels()
        
        message = "📺 **Channels/Groups Management**\n\n"
        if channels:
            for idx, channel in enumerate(channels[:10], 1):
                message += f"{idx}. {channel.get('channel_name', 'Unknown')}\n"
                message += f"   👥 {channel.get('member_count', 0)} members\n"
                message += f"   🆔 `{channel.get('channel_id')}`\n\n"
            if len(channels) > 10:
                message += f"... and {len(channels)-10} more"
        else:
            message += "No channels/groups added yet."
        
        keyboard = [
            [InlineKeyboardButton("➕ Add Channel/Group", callback_data="admin_add_channel")],
            [InlineKeyboardButton("🔙 Back", callback_data="admin_back")]
        ]
        
        await update.callback_query.message.edit_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    @staticmethod
    async def show_withdraw_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show all pending withdraw requests"""
        requests = WithdrawRequest.get_pending_requests()
        
        if not requests:
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_back")]]
            await update.callback_query.message.edit_text(
                "✅ No pending withdrawal requests.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        message = "🔔 **Pending Withdraw Requests**\n\n"
        for req in requests[:20]:
            user = User.collection.find_one({'user_id': req['user_id']})
            username = user.get('username') if user else 'Unknown'
            
            message += f"🔢 #{req.get('serial_number')}\n"
            message += f"👤 User: @{username} (`{req['user_id']}`)\n"
            message += f"💰 Points: {req.get('points_used')}\n"
            message += f"🔑 Token: `{req.get('token')}`\n"
            message += f"📅 Date: {req.get('created_at').strftime('%Y-%m-%d %H:%M')}\n"
            message += f"📦 ID to Provide: `{req.get('provided_id')}`\n"
            message += f"---\n\n"
        
        if len(requests) > 20:
            message += f"... and {len(requests)-20} more"
        
        keyboard = [[InlineKeyboardButton("🔄 Refresh", callback_data="admin_withdraw_requests")],
                   [InlineKeyboardButton("🔙 Back", callback_data="admin_back")]]
        
        await update.callback_query.message.edit_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    @staticmethod
    async def approve_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE, request_id):
        """Approve a withdraw request"""
        request = WithdrawRequest.collection.find_one({'_id': request_id})
        if not request:
            await update.callback_query.message.reply_text("❌ Request not found.")
            return
        
        # Mark as approved
        WithdrawRequest.approve_request(request_id, request.get('provided_id'))
        
        # Notify user
        try:
            await context.bot.send_message(
                chat_id=request['user_id'],
                text=f"✅ **Your ID Withdrawal Request is Approved!**\n\n"
                     f"🔢 Serial Number: `{request['serial_number']}`\n"
                     f"🔑 Token: `{request['token']}`\n"
                     f"📦 Your ID: `{request['provided_id']}`\n\n"
                     f"🎉 Congratulations! Your ID is ready.\n"
                     f"📝 Keep this ID safe for future reference.",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Could not notify user: {e}")
        
        # Update admin message
        keyboard = [[InlineKeyboardButton("🔄 Refresh", callback_data="admin_withdraw_requests")]]
        await update.callback_query.message.edit_text(
            f"✅ **Withdraw Request Approved!**\n\n"
            f"🔢 Serial Number: `{request['serial_number']}`\n"
            f"👤 User ID: `{request['user_id']}`\n"
            f"🔑 Token: `{request['token']}`\n"
            f"📦 ID Provided: `{request['provided_id']}`\n"
            f"✅ Status: Approved",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    @staticmethod
    async def reject_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE, request_id):
        """Reject a withdraw request"""
        request = WithdrawRequest.collection.find_one({'_id': request_id})
        if not request:
            await update.callback_query.message.reply_text("❌ Request not found.")
            return
        
        # Return points to user
        User.update_points(request['user_id'], request.get('points_used', 0))
        
        # Reject request
        WithdrawRequest.reject_request(request_id, "Rejected by admin")
        
        # Notify user
        try:
            await context.bot.send_message(
                chat_id=request['user_id'],
                text=f"❌ **Your Withdrawal Request was Rejected**\n\n"
                     f"🔢 Serial Number: `{request['serial_number']}`\n"
                     f"💰 Points Returned: {request.get('points_used', 0)}\n"
                     f"📝 Reason: Rejected by admin\n\n"
                     f"Contact admin for more information.",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Could not notify user: {e}")
        
        keyboard = [[InlineKeyboardButton("🔄 Refresh", callback_data="admin_withdraw_requests")]]
        await update.callback_query.message.edit_text(
            f"❌ **Withdraw Request Rejected**\n\n"
            f"🔢 Serial Number: `{request['serial_number']}`\n"
            f"👤 User ID: `{request['user_id']}`\n"
            f"💰 Points Returned: {request.get('points_used', 0)}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    @staticmethod
    async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show bot settings"""
        points = DEFAULT_POINTS
        settings = WithdrawSettings.get_settings()
        
        message = f"""
⚙️ **Bot Settings**

**💰 Points Configuration:**
• Level 1 Referral: {points['refer_level1']}
• Level 2 Referral: {points['refer_level2']}
• Group/Channel Task: {points['task_points']['group_channel']}

**📈 Channel Points:**
• Small (<100): {points['task_points']['small']}
• Medium (101-1000): {points['task_points']['medium']}
• M2 (1001-2000): {points['task_points']['m2']}
• M3 (2001-3000): {points['task_points']['m3']}
• M4 (3001-5000): {points['task_points']['m4']}
• Big (5000+): {points['task_points']['big']}

**🎯 Withdraw Settings:**
• Min Points: {settings.get('min_points', 100)}
• Points per ID: {settings.get('points_per_id', 50)}
• Available IDs: {len(settings.get('available_ids', []))}
• Status: {'🟢 Active' if settings.get('is_active', True) else '🔴 Inactive'}

**🔧 Force Join Channels:** {len(FORCE_JOIN_CHANNELS)}
**🌐 External Links:** {len(EXTERNAL_LINKS)}
        """
        
        keyboard = [
            [InlineKeyboardButton("💰 Update Points", callback_data="admin_update_points")],
            [InlineKeyboardButton("📢 Force Join Channels", callback_data="admin_force_join")],
            [InlineKeyboardButton("🔗 External Links", callback_data="admin_external_links")],
            [InlineKeyboardButton("🎯 Withdraw Settings", callback_data="admin_withdraw_settings")],
            [InlineKeyboardButton("🔙 Back", callback_data="admin_back")]
        ]
        
        await update.callback_query.message.edit_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    @staticmethod
    async def show_analytics(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show bot analytics"""
        total_users = User.collection.count_documents({})
        total_channels = Channel.collection.count_documents({})
        
        points_pipeline = [
            {"$group": {"_id": None, "total_points": {"$sum": "$points"}}}
        ]
        points_result = User.collection.aggregate(points_pipeline)
        total_points = next(points_result, {}).get('total_points', 0)
        
        pending_withdraw = len(WithdrawRequest.get_pending_requests())
        total_withdraw = WithdrawRequest.collection.count_documents({})
        
        # Recent users
        recent_users = User.collection.find().sort('join_date', -1).limit(5)
        recent_list = "\n".join([f"• @{u.get('username', u['user_id'])}" for u in recent_users])
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_back")]]
        
        await update.callback_query.message.edit_text(
            f"📊 **Analytics Report**\n\n"
            f"👥 Total Users: {total_users}\n"
            f"📺 Total Channels: {total_channels}\n"
            f"💎 Total Points Distributed: {total_points}\n"
            f"📈 Avg Points/User: {total_points/total_users if total_users > 0 else 0:.2f}\n\n"
            f"🎯 Withdraw Statistics:\n"
            f"• Pending: {pending_withdraw}\n"
            f"• Total Requests: {total_withdraw}\n\n"
            f"🆕 Recent Users:\n{recent_list if recent_list else 'None'}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    @staticmethod
    async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Broadcast message to all users"""
        user_id = update.effective_user.id
        if user_id not in ADMIN_IDS:
            return
        
        message = update.message.text.replace('/send_broadcast', '').strip()
        
        if not message:
            await update.message.reply_text("❌ Please provide a message to broadcast.")
            return
        
        # Get all users
        users = User.get_all_users()
        total = len(users)
        
        if total == 0:
            await update.message.reply_text("❌ No users to broadcast to.")
            return
        
        # Send initial status
        status_msg = await update.message.reply_text(
            f"📢 Broadcasting started...\n"
            f"📊 Total users: {total}\n"
            f"⏳ Progress: 0/{total} (0%)"
        )
        
        sent = 0
        failed = 0
        
        # Send messages with delay to respect Telegram limits
        for idx, user in enumerate(users, 1):
            try:
                await context.bot.send_message(
                    chat_id=user['user_id'],
                    text=message,
                    parse_mode='Markdown'
                )
                sent += 1
            except Exception as e:
                failed += 1
                logger.error(f"Failed to send to {user['user_id']}: {e}")
            
            # Update status every 10 messages
            if idx % 10 == 0:
                progress = (idx / total) * 100
                await status_msg.edit_text(
                    f"📢 Broadcasting...\n"
                    f"📊 Total: {total}\n"
                    f"✅ Sent: {sent}\n"
                    f"❌ Failed: {failed}\n"
                    f"⏳ Progress: {idx}/{total} ({progress:.1f}%)"
                )
            
            # Respect Telegram limits - 30 messages/second
            await asyncio.sleep(0.5)
        
        # Final status
        await status_msg.edit_text(
            f"✅ **Broadcast Completed!**\n\n"
            f"📊 Total users: {total}\n"
            f"✅ Sent: {sent}\n"
            f"❌ Failed: {failed}\n"
            f"📅 Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
    
    @staticmethod
    async def add_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add a new task"""
        if update.effective_user.id not in ADMIN_IDS:
            return
        
        try:
            args = context.args
            if len(args) < 3:
                await update.message.reply_text(
                    "❌ **Usage:** /add_task <title> <points> <description>\n\n"
                    "Example: /add_task Complete Survey 50 Answer all questions",
                    parse_mode='Markdown'
                )
                return
            
            title = args[0]
            points = int(args[1])
            description = ' '.join(args[2:])
            
            # Determine task type
            task_type = 'external_link'  # Default
            if 'join' in title.lower() or 'channel' in title.lower():
                task_type = 'force_join'
            elif 'group' in title.lower() or 'channel' in title.lower():
                task_type = 'group_channel'
            
            task_data = {
                'title': title,
                'points': points,
                'description': description,
                'type': task_type
            }
            
            Task.add_task(task_data)
            await update.message.reply_text(
                f"✅ **Task Added Successfully!**\n\n"
                f"📝 Title: {title}\n"
                f"💰 Points: {points}\n"
                f"📋 Description: {description}\n"
                f"📊 Type: {task_type}"
            )
            
        except ValueError:
            await update.message.reply_text("❌ Invalid points value. Please provide a number.")
        except Exception as e:
            await update.message.reply_text(f"❌ Error adding task: {e}")
    
    @staticmethod
    async def add_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add ID to available pool"""
        if update.effective_user.id not in ADMIN_IDS:
            return
        
        args = context.args
        if not args:
            await update.message.reply_text(
                "❌ **Usage:** /add_id <telegram_id>\n"
                "Example: /add_id TG12345\n\n"
                "You can add multiple IDs at once:\n"
                "/add_id TG12345 TG67890 TG11111",
                parse_mode='Markdown'
            )
            return
        
        added = 0
        for id_value in args:
            if WithdrawSettings.add_available_id(id_value):
                added += 1
        
        await update.message.reply_text(
            f"✅ **IDs Added!**\n\n"
            f"Added: {added} ID(s)\n"
            f"📦 Total available: {len(WithdrawSettings.get_settings().get('available_ids', []))}\n\n"
            f"Added IDs: {', '.join(args[:5])}" + (f" ... and {len(args)-5} more" if len(args) > 5 else ""),
            parse_mode='Markdown'
        )
    
    @staticmethod
    async def remove_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Remove ID from available pool"""
        if update.effective_user.id not in ADMIN_IDS:
            return
        
        args = context.args
        if not args:
            await update.message.reply_text(
                "❌ **Usage:** /remove_id <id>\n"
                "Example: /remove_id TG12345",
                parse_mode='Markdown'
            )
            return
        
        removed = 0
        for id_value in args:
            if WithdrawSettings.remove_available_id(id_value):
                removed += 1
        
        await update.message.reply_text(
            f"✅ **IDs Removed!**\n\n"
            f"Removed: {removed} ID(s)\n"
            f"📦 Total available: {len(WithdrawSettings.get_settings().get('available_ids', []))}",
            parse_mode='Markdown'
        )
    
    @staticmethod
    async def set_withdraw_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set withdraw settings"""
        if update.effective_user.id not in ADMIN_IDS:
            return
        
        args = context.args
        if len(args) < 2:
            await update.message.reply_text(
                "❌ **Usage:** /set_withdraw <setting> <value>\n\n"
                "Settings:\n"
                "• min_points <number>\n"
                "• points_per_id <number>\n"
                "• status <on/off>\n\n"
                "Example:\n"
                "/set_withdraw min_points 200\n"
                "/set_withdraw status on",
                parse_mode='Markdown'
            )
            return
        
        setting = args[0].lower()
        value = ' '.join(args[1:])
        settings = WithdrawSettings.get_settings()
        
        if setting == 'min_points':
            try:
                settings['min_points'] = int(value)
                WithdrawSettings.update_settings(settings)
                await update.message.reply_text(f"✅ Minimum points set to {value}")
            except ValueError:
                await update.message.reply_text("❌ Please provide a valid number.")
        
        elif setting == 'points_per_id':
            try:
                settings['points_per_id'] = int(value)
                WithdrawSettings.update_settings(settings)
                await update.message.reply_text(f"✅ Points per ID set to {value}")
            except ValueError:
                await update.message.reply_text("❌ Please provide a valid number.")
        
        elif setting == 'status':
            if value.lower() in ['on', 'true', 'active']:
                settings['is_active'] = True
                await update.message.reply_text("✅ Withdraw system activated!")
            elif value.lower() in ['off', 'false', 'inactive']:
                settings['is_active'] = False
                await update.message.reply_text("✅ Withdraw system deactivated!")
            else:
                await update.message.reply_text("❌ Invalid status. Use 'on' or 'off'")
            WithdrawSettings.update_settings(settings)
        
        else:
            await update.message.reply_text("❌ Invalid setting. Use: min_points, points_per_id, or status")
