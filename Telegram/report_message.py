import asyncio
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ContextTypes,
)

from .common import run_report_process, cancel_operation, REPORT_TYPES, parse_message_link
from .common_improved import run_enhanced_report_process

# States
(
    SELECT_REASON,
    ENTER_TARGETS,
    ENTER_DETAILS,
    ENTER_REPORT_COUNT,
    ENTER_DELAY,
    CONFIRM_START,
) = range(20, 26)

async def start_message_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["method_type"] = "message"

    keyboard = [[InlineKeyboardButton(r[0], callback_data=f"reason_{k}")] for k, r in REPORT_TYPES.items()]
    keyboard.append([InlineKeyboardButton("رجوع 🔙", callback_data="cancel")])
    
    await query.edit_message_text(
        "📬 <b>طريقة الإبلاغ عن الرسائل</b>\n\n"
        "اختر سبب الإبلاغ من القائمة:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
        )
    return SELECT_REASON
    
async def select_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    reason_num = int(query.data.split("_")[1])
    context.user_data["reason_obj"] = REPORT_TYPES[reason_num][1]
    
    keyboard = [[InlineKeyboardButton("رجوع 🔙", callback_data="cancel")]]
    await query.edit_message_text(
        "📩 <b>إدخال روابط الرسائل</b>\n\n"
        "أرسل رابط الرسالة أو عدة روابط مفصولة بفاصلة (,)\n\n"
        "📌 <i>أمثلة:</i>\n"
        "https://t.me/channel_name/123\n"
        "https://t.me/c/123456789/456",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ENTER_TARGETS

async def process_targets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    targets_input = update.message.text.strip().split(',')
    # تنظيف الروابط والتأكد من أنها صالحة
    valid_targets = []
    for link in targets_input:
        link = link.strip()
        if not link:
            continue
            
        # استخدام دالة التحليل من common.py
        parsed = parse_message_link(link)
        if parsed:
            valid_targets.append({
                "channel": parsed["channel"],
                "message_id": parsed["message_id"]
            })
    
    if not valid_targets:
        await update.message.reply_text(
            "❌ <b>خطأ في المدخلات</b>\n"
            "لم يتم إرسال روابط صالحة. يرجى المحاولة مرة أخرى.",
            parse_mode="HTML"
        )
        return ENTER_TARGETS
        
    context.user_data["targets"] = valid_targets
    keyboard = [[InlineKeyboardButton("رجوع 🔙", callback_data="cancel")]]
    await update.message.reply_text(
        "💬 <b>التفاصيل الإضافية</b>\n\n"
        "أرسل رسالة تفصيلية للبلاغ (أو أرسل /skip للتخطي):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ENTER_DETAILS
    
async def process_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip().lower() != '/skip':
        context.user_data["message"] = update.message.text
    else:
        context.user_data["message"] = ""
    
    keyboard = [
        [InlineKeyboardButton("1 مرة", callback_data="count_1"),
         InlineKeyboardButton("2 مرات", callback_data="count_2")],
        [InlineKeyboardButton("3 مرات", callback_data="count_3"),
         InlineKeyboardButton("50 بلاغ 🔥", callback_data="count_50")],
        [InlineKeyboardButton("مخصص 🔢", callback_data="count_custom")],
        [InlineKeyboardButton("رجوع 🔙", callback_data="cancel")]
    ]
    await update.message.reply_text(
        "🔄 <b>عدد مرات الإبلاغ</b>\n\n"
        "اختر عدد مرات الإبلاغ على كل رسالة من كل حساب:",
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
        f"• عدد الرسائل: {len(config['targets'])}\n"
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
            f"• عدد الرسائل: {len(config['targets'])}\n"
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
    num_targets = len(context.user_data["targets"])
    reports_per = context.user_data["reports_per_account"]
    total_reports = num_accounts * num_targets * reports_per
    
    # تقدير الوقت
    delay = context.user_data["cycle_delay"]
    est_time = total_reports * delay / 60  # بالدقائق
    
    # بدء عملية الإبلاغ المحسنة في الخلفية (ستقوم بتحديث نفس الرسالة)
    asyncio.create_task(run_enhanced_report_process(update, context))
    return ConversationHandler.END


message_report_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_message_report, pattern='^method_message$')],
    states={
        SELECT_REASON: [
            CallbackQueryHandler(select_reason, pattern='^reason_'),
            CallbackQueryHandler(cancel_operation, pattern='^cancel$')
        ],
        ENTER_TARGETS: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, process_targets),
            CallbackQueryHandler(cancel_operation, pattern='^cancel$')
        ],
        ENTER_DETAILS: [
            MessageHandler(filters.TEXT | filters.COMMAND, process_details),
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