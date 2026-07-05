import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import asyncio
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    ChatMemberHandler, MessageHandler, filters, ContextTypes
)
from telegram.constants import ParseMode
from pymongo import ReturnDocument
from config import BOT_TOKEN, ADMIN_IDS
from database import *
from reward_service import *
from datetime import datetime
from bson import ObjectId
import random
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============ FLASK ============
web_app = Flask(__name__)

@web_app.route("/")
def home():
    return "Bot Running ✅", 200

def run_web_server():
    web_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)), use_reloader=False)

# ============ PREMIUM KEYBOARDS ============
MAIN_KEYBOARD = ReplyKeyboardMarkup([
    [KeyboardButton("🆔 ɢᴇᴛ ɪᴅ"), KeyboardButton("🔗 ʀᴇꜰᴇʀ & ᴇᴀʀɴ")],
    [KeyboardButton("📊 ᴅᴀsʜʙᴏᴀʀᴅ"), KeyboardButton("📋 ᴛᴀsᴋs")],
    [KeyboardButton("💰 ʙᴀʟᴀɴᴄᴇ"), KeyboardButton("👤 ᴘʀᴏꜰɪʟᴇ")]
], resize_keyboard=True)

VERIFY_KEYBOARD = ReplyKeyboardMarkup([
    [KeyboardButton("🔄 sᴛᴀʀᴛ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ")]
], resize_keyboard=True)

# ============ PREMIUM HELPERS ============
def get_payout_channel():
    """Get configured payout channel ID"""
    s = get_collection("settings").find_one({"type": "payout_channel"})
    return s["channel_id"] if s else None

def create_main_menu_keyboard(user_id):
    u = get_user(user_id)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 ᴡɪᴛʜᴅʀᴀᴡ ɪᴅ", callback_data="main_get_id")],
        [InlineKeyboardButton("🔗 ʀᴇꜰᴇʀʀᴀʟ ʟɪɴᴋ", callback_data="main_refer")],
        [InlineKeyboardButton("📊 sʏsᴛᴇᴍ sᴛᴀᴛᴜs", callback_data="main_available_ids")],
        [InlineKeyboardButton("📋 ᴀᴠᴀɪʟᴀʙʟᴇ ᴛᴀsᴋs", callback_data="main_tasks")],
        [InlineKeyboardButton("💎 ᴇᴀʀɴ ᴘᴏɪɴᴛs ʜᴇʀᴇ", callback_data="main_earn")],
        [InlineKeyboardButton(f"💰 ʙᴀʟᴀɴᴄᴇ: {u['points']} ᴘᴏɪɴᴛs", callback_data="main_balance")],
        [InlineKeyboardButton("👤 ᴍʏ ᴘʀᴏꜰɪʟᴇ", callback_data="main_stats")]
    ])

def create_admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 ʙʀᴏᴀᴅᴄᴀsᴛ ᴛᴏ ᴜsᴇʀs", callback_data="admin_broadcast_menu")],
        [InlineKeyboardButton("📊 ʙᴏᴛ sᴛᴀᴛɪsᴛɪᴄs", callback_data="admin_stats")],
        [InlineKeyboardButton("🔗 ꜰᴏʀᴄᴇ ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟs", callback_data="admin_manage_channels")],
        [InlineKeyboardButton("🔗 ᴇxᴛᴇʀɴᴀʟ ʟɪɴᴋs", callback_data="admin_manage_links")],
        [InlineKeyboardButton("📋 ᴍᴀɴᴀɢᴇ ᴛᴀsᴋs", callback_data="admin_manage_tasks")],
        [InlineKeyboardButton("💎 ᴘᴏɪɴᴛs ᴄᴏɴꜰɪɢ", callback_data="admin_points_config")],
        [InlineKeyboardButton("👥 ɢʀᴏᴜᴘ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ", callback_data="admin_groups_menu")],
        [InlineKeyboardButton("💳 ᴡɪᴛʜᴅʀᴀᴡᴀʟ ʀᴇǫᴜᴇsᴛs", callback_data="admin_withdrawals")],
        [InlineKeyboardButton("📢 sᴇᴛ ᴘᴀʏᴏᴜᴛ ᴄʜᴀɴɴᴇʟ", callback_data="admin_set_payout")],
        [InlineKeyboardButton("ℹ️ ʜᴏᴡ ɪᴛ ᴡᴏʀᴋs", callback_data="admin_how_it_works")]
    ])

def format_points_message():
    p = get_points_config()
    return (
        "╔══════════════════════════╗\n"
        "║   💎 ᴘᴏɪɴᴛs ᴄᴏɴғɪɢᴜʀᴀᴛɪᴏɴ   ║\n"
        "╚══════════════════════════╝\n\n"
        "👥 *ʀᴇꜰᴇʀʀᴀʟ sʏsᴛᴇᴍ*\n"
        f"  ├─ ʟᴇᴠᴇʟ 1: *{p['refer_level_1']}* ᴘᴏɪɴᴛs\n"
        f"  └─ ʟᴇᴠᴇʟ 2: *{p['refer_level_2']}* ᴘᴏɪɴᴛs\n\n"
        "📱 *ɢʀᴏᴜᴘ ʀᴇᴡᴀʀᴅs*\n"
        f"  ├─ 100-1K ᴍᴇᴍʙᴇʀs: *{p['group_add_small']}* ᴘᴛs\n"
        f"  ├─ 1K-2K ᴍᴇᴍʙᴇʀs: *{p['group_add_medium']}* ᴘᴛs\n"
        f"  ├─ 2K-3K ᴍᴇᴍʙᴇʀs: *{p['group_add_m2']}* ᴘᴛs\n"
        f"  ├─ 3K-5K ᴍᴇᴍʙᴇʀs: *{p['group_add_m3']}* ᴘᴛs\n"
        f"  ├─ 5K-10K ᴍᴇᴍʙᴇʀs: *{p['group_add_m4']}* ᴘᴛs\n"
        f"  └─ 10K+ ᴍᴇᴍʙᴇʀs: *{p['group_add_big']}* ᴘᴛs\n\n"
        "⚠️ *<100 ᴍᴇᴍʙᴇʀs = 0 ʀᴇᴡᴀʀᴅ*\n\n"
        f"🎯 *ᴡɪᴛʜᴅʀᴀᴡᴀʟ ᴍɪɴɪᴍᴜᴍ:* {p['min_withdraw']} ᴘᴏɪɴᴛs"
    )

# ============ USER HANDLERS ============
async def check_force_join(uid, context):
    not_joined = []
    for ch in get_collection("channels").find({"active": True}):
        try:
            m = await context.bot.get_chat_member(ch["channel_id"], uid)
            if m.status in ['left', 'kicked']: not_joined.append(ch)
        except: not_joined.append(ch)
    return not_joined

async def ensure_force_join_verified(uid, context):
    if await check_force_join(uid, context):
        get_collection("users").update_one({"user_id": uid}, {"$set": {"force_join_completed": False}})
        return False
    get_collection("users").update_one({"user_id": uid}, {"$set": {"force_join_completed": True}})
    return True

async def ensure_user_verified(uid, context):
    u = get_user(uid)
    if not u.get("external_tasks_completed"): return False
    if u.get("verification_version", 0) != get_verification_version():
        get_collection("users").update_one({"user_id": uid}, {"$set": {"external_tasks_completed": False, "verification_version": 0}, "$unset": {"verification.external_required": "", "verification.external_attempts": ""}})
        return False
    return await ensure_force_join_verified(uid, context)

async def process_pending_group_rewards(uid, context):
    for r in process_pending_group_rewards_atomic(uid):
        try: await context.bot.send_message(uid, f"🎉 *ᴘᴇɴᴅɪɴɢ ɢʀᴏᴜᴘ ʀᴇᴡᴀʀᴅ ᴄʀᴇᴅɪᴛᴇᴅ!*\n\n📱 ɢʀᴏᴜᴘ: {r['title']}\n💰 ʀᴇᴡᴀʀᴅ: *{r['points']}* ᴘᴏɪɴᴛs", parse_mode=ParseMode.MARKDOWN)
        except: pass

async def handle_referral_points(uid, rid, context):
    if not await ensure_user_verified(uid, context) or uid == rid: return False
    r = credit_referral_atomic(uid, rid)
    if not r: return False
    try: await context.bot.send_message(r["referrer_id"], f"🎉 *ɴᴇᴡ ʀᴇꜰᴇʀʀᴀʟ ᴇᴀʀɴɪɴɢ!*\n\n👤 ᴀ ɴᴇᴡ ᴜsᴇʀ ᴊᴏɪɴᴇᴅ ᴜsɪɴɢ ʏᴏᴜʀ ʟɪɴᴋ!\n💰 ʏᴏᴜ ᴇᴀʀɴᴇᴅ: *+{r['level1_points']}* ᴘᴏɪɴᴛs", parse_mode=ParseMode.MARKDOWN)
    except: pass
    if r.get("level2_id"):
        try: await context.bot.send_message(r["level2_id"], f"🌟 *ʟᴇᴠᴇʟ 2 ʙᴏɴᴜs!*\n\n💰 ʏᴏᴜ ᴇᴀʀɴᴇᴅ: *+{r['level2_points']}* ᴘᴏɪɴᴛs\nꜰʀᴏᴍ ʏᴏᴜʀ ʀᴇꜰᴇʀʀᴀʟ's ɴᴇᴛᴡᴏʀᴋ!", parse_mode=ParseMode.MARKDOWN)
        except: pass
    return True

# ============ TASK HANDLERS ============
async def handle_force_join_complete(update, context):
    q = update.callback_query
    get_collection("users").update_one({"user_id": q.from_user.id}, {"$set": {"force_join_completed": True}})
    links = list(get_collection("external_links").find({"active": True}))
    if links:
        kb = [[InlineKeyboardButton(f"🔗 {l['name']}", url=l['url'])] for l in links]
        kb.append([InlineKeyboardButton("✅ ɪ'ᴠᴇ ᴄᴏᴍᴘʟᴇᴛᴇᴅ ᴀʟʟ", callback_data="ext_tasks_complete")])
        await q.message.edit_text(
            "╔══════════════════════════╗\n"
            "║  ✅ ᴄʜᴀɴɴᴇʟs ᴠᴇʀɪꜰɪᴇᴅ!   ║\n"
            "╚══════════════════════════╝\n\n"
            "📋 *ɴᴏᴡ ᴄᴏᴍᴘʟᴇᴛᴇ ᴛʜᴇsᴇ ᴛᴀsᴋs:*\n\n"
            "👇 ᴄʟɪᴄᴋ ᴇᴀᴄʜ ʟɪɴᴋ ʙᴇʟᴏᴡ\n"
            "✅ ᴄᴏᴍᴘʟᴇᴛᴇ ᴛʜᴇ ʀᴇǫᴜɪʀᴇᴅ ᴀᴄᴛɪᴏɴ\n"
            "✅ ᴛʜᴇɴ ᴄʟɪᴄᴋ 'ɪ'ᴠᴇ ᴄᴏᴍᴘʟᴇᴛᴇᴅ ᴀʟʟ'\n\n"
            "⚠️ *ᴍᴜʟᴛɪᴘʟᴇ ᴄᴏɴꜰɪʀᴍᴀᴛɪᴏɴs ʀᴇǫᴜɪʀᴇᴅ*",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    else:
        await complete_verification(update, context, q.from_user.id)

async def handle_external_tasks_complete(update, context):
    q = update.callback_query; uid = q.from_user.id
    if not await ensure_force_join_verified(uid, context): await q.answer("❌ ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟs ꜰɪʀsᴛ!", show_alert=True); return
    u = get_user(uid); v = u.get("verification", {})
    req = v.get("external_required")
    if not req:
        req = random.randint(2, 3)
        get_collection("users").update_one({"user_id": uid}, {"$set": {"verification.external_required": req, "verification.external_attempts": 1}})
        await q.answer(f"⚠️ ᴄᴏɴꜰɪʀᴍᴀᴛɪᴏɴ 1/{req}", show_alert=True); return
    cur = v.get("external_attempts", 0) + 1
    get_collection("users").update_one({"user_id": uid}, {"$set": {"verification.external_attempts": cur}})
    if cur < req: await q.answer(f"⚠️ ᴋᴇᴇᴘ ᴄᴏɴꜰɪʀᴍɪɴɢ... {cur}/{req}", show_alert=True); return
    await complete_verification(update, context, uid)

async def complete_verification(update, context, uid):
    q = update.callback_query
    if not await ensure_force_join_verified(uid, context): await q.answer("❌ sᴛᴀʏ ɪɴ ᴄʜᴀɴɴᴇʟs!", show_alert=True); return
    get_collection("users").update_one({"user_id": uid}, {"$set": {"external_tasks_completed": True, "verification_version": get_verification_version()}, "$unset": {"verification.external_required": "", "verification.external_attempts": ""}})
    await process_pending_group_rewards(uid, context)
    u = get_user(uid)
    if u.get("pending_referrer"): await handle_referral_points(uid, u["pending_referrer"], context)
    await q.message.edit_text(
        "╔══════════════════════════╗\n"
        "║  🎉 ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴅᴏɴᴇ!   ║\n"
        "╚══════════════════════════╝\n\n"
        "✅ ᴄʜᴀɴɴᴇʟs ᴠᴇʀɪꜰɪᴇᴅ\n"
        "✅ ᴛᴀsᴋs ᴄᴏᴍᴘʟᴇᴛᴇᴅ\n"
        "✅ ʀᴇꜰᴇʀʀᴀʟ ᴘʀᴏᴄᴇssᴇᴅ\n\n"
        "*ᴡᴇʟᴄᴏᴍᴇ ᴀʙᴏᴀʀᴅ!* 🚀",
        reply_markup=create_main_menu_keyboard(uid), parse_mode=ParseMode.MARKDOWN)

# ============ CALLBACK ROUTER ============
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; d = q.data; uid = q.from_user.id
    
    if d == "main_menu":
        if await ensure_user_verified(uid, context):
            await q.message.edit_text("📱 *ᴍᴀɪɴ ᴍᴇɴᴜ*\n\nsᴇʟᴇᴄᴛ ᴀɴ ᴏᴘᴛɪᴏɴ:", reply_markup=create_main_menu_keyboard(uid), parse_mode="Markdown")
        else:
            await q.message.edit_text("⚠️ *ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ʀᴇǫᴜɪʀᴇᴅ!*\n\nᴜsᴇ /start ᴛᴏ ᴠᴇʀɪꜰʏ.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 sᴛᴀʀᴛ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ", callback_data="start_verify")]]), parse_mode="Markdown")
    
    elif d == "main_get_id": await get_id_handler(update, context)
    elif d == "main_refer": await refer_menu_handler(update, context)
    elif d == "main_available_ids": await available_ids_handler(update, context)
    elif d == "main_tasks": await tasks_menu_handler(update, context)
    elif d == "main_earn": await earn_points_handler(update, context)
    elif d == "main_balance": await q.answer(f"💰 ʙᴀʟᴀɴᴄᴇ: {get_user(uid)['points']} ᴘᴏɪɴᴛs", show_alert=True)
    elif d == "main_stats": await show_stats(update, context)
    elif d == "check_join":
        if await check_force_join(uid, context): await q.answer("❌ ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟs ꜰɪʀsᴛ!", show_alert=True)
        else: await q.answer("✅ ᴠᴇʀɪꜰɪᴇᴅ!"); await handle_force_join_complete(update, context)
    elif d == "start_verify":
        cv = get_verification_version(); u = get_user(uid)
        if u.get("verification_version", 0) != cv:
            get_collection("users").update_one({"user_id": uid}, {"$set": {"external_tasks_completed": False, "verification_version": 0}, "$unset": {"verification.external_required": "", "verification.external_attempts": ""}})
        nj = await check_force_join(uid, context)
        if nj:
            kb = [[InlineKeyboardButton(f"📢 {c['channel_name']}", url=c['invite_link'])] for c in nj]
            kb.append([InlineKeyboardButton("✅ ᴄʜᴇᴄᴋ & ᴄᴏɴᴛɪɴᴜᴇ", callback_data="check_join")])
            await q.message.edit_text("⚠️ *ᴊᴏɪɴ ʀᴇǫᴜɪʀᴇᴅ ᴄʜᴀɴɴᴇʟs:*", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        else:
            await handle_force_join_complete(update, context)
    elif d == "ext_tasks_complete": await handle_external_tasks_complete(update, context)
    elif d.startswith("task_do_"): await handle_specific_task(update, context, d.replace("task_do_", ""))
    elif d.startswith("task_verify_"): await verify_task_completion(update, context, d.replace("task_verify_", ""))
    elif d == "admin_panel" or d.startswith("admin_"): await handle_admin_callbacks(update, context)
    else: await q.answer("❓ ᴜɴᴋɴᴏᴡɴ", show_alert=True)

# ============ MENU HANDLERS ============
async def refer_menu_handler(update, context):
    q = update.callback_query; uid = q.from_user.id
    link = f"https://t.me/{context.bot.username}?start=ref_{uid}"
    p = get_points_config()
    await q.message.edit_text(
        "╔══════════════════════════╗\n"
        "║    🔗 ʏᴏᴜʀ ʀᴇꜰᴇʀʀᴀʟ ʟɪɴᴋ    ║\n"
        "╚══════════════════════════╝\n\n"
        f"📋 `{link}`\n\n"
        "📊 *ᴇᴀʀɴɪɴɢ sᴛʀᴜᴄᴛᴜʀᴇ:*\n"
        f"├─ ᴅɪʀᴇᴄᴛ ʀᴇꜰᴇʀʀᴀʟ: *{p['refer_level_1']}* ᴘᴏɪɴᴛs\n"
        f"└─ ʟᴇᴠᴇʟ 2: *{p['refer_level_2']}* ᴘᴏɪɴᴛs\n\n"
        "💡 *ʜᴏᴡ ɪᴛ ᴡᴏʀᴋs:*\n"
        "1. sʜᴀʀᴇ ʏᴏᴜʀ ʟɪɴᴋ\n"
        "2. ᴜsᴇʀ ᴊᴏɪɴs & ᴠᴇʀɪꜰɪᴇs\n"
        "3. ʏᴏᴜ ɢᴇᴛ ᴘᴏɪɴᴛs!\n\n"
        "🚀 *sᴛᴀʀᴛ sʜᴀʀɪɴɢ ɴᴏᴡ!*",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 ʀᴇꜰʀᴇsʜ", callback_data="main_refer")], [InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="main_menu")]]), parse_mode=ParseMode.MARKDOWN)

async def earn_points_handler(update, context):
    q = update.callback_query; uid = q.from_user.id
    p = get_points_config()
    await q.message.edit_text(
        "╔══════════════════════════╗\n"
        "║   💎 ᴡᴀʏs ᴛᴏ ᴇᴀʀɴ ᴘᴏɪɴᴛs   ║\n"
        "╚══════════════════════════╝\n\n"
        "🔗 *ʀᴇꜰᴇʀʀᴀʟ sʏsᴛᴇᴍ*\n"
        f"├─ ᴅɪʀᴇᴄᴛ: {p['refer_level_1']} ᴘᴏɪɴᴛs\n"
        f"└─ ʟᴇᴠᴇʟ 2: {p['refer_level_2']} ᴘᴏɪɴᴛs\n\n"
        "📱 *ɢʀᴏᴜᴘ ʀᴇᴡᴀʀᴅs*\n"
        "├─ ᴀᴅᴅ ʙᴏᴛ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ\n"
        "└─ ɢᴇᴛ ʀᴇᴡᴀʀᴅᴇᴅ!\n\n"
        "📋 *ᴛᴀsᴋs*\n"
        "└─ ᴄᴏᴍᴘʟᴇᴛᴇ ᴛᴀsᴋs ꜰᴏʀ ᴘᴏɪɴᴛs\n\n"
        "💳 *ᴡɪᴛʜᴅʀᴀᴡᴀʟ*\n"
        f"└─ ᴍɪɴɪᴍᴜᴍ: {p['min_withdraw']} ᴘᴏɪɴᴛs",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="main_menu")]]), parse_mode=ParseMode.MARKDOWN)

async def get_id_handler(update, context):
    q = update.callback_query; cfg = get_points_config(); uid = q.from_user.id
    if not await ensure_user_verified(uid, context): await q.answer("❌ ᴠᴇʀɪꜰʏ ꜰɪʀsᴛ!", show_alert=True); return
    
    u = get_user(uid)
    if u['points'] < cfg["min_withdraw"]:
        await q.answer(f"❌ ɴᴇᴇᴅ {cfg['min_withdraw']} ᴘᴏɪɴᴛs! ʏᴏᴜ ʜᴀᴠᴇ: {u['points']}", show_alert=True); return
    
    r = create_withdrawal_atomic(uid, cfg["min_withdraw"], q.from_user.username or "N/A", q.from_user.full_name)
    if not r: await q.answer("❌ ᴛʀᴀɴsᴀᴄᴛɪᴏɴ ꜰᴀɪʟᴇᴅ!", show_alert=True); return
    
    # Send to payout channel
    payout_channel = get_payout_channel()
    if payout_channel:
        try:
            await context.bot.send_message(payout_channel,
                "╔══════════════════════════╗\n"
                "║   💳 ɴᴇᴡ ᴡɪᴛʜᴅʀᴀᴡᴀʟ    ║\n"
                "╚══════════════════════════╝\n\n"
                f"🔢 ᴛᴏᴋᴇɴ: #{r['serial_no']}\n"
                f"👤 ᴜsᴇʀ: {q.from_user.full_name}\n"
                f"🆔 ᴜsᴇʀ ɪᴅ: `{uid}`\n"
                f"📱 ᴜsᴇʀɴᴀᴍᴇ: @{q.from_user.username or 'N/A'}\n"
                f"💰 ᴘᴏɪɴᴛs: {r['withdraw_amount']}\n"
                f"📅 ᴅᴀᴛᴇ: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                f"📋 sᴛᴀᴛᴜs: ᴘᴇɴᴅɪɴɢ",
                parse_mode=ParseMode.MARKDOWN)
        except: pass
    
    await q.message.edit_text(
        "╔══════════════════════════╗\n"
        "║  ✅ ᴡɪᴛʜᴅʀᴀᴡᴀʟ sᴜʙᴍɪᴛᴛᴇᴅ  ║\n"
        "╚══════════════════════════╝\n\n"
        f"🔢 *ᴛᴏᴋᴇɴ ɴᴜᴍʙᴇʀ:* `{r['serial_no']}`\n"
        f"💰 *ᴘᴏɪɴᴛs ᴅᴇᴅᴜᴄᴛᴇᴅ:* {r['withdraw_amount']}\n"
        f"💎 *ʀᴇᴍᴀɪɴɪɴɢ ʙᴀʟᴀɴᴄᴇ:* {r['new_balance']}\n\n"
        "📋 *ɴᴇxᴛ sᴛᴇᴘs:*\n"
        "1. ɴᴏᴛᴇ ʏᴏᴜʀ ᴛᴏᴋᴇɴ ɴᴜᴍʙᴇʀ\n"
        "2. ᴀᴅᴍɪɴ ᴡɪʟʟ ᴘʀᴏᴄᴇss ʏᴏᴜʀ ʀᴇǫᴜᴇsᴛ\n"
        "3. ʏᴏᴜ'ʟʟ ɢᴇᴛ ʏᴏᴜʀ ɪᴅ sᴏᴏɴ!\n\n"
        "⏳ *ᴘʀᴏᴄᴇssɪɴɢ: 24-48 ʜᴏᴜʀs*",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ᴍᴀɪɴ ᴍᴇɴᴜ", callback_data="main_menu")]]), parse_mode=ParseMode.MARKDOWN)

async def show_stats(update, context):
    q = update.callback_query; u = get_user(q.from_user.id)
    await q.message.edit_text(
        "╔══════════════════════════╗\n"
        "║      👤 ᴍʏ ᴘʀᴏꜰɪʟᴇ       ║\n"
        "╚══════════════════════════╝\n\n"
        f"👤 *ɴᴀᴍᴇ:* {u.get('full_name', 'N/A')}\n"
        f"🆔 *ᴜsᴇʀ ɪᴅ:* `{q.from_user.id}`\n"
        f"💰 *ʙᴀʟᴀɴᴄᴇ:* {u['points']} ᴘᴏɪɴᴛs\n"
        f"👥 *ᴅɪʀᴇᴄᴛ ʀᴇꜰᴇʀʀᴀʟs:* {len(u.get('referrals',[]))}\n"
        f"🌟 *ʟᴇᴠᴇʟ 2:* {len(u.get('level2_referrals',[]))}\n"
        f"✅ *ᴛᴀsᴋs ᴅᴏɴᴇ:* {len(u.get('completed_tasks',[]))}\n"
        f"📅 *ᴊᴏɪɴᴇᴅ:* {u['join_date'].strftime('%Y-%m-%d')}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="main_menu")]]), parse_mode=ParseMode.MARKDOWN)

async def available_ids_handler(update, context):
    q = update.callback_query
    t = get_collection("withdraw_requests").count_documents({})
    p = get_collection("withdraw_requests").count_documents({"status":"pending"})
    c = get_collection("withdraw_requests").count_documents({"status":"completed"})
    await q.message.edit_text(
        "╔══════════════════════════╗\n"
        "║   📊 sʏsᴛᴇᴍ sᴛᴀᴛᴜs     ║\n"
        "╚══════════════════════════╝\n\n"
        f"📊 *ᴛᴏᴛᴀʟ ɪᴅs ɪssᴜᴇᴅ:* {c}\n"
        f"⏳ *ᴘᴇɴᴅɪɴɢ:* {p}\n"
        f"💰 *ᴛᴏᴛᴀʟ ʀᴇǫᴜᴇsᴛs:* {t}\n\n"
        f"💎 *ᴄᴏsᴛ ᴘᴇʀ ɪᴅ:* {get_points_config()['min_withdraw']} ᴘᴏɪɴᴛs",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="main_menu")]]), parse_mode=ParseMode.MARKDOWN)

async def tasks_menu_handler(update, context):
    q = update.callback_query
    if not await ensure_user_verified(q.from_user.id, context): await q.answer("❌ ᴠᴇʀɪꜰʏ!", show_alert=True); return
    tasks = list(get_collection("tasks").find({"active": True}))
    if not tasks:
        await q.message.edit_text("📋 *ɴᴏ ᴛᴀsᴋs ᴀᴠᴀɪʟᴀʙʟᴇ ʀɪɢʜᴛ ɴᴏᴡ!*\n\nᴄʜᴇᴄᴋ ʙᴀᴄᴋ ʟᴀᴛᴇʀ.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ᴍᴇɴᴜ", callback_data="main_menu")]]), parse_mode=ParseMode.MARKDOWN)
        return
    kb = [[InlineKeyboardButton(f"📌 {t['name']} (+{t['points']} ᴘᴛs)", callback_data=f"task_do_{t['_id']}")] for t in tasks]
    kb.append([InlineKeyboardButton("🔙 ᴍᴀɪɴ ᴍᴇɴᴜ", callback_data="main_menu")])
    await q.message.edit_text(
        "╔══════════════════════════╗\n"
        "║   📋 ᴀᴠᴀɪʟᴀʙʟᴇ ᴛᴀsᴋs    ║\n"
        "╚══════════════════════════╝\n\n"
        "ᴄᴏᴍᴘʟᴇᴛᴇ ᴛᴀsᴋs ᴛᴏ ᴇᴀʀɴ ᴘᴏɪɴᴛs!\n\n"
        "*sᴇʟᴇᴄᴛ ᴀ ᴛᴀsᴋ:*",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

async def handle_specific_task(update, context, tid):
    q = update.callback_query; t = get_task_by_id(tid)
    if not t: await q.answer("❌ ɴᴏᴛ ꜰᴏᴜɴᴅ!", show_alert=True); return
    if not await ensure_user_verified(q.from_user.id, context): await q.answer("❌ ᴠᴇʀɪꜰʏ!", show_alert=True); return
    u = get_user(q.from_user.id)
    if tid in [str(x) for x in u.get("completed_tasks",[])]: await q.answer("✅ ᴀʟʀᴇᴀᴅʏ ᴅᴏɴᴇ!", show_alert=True); return
    if t["type"] == "add_to_group":
        await q.message.edit_text(
            "╔══════════════════════════╗\n"
            "║  📋 ᴀᴅᴅ ʙᴏᴛ ᴛᴏ ɢʀᴏᴜᴘ    ║\n"
            "╚══════════════════════════╝\n\n"
            f"1. ᴀᴅᴅ @{context.bot.username} ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ\n"
            "2. ᴍᴀᴋᴇ ʙᴏᴛ ᴀᴅᴍɪɴ\n"
            "3. ʙᴏᴛ ᴡɪʟʟ ᴀᴜᴛᴏ-ᴅᴇᴛᴇᴄᴛ\n"
            "4. ᴘᴏɪɴᴛs ᴄʀᴇᴅɪᴛᴇᴅ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ!\n\n"
            f"💰 *ʀᴇᴡᴀʀᴅ:* ʙᴀsᴇᴅ ᴏɴ ᴍᴇᴍʙᴇʀ ᴄᴏᴜɴᴛ",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="main_tasks")]]), parse_mode=ParseMode.MARKDOWN)
    else:
        a = u.get("task_attempts",{}).get(tid,0)
        await q.message.edit_text(
            "╔══════════════════════════╗\n"
            f"║  📋 {t['name'][:20]:<20} ║\n"
            "╚══════════════════════════╝\n\n"
            f"💰 *ʀᴇᴡᴀʀᴅ:* {t['points']} ᴘᴏɪɴᴛs\n"
            f"⏳ *ᴄᴏɴꜰɪʀᴍᴀᴛɪᴏɴs:* {a}/2\n\n"
            "📌 *sᴛᴇᴘs:*\n"
            "1. ᴄʟɪᴄᴋ 'ᴏᴘᴇɴ ʟɪɴᴋ'\n"
            "2. ᴄᴏᴍᴘʟᴇᴛᴇ ᴛʜᴇ ᴀᴄᴛɪᴏɴ\n"
            "3. ʀᴇᴛᴜʀɴ & ᴄʟɪᴄᴋ 'ᴄʟᴀɪᴍ ᴘᴏɪɴᴛs'\n\n"
            "ℹ️ ᴍᴜʟᴛɪᴘʟᴇ ᴄᴏɴꜰɪʀᴍᴀᴛɪᴏɴs ᴘʀᴇᴠᴇɴᴛ ᴀʙᴜsᴇ",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 ᴏᴘᴇɴ ʟɪɴᴋ", url=t['url'])],
                [InlineKeyboardButton("🎯 ᴄʟᴀɪᴍ ᴘᴏɪɴᴛs", callback_data=f"task_verify_{tid}")],
                [InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="main_tasks")]
            ]), parse_mode=ParseMode.MARKDOWN)

async def verify_task_completion(update, context, tid):
    q = update.callback_query; t = get_task_by_id(tid)
    if not t: await q.answer("❌ ɴᴏᴛ ꜰᴏᴜɴᴅ!", show_alert=True); return
    if not await ensure_user_verified(q.from_user.id, context): await q.answer("❌ ᴠᴇʀɪꜰʏ!", show_alert=True); return
    uid = q.from_user.id; u = get_user(uid); a = u.get("task_attempts",{}).get(tid,0) + 1
    if a < 2:
        get_collection("users").update_one({"user_id": uid}, {"$set": {f"task_attempts.{tid}": a}})
        await q.answer(f"⚠️ {2-a} ᴍᴏʀᴇ ᴄᴏɴꜰɪʀᴍᴀᴛɪᴏɴ ɴᴇᴇᴅᴇᴅ!", show_alert=True); return
    r = get_collection("users").update_one({"user_id": uid, "completed_tasks": {"$ne": ObjectId(tid)}}, {"$inc": {"points": t["points"]}, "$addToSet": {"completed_tasks": ObjectId(tid)}, "$set": {f"task_attempts.{tid}": a}})
    if r.modified_count == 0: await q.answer("✅ ᴀʟʀᴇᴀᴅʏ ᴄʟᴀɪᴍᴇᴅ!", show_alert=True); return
    await q.answer(f"🎉 +{t['points']} ᴘᴏɪɴᴛs ᴇᴀʀɴᴇᴅ!", show_alert=True)
    await tasks_menu_handler(update, context)

# ============ KEYBOARD MESSAGE HANDLER ============
async def handle_keyboard_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text; uid = update.effective_user.id
    
    if text == "🆔 ɢᴇᴛ ɪᴅ":
        cfg = get_points_config()
        if not await ensure_user_verified(uid, context): await update.message.reply_text("❌ *ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ʀᴇǫᴜɪʀᴇᴅ!*\nᴜsᴇ /start", reply_markup=VERIFY_KEYBOARD, parse_mode=ParseMode.MARKDOWN); return
        u = get_user(uid)
        if u['points'] < cfg["min_withdraw"]: await update.message.reply_text(f"❌ *ɪɴsᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ!*\n\n💰 ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ: {u['points']} ᴘᴏɪɴᴛs\n💎 ɴᴇᴇᴅ: {cfg['min_withdraw']} ᴘᴏɪɴᴛs\n\nᴄᴏᴍᴘʟᴇᴛᴇ ᴛᴀsᴋs ᴛᴏ ᴇᴀʀɴ ᴍᴏʀᴇ!", reply_markup=MAIN_KEYBOARD, parse_mode=ParseMode.MARKDOWN); return
        r = create_withdrawal_atomic(uid, cfg["min_withdraw"], update.effective_user.username or "N/A", update.effective_user.full_name)
        if r:
            # Send to payout channel
            payout_channel = get_payout_channel()
            if payout_channel:
                try: await context.bot.send_message(payout_channel, f"💳 *ɴᴇᴡ ᴡɪᴛʜᴅʀᴀᴡᴀʟ*\n\n🔢 #{r['serial_no']}\n👤 {update.effective_user.full_name}\n🆔 `{uid}`\n💰 {r['withdraw_amount']} ᴘᴏɪɴᴛs", parse_mode=ParseMode.MARKDOWN)
                except: pass
            await update.message.reply_text(
                "╔══════════════════════════╗\n"
                "║  ✅ ᴡɪᴛʜᴅʀᴀᴡᴀʟ sᴜʙᴍɪᴛᴛᴇᴅ  ║\n"
                "╚══════════════════════════╝\n\n"
                f"🔢 *ᴛᴏᴋᴇɴ:* `{r['serial_no']}`\n"
                f"💰 *ᴅᴇᴅᴜᴄᴛᴇᴅ:* {r['withdraw_amount']}\n"
                f"💎 *ʀᴇᴍᴀɪɴɪɴɢ:* {r['new_balance']}\n\n"
                "⏳ ᴀᴅᴍɪɴ ᴡɪʟʟ ᴘʀᴏᴄᴇss sᴏᴏɴ!",
                reply_markup=MAIN_KEYBOARD, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text("❌ ᴛʀᴀɴsᴀᴄᴛɪᴏɴ ꜰᴀɪʟᴇᴅ! ᴛʀʏ ᴀɢᴀɪɴ.", reply_markup=MAIN_KEYBOARD)
    
    elif text == "🔗 ʀᴇꜰᴇʀ & ᴇᴀʀɴ":
        link = f"https://t.me/{context.bot.username}?start=ref_{uid}"
        p = get_points_config()
        await update.message.reply_text(
            "╔══════════════════════════╗\n"
            "║    🔗 ʏᴏᴜʀ ʀᴇꜰᴇʀʀᴀʟ ʟɪɴᴋ    ║\n"
            "╚══════════════════════════╝\n\n"
            f"📋 `{link}`\n\n"
            f"💰 ᴅɪʀᴇᴄᴛ: *{p['refer_level_1']}* ᴘᴏɪɴᴛs\n"
            f"🌟 ʟᴇᴠᴇʟ 2: *{p['refer_level_2']}* ᴘᴏɪɴᴛs\n\n"
            "🚀 sʜᴀʀᴇ & ᴇᴀʀɴ!",
            reply_markup=MAIN_KEYBOARD, parse_mode=ParseMode.MARKDOWN)
    
    elif text == "📊 ᴅᴀsʜʙᴏᴀʀᴅ":
        t = get_collection("withdraw_requests").count_documents({})
        p = get_collection("withdraw_requests").count_documents({"status":"pending"})
        c = get_collection("withdraw_requests").count_documents({"status":"completed"})
        await update.message.reply_text(
            "╔══════════════════════════╗\n"
            "║   📊 sʏsᴛᴇᴍ ᴅᴀsʜʙᴏᴀʀᴅ   ║\n"
            "╚══════════════════════════╝\n\n"
            f"📊 ᴛᴏᴛᴀʟ ɪᴅs: {c}\n"
            f"⏳ ᴘᴇɴᴅɪɴɢ: {p}\n"
            f"💰 ᴛᴏᴛᴀʟ ʀᴇǫs: {t}",
            reply_markup=MAIN_KEYBOARD)
    
    elif text == "📋 ᴛᴀsᴋs":
        if not await ensure_user_verified(uid, context): await update.message.reply_text("❌ ᴠᴇʀɪꜰʏ ꜰɪʀsᴛ!", reply_markup=VERIFY_KEYBOARD); return
        tasks = list(get_collection("tasks").find({"active":True}))
        if tasks:
            kb = [[InlineKeyboardButton(f"📌 {t['name']} (+{t['points']} ᴘᴛs)", callback_data=f"task_do_{t['_id']}")] for t in tasks]
            await update.message.reply_text("📋 *ᴀᴠᴀɪʟᴀʙʟᴇ ᴛᴀsᴋs*", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text("📋 ɴᴏ ᴛᴀsᴋs ᴀᴠᴀɪʟᴀʙʟᴇ!", reply_markup=MAIN_KEYBOARD)
    
    elif text == "💰 ʙᴀʟᴀɴᴄᴇ":
        u = get_user(uid); cfg = get_points_config()
        await update.message.reply_text(
            "╔══════════════════════════╗\n"
            "║     💰 ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ     ║\n"
            "╚══════════════════════════╝\n\n"
            f"💎 *{u['points']}* ᴘᴏɪɴᴛs\n\n"
            f"🎯 ᴡɪᴛʜᴅʀᴀᴡᴀʟ ᴍɪɴ: {cfg['min_withdraw']} ᴘᴛs\n"
            f"📊 ᴘʀᴏɢʀᴇss: {u['points']}/{cfg['min_withdraw']}",
            reply_markup=MAIN_KEYBOARD, parse_mode=ParseMode.MARKDOWN)
    
    elif text == "👤 ᴘʀᴏꜰɪʟᴇ":
        u = get_user(uid)
        await update.message.reply_text(
            "╔══════════════════════════╗\n"
            "║      👤 ᴍʏ ᴘʀᴏꜰɪʟᴇ       ║\n"
            "╚══════════════════════════╝\n\n"
            f"👤 *ɴᴀᴍᴇ:* {u.get('full_name', 'N/A')}\n"
            f"🆔 *ɪᴅ:* `{uid}`\n"
            f"💰 *ʙᴀʟᴀɴᴄᴇ:* {u['points']} ᴘᴏɪɴᴛs\n"
            f"👥 *ʀᴇꜰᴇʀʀᴀʟs:* {len(u.get('referrals',[]))}\n"
            f"✅ *ᴛᴀsᴋs:* {len(u.get('completed_tasks',[]))}\n"
            f"📅 *ᴊᴏɪɴᴇᴅ:* {u['join_date'].strftime('%d %b %Y')}",
            reply_markup=MAIN_KEYBOARD, parse_mode=ParseMode.MARKDOWN)
    
    elif text == "🔄 sᴛᴀʀᴛ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ":
        await update.message.reply_text("👋 ᴜsᴇ /start ᴛᴏ ʙᴇɢɪɴ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ!", reply_markup=VERIFY_KEYBOARD)

# ============ ADMIN MESSAGE HANDLER ============
async def handle_admin_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    text = update.message.text.strip()
    awaiting = context.user_data.get("awaiting")
    if not awaiting: await handle_keyboard_message(update, context); return
    
    if awaiting == "channel_username":
        try:
            username = text.replace("@","").strip()
            chat = await context.bot.get_chat(f"@{username}")
            try: link = (await context.bot.create_chat_invite_link(chat.id)).invite_link
            except: link = f"https://t.me/{username}"
            get_collection("channels").insert_one({"channel_id": chat.id, "channel_name": f"@{username}", "invite_link": link, "active": True, "added_date": datetime.now()})
            context.user_data.clear()
            await update.message.reply_text(f"✅ *ᴄʜᴀɴɴᴇʟ ᴀᴅᴅᴇᴅ!*\n\n📱 {chat.title}\n🆔 `{chat.id}`\n👥 ᴍᴇᴍʙᴇʀs: {await chat.get_member_count()}", reply_markup=create_admin_keyboard(), parse_mode=ParseMode.MARKDOWN)
        except Exception as e: await update.message.reply_text("❌ ꜰᴀɪʟᴇᴅ! ᴍᴀᴋᴇ sᴜʀᴇ ᴄʜᴀɴɴᴇʟ ɪs ᴘᴜʙʟɪᴄ & ʙᴏᴛ ɪs ᴀᴅᴍɪɴ.")
    elif awaiting == "link_name":
        context.user_data["link_name"] = text; context.user_data["awaiting"] = "link_url"
        await update.message.reply_text("🔗 ɴᴏᴡ sᴇɴᴅ ᴛʜᴇ ᴜʀʟ:")
    elif awaiting == "link_url":
        name = context.user_data.get("link_name","Link")
        get_collection("external_links").insert_one({"name": name, "url": text, "active": True, "added_date": datetime.now()})
        increment_verification_version(); context.user_data.clear()
        await update.message.reply_text(f"✅ *{name}* ᴀᴅᴅᴇᴅ!\n🔄 ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴠᴇʀsɪᴏɴ ᴜᴘᴅᴀᴛᴇᴅ.", reply_markup=create_admin_keyboard())
    elif awaiting == "payout_channel":
        try:
            username = text.replace("@","").strip()
            chat = await context.bot.get_chat(f"@{username}")
            get_collection("settings").update_one({"type": "payout_channel"}, {"$set": {"channel_id": chat.id, "channel_name": f"@{username}"}}, upsert=True)
            context.user_data.clear()
            await update.message.reply_text(f"✅ ᴘᴀʏᴏᴜᴛ ᴄʜᴀɴɴᴇʟ sᴇᴛ: @{username}!", reply_markup=create_admin_keyboard())
        except: await update.message.reply_text("❌ ᴄʜᴀɴɴᴇʟ ɴᴏᴛ ꜰᴏᴜɴᴅ!")

# ============ ADMIN CALLBACKS ============
async def handle_admin_callbacks(update, context):
    q = update.callback_query; d = q.data; uid = q.from_user.id
    if uid not in ADMIN_IDS: await q.answer("❌ ᴜɴᴀᴜᴛʜᴏʀɪᴢᴇᴅ!", show_alert=True); return
    
    NAV_BUTTONS = {"admin_panel","admin_manage_channels","admin_manage_links","admin_manage_tasks","admin_points_config","admin_groups_menu","admin_withdrawals"}
    if d in NAV_BUTTONS: context.user_data.clear()
    
    if d == "admin_stats":
        u = get_collection("users").count_documents({})
        g = (get_collection("settings").find_one({"type":"bot_stats"}) or {}).get("total_groups",0)
        w = get_collection("withdraw_requests").count_documents({})
        p = get_collection("withdraw_requests").count_documents({"status":"pending"})
        await q.message.edit_text(
            "╔══════════════════════════╗\n"
            "║   📊 ʙᴏᴛ sᴛᴀᴛɪsᴛɪᴄs    ║\n"
            "╚══════════════════════════╝\n\n"
            f"👥 ᴛᴏᴛᴀʟ ᴜsᴇʀs: *{u}*\n"
            f"📱 ᴛᴏᴛᴀʟ ɢʀᴏᴜᴘs: *{g}*\n"
            f"💳 ᴡɪᴛʜᴅʀᴀᴡᴀʟs: *{w}*\n"
            f"⏳ ᴘᴇɴᴅɪɴɢ: *{p}*",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ᴘᴀɴᴇʟ", callback_data="admin_panel")]]), parse_mode=ParseMode.MARKDOWN)
    
    elif d == "admin_manage_channels":
        chs = list(get_collection("channels").find({"active":True}))
        kb = [[InlineKeyboardButton(f"❌ {c['channel_name']}", callback_data=f"admin_remove_ch_{c['_id']}")] for c in chs]
        kb.append([InlineKeyboardButton("➕ ᴀᴅᴅ ᴄʜᴀɴɴᴇʟ", callback_data="admin_add_channel")])
        kb.append([InlineKeyboardButton("🔙 ᴘᴀɴᴇʟ", callback_data="admin_panel")])
        await q.message.edit_text(f"🔗 *ꜰᴏʀᴄᴇ ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟs*\n\nᴀᴄᴛɪᴠᴇ: *{len(chs)}*", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    
    elif d == "admin_add_channel":
        context.user_data["awaiting"] = "channel_username"
        await q.message.edit_text("📢 sᴇɴᴅ @ᴜsᴇʀɴᴀᴍᴇ:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data="admin_manage_channels")]]), parse_mode=ParseMode.MARKDOWN)
    
    elif d.startswith("admin_remove_ch_"):
        get_collection("channels").delete_one({"_id": ObjectId(d.replace("admin_remove_ch_",""))}); await q.answer("✅ ʀᴇᴍᴏᴠᴇᴅ!", show_alert=True)
        chs = list(get_collection("channels").find({"active":True}))
        kb = [[InlineKeyboardButton(f"❌ {c['channel_name']}", callback_data=f"admin_remove_ch_{c['_id']}")] for c in chs]
        kb.append([InlineKeyboardButton("➕ ᴀᴅᴅ", callback_data="admin_add_channel")]); kb.append([InlineKeyboardButton("🔙 ᴘᴀɴᴇʟ", callback_data="admin_panel")])
        await q.message.edit_text(f"🔗 ᴄʜᴀɴɴᴇʟs: {len(chs)}", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    
    elif d == "admin_manage_links":
        links = list(get_collection("external_links").find({"active":True}))
        kb = [[InlineKeyboardButton(f"❌ {l['name']}", callback_data=f"admin_remove_link_{l['_id']}")] for l in links]
        kb.append([InlineKeyboardButton("➕ ᴀᴅᴅ ʟɪɴᴋ", callback_data="admin_add_link")]); kb.append([InlineKeyboardButton("🔙 ᴘᴀɴᴇʟ", callback_data="admin_panel")])
        await q.message.edit_text(f"🔗 *ᴇxᴛᴇʀɴᴀʟ ʟɪɴᴋs*\n\nᴀᴄᴛɪᴠᴇ: *{len(links)}*", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    
    elif d == "admin_add_link":
        context.user_data["awaiting"] = "link_name"
        await q.message.edit_text("➕ sᴇɴᴅ ʟɪɴᴋ ɴᴀᴍᴇ:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data="admin_manage_links")]]), parse_mode=ParseMode.MARKDOWN)
    
    elif d.startswith("admin_remove_link_"):
        get_collection("external_links").delete_one({"_id": ObjectId(d.replace("admin_remove_link_",""))}); await q.answer("✅ ʀᴇᴍᴏᴠᴇᴅ!", show_alert=True)
        links = list(get_collection("external_links").find({"active":True}))
        kb = [[InlineKeyboardButton(f"❌ {l['name']}", callback_data=f"admin_remove_link_{l['_id']}")] for l in links]
        kb.append([InlineKeyboardButton("➕ ᴀᴅᴅ", callback_data="admin_add_link")]); kb.append([InlineKeyboardButton("🔙 ᴘᴀɴᴇʟ", callback_data="admin_panel")])
        await q.message.edit_text(f"🔗 ʟɪɴᴋs: {len(links)}", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    
    elif d == "admin_set_payout":
        context.user_data["awaiting"] = "payout_channel"
        pc = get_payout_channel()
        await q.message.edit_text(
            f"📢 *sᴇᴛ ᴘᴀʏᴏᴜᴛ ᴄʜᴀɴɴᴇʟ*\n\n"
            f"ᴄᴜʀʀᴇɴᴛ: {f'`{pc}`' if pc else 'ɴᴏᴛ sᴇᴛ'}\n\n"
            "sᴇɴᴅ ᴄʜᴀɴɴᴇʟ @ᴜsᴇʀɴᴀᴍᴇ:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data="admin_panel")]]), parse_mode=ParseMode.MARKDOWN)
    
    elif d == "admin_how_it_works":
        await q.message.edit_text(
            "╔══════════════════════════╗\n"
            "║   ℹ️ ʜᴏᴡ ɪᴛ ᴡᴏʀᴋs    ║\n"
            "╚══════════════════════════╝\n\n"
            "1. sᴇᴛ ꜰᴏʀᴄᴇ ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟs\n"
            "2. ᴀᴅᴅ ᴇxᴛᴇʀɴᴀʟ ʟɪɴᴋs\n"
            "3. ᴄʀᴇᴀᴛᴇ ᴛᴀsᴋs\n"
            "4. sᴇᴛ ᴘᴏɪɴᴛs ᴄᴏɴꜰɪɢ\n"
            "5. sᴇᴛ ᴘᴀʏᴏᴜᴛ ᴄʜᴀɴɴᴇʟ\n\n"
            "ᴜsᴇʀs ᴡɪʟʟ:\n"
            "• ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟs\n"
            "• ᴄᴏᴍᴘʟᴇᴛᴇ ᴛᴀsᴋs\n"
            "• ᴇᴀʀɴ ᴘᴏɪɴᴛs\n"
            "• ᴡɪᴛʜᴅʀᴀᴡ ɪᴅs\n\n"
            "ᴡɪᴛʜᴅʀᴀᴡᴀʟs ɢᴏ ᴛᴏ ᴘᴀʏᴏᴜᴛ ᴄʜᴀɴɴᴇʟ!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ᴘᴀɴᴇʟ", callback_data="admin_panel")]]), parse_mode=ParseMode.MARKDOWN)
    
    elif d == "admin_manage_tasks":
        tasks = list(get_collection("tasks").find({}))
        kb = [[InlineKeyboardButton(f"{'✅' if t.get('active',True) else '❌'} {t['name']} ({t['points']})", callback_data=f"admin_toggle_task_{t['_id']}"), InlineKeyboardButton("🗑", callback_data=f"admin_remove_task_{t['_id']}")] for t in tasks]
        kb.append([InlineKeyboardButton("➕ ᴀᴅᴅ ᴛᴀsᴋ", callback_data="admin_add_task")]); kb.append([InlineKeyboardButton("🔙 ᴘᴀɴᴇʟ", callback_data="admin_panel")])
        await q.message.edit_text(f"📋 *ᴛᴀsᴋs:* {len(tasks)}", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    
    elif d == "admin_add_task":
        await q.message.edit_text("ᴜsᴇ: `/addtask name | pts | type | url`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="admin_manage_tasks")]]), parse_mode=ParseMode.MARKDOWN)
    
    elif d.startswith("admin_remove_task_"):
        get_collection("tasks").delete_one({"_id": ObjectId(d.replace("admin_remove_task_",""))}); await q.answer("✅ ʀᴇᴍᴏᴠᴇᴅ!", show_alert=True)
        tasks = list(get_collection("tasks").find({}))
        kb = [[InlineKeyboardButton(f"{'✅' if t.get('active',True) else '❌'} {t['name']} ({t['points']})", callback_data=f"admin_toggle_task_{t['_id']}"), InlineKeyboardButton("🗑", callback_data=f"admin_remove_task_{t['_id']}")] for t in tasks]
        kb.append([InlineKeyboardButton("➕ ᴀᴅᴅ", callback_data="admin_add_task")]); kb.append([InlineKeyboardButton("🔙 ᴘᴀɴᴇʟ", callback_data="admin_panel")])
        await q.message.edit_text(f"📋 ᴛᴀsᴋs: {len(tasks)}", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    
    elif d.startswith("admin_toggle_task_"):
        tid = ObjectId(d.replace("admin_toggle_task_","")); t = get_collection("tasks").find_one({"_id": tid})
        if t: get_collection("tasks").update_one({"_id": tid}, {"$set": {"active": not t.get("active",True)}})
        await q.answer("✅ ᴛᴏɢɢʟᴇᴅ!", show_alert=True)
        tasks = list(get_collection("tasks").find({}))
        kb = [[InlineKeyboardButton(f"{'✅' if t.get('active',True) else '❌'} {t['name']} ({t['points']})", callback_data=f"admin_toggle_task_{t['_id']}"), InlineKeyboardButton("🗑", callback_data=f"admin_remove_task_{t['_id']}")] for t in tasks]
        kb.append([InlineKeyboardButton("➕ ᴀᴅᴅ", callback_data="admin_add_task")]); kb.append([InlineKeyboardButton("🔙 ᴘᴀɴᴇʟ", callback_data="admin_panel")])
        await q.message.edit_text(f"📋 ᴛᴀsᴋs: {len(tasks)}", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    
    elif d == "admin_points_config":
        await q.message.edit_text(format_points_message(), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✏️ ᴇᴅɪᴛ", callback_data="admin_edit_points")], [InlineKeyboardButton("🔙 ᴘᴀɴᴇʟ", callback_data="admin_panel")]]), parse_mode=ParseMode.MARKDOWN)
    
    elif d == "admin_edit_points":
        await q.message.edit_text("✏️ `/setpoints key value`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="admin_points_config")]]), parse_mode=ParseMode.MARKDOWN)
    
    elif d == "admin_withdrawals":
        pending = list(get_collection("withdraw_requests").find({"status":"pending"}).limit(5))
        if not pending: await q.message.edit_text("✅ *ɴᴏ ᴘᴇɴᴅɪɴɢ ʀᴇǫᴜᴇsᴛs!*", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ᴘᴀɴᴇʟ", callback_data="admin_panel")]]), parse_mode=ParseMode.MARKDOWN)
        else:
            text = "💳 *ᴘᴇɴᴅɪɴɢ ᴡɪᴛʜᴅʀᴀᴡᴀʟs:*\n\n"; kb = []
            for req in pending:
                text += f"🔢 #{req['serial_no']} | 👤 {req.get('full_name','N/A')}\n💰 {req['points']} ᴘᴏɪɴᴛs\n\n"
                kb.append([InlineKeyboardButton(f"✅ ᴀᴘᴘʀᴏᴠᴇ #{req['serial_no']}", callback_data=f"admin_approve_{req['_id']}"), InlineKeyboardButton(f"❌ ʀᴇᴊᴇᴄᴛ #{req['serial_no']}", callback_data=f"admin_reject_{req['_id']}")])
            kb.append([InlineKeyboardButton("🔙 ᴘᴀɴᴇʟ", callback_data="admin_panel")])
            await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    
    elif d.startswith("admin_approve_"):
        r = get_collection("withdraw_requests").find_one_and_update({"_id": ObjectId(d.replace("admin_approve_","")), "status":"pending"}, {"$set":{"status":"completed","processed_date":datetime.now()}}, return_document=ReturnDocument.BEFORE)
        if r:
            try: await context.bot.send_message(r["user_id"], f"✅ *ᴀᴘᴘʀᴏᴠᴇᴅ!*\n\n🔢 ᴛᴏᴋᴇɴ: #{r['serial_no']}\n💰 ᴘᴏɪɴᴛs: {r['points']}\n\nʏᴏᴜʀ ɪᴅ ᴡɪʟʟ ʙᴇ sᴇɴᴛ sᴏᴏɴ!", parse_mode=ParseMode.MARKDOWN)
            except: pass
            await q.answer("✅ ᴀᴘᴘʀᴏᴠᴇᴅ!", show_alert=True)
        else: await q.answer("⚠️ ᴀʟʀᴇᴀᴅʏ ᴘʀᴏᴄᴇssᴇᴅ!", show_alert=True)
        pending = list(get_collection("withdraw_requests").find({"status":"pending"}).limit(5))
        if not pending: await q.message.edit_text("✅ *ɴᴏ ᴘᴇɴᴅɪɴɢ!*", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ᴘᴀɴᴇʟ", callback_data="admin_panel")]]))
        else:
            text = "💳 *ᴘᴇɴᴅɪɴɢ:*\n\n"; kb = []
            for req in pending:
                text += f"🔢 #{req['serial_no']}\n👤 {req.get('full_name','N/A')}\n💰 {req['points']} ᴘᴛs\n\n"
                kb.append([InlineKeyboardButton(f"✅ #{req['serial_no']}", callback_data=f"admin_approve_{req['_id']}"), InlineKeyboardButton(f"❌ #{req['serial_no']}", callback_data=f"admin_reject_{req['_id']}")])
            kb.append([InlineKeyboardButton("🔙 ᴘᴀɴᴇʟ", callback_data="admin_panel")])
            await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    
    elif d.startswith("admin_reject_"):
        r = get_collection("withdraw_requests").find_one_and_update({"_id": ObjectId(d.replace("admin_reject_","")), "status":"pending"}, {"$set":{"status":"rejected","processed_date":datetime.now()}}, return_document=ReturnDocument.BEFORE)
        if r:
            get_collection("users").update_one({"user_id": r["user_id"]}, {"$inc": {"points": r["points"]}})
            try: await context.bot.send_message(r["user_id"], f"❌ *ʀᴇᴊᴇᴄᴛᴇᴅ*\n\n🔢 ᴛᴏᴋᴇɴ: #{r['serial_no']}\n💰 {r['points']} ᴘᴏɪɴᴛs ʀᴇꜰᴜɴᴅᴇᴅ", parse_mode=ParseMode.MARKDOWN)
            except: pass
            await q.answer("❌ ʀᴇᴊᴇᴄᴛᴇᴅ & ʀᴇꜰᴜɴᴅᴇᴅ!", show_alert=True)
        else: await q.answer("⚠️ ᴀʟʀᴇᴀᴅʏ ᴘʀᴏᴄᴇssᴇᴅ!", show_alert=True)
        pending = list(get_collection("withdraw_requests").find({"status":"pending"}).limit(5))
        if not pending: await q.message.edit_text("✅ *ɴᴏ ᴘᴇɴᴅɪɴɢ!*", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ᴘᴀɴᴇʟ", callback_data="admin_panel")]]))
        else:
            text = "💳 *ᴘᴇɴᴅɪɴɢ:*\n\n"; kb = []
            for req in pending:
                text += f"🔢 #{req['serial_no']}\n👤 {req.get('full_name','N/A')}\n💰 {req['points']} ᴘᴛs\n\n"
                kb.append([InlineKeyboardButton(f"✅ #{req['serial_no']}", callback_data=f"admin_approve_{req['_id']}"), InlineKeyboardButton(f"❌ #{req['serial_no']}", callback_data=f"admin_reject_{req['_id']}")])
            kb.append([InlineKeyboardButton("🔙 ᴘᴀɴᴇʟ", callback_data="admin_panel")])
            await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    
    elif d == "admin_panel": await q.message.edit_text("🔐 *ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ*\n\nsᴇʟᴇᴄᴛ ᴀɴ ᴏᴘᴛɪᴏɴ:", reply_markup=create_admin_keyboard(), parse_mode=ParseMode.MARKDOWN)
    elif d == "admin_broadcast_menu": await q.message.edit_text("📢 ʀᴇᴘʟʏ + `/broadcast`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ᴘᴀɴᴇʟ", callback_data="admin_panel")]]), parse_mode=ParseMode.MARKDOWN)
    elif d == "admin_groups_menu": await q.message.edit_text(f"👥 *ɢʀᴏᴜᴘs:* {get_collection('groups').count_documents({})}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📊 sᴛᴀᴛs", callback_data="admin_group_stats")], [InlineKeyboardButton("📢 ʙʀᴏᴀᴅᴄᴀsᴛ", callback_data="admin_broadcast_groups")], [InlineKeyboardButton("🔙 ᴘᴀɴᴇʟ", callback_data="admin_panel")]]), parse_mode=ParseMode.MARKDOWN)
    elif d == "admin_group_stats":
        groups = list(get_collection("groups").find({}).limit(10))
        await q.message.edit_text("\n".join([f"📱 {g.get('title','?')} | 👥{g.get('member_count',0)} | 💰{g.get('reward_points',0)}" for g in groups]) if groups else "ɴᴏ ɢʀᴏᴜᴘs!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="admin_groups_menu")]]), parse_mode=ParseMode.MARKDOWN)
    elif d == "admin_broadcast_groups": await q.message.edit_text("📢 ʀᴇᴘʟʏ + `/broadcastgroups`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="admin_groups_menu")]]), parse_mode=ParseMode.MARKDOWN)
    else: await q.answer("ᴄᴏᴍɪɴɢ sᴏᴏɴ!", show_alert=True)

# ============ BOT COMMANDS ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; args = context.args; uid = user.id
    get_collection("users").update_one({"user_id": uid}, {"$set": {"username": user.username or "", "full_name": user.full_name}})
    
    if args and args[0].startswith("ref_"):
        try:
            rid = int(args[0].replace("ref_",""))
            if rid != uid and not get_user(uid).get("referred_by") and not get_user(uid).get("referral_rewarded"):
                get_collection("users").update_one({"user_id": uid}, {"$set": {"pending_referrer": rid}})
        except: pass
    
    cv = get_verification_version(); u = get_user(uid)
    if u.get("verification_version", 0) != cv:
        get_collection("users").update_one({"user_id": uid}, {"$set": {"external_tasks_completed": False, "verification_version": 0}, "$unset": {"verification.external_required": "", "verification.external_attempts": ""}})
        u = get_user(uid)
    
    nj = await check_force_join(uid, context)
    if nj:
        kb = [[InlineKeyboardButton(f"📢 {c['channel_name']}", url=c['invite_link'])] for c in nj]
        kb.append([InlineKeyboardButton("✅ ᴄʜᴇᴄᴋ & ᴄᴏɴᴛɪɴᴜᴇ", callback_data="check_join")])
        await update.message.reply_text(
            "╔══════════════════════════╗\n"
            "║   👋 ᴡᴇʟᴄᴏᴍᴇ ᴀʙᴏᴀʀᴅ!   ║\n"
            "╚══════════════════════════╝\n\n"
            "⚠️ *ᴊᴏɪɴ ᴏᴜʀ ᴄʜᴀɴɴᴇʟs ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ:*\n\n"
            "👇 ᴄʟɪᴄᴋ ᴇᴀᴄʜ ʟɪɴᴋ ᴀɴᴅ ᴊᴏɪɴ\n"
            "✅ ᴛʜᴇɴ ᴄʟɪᴄᴋ 'ᴄʜᴇᴄᴋ & ᴄᴏɴᴛɪɴᴜᴇ'",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
        await update.message.reply_text("👇 ᴜsᴇ ʙᴜᴛᴛᴏɴs ʙᴇʟᴏᴡ:", reply_markup=VERIFY_KEYBOARD)
        return
    
    if u.get("force_join_completed") and u.get("external_tasks_completed"):
        await update.message.reply_text(
            "╔══════════════════════════╗\n"
            "║  👋 ᴡᴇʟᴄᴏᴍᴇ ʙᴀᴄᴋ!  ║\n"
            "╚══════════════════════════╝\n\n"
            "✅ ᴀʟʟ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴs ᴄᴏᴍᴘʟᴇᴛᴇ\n\n"
            "👇 ᴄʜᴏᴏsᴇ ᴀɴ ᴏᴘᴛɪᴏɴ:",
            reply_markup=MAIN_KEYBOARD, parse_mode=ParseMode.MARKDOWN)
    else:
        get_collection("users").update_one({"user_id": uid}, {"$set": {"force_join_completed": True}})
        links = list(get_collection("external_links").find({"active":True}))
        if links:
            kb = [[InlineKeyboardButton(f"🔗 {l['name']}", url=l['url'])] for l in links]
            kb.append([InlineKeyboardButton("✅ ɪ'ᴠᴇ ᴄᴏᴍᴘʟᴇᴛᴇᴅ ᴀʟʟ", callback_data="ext_tasks_complete")])
            await update.message.reply_text(
                "╔══════════════════════════╗\n"
                "║  ✅ ᴄʜᴀɴɴᴇʟs ᴊᴏɪɴᴇᴅ!  ║\n"
                "╚══════════════════════════╝\n\n"
                "📋 *ɴᴏᴡ ᴄᴏᴍᴘʟᴇᴛᴇ ᴛʜᴇsᴇ:*\n\n"
                "👇 ᴄʟɪᴄᴋ ᴇᴀᴄʜ ʟɪɴᴋ\n"
                "✅ ᴄᴏᴍᴘʟᴇᴛᴇ ᴛʜᴇ ᴀᴄᴛɪᴏɴ\n"
                "✅ ᴛʜᴇɴ ᴄʟɪᴄᴋ 'ɪ'ᴠᴇ ᴄᴏᴍᴘʟᴇᴛᴇᴅ ᴀʟʟ'",
                reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
        else:
            get_collection("users").update_one({"user_id": uid}, {"$set": {"external_tasks_completed": True, "verification_version": get_verification_version()}, "$unset": {"verification.external_required": "", "verification.external_attempts": ""}})
            await process_pending_group_rewards(uid, context)
            if get_user(uid).get("pending_referrer"): await handle_referral_points(uid, get_user(uid)["pending_referrer"], context)
            await update.message.reply_text(
                "╔══════════════════════════╗\n"
                "║  🎉 ᴀʟʟ ᴅᴏɴᴇ!  ║\n"
                "╚══════════════════════════╝\n\n"
                "✅ ʏᴏᴜ'ʀᴇ ꜰᴜʟʟʏ ᴠᴇʀɪꜰɪᴇᴅ!\n\n"
                "👇 ᴄʜᴏᴏsᴇ ᴀɴ ᴏᴘᴛɪᴏɴ:",
                reply_markup=MAIN_KEYBOARD, parse_mode=ParseMode.MARKDOWN)

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    await update.message.reply_text("🔐 *ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ*\n\nsᴇʟᴇᴄᴛ ᴀɴ ᴏᴘᴛɪᴏɴ ᴛᴏ ᴍᴀɴᴀɢᴇ:", reply_markup=create_admin_keyboard(), parse_mode=ParseMode.MARKDOWN)

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS or not update.message.reply_to_message: return
    msg = update.message.reply_to_message; users = get_collection("users").find({}); total = get_collection("users").count_documents({})
    s = await update.message.reply_text(f"📢 *ʙʀᴏᴀᴅᴄᴀsᴛɪɴɢ...* 0/{total}", parse_mode=ParseMode.MARKDOWN)
    ok = fail = 0
    for i, u in enumerate(users, 1):
        try: await msg.copy(chat_id=u["user_id"]); ok += 1
        except: fail += 1
        if i % 20 == 0: await s.edit_text(f"📢 ✅{ok} ❌{fail} 📊{i}/{total}")
        await asyncio.sleep(0.05)
    await s.edit_text(f"✅ *ᴅᴏɴᴇ!* sᴇɴᴛ: {ok}/{total}", parse_mode=ParseMode.MARKDOWN)

async def broadcast_groups_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS or not update.message.reply_to_message: return
    for g in get_collection("groups").find({"reward_given":True}):
        try: await update.message.reply_to_message.copy(chat_id=g["chat_id"])
        except: pass
        await asyncio.sleep(0.1)
    await update.message.reply_text("✅ *sᴇɴᴛ ᴛᴏ ᴀʟʟ ɢʀᴏᴜᴘs!*", parse_mode=ParseMode.MARKDOWN)

async def add_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    try:
        p = update.message.text.replace("/addchannel ","").split("|")
        get_collection("channels").insert_one({"channel_id": int(p[0].strip()), "channel_name": p[1].strip(), "invite_link": p[2].strip(), "active":True, "added_date":datetime.now()})
        await update.message.reply_text("✅ ᴄʜᴀɴɴᴇʟ ᴀᴅᴅᴇᴅ!")
    except: await update.message.reply_text("❌ ꜰᴏʀᴍᴀᴛ: /addchannel id | @name | link")

async def add_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    try:
        p = update.message.text.replace("/addlink ","").split("|")
        get_collection("external_links").insert_one({"name": p[0].strip(), "url": p[1].strip(), "active":True, "added_date":datetime.now()})
        increment_verification_version()
        await update.message.reply_text("✅ ʟɪɴᴋ ᴀᴅᴅᴇᴅ! ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴠᴇʀsɪᴏɴ ᴜᴘᴅᴀᴛᴇᴅ.")
    except: await update.message.reply_text("❌ ꜰᴏʀᴍᴀᴛ: /addlink name | url")

async def add_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    try:
        p = update.message.text.replace("/addtask ","").split("|")
        get_collection("tasks").insert_one({"name": p[0].strip(), "points": int(p[1].strip()), "type": p[2].strip(), "url": p[3].strip() if len(p)>3 else "", "active":True, "created_date":datetime.now()})
        await update.message.reply_text("✅ ᴛᴀsᴋ ᴀᴅᴅᴇᴅ!")
    except: await update.message.reply_text("❌ ꜰᴏʀᴍᴀᴛ: /addtask name | pts | type | url")

async def set_points_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    try:
        k, v = update.message.text.replace("/setpoints ","").split()
        pts = get_points_config()
        if k in pts: pts[k] = int(v); update_points_config(pts); await update.message.reply_text(f"✅ {k} = {v}")
        else: await update.message.reply_text("❌ ɪɴᴠᴀʟɪᴅ ᴋᴇʏ!")
    except: await update.message.reply_text("❌ ꜰᴏʀᴍᴀᴛ: /setpoints key value")

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    context.user_data.clear()
    await update.message.reply_text("❌ ᴄᴀɴᴄᴇʟʟᴇᴅ.", reply_markup=create_admin_keyboard())

async def handle_bot_added_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cm = update.my_chat_member
    if cm.new_chat_member.status != "administrator": return
    chat, added_by = cm.chat, cm.from_user
    if not added_by: return
    
    try: mc = await context.bot.get_chat_member_count(chat.id)
    except: mc = 0
    
    cfg, pts = get_points_config(), 0
    if 100 <= mc <= 1000: pts = cfg["group_add_small"]
    elif 1001 <= mc <= 2000: pts = cfg["group_add_medium"]
    elif 2001 <= mc <= 3000: pts = cfg["group_add_m2"]
    elif 3001 <= mc <= 5000: pts = cfg["group_add_m3"]
    elif 5001 <= mc <= 10000: pts = cfg["group_add_m4"]
    elif mc > 10000: pts = cfg["group_add_big"]
    
    if pts == 0:
        try: await context.bot.send_message(added_by.id, "❌ *ɴᴏ ʀᴇᴡᴀʀᴅ!*\n\nɢʀᴏᴜᴘ ʜᴀs ʟᴇss ᴛʜᴀɴ 100 ᴍᴇᴍʙᴇʀs.\nᴍɪɴɪᴍᴜᴍ 100 ᴍᴇᴍʙᴇʀs ʀᴇǫᴜɪʀᴇᴅ.", parse_mode=ParseMode.MARKDOWN)
        except: pass
        return
    
    try: get_collection("groups").update_one({"chat_id": chat.id}, {"$setOnInsert": {"chat_id": chat.id, "reward_given": False, "added_at": datetime.now()}, "$set": {"title": chat.title or "?", "member_count": mc, "added_by": added_by.id, "reward_points": pts}}, upsert=True)
    except: pass
    
    if await ensure_user_verified(added_by.id, context):
        if credit_group_reward_atomic(chat.id, added_by.id, chat.title, mc, pts):
            try: await context.bot.send_message(added_by.id, f"🎉 *ɢʀᴏᴜᴘ ʀᴇᴡᴀʀᴅ ᴇᴀʀɴᴇᴅ!*\n\n📱 ɢʀᴏᴜᴘ: {chat.title}\n👥 ᴍᴇᴍʙᴇʀs: {mc}\n💰 ʀᴇᴡᴀʀᴅ: *{pts}* ᴘᴏɪɴᴛs", parse_mode=ParseMode.MARKDOWN)
            except: pass
    else:
        create_group_pending_reward(chat.id, added_by.id, chat.title, mc, pts)
        try: await context.bot.send_message(added_by.id, f"⚠️ *ᴘᴇɴᴅɪɴɢ ʀᴇᴡᴀʀᴅ!*\n\n📱 ɢʀᴏᴜᴘ: {chat.title}\n💰 ᴘᴏᴛᴇɴᴛɪᴀʟ: *{pts}* ᴘᴏɪɴᴛs\n\n❌ ᴄᴏᴍᴘʟᴇᴛᴇ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ꜰɪʀsᴛ!\nᴜsᴇ /start", parse_mode=ParseMode.MARKDOWN)
        except: pass

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")

def main():
    init_db()
    Thread(target=run_web_server, daemon=True).start()
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("broadcastgroups", broadcast_groups_command))
    app.add_handler(CommandHandler("addchannel", add_channel_command))
    app.add_handler(CommandHandler("addlink", add_link_command))
    app.add_handler(CommandHandler("addtask", add_task_command))
    app.add_handler(CommandHandler("setpoints", set_points_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.User(user_id=ADMIN_IDS) & ~filters.COMMAND, handle_admin_messages))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_keyboard_message))
    app.add_handler(ChatMemberHandler(handle_bot_added_to_group, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_error_handler(error_handler)
    
    logger.info("🚀 Premium Bot Started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
