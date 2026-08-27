from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, MessageHandler, ConversationHandler, CommandHandler, filters, ContextTypes
from telethon import TelegramClient
from telethon.sessions import StringSession
# Removed MTProto proxy import - now using Socks5
from telethon.errors import AuthKeyDuplicatedError
import os
import asyncio
import sqlite3
import logging

# استيراد DB_PATH من config.py
try:
    from config import DB_PATH
except ImportError:
    DB_PATH = 'accounts.db'  # قيمة افتراضية

# تعريف حالات ConversationHandler لقسم الدعم الخاص
SELECT_SUPPORT_TYPE = 300
ENTER_SUPPORT_MESSAGE = 301
GET_SUPPORT_ATTACHMENTS = 302
ENTER_SUPPORT_COUNT = 303
ENTER_SUPPORT_DELAY = 304
CONFIRM_SUPPORT = 305
SUPPORT_PROGRESS = 306

# --- دوال مساعدة ---
def get_categories(user_id=None):
    """استيراد الفئات مع عدد الحسابات في كل فئة"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        query = """
            SELECT 
                c.id, 
                c.name,
                COUNT(a.id) AS account_count
            FROM categories c
            LEFT JOIN accounts a ON c.id = a.category_id AND a.is_active = 1
        """
        params = []
        if user_id:
            query += " WHERE c.owner_id = ?"
            params.append(user_id)
            # إضافة شرط لتصفية الحسابات حسب owner_id أيضاً
            query = query.replace(
                "LEFT JOIN accounts a ON c.id = a.category_id AND a.is_active = 1",
                "LEFT JOIN accounts a ON c.id = a.category_id AND a.is_active = 1 AND a.owner_id = ?"
            )
            params.insert(0, user_id)  # إضافة user_id للـ JOIN
            
        query += """
            GROUP BY c.id, c.name
            HAVING COUNT(a.id) > 0
            ORDER BY c.created_at DESC
        """
        
        cursor.execute(query, tuple(params))
        categories = cursor.fetchall()
        conn.close()
        return categories
    except Exception as e:
        logging.error(f"خطأ في استيراد الفئات: {e}")
        return []

def get_accounts(category_id, user_id=None):
    """استيراد الحسابات لفئة محددة مع فك تشفير الجلسات"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        query = """
            SELECT id, phone, username, session_str, device_info 
            FROM accounts 
            WHERE category_id = ?
        """
        params = [category_id]
        if user_id:
            query += " AND owner_id = ?"
            params.append(user_id)
            
        cursor.execute(query, tuple(params))
        
        accounts = []
        for row in cursor.fetchall():
            # فك تشفير الجلسة
            decrypted_session = decrypt_session(row[3])
            if decrypted_session:
                accounts.append({
                    "id": row[0],
                    "phone": row[1],
                    "username": row[2],
                    "session_str": decrypted_session,
                    "device_info": row[4]
                })
        conn.close()
        return accounts
    except Exception as e:
        logging.error(f"خطأ في استيراد الحسابات: {e}")
        return []

def decrypt_session(enc_session: str) -> str:
    """فك تشفير جلسة التليجرام"""
    try:
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.backends import default_backend
        import base64
        
        SALT = os.getenv('ENCRYPTION_SALT', 'default_salt').encode()
        PASSPHRASE = os.getenv('ENCRYPTION_PASSPHRASE', 'default_pass').encode()
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=SALT,
            iterations=100000,
            backend=default_backend()
        )
        ENCRYPTION_KEY = base64.urlsafe_b64encode(kdf.derive(PASSPHRASE))
        cipher_suite = Fernet(ENCRYPTION_KEY)
        
        return cipher_suite.decrypt(enc_session.encode()).decode()
    except Exception as e:
        logging.error(f"خطأ في فك تشفير الجلسة: {e}")
        return None

# --- 1. بدء محادثة الدعم الخاص ---
async def start_special_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    BACK_BUTTON = InlineKeyboardButton('رجوع', callback_data='back')
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    context.user_data.setdefault('state_stack', []).append('start_special_support')
    keyboard = [
        [InlineKeyboardButton("انتهاكات عامة", callback_data="special_support_1")],
        [InlineKeyboardButton("انتهاك الملكية", callback_data="special_support_2")],
        [InlineKeyboardButton("احتيال", callback_data="special_support_3")],
        [InlineKeyboardButton("مشاكل بوتات", callback_data="special_support_4")],
        [BACK_BUTTON]
    ]
    await query.edit_message_text(
        "🛠️ اختر نوع الدعم الخاص:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_SUPPORT_TYPE

# --- 2. بعد اختيار نوع الدعم: إظهار رسالة فحص الحسابات ثم تلخيص النتائج وطلب نص الرسالة ---
async def select_support_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    BACK_BUTTON = InlineKeyboardButton('رجوع', callback_data='back')
    API_ID = int(os.getenv('TG_API_ID', '26924046'))
    API_HASH = os.getenv('TG_API_HASH', '4c6ef4cee5e129b7a674de156e2bcc15')
    
    query = update.callback_query
    await query.answer()

    # 1) استخراج نوع الدعم
    support_type = int(query.data.split("_")[-1])
    context.user_data['support_type'] = support_type

    # 2) نستجيب فوراً برسالة "جاري فحص الحسابات..."
    progress_msg = await query.edit_message_text("⏳ جاري فحص الحسابات، يرجى الانتظار...")

    # 3) تحميل جميع الحسابات من قاعدة البيانات
    categories = get_categories(update.effective_user.id)
    all_accounts = []
    for category in categories:
        category_id = category[0]
        accounts = get_accounts(category_id, update.effective_user.id)
        all_accounts.extend(accounts)

    # 4) فحص صلاحية كل حساب
    valid_sessions = []
    invalid_count = 0

    for account in all_accounts:
        client = TelegramClient(StringSession(account['session_str']), API_ID, API_HASH)
        try:
            await client.connect()
            await client.get_me()  # تفعيل الجلسة
            valid_sessions.append(account)
        except Exception as e:
            invalid_count += 1
        finally:
            await client.disconnect()

    # 5) إذا لم توجد جلسات صالحة، نعرض رسالة خطأ
    if not valid_sessions:
        await progress_msg.edit_text(
            "❌ لا توجد جلسات صالحة بعد الفحص.",
            reply_markup=InlineKeyboardMarkup([[BACK_BUTTON]])
        )
        return ConversationHandler.END

    # 6) حفظ الجلسات الصالحة في context
    context.user_data['sessions'] = valid_sessions

    # 7) تحديث الرسالة بعد الفحص لإظهار النتائج
    await progress_msg.edit_text(
        f"✅ تم فحص الحسابات:\n"
        f"- صالحة: {len(valid_sessions)}\n"
        f"- غير صالحة: {invalid_count}\n\n"
        "🖋️ الآن أرسل نص رسالة الدعم الخاص:",
        reply_markup=InlineKeyboardMarkup([[BACK_BUTTON]])
    )
    context.user_data.setdefault('state_stack', []).append(ENTER_SUPPORT_MESSAGE)
    return ENTER_SUPPORT_MESSAGE

# --- 3. استقبال نص رسالة الدعم ---
async def get_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    BACK_BUTTON = InlineKeyboardButton('رجوع', callback_data='back')
    text = update.message.text.strip()
    if text == 'رجوع':
        return await cancel(update, context)
    context.user_data["message"] = update.message.text
    kb = [[InlineKeyboardButton('التالي ➡️', callback_data='next')], [BACK_BUTTON]]
    await update.message.reply_text(
        'أرسل مرفق أو اضغط التالي:',
        reply_markup=InlineKeyboardMarkup(kb)
    )
    context.user_data.setdefault('state_stack', []).append(GET_SUPPORT_ATTACHMENTS)
    return GET_SUPPORT_ATTACHMENTS

# --- 4. استقبال المرفقات (اختياري) ---
async def get_support_attachments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    BACK_BUTTON = InlineKeyboardButton('رجوع', callback_data='back')
    TEMP_DIR = 'temp_attachments'
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    if update.message.document:
        file = await update.message.document.get_file()
        name = update.message.document.file_name
    elif update.message.photo:
        file = await update.message.photo[-1].get_file()
        name = f"photo_{file.file_id}.jpg"
    else:
        await update.message.reply_text('نوع المرفق غير مدعوم.', reply_markup=InlineKeyboardMarkup([[BACK_BUTTON]]))
        return GET_SUPPORT_ATTACHMENTS
    
    path = os.path.join(TEMP_DIR, f"{file.file_id}_{name}")
    await file.download_to_drive(path)
    context.user_data.setdefault('attachments', []).append(path)
    
    kb = [[InlineKeyboardButton('التالي ➡️', callback_data='next')], [BACK_BUTTON]]
    await update.message.reply_text(f'تم رفع {name}', reply_markup=InlineKeyboardMarkup(kb))
    context.user_data.setdefault('state_stack', []).append(GET_SUPPORT_ATTACHMENTS)
    return GET_SUPPORT_ATTACHMENTS

# --- 5. الانتقال بعد الانتهاء من المرفقات ---
async def next_step_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    BACK_BUTTON = InlineKeyboardButton('رجوع', callback_data='back')
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        '🔢 الآن أدخل عدد مرات الإرسال لكل حساب:',
        reply_markup=InlineKeyboardMarkup([[BACK_BUTTON]])
    )
    context.user_data.setdefault('state_stack', []).append(ENTER_SUPPORT_COUNT)
    return ENTER_SUPPORT_COUNT

# --- 6. استقبال عدد مرات الإرسال ---
async def get_support_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    BACK_BUTTON = InlineKeyboardButton('رجوع', callback_data='back')
    text = update.message.text.strip()
    if text == 'رجوع':
        return await cancel(update, context)
    try:
        count = int(text)
        if count <= 0:
            raise ValueError
        context.user_data['count'] = count
        await update.message.reply_text(
            '🔢 الآن أدخل التأخير بين كل إرسال (بالثواني):',
            reply_markup=InlineKeyboardMarkup([[BACK_BUTTON]])
        )
        context.user_data.setdefault('state_stack', []).append(ENTER_SUPPORT_DELAY)
        return ENTER_SUPPORT_DELAY
    except:
        await update.message.reply_text('عدد غير صالح!', reply_markup=InlineKeyboardMarkup([[BACK_BUTTON]]))
        return ENTER_SUPPORT_COUNT

# --- 7. استقبال قيمة التأخير ---
async def get_support_delay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    BACK_BUTTON = InlineKeyboardButton('رجوع', callback_data='back')
    text = update.message.text.strip()
    if text == 'رجوع':
        return await cancel(update, context)
    try:
        d = float(text)
        if d < 0:
            raise ValueError
        context.user_data['delay'] = d
        count = context.user_data.get('count', 0)
        attachments = context.user_data.get('attachments', [])
        support_type = context.user_data.get('support_type', 0)
        support_labels = {1: "انتهاكات عامة", 2: "انتهاك الملكية", 3: "احتيال", 4: "مشاكل بوتات"}
        summary = (
            f"عدد مرات الإرسال من كل حساب: {count}\n"
            f"نوع الدعم: {support_labels.get(support_type, '')}\n"
            f"نص الرسالة: {context.user_data.get('message', '') or 'بدون نص'}\n"
            f"عدد المرفقات: {len(attachments)}\n"
            f"التأخير بين كل إرسال: {d} ث\n"
            "اضغط إرسال."
        )
        kb = [[InlineKeyboardButton('إرسال', callback_data='support_send')], [BACK_BUTTON]]
        await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(kb))
        context.user_data.setdefault('state_stack', []).append(CONFIRM_SUPPORT)
        return CONFIRM_SUPPORT
    except:
        await update.message.reply_text('تأخير غير صالح!', reply_markup=InlineKeyboardMarkup([[BACK_BUTTON]]))
        return ENTER_SUPPORT_DELAY

# --- 8. تأكيد الإرسال ---
async def confirm_support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة زر الإرسال: بدء عملية إرسال الدعم."""
    await update.callback_query.answer()
    return await perform_support(update, context)

async def perform_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنفيذ الإرسال المتوازي لرسائل الدعم باستخدام جلسات تيليجرام."""
    required_keys = ['count', 'message', 'delay']
    for key in required_keys:
        if key not in context.user_data:
            await update.callback_query.message.reply_text(f'❌ بيانات ناقصة: {key}')
            return
    
    # استخدام الجلسات التي تم فحص صلاحيتها سابقًا
    sessions = context.user_data.get('sessions', [])
    if not sessions:
        await update.callback_query.message.reply_text('❌ لا توجد جلسات تيليجرام مخزنة.')
        return
    
    # إرسال رسالة بداية واستعداد للتتبع
    msg = update.callback_query.message
    await msg.reply_text('📤 جاري بدء إرسال الدعم الخاص...')
    start_text = "📊 جاري الإرسال..."
    context.user_data["progress_message"] = await msg.reply_text(start_text)
    context.user_data["active"] = True
    
    # بدء مهمة الخلفية لمراقبة التقدم
    task = asyncio.create_task(run_support_process(update, context))
    context.user_data.setdefault("tasks", []).append(task)
    return SUPPORT_PROGRESS

async def run_support_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    تنفيذ إرسال رسالة الدعم الخاص بالتوازي لكل جلسة،
    وتحديث رسالة التقدم كل 15 ثانية حتى الانتهاء أو الإلغاء.
    """
    cfg = context.user_data
    sessions = cfg.get("sessions", [])
    count = cfg.get("count", 0)
    total_msgs = len(sessions) * count
    cfg["total_msgs"] = total_msgs
    cfg["progress_sent"] = 0
    cfg["progress_failed"] = 0

    # تحديد جهة الاتصال حسب نوع الدعم
    support_type = cfg.get("support_type", 0)
    support_contacts = {
        1: '@AbuseNotifications',
        2: '@dmcatelegram',
        3: '@notoscam',
        4: '@BotSupport'
    }
    contact = support_contacts.get(support_type)
    if not contact:
        await context.bot.edit_message_text(
            chat_id=cfg["progress_message"].chat_id,
            message_id=cfg["progress_message"].message_id,
            text="❌ نوع دعم غير صالح!"
        )
        return ConversationHandler.END

    # إنشاء مهام إرسال لكل جلسة
    session_tasks = []
    for session_data in sessions:
        task = asyncio.create_task(do_session_support(session_data, contact, cfg, context))
        context.user_data.setdefault("tasks", []).append(task)
        session_tasks.append(task)

    # دالة داخلية لتحديث التقدم كل 15 ثانية
    async def update_progress():
        while context.user_data.get("active", True) and not all(t.done() for t in session_tasks):
            sent = cfg.get("progress_sent", 0)
            failed = cfg.get("progress_failed", 0)
            remaining = total_msgs - sent - failed
            text = (
                f"📊 تقدم إرسال الدعم الخاص:\n"
                f"- الإجمالي المطلوب: {total_msgs}\n"
                f"- تم الإرسال: {sent}\n"
                f"- المتبقي: {remaining}\n"
                f"- الفشل: {failed}"
            )
            try:
                await context.bot.edit_message_text(
                    chat_id=cfg["progress_message"].chat_id,
                    message_id=cfg["progress_message"].message_id,
                    text=text
                )
            except Exception:
                pass
            await asyncio.sleep(15)

    # بدء مهمة تحديث التقدم
    asyncio.create_task(update_progress())
    
    # انتظار انتهاء جميع مهام الجلسات
    await asyncio.gather(*session_tasks, return_exceptions=True)

    # تعديل الرسالة النهائية عند الانتهاء
    try:
        await context.bot.edit_message_text(
            chat_id=cfg["progress_message"].chat_id,
            message_id=cfg["progress_message"].message_id,
            text="✅ تم الانتهاء من جميع عمليات الدعم الخاص!",
            reply_markup=None
        )
    except Exception:
        pass

    # حذف الملفات المؤقتة
    for fp in cfg.get('attachments', []):
        try:
            os.remove(fp)
        except:
            pass

    # إعادة المستخدم إلى القائمة الرئيسية
    chat_id = cfg["progress_message"].chat_id
    kb = [
        [InlineKeyboardButton('قسم بلاغات ايميل', callback_data='email_reports')],
        [InlineKeyboardButton('قسم بلاغات تيليجرام', callback_data='telegram_reports')]
    ]
    await context.bot.send_message(
        chat_id=chat_id, 
        text='✅ تم الانتهاء بنجاح! اختر القسم:',
        reply_markup=InlineKeyboardMarkup(kb)
    )
    context.user_data.clear()

async def do_session_support(session_data, contact, cfg, context):
    """تنفيذ إرسال رسالة الدعم لحساب تيليجرام واحد (جلسة واحدة)."""
    API_ID = int(os.getenv('TG_API_ID', '26924046'))
    API_HASH = os.getenv('TG_API_HASH', '4c6ef4cee5e129b7a674de156e2bcc15')
    
    client = None
    connected = False
    proxies = cfg.get("proxies", [])

    # محاولة الاتصال عبر بروكسيات Socks5 إن وجدت
    for proxy in proxies:
        if not context.user_data.get("active", True):
            return
        try:
            import socks
            import socket
            
            # إعداد البروكسي Socks5
            socks.set_default_proxy(socks.SOCKS5, proxy["host"], proxy["port"])
            socket.socket = socks.socksocket
            
            client = TelegramClient(
                StringSession(session_data['session_str']),
                API_ID,
                API_HASH,
                auto_reconnect=True,
                connection_retries=5,
                retry_delay=5
            )
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                # إعادة تعيين الإعدادات
                socks.set_default_proxy()
                import socket as original_socket
                socket.socket = original_socket.socket
                return
            connected = True
            break
        except AuthKeyDuplicatedError:
            # إعادة تعيين الإعدادات عند الخطأ
            socks.set_default_proxy()
            import socket as original_socket
            socket.socket = original_socket.socket
            return
        except Exception:
            # إعادة تعيين الإعدادات عند الخطأ
            try:
                socks.set_default_proxy()
                import socket as original_socket
                socket.socket = original_socket.socket
            except:
                pass
            if client:
                try: 
                    await client.disconnect()
                except: 
                    pass
            continue

    # إذا لم تنجح البروكسيات، المحاولة بدونها
    if not connected:
        try:
            client = TelegramClient(
                StringSession(session_data['session_str']), 
                API_ID, 
                API_HASH
            )
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                return
        except Exception:
            return

    # إرسال الرسائل بالتكرار المحدد
    try:
        for i in range(cfg.get("count", 0)):
            if not context.user_data.get("active", True):
                break
            try:
                if cfg.get("attachments"):
                    await client.send_message(
                        contact, 
                        cfg.get("message", ""), 
                        file=cfg["attachments"]
                    )
                else:
                    await client.send_message(
                        contact, 
                        cfg.get("message", "")
                    )
                cfg["progress_sent"] += 1
            except Exception as e:
                cfg["progress_failed"] += 1
                logging.error(f"فشل الإرسال: {str(e)}")
            
            # الانتظار بين كل إرسال وآخر
            if i < cfg.get("count", 0) - 1:
                await asyncio.sleep(cfg.get("delay", 0))
    finally:
        # إعادة تعيين إعدادات البروكسي وقطع الاتصال
        try:
            socks.set_default_proxy()
            import socket as original_socket
            socket.socket = original_socket.socket
        except:
            pass
        try:
            await client.disconnect()
        except:
            pass

# --- دوال مساعدة ---
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إلغاء العملية الحالية والعودة للقائمة الرئيسية"""
    context.user_data.clear()
    if hasattr(update, 'message'):
        await update.message.reply_text("تم الإلغاء.")
    else:
        await update.callback_query.message.reply_text("تم الإلغاء.")
    return ConversationHandler.END

# --- تسجيل ConversationHandler الخاص بالدعم الخاص ---
def register_support_handlers(app):
    support_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_special_support, pattern=r'^special_support$'),
        ],
        states={
            SELECT_SUPPORT_TYPE: [
                CallbackQueryHandler(select_support_type, pattern=r'^special_support_\d+$')
            ],
            ENTER_SUPPORT_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_support_message)
            ],
            GET_SUPPORT_ATTACHMENTS: [
                MessageHandler(filters.Document.ALL | filters.PHOTO, get_support_attachments),
                CallbackQueryHandler(next_step_callback, pattern=r'^next$')
            ],
            ENTER_SUPPORT_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_support_count)
            ],
            ENTER_SUPPORT_DELAY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_support_delay)
            ],
            CONFIRM_SUPPORT: [
                CallbackQueryHandler(confirm_support_callback, pattern=r'^support_send$')
            ],
            SUPPORT_PROGRESS: [
                CallbackQueryHandler(cancel, pattern=r'^cancel$')
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel, pattern=r'^cancel$'),
            CommandHandler('cancel', cancel)
        ],
        per_user=True
    )
    app.add_handler(support_conv)