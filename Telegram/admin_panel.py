import asyncio
import time
import math
import shutil
import zipfile
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    CommandHandler
)
from config import OWNER_ID, DB_PATH

import sys
import os
# إضافة المسار الجذري للمشروع
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from database_manager import db

# المتغيرات الخاصة بالحوار
(
    ADMIN_ENTER_ID,
    ADMIN_SELECT_DURATION,
    ADMIN_CONFIRM_ADD,
    ADMIN_DELETE_USER,
    ADMIN_WAIT_RESTORE_FILE
) = range(500, 505)

DEV_USERNAME = "@vxxsmk"

# مسار مجلد الإيميلات
EMAILS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'emails_data')

# ================= الدوال المساعدة =================

async def admin_panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        return

    users = db.get_all_users()
    active_users = sum(1 for u in users if u[5] == 'active' and u[3] > time.time())
    
    keyboard = [
        [InlineKeyboardButton("➕ إضافة مستخدم", callback_data="admin_add_user"),
         InlineKeyboardButton("➖ حذف مستخدم", callback_data="admin_del_user")],
        [InlineKeyboardButton("📋 عرض المشتركين", callback_data="admin_list_users_0")],
        [InlineKeyboardButton("📧 لوحة الإيميلات", callback_data="owner_email_panel"),
         InlineKeyboardButton("📱 لوحة حسابات تلجرام", callback_data="owner_telegram_panel")],
        [InlineKeyboardButton("💾 نسخ احتياطي", callback_data="admin_backup_menu"),
         InlineKeyboardButton("🔄 استعادة بيانات", callback_data="admin_restore_menu")],
        [InlineKeyboardButton("🔙 إغلاق اللوحة", callback_data="admin_close_panel")]
    ]
    
    text = (
        f"👮‍♂️ <b>لوحة تحكم المطور</b>\n\n"
        f"• عدد المشتركين الكلي: {len(users)}\n"
        f"• الاشتراكات النشطة: {active_users}\n"
        f"• حالتك: مطور النظام 👨‍💻"
    )
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

# --- وظائف النسخ الاحتياطي والاستعادة ---

async def admin_backup_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📨 نسخ احتياطي للإيميلات", callback_data="backup_emails")],
        [InlineKeyboardButton("📱 نسخ احتياطي للحسابات", callback_data="backup_accounts")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
    ]
    
    await query.edit_message_text(
        "💾 <b>قسم النسخ الاحتياطي</b>\n\n"
        "اختر نوع البيانات التي تريد أخذ نسخة احتياطية لها:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def perform_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    action = query.data
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if action == "backup_emails":
        if not os.path.exists(EMAILS_DIR) or not os.listdir(EMAILS_DIR):
            await query.answer("❌ لا توجد إيميلات لنسخها!", show_alert=True)
            return
            
        zip_path = f"emails_backup_{timestamp}.zip"
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(EMAILS_DIR):
                for file in files:
                    zipf.write(os.path.join(root, file), file)
        
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=open(zip_path, 'rb'),
            filename=zip_path,
            caption=f"✅ نسخة احتياطية لكافة الإيميلات\n📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        os.remove(zip_path)
        
    elif action == "backup_accounts":
        if not os.path.exists(DB_PATH):
            await query.answer("❌ قاعدة البيانات غير موجودة!", show_alert=True)
            return
            
        db_backup = f"accounts_backup_{timestamp}.db"
        shutil.copy2(DB_PATH, db_backup)
        
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=open(db_backup, 'rb'),
            filename=db_backup,
            caption=f"✅ نسخة احتياطية لقاعدة البيانات (الحسابات والمشتركين)\n📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        os.remove(db_backup)

async def admin_restore_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📨 استعادة الإيميلات", callback_data="restore_emails")],
        [InlineKeyboardButton("📱 استعادة الحسابات", callback_data="restore_accounts")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
    ]
    
    await query.edit_message_text(
        "🔄 <b>قسم استعادة البيانات</b>\n\n"
        "⚠️ <b>تنبيه:</b> الاستعادة ستقوم باستبدال البيانات الحالية بالبيانات الموجودة في الملف.\n\n"
        "اختر النوع الذي تريد استعادته:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def request_restore_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    restore_type = query.data.split('_')[1]
    context.user_data['restore_type'] = restore_type
    
    text = ""
    if restore_type == "emails":
        text = "📤 يرجى إرسال ملف النسخة الاحتياطية للإيميلات (ملف .zip):"
    else:
        text = "📤 يرجى إرسال ملف قاعدة البيانات (ملف .db):"
        
    await query.edit_message_text(
        f"🔄 <b>استعادة {restore_type}</b>\n\n{text}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="admin_panel")]])
    )
    return ADMIN_WAIT_RESTORE_FILE

async def handle_restore_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = update.message.document
    restore_type = context.user_data.get('restore_type')
    
    if not file:
        await update.message.reply_text("❌ يرجى إرسال ملف صحيح.")
        return ADMIN_WAIT_RESTORE_FILE
        
    # التحقق من الامتداد
    if restore_type == "emails" and not file.file_name.endswith('.zip'):
        await update.message.reply_text("❌ يرجى إرسال ملف ZIP للنسخة الاحتياطية للإيميلات.")
        return ADMIN_WAIT_RESTORE_FILE
    elif restore_type == "accounts" and not file.file_name.endswith('.db'):
        await update.message.reply_text("❌ يرجى إرسال ملف DB لقاعدة البيانات.")
        return ADMIN_WAIT_RESTORE_FILE
        
    new_file = await context.bot.get_file(file.file_id)
    temp_path = f"temp_restore_{file.file_name}"
    await new_file.download_to_drive(temp_path)
    
    try:
        if restore_type == "emails":
            # مسح المجلد الحالي أو استبدال الملفات
            os.makedirs(EMAILS_DIR, exist_ok=True)
            with zipfile.ZipFile(temp_path, 'r') as zip_ref:
                zip_ref.extractall(EMAILS_DIR)
            await update.message.reply_text("✅ تم استعادة الإيميلات بنجاح!")
            
        elif restore_type == "accounts":
            # استبدال قاعدة البيانات
            # يفضل إغلاق أي اتصالات مفتوحة إذا أمكن، لكن SQLite مع WAL تتعامل مع هذا غالباً
            shutil.copy2(temp_path, DB_PATH)
            await update.message.reply_text("✅ تم استعادة قاعدة البيانات بنجاح! قد تحتاج لإعادة تشغيل البوت لتفعيل كافة التغييرات.")
            
    except Exception as e:
        await update.message.reply_text(f"❌ حدث خطأ أثناء الاستعادة: {str(e)}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
    await admin_panel_command(update, context)
    return ConversationHandler.END

# --- باقي الدوال الأصلية ---

async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer("تم الإلغاء")
        await admin_panel_command(update, context)
    else:
        await update.message.reply_text("تم الإلغاء.")
        await admin_panel_command(update, context)
    return ConversationHandler.END

async def admin_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("تم إغلاق اللوحة")
    await query.message.delete()
    return ConversationHandler.END

async def admin_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await admin_panel_command(update, context)

async def request_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [[InlineKeyboardButton("إلغاء ❌", callback_data="admin_cancel")]]
    await query.edit_message_text(
        "🆔 <b>إضافة مستخدم جديد</b>\n\n"
        "أرسل الآيدي (ID) الخاص بالمستخدم:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADMIN_ENTER_ID

async def receive_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.text.strip()
    if not user_id.isdigit():
        await update.message.reply_text("❌ يرجى إرسال أرقام فقط.")
        return ADMIN_ENTER_ID
        
    context.user_data['target_user_id'] = int(user_id)
    
    keyboard = [
        [InlineKeyboardButton("يوم واحد 🕐", callback_data="dur_1"),
         InlineKeyboardButton("أسبوع (7 أيام) 📅", callback_data="dur_7")],
        [InlineKeyboardButton("شهر (30 يوم) 🗓", callback_data="dur_30"),
         InlineKeyboardButton("سنة كاملة 📆", callback_data="dur_365")],
        [InlineKeyboardButton("اشتراك دائم ♾️", callback_data="dur_life")],
        [InlineKeyboardButton("إلغاء ❌", callback_data="admin_cancel")]
    ]
    
    await update.message.reply_text(
        f"⏱ <b>تحديد مدة الاشتراك</b>\n\n"
        f"المستخدم: <code>{user_id}</code>\n"
        f"اختر المدة من الأسفل:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADMIN_SELECT_DURATION

async def process_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    target_id = context.user_data.get('target_user_id')
    
    if data == "admin_cancel":
        await admin_panel_command(update, context)
        return ConversationHandler.END

    days = 0
    is_lifetime = False
    dur_text = ""
    
    if data == "dur_1": days = 1; dur_text = "يوم واحد"
    elif data == "dur_7": days = 7; dur_text = "أسبوع"
    elif data == "dur_30": days = 30; dur_text = "شهر"
    elif data == "dur_365": days = 365; dur_text = "سنة"
    elif data == "dur_life": is_lifetime = True; dur_text = "مدى الحياة"
    
    expiry = db.add_user(target_id, "Unknown", days, is_lifetime)
    
    await query.edit_message_text(
        f"✅ <b>تم تفعيل الاشتراك بنجاح</b>\n\n"
        f"👤 المستخدم: <code>{target_id}</code>\n"
        f"⏱ المدة: {dur_text}\n"
        f"📅 الانتهاء: {datetime.fromtimestamp(expiry).strftime('%Y-%m-%d') if not is_lifetime else '♾️'}",
        parse_mode="HTML"
    )
    
    try:
        if is_lifetime:
            msg = f"✅ <b>تم تفعيل اشتراكك الدائم!</b>\n\nاستمتع بكافة مميزات البوت بلا حدود ♾️"
        else:
            msg = (f"✅ <b>تم تفعيل اشتراكك!</b>\n\n"
                   f"⏱ المدة: {dur_text}\n"
                   f"📅 ينتهي في: {datetime.fromtimestamp(expiry).strftime('%Y-%m-%d')}")
        await context.bot.send_message(target_id, msg, parse_mode="HTML")
    except: pass
        
    context.job_queue.run_once(lambda ctx: admin_panel_command(update, context), 3)
    return ConversationHandler.END

async def admin_list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    page = 0
    if query.data.startswith("admin_list_users_"):
        page = int(query.data.split("_")[-1])
    
    users = db.get_all_users()
    if not users:
        await query.edit_message_text("لا يوجد مستخدمين مسجلين.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("رجوع", callback_data="admin_back")]]))
        return

    per_page = 8
    total_pages = math.ceil(len(users) / per_page)
    current_users = users[page*per_page : (page+1)*per_page]

    msg = f"📋 <b>قائمة المشتركين (صفحة {page+1}/{total_pages}):</b>\n\n"
    keyboard = []
    for u in current_users:
        is_active = u[5] == 'active'
        is_expired = u[3] < time.time() and not u[4]
        status_icon = "⚪️" if not is_active else ("🔴" if is_expired else "🟢")
        expiry = "♾️" if u[4] else datetime.fromtimestamp(u[3]).strftime('%Y-%m-%d')
        msg += f"{status_icon} <code>{u[0]}</code> | {expiry}\n"
        toggle_text = "✅ تفعيل" if not is_active else "🚫 تعطيل"
        toggle_data = f"admin_toggle_{u[0]}_{'active' if not is_active else 'inactive'}_{page}"
        keyboard.append([InlineKeyboardButton(f"👤 {u[0]}", callback_data="noop"), InlineKeyboardButton(toggle_text, callback_data=toggle_data)])
    
    nav = []
    if page > 0: nav.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"admin_list_users_{page-1}"))
    if page < total_pages - 1: nav.append(InlineKeyboardButton("التالي ➡️", callback_data=f"admin_list_users_{page+1}"))
    if nav: keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")])
    await query.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_toggle_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split('_')
    target_id = int(data[2])
    new_status = data[3]
    page = data[4] if len(data) > 4 else "0"
    db.update_user_status(target_id, new_status)
    await query.answer(f"✅ تم {'تفعيل' if new_status == 'active' else 'تعطيل'} حساب المستخدم {target_id}", show_alert=True)
    query.data = f"admin_list_users_{page}"
    return await admin_list_users(update, context)

async def admin_ask_delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("إلغاء ❌", callback_data="admin_cancel")]]
    await query.edit_message_text("🗑 <b>حذف مستخدم</b>\n\nأرسل الآيدي (ID) الخاص بالمستخدم المراد حذفه:", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_DELETE_USER

async def admin_perform_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id_text = update.message.text.strip()
    if not user_id_text.isdigit():
        await update.message.reply_text("❌ يرجى إرسال أرقام فقط.")
        return ADMIN_DELETE_USER
    target_id = int(user_id_text)
    user = db.get_user(target_id)
    if not user:
        await update.message.reply_text("❌ هذا المستخدم غير موجود.")
        context.job_queue.run_once(lambda ctx: admin_panel_command(update, context), 2)
        return ConversationHandler.END
    db.remove_user(target_id)
    await update.message.reply_text(f"✅ <b>تم حذف المستخدم بنجاح</b>\n🆔 الآيدي: <code>{target_id}</code>", parse_mode="HTML")
    try: await context.bot.send_message(target_id, "🚫 <b>تم حذف حسابك من البوت بواسطة الإدارة.</b>", parse_mode="HTML")
    except: pass
    context.job_queue.run_once(lambda ctx: admin_panel_command(update, context), 3)
    return ConversationHandler.END

async def new_user_approval_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    sub_status = db.check_subscription(user.id)
    if sub_status == "active": return True
    keyboard = [[InlineKeyboardButton("✅ موافقة كاملة", callback_data=f"appr_perm_{user.id}")], [InlineKeyboardButton("⏱ تحديد مدة", callback_data=f"appr_ok_{user.id}")], [InlineKeyboardButton("❌ رفض", callback_data=f"appr_no_{user.id}")]]
    try:
        await context.bot.send_message(chat_id=OWNER_ID, text=(f"📢 <b>طلب اشتراك جديد</b>\n\n👤 المستخدم: {user.mention_html()}\n🆔 الآيدي: <code>{user.id}</code>\n🏷 اليوزر: @{user.username if user.username else 'لا يوجد'}\n\nهل توافق؟"), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        await update.message.reply_text("⏳ تم إرسال طلب تفعيل حسابك للمطور. يرجى الانتظار...")
    except: await update.message.reply_text("❌ حدث خطأ في إرسال طلبك.")
    return False

async def handle_approval_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split('_')
    action = data[1]
    target_id = int(data[2])
    if action == "perm":
        db.add_user(target_id, "User", is_lifetime=True)
        await query.edit_message_text(f"✅ تم تفعيل اشتراك دائم للمستخدم <code>{target_id}</code>", parse_mode="HTML")
        try: await context.bot.send_message(target_id, "✅ <b>تمت الموافقة على طلبك!</b>", parse_mode="HTML")
        except: pass
    elif action == "ok":
        context.user_data['target_user_id'] = target_id
        keyboard = [[InlineKeyboardButton("يوم", callback_data="dur_1"), InlineKeyboardButton("أسبوع", callback_data="dur_7")], [InlineKeyboardButton("شهر", callback_data="dur_30"), InlineKeyboardButton("سنة", callback_data="dur_365")], [InlineKeyboardButton("إلغاء", callback_data="admin_cancel")]]
        await query.edit_message_text(f"⏱ اختر مدة الاشتراك للمستخدم <code>{target_id}</code>:", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        return ADMIN_SELECT_DURATION
    elif action == "no":
        await query.edit_message_text(f"❌ تم رفض طلب المستخدم <code>{target_id}</code>", parse_mode="HTML")
        try: await context.bot.send_message(target_id, "❌ <b>عذراً، تم رفض طلبك.</b>", parse_mode="HTML")
        except: pass
    return ConversationHandler.END

async def my_subscription_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    if not user: 
        if query:
            await query.edit_message_text("❌ لم يتم العثور على بيانات اشتراكك.")
        return
        
    expiry = datetime.fromtimestamp(user[3]).strftime('%Y-%m-%d') if user[3] < 9999999999 else "لانهائي ♾️"
    status = "🟢 نشط" if user[5] == 'active' and (user[4] or user[3] > time.time()) else "🔴 منتهي/معطل"
    text = (
        f"💳 <b>تفاصيل اشتراكك:</b>\n\n"
        f"🆔 الآيدي: <code>{user_id}</code>\n"
        f"📊 الحالة: {status}\n"
        f"📅 ينتهي في: {expiry}"
    )
    keyboard = [[InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="back_to_main_menu")]]
    
    if query:
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def user_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    # جلب البيانات مباشرة من قاعدة البيانات لضمان الدقة
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT total_email_reports, total_telegram_reports, external_emails_count FROM users WHERE user_id = ?', (user_id,))
    stats = cursor.fetchone()
    conn.close()
    
    if not stats:
        email_reports, telegram_reports, external_emails = 0, 0, 0
    else:
        email_reports, telegram_reports, external_emails = stats
        
    text = (
        f"📊 <b>إحصائيات استخدامك:</b>\n\n"
        f"🏴‍☠ بلاغات تيليجرام: <code>{telegram_reports or 0}</code>\n"
        f"📧 بلاغات إيميل: <code>{email_reports or 0}</code>\n"
        f"📨 إيميلات خارجية مضافة: <code>{external_emails or 0}</code>"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="back_to_main_menu")]]
    
    if query:
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

# الـ Handler الرئيسي للوحة الإدارة
admin_conv_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(admin_panel_command, pattern="^admin_panel$"),
        CallbackQueryHandler(request_user_id, pattern="^admin_add_user$"),
        CallbackQueryHandler(admin_ask_delete_command, pattern="^admin_del_user$"),
        CallbackQueryHandler(admin_list_users, pattern="^admin_list_users_"),
        CallbackQueryHandler(handle_approval_action, pattern="^appr_"),
        CallbackQueryHandler(admin_backup_menu, pattern="^admin_backup_menu$"),
        CallbackQueryHandler(admin_restore_menu, pattern="^admin_restore_menu$"),
        CallbackQueryHandler(perform_backup, pattern="^backup_"),
        CallbackQueryHandler(request_restore_file, pattern="^restore_")
    ],
    states={
        ADMIN_ENTER_ID: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_user_id),
            CallbackQueryHandler(admin_cancel, pattern="^admin_cancel$")
        ],
        ADMIN_SELECT_DURATION: [
            CallbackQueryHandler(process_duration, pattern="^dur_"),
            CallbackQueryHandler(admin_cancel, pattern="^admin_cancel$")
        ],
        ADMIN_DELETE_USER: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, admin_perform_delete),
            CallbackQueryHandler(admin_cancel, pattern="^admin_cancel$")
        ],
        ADMIN_WAIT_RESTORE_FILE: [
            MessageHandler(filters.Document.ALL, handle_restore_file),
            CallbackQueryHandler(admin_cancel, pattern="^admin_cancel$")
        ]
    },
    fallbacks=[CallbackQueryHandler(admin_panel_command, pattern="^admin_panel$")],
    map_to_parent={
        ConversationHandler.END: ConversationHandler.END
    }
)
