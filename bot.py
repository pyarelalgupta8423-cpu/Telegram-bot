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

# ============ KEYBOARDS ============
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🆔 Get ID"), KeyboardButton("🔗 Refer & Earn")],
        [KeyboardButton("📊 Status"), KeyboardButton("📋 Tasks")],
        [KeyboardButton("💰 Balance"), KeyboardButton("📈 My Stats")]
    ],
    resize_keyboard=True
)

VERIFY_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton("🔄 Start Verification")]],
    resize_keyboard=True
)

# ============ HELPERS ============
def create_main_menu_keyboard(user_id):
    u = get_user(user_id)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🆔 Get ID", callback_data="main_get_id")],
        [InlineKeyboardButton("🔗 Refer & Earn", callback_data="main_refer")],
        [InlineKeyboardButton("📊 Status", callback_data="main_available_ids")],
        [InlineKeyboardButton("📋 Tasks", callback_data="main_tasks")],
        [InlineKeyboardButton(f"💰 Balance: {u['points']} pts", callback_data="main_balance")],
        [InlineKeyboardButton("📈 My Stats", callback_data="main_stats")]
    ])

def create_admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast_menu")],
        [InlineKeyboardButton("📊 Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("🔗 Channels", callback_data="admin_manage_channels")],
        [InlineKeyboardButton("🔗 Links", callback_data="admin_manage_links")],
        [InlineKeyboardButton("📋 Tasks", callback_data="admin_manage_tasks")],
        [InlineKeyboardButton("💎 Points Config", callback_data="admin_points_config")],
        [InlineKeyboardButton("👥 Groups", callback_data="admin_groups_menu")],
        [InlineKeyboardButton("💰 Withdrawals", callback_data="admin_withdrawals")]
    ])

def format_points_message():
    p = get_points_config()
    return (
        "💎 *Points Config*\n\n"
        f"👥 Referral: L1={p['refer_level_1']} | L2={p['refer_level_2']}\n\n"
        f"📱 Groups:\n"
        f"• 100-1K: {p['group_add_small']}\n"
        f"• 1K-2K: {p['group_add_medium']}\n"
        f"• 2K-3K: {p['group_add_m2']}\n"
        f"• 3K-5K: {p['group_add_m3']}\n"
        f"• 5K-10K: {p['group_add_m4']}\n"
        f"• >10K: {p['group_add_big']}\n\n"
        f"⚠️ <100: No reward\n"
        f"🎯 Min Withdraw: {p['min_withdraw']}"
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
        try: await context.bot.send_message(uid, f"🎉 *Pending Reward!*\n📱 {r['title']}\n💰 *{r['points']}* pts", parse_mode=ParseMode.MARKDOWN)
        except: pass

async def handle_referral_points(uid, rid, context):
    if not await ensure_user_verified(uid, context) or uid == rid: return False
    r = credit_referral_atomic(uid, rid)
    if not r: return False
    try: await context.bot.send_message(r["referrer_id"], f"🎉 *Referral!* +{r['level1_points']} pts", parse_mode=ParseMode.MARKDOWN)
    except: pass
    if r.get("level2_id"):
        try: await context.bot.send_message(r["level2_id"], f"🎉 *L2 Bonus!* +{r['level2_points']} pts", parse_mode=ParseMode.MARKDOWN)
        except: pass
    return True

# ============ TASK HANDLERS ============
async def handle_force_join_complete(update, context):
    q = update.callback_query
    get_collection("users").update_one({"user_id": q.from_user.id}, {"$set": {"force_join_completed": True}})
    links = list(get_collection("external_links").find({"active": True}))
    if links:
        kb = [[InlineKeyboardButton(f"🔗 {l['name']}", url=l['url'])] for l in links]
        kb.append([InlineKeyboardButton("✅ Completed All", callback_data="ext_tasks_complete")])
        await q.message.edit_text("✅ *Channels Done!*\n\n📋 Complete external tasks:", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    else:
        await complete_verification(update, context, q.from_user.id)

async def handle_external_tasks_complete(update, context):
    q = update.callback_query; uid = q.from_user.id
    if not await ensure_force_join_verified(uid, context): await q.answer("❌ Join channels!", show_alert=True); return
    u = get_user(uid); v = u.get("verification", {})
    req = v.get("external_required")
    if not req:
        req = random.randint(2, 3)
        get_collection("users").update_one({"user_id": uid}, {"$set": {"verification.external_required": req, "verification.external_attempts": 1}})
        await q.answer(f"⚠️ 1/{req}", show_alert=True); return
    cur = v.get("external_attempts", 0) + 1
    get_collection("users").update_one({"user_id": uid}, {"$set": {"verification.external_attempts": cur}})
    if cur < req: await q.answer(f"⚠️ {cur}/{req}", show_alert=True); return
    await complete_verification(update, context, uid)

async def complete_verification(update, context, uid):
    q = update.callback_query
    if not await ensure_force_join_verified(uid, context): await q.answer("❌ Stay in channels!", show_alert=True); return
    get_collection("users").update_one({"user_id": uid}, {"$set": {"external_tasks_completed": True, "verification_version": get_verification_version()}, "$unset": {"verification.external_required": "", "verification.external_attempts": ""}})
    await process_pending_group_rewards(uid, context)
    u = get_user(uid)
    if u.get("pending_referrer"): await handle_referral_points(uid, u["pending_referrer"], context)
    await q.message.edit_text("🎉 *Done!*", reply_markup=create_main_menu_keyboard(uid), parse_mode=ParseMode.MARKDOWN)

# ============ CALLBACK ROUTER ============
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; d = q.data; uid = q.from_user.id
    
    if d == "main_menu":
        if await ensure_user_verified(uid, context):
            await q.message.edit_text("📱 *Main Menu*", reply_markup=create_main_menu_keyboard(uid), parse_mode="Markdown")
        else:
            await q.message.edit_text("⚠️ Verification required!\nUse /start", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Start", callback_data="start_verify")]]), parse_mode="Markdown")
    
    elif d == "main_get_id": await get_id_handler(update, context)
    elif d == "main_refer": await refer_menu_handler(update, context)
    elif d == "main_available_ids": await available_ids_handler(update, context)
    elif d == "main_tasks": await tasks_menu_handler(update, context)
    elif d == "main_balance": await q.answer(f"💰 {get_user(uid)['points']} pts", show_alert=True)
    elif d == "main_stats": await show_stats(update, context)
    
    elif d == "check_join":
        if await check_force_join(uid, context): await q.answer("❌ Join channels!", show_alert=True)
        else: await q.answer("✅ Verified!"); await handle_force_join_complete(update, context)
    
    elif d == "start_verify":
        cv = get_verification_version(); u = get_user(uid)
        if u.get("verification_version", 0) != cv:
            get_collection("users").update_one({"user_id": uid}, {"$set": {"external_tasks_completed": False, "verification_version": 0}, "$unset": {"verification.external_required": "", "verification.external_attempts": ""}})
        nj = await check_force_join(uid, context)
        if nj:
            kb = [[InlineKeyboardButton(f"📢 {c['channel_name']}", url=c['invite_link'])] for c in nj]
            kb.append([InlineKeyboardButton("✅ Check", callback_data="check_join")])
            await q.message.edit_text("⚠️ *Join:*", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        else:
            await handle_force_join_complete(update, context)
    
    elif d == "ext_tasks_complete": await handle_external_tasks_complete(update, context)
    elif d.startswith("task_do_"): await handle_specific_task(update, context, d.replace("task_do_", ""))
    elif d.startswith("task_verify_"): await verify_task_completion(update, context, d.replace("task_verify_", ""))
    elif d == "admin_panel" or d.startswith("admin_"): await handle_admin_callbacks(update, context)
    else: await q.answer("❓ Unknown", show_alert=True)

# ============ MENU HANDLERS ============
async def refer_menu_handler(update, context):
    q = update.callback_query
    link = f"https://t.me/{context.bot.username}?start=ref_{q.from_user.id}"
    await q.message.edit_text(f"🔗 `{link}`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh", callback_data="main_refer")], [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]), parse_mode=ParseMode.MARKDOWN)

async def get_id_handler(update, context):
    q = update.callback_query; cfg = get_points_config()
    if not await ensure_user_verified(q.from_user.id, context): await q.answer("❌ Verify!", show_alert=True); return
    r = create_withdrawal_atomic(q.from_user.id, cfg["min_withdraw"], q.from_user.username or "N/A", q.from_user.full_name)
    if not r: await q.answer(f"❌ Need {cfg['min_withdraw']} pts!", show_alert=True); return
    await q.message.edit_text(f"✅ Token: `{r['serial_no']}`\n💰 -{r['withdraw_amount']} | 💎 {r['new_balance']}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]]), parse_mode=ParseMode.MARKDOWN)

async def show_stats(update, context):
    q = update.callback_query; u = get_user(q.from_user.id)
    await q.message.edit_text(f"📊 💰{u['points']} | 👥{len(u.get('referrals',[]))} | ✅{len(u.get('completed_tasks',[]))}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]), parse_mode=ParseMode.MARKDOWN)

async def available_ids_handler(update, context):
    q = update.callback_query
    await q.message.edit_text(f"🆔 Total: {get_collection('withdraw_requests').count_documents({})} | ⏳ {get_collection('withdraw_requests').count_documents({'status':'pending'})} | ✅ {get_collection('withdraw_requests').count_documents({'status':'completed'})}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]), parse_mode=ParseMode.MARKDOWN)

async def tasks_menu_handler(update, context):
    q = update.callback_query
    if not await ensure_user_verified(q.from_user.id, context): await q.answer("❌ Verify!", show_alert=True); return
    tasks = list(get_collection("tasks").find({"active": True}))
    kb = [[InlineKeyboardButton(f"📌 {t['name']} (+{t['points']})", callback_data=f"task_do_{t['_id']}")] for t in tasks]
    kb.append([InlineKeyboardButton("🔙 Menu", callback_data="main_menu")])
    await q.message.edit_text("📋 *Tasks*", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

async def handle_specific_task(update, context, tid):
    q = update.callback_query; t = get_task_by_id(tid)
    if not t: await q.answer("❌ Not found!", show_alert=True); return
    if not await ensure_user_verified(q.from_user.id, context): await q.answer("❌ Verify!", show_alert=True); return
    u = get_user(q.from_user.id)
    if tid in [str(x) for x in u.get("completed_tasks",[])]: await q.answer("✅ Done!", show_alert=True); return
    if t["type"] == "add_to_group":
        await q.message.edit_text(f"📋 Add @{context.bot.username} as admin!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main_tasks")]]), parse_mode=ParseMode.MARKDOWN)
    else:
        a = u.get("task_attempts",{}).get(tid,0)
        await q.message.edit_text(f"📋 *{t['name']}*\n💰 {t['points']} pts\n⏳ {a}/2", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Open", url=t['url'])], [InlineKeyboardButton("🎯 Claim", callback_data=f"task_verify_{tid}")], [InlineKeyboardButton("🔙 Back", callback_data="main_tasks")]]), parse_mode=ParseMode.MARKDOWN)

async def verify_task_completion(update, context, tid):
    q = update.callback_query; t = get_task_by_id(tid)
    if not t: await q.answer("❌ Not found!", show_alert=True); return
    if not await ensure_user_verified(q.from_user.id, context): await q.answer("❌ Verify!", show_alert=True); return
    uid = q.from_user.id; u = get_user(uid); a = u.get("task_attempts",{}).get(tid,0) + 1
    if a < 2:
        get_collection("users").update_one({"user_id": uid}, {"$set": {f"task_attempts.{tid}": a}})
        await q.answer(f"⚠️ {2-a} more!", show_alert=True); return
    r = get_collection("users").update_one({"user_id": uid, "completed_tasks": {"$ne": ObjectId(tid)}}, {"$inc": {"points": t["points"]}, "$addToSet": {"completed_tasks": ObjectId(tid)}, "$set": {f"task_attempts.{tid}": a}})
    if r.modified_count == 0: await q.answer("✅ Already!", show_alert=True); return
    await q.answer(f"✅ +{t['points']}!", show_alert=True)
    await tasks_menu_handler(update, context)

# ============ KEYBOARD MESSAGE HANDLER ============
async def handle_keyboard_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text; uid = update.effective_user.id
    
    if text == "🆔 Get ID":
        if not await ensure_user_verified(uid, context): await update.message.reply_text("❌ Verify!", reply_markup=VERIFY_KEYBOARD); return
        r = create_withdrawal_atomic(uid, get_points_config()["min_withdraw"], update.effective_user.username or "N/A", update.effective_user.full_name)
        await update.message.reply_text(f"✅ Token: `{r['serial_no']}`\n💰 -{r['withdraw_amount']} | 💎 {r['new_balance']}" if r else f"❌ Need {get_points_config()['min_withdraw']} pts!", reply_markup=MAIN_KEYBOARD, parse_mode=ParseMode.MARKDOWN)
    
    elif text == "🔗 Refer & Earn":
        await update.message.reply_text(f"🔗 `https://t.me/{context.bot.username}?start=ref_{uid}`", reply_markup=MAIN_KEYBOARD, parse_mode=ParseMode.MARKDOWN)
    
    elif text == "📊 Status":
        t = get_collection("withdraw_requests").count_documents({}); p = get_collection("withdraw_requests").count_documents({"status":"pending"}); c = get_collection("withdraw_requests").count_documents({"status":"completed"})
        await update.message.reply_text(f"🆔 Total: {t} | ⏳{p} | ✅{c}", reply_markup=MAIN_KEYBOARD)
    
    elif text == "📋 Tasks":
        if not await ensure_user_verified(uid, context): await update.message.reply_text("❌ Verify!", reply_markup=VERIFY_KEYBOARD); return
        tasks = list(get_collection("tasks").find({"active":True}))
        await update.message.reply_text("📋 *Tasks*", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"📌 {t['name']} (+{t['points']})", callback_data=f"task_do_{t['_id']}")] for t in tasks]) if tasks else None or await update.message.reply_text("No tasks!", reply_markup=MAIN_KEYBOARD), parse_mode=ParseMode.MARKDOWN)
    
    elif text == "💰 Balance": await update.message.reply_text(f"💰 {get_user(uid)['points']} pts", reply_markup=MAIN_KEYBOARD)
    elif text == "📈 My Stats":
        u = get_user(uid); await update.message.reply_text(f"📊 💰{u['points']} | 👥{len(u.get('referrals',[]))} | ✅{len(u.get('completed_tasks',[]))}", reply_markup=MAIN_KEYBOARD)
    elif text == "🔄 Start Verification": await update.message.reply_text("Use /start!", reply_markup=VERIFY_KEYBOARD)

# ============ ADMIN MESSAGE HANDLER ============
async def handle_admin_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    
    text = update.message.text.strip()
    awaiting = context.user_data.get("awaiting")
    
    # FIXED: Pass to keyboard handler if not in awaiting mode
    if not awaiting:
        await handle_keyboard_message(update, context)
        return
    
    if awaiting == "channel_username":
        try:
            username = text.replace("@","").strip()
            chat = await context.bot.get_chat(f"@{username}")
            try: link = (await context.bot.create_chat_invite_link(chat.id)).invite_link
            except: link = f"https://t.me/{username}"
            get_collection("channels").insert_one({"channel_id": chat.id, "channel_name": f"@{username}", "invite_link": link, "active": True, "added_date": datetime.now()})
            context.user_data.clear()
            await update.message.reply_text(f"✅ Added: {chat.title}\n🆔 `{chat.id}`", reply_markup=create_admin_keyboard(), parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Channel error: {e}")
            await update.message.reply_text("❌ Failed! Make sure channel is public & bot is admin.")
    
    elif awaiting == "link_name":
        context.user_data["link_name"] = text; context.user_data["awaiting"] = "link_url"
        await update.message.reply_text("🔗 Send URL:")
    
    elif awaiting == "link_url":
        name = context.user_data.get("link_name", "Link")
        get_collection("external_links").insert_one({"name": name, "url": text, "active": True, "added_date": datetime.now()})
        increment_verification_version(); context.user_data.clear()
        await update.message.reply_text(f"✅ '{name}' added!\n🔄 Version updated.", reply_markup=create_admin_keyboard())

# ============ ADMIN CALLBACKS ============
async def handle_admin_callbacks(update, context):
    q = update.callback_query; d = q.data; uid = q.from_user.id
    if uid not in ADMIN_IDS: await q.answer("❌ Unauthorized!", show_alert=True); return
    
    # FIXED: Clear awaiting state on navigation
    NAV_BUTTONS = {"admin_panel", "admin_manage_channels", "admin_manage_links", "admin_manage_tasks", "admin_points_config", "admin_groups_menu", "admin_withdrawals"}
    if d in NAV_BUTTONS: context.user_data.clear()
    
    if d == "admin_stats":
        u = get_collection("users").count_documents({}); g = (get_collection("settings").find_one({"type":"bot_stats"}) or {}).get("total_groups",0)
        await q.message.edit_text(f"📊 👥{u} | 📱{g} | 💰{get_collection('withdraw_requests').count_documents({})} | ⏳{get_collection('withdraw_requests').count_documents({'status':'pending'})}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Panel", callback_data="admin_panel")]]), parse_mode=ParseMode.MARKDOWN)
    
    elif d == "admin_manage_channels":
        chs = list(get_collection("channels").find({"active":True}))
        kb = [[InlineKeyboardButton(f"❌ {c['channel_name']}", callback_data=f"admin_remove_ch_{c['_id']}")] for c in chs]
        kb.append([InlineKeyboardButton("➕ Add", callback_data="admin_add_channel")]); kb.append([InlineKeyboardButton("🔙 Panel", callback_data="admin_panel")])
        await q.message.edit_text(f"🔗 Channels: {len(chs)}", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    
    elif d == "admin_add_channel":
        context.user_data["awaiting"] = "channel_username"
        await q.message.edit_text("📢 Send @username:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_manage_channels")]]), parse_mode=ParseMode.MARKDOWN)
    
    elif d.startswith("admin_remove_ch_"):
        get_collection("channels").delete_one({"_id": ObjectId(d.replace("admin_remove_ch_",""))}); await q.answer("✅ Removed!", show_alert=True)
        chs = list(get_collection("channels").find({"active":True}))
        kb = [[InlineKeyboardButton(f"❌ {c['channel_name']}", callback_data=f"admin_remove_ch_{c['_id']}")] for c in chs]
        kb.append([InlineKeyboardButton("➕ Add", callback_data="admin_add_channel")]); kb.append([InlineKeyboardButton("🔙 Panel", callback_data="admin_panel")])
        await q.message.edit_text(f"🔗 Channels: {len(chs)}", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    
    elif d == "admin_manage_links":
        links = list(get_collection("external_links").find({"active":True}))
        kb = [[InlineKeyboardButton(f"❌ {l['name']}", callback_data=f"admin_remove_link_{l['_id']}")] for l in links]
        kb.append([InlineKeyboardButton("➕ Add", callback_data="admin_add_link")]); kb.append([InlineKeyboardButton("🔙 Panel", callback_data="admin_panel")])
        await q.message.edit_text(f"🔗 Links: {len(links)}", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    
    elif d == "admin_add_link":
        context.user_data["awaiting"] = "link_name"
        await q.message.edit_text("➕ Send name:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_manage_links")]]), parse_mode=ParseMode.MARKDOWN)
    
    elif d.startswith("admin_remove_link_"):
        get_collection("external_links").delete_one({"_id": ObjectId(d.replace("admin_remove_link_",""))}); await q.answer("✅ Removed!", show_alert=True)
        links = list(get_collection("external_links").find({"active":True}))
        kb = [[InlineKeyboardButton(f"❌ {l['name']}", callback_data=f"admin_remove_link_{l['_id']}")] for l in links]
        kb.append([InlineKeyboardButton("➕ Add", callback_data="admin_add_link")]); kb.append([InlineKeyboardButton("🔙 Panel", callback_data="admin_panel")])
        await q.message.edit_text(f"🔗 Links: {len(links)}", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    
    elif d == "admin_manage_tasks":
        tasks = list(get_collection("tasks").find({}))
        kb = [[InlineKeyboardButton(f"{'✅' if t.get('active',True) else '❌'} {t['name']} ({t['points']})", callback_data=f"admin_toggle_task_{t['_id']}"), InlineKeyboardButton("🗑", callback_data=f"admin_remove_task_{t['_id']}")] for t in tasks]
        kb.append([InlineKeyboardButton("➕ Add", callback_data="admin_add_task")]); kb.append([InlineKeyboardButton("🔙 Panel", callback_data="admin_panel")])
        await q.message.edit_text(f"📋 Tasks: {len(tasks)}", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    
    elif d == "admin_add_task":
        await q.message.edit_text("Use: `/addtask name | pts | type | url`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_manage_tasks")]]), parse_mode=ParseMode.MARKDOWN)
    
    elif d.startswith("admin_remove_task_"):
        get_collection("tasks").delete_one({"_id": ObjectId(d.replace("admin_remove_task_",""))}); await q.answer("✅ Removed!", show_alert=True)
        tasks = list(get_collection("tasks").find({}))
        kb = [[InlineKeyboardButton(f"{'✅' if t.get('active',True) else '❌'} {t['name']} ({t['points']})", callback_data=f"admin_toggle_task_{t['_id']}"), InlineKeyboardButton("🗑", callback_data=f"admin_remove_task_{t['_id']}")] for t in tasks]
        kb.append([InlineKeyboardButton("➕ Add", callback_data="admin_add_task")]); kb.append([InlineKeyboardButton("🔙 Panel", callback_data="admin_panel")])
        await q.message.edit_text(f"📋 Tasks: {len(tasks)}", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    
    elif d.startswith("admin_toggle_task_"):
        tid = ObjectId(d.replace("admin_toggle_task_","")); t = get_collection("tasks").find_one({"_id": tid})
        if t: get_collection("tasks").update_one({"_id": tid}, {"$set": {"active": not t.get("active",True)}})
        await q.answer("✅ Toggled!", show_alert=True)
        tasks = list(get_collection("tasks").find({}))
        kb = [[InlineKeyboardButton(f"{'✅' if t.get('active',True) else '❌'} {t['name']} ({t['points']})", callback_data=f"admin_toggle_task_{t['_id']}"), InlineKeyboardButton("🗑", callback_data=f"admin_remove_task_{t['_id']}")] for t in tasks]
        kb.append([InlineKeyboardButton("➕ Add", callback_data="admin_add_task")]); kb.append([InlineKeyboardButton("🔙 Panel", callback_data="admin_panel")])
        await q.message.edit_text(f"📋 Tasks: {len(tasks)}", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    
    elif d == "admin_points_config":
        await q.message.edit_text(format_points_message(), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✏️ Edit", callback_data="admin_edit_points")], [InlineKeyboardButton("🔙 Panel", callback_data="admin_panel")]]), parse_mode=ParseMode.MARKDOWN)
    
    elif d == "admin_edit_points":
        await q.message.edit_text("✏️ `/setpoints key value`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_points_config")]]), parse_mode=ParseMode.MARKDOWN)
    
    elif d == "admin_withdrawals":
        pending = list(get_collection("withdraw_requests").find({"status":"pending"}).limit(5))
        if not pending: await q.message.edit_text("✅ No pending!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Panel", callback_data="admin_panel")]]))
        else:
            text = "💰 *Pending:*\n\n"; kb = []
            for req in pending:
                text += f"#{req['serial_no']} | {req.get('full_name','N/A')} | {req['points']} pts\n"
                kb.append([InlineKeyboardButton(f"✅ #{req['serial_no']}", callback_data=f"admin_approve_{req['_id']}"), InlineKeyboardButton("❌ Reject", callback_data=f"admin_reject_{req['_id']}")])
            kb.append([InlineKeyboardButton("🔙 Panel", callback_data="admin_panel")])
            await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    
    elif d.startswith("admin_approve_"):
        r = get_collection("withdraw_requests").find_one_and_update({"_id": ObjectId(d.replace("admin_approve_","")), "status":"pending"}, {"$set":{"status":"completed","processed_date":datetime.now()}}, return_document=ReturnDocument.BEFORE)
        if r: 
            try: await context.bot.send_message(r["user_id"], f"✅ Approved! #{r['serial_no']}", parse_mode=ParseMode.MARKDOWN)
            except: pass
            await q.answer("✅ Approved!", show_alert=True)
        else: await q.answer("⚠️ Already processed!", show_alert=True)
        pending = list(get_collection("withdraw_requests").find({"status":"pending"}).limit(5))
        if not pending: await q.message.edit_text("✅ No pending!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Panel", callback_data="admin_panel")]]))
        else:
            text = "💰 *Pending:*\n\n"; kb = []
            for req in pending:
                text += f"#{req['serial_no']} | {req.get('full_name','N/A')} | {req['points']} pts\n"
                kb.append([InlineKeyboardButton(f"✅ #{req['serial_no']}", callback_data=f"admin_approve_{req['_id']}"), InlineKeyboardButton("❌ Reject", callback_data=f"admin_reject_{req['_id']}")])
            kb.append([InlineKeyboardButton("🔙 Panel", callback_data="admin_panel")])
            await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    
    elif d.startswith("admin_reject_"):
        r = get_collection("withdraw_requests").find_one_and_update({"_id": ObjectId(d.replace("admin_reject_","")), "status":"pending"}, {"$set":{"status":"rejected","processed_date":datetime.now()}}, return_document=ReturnDocument.BEFORE)
        if r:
            get_collection("users").update_one({"user_id": r["user_id"]}, {"$inc": {"points": r["points"]}})
            try: await context.bot.send_message(r["user_id"], f"❌ Rejected\n💰 {r['points']} pts refunded", parse_mode=ParseMode.MARKDOWN)
            except: pass
            await q.answer("❌ Refunded!", show_alert=True)
        else: await q.answer("⚠️ Already processed!", show_alert=True)
        pending = list(get_collection("withdraw_requests").find({"status":"pending"}).limit(5))
        if not pending: await q.message.edit_text("✅ No pending!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Panel", callback_data="admin_panel")]]))
        else:
            text = "💰 *Pending:*\n\n"; kb = []
            for req in pending:
                text += f"#{req['serial_no']} | {req.get('full_name','N/A')} | {req['points']} pts\n"
                kb.append([InlineKeyboardButton(f"✅ #{req['serial_no']}", callback_data=f"admin_approve_{req['_id']}"), InlineKeyboardButton("❌ Reject", callback_data=f"admin_reject_{req['_id']}")])
            kb.append([InlineKeyboardButton("🔙 Panel", callback_data="admin_panel")])
            await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    
    elif d == "admin_panel": await q.message.edit_text("🔐 *Admin Panel*", reply_markup=create_admin_keyboard(), parse_mode=ParseMode.MARKDOWN)
    elif d == "admin_broadcast_menu": await q.message.edit_text("📢 Reply + `/broadcast`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Panel", callback_data="admin_panel")]]), parse_mode=ParseMode.MARKDOWN)
    elif d == "admin_groups_menu": await q.message.edit_text(f"👥 Groups: {get_collection('groups').count_documents({})}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📊 Stats", callback_data="admin_group_stats")], [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast_groups")], [InlineKeyboardButton("🔙 Panel", callback_data="admin_panel")]]), parse_mode=ParseMode.MARKDOWN)
    elif d == "admin_group_stats":
        groups = list(get_collection("groups").find({}).limit(10))
        await q.message.edit_text("\n".join([f"📱 {g.get('title','?')} | 👥{g.get('member_count',0)} | 💰{g.get('reward_points',0)}" for g in groups]) if groups else "No groups!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_groups_menu")]]), parse_mode=ParseMode.MARKDOWN)
    elif d == "admin_broadcast_groups": await q.message.edit_text("📢 Reply + `/broadcastgroups`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_groups_menu")]]), parse_mode=ParseMode.MARKDOWN)
    else: await q.answer("Coming soon!", show_alert=True)

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
    
    # Check version on /start
    cv = get_verification_version(); u = get_user(uid)
    if u.get("verification_version", 0) != cv:
        get_collection("users").update_one({"user_id": uid}, {"$set": {"external_tasks_completed": False, "verification_version": 0}, "$unset": {"verification.external_required": "", "verification.external_attempts": ""}})
        u = get_user(uid)
    
    nj = await check_force_join(uid, context)
    if nj:
        kb = [[InlineKeyboardButton(f"📢 {c['channel_name']}", url=c['invite_link'])] for c in nj]
        kb.append([InlineKeyboardButton("✅ Check & Continue", callback_data="check_join")])
        await update.message.reply_text("👋 *Welcome!*\n\n⚠️ Join channels:", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
        await update.message.reply_text("Use buttons:", reply_markup=VERIFY_KEYBOARD)
        return
    
    if u.get("force_join_completed") and u.get("external_tasks_completed"):
        await update.message.reply_text("👋 *Welcome Back!*", reply_markup=MAIN_KEYBOARD, parse_mode=ParseMode.MARKDOWN)
    else:
        get_collection("users").update_one({"user_id": uid}, {"$set": {"force_join_completed": True}})
        links = list(get_collection("external_links").find({"active":True}))
        if links:
            kb = [[InlineKeyboardButton(f"🔗 {l['name']}", url=l['url'])] for l in links]
            kb.append([InlineKeyboardButton("✅ Completed All", callback_data="ext_tasks_complete")])
            await update.message.reply_text("✅ Channels done!\n\n📋 External tasks:", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
        else:
            get_collection("users").update_one({"user_id": uid}, {"$set": {"external_tasks_completed": True, "verification_version": get_verification_version()}, "$unset": {"verification.external_required": "", "verification.external_attempts": ""}})
            await process_pending_group_rewards(uid, context)
            if get_user(uid).get("pending_referrer"): await handle_referral_points(uid, get_user(uid)["pending_referrer"], context)
            await update.message.reply_text("🎉 *Done!*", reply_markup=MAIN_KEYBOARD, parse_mode=ParseMode.MARKDOWN)

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    await update.message.reply_text("🔐 *Admin Panel*", reply_markup=create_admin_keyboard(), parse_mode=ParseMode.MARKDOWN)

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS or not update.message.reply_to_message: return
    msg = update.message.reply_to_message; users = get_collection("users").find({}); total = get_collection("users").count_documents({})
    s = await update.message.reply_text(f"📢 0/{total}"); ok = fail = 0
    for i, u in enumerate(users, 1):
        try: await msg.copy(chat_id=u["user_id"]); ok += 1
        except: fail += 1
        if i % 20 == 0: await s.edit_text(f"📢 ✅{ok} ❌{fail} {i}/{total}")
        await asyncio.sleep(0.05)
    await s.edit_text(f"✅ Done! {ok}/{total}")

async def broadcast_groups_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS or not update.message.reply_to_message: return
    for g in get_collection("groups").find({"reward_given":True}):
        try: await update.message.reply_to_message.copy(chat_id=g["chat_id"])
        except: pass
        await asyncio.sleep(0.1)
    await update.message.reply_text("✅ Sent!")

async def add_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    try:
        p = update.message.text.replace("/addchannel ","").split("|")
        get_collection("channels").insert_one({"channel_id": int(p[0].strip()), "channel_name": p[1].strip(), "invite_link": p[2].strip(), "active":True, "added_date":datetime.now()})
        await update.message.reply_text("✅ Added!")
    except: await update.message.reply_text("❌ Format: /addchannel id | @name | link")

async def add_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    try:
        p = update.message.text.replace("/addlink ","").split("|")
        get_collection("external_links").insert_one({"name": p[0].strip(), "url": p[1].strip(), "active":True, "added_date":datetime.now()})
        increment_verification_version()
        await update.message.reply_text("✅ Added! Version updated.")
    except: await update.message.reply_text("❌ Format: /addlink name | url")

async def add_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    try:
        p = update.message.text.replace("/addtask ","").split("|")
        get_collection("tasks").insert_one({"name": p[0].strip(), "points": int(p[1].strip()), "type": p[2].strip(), "url": p[3].strip() if len(p)>3 else "", "active":True, "created_date":datetime.now()})
        await update.message.reply_text("✅ Added!")
    except: await update.message.reply_text("❌ Format: /addtask name | pts | type | url")

async def set_points_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    try:
        k, v = update.message.text.replace("/setpoints ","").split()
        pts = get_points_config()
        if k in pts: pts[k] = int(v); update_points_config(pts); await update.message.reply_text(f"✅ {k} = {v}")
        else: await update.message.reply_text("❌ Invalid key!")
    except: await update.message.reply_text("❌ Format: /setpoints key value")

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled.", reply_markup=create_admin_keyboard())

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
        try: await context.bot.send_message(added_by.id, "❌ <100 members: No reward!", parse_mode=ParseMode.MARKDOWN)
        except: pass
        return
    
    try:
        get_collection("groups").update_one({"chat_id": chat.id}, {"$setOnInsert": {"chat_id": chat.id, "reward_given": False, "added_at": datetime.now()}, "$set": {"title": chat.title or "?", "member_count": mc, "added_by": added_by.id, "reward_points": pts}}, upsert=True)
    except: pass
    
    if await ensure_user_verified(added_by.id, context):
        if credit_group_reward_atomic(chat.id, added_by.id, chat.title, mc, pts):
            try: await context.bot.send_message(added_by.id, f"✅ *Reward!*\n📱 {chat.title}\n💰 *{pts}* pts", parse_mode=ParseMode.MARKDOWN)
            except: pass
    else:
        create_group_pending_reward(chat.id, added_by.id, chat.title, mc, pts)
        try: await context.bot.send_message(added_by.id, f"⚠️ *Pending!*\n💰 *{pts}* pts\n\nVerify with /start", parse_mode=ParseMode.MARKDOWN)
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
    
    logger.info("Bot deployed with all fixes!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
