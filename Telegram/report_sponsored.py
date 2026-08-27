import asyncio
import base64
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ContextTypes,
)

from .common import run_report_process, cancel_operation
from .common_improved import run_enhanced_report_process

# States
(
    ENTER_TARGET,
    ENTER_REPORT_COUNT,
    ENTER_DELAY,
    CONFIRM_START,
) = range(40, 44)

async def start_sponsored_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["method_type"] = "sponsored"
    context.user_data["reason_obj"] = None 
    context.user_data["message"] = ""

    keyboard = [[InlineKeyboardButton("رجوع 🔙", callback_data="cancel")]]
    await query.edit_message_text(
        "📢 <b>طريقة الإبلاغ عن الإعلانات الممولة</b>\n\n"
        "أرسل رابط الإعلان الممول الذي نسخته من تيليجرام.\n\n"
        "<b>كيفية الحصول على الرابط:</b>\n"
        "1. اضغط على الثلاث نقاط بجانب الإعلان\n"
        "2. اختر 'نسخ الرابط'\n\n"
        "📌 <i>مثال:</i>\n"
        "https://t.me/c/123456789?post=abcdefg123456",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ENTER_TARGET

async def process_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()
    # تحليل الرابط باستخدام تعبير منتظم
    pattern = r't\.me\/c\/(\d+)\?post=([\w-]+)'
    match = re.search(pattern, link)
    
    if not match:
        keyboard = [[InlineKeyboardButton("رجوع 🔙", callback_data="cancel")]]
        await update.message.reply_text(
            "❌ <b>رابط غير صالح</b>\n"
            "تأكد من نسخ الرابط الصحيح للإعلان.\n\n"
            "📌 <i>يجب أن يكون بالشكل:</i>\n"
            "https://t.me/c/123456789?post=abcdefg123456",
            parse_mode="HTML"
        )
        return ENTER_TARGET
        
    try:
        channel_id = int(match.group(1))
        random_id_b64 = match.group(2)
        
        # تخزين الهدف
        context.user_data["targets"] = [random_id_b64]
        context.user_data["channel_for_sponsored"] = channel_id
    except Exception as e:
        await update.message.reply_text(f"❌ حدث خطأ في معالجة الرابط: {str(e)}")
        return ENTER_TARGET

    keyboard = [
        [InlineKeyboardButton("1 مرة", callback_data="count_1")],
        [InlineKeyboardButton("2 مرات", callback_data="count_2")],
        [InlineKeyboardButton("3 مرات", callback_data="count_3")],
        [InlineKeyboardButton("مخصص", callback_data="count_custom")],
        [InlineKeyboardButton("رجوع 🔙", callback_data="cancel")]
    ]
    await update.message.reply_text(
        "🔄 <b>عدد مرات الإبلاغ</b>\n\n"
        "اختر عدد مرات الإبلاغ على الإعلان من كل حساب:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard))
    return ENTER_REPORT_COUNT

async def process_report_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "count_custom":
        keyboard = [[InlineKeyboardButton("رجوع 🔙", callback_data="cancel")]]
        await query.edit_message_text(
            "🔢 <b>عدد مخصص</b>\n\n"
            "أدخل عدد مرات الإبلاغ:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ENTER_REPORT_COUNT
    
    count = int(query.data.split("_")[1])
    context.user_data["reports_per_account"] = count
    
    keyboard = [
        [InlineKeyboardButton("5 ثواني", callback_data="delay_5")],
        [InlineKeyboardButton("10 ثواني", callback_data="delay_10")],
        [InlineKeyboardButton("30 ثواني", callback_data="delay_30")],
        [InlineKeyboardButton("مخصص", callback_data="delay_custom")],
        [InlineKeyboardButton("رجوع 🔙", callback_data="cancel")]
    ]
    await query.edit_message_text(
        "⏱️ <b>الفاصل الزمني</b>\n\n"
        "اختر الفاصل الزمني بين الإبلاغات:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard))
    return ENTER_DELAY

async def custom_report_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة العدد المخصص للإبلاغات"""
    try:
        count = int(update.message.text)
        if count <= 0:
            await update.message.reply_text("❌ يجب أن يكون العدد أكبر من الصفر.")
            return ENTER_REPORT_COUNT
            
        context.user_data["reports_per_account"] = count
        
        keyboard = [
            [InlineKeyboardButton("5 ثواني", callback_data="delay_5")],
            [InlineKeyboardButton("10 ثواني", callback_data="delay_10")],
            [InlineKeyboardButton("30 ثواني", callback_data="delay_30")],
            [InlineKeyboardButton("مخصص", callback_data="delay_custom")],
            [InlineKeyboardButton("رجوع 🔙", callback_data="cancel")]
        ]
        await update.message.reply_text(
            "⏱️ <b>الفاصل الزمني</b>\n\n"
            "اختر الفاصل الزمني بين الإبلاغات:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard))
        return ENTER_DELAY
    except ValueError:
        await update.message.reply_text("❌ أدخل رقمًا صحيحًا فقط.")
        return ENTER_REPORT_COUNT

async def process_delay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "delay_custom":
        keyboard = [[InlineKeyboardButton("رجوع 🔙", callback_data="cancel")]]
        await query.edit_message_text(
            "⏳ <b>فاصل زمني مخصص</b>\n\n"
            "أدخل الفاصل الزمني (بالثواني):",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ENTER_DELAY
    
    delay = int(query.data.split("_")[1])
    context.user_data["cycle_delay"] = delay
    
    # عرض ملخص وتأكيد
    config = context.user_data
    summary = (
        f"📝 <b>ملخص العملية</b>\n\n"
        f"• نوع الإبلاغ: إعلان ممول\n"
        f"• عدد البلاغات/حساب: {config['reports_per_account']}\n"
        f"• الفاصل الزمني: {config['cycle_delay']} ثانية\n\n"
        f"هل تريد بدء العملية؟"
    )
    keyboard = [
        [InlineKeyboardButton("بدء العملية ✅", callback_data="confirm")],
        [InlineKeyboardButton("رجوع 🔙", callback_data="cancel")],
    ]
    await query.edit_message_text(
        summary, 
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard))
    return CONFIRM_START

async def custom_delay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الفاصل الزمني المخصص"""
    try:
        delay = int(update.message.text)
        if delay <= 0:
            await update.message.reply_text("❌ يجب أن يكون الفاصل الزمني أكبر من الصفر.")
            return ENTER_DELAY
            
        context.user_data["cycle_delay"] = delay
    
        # عرض ملخص وتأكيد
        config = context.user_data
        summary = (
            f"📝 <b>ملخص العملية</b>\n\n"
            f"• نوع الإبلاغ: إعلان ممول\n"
            f"• عدد البلاغات/حساب: {config['reports_per_account']}\n"
            f"• الفاصل الزمني: {config['cycle_delay']} ثانية\n\n"
            f"هل تريد بدء العملية؟"
        )
        keyboard = [
            [InlineKeyboardButton("بدء العملية ✅", callback_data="confirm")],
            [InlineKeyboardButton("رجوع 🔙", callback_data="cancel")],
        ]
        await update.message.reply_text(
            summary, 
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard))
        return CONFIRM_START
    except ValueError:
        await update.message.reply_text("❌ أدخل رقمًا صحيحًا فقط.")
        return ENTER_DELAY
    
async def confirm_and_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["active"] = True
    
    # حساب التكلفة التقديرية
    num_accounts = len(context.user_data["accounts"])
    reports_per = context.user_data["reports_per_account"]
    total_reports = num_accounts * reports_per
    
    # تقدير الوقت
    delay = context.user_data["cycle_delay"]
    est_time = total_reports * delay / 60  # بالدقائق
    
    # بدء عملية الإبلاغ المحسنة في الخلفية (ستقوم بتحديث نفس الرسالة)
    asyncio.create_task(run_enhanced_report_process(update, context))
    return CONFIRM_START


sponsored_report_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_sponsored_report, pattern='^method_sponsored$')],
    states={
        ENTER_TARGET: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, process_target),
            CallbackQueryHandler(cancel_operation, pattern='^cancel$')
        ],
        ENTER_REPORT_COUNT: [
            CallbackQueryHandler(process_report_count, pattern='^count_'),
            MessageHandler(filters.TEXT & ~filters.COMMAND, custom_report_count),
            CallbackQueryHandler(cancel_operation, pattern='^cancel$')
        ],
        ENTER_DELAY: [
            CallbackQueryHandler(process_delay, pattern='^delay_'),
            MessageHandler(filters.TEXT & ~filters.COMMAND, custom_delay),
            CallbackQueryHandler(cancel_operation, pattern='^cancel$')
        ],
        CONFIRM_START: [
            CallbackQueryHandler(confirm_and_start, pattern='^confirm$'),
            CallbackQueryHandler(cancel_operation, pattern='^cancel$'),
        ],
    },
    fallbacks=[CallbackQueryHandler(cancel_operation, pattern='^cancel$')],
    per_user=True,
)