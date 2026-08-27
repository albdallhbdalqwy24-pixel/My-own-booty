# DrKhayal/khayal.py - نسخة منظمة

import sys
import os
import sqlite3
import asyncio
import logging
import time
from urllib.parse import urlparse, parse_qs

# ===================================================================
#  إضافة المجلد الرئيسي للمشروع إلى مسار بايثون
# ===================================================================
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ===================================================================
#  استيراد مكتبات Telegram
# ===================================================================
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.error import BadRequest
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telethon import TelegramClient
from telethon.sessions import StringSession

# ===================================================================
#  استيراد الإعدادات والوحدات
# ===================================================================

# --- استيراد الإعدادات الأساسية ---
try:
    from config import BOT_TOKEN, OWNER_ID, DB_PATH, API_ID, API_HASH
except ImportError:
    logging.error("خطأ: لم يتم العثور على ملف config.py أو أنه ناقص. يجب أن يحتوي على: BOT_TOKEN, OWNER_ID, DB_PATH, API_ID, API_HASH")
    exit(1)

# --- استيراد معالجات قاعدة البيانات والإدارة ---
from database_manager import db
from Telegram.admin_panel import (
    admin_panel_command,
    admin_conv_handler,
    admin_list_users,
    admin_back,
    admin_toggle_user,
    admin_cancel,
    admin_close,
    handle_approval_action,
    new_user_approval_request,
    my_subscription_command,
    user_stats_command,
    ADMIN_ENTER_ID,
    ADMIN_SELECT_DURATION
)

# --- استيراد لوحة إدارة الإيميلات للمالك ---
try:
    from Telegram.owner_email_panel import owner_email_conv_handler
    OWNER_EMAIL_AVAILABLE = True
except ImportError:
    OWNER_EMAIL_AVAILABLE = False
    owner_email_conv_handler = None

# --- استيراد لوحة إدارة حسابات تلجرام للمالك ---
try:
    from Telegram.owner_telegram_panel import owner_telegram_conv_handler
    OWNER_TELEGRAM_AVAILABLE = True
except ImportError:
    OWNER_TELEGRAM_AVAILABLE = False
    owner_telegram_conv_handler = None

# --- استيراد معالجات البريد الإلكتروني ---
try:
    from Email.email_reports import email_conv_handler
    EMAIL_AVAILABLE = True
except ImportError:
    EMAIL_AVAILABLE = False
    email_conv_handler = None

# --- استيراد معالجات الدعم (معطل مؤقتاً) ---
try:
    from Telegram.support_module import register_support_handlers
    SUPPORT_AVAILABLE = True
except ImportError:
    SUPPORT_AVAILABLE = False
    register_support_handlers = None

# --- استيراد معالجات تقارير تيليجرام ---
from Telegram.report_peer import peer_report_conv
from Telegram.report_message import message_report_conv
from Telegram.report_photo import photo_report_conv
from Telegram.report_sponsored import sponsored_report_conv
from Telegram.report_mass import mass_report_conv
from Telegram.research import research_conv
from Telegram.report_bot_messages import bot_messages_report_conv

# --- استيراد معالجات إضافة الحسابات (من add.py) ---
try:
    import sys
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from add import (
        add_account_method,
        add_account_session,
        add_account_category,
        add_account_phone,
        handle_existing_account,
        add_account_code,
        add_account_password,
        cancel_operation as add_cancel_operation,
        main_menu as add_main_menu_handler,
        # استيراد الثوابت
        MAIN_MENU,
        ADD_ACCOUNT_METHOD,
        ADD_ACCOUNT_SESSION,
        ADD_ACCOUNT_CATEGORY,
        ADD_ACCOUNT_PHONE,
        ADD_ACCOUNT_PHONE_HANDLE_EXISTING,
        ADD_ACCOUNT_CODE,
        ADD_ACCOUNT_PASSWORD,
        # استيراد باقي الهاندلرات
        view_category_select,
        view_accounts,
        delete_category_select,
        delete_account_select,
        delete_account_confirm,
        check_category_select,
        start_accounts_check,
        back_to_check_categories,
        show_account_details,
        back_to_check_start,
        delete_account_after_check,
        recheck_account,
        back_to_check_results,
        storage_category_select,
        storage_account_select,
        # استيراد باقي الثوابت
        VIEW_CATEGORY_SELECT,
        VIEW_ACCOUNTS,
        DELETE_CATEGORY_SELECT,
        DELETE_ACCOUNT_SELECT,
        DELETE_ACCOUNT_CONFIRM,
        CHECK_CATEGORY_SELECT,
        CHECK_ACCOUNT_SELECT,
        CHECK_ACCOUNTS_IN_PROGRESS,
        CHECK_ACCOUNT_DETAILS,
        STORAGE_CATEGORY_SELECT,
        STORAGE_ACCOUNT_SELECT
    )
except ImportError as e:
    logger.error(f"Failed to import from add.py: {e}")
    # تعريف مؤقت لتجنب الأخطاء إذا فشل الاستيراد
    MAIN_MENU = 100
    ADD_ACCOUNT_METHOD = 101
    ADD_ACCOUNT_SESSION = 102
    ADD_ACCOUNT_CATEGORY = 103
    ADD_ACCOUNT_PHONE = 104
    ADD_ACCOUNT_PHONE_HANDLE_EXISTING = 105
    ADD_ACCOUNT_CODE = 106
    ADD_ACCOUNT_PASSWORD = 107

# --- استيراد الدوال المشتركة ---
from Telegram.common import get_categories, get_accounts, cancel_operation
from Telegram.common_improved import (
    socks5_proxy_checker, 
    parse_socks5_proxy, 
    run_enhanced_report_process,
    Socks5ProxyChecker,
    VerifiedReporter
)
from config_enhanced import enhanced_config

# ===================================================================
#  إعداد التسجيل
# ===================================================================
logging.getLogger('telethon').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# ===================================================================
#  تعريف حالات المحادثة
# ===================================================================
(
    TELEGRAM_MENU,
    SELECT_PROXY_OPTION,
    ENTER_PROXY_LINKS,
    SELECT_CATEGORY,
    SELECT_METHOD,
    MANAGE_SESSIONS_MENU,
    VIEW_SESSIONS_LIST
) = range(7)

# تعريف حالات إدارة الحسابات (من add.py)
(
    ADD_ACCOUNT_MENU, ADD_ACCOUNT_METHOD, ADD_ACCOUNT_SESSION, 
    ADD_ACCOUNT_CATEGORY, ADD_ACCOUNT_PHONE, 
    ADD_ACCOUNT_PHONE_HANDLE_EXISTING, ADD_ACCOUNT_CODE, 
    ADD_ACCOUNT_PASSWORD
) = range(100, 108)

# ===================================================================
#  دوال القائمة الرئيسية والبدء
# ===================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """يعرض القائمة الرئيسية عند إرسال /start أو العودة إليها."""
    user = update.effective_user
    
    # 1. التحقق من قاعدة البيانات
    is_allowed = False
    
    if user.id == OWNER_ID:
        is_allowed = True
        # نضمن وجود المالك في قاعدة البيانات
        if not db.get_user(OWNER_ID):
            db.add_user(OWNER_ID, "Developer", is_lifetime=True)
    else:
        status = db.check_subscription(user.id)
        if status == "active":
            is_allowed = True
        elif status == "not_found":
            # تدفق طلب الاشتراك
            allowed = await new_user_approval_request(update, context)
            if not allowed:
                return
        elif status == "expired":
            await update.message.reply_text("❌ انتهى اشتراكك. يرجى التواصل مع المطور @vxxsmk للتجديد.")
            return
        elif status == "pendng" or status == "inactive":
             await update.message.reply_text("⏳ حسابك قيد المراجعة أو معطل.")
             return

    if not is_allowed:
        return

    # 2. عرض القائمة الرئيسية الفخمة
    keyboard = [
        [InlineKeyboardButton("🚀 قسم بلاغات تيليجرام", callback_data="main_telegram"),
         InlineKeyboardButton("📧 قسم بلاغات ايميل", callback_data="email_reports")],
        [InlineKeyboardButton("💳 اشتراكي", callback_data="my_subscription"),
         InlineKeyboardButton("📊 إحصائياتي", callback_data="my_stats")],
        [InlineKeyboardButton("👮‍♂️ لوحة المالك", callback_data="admin_panel")] if user.id == OWNER_ID else [],
        [InlineKeyboardButton("💬 الدعم والمساعدة", url="https://t.me/vxxsmk")]
    ]
    # تنظيف الصفوف الفارغة
    keyboard = [row for row in keyboard if row]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        f"👋 <b>مرحباً بك عزيزي {user.first_name}</b>\n\n"
        f"🤖 <b>نظام الإبلاغ المطور (الإصدار الخاص)</b>\n"
        f"ــــــــــــــــــــــــــــــــــــــــــــــــ\n\n"
        f"⚡️ اختر القسم المناسب للبدء:"
    )
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)

async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """دالة العودة إلى القائمة الرئيسية من أي مكان."""
    query = update.callback_query
    if query: 
        try:
            await query.answer()
        except Exception:
            pass
    
    # تنظيف البيانات المؤقتة فقط
    keys_to_remove = ['targets', 'reason_obj', 'method_type', 'reports_per_account', 'cycle_delay']
    for k in keys_to_remove:
        context.user_data.pop(k, None)
        
    await start(update, context)
    return ConversationHandler.END

# ===================================================================
#  دوال قائمة تيليجرام
# ===================================================================

async def show_telegram_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يعرض قائمة خيارات قسم تيليجرام."""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🏴‍☠ بدء عملية الإبلاغ", callback_data="start_proxy_setup")],
        [InlineKeyboardButton(" التحكم في الجلسات", callback_data="manage_sessions")],
        [InlineKeyboardButton("➕ إضافة جلسة جديدة", callback_data="add_new_session")],
        [InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="back_to_main_menu")]
    ]
    
    await query.edit_message_text(
        "📢 <b>قسم بلاغات تيليجرام الداخلي</b>\n\n"
        "🔥 <b>المميزات:</b>\n"
        "• ✅ دعم Socks5 Proxy\n"
        "• 🚀 إرسال سريع وموثوق\n"
        "• 🛡 حماية عالية للحسابات\n"
        "• 📊 تقارير فورية\n\n"
        "اختر الإجراء الذي تريد تنفيذه:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return TELEGRAM_MENU

async def start_add_session_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء عملية إضافة جلسة جديدة من داخل khayal.py"""
    query = update.callback_query
    await query.answer()
    
    # محاكاة سلوك main_menu -> إضافة حسابات
    keyboard = [
        [InlineKeyboardButton("➕ إضافة برقم الهاتف", callback_data="add_phone")],
        [InlineKeyboardButton("🔑 إضافة بكود الجلسة", callback_data="add_session")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="main_telegram")]
    ]
    
    await query.edit_message_text(
        "➕ <b>إضافة جلسة جديدة</b>\n\n"
        "اختر طريقة الإضافة:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADD_ACCOUNT_METHOD

# ===================================================================
#  دوال إدارة الجلسات
# ===================================================================

async def manage_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """عرض قائمة التحكم في الجلسات (الفئات)"""
    query = update.callback_query
    await query.answer()

    categories = get_categories(update.effective_user.id)
    if not categories:
        text = "❌ لا توجد جلسات/فئات متاحة حالياً."
        kb = [[InlineKeyboardButton("🔙 رجوع", callback_data="main_telegram")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
        return TELEGRAM_MENU

    # بناء أزرار ديناميكية للفئات
    keyboard = []
    total_accounts = 0
    
    # صف لكل فئة
    for cat_id, name, count in categories:
        total_accounts += count
        keyboard.append([
            InlineKeyboardButton(f"📂 {name} ({count})", callback_data=f"view_cat_{cat_id}")
        ])

    keyboard.append([InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="main_telegram")])
    
    await query.edit_message_text(
        f"📂 <b>قسم التحكم في الجلسات</b>\n\n"
        f"• عدد الفئات: {len(categories)}\n"
        f"• إجمالي الحسابات: {total_accounts}\n\n"
        f"👇 اختر فئة لعرض تفاصيلها:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return MANAGE_SESSIONS_MENU

async def view_category_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """عرض الحسابات داخل فئة معينة"""
    query = update.callback_query
    await query.answer()
    
    try:
        cat_id = query.data.split('view_cat_')[1]
        accounts = get_accounts(cat_id, update.effective_user.id)
        
        # البحث عن اسم الفئة للعرض
        categories = get_categories(update.effective_user.id)
        cat_name = next((name for cid, name, _ in categories if str(cid) == str(cat_id)), "غير معروف")
        
        if not accounts:
            # إذا كانت الفئة فارغة، نعرض خيار حذفها أيضاً
            keyboard = [
                [InlineKeyboardButton("🗑️ حذف هذه الفئة الفارغة", callback_data=f"delete_cat_full_{cat_id}")],
                [InlineKeyboardButton("🔙 قائمة الفئات", callback_data="manage_sessions")]
            ]
            await query.edit_message_text(
                f"❌ الفئة <b>{cat_name}</b> فارغة.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return MANAGE_SESSIONS_MENU

        # عرض ملخص الحسابات (أول 20 حساب لتجنب ضخامة الرسالة)
        acc_list_text = ""
        for idx, acc in enumerate(accounts[:20]):
            phone = acc.get('phone', 'N/A')
            proxy_st = "✅ بروكسي" if acc.get('proxy_server') else "❌ مباشر"
            acc_list_text += f"{idx+1}. <code>{phone}</code> | {proxy_st}\n"

        if len(accounts) > 20:
            acc_list_text += f"\n<i>... وهناك {len(accounts) - 20} حساب آخر.</i>"

        keyboard = [
            [InlineKeyboardButton("🗑️ حذف هذه الفئة بالكامل", callback_data=f"delete_cat_full_{cat_id}")],
            [InlineKeyboardButton("🔙 قائمة الفئات", callback_data="manage_sessions")]
        ]
        
        # إضافة زر مسح الحسابات المضافة للمالك فقط
        if update.effective_user.id == OWNER_ID:
            keyboard.insert(1, [InlineKeyboardButton("🧹 مسح الحسابات المضافة", callback_data=f"clear_added_accs_{cat_id}")])

        await query.edit_message_text(
            f"👤 <b>حسابات الفئة: {cat_name}</b>\n\n"
            f"{acc_list_text}\n\n"
            f"عدد الحسابات: {len(accounts)}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return VIEW_SESSIONS_LIST
        
    except Exception as e:
        logger.error(f"Error viewing sessions: {e}")
        await query.edit_message_text("❌ حدث خطأ.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="manage_sessions")]]))
        return MANAGE_SESSIONS_MENU

async def delete_category_full(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """حذف الفئة وجميع الحسابات المرتبطة بها"""
    query = update.callback_query
    await query.answer()
    
    try:
        cat_id = query.data.split('delete_cat_full_')[1]
        
        with sqlite3.connect(DB_PATH, timeout=30) as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            cursor = conn.cursor()
            cursor.execute("DELETE FROM accounts WHERE category_id = ?", (cat_id,))
            accounts_deleted = cursor.rowcount
            cursor.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
            conn.commit()
            
        await query.edit_message_text(
            f"✅ تم حذف الفئة بنجاح.\n"
            f"🗑️ عدد الحسابات المحذوفة: {accounts_deleted}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 قائمة الفئات", callback_data="manage_sessions")]])
        )
        return MANAGE_SESSIONS_MENU
    except Exception as e:
        logger.error(f"Error deleting category: {e}")
        await query.edit_message_text(f"❌ خطأ: {e}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="manage_sessions")]]))
        return MANAGE_SESSIONS_MENU

async def clear_added_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """مسح الحسابات المضافة في فئة معينة للمالك"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != OWNER_ID:
        return MANAGE_SESSIONS_MENU
        
    try:
        cat_id = query.data.split('clear_added_accs_')[1]
        
        with sqlite3.connect(DB_PATH, timeout=30) as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            cursor = conn.cursor()
            # مسح الحسابات فقط دون حذف الفئة
            cursor.execute("DELETE FROM accounts WHERE category_id = ?", (cat_id,))
            deleted_count = cursor.rowcount
            conn.commit()
            
        await query.edit_message_text(
            f"🧹 تم مسح <code>{deleted_count}</code> حساب من هذه الفئة بنجاح.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للفئة", callback_data=f"view_cat_{cat_id}")]])
        )
        return VIEW_SESSIONS_LIST
    except Exception as e:
        logger.error(f"Error clearing accounts: {e}")
        await query.edit_message_text(f"❌ خطأ: {e}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="manage_sessions")]]))
        return MANAGE_SESSIONS_MENU


# ===================================================================
#  دوال إعداد البروكسي
# ===================================================================

async def start_proxy_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """الخطوة 1: اختيار نوع البروكسي قبل تحميل الحسابات."""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📡 استخدام بروكسي Socks5", callback_data="use_proxy")],
        [InlineKeyboardButton("⏭️ تخطي (اتصال مباشر)", callback_data="skip_proxy")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_tg_menu")]
    ]
    
    await query.edit_message_text(
        "🌐 <b>الخطوة 1/3: إعداد البروكسي</b>\n\n"
        "🔄 <b>التحديث الجديد:</b>\n"
        "• ❌ إزالة نظام MTProto\n"
        "• ✅ تفعيل Socks5 فقط\n"
        "• 🚀 أداء أفضل وأكثر استقراراً\n\n"
        "اختر نوع الاتصال:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_PROXY_OPTION

async def process_proxy_option(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """معالجة اختيار نوع البروكسي."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "use_proxy":
        await query.edit_message_text(
            "📡 <b>إدخال بروكسيات (Socks5 / MTProto)</b>\n\n"
            "يمكنك إرسال البروكسيات بإحدى الطرق التالية:\n"
            "1. 📝 <b>نص كتابي:</b> أرسل القائمة مباشرة هنا.\n"
            "2. 📁 <b>ملف نصي:</b> أرسل ملف .txt يحتوي على البروكسيات.\n\n"
            "📌 <b>التنسيقات المدعومة:</b>\n"
            "• Socks5: `IP:PORT`\n"
            "• MTProto: `IP:PORT:SECRET`\n"
            "• روابط MTProto: `https://t.me/proxy?...`\n\n"
            "⚠️ سيتم فحص جميع البروكسيات فحصاً شاملاً قبل الاستخدام.",
            parse_mode="HTML"
        )
        return ENTER_PROXY_LINKS
    else:
        context.user_data['proxies'] = []
        # عرض فئات الحسابات مباشرة بدون بروكسي
        return await choose_session_source(update, context)

async def process_proxy_links(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """معالجة بروكسيات Socks5 (نص أو ملف) مع الفحص الفوري - نسخة محسنة async"""
    from proxy_checker_async import check_proxies_batch, get_proxy_statistics, format_proxy_results
    
    input_text = ""
    
    # معالجة الملفات المرفقة
    if update.message.document:
        doc = update.message.document
        if doc.mime_type.startswith('text') or doc.file_name.endswith('.txt'):
            file = await doc.get_file()
            byte_array = await file.download_as_bytearray()
            input_text = byte_array.decode('utf-8')
        else:
            await update.message.reply_text("❌ يرجى إرسال ملف نصي (.txt) صالح.")
            return ENTER_PROXY_LINKS
    # معالجة النص المباشر
    elif update.message.text:
        input_text = update.message.text
    else:
        await update.message.reply_text("❌ يرجى إرسال نص أو ملف يحتوي على البروكسيات.")
        return ENTER_PROXY_LINKS

    input_proxies = input_text.strip().splitlines()
    if not input_proxies:
        await update.message.reply_text("❌ لم يتم العثور على أي بيانات في الرسالة.")
        return ENTER_PROXY_LINKS

    # تنظيف القائمة وإزالة الأسطر الفارغة
    input_proxies = [line.strip() for line in input_proxies if line.strip()]

    msg = await update.message.reply_text(f"🔍 تم استلام {len(input_proxies)} سطر. جاري التحليل...")

    # تحليل البروكسيات
    parsed_proxies = []
    for proxy_line in input_proxies:
        proxy_info = parse_socks5_proxy(proxy_line)
        if proxy_info:
            parsed_proxies.append(proxy_info)
            
    if not parsed_proxies:
        await msg.edit_text("❌ لم يتم العثور على أي بروكسي صالح بالتنسيق IP:PORT")
        return await choose_session_source(update, context)
        
    # فحص البروكسيات بشكل متوازي (async)
    try:
        await msg.edit_text(
            f"🚀 <b>بدء الفحص المتوازي</b>\n\n"
            f"📊 العدد: {len(parsed_proxies)} بروكسي\n"
            f"⚡ السرعة: حتى 20 فحص متزامن\n"
            f"⏱️ المهلة: 3 ثواني لكل بروكسي\n\n"
            f"⏳ جاري الفحص...",
            parse_mode="HTML"
        )
        
        # متغيرات لتتبع التقدم
        last_update_time = [time.time()]
        
        # دالة callback لتحديث التقدم
        async def progress_callback(current: int, total: int, result: dict):
            # تحديث الرسالة كل 2 ثانية فقط لتجنب rate limiting
            if time.time() - last_update_time[0] >= 2:
                percentage = (current / total) * 100
                await msg.edit_text(
                    f"🚀 <b>جاري الفحص...</b>\n\n"
                    f"📊 التقدم: {current}/{total} ({percentage:.0f}%)\n"
                    f"⚡ آخر فحص: {result.get('host')}:{result.get('port')}\n"
                    f"✅ الحالة: {result.get('status')}",
                    parse_mode="HTML"
                )
                last_update_time[0] = time.time()
        
        # فحص البروكسيات بشكل متوازي
        checked_proxies = await check_proxies_batch(
            parsed_proxies,
            max_concurrent=20,  # 20 فحص متزامن
            timeout=3,  # 3 ثواني لكل فحص
            progress_callback=progress_callback
        )
        
        # حساب الإحصائيات
        stats = get_proxy_statistics(checked_proxies)
        
        # حفظ البروكسيات الناجحة
        valid_proxies = [p for p in checked_proxies if p.get('status') == 'active']
        
        if not valid_proxies:
            await msg.edit_text(
                f"❌ <b>فشل الفحص!</b>\n"
                f"تم فحص {len(parsed_proxies)} بروكسي ولم يعمل أي منها.\n"
                f"سيتم استخدام الاتصال المباشر.",
                parse_mode="HTML"
            )
            context.user_data['proxies'] = []
        else:
            # عرض النتائج
            result_text = format_proxy_results(stats)
            await msg.edit_text(result_text, parse_mode="HTML")
            context.user_data['proxies'] = valid_proxies
            
        # الانتقال للخطوة التالية
        return await choose_session_source(update, context)
        
    except Exception as e:
        logger.error(f"Proxy check error: {e}")
        await msg.edit_text(f"❌ حدث خطأ غير متوقع أثناء الفحص: {str(e)}")
        return await choose_session_source(update, context)

# ===================================================================
#  دوال اختيار الحسابات
# ===================================================================

async def choose_session_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """الخطوة 2: اختيار فئة الحسابات بعد إعداد البروكسي."""
    try:
        if update.callback_query:
            query = update.callback_query
            await query.answer()
        
        categories = get_categories(update.effective_user.id)
        if not categories:
            text = "❌ لا توجد فئات متاحة. تأكد من وجود حسابات في قاعدة البيانات."
            keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back_to_proxy_setup")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
            else:
                await update.message.reply_text(text, reply_markup=reply_markup)
            return SELECT_CATEGORY
        
        keyboard = []
        # خيار جديد لاستخدام كافة الحسابات المتاحة
        from database_manager import DatabaseManager
        db_mgr = DatabaseManager()
        all_accs = db_mgr.get_all_accounts()
        if all_accs:
            keyboard.append([InlineKeyboardButton(f"🔥 استخدام كافة حسابات النظام ({len(all_accs)})", callback_data="cat_all")])
            
        for cat_id, name, count in categories:
            keyboard.append([InlineKeyboardButton(f"{name} ({count} حساب)", callback_data=f"cat_{cat_id}")])
        
        keyboard.append([InlineKeyboardButton("رجوع 🔙", callback_data="back_to_proxy_setup")])
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                "📂 <b>الخطوة 2/3: اختيار فئة الحسابات</b>\n\n"
                "اختر الفئة التي تريد استخدامها للإبلاغ:",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                "📂 <b>الخطوة 2/3: اختيار فئة الحسابات</b>\n\n"
                "اختر الفئة التي تريد استخدامها للإبلاغ:",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        return SELECT_CATEGORY
        
    except Exception as e:
        logger.error(f"خطأ في choose_session_source: {e}")
        await update.message.reply_text("❌ حدث خطأ أثناء تحميل الفئات.")
        return ConversationHandler.END

async def process_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """معالجة اختيار فئة الحسابات والانتقال لقائمة طرق الإبلاغ."""
    query = update.callback_query
    await query.answer()
    
    category_id = query.data.split('_')[1]  # قد يكون UUID أو رقم
    context.user_data['selected_category'] = category_id
    
    if category_id == "all":
        from database_manager import DatabaseManager
        db_mgr = DatabaseManager()
        accounts = db_mgr.get_all_accounts()
        context.user_data['selected_category'] = "كافة حسابات النظام"
    else:
        accounts = get_accounts(category_id, update.effective_user.id)
        
    if not accounts:
        await query.edit_message_text("❌ لا توجد حسابات متاحة.")
        return ConversationHandler.END
    
    context.user_data['accounts'] = accounts
    
    # عرض قائمة طرق الإبلاغ والانتقال لحالة اختيار الطريقة
    await select_method_menu(update, context, is_query=True)
    return SELECT_METHOD

# ===================================================================
#  دوال اختيار طريقة الإبلاغ
# ===================================================================

async def select_method_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, is_query=False) -> int:
    """الخطوة 3: عرض قائمة طرق الإبلاغ المتاحة."""
    query = update.callback_query
    if query:
        await query.answer()
        
    proxies = context.user_data.get('proxies', [])
    proxy_status = f"✅ {len(proxies)} بروكسي نشط" if proxies else "🔗 اتصال مباشر"
    
    selected_category = context.user_data.get('selected_category')
    accounts = context.user_data.get('accounts', [])
    
    text = (
        f"🎯 <b>الخطوة 3/3: اختيار طريقة الإبلاغ</b>\n\n"
        f"📊 <b>ملخص الإعداد:</b>\n"
        f"• البروكسي: {proxy_status}\n"
        f"• الحسابات: {len(accounts)} حساب\n"
        f"• الفئة: {selected_category}\n\n"
        f"🔥 اختر نوع الإبلاغ:"
    )
    
    keyboard = [
        [InlineKeyboardButton("👤 بلاغ عضو", callback_data="method_peer")],
        [InlineKeyboardButton("💬 بلاغ رسالة", callback_data="method_message")],
        [InlineKeyboardButton("🖼️ صورة شخصية", callback_data="method_photo")],
        [InlineKeyboardButton("📢 إعلان ممول", callback_data="method_sponsored")],
        [InlineKeyboardButton("🔥 بلاغ جماعي", callback_data="method_mass")],
        [InlineKeyboardButton("🔍 بلاغ بحث", callback_data="method_research")],
        [InlineKeyboardButton("🤖 رسائل بوت", callback_data="method_bot_messages")],
        [InlineKeyboardButton("رجوع 🔙", callback_data="back_to_proxy_option")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if query:
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)
        
    # ملاحظة: ننهي المحادثة هنا لأن كل طريقة إبلاغ لها ConversationHandler خاص بها
    return ConversationHandler.END

# ===================================================================
#  دوال الرجوع والإلغاء
# ===================================================================

async def cancel_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يلغي عملية الإعداد ويعود للقائمة الرئيسية."""
    query = update.callback_query
    if query:
        try:
            await query.answer("🛑 تم الإلغاء")
        except Exception:
            pass
        await query.edit_message_text("🛑 تم إلغاء عملية الإعداد.")
    
    # تنظيف البيانات المؤقتة
    keys_to_remove = ['proxies', 'selected_category', 'accounts', 'method_type']
    for key in keys_to_remove:
        context.user_data.pop(key, None)
        
    await start(update, context)
    return ConversationHandler.END

async def back_to_proxy_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """الرجوع إلى إعداد البروكسي."""
    return await start_proxy_setup(update, context)

async def back_to_tg_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """الرجوع إلى قائمة تيليجرام."""
    return await show_telegram_menu(update, context)

async def back_to_proxy_option(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """الرجوع إلى خيارات البروكسي."""
    return await start_proxy_setup(update, context)

# ===================================================================
#  إعداد البوت والمعالجات
# ===================================================================

async def stop_reporting_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إيقاف عملية الإبلاغ الجارية"""
    query = update.callback_query
    await query.answer("🛑 جاري إيقاف العملية...", show_alert=True)
    
    # تعيين علامة الإيقاف
    context.user_data['stop_requested'] = True
    context.user_data['active'] = False
    
    logger.info(f"User {update.effective_user.id} requested to stop reporting.")

def main():
    """الدالة الرئيسية لتشغيل البوت."""
    logger.info("🤖 بدء تشغيل بوت الإبلاغ المطور...")
    logger.info("🌐 نظام Socks5 الجديد محمل")
    
    # إنشاء تطبيق البوت
    logger.info("🤖 إنشاء تطبيق البوت...")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    logger.info("✅ تم إنشاء التطبيق بنجاح")

    # --- المعالجات الأساسية ---
    logger.info("📱 إضافة معالجات أساسية...")
    app.add_handler(CommandHandler("start", start))
    logger.info("✅ تم إضافة المعالجات الأساسية")

    # --- معالج قسم تيليجرام (الإعداد الأولي) ---
    logger.info("🛠️ إعداد معالج التليجرام...")
    logger.info("🔧 بدء إنشاء ConversationHandler...")
    telegram_setup_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(show_telegram_menu, pattern='^main_telegram$')],
        allow_reentry=True,  # السماح بإعادة الدخول للمحادثة في أي وقت
        states={
            TELEGRAM_MENU: [
                CallbackQueryHandler(start_proxy_setup, pattern='^start_proxy_setup$'),
                CallbackQueryHandler(manage_sessions, pattern='^manage_sessions$'),
                CallbackQueryHandler(start_add_session_flow, pattern='^add_new_session$'),
                CallbackQueryHandler(back_to_main_menu, pattern='^back_to_main_menu$'),
            ],
            MANAGE_SESSIONS_MENU: [
                CallbackQueryHandler(view_category_sessions, pattern='^view_cat_'),
                CallbackQueryHandler(start_add_session_flow, pattern='^add_new_session$'),
                CallbackQueryHandler(show_telegram_menu, pattern='^main_telegram$'),
                CallbackQueryHandler(back_to_tg_menu, pattern='^back_to_tg_menu$'),
            ],
            VIEW_SESSIONS_LIST: [
                CallbackQueryHandler(manage_sessions, pattern='^manage_sessions$'),
                CallbackQueryHandler(delete_category_full, pattern='^delete_cat_full_'),
                CallbackQueryHandler(clear_added_accounts, pattern='^clear_added_accs_'),
                CallbackQueryHandler(view_category_sessions, pattern='^view_cat_'),
            ],
            # --- حالات إضافة الحسابات (من add.py) ---
            MAIN_MENU: [
                 MessageHandler(filters.TEXT & ~filters.COMMAND, add_main_menu_handler),
            ],
            ADD_ACCOUNT_METHOD: [
                CallbackQueryHandler(add_account_method, pattern='^(add_phone|add_session)$'),
                CallbackQueryHandler(show_telegram_menu, pattern='^main_telegram$'),
                CallbackQueryHandler(back_to_tg_menu, pattern='^back_to_tg_menu$'),
            ],
            ADD_ACCOUNT_CATEGORY: [
                 MessageHandler(filters.TEXT & ~filters.COMMAND, add_account_category),
                 CallbackQueryHandler(add_cancel_operation, pattern='^cancel$'),
            ],
            ADD_ACCOUNT_PHONE: [
                 MessageHandler(filters.TEXT & ~filters.COMMAND, add_account_phone),
                 CallbackQueryHandler(add_cancel_operation, pattern='^cancel$'),
            ],
            ADD_ACCOUNT_PHONE_HANDLE_EXISTING: [
                 CallbackQueryHandler(handle_existing_account),
                 CallbackQueryHandler(add_cancel_operation, pattern='^cancel$'),
            ],
            ADD_ACCOUNT_CODE: [
                 MessageHandler(filters.TEXT & ~filters.COMMAND, add_account_code),
                 CallbackQueryHandler(add_cancel_operation, pattern='^cancel$'),
            ],
            ADD_ACCOUNT_PASSWORD: [
                 MessageHandler(filters.TEXT & ~filters.COMMAND, add_account_password),
                 CallbackQueryHandler(add_cancel_operation, pattern='^cancel$'),
            ],
            ADD_ACCOUNT_SESSION: [
                 MessageHandler(filters.TEXT & ~filters.COMMAND, add_account_session),
                 CallbackQueryHandler(add_cancel_operation, pattern='^cancel$'),
            ],
             # --- حالات العرض والحذف والفحص (من add.py) ---
            VIEW_CATEGORY_SELECT: [
                CallbackQueryHandler(view_category_select)
            ],
            VIEW_ACCOUNTS: [
                CallbackQueryHandler(view_accounts)
            ],
            DELETE_CATEGORY_SELECT: [
                CallbackQueryHandler(delete_category_select)
            ],
            DELETE_ACCOUNT_SELECT: [
                CallbackQueryHandler(delete_account_select)
            ],
            DELETE_ACCOUNT_CONFIRM: [
                CallbackQueryHandler(delete_account_confirm)
            ],
            CHECK_CATEGORY_SELECT: [
                CallbackQueryHandler(check_category_select)
            ],
            CHECK_ACCOUNT_SELECT: [
                CallbackQueryHandler(start_accounts_check),
                CallbackQueryHandler(back_to_check_categories, pattern="back_to_check_categories")
            ],
            CHECK_ACCOUNTS_IN_PROGRESS: [
                CallbackQueryHandler(show_account_details, pattern="account_detail_"),
                CallbackQueryHandler(back_to_check_start, pattern="back_to_check_start")
            ],
            CHECK_ACCOUNT_DETAILS: [
                CallbackQueryHandler(delete_account_after_check, pattern="delete_"),
                CallbackQueryHandler(recheck_account, pattern="recheck_"),
                CallbackQueryHandler(back_to_check_results, pattern="back_to_check_results")
            ],
            STORAGE_CATEGORY_SELECT: [
                CallbackQueryHandler(storage_category_select)
            ],
            STORAGE_ACCOUNT_SELECT: [
                CallbackQueryHandler(storage_account_select)
            ],
            SELECT_PROXY_OPTION: [
                CallbackQueryHandler(process_proxy_option, pattern='^(use_proxy|skip_proxy)$'),
                CallbackQueryHandler(back_to_tg_menu, pattern='^back_to_tg_menu$'),
            ],
            ENTER_PROXY_LINKS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND | filters.Document.ALL, process_proxy_links),
                CallbackQueryHandler(back_to_proxy_option, pattern='^back_to_proxy_option$')
            ],
            SELECT_CATEGORY: [
                CallbackQueryHandler(process_category_selection, pattern='^cat_'),
                CallbackQueryHandler(back_to_proxy_setup, pattern='^back_to_proxy_setup$')
            ],
            SELECT_METHOD: [
                # هذه الحالة تنتهي المحادثة وتنتقل للمعالجات الخارجية
                # أزرار method_* يتم معالجتها بواسطة ConversationHandlers الأخرى
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_setup, pattern='^cancel_setup$'),
            CallbackQueryHandler(back_to_main_menu, pattern='^back_to_main_menu$'),
        ],
        per_user=True,
        per_chat=False,
        per_message=False,
    )

    # --- معالجات الأدمن والمستخدم ---
    logger.info("🔧 إضافة معالجات الأدمن والمستخدم...")
    app.add_handler(admin_conv_handler)
    
    # --- معالج لوحة الإيميلات للمالك ---
    if OWNER_EMAIL_AVAILABLE and owner_email_conv_handler:
        app.add_handler(owner_email_conv_handler)
        logger.info("✅ تم إضافة لوحة إدارة الإيميلات")
    else:
        logger.info("ℹ️ لوحة إدارة الإيميلات غير متاحة")
    
    # --- معالج لوحة حسابات تلجرام للمالك ---
    if OWNER_TELEGRAM_AVAILABLE and owner_telegram_conv_handler:
        app.add_handler(owner_telegram_conv_handler)
        logger.info("✅ تم إضافة لوحة إدارة حسابات تلجرام")
    else:
        logger.info("ℹ️ لوحة إدارة حسابات تلجرام غير متاحة")
    app.add_handler(CommandHandler("admin", admin_panel_command))
    app.add_handler(CallbackQueryHandler(admin_panel_command, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(admin_list_users, pattern="^admin_list_users$"))
    app.add_handler(CallbackQueryHandler(admin_toggle_user, pattern="^admin_toggle_"))
    app.add_handler(CallbackQueryHandler(admin_close, pattern="^admin_close_panel$"))
    app.add_handler(CallbackQueryHandler(admin_back, pattern="^admin_back$"))
    app.add_handler(CallbackQueryHandler(admin_cancel, pattern="^admin_cancel$"))
    
    # معالجات الموافقة والرفض للمستخدمين الجدد
    from Telegram.admin_panel import process_duration
    app.add_handler(CallbackQueryHandler(handle_approval_action, pattern="^appr_"))
    
    # معالجة أزرار المدة خارج ConversationHandler (لأننا نشغلها يدوياً من الموافقة)
    # ملاحظة: process_duration في الأصل صممت لتعمل كجزء من ConversationHandler وتسترجع Context
    # سنحتاج لتعديلها قليلاً لتعمل بشكل منفصل أو نعيد توجيهها
    # الحل الأبسط: إضافة CallbackQueryHandler مستقل يستدعيها
    app.add_handler(CallbackQueryHandler(process_duration, pattern="^dur_"))
    
    # معالجات واجهة المستخدم
    app.add_handler(CallbackQueryHandler(my_subscription_command, pattern="^my_subscription$"))
    app.add_handler(CallbackQueryHandler(user_stats_command, pattern="^my_stats$"))
    
    # --- إضافة جميع المعالجات إلى التطبيق ---
    logger.info("🔧 إضافة معالج إعداد التليجرام...")
    app.add_handler(telegram_setup_conv)
    logger.info("✅ تم إضافة معالج التليجرام")
    
    # --- معالجات البريد الإلكتروني ---
    logger.info("📧 فحص معالج البريد الإلكتروني...")
    if EMAIL_AVAILABLE and email_conv_handler:
        app.add_handler(email_conv_handler)
        logger.info("✅ تم إضافة معالج البريد الإلكتروني")
    else:
        logger.info("ℹ️ معالج البريد الإلكتروني غير متاح")
    
    # --- معالجات تقارير تيليجرام ---
    logger.info("📱 إضافة معالجات التقارير...")
    
    app.add_handler(peer_report_conv)
    logger.info("✅ معالج تقارير الأعضاء")
    
    app.add_handler(message_report_conv)
    logger.info("✅ معالج تقارير الرسائل")
    
    app.add_handler(photo_report_conv)
    logger.info("✅ معالج تقارير الصور")
    
    app.add_handler(sponsored_report_conv)
    logger.info("✅ معالج التقارير الممولة")
    
    app.add_handler(mass_report_conv)
    logger.info("✅ معالج التقارير الجماعية")
    
    app.add_handler(research_conv)  
    logger.info("✅ معالج بلاغ البحث")
    
    app.add_handler(bot_messages_report_conv)
    logger.info("✅ معالج بلاغ رسائل البوت")
    
    # --- معالجات الدعم ---
    logger.info("🔧 إضافة معالجات الدعم...")
    if register_support_handlers: 
        register_support_handlers(app)
        logger.info("✅ تم إضافة معالجات الدعم")
    else:
        logger.info("ℹ️ معالجات الدعم غير متاحة")
    
    # --- إضافة المعالجات العامة في النهاية ---
    logger.info("🔧 إضافة المعالجات العامة...")
    app.add_handler(CallbackQueryHandler(stop_reporting_handler, pattern='^stop_reporting_process$'))
    app.add_handler(CallbackQueryHandler(stop_reporting_handler, pattern='^stop_bot_messages_report$'))
    app.add_handler(CallbackQueryHandler(back_to_main_menu, pattern='^back_to_main_menu$'))
    logger.info("✅ تم إضافة المعالجات العامة")
    
    logger.info("🎉 اكتمل تحميل جميع المعالجات!")
    logger.info("🚀 البوت جاهز ويبدأ التشغيل...")
    logger.info("🔗 رابط البوت: @AAAK6BOT")
    logger.info("✅ نظام Socks5 محمل وجاهز للاختبار")
    
    app.run_polling()

if __name__ == '__main__':
    main()