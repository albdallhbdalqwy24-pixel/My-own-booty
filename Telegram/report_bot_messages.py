import asyncio
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ContextTypes,
    CommandHandler,
)

from .common import cancel_operation, REPORT_TYPES
from telethon import TelegramClient, functions, types
from telethon.sessions import StringSession
from config import API_ID, API_HASH

# States - تم تبسيط الحالات حسب المتطلبات الجديدة
(
    SELECT_REASON,
    ENTER_BOT_USERNAME,
    ENTER_DETAILS,
    ENTER_REPORT_COUNT,
    ENTER_DELAY,
    CONFIRM_START,
) = range(70, 76)

async def start_bot_messages_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الخطوة 1: اختيار نوع البلاغ"""
    query = update.callback_query
    await query.answer()
    context.user_data["method_type"] = "bot_messages"

    keyboard = [[InlineKeyboardButton(r[0], callback_data=f"reason_{k}")] for k, r in REPORT_TYPES.items()]
    keyboard.append([InlineKeyboardButton("إلغاء ❌", callback_data="cancel")])
    
    await query.edit_message_text(
        "🤖 <b>طريقة الإبلاغ عن رسائل بوت</b>\n\n"
        "اختر سبب الإبلاغ:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_REASON

async def select_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الخطوة 2: اختيار سبب البلاغ"""
    query = update.callback_query
    await query.answer()
    reason_num = int(query.data.split("_")[1])
    context.user_data["reason_obj"] = REPORT_TYPES[reason_num][1]
    
    await query.edit_message_text(
        "🤖 <b>إدخال يوزر البوت</b>\n\n"
        "أرسل يوزر البوت المستهدف (مثال: @examplebot)",
        parse_mode="HTML"
    )
    return ENTER_BOT_USERNAME

async def process_bot_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الخطوة 3: معالجة يوزر البوت"""
    username = update.message.text.strip()
    if username.startswith("https://t.me/"):
        username = username.split("/")[-1]
    if not username.startswith("@"):
        username = "@" + username
    context.user_data["bot_username"] = username
    
    await update.message.reply_text(
        "💬 <b>التفاصيل الإضافية</b>\n\n"
        "أرسل رسالة تفصيلية للبلاغ (أو أرسل /skip للتخطي):",
        parse_mode="HTML"
    )
    return ENTER_DETAILS

async def process_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الخطوة 4: معالجة التفاصيل"""
    if update.message.text.strip().lower() != '/skip':
        context.user_data["message"] = update.message.text
    else:
        context.user_data["message"] = ""

    keyboard = [
        [InlineKeyboardButton("1 مرة", callback_data="count_1"),
         InlineKeyboardButton("2 مرات", callback_data="count_2")],
        [InlineKeyboardButton("3 مرات", callback_data="count_3"),
         InlineKeyboardButton("50 بلاغ 🔥", callback_data="count_50")],
        [InlineKeyboardButton("مخصص 🔢", callback_data="count_custom")]
    ]
    await update.message.reply_text(
        "🔄 <b>عدد مرات الإبلاغ</b>\n\n"
        "اختر عدد مرات الإبلاغ من كل حساب (كل حساب سيقوم بالإبلاغ عن جميع رسائل البوت الموجودة في المحادثة الخاصة):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ENTER_REPORT_COUNT

async def process_report_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الخطوة 5: معالجة عدد مرات الإبلاغ"""
    query = update.callback_query
    await query.answer()

    if query.data == "count_custom":
        await query.edit_message_text(
            "🔢 <b>عدد مخصص</b>\n\n"
            "أدخل عدد مرات الإبلاغ من كل حساب:",
            parse_mode="HTML"
        )
        return ENTER_REPORT_COUNT

    count = int(query.data.split("_")[1])
    context.user_data["reports_per_account"] = count

    keyboard = [
        [InlineKeyboardButton("5 ثواني", callback_data="delay_5")],
        [InlineKeyboardButton("10 ثواني", callback_data="delay_10")],
        [InlineKeyboardButton("30 ثواني", callback_data="delay_30")],
        [InlineKeyboardButton("مخصص", callback_data="delay_custom")]
    ]
    await query.edit_message_text(
        "⏱️ <b>الفاصل الزمني</b>\n\n"
        "اختر الفاصل الزمني بين عمليات الإبلاغ لكل حساب:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ENTER_DELAY

async def custom_report_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة عدد مرات الإبلاغ المخصص"""
    try:
        count = int(update.message.text)
        if count <= 0:
            await update.message.reply_text("❌ يجب أن يكون العدد أكبر من الصفر.")
            return ENTER_REPORT_COUNT
        context.user_data["reports_per_account"] = count
    except ValueError:
        await update.message.reply_text("❌ أدخل رقمًا صحيحًا فقط.")
        return ENTER_REPORT_COUNT

    keyboard = [
        [InlineKeyboardButton("5 ثواني", callback_data="delay_5")],
        [InlineKeyboardButton("10 ثواني", callback_data="delay_10")],
        [InlineKeyboardButton("30 ثواني", callback_data="delay_30")],
        [InlineKeyboardButton("مخصص", callback_data="delay_custom")]
    ]
    await update.message.reply_text(
        "⏱️ <b>الفاصل الزمني</b>\n\n"
        "اختر الفاصل الزمني بين عمليات الإبلاغ لكل حساب:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ENTER_DELAY

async def process_delay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الخطوة 5: معالجة الفاصل الزمني"""
    query = update.callback_query
    await query.answer()

    if query.data == "delay_custom":
        await query.edit_message_text(
            "⏳ <b>فاصل زمني مخصص</b>\n\n"
            "أدخل الفاصل الزمني (بالثواني):",
            parse_mode="HTML"
        )
        return ENTER_DELAY

    delay = int(query.data.split("_")[1])
    context.user_data["cycle_delay"] = delay

    # عرض ملخص وتأكيد
    cfg = context.user_data
    num_accounts = len(cfg.get("accounts", []))
    
    summary = (
        f"📝 <b>ملخص العملية</b>\n\n"
        f"• البوت: {cfg.get('bot_username')}\n"
        f"• عدد الحسابات: {num_accounts}\n"
        f"• مرات الإبلاغ من كل حساب: {cfg.get('reports_per_account', 1)}\n"
        f"• الفاصل الزمني بين الحسابات: {cfg.get('cycle_delay')} ثانية\n"
        f"• كل حساب سيقوم بالإبلاغ عن جميع رسائل البوت الموجودة في المحادثة الخاصة\n\n"
        f"هل تريد بدء العملية؟"
    )
    keyboard = [
        [InlineKeyboardButton("بدء العملية ✅", callback_data="confirm")],
        [InlineKeyboardButton("إلغاء ❌", callback_data="cancel")],
    ]
    await query.edit_message_text(
        summary,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CONFIRM_START

async def custom_delay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الفاصل الزمني المخصص"""
    try:
        delay = int(update.message.text)
        if delay <= 0:
            await update.message.reply_text("❌ يجب أن يكون الفاصل الزمني أكبر من الصفر.")
            return ENTER_DELAY
        context.user_data["cycle_delay"] = delay
    except ValueError:
        await update.message.reply_text("❌ أدخل رقمًا صحيحًا فقط.")
        return ENTER_DELAY

    cfg = context.user_data
    num_accounts = len(cfg.get("accounts", []))

    summary = (
        f"📝 <b>ملخص العملية</b>\n\n"
        f"• البوت: {cfg.get('bot_username')}\n"
        f"• عدد الحسابات: {num_accounts}\n"
        f"• مرات الإبلاغ من كل حساب: {cfg.get('reports_per_account', 1)}\n"
        f"• الفاصل الزمني بين الحسابات: {cfg.get('cycle_delay')} ثانية\n"
        f"• كل حساب سيقوم بالإبلاغ عن جميع رسائل البوت الموجودة في المحادثة الخاصة\n\n"
        f"هل تريد بدء العملية؟"
    )
    keyboard = [
        [InlineKeyboardButton("بدء العملية ✅", callback_data="confirm")],
        [InlineKeyboardButton("إلغاء ❌", callback_data="cancel")],
    ]
    await update.message.reply_text(
        summary,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CONFIRM_START

async def confirm_and_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الخطوة 6: تأكيد وبدء العملية"""
    query = update.callback_query
    await query.answer()
    context.user_data["active"] = True

    cfg = context.user_data
    num_accounts = len(cfg.get("accounts", []))

    # استخدام الرسالة الحالية كلوحة حية
    context.user_data["progress_message"] = query.message
    
    asyncio.create_task(run_bot_messages_report(update, context))
    return ConversationHandler.END

async def run_bot_messages_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تشغيل عملية الإبلاغ عن رسائل البوت"""
    cfg = context.user_data
    sessions = cfg.get("accounts", [])
    reason_obj = cfg.get("reason_obj")
    bot_username = cfg.get("bot_username")
    cycle_delay = cfg.get("cycle_delay", 5)
    detail_message = cfg.get("message", "")
    reports_per_account = cfg.get("reports_per_account", 1)

    # تتبع التقدم
    cfg.setdefault("lock", asyncio.Lock())
    cfg["progress_success"] = 0
    cfg["progress_failed"] = 0
    cfg["total_messages_reported"] = 0

    async def report_for_session(session):
        """الإبلاغ عن رسائل البوت لحساب واحد"""
        if not context.user_data.get("active", True) or context.user_data.get('stop_requested', False):
            return
            
        client = TelegramClient(StringSession(session["session"]), API_ID, API_HASH)
        try:
            await client.connect()
            entity = await client.get_entity(bot_username)
            
            # جلب جميع رسائل البوت من المحادثة الخاصة
            bot_messages = []
            async for m in client.iter_messages(entity, limit=None):  # لا يوجد حد - جميع الرسائل
                if m.from_id and getattr(m.from_id, 'user_id', None) == entity.id:
                    bot_messages.append(m.id)
            
            if not bot_messages:
                async with cfg["lock"]:
                    cfg["progress_failed"] += 1
                return
            
            # تحديث رسالة التقدم مع القائمة الحية
            async with cfg["lock"]:
                # لا نحتاج لزيادة total_messages_reported هنا لأننا سنزيدها مع كل بلاغ ناجح/فاشل
                current_total = cfg.get("total_messages_reported", 0)
                current_success = cfg.get("progress_success", 0)
                current_failed = cfg.get("progress_failed", 0)
                
                progress_text = (
                    f"⏳ <b>جاري الإبلاغ عن رسائل البوت...</b>\n\n"
                    f"• تم الإبلاغ عن: {current_total} رسالة\n"
                    f"• الحسابات الناجحة: {current_success}\n"
                    f"• الحسابات الفاشلة: {current_failed}\n"
                    f"• البوت: {bot_username}\n\n"
                    "جاري معالجة الحساب التالي..."
                )
                
                # إضافة القائمة الحية مع زر الإيقاف
                status_keyboard = [
                    [
                        InlineKeyboardButton(f"✅: {current_success}", callback_data="noop"),
                        InlineKeyboardButton(f"❌: {current_failed}", callback_data="noop")
                    ],
                    [
                        InlineKeyboardButton(f"📊: {current_total} رسالة", callback_data="noop")
                    ],
                    [
                        InlineKeyboardButton("⛔ إيقاف فوراً", callback_data="stop_bot_messages_report")
                    ]
                ]
                
                try:
                    await context.bot.edit_message_text(
                        chat_id=cfg["progress_message"].chat_id,
                        message_id=cfg["progress_message"].message_id,
                        text=progress_text,
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup(status_keyboard)
                    )
                except:
                    pass
            
            # تنفيذ الإبلاغ بعدد المرات المطلوب
            for rep in range(reports_per_account):
                if not context.user_data.get("active", True) or context.user_data.get('stop_requested', False):
                    break
                    
                # طلب خيارات البلاغ أولاً
                result = await client(functions.messages.ReportRequest(
                    peer=entity,
                    id=bot_messages,
                    option=b'',
                    message=''
                ))

                chosen_option = None
                if isinstance(result, types.ReportResultChooseOption):
                    # محاولة مطابقة السبب مع الخيارات المتاحة
                    for opt in result.options:
                        if reason_obj.__class__.__name__.lower().find(opt.text.lower()) != -1 or reason_obj.__class__.__name__.lower() == opt.text.lower():
                            chosen_option = opt.option
                            break
                    if not chosen_option and result.options:
                        chosen_option = result.options[0].option

                    # إرسال البلاغ مع الخيار المختار
                    try:
                        await client(functions.messages.ReportRequest(
                            peer=entity,
                            id=bot_messages,
                            option=chosen_option or b'',
                            message=detail_message
                        ))
                        async with cfg["lock"]:
                            cfg["progress_success"] += 1
                            cfg["total_messages_reported"] += len(bot_messages)
                    except Exception as e:
                        detailed_logger.error(f"Error in bot report: {e}")
                        async with cfg["lock"]:
                            cfg["progress_failed"] += 1
                    
                    # تحديث اللوحة الحية فوراً بعد كل بلاغ
                    async with cfg["lock"]:
                        current_total = cfg["total_messages_reported"]
                        current_success = cfg["progress_success"]
                        current_failed = cfg["progress_failed"]
                        
                        progress_text = (
                            f"⏳ <b>جاري الإبلاغ عن رسائل البوت...</b>\n\n"
                            f"• تم الإبلاغ عن: {current_total} رسالة\n"
                            f"• الحسابات الناجحة: {current_success}\n"
                            f"• الحسابات الفاشلة: {current_failed}\n"
                            f"• البوت: {bot_username}\n\n"
                            "جاري معالجة الحساب التالي..."
                        )
                        
                        status_keyboard = [
                            [
                                InlineKeyboardButton(f"✅: {current_success}", callback_data="noop"),
                                InlineKeyboardButton(f"❌: {current_failed}", callback_data="noop")
                            ],
                            [
                                InlineKeyboardButton(f"📊: {current_total} رسالة", callback_data="noop")
                            ],
                            [
                                InlineKeyboardButton("⛔ إيقاف فوراً", callback_data="stop_bot_messages_report")
                            ]
                        ]
                        
                        try:
                            await context.bot.edit_message_text(
                                chat_id=cfg["progress_message"].chat_id,
                                message_id=cfg["progress_message"].message_id,
                                text=progress_text,
                                parse_mode="HTML",
                                reply_markup=InlineKeyboardMarkup(status_keyboard)
                            )
                        except:
                            pass
                
                # تأخير بين التكرارات (إلا إذا كان آخر تكرار)
                if rep < reports_per_account - 1:
                    await asyncio.sleep(2)  # تأخير 2 ثانية بين التكرارات
                    
        except Exception as e:
            async with cfg["lock"]:
                cfg["progress_failed"] += 1
        finally:
            if client and client.is_connected():
                await client.disconnect()

    # تشغيل كل حساب بشكل منفصل مع فاصل زمني
    for i, session in enumerate(sessions):
        if not context.user_data.get("active", True) or context.user_data.get('stop_requested', False):
            break
            
        # إنشاء مهمة للحساب الحالي
        task = asyncio.create_task(report_for_session(session))
        context.user_data.setdefault("tasks", []).append(task)
        
        # انتظار انتهاء المهمة
        try:
            await task
        except asyncio.CancelledError:
            pass
        
        # فاصل زمني بين الحسابات (إلا إذا كان آخر حساب)
        if i < len(sessions) - 1:
            for _ in range(int(cycle_delay)):
                if not context.user_data.get("active", True) or context.user_data.get('stop_requested', False):
                    break
                await asyncio.sleep(1)

    # تحديث نهائي
    async with cfg["lock"]:
        success = cfg.get("progress_success", 0)
        failed = cfg.get("progress_failed", 0)
        total_messages = cfg.get("total_messages_reported", 0)
    
    # التحقق من الإيقاف اليدوي
    final_status = "✅ اكتملت العملية" if not context.user_data.get('stop_requested', False) else "⛔ تم الإيقاف يدوياً"
    
    text = (
        f"{final_status}\n\n"
        f"📊 <b>التقرير النهائي:</b>\n"
        f"• الحسابات الناجحة: {success}\n"
        f"• الحسابات الفاشلة: {failed}\n"
        f"• إجمالي الرسائل المبلغ عنها: {total_messages}\n"
        f"• البوت: {bot_username}"
    )
    
    try:
        await context.bot.edit_message_text(
            chat_id=cfg["progress_message"].chat_id,
            message_id=cfg["progress_message"].message_id,
            text="✅ اكتملت العملية. انظر الرسالة أدناه.",
            parse_mode="HTML"
        )
    except Exception:
        pass

    # عرض التقرير النهائي في رسالة منفصلة
    try:
        final_keyboard = [
            [InlineKeyboardButton("🔙 عودة للقائمة", callback_data="back_to_main_menu")]
        ]
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(final_keyboard)
        )
    except Exception:
        pass

# معالج المحادثة المبسط
bot_messages_report_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_bot_messages_report, pattern='^method_bot_messages$')],
    states={
        SELECT_REASON: [
            CallbackQueryHandler(select_reason, pattern='^reason_'),
            CallbackQueryHandler(cancel_operation, pattern='^cancel$')
        ],
        ENTER_BOT_USERNAME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, process_bot_username),
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
    fallbacks=[
        CallbackQueryHandler(cancel_operation, pattern='^cancel$'),
        CallbackQueryHandler(cancel_operation, pattern='^back$'),
        CommandHandler('cancel', cancel_operation)
    ],
    per_user=True,
)