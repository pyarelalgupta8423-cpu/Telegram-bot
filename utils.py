from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import FORCE_JOIN_CHANNELS, EXTERNAL_LINKS, logger, ADMIN_IDS, DEFAULT_POINTS
import random
import asyncio
from datetime import datetime

async def check_force_join(update, context):
    """Check if user has joined all force join channels"""
    if not FORCE_JOIN_CHANNELS:
        return True
    
    user_id = update.effective_user.id
    
    for channel in FORCE_JOIN_CHANNELS:
        try:
            chat_member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if chat_member.status in ['left', 'kicked']:
                return False
        except Exception as e:
            logger.error(f"Error checking channel {channel}: {e}")
            return False
    
    return True

def get_referral_points():
    """Get referral points from config"""
    return DEFAULT_POINTS['refer_level1'], DEFAULT_POINTS['refer_level2']

async def process_referral(referrer_id, referred_id, context):
    """Process referral with level 1 and level 2 bonuses"""
    try:
        from models import User
        level1_points = DEFAULT_POINTS['refer_level1']
        level2_points = DEFAULT_POINTS['refer_level2']
        
        # Add points to referrer (level 1)
        User.update_points(referrer_id, level1_points)
        User.add_referral(referrer_id, referred_id)
        
        # Check if referrer has a referrer (level 2)
        user = User.collection.find_one({'user_id': referrer_id})
        if user and user.get('referred_by'):
            level2_referrer = user['referred_by']
            User.update_points(level2_referrer, level2_points)
            
            try:
                await context.bot.send_message(
                    chat_id=level2_referrer,
                    text=f"🎉 **Level 2 Referral Bonus!**\n\n"
                         f"You received {level2_points} points!\n"
                         f"Your referral referred someone else.\n"
                         f"Total referrals: {len(user.get('referrals', []))}",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Could not notify level 2 referrer: {e}")
        
        return True
    except Exception as e:
        logger.error(f"Error processing referral: {e}")
        return False

def generate_progress_keyboard():
    """Generate keyboard for task progress simulation"""
    keyboard = [
        [InlineKeyboardButton("🔄 Continue Task", callback_data="task_continue")],
        [InlineKeyboardButton("✅ Complete Task", callback_data="task_complete")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_channel_points(member_count):
    """Calculate points based on channel members"""
    if member_count <= 100:
        return DEFAULT_POINTS['task_points']['small']
    elif member_count <= 1000:
        return DEFAULT_POINTS['task_points']['medium']
    elif member_count <= 2000:
        return DEFAULT_POINTS['task_points']['m2']
    elif member_count <= 3000:
        return DEFAULT_POINTS['task_points']['m3']
    elif member_count <= 5000:
        return DEFAULT_POINTS['task_points']['m4']
    else:
        return DEFAULT_POINTS['task_points']['big']

def is_admin(user_id):
    """Check if user is admin"""
    return user_id in ADMIN_IDS

def format_number(num):
    """Format number with commas"""
    return f"{num:,}"

def get_main_menu_keyboard():
    """Get main menu keyboard"""
    keyboard = [
        [InlineKeyboardButton("🎯 Get ID", callback_data="get_id")],
        [InlineKeyboardButton("👥 Refer to Get", callback_data="refer_to_get")],
        [InlineKeyboardButton("📊 Available IDs", callback_data="available_ids")],
        [InlineKeyboardButton("📝 Tasks", callback_data="tasks")],
        [InlineKeyboardButton("🏆 Referral System", callback_data="referral_system")],
        [InlineKeyboardButton("📈 My Stats", callback_data="my_stats")]
    ]
    return InlineKeyboardMarkup(keyboard)
