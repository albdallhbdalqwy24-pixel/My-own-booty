# DrKhayal/Telegram/research.py - نظام بلاغ البحث (معدل)

import asyncio
import time
import logging
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ContextTypes,
    CommandHandler,
)

from telethon import TelegramClient, errors
from telethon.sessions import StringSession

from .common import cancel_operation

# استيراد الإعدادات
try:
    from config import API_ID, API_HASH
except ImportError:
    API_ID = None
    API_HASH = None

logger = logging.getLogger(__name__)

# حالات المحادثة (تم تحديثها)
(
    ENTER_MESSAGE_TEXT,
    ENTER_CYCLES_COUNT,
    ENTER_CYCLE_DELAY,
    CONFIRM_OPERATION,
    RUNNING_OPERATION,
) = range(100, 105)

# بوت البحث المستهدف
SEARCH_BOT = "@SearchReport"

async def start_research_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء عملية بلاغ البحث"""
    query = update.callback_query
    await query.answer()
    
    # التحقق من وجود الحسابات المحددة مسبقاً
    if 'accounts' not in context.user_data or not context.user_data['accounts']:
        await query.edit_message_text(
            "❌ <b>خطأ: لم يتم اختيار حسابات</b>\n\n"
            "يجب اختيار فئة الحسابات أولاً من القائمة الرئيسية.",
            parse_mode="HTML"
        )
        return ConversationHandler.END
    
    # تنظيف البيانات القديمة للحفاظ على البيانات الأساسية فقط
    accounts = context.user_data['accounts']
    proxies = context.user_data.get('proxies', [])
    
    # حفظ البيانات الأساسية
    context.user_data.clear()
    context.user_data["method_type"] = "research"
    context.user_data['accounts'] = accounts
    context.user_data['proxies'] = proxies
    
    # عرض معلومات التهيئة
    proxy_status = f"✅ {len(proxies)} بروكسي نشط" if proxies else "🔗 اتصال مباشر"
    
    await query.edit_message_text(
        f"🔍 <b>نظام بلاغ البحث</b>\n\n"
        f"📊 <b>الإعدادات الحالية:</b>\n"
        f"• الحسابات: {len(accounts)} حساب\n"
        f"• البروكسي: {proxy_status}\n\n"
        f"📝 <b>خطوات العمل:</b>\n"
        "1. إدخال نص البلاغ\n"
        "2. تحديد عدد الدورات\n"
        "3. تحديد الفاصل الزمني\n\n"
        f"🚀 <b>ملاحظة:</b> كل حساب سيرسل 3 رسائل:\n"
        "• /start\n"
        "• Submit\n"
        "• النص الذي تدخله\n\n"
        f"💬 <b>الخطوة 1: إدخال نص البلاغ</b>\n\n"
        "أرسل النص الذي تريد إرساله كرسالة ثالثة إلى @SearchReport:\n\n"
        f"📝 <b>مثال:</b>\n"
        f"هذا حساب يبيع مخدرات @username\n"
        f"يرجى حظره فوراً",
        parse_mode="HTML"
    )
    
    return ENTER_MESSAGE_TEXT

async def process_message_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة نص الرسالة"""
    message_text = update.message.text.strip()
    
    if not message_text:
        await update.message.reply_text("❌ النص لا يمكن أن يكون فارغاً. أرسل نصاً صالحاً.")
        return ENTER_MESSAGE_TEXT
    
    context.user_data['message_text'] = message_text
    
    keyboard = [
        [InlineKeyboardButton("1 دورة", callback_data="cycles_1")],
        [InlineKeyboardButton("3 دورات", callback_data="cycles_3")],
        [InlineKeyboardButton("5 دورات", callback_data="cycles_5")],
        [InlineKeyboardButton("10 دورات", callback_data="cycles_10")],
        [InlineKeyboardButton("مخصص", callback_data="cycles_custom")],
    ]
    
    await update.message.reply_text(
        "🔄 <b>الخطوة 2: عدد الدورات</b>\n\n"
        "اختر عدد الدورات التي سينفذها كل حساب:\n\n"
        "📊 <b>ملاحظة:</b> كل دورة تتكون من 3 رسائل:\n"
        "1. /start\n"
        "2. Submit\n"
        "3. النص الذي أدخلته\n\n"
        "اختر عدد الدورات:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return ENTER_CYCLES_COUNT

async def process_cycles_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة عدد الدورات"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cycles_custom":
        await query.edit_message_text(
            "🔢 <b>عدد دورات مخصص</b>\n\n"
            "أدخل عدد الدورات التي تريد تنفيذها لكل حساب:",
            parse_mode="HTML"
        )
        return ENTER_CYCLES_COUNT
    
    cycles = int(query.data.split("_")[1])
    context.user_data['cycles_count'] = cycles
    
    keyboard = [
        [InlineKeyboardButton("5 ثواني", callback_data="delay_5")],
        [InlineKeyboardButton("10 ثواني", callback_data="delay_10")],
        [InlineKeyboardButton("30 ثواني", callback_data="delay_30")],
        [InlineKeyboardButton("60 ثواني", callback_data="delay_60")],
        [InlineKeyboardButton("مخصص", callback_data="delay_custom")],
    ]
    
    await query.edit_message_text(
        "⏱️ <b>الخطوة 3: الفاصل الزمني</b>\n\n"
        "اختر الفاصل الزمني بين كل دورة والتي تليها لكل حساب:\n\n"
        "📝 <b>ملاحظة:</b> هذا هو الوقت الذي سينتظره الحساب بعد إكمال دورة كاملة (3 رسائل)\n"
        "قبل البدء في الدورة التالية.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return ENTER_CYCLE_DELAY

async def custom_cycles_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة عدد الدورات المخصص"""
    try:
        cycles = int(update.message.text)
        if cycles <= 0:
            await update.message.reply_text("❌ يجب أن يكون عدد الدورات أكبر من الصفر.")
            return ENTER_CYCLES_COUNT
        
        context.user_data['cycles_count'] = cycles
        
        keyboard = [
            [InlineKeyboardButton("5 ثواني", callback_data="delay_5")],
            [InlineKeyboardButton("10 ثواني", callback_data="delay_10")],
            [InlineKeyboardButton("30 ثواني", callback_data="delay_30")],
            [InlineKeyboardButton("60 ثواني", callback_data="delay_60")],
            [InlineKeyboardButton("مخصص", callback_data="delay_custom")],
        ]
        
        await update.message.reply_text(
            "⏱️ <b>الخطوة 3: الفاصل الزمني</b>\n\n"
            "اختر الفاصل الزمني بين كل دورة والتي تليها لكل حساب:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return ENTER_CYCLE_DELAY
    except ValueError:
        await update.message.reply_text("❌ أدخل رقمًا صحيحًا فقط.")
        return ENTER_CYCLES_COUNT

async def process_cycle_delay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الفاصل الزمني"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "delay_custom":
        await query.edit_message_text(
            "⏳ <b>فاصل زمني مخصص</b>\n\n"
            "أدخل الفاصل الزمني بين الدورات (بالثواني):",
            parse_mode="HTML"
        )
        return ENTER_CYCLE_DELAY
    
    delay = int(query.data.split("_")[1])
    context.user_data['cycle_delay'] = delay
    
    # عرض ملخص العملية
    return await show_confirmation(update, context)

async def custom_cycle_delay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الفاصل الزمني المخصص"""
    try:
        delay = int(update.message.text)
        if delay <= 0:
            await update.message.reply_text("❌ يجب أن يكون الفاصل الزمني أكبر من الصفر.")
            return ENTER_CYCLE_DELAY
        
        context.user_data['cycle_delay'] = delay
        
        # عرض ملخص العملية
        return await show_confirmation(update, context)
    except ValueError:
        await update.message.reply_text("❌ أدخل رقمًا صحيحًا فقط.")
        return ENTER_CYCLE_DELAY

async def show_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض ملخص العملية للتأكيد"""
    try:
        config = context.user_data
        
        # جمع المعلومات
        accounts = config.get('accounts', [])
        proxies = config.get('proxies', [])
        message_text = config.get('message_text', '')
        cycles_count = config.get('cycles_count', 1)
        cycle_delay = config.get('cycle_delay', 5)
        
        proxy_status = f"✅ {len(proxies)} بروكسي نشط" if proxies else "🔗 اتصال مباشر"
        
        summary = (
            f"📝 <b>ملخص عملية بلاغ البحث</b>\n\n"
            f"• عدد الحسابات: {len(accounts)}\n"
            f"• نوع الاتصال: {proxy_status}\n"
            f"• عدد الدورات/حساب: {cycles_count}\n"
            f"• الفاصل بين الدورات: {cycle_delay} ثانية\n\n"
            f"📋 <b>نص الرسالة الثالثة:</b>\n"
            f"{message_text[:200]}{'...' if len(message_text) > 200 else ''}\n\n"
            f"🚀 <b>إجمالي الرسائل المتوقعة:</b>\n"
            f"• {len(accounts)} حساب × {cycles_count} دورة × 3 رسائل = {len(accounts) * cycles_count * 3} رسالة\n\n"
            f"هل تريد بدء العملية؟"
        )
        
        keyboard = [
            [InlineKeyboardButton("بدء العملية ✅", callback_data="research_confirm")],
            [InlineKeyboardButton("إلغاء ❌", callback_data="cancel")],
        ]
        
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(
                summary,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                summary,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        return CONFIRM_OPERATION
        
    except Exception as e:
        logger.error(f"خطأ في show_confirmation: {e}")
        error_text = "❌ حدث خطأ أثناء عرض الملخص."
        
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(error_text)
        else:
            await update.message.reply_text(error_text)
        
        return CONFIRM_OPERATION

async def confirm_and_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تأكيد وبدء العملية"""
    query = update.callback_query
    await query.answer()
    
    # التحقق من وجود جميع البيانات المطلوبة
    required_keys = ['accounts', 'message_text', 'cycles_count', 'cycle_delay']
    for key in required_keys:
        if key not in context.user_data:
            await query.edit_message_text(f"❌ بيانات ناقصة: {key}")
            return CONFIRM_OPERATION
    
    # بدء العملية
    context.user_data['active'] = True
    
    msg = await query.edit_message_text(
        "🚀 <b>جاري بدء عملية بلاغ البحث...</b>\n\n"
        "⏳ يتم تحميل الحسابات وإعداد الاتصال...",
        parse_mode="HTML"
    )
    
    context.user_data['progress_message'] = msg
    
    # تشغيل العملية في الخلفية
    asyncio.create_task(run_research_process(update, context))
    
    return RUNNING_OPERATION

async def run_research_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنفيذ عملية بلاغ البحث"""
    try:
        config = context.user_data
        accounts = config.get('accounts', [])
        proxies = config.get('proxies', [])
        message_text = config.get('message_text', '')
        cycles_count = config.get('cycles_count', 1)
        cycle_delay = config.get('cycle_delay', 5)
        
        if not accounts:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ لا توجد حسابات صالحة لبدء العملية."
            )
            return
        
        # إعداد الإحصائيات
        total_accounts = len(accounts)
        total_messages_expected = total_accounts * cycles_count * 3
        
        config.update({
            "total_messages": total_messages_expected,
            "messages_sent": 0,
            "messages_failed": 0,
            "accounts_completed": 0,
            "accounts_failed": 0,
            "start_time": time.time(),
            "lock": asyncio.Lock(),
        })
        
        # تحديث رسالة التقدم
        progress_text = (
            f"📊 <b>بدء عملية بلاغ البحث</b>\n\n"
            f"• الحسابات: {total_accounts}\n"
            f"• الدورات/حساب: {cycles_count}\n"
            f"• الرسائل المتوقعة: {total_messages_expected}\n"
            f"• الحالة: جاري تحميل الحسابات...\n\n"
            f"⏳ يرجى الانتظار..."
        )
        
        try:
            await context.bot.edit_message_text(
                chat_id=config['progress_message'].chat_id,
                message_id=config['progress_message'].message_id,
                text=progress_text,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"خطأ في تحديث رسالة التقدم: {e}")
        
        # إنشاء مهام لكل حساب بشكل غير متزامن
        tasks = []
        for account in accounts:
            task = asyncio.create_task(
                process_account_research(
                    account, 
                    message_text, 
                    cycles_count, 
                    cycle_delay,
                    proxies,
                    config,
                    context
                )
            )
            tasks.append(task)
        
        config['tasks'] = tasks
        
        # مراقبة التقدم
        await monitor_research_progress(context, config['progress_message'], tasks)
        
    except Exception as e:
        logger.error(f"خطأ في run_research_process: {e}")
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"❌ خطأ في العملية: {str(e)}"
            )
        except:
            pass

async def process_account_research(account, message_text, cycles_count, cycle_delay, proxies, config, context):
    """معالجة حساب واحد لإرسال رسائل البحث"""
    session_str = account.get("session")
    account_id = account.get("id", "unknown")
    
    if not session_str:
        async with config["lock"]:
            config["accounts_failed"] += 1
        return
    
    client = None
    current_proxy = None
    
    try:
        # اختيار بروكسي عشوائي إذا كان متوفراً
        if proxies:
            import random
            current_proxy = random.choice(proxies) if proxies else None
        
        # إعداد معلمات العميل
        params = {
            "api_id": API_ID,
            "api_hash": API_HASH,
            "timeout": 30,
            "device_model": f"ResearchBot-{account_id}",
            "system_version": "1.0.0",
            "app_version": "1.0.0"
        }
        
        if current_proxy:
            try:
                import socks
                params.update({
                    "proxy": (socks.SOCKS5, current_proxy["host"], current_proxy["port"])
                })
            except ImportError:
                current_proxy = None
        
        # الاتصال
        client = TelegramClient(StringSession(session_str), **params)
        await client.connect()
        
        # التحقق من تفعيل الجلسة
        if not await client.is_user_authorized():
            raise Exception(f"الجلسة غير مفوضة")
        
        # حل بوت البحث
        try:
            bot_entity = await client.get_entity(SEARCH_BOT)
        except Exception as e:
            raise Exception(f"لا يمكن الوصول إلى {SEARCH_BOT}: {str(e)}")
        
        # تنفيذ الدورات
        for cycle in range(cycles_count):
            if not context.user_data.get("active", True):
                break
            
            try:
                # الرسالة الأولى: /start
                await client.send_message(bot_entity, "/start")
                async with config["lock"]:
                    config["messages_sent"] += 1
                
                # انتظار بسيط بين الرسائل
                await asyncio.sleep(2)
                
                # الرسالة الثانية: "Submit"
                await client.send_message(bot_entity, "Submit")
                async with config["lock"]:
                    config["messages_sent"] += 1
                
                # انتظار بسيط بين الرسائل
                await asyncio.sleep(2)
                
                # الرسالة الثالثة: النص الذي أدخله المستخدم
                await client.send_message(bot_entity, message_text)
                async with config["lock"]:
                    config["messages_sent"] += 1
                
                # تسجيل الدورة الناجحة
                logger.info(f"✅ الحساب {account_id}: أكمل الدورة {cycle + 1}/{cycles_count}")
                
                # انتظار بين الدورات (إلا إذا كانت الدورة الأخيرة)
                if cycle < cycles_count - 1:
                    for _ in range(cycle_delay):
                        if not context.user_data.get("active", True):
                            break
                        await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"❌ الحساب {account_id}: فشل في الدورة {cycle + 1}: {str(e)}")
                async with config["lock"]:
                    config["messages_failed"] += 3  # فشل 3 رسائل
        
        # تحديث عدد الحسابات المكتملة
        async with config["lock"]:
            config["accounts_completed"] += 1
        
    except Exception as e:
        logger.error(f"❌ الحساب {account_id}: فشل كامل: {str(e)}")
        async with config["lock"]:
            config["accounts_failed"] += 1
            config["messages_failed"] += (cycles_count * 3)  # فشل جميع رسائل هذا الحساب
    
    finally:
        if client and client.is_connected():
            try:
                await client.disconnect()
            except:
                pass

async def monitor_research_progress(context, progress_message, tasks):
    """مراقبة تقدم عملية البحث"""
    config = context.user_data
    start_time = config.get("start_time", time.time())
    
    try:
        while config.get("active", True) and any(not t.done() for t in tasks):
            async with config["lock"]:
                messages_sent = config.get("messages_sent", 0)
                messages_failed = config.get("messages_failed", 0)
                accounts_completed = config.get("accounts_completed", 0)
                accounts_failed = config.get("accounts_failed", 0)
                total_accounts = len(config.get("accounts", []))
                total_messages = config.get("total_messages", 1)
            
            if not config.get("active", True):
                break
            
            # حساب النسب
            completed = messages_sent + messages_failed
            progress_percent = min(100, int((completed / total_messages) * 100)) if total_messages > 0 else 0
            
            # حساب الوقت
            elapsed = time.time() - start_time
            if messages_sent > 0 and elapsed > 0:
                speed = messages_sent / elapsed
                if speed > 0:
                    remaining = total_messages - completed
                    eta_seconds = remaining / speed
                    eta_str = str(timedelta(seconds=int(eta_seconds)))
                else:
                    eta_str = "حساب..."
            else:
                eta_str = "حساب..."
            
            # شريط التقدم
            filled = int(20 * (progress_percent / 100))
            progress_bar = "█" * filled + "░" * (20 - filled)
            
            # حساب النجاح والفشل
            success_rate = (messages_sent / completed * 100) if completed > 0 else 0
            
            text = (
                f"📊 <b>تقدم عملية بلاغ البحث</b>\n\n"
                f"<code>[{progress_bar}]</code> {progress_percent}%\n\n"
                f"📈 <b>الإحصائيات:</b>\n"
                f"▫️ الحسابات: {accounts_completed + accounts_failed}/{total_accounts}\n"
                f"✅ الرسائل الناجحة: {messages_sent}\n"
                f"❌ الرسائل الفاشلة: {messages_failed}\n"
                f"📊 معدل النجاح: {success_rate:.1f}%\n"
                f"⏱ المتبقي: {eta_str}\n"
                f"⏰ المدة: {str(timedelta(seconds=int(elapsed)))}"
            )
            
            try:
                await context.bot.edit_message_text(
                    chat_id=progress_message.chat_id,
                    message_id=progress_message.message_id,
                    text=text,
                    parse_mode="HTML"
                )
            except Exception:
                pass
            
            await asyncio.sleep(3)
        
        # النتائج النهائية
        async with config["lock"]:
            messages_sent = config.get("messages_sent", 0)
            messages_failed = config.get("messages_failed", 0)
            accounts_completed = config.get("accounts_completed", 0)
            accounts_failed = config.get("accounts_failed", 0)
            total_accounts = len(config.get("accounts", []))
        
        total_messages = messages_sent + messages_failed
        success_rate = (messages_sent / total_messages * 100) if total_messages > 0 else 0
        elapsed = time.time() - start_time
        
        final_text = (
            f"🎯 <b>اكتملت عملية بلاغ البحث!</b>\n\n"
            f"📊 <b>النتائج النهائية:</b>\n"
            f"• الحسابات الناجحة: {accounts_completed}/{total_accounts}\n"
            f"• الحسابات الفاشلة: {accounts_failed}/{total_accounts}\n"
            f"• الرسائل المرسولة: {messages_sent}\n"
            f"• الرسائل الفاشلة: {messages_failed}\n"
            f"• معدل النجاح: {success_rate:.1f}%\n"
            f"• المدة الإجمالية: {str(timedelta(seconds=int(elapsed)))}\n\n"
            f"✅ تم إرسال جميع الرسائل إلى @SearchReport"
        )
        
        try:
            await context.bot.edit_message_text(
                chat_id=progress_message.chat_id,
                message_id=progress_message.message_id,
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
                chat_id=progress_message.chat_id,
                text=final_text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(final_keyboard)
            )
        except Exception:
            pass
        
    except Exception as e:
        logger.error(f"خطأ في مراقبة التقدم: {e}")
        try:
            await progress_message.edit_text(f"❌ خطأ في مراقبة التقدم: {str(e)}")
        except:
            pass

# معالج المحادثة المعدل
research_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_research_report, pattern='^method_research$')],
    states={
        ENTER_MESSAGE_TEXT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, process_message_text),
            CallbackQueryHandler(cancel_operation, pattern='^cancel$'),
        ],
        ENTER_CYCLES_COUNT: [
            CallbackQueryHandler(process_cycles_count, pattern='^cycles_'),
            MessageHandler(filters.TEXT & ~filters.COMMAND, custom_cycles_count),
            CallbackQueryHandler(cancel_operation, pattern='^cancel$'),
        ],
        ENTER_CYCLE_DELAY: [
            CallbackQueryHandler(process_cycle_delay, pattern='^delay_'),
            MessageHandler(filters.TEXT & ~filters.COMMAND, custom_cycle_delay),
            CallbackQueryHandler(cancel_operation, pattern='^cancel$'),
        ],
        CONFIRM_OPERATION: [
            CallbackQueryHandler(confirm_and_start, pattern='^research_confirm$'),
            CallbackQueryHandler(cancel_operation, pattern='^cancel$'),
        ],
        RUNNING_OPERATION: [
            CallbackQueryHandler(cancel_operation, pattern='^cancel$'),
            CommandHandler('cancel', cancel_operation),
        ],
    },
    fallbacks=[
        CallbackQueryHandler(cancel_operation, pattern='^cancel$'),
        CommandHandler('cancel', cancel_operation),
        CommandHandler('start', cancel_operation),
    ],
    per_user=True,
    per_chat=False,
    per_message=False,
)