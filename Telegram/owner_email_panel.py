# Telegram/owner_email_panel.py - لوحة المالك لإدارة إيميلات المستخدمين (نسخة مطورة)

import os
import json
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
from config import OWNER_ID

logger = logging.getLogger(__name__)

# حالات المحادثة
(
    OWNER_EMAIL_MENU,
    OWNER_VIEW_ALL_EMAILS,
    OWNER_SELECT_USER_EMAILS,
    OWNER_ADD_TO_GROUP,
) = range(600, 604)

# مسار مجلد الإيميلات
EMAILS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'emails_data')

def load_all_user_emails():
    """تحميل جميع إيميلات المستخدمين من المجلد"""
    all_emails = {}
    
    if not os.path.exists(EMAILS_DIR):
        return all_emails
    
    for filename in os.listdir(EMAILS_DIR):
        if filename.startswith('emails_') and filename.endswith('.json'):
            try:
                user_id = filename.replace('emails_', '').replace('.json', '')
                filepath = os.path.join(EMAILS_DIR, filename)
                
                with open(filepath, 'r', encoding='utf-8') as f:
                    emails = json.load(f)
                    if emails:  # فقط إذا كان المستخدم لديه إيميلات
                        all_emails[user_id] = emails
            except Exception as e:
                logger.error(f"خطأ في تحميل إيميلات المستخدم {filename}: {e}")
                continue
    
    return all_emails

def get_user_emails(user_id):
    """الحصول على إيميلات مستخدم معين"""
    filepath = os.path.join(EMAILS_DIR, f'emails_{user_id}.json')
    
    if not os.path.exists(filepath):
        return []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"خطأ في قراءة إيميلات المستخدم {user_id}: {e}")
        return []

def save_user_emails(user_id, emails):
    """حفظ إيميلات مستخدم معين"""
    filepath = os.path.join(EMAILS_DIR, f'emails_{user_id}.json')
    
    try:
        os.makedirs(EMAILS_DIR, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(emails, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"خطأ في حفظ إيميلات المستخدم {user_id}: {e}")
        return False

async def owner_email_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """القائمة الرئيسية للوحة إدارة الإيميلات"""
    user_id = update.effective_user.id
    
    if user_id != OWNER_ID:
        return ConversationHandler.END
    
    query = update.callback_query
    if query:
        await query.answer()
    
    # تحميل جميع الإيميلات
    all_emails = load_all_user_emails()
    total_users = len(all_emails)
    total_emails = sum(len(emails) for emails in all_emails.values())
    
    text = (
        f"📧 <b>لوحة إدارة الإيميلات</b>\n\n"
        f"👥 عدد المستخدمين: <code>{total_users}</code>\n"
        f"📨 إجمالي الإيميلات: <code>{total_emails}</code>\n\n"
        f"اختر الإجراء المطلوب:"
    )
    
    keyboard = [
        [InlineKeyboardButton("📋 عرض جميع الإيميلات", callback_data="owner_view_all")],
        [InlineKeyboardButton("👤 عرض إيميلات مستخدم معين", callback_data="owner_view_user")],
        [InlineKeyboardButton("📥 تصدير الكل (TXT)", callback_data="owner_export_all")],
        [InlineKeyboardButton("🔙 رجوع للوحة المالك", callback_data="admin_panel")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if query:
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)
    
    return OWNER_EMAIL_MENU

async def owner_view_all_emails(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض جميع الإيميلات من كل المستخدمين مع تقسيم الرسائل"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        return ConversationHandler.END
    
    all_emails = load_all_user_emails()
    
    if not all_emails:
        await query.edit_message_text(
            "❌ لا توجد إيميلات مسجلة حالياً.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="owner_email_panel")]])
        )
        return OWNER_EMAIL_MENU
    
    await query.edit_message_text("⏳ جاري تحضير القائمة وإرسالها...")
    
    # بناء الرسالة
    msg = "📧 <b>جميع الإيميلات المسجلة:</b>\n\n"
    
    for user_id_str, emails in all_emails.items():
        user_header = f"👤 <b>المستخدم:</b> <code>{user_id_str}</code>\n"
        user_header += f"📨 <b>عدد الإيميلات:</b> {len(emails)}\n\n"
        
        # إذا كانت الرسالة الحالية + الهيدر ستتجاوز الحد، أرسلها وابدأ جديدة
        if len(msg) + len(user_header) > 3800:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode="HTML")
            msg = ""
            
        msg += user_header
        
        for idx, email_data in enumerate(emails, 1):
            email = email_data.get('email', 'N/A')
            password = email_data.get('password', 'N/A')
            line = f"  {idx}. 📧 <code>{email}</code>\n     🔑 <code>{password}</code>\n"
            
            if len(msg) + len(line) > 3800:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode="HTML")
                msg = "📧 <b>تكملة القائمة:</b>\n\n"
            
            msg += line
        
        msg += "\n" + "─" * 20 + "\n\n"
    
    if msg:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode="HTML")
    
    keyboard = [
        [InlineKeyboardButton("👤 عرض مستخدم معين", callback_data="owner_view_user")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="owner_email_panel")]
    ]
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="✅ تم عرض جميع الإيميلات أعلاه.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return OWNER_EMAIL_MENU

async def owner_export_all_emails(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصدير جميع الإيميلات في ملف نصي"""
    query = update.callback_query
    await query.answer("جاري التصدير...")
    
    all_emails = load_all_user_emails()
    if not all_emails:
        await query.answer("❌ لا توجد بيانات لتصديرها", show_alert=True)
        return OWNER_EMAIL_MENU
        
    file_path = "all_emails_export.txt"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("=== تقرير جميع الإيميلات ===\n\n")
        for uid, emails in all_emails.items():
            f.write(f"المستخدم: {uid} (العدد: {len(emails)})\n")
            f.write("-" * 30 + "\n")
            for idx, e in enumerate(emails, 1):
                f.write(f"{idx}. {e.get('email')} : {e.get('password')}\n")
            f.write("\n" + "="*40 + "\n\n")
            
    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=open(file_path, "rb"),
        filename="all_emails.txt",
        caption="✅ تم تصدير جميع الإيميلات بنجاح."
    )
    
    if os.path.exists(file_path):
        os.remove(file_path)
        
    return OWNER_EMAIL_MENU

async def owner_view_user_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة المستخدمين لاختيار واحد مع تقسيم الصفحات"""
    query = update.callback_query
    await query.answer()
    
    # الحصول على الصفحة الحالية من callback_data
    page = 0
    if query.data.startswith("owner_view_user_page_"):
        page = int(query.data.split("_")[-1])
    
    all_emails = load_all_user_emails()
    
    if not all_emails:
        await query.edit_message_text(
            "❌ لا توجد إيميلات مسجلة.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="owner_email_panel")]])
        )
        return OWNER_EMAIL_MENU
    
    user_ids = sorted(list(all_emails.keys()))
    per_page = 10
    total_pages = math.ceil(len(user_ids) / per_page)
    
    start_idx = page * per_page
    end_idx = start_idx + per_page
    current_users = user_ids[start_idx:end_idx]
    
    keyboard = []
    for uid in current_users:
        count = len(all_emails[uid])
        keyboard.append([InlineKeyboardButton(f"👤 {uid} ({count} إيميل)", callback_data=f"owner_select_{uid}")])
    
    # أزرار التنقل
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"owner_view_user_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("التالي ➡️", callback_data=f"owner_view_user_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
        
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="owner_email_panel")])
    
    text = f"👥 <b>اختر المستخدم (صفحة {page+1}/{total_pages}):</b>"
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    
    return OWNER_SELECT_USER_EMAILS

async def owner_show_user_emails(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إيميلات مستخدم معين مع خيار التصدير"""
    query = update.callback_query
    await query.answer()
    
    selected_user_id = query.data.split('owner_select_')[1]
    emails = get_user_emails(selected_user_id)
    
    if not emails:
        await query.edit_message_text(
            f"❌ المستخدم <code>{selected_user_id}</code> ليس لديه إيميلات.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="owner_view_user")]])
        )
        return OWNER_SELECT_USER_EMAILS
    
    # إذا كان العدد كبير جداً، نعرض ملخص ونوفر زر تصدير
    if len(emails) > 30:
        msg = (
            f"👤 <b>إيميلات المستخدم:</b> <code>{selected_user_id}</code>\n"
            f"📨 <b>العدد الإجمالي:</b> <code>{len(emails)}</code>\n\n"
            f"⚠️ العدد كبير جداً للعرض المباشر، يرجى استخدام زر التصدير أدناه لرؤية القائمة كاملة."
        )
        # عرض أول 5 فقط كعينة
        msg += "\n\n<b>عينة من الإيميلات:</b>\n"
        for idx, email_data in enumerate(emails[:5], 1):
            msg += f"{idx}. 📧 <code>{email_data.get('email')}</code>\n"
    else:
        msg = f"👤 <b>إيميلات المستخدم:</b> <code>{selected_user_id}</code>\n\n"
        for idx, email_data in enumerate(emails, 1):
            email = email_data.get('email', 'N/A')
            password = email_data.get('password', 'N/A')
            msg += f"{idx}. 📧 <code>{email}</code>\n   🔑 <code>{password}</code>\n\n"
    
    keyboard = [
        [InlineKeyboardButton("📥 تصدير إيميلات هذا المستخدم", callback_data=f"owner_exp_u_{selected_user_id}")],
        [InlineKeyboardButton("➕ إضافة الكل لمجموعتي", callback_data=f"owner_add_all_{selected_user_id}")],
        [InlineKeyboardButton("🗑️ حذف إيميل معين", callback_data=f"owner_delete_{selected_user_id}")],
        [InlineKeyboardButton("🔙 رجوع للمستخدمين", callback_data="owner_view_user")],
        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="owner_email_panel")]
    ]
    
    await query.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    return OWNER_SELECT_USER_EMAILS

async def owner_export_user_emails(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصدير إيميلات مستخدم معين في ملف"""
    query = update.callback_query
    await query.answer("جاري التصدير...")
    
    uid = query.data.split('owner_exp_u_')[1]
    emails = get_user_emails(uid)
    
    if not emails:
        await query.answer("❌ لا توجد بيانات", show_alert=True)
        return OWNER_SELECT_USER_EMAILS
        
    file_path = f"emails_{uid}.txt"
    with open(file_path, "w", encoding="utf-8") as f:
        for e in emails:
            f.write(f"{e.get('email')}:{e.get('password')}\n")
            
    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=open(file_path, "rb"),
        filename=f"emails_{uid}.txt",
        caption=f"✅ إيميلات المستخدم <code>{uid}</code>"
    )
    
    if os.path.exists(file_path):
        os.remove(file_path)
    return OWNER_SELECT_USER_EMAILS

async def owner_add_all_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة جميع إيميلات مستخدم إلى مجموعة المالك"""
    query = update.callback_query
    await query.answer()
    
    selected_user_id = query.data.split('owner_add_all_')[1]
    user_emails = get_user_emails(selected_user_id)
    
    if not user_emails:
        await query.answer("❌ لا توجد إيميلات للإضافة!", show_alert=True)
        return OWNER_SELECT_USER_EMAILS
    
    owner_emails = get_user_emails(OWNER_ID)
    existing_emails = {e.get('email') for e in owner_emails}
    added_count = 0
    
    for email_data in user_emails:
        if email_data.get('email') not in existing_emails:
            owner_emails.append(email_data)
            added_count += 1
    
    if added_count > 0:
        save_user_emails(OWNER_ID, owner_emails)
        await query.answer(f"✅ تمت إضافة {added_count} إيميل جديد لمجموعتك!", show_alert=True)
    else:
        await query.answer("ℹ️ جميع الإيميلات موجودة مسبقاً!", show_alert=True)
    
    return await owner_show_user_emails(update, context)

async def owner_delete_email_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة الإيميلات للحذف مع تقسيم صفحات"""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split('_')
    selected_user_id = parts[2]
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
    
    emails = get_user_emails(selected_user_id)
    if not emails:
        await query.answer("❌ لا توجد إيميلات!", show_alert=True)
        return OWNER_SELECT_USER_EMAILS
    
    per_page = 10
    total_pages = math.ceil(len(emails) / per_page)
    start_idx = page * per_page
    current_emails = emails[start_idx:start_idx + per_page]
    
    keyboard = []
    for i, email_data in enumerate(current_emails):
        idx = start_idx + i
        email = email_data.get('email', 'N/A')
        keyboard.append([InlineKeyboardButton(f"🗑️ {email}", callback_data=f"owner_del_confirm_{selected_user_id}_{idx}")])
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"owner_delete_{selected_user_id}_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("التالي ➡️", callback_data=f"owner_delete_{selected_user_id}_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
        
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"owner_select_{selected_user_id}")])
    
    await query.edit_message_text(
        f"🗑 <b>اختر الإيميل للحذف (صفحة {page+1}/{total_pages}):</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return OWNER_SELECT_USER_EMAILS

async def owner_confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تأكيد حذف إيميل معين"""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split('_')
    # owner_del_confirm_{user_id}_{idx}
    user_id = parts[3]
    idx = int(parts[4])
    
    emails = get_user_emails(user_id)
    if 0 <= idx < len(emails):
        deleted_email = emails.pop(idx)
        save_user_emails(user_id, emails)
        await query.answer(f"✅ تم حذف {deleted_email.get('email')}", show_alert=True)
    
    # العودة لقائمة الحذف
    query.data = f"owner_delete_{user_id}_0"
    return await owner_delete_email_selection(update, context)

# تعريف الـ Handler
owner_email_conv_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(owner_email_panel, pattern="^owner_email_panel$"),
        CallbackQueryHandler(owner_view_all_emails, pattern="^owner_view_all$"),
        CallbackQueryHandler(owner_export_all_emails, pattern="^owner_export_all$"),
        CallbackQueryHandler(owner_view_user_selection, pattern="^owner_view_user"),
        CallbackQueryHandler(owner_show_user_emails, pattern="^owner_select_"),
        CallbackQueryHandler(owner_export_user_emails, pattern="^owner_exp_u_"),
        CallbackQueryHandler(owner_add_all_to_group, pattern="^owner_add_all_"),
        CallbackQueryHandler(owner_delete_email_selection, pattern="^owner_delete_"),
        CallbackQueryHandler(owner_confirm_delete, pattern="^owner_del_confirm_"),
    ],
    states={
        OWNER_EMAIL_MENU: [
            CallbackQueryHandler(owner_view_all_emails, pattern="^owner_view_all$"),
            CallbackQueryHandler(owner_export_all_emails, pattern="^owner_export_all$"),
            CallbackQueryHandler(owner_view_user_selection, pattern="^owner_view_user"),
        ],
        OWNER_SELECT_USER_EMAILS: [
            CallbackQueryHandler(owner_show_user_emails, pattern="^owner_select_"),
            CallbackQueryHandler(owner_export_user_emails, pattern="^owner_exp_u_"),
            CallbackQueryHandler(owner_add_all_to_group, pattern="^owner_add_all_"),
            CallbackQueryHandler(owner_delete_email_selection, pattern="^owner_delete_"),
            CallbackQueryHandler(owner_confirm_delete, pattern="^owner_del_confirm_"),
            CallbackQueryHandler(owner_view_user_selection, pattern="^owner_view_user"),
        ],
    },
    fallbacks=[CallbackQueryHandler(owner_email_panel, pattern="^owner_email_panel$")],
    map_to_parent={
        ConversationHandler.END: ConversationHandler.END # أو الحالة التي تريد العودة إليها
    }
)
