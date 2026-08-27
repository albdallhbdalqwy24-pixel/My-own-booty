# Telegram/owner_telegram_panel.py - لوحة إدارة حسابات تلجرام للمالك (نسخة مطورة)

import os
import sqlite3
import logging
import math
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from config import OWNER_ID, DB_PATH

logger = logging.getLogger(__name__)

# حالات المحادثة
(
    OWNER_TELEGRAM_MENU,
    OWNER_VIEW_ALL_ACCOUNTS,
    OWNER_SELECT_USER_ACCOUNTS,
    OWNER_VIEW_CATEGORY_ACCOUNTS,
) = range(700, 704)

def get_all_telegram_accounts():
    """تحميل جميع حسابات تلجرام من قاعدة البيانات"""
    try:
        with sqlite3.connect(DB_PATH, timeout=20) as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT 
                    a.id, a.username, a.phone, a.created_at, 
                    a.last_used, a.is_active, a.owner_id,
                    c.name as category_name
                FROM accounts a
                LEFT JOIN categories c ON a.category_id = c.id
                ORDER BY a.owner_id, c.name, a.created_at DESC
            ''')
            
            accounts = cursor.fetchall()
            return accounts
    except Exception as e:
        logger.error(f"خطأ في تحميل حسابات تلجرام: {e}")
        return []

def get_accounts_by_user(user_id):
    """الحصول على حسابات تلجرام لمستخدم معين"""
    try:
        with sqlite3.connect(DB_PATH, timeout=20) as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT 
                    a.id, a.username, a.phone, a.created_at, 
                    a.last_used, a.is_active,
                    c.name as category_name
                FROM accounts a
                LEFT JOIN categories c ON a.category_id = c.id
                WHERE a.owner_id = ?
                ORDER BY c.name, a.created_at DESC
            ''', (user_id,))
            
            accounts = cursor.fetchall()
            return accounts
    except Exception as e:
        logger.error(f"خطأ في قراءة حسابات المستخدم {user_id}: {e}")
        return []

def get_all_users_with_accounts():
    """الحصول على قائمة المستخدمين الذين لديهم حسابات"""
    try:
        with sqlite3.connect(DB_PATH, timeout=20) as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT DISTINCT a.owner_id, COUNT(a.id) as account_count
                FROM accounts a
                WHERE a.is_active = 1
                GROUP BY a.owner_id
                ORDER BY account_count DESC
            ''')
            
            users = cursor.fetchall()
            return users
    except Exception as e:
        logger.error(f"خطأ في قراءة قائمة المستخدمين: {e}")
        return []

async def owner_telegram_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """القائمة الرئيسية للوحة إدارة حسابات تلجرام"""
    user_id = update.effective_user.id
    
    if user_id != OWNER_ID:
        return ConversationHandler.END
    
    query = update.callback_query
    if query:
        await query.answer()
    
    all_accounts = get_all_telegram_accounts()
    users_with_accounts = get_all_users_with_accounts()
    
    total_accounts = len(all_accounts)
    total_users = len(users_with_accounts)
    active_accounts = sum(1 for acc in all_accounts if acc[5] == 1)
    
    text = (
        f"📱 <b>لوحة إدارة حسابات تلجرام</b>\n\n"
        f"👥 عدد المستخدمين: <code>{total_users}</code>\n"
        f"📊 إجمالي الحسابات: <code>{total_accounts}</code>\n"
        f"✅ الحسابات النشطة: <code>{active_accounts}</code>\n"
        f"⚠️ الحسابات المعطلة: <code>{total_accounts - active_accounts}</code>\n\n"
        f"اختر الإجراء المطلوب:"
    )
    
    keyboard = [
        [InlineKeyboardButton("📋 عرض جميع الحسابات", callback_data="owner_tg_view_all")],
        [InlineKeyboardButton("👤 عرض حسابات مستخدم معين", callback_data="owner_tg_view_user")],
        [InlineKeyboardButton("📥 تصدير الكل (TXT)", callback_data="owner_tg_export_all")],
        [InlineKeyboardButton("🔄 نسخ كافة حسابات النظام", callback_data="owner_tg_copy_all")],
        [InlineKeyboardButton("🔙 رجوع للوحة المالك", callback_data="admin_panel")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if query:
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)
    
    return OWNER_TELEGRAM_MENU

async def owner_view_all_telegram_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض جميع حسابات تلجرام مع تقسيم الرسائل"""
    query = update.callback_query
    await query.answer()
    
    all_accounts = get_all_telegram_accounts()
    if not all_accounts:
        await query.edit_message_text("❌ لا توجد حسابات مسجلة.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="owner_telegram_panel")]]))
        return OWNER_TELEGRAM_MENU
    
    await query.edit_message_text("⏳ جاري تحضير القائمة وإرسالها...")
    
    msg = "📱 <b>جميع حسابات تلجرام المسجلة:</b>\n\n"
    current_owner = None
    
    for account in all_accounts:
        acc_id, username, phone, created_at, last_used, is_active, owner_id, category_name = account
        
        acc_info = ""
        if current_owner != owner_id:
            current_owner = owner_id
            acc_info += f"\n👤 <b>المستخدم:</b> <code>{owner_id}</code>\n" + "─" * 20 + "\n"
        
        status = "✅ نشط" if is_active else "⚠️ معطل"
        acc_info += f"📞 <code>{phone}</code> | {status} | 📂 {category_name or 'عام'}\n"
        
        if len(msg) + len(acc_info) > 3800:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode="HTML")
            msg = "📱 <b>تكملة القائمة:</b>\n\n"
            
        msg += acc_info
    
    if msg:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode="HTML")
    
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="owner_telegram_panel")]]
    await context.bot.send_message(chat_id=update.effective_chat.id, text="✅ تم عرض جميع الحسابات.", reply_markup=InlineKeyboardMarkup(keyboard))
    return OWNER_TELEGRAM_MENU

async def owner_export_all_tg_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصدير جميع الحسابات في ملف"""
    query = update.callback_query
    await query.answer("جاري التصدير...")
    
    all_accounts = get_all_telegram_accounts()
    if not all_accounts:
        await query.answer("❌ لا توجد بيانات", show_alert=True)
        return OWNER_TELEGRAM_MENU
        
    file_path = "all_tg_accounts.txt"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("=== تقرير حسابات تلجرام ===\n\n")
        for acc in all_accounts:
            f.write(f"المالك: {acc[6]} | الهاتف: {acc[2]} | اليوزر: @{acc[1]} | الحالة: {'نشط' if acc[5] else 'معطل'} | الفئة: {acc[7]}\n")
            
    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=open(file_path, "rb"),
        filename="all_tg_accounts.txt",
        caption="✅ تم تصدير جميع حسابات تلجرام."
    )
    if os.path.exists(file_path): os.remove(file_path)
    return OWNER_TELEGRAM_MENU

async def owner_view_user_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة المستخدمين مع تقسيم صفحات"""
    query = update.callback_query
    await query.answer()
    
    page = 0
    if query.data.startswith("owner_tg_view_user_page_"):
        page = int(query.data.split("_")[-1])
        
    users = get_all_users_with_accounts()
    if not users:
        await query.edit_message_text("❌ لا توجد حسابات.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="owner_telegram_panel")]]))
        return OWNER_TELEGRAM_MENU
        
    per_page = 10
    total_pages = math.ceil(len(users) / per_page)
    current_users = users[page*per_page : (page+1)*per_page]
    
    keyboard = []
    for uid, count in current_users:
        keyboard.append([InlineKeyboardButton(f"👤 {uid} ({count} حساب)", callback_data=f"owner_tg_select_{uid}")])
        
    nav = []
    if page > 0: nav.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"owner_tg_view_user_page_{page-1}"))
    if page < total_pages - 1: nav.append(InlineKeyboardButton("التالي ➡️", callback_data=f"owner_tg_view_user_page_{page+1}"))
    if nav: keyboard.append(nav)
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="owner_telegram_panel")])
    await query.edit_message_text(f"👥 <b>اختر المستخدم (صفحة {page+1}/{total_pages}):</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    return OWNER_SELECT_USER_ACCOUNTS

async def owner_copy_all_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نسخ كافة حسابات النظام للمالك دون حذفها من المستخدمين"""
    query = update.callback_query
    await query.answer()
    
    try:
        # 1. الحصول على فئة المالك الافتراضية أو إنشاؤها
        with sqlite3.connect(DB_PATH, timeout=20) as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            cursor = conn.cursor()
            
            # البحث عن فئة "حسابات المالك المنسوخة"
            cursor.execute("SELECT id FROM categories WHERE name = ? AND owner_id = ?", ("حسابات المالك المنسوخة", OWNER_ID))
            row = cursor.fetchone()
            if row:
                target_cat_id = row[0]
            else:
                import uuid
                target_cat_id = str(uuid.uuid4())
                cursor.execute("INSERT INTO categories (id, name, owner_id) VALUES (?, ?, ?)", 
                               (target_cat_id, "حسابات المالك المنسوخة", OWNER_ID))
            
            # 2. جلب كافة الحسابات التي لا يملكها المالك حالياً
            cursor.execute("SELECT * FROM accounts WHERE owner_id != ?", (OWNER_ID,))
            other_accounts = cursor.fetchall()
            
            # الحصول على أسماء الأعمدة (باستثناء id لأنه PRIMARY KEY)
            cursor.execute("PRAGMA table_info(accounts)")
            columns = [col[1] for col in cursor.fetchall()]
            
            copied_count = 0
            for acc in other_accounts:
                # تحويل الصف إلى قاموس
                acc_dict = dict(zip(columns, acc))
                
                # التحقق من وجود الحساب مسبقاً عند المالك (بناءً على رقم الهاتف)
                cursor.execute("SELECT id FROM accounts WHERE phone = ? AND owner_id = ?", (acc_dict['phone'], OWNER_ID))
                if cursor.fetchone():
                    continue
                
                # إعداد بيانات الحساب الجديد
                import uuid
                new_acc_id = str(uuid.uuid4())
                acc_dict['id'] = new_acc_id
                acc_dict['owner_id'] = OWNER_ID
                acc_dict['category_id'] = target_cat_id
                
                # بناء استعلام الإدخال
                cols = ', '.join(acc_dict.keys())
                placeholders = ', '.join(['?' for _ in acc_dict])
                cursor.execute(f"INSERT INTO accounts ({cols}) VALUES ({placeholders})", list(acc_dict.values()))
                copied_count += 1
            
            conn.commit()
            
        await query.edit_message_text(
            f"✅ <b>تمت عملية النسخ بنجاح!</b>\n\n"
            f"• تم نسخ <code>{copied_count}</code> حساب جديد.\n"
            f"• تمت إضافتها إلى فئة: <b>حسابات المالك المنسوخة</b>\n"
            f"• الحسابات لا تزال موجودة عند أصحابها الأصليين.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="owner_telegram_panel")]])
        )
    except Exception as e:
        logger.error(f"Error copying accounts: {e}")
        await query.edit_message_text(f"❌ خطأ أثناء النسخ: {str(e)}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="owner_telegram_panel")]]))
    
    return OWNER_TELEGRAM_MENU

async def owner_show_user_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض حسابات مستخدم معين"""
    query = update.callback_query
    await query.answer()
    
    uid = query.data.split('owner_tg_select_')[1]
    accounts = get_accounts_by_user(uid)
    
    if not accounts:
        await query.edit_message_text("❌ لا توجد حسابات لهذا المستخدم.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="owner_tg_view_user")]]))
        return OWNER_SELECT_USER_ACCOUNTS
        
    msg = f"👤 <b>حسابات المستخدم:</b> <code>{uid}</code>\n"
    msg += f"📊 <b>العدد:</b> {len(accounts)}\n\n"
    
    # عرض أول 10 فقط لتجنب التعليق
    for acc in accounts[:10]:
        status = "✅" if acc[5] else "⚠️"
        msg += f"{status} <code>{acc[2]}</code> | 📂 {acc[6] or 'عام'}\n"
        
    if len(accounts) > 10:
        msg += f"\n... و {len(accounts)-10} حسابات أخرى. استخدم زر التصدير للملف الكامل."
        
    keyboard = [
        [InlineKeyboardButton("📥 تصدير حسابات هذا المستخدم", callback_data=f"owner_tg_exp_u_{uid}")],
        [InlineKeyboardButton("🔙 رجوع للمستخدمين", callback_data="owner_tg_view_user")],
        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="owner_telegram_panel")]
    ]
    await query.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    return OWNER_SELECT_USER_ACCOUNTS

async def owner_export_user_tg_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصدير حسابات مستخدم معين"""
    query = update.callback_query
    await query.answer()
    
    uid = query.data.split('owner_tg_exp_u_')[1]
    accounts = get_accounts_by_user(uid)
    
    file_path = f"tg_accounts_{uid}.txt"
    with open(file_path, "w", encoding="utf-8") as f:
        for acc in accounts:
            f.write(f"الهاتف: {acc[2]} | اليوزر: @{acc[1]} | الحالة: {'نشط' if acc[5] else 'معطل'} | الفئة: {acc[6]}\n")
            
    await context.bot.send_document(chat_id=update.effective_chat.id, document=open(file_path, "rb"), filename=f"tg_accounts_{uid}.txt", caption=f"✅ حسابات المستخدم {uid}")
    if os.path.exists(file_path): os.remove(file_path)
    return OWNER_SELECT_USER_ACCOUNTS

# تعريف الـ Handler
owner_telegram_conv_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(owner_telegram_panel, pattern="^owner_telegram_panel$"),
        CallbackQueryHandler(owner_view_all_telegram_accounts, pattern="^owner_tg_view_all$"),
        CallbackQueryHandler(owner_export_all_tg_accounts, pattern="^owner_tg_export_all$"),
        CallbackQueryHandler(owner_view_user_selection, pattern="^owner_tg_view_user"),
        CallbackQueryHandler(owner_show_user_accounts, pattern="^owner_tg_select_"),
        CallbackQueryHandler(owner_export_user_tg_accounts, pattern="^owner_tg_exp_u_"),
        CallbackQueryHandler(owner_copy_all_accounts, pattern="^owner_tg_copy_all$"),
    ],
    states={
        OWNER_TELEGRAM_MENU: [
            CallbackQueryHandler(owner_view_all_telegram_accounts, pattern="^owner_tg_view_all$"),
            CallbackQueryHandler(owner_export_all_tg_accounts, pattern="^owner_tg_export_all$"),
            CallbackQueryHandler(owner_view_user_selection, pattern="^owner_tg_view_user"),
            CallbackQueryHandler(owner_copy_all_accounts, pattern="^owner_tg_copy_all$"),
        ],
        OWNER_SELECT_USER_ACCOUNTS: [
            CallbackQueryHandler(owner_show_user_accounts, pattern="^owner_tg_select_"),
            CallbackQueryHandler(owner_export_user_tg_accounts, pattern="^owner_tg_exp_u_"),
            CallbackQueryHandler(owner_view_user_selection, pattern="^owner_tg_view_user"),
        ],
    },
    fallbacks=[CallbackQueryHandler(owner_telegram_panel, pattern="^owner_telegram_panel$")],
    map_to_parent={
        ConversationHandler.END: ConversationHandler.END
    }
)
