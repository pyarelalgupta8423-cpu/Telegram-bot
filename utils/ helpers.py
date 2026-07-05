from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database import get_user, get_points_config

def create_main_menu_keyboard(user_id):
    user_data = get_user(user_id)
    
    keyboard = [
        [InlineKeyboardButton("🆔 Get ID (Withdraw)", callback_data="main_get_id")],
        [InlineKeyboardButton("🔗 Refer & Earn", callback_data="main_refer")],
        [InlineKeyboardButton("📊 Available IDs Status", callback_data="main_available_ids")],
        [InlineKeyboardButton("📋 Tasks", callback_data="main_tasks")],
        [InlineKeyboardButton(f"💰 Balance: {user_data['points']} Points", callback_data="main_balance")],
        [InlineKeyboardButton("📈 My Stats", callback_data="main_stats")]
    ]
    
    return InlineKeyboardMarkup(keyboard)

def create_admin_keyboard():
    keyboard = [
        [InlineKeyboardButton("📢 Broadcast to Users", callback_data="admin_broadcast_menu")],
        [InlineKeyboardButton("📊 Bot Statistics", callback_data="admin_stats")],
        [InlineKeyboardButton("🔗 Force Join Channels", callback_data="admin_manage_channels")],
        [InlineKeyboardButton("🔗 External Links", callback_data="admin_manage_links")],
        [InlineKeyboardButton("📋 Manage Tasks", callback_data="admin_manage_tasks")],
        [InlineKeyboardButton("💎 Points Configuration", callback_data="admin_points_config")],
        [InlineKeyboardButton("👥 Groups Management", callback_data="admin_groups_menu")],
        [InlineKeyboardButton("💰 Withdrawal Requests", callback_data="admin_withdrawals")]
    ]
    
    return InlineKeyboardMarkup(keyboard)

def format_points_message():
    points = get_points_config()
    return (
        "💎 *Current Points Configuration*\n\n"
        f"👥 *Referral System:*\n"
        f"• Level 1: {points['refer_level_1']} points\n"
        f"• Level 2: {points['refer_level_2']} points\n\n"
        f"📱 *Group Addition Rewards:*\n"
        f"• <100 members: {points['group_add_small']} points\n"
        f"• 101-1K members: {points['group_add_medium']} points\n"
        f"• 1K-2K members: {points['group_add_m2']} points\n"
        f"• 2K-3K members: {points['group_add_m3']} points\n"
        f"• 3K-5K members: {points['group_add_m4']} points\n"
        f"• >5K members: {points['group_add_big']} points\n\n"
        f"🎯 *Minimum Withdrawal:* {points['min_withdraw']} points"
    )
