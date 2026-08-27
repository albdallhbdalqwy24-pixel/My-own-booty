# DrKhayal/Email/email_reports.py - نسخة مصححة بالكامل

import os
import json
import logging
import re
import smtplib
import asyncio
import traceback
from threading import Thread, Lock, Event
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from time import sleep
import mimetypes
from email.utils import make_msgid, formatdate
import uuid

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CommandHandler,
)

# --- استيراد الإعدادات من ملف config.py الرئيسي ---
try:
    from config import OWNER_ID
except ImportError:
    logging.error("خطأ: لا يمكن استيراد OWNER_ID من config.py.")
    OWNER_ID = 0

# إعداد بريد المالك للاختبار
OWNER_EMAIL = "test@example.com"  # يجب تحديث هذا ببريد المالك الفعلي

# --- تعريف الثوابت والمتغيرات الخاصة بوحدة الإيميل ---
logger = logging.getLogger(__name__)

# إيفنت عام لإلغاء مهام الإرسال
EMAIL_CANCEL_EVENT = Event()

# تحديد المسارات بناءً على موقع الملف الحالي
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
EMAILS_DIR = os.path.join(CURRENT_DIR, '..', 'emails_data')
TEMP_DIR = os.path.join(CURRENT_DIR, '..', 'temp_attachments')
os.makedirs(EMAILS_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# دالة للحصول على مسار ملف الإيميلات الخاص بمستخدم معين
def get_user_emails_file(user_id):
    return os.path.join(EMAILS_DIR, f'emails_{user_id}.json')

FILE_LOCK = Lock()
EMAIL_REGEX = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'

# -------------- تهيئة التخزين --------------
def initialize_storage(user_id):
    """تهيئة ملف التخزين الخاص بمستخدم معين"""
    try:
        emails_file = get_user_emails_file(user_id)
        with FILE_LOCK:
            if not os.path.exists(emails_file):
                with open(emails_file, 'w', encoding='utf-8') as f:
                    json.dump([], f)
                os.chmod(emails_file, 0o666)
                logger.info(f"تم إنشاء ملف جديد للمستخدم {user_id}: {emails_file}")
    except Exception:
        logger.critical(f"فشل تهيئة التخزين للمستخدم {user_id}: {traceback.format_exc()}")
        raise

# ------------ حالات المحادثة ------------
EMAIL_MENU = 1
GET_NUMBER = 2
GET_EMAILS = 3
GET_SUBJECT = 4
GET_BODY = 5
GET_ATTACHMENTS = 6
GET_DELAY = 7
CONFIRM_SEND = 8
MANAGE_EMAILS_MENU = 9
ADD_EMAILS = 10
DELETE_EMAIL = 11
EMAIL_DASHBOARD = 12
GET_SUPPORT_EMAIL = 13
SHOW_EMAILS = 12
TEST_EMAIL = 13
EMAIL_DASHBOARD = 14  # حالة لوحة التحكم الجديدة

# -------------- دوال مساعدة --------------
def load_email_accounts(user_id):
    """تحميل حسابات الإيميل الخاصة بمستخدم معين"""
    try:
        initialize_storage(user_id)  # التأكد من وجود الملف
        emails_file = get_user_emails_file(user_id)
        with FILE_LOCK, open(emails_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"فشل تحميل الإيميلات للمستخدم {user_id}: {e}")
        return []

def save_email_accounts(accounts, user_id):
    """حفظ حسابات الإيميل الخاصة بمستخدم معين"""
    try:
        initialize_storage(user_id)  # التأكد من وجود الملف
        emails_file = get_user_emails_file(user_id)
        with FILE_LOCK, open(emails_file, 'w', encoding='utf-8') as f:
            json.dump(accounts, f, indent=2, ensure_ascii=False)
        os.chmod(emails_file, 0o666)
        return True
    except Exception as e:
        logger.error(f"فشل حفظ الإيميلات للمستخدم {user_id}: {e}")
        return False

def is_authorized(user_id):
    # السماح لأي مستخدم بالاستخدام
    return True

async def unauthorized_response(update: Update):
    # هذه الدالة قد لا تستخدم الآن
    pass

# -------------- فئة عميل SMTP --------------
class SMTPClient:
    def __init__(self, email, password, targets, count, subject, body, attachments, delay, cancel_event: Event):
        self.email = email
        self.password = password
        self.targets = targets
        self.count = count
        self.subject = subject
        self.body = body
        self.attachments = attachments or []
        self.delay = delay
        self.cancel_event = cancel_event

    def verify(self):
        try:
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(self.email, self.password)
            server.quit()
            return True
        except Exception as e:
            logger.error(f"فشل التحقق من SMTP: {e}")
            return False

    def send_emails(self):
        try:
            if self.cancel_event.is_set():
                logger.info("تم إلغاء عملية الإرسال")
                return False
            
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(self.email, self.password)
            
            sent_count = 0
            for i in range(self.count):
                if self.cancel_event.is_set():
                    break
                
                for target in self.targets:
                    if self.cancel_event.is_set():
                        break
                    
                    try:
                        msg = MIMEMultipart()
                        msg['From'] = self.email
                        msg['To'] = target
                        subject_suffix = f" [{i+1}]" if self.count > 1 else ""
                        msg['Subject'] = f"{self.subject}{subject_suffix}"
                        msg['Message-ID'] = make_msgid()
                        msg['Date'] = formatdate(localtime=True)
                        
                        # إضافة نص الرسالة
                        msg.attach(MIMEText(self.body or '', 'plain', 'utf-8'))
                        
                        # إضافة المرفقات
                        for path in self.attachments:
                            if self.cancel_event.is_set():
                                break
                            if not os.path.exists(path):
                                continue
                                
                            ctype, encoding = mimetypes.guess_type(path)
                            if ctype is None or encoding is not None:
                                ctype = 'application/octet-stream'
                            
                            maintype, subtype = ctype.split('/', 1)
                            try:
                                if maintype == 'text':
                                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                                        part = MIMEText(f.read(), _subtype=subtype, _charset='utf-8')
                                elif maintype == 'image':
                                    from email.mime.image import MIMEImage
                                    with open(path, 'rb') as f:
                                        part = MIMEImage(f.read(), _subtype=subtype)
                                elif maintype == 'audio':
                                    from email.mime.audio import MIMEAudio
                                    with open(path, 'rb') as f:
                                        part = MIMEAudio(f.read(), _subtype=subtype)
                                else:
                                    with open(path, 'rb') as f:
                                        part = MIMEBase(maintype, subtype)
                                        part.set_payload(f.read())
                                        encoders.encode_base64(part)
                            except Exception:
                                with open(path, 'rb') as f:
                                    part = MIMEBase('application', 'octet-stream')
                                    part.set_payload(f.read())
                                    encoders.encode_base64(part)
                            
                            filename = os.path.basename(path)
                            part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
                            msg.attach(part)
                        
                        # إرسال الرسالة
                        server.sendmail(self.email, [target], msg.as_string())
                        sent_count += 1
                        logger.info(f"تم إرسال رسالة #{sent_count} من {self.email} إلى {target}")
                        
                        # تأخير بين الرسائل
                        if self.delay and self.delay > 0:
                            for _ in range(int(self.delay * 10)):
                                if self.cancel_event.is_set():
                                    break
                                sleep(0.1)
                                
                    except Exception as e:
                        logger.error(f"فشل إرسال رسالة: {e}")
                        continue
                
                if self.cancel_event.is_set():
                    break
            
            server.quit()
            logger.info(f"اكتمل إرسال {sent_count} رسالة من {self.email}")
            return sent_count > 0
            
        except Exception as e:
            logger.error(f"فشل إرسال SMTP: {e}")
            return False
        finally:
            # تنظيف المرفقات المؤقتة
            for path in self.attachments:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except Exception as e:
                    logger.error(f"فشل حذف المرفق {path}: {e}")

# =========== دوال القائمة الرئيسية للإيميل ===========
async def start_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء قسم الإيميل - القائمة الرئيسية"""
    query = update.callback_query
    await query.answer()
    
    if not is_authorized(query.from_user.id):
        await query.edit_message_text("❌ ليس مصرحاً لك باستخدام هذا الأمر.")
        return ConversationHandler.END
    
    # تنظيف بيانات المستخدم
    context.user_data.clear()
    
    keyboard = [
        [InlineKeyboardButton('📤 بدء الرفع الخارجي', callback_data='email_external_upload')],
        [InlineKeyboardButton('📧 إدارة الإيميلات', callback_data='email_manage_emails')],
        [InlineKeyboardButton('🔙 العودة للقائمة الرئيسية', callback_data='back_to_main_menu')]
    ]
    
    await query.edit_message_text(
        '📧 <b>قسم بلاغات ايميل</b>\n\n'
        'اختر الإجراء الذي تريد تنفيذه:',
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return EMAIL_MENU

async def back_to_email_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """العودة لقائمة الإيميل الرئيسية"""
    query = update.callback_query
    await query.answer()
    return await start_email(update, context)

# =========== دوال الرفع الخارجي ===========
async def external_upload_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء عملية الرفع الخارجي - عرض لوحة التحكم"""
    query = update.callback_query
    await query.answer()
    
    if not is_authorized(query.from_user.id):
        await query.edit_message_text("❌ ليس مصرحاً لك باستخدام هذا الأمر.")
        return ConversationHandler.END
    
    # تهيئة البيانات
    if 'email_dashboard_data' not in context.user_data:
        context.user_data['email_dashboard_data'] = {
            'count': 1,
            'targets': [],
            'subject': 'بلاغ',
            'body': '',
            'attachments': [],
            'delay': 0
        }
    
    return await email_dashboard(update, context)

async def email_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """عرض لوحة تحكم البلاغات الخارجية"""
    data = context.user_data.get('email_dashboard_data', {})
    
    targets_count = len(data.get('targets', []))
    atts_count = len(data.get('attachments', []))
    subject_val = data.get('subject', 'غير محدد')
    body_val = "موجود" if data.get('body') else "غير محدد"
    
    text = (
        f"📊 <b>لوحة تحكم البلاغات الخارجية</b>\n\n"
        f"🎯 <b>المستهدفون (بريد الدعم):</b> {targets_count}\n"
        f"📝 <b>الموضوع:</b> {subject_val}\n"
        f"📄 <b>الكليشة:</b> {body_val}\n"
        f"📎 <b>المرفقات:</b> {atts_count}\n"
        f"🔢 <b>العدد لكل هدف:</b> {data.get('count', 1)}\n"
        f"⏱ <b>الفاصل الزمني:</b> {data.get('delay', 0)} ثانية\n"
        f"📧 <b>الحسابات المرسلة:</b> {len(load_email_accounts(update.effective_user.id))}\n\n"
        f"👇 <b>اختر الإجراء المطلوب:</b>"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("📝 إضافة كليشة", callback_data="dash_set_body"),
            InlineKeyboardButton("🏷 إضافة موضوع", callback_data="dash_set_subject")
        ],
        [
            InlineKeyboardButton("⏱ تحديد الوقت", callback_data="dash_set_delay"),
            InlineKeyboardButton("🔢 عدد البلاغات", callback_data="dash_set_count")
        ],
        [
            InlineKeyboardButton("📎 إضافة مرفق", callback_data="dash_set_att"),
            InlineKeyboardButton("🎯 بريد الدعم", callback_data="dash_set_target")
        ],
        [
            InlineKeyboardButton("ℹ️ عرض المعلومات", callback_data="dash_show_info")
        ],
        [
            InlineKeyboardButton("🚀 بدأ البلاغ", callback_data="dash_start_sending")
        ],
        [
            InlineKeyboardButton("🔙 رجوع", callback_data="back_to_email_menu")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode='HTML', reply_markup=reply_markup)
    elif update.message:
        await update.message.reply_text(text, parse_mode='HTML', reply_markup=reply_markup)
        
    return EMAIL_DASHBOARD

async def dash_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """معالجة أزرار لوحة التحكم"""
    query = update.callback_query
    await query.answer()
    data = query.data
    
    keyboard_back = [[InlineKeyboardButton("🔙 إلغاء", callback_data="back_to_dashboard")]]
    
    if data == "dash_set_body":
        await query.edit_message_text("📝 <b>أرسل نص الكليشة الآن:</b>", parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard_back))
        return GET_BODY
        
    elif data == "dash_set_subject":
        await query.edit_message_text("🏷 <b>أرسل عنوان الموضوع:</b>", parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard_back))
        return GET_SUBJECT
        
    elif data == "dash_set_delay":
        await query.edit_message_text("⏱ <b>أرسل الفاصل الزمني (بالثواني):</b>", parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard_back))
        return GET_DELAY
        
    elif data == "dash_set_count":
        await query.edit_message_text("🔢 <b>أرسل عدد البلاغات:</b>", parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard_back))
        return GET_NUMBER
        
    elif data == "dash_set_att":
        await query.edit_message_text("📎 <b>أرسل المرفق (صورة/ملف):</b>", parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard_back))
        return GET_ATTACHMENTS
        
    elif data == "dash_set_target":
        await query.edit_message_text("🎯 <b>أرسل بريد الدعم (يمكن فواصل):</b>", parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard_back))
        return GET_EMAILS
        
    elif data == "dash_show_info" or data == "back_to_dashboard":
        return await email_dashboard(update, context)
        
    elif data == "dash_start_sending":
        dash_data = context.user_data.get('email_dashboard_data', {})
        if not dash_data.get('targets') or not dash_data.get('subject'):
            await query.answer("⚠️ يجب تحديد الموضوع والمستهدفين!", show_alert=True)
            return EMAIL_DASHBOARD
            
        # نقل البيانات للمعالج الرئيسي
        context.user_data.update(dash_data)
        return await start_sending(update, context)
        
    return EMAIL_DASHBOARD

async def get_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """الحصول على عدد الرسائل"""
    try:
        text = update.message.text.strip()
        count = int(text)
        
        if count <= 0:
            await update.message.reply_text('❌ الرقم يجب أن يكون > 0')
            return GET_NUMBER
            
        context.user_data.setdefault('email_dashboard_data', {})['count'] = count
        return await email_dashboard(update, context)
        
    except ValueError:
        await update.message.reply_text('❌ أدخل رقماً صحيحاً')
        return GET_NUMBER

async def get_emails(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """الحصول على إيميلات المستفيدين"""
    text = update.message.text.strip()
    emails = [e.strip() for e in text.split(',')]
    valid = [e for e in emails if re.match(EMAIL_REGEX, e)]
    
    if not valid:
        await update.message.reply_text("❌ لم يتم العثور على إيميلات صالحة!")
        return GET_EMAILS
        
    context.user_data.setdefault('email_dashboard_data', {})['targets'] = valid
    return await email_dashboard(update, context)

async def get_subject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """الحصول على عنوان الرسالة"""
    subject = update.message.text.strip()
    if not subject:
        return GET_SUBJECT
        
    context.user_data.setdefault('email_dashboard_data', {})['subject'] = subject
    return await email_dashboard(update, context)

async def get_body(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """الحصول على نص الرسالة"""
    text = update.message.text
    if text == '/skip': text = ''
    
    context.user_data.setdefault('email_dashboard_data', {})['body'] = text
    return await email_dashboard(update, context)

async def get_attachments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """الحصول على المرفقات"""
    # تهيئة القائمة في البيانات الجديدة وتأكد أنها قائمة
    dash_data = context.user_data.setdefault('email_dashboard_data', {})
    if 'attachments' not in dash_data:
        dash_data['attachments'] = []

    if update.message.text == '/skip':
        return await email_dashboard(update, context)
    
    try:
        file = None
        filename = None
        
        if update.message.document:
            file = await update.message.document.get_file()
            filename = update.message.document.file_name or f"doc_{update.message.document.file_unique_id}"
        elif update.message.photo:
            photo = update.message.photo[-1]
            file = await photo.get_file()
            filename = f"photo_{photo.file_unique_id}.jpg"
        elif update.message.video:
            file = await update.message.video.get_file()
            filename = update.message.video.file_name or f"vid_{update.message.video.file_unique_id}.mp4"
        elif update.message.audio:
            file = await update.message.audio.get_file()
            filename = update.message.audio.file_name or f"aud_{update.message.audio.file_unique_id}.mp3"
        elif update.message.voice:
            file = await update.message.voice.get_file()
            filename = f"voice_{update.message.voice.file_unique_id}.ogg"
            
        if file:
            filepath = os.path.join(TEMP_DIR, filename)
            await file.download_to_drive(filepath)
            dash_data['attachments'].append(filepath)
            
            await update.message.reply_text(f'✅ تم إضافة المرفق: {filename}')
            return await email_dashboard(update, context)
            
        return await email_dashboard(update, context)
        
    except Exception as e:
        logger.error(f"Attachment error: {e}")
        return await email_dashboard(update, context)

async def get_delay(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """الحصول على الفاصل الزمني"""
    try:
        delay = float(update.message.text.strip())
        if delay < 0:
            await update.message.reply_text("❌ يجب أن يكون الرقم موجباً")
            return GET_DELAY
            
        context.user_data.setdefault('email_dashboard_data', {})['delay'] = delay
        return await email_dashboard(update, context)
        
    except ValueError:
        await update.message.reply_text("❌ رقم غير صالح")
        return GET_DELAY

class JobStatus:
    def __init__(self):
        self.total_emails = 0
        self.sent_count = 0
        self.failed_count = 0
        self.remaining = 0
        self.is_running = True
        self.lock = Lock()

    def update(self, sent, failed):
        with self.lock:
            self.sent_count += sent
            self.failed_count += failed
            self.remaining = self.total_emails - (self.sent_count + self.failed_count)

async def monitor_sending_progress(msg, job_status, bg_thread, targets, subject, attachments, email_accounts_count, context):
    """مراقبة عملية الإرسال وتحديث الواجهة"""
    try:
        while bg_thread.is_alive() or job_status.is_running:
            # فحص الإلغاء كل 0.5 ثانية (4 مرات * 0.5 = 2.0 ثانية تحديث)
            for _ in range(4):
                if EMAIL_CANCEL_EVENT.is_set():
                    break
                await asyncio.sleep(0.5)
            
            if EMAIL_CANCEL_EVENT.is_set():
                break
                
            status_keyboard = [
                [
                    InlineKeyboardButton(f"✅: {job_status.sent_count}", callback_data="noop"),
                    InlineKeyboardButton(f"❌: {job_status.failed_count}", callback_data="noop")
                ],
                [
                    InlineKeyboardButton(f"⏳: {job_status.remaining}", callback_data="noop")
                ],
                [
                    InlineKeyboardButton("⛔ إيقاف فوراً", callback_data="stop_sending_now")
                ]
            ]
            
            try:
                await msg.edit_text(
                    f"🚀 <b>جاري إرسال البلاغات...</b>\n\n"
                    f"📊 <b>تقرير حي:</b>\n"
                    f"• الحسابات المرسلة: {email_accounts_count}\n"
                    f"• المستلمين: {len(targets)}\n"
                    f"• الموضوع: {subject[:20]}...\n",
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(status_keyboard)
                )
            except Exception:
                pass
            
            await asyncio.sleep(2.0)

        # التأكد من انتهاء الخيط
        if bg_thread.is_alive():
            bg_thread.join(timeout=1.0)
        
        # التنظيف النهائي
        for attachment in attachments:
            if os.path.exists(attachment):
                try: os.remove(attachment)
                except: pass
                
        final_status = "✅ تمت العملية" if not EMAIL_CANCEL_EVENT.is_set() else "⛔ تم الإيقاف يدوياً"
        
        final_keyboard = [
            [InlineKeyboardButton('📤 حملة جديدة', callback_data='email_external_upload')],
            [InlineKeyboardButton('🔙 القائمة الرئيسية للإيميل', callback_data='back_to_email_menu')]
        ]
        
        try:
            await msg.edit_text(
                f"{final_status}\n\n"
                f"📊 <b>التقرير النهائي:</b>\n"
                f"✅ تم بنجاح: {job_status.sent_count}\n"
                f"❌ فشل: {job_status.failed_count}\n"
                f"📉 المجموع: {job_status.total_emails}",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(final_keyboard)
            )
        except Exception:
            pass

        context.user_data.clear()
        
    except Exception as e:
        logger.error(f"Error in monitor: {e}")

async def start_sending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء عملية الإرسال - نظام محسّن مع تحديث مباشر"""
    query = update.callback_query
    await query.answer()
    
    # جمع البيانات
    count = context.user_data.get('count', 0)
    targets = context.user_data.get('targets', [])
    subject = context.user_data.get('subject', '')
    body = context.user_data.get('body', '')
    attachments = context.user_data.get('attachments', [])
    delay = context.user_data.get('delay', 0)
    
    if not count or not targets:
        await query.edit_message_text(
            '❌ بيانات ناقصة. يرجى البدء من جديد.',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🔙 رجوع', callback_data='back_to_email_menu')]])
        )
        return EMAIL_MENU
    
    # تحميل حسابات الإيميل
    email_accounts = load_email_accounts(update.effective_user.id)
    
    if not email_accounts:
        await query.edit_message_text(
            '❌ لا توجد حسابات إيميل مخزنة.\n'
            'يرجى إضافة حسابات من قسم "إدارة الإيميلات" أولاً.',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🔙 رجوع', callback_data='back_to_email_menu')]])
        )
        return EMAIL_MENU
    
    # تحضير كائن الحالة
    job_status = JobStatus()
    job_status.total_emails = count * len(targets) * len(email_accounts)
    job_status.remaining = job_status.total_emails
    
    # واجهة التحديث المباشر
    msg = await query.edit_message_text(
        f'🚀 <b>بدء عملية الإرسال...</b>\n\n'
        f'• جاري تهيئة {len(email_accounts)} حسابات...\n'
        f'• الهدف: {len(targets)} مستلم\n'
        f'• الإجمالي: {job_status.total_emails} رسالة',
        parse_mode='HTML'
    )
    
    EMAIL_CANCEL_EVENT.clear()
    
    # دالة العمل في الخلفية (Thread)
    def sending_task_thread(status_obj: JobStatus):
        try:
            for account in email_accounts:
                if EMAIL_CANCEL_EVENT.is_set():
                    break
                    
                client = SMTPClient(
                    email=account['email'],
                    password=account['password'],
                    targets=targets,
                    count=count,
                    subject=subject,
                    body=body,
                    attachments=attachments.copy(),
                    delay=delay,
                    cancel_event=EMAIL_CANCEL_EVENT
                )
                
                # إرسال فعلي وتحديث الحالة
                try:
                    server = smtplib.SMTP('smtp.gmail.com', 587)
                    server.starttls()
                    server.login(client.email, client.password)
                    
                    for i in range(client.count):
                        if EMAIL_CANCEL_EVENT.is_set():
                            break
                        
                        for target in client.targets:
                            if EMAIL_CANCEL_EVENT.is_set():
                                break
                            
                            try:
                                msg_obj = MIMEMultipart()
                                msg_obj['From'] = client.email
                                msg_obj['To'] = target
                                subject_suffix = f" [{i+1}]" if client.count > 1 else ""
                                msg_obj['Subject'] = f"{client.subject}{subject_suffix}"
                                msg_obj.attach(MIMEText(client.body or '', 'plain', 'utf-8'))
                                
                                # المرفقات
                                for path in client.attachments:
                                    if os.path.exists(path):
                                        ctype, encoding = mimetypes.guess_type(path)
                                        if ctype is None or encoding is not None:
                                            ctype = 'application/octet-stream'
                                        maintype, subtype = ctype.split('/', 1)
                                        with open(path, 'rb') as f:
                                            part = MIMEBase(maintype, subtype)
                                            part.set_payload(f.read())
                                            encoders.encode_base64(part)
                                            part.add_header('Content-Disposition', f'attachment; filename="{os.path.basename(path)}"')
                                            msg_obj.attach(part)

                                server.sendmail(client.email, [target], msg_obj.as_string())
                                status_obj.update(1, 0)
                                
                                if delay > 0:
                                    # انتظار مجزأ للسماح بالإيقاف الفوري
                                    steps = int(delay * 10)
                                    for _ in range(steps):
                                        if EMAIL_CANCEL_EVENT.is_set():
                                            break
                                        sleep(0.1)
                                    # ما تبقى من الوقت إذا كان الكسر صغيراً
                                    remaining_sleep = delay - (steps * 0.1)
                                    if remaining_sleep > 0 and not EMAIL_CANCEL_EVENT.is_set():
                                        sleep(remaining_sleep)
                                    
                            except Exception as e:
                                logger.error(f"فشل إرسال رسالة: {e}")
                                status_obj.update(0, 1) # فشل
                    
                    server.quit()
                    
                except Exception as e:
                    logger.error(f"Fails account {client.email}: {e}")
                    # في حال فشل الحساب بالكامل، نحسب جميع رسائله كفشل
                    remaining_for_account = count * len(targets)
                    status_obj.update(0, remaining_for_account)

        except Exception as e:
            logger.error(f"Critical sending error: {e}")
        finally:
            status_obj.is_running = False

    # بدء الخيط في الخلفية
    bg_thread = Thread(target=sending_task_thread, args=(job_status,))
    bg_thread.start()
    
    # بدء مهمة المراقبة في الخلفية (Async Task) لتجنب تجميد البوت
    context.application.create_task(
        monitor_sending_progress(
            msg, job_status, bg_thread, targets, subject, attachments, len(email_accounts), context
        )
    )
    
    return CONFIRM_SEND

async def stop_sending_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """معالج زر الإيقاف الفوري"""
    query = update.callback_query
    await query.answer("جاري الإيقاف...", show_alert=True)
    EMAIL_CANCEL_EVENT.set()
    return CONFIRM_SEND # البقاء في نفس الحالة حتى تكتمل حلقة start_sending

    
    if successful > 0:
        result_text += '🎉 تم إرسال الرسائل بنجاح!'
    else:
        result_text += '❌ فشل جميع محاولات الإرسال. تحقق من حسابات الإيميل.'
    
    keyboard = [
        [InlineKeyboardButton('📤 رفع خارجي جديد', callback_data='email_external_upload')],
        [InlineKeyboardButton('📧 القائمة الرئيسية للإيميل', callback_data='back_to_email_menu')],
        [InlineKeyboardButton('🔙 القائمة الرئيسية', callback_data='back_to_main_menu')]
    ]
    
    await query.edit_message_text(
        result_text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # تنظيف البيانات
    context.user_data.clear()
    return EMAIL_MENU

# =========== دوال إدارة الإيميلات ===========
async def manage_emails(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """عرض قائمة إدارة الإيميلات"""
    query = update.callback_query
    await query.answer()
    
    if not is_authorized(query.from_user.id):
        await query.edit_message_text("❌ ليس مصرحاً لك باستخدام هذا الأمر.")
        return ConversationHandler.END
    
    keyboard = [
        [InlineKeyboardButton('📋 عرض الإيميلات', callback_data='show_emails')],
        [InlineKeyboardButton('➕ إضافة إيميلات', callback_data='add_emails')],
        [InlineKeyboardButton('🗑️ حذف إيميل', callback_data='delete_email')],
        [InlineKeyboardButton('🔙 رجوع', callback_data='back_to_email_menu')]
    ]
    
    await query.edit_message_text(
        '📊 <b>إدارة الإيميلات</b>\n\n'
        'اختر الإجراء الذي تريد تنفيذه:',
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return MANAGE_EMAILS_MENU

async def show_emails(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """عرض قائمة الإيميلات المخزنة"""
    query = update.callback_query
    await query.answer()
    
    accounts = load_email_accounts(update.effective_user.id)
    
    if not accounts:
        text = '📭 <b>لا توجد إيميلات مخزنة</b>\n\n'
        text += 'استخدم "إضافة إيميلات" لإضافة حسابات جديدة.'
    else:
        text = f'📧 <b>الإيميلات المخزنة ({len(accounts)})</b>\n\n'
        for i, account in enumerate(accounts, 1):
            email = account['email']
            # إخفاء جزء من كلمة المرور
            password_preview = account['password'][:3] + '***' if len(account['password']) > 3 else '***'
            text += f'{i}. {email}\n   كلمة المرور: {password_preview}\n'
    
    keyboard = [[InlineKeyboardButton('🔙 رجوع', callback_data='email_manage_emails')]]
    
    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return MANAGE_EMAILS_MENU

async def add_emails(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء إضافة إيميلات جديدة"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        '➕ <b>إضافة إيميلات جديدة</b>\n\n'
        'أرسل الإيميلات وكلمات المرور بالتنسيق:\n\n'
        '<code>email@example.com:password123</code>\n'
        '<code>user@gmail.com:mypassword</code>\n\n'
        'ملاحظات:\n'
        '• كل إيميل وكلمة مرور في سطر منفصل\n'
        '• النقطتان الرأسيتان (:) تفصل بين الإيميل وكلمة المرور\n'
        '• بدون مسافات حول النقطتين\n\n'
        'يمكنك إرسال إيميل واحد أو عدة إيميلات دفعة واحدة.',
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🔙 رجوع', callback_data='email_manage_emails')]])
    )
    return ADD_EMAILS

async def process_add_emails(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """معالجة الإيميلات المضافة"""
    try:
        text = update.message.text.strip()
        
        # التحقق من زر الرجوع إذا كان المستخدم أرسل نصاً بدلاً من الضغط
        if text.lower() == 'رجوع':
            return await manage_emails(update, context)
        
        lines = text.splitlines()
        accounts = load_email_accounts(update.effective_user.id)
        existing_emails = {acc['email'].lower() for acc in accounts}
        
        added = 0
        duplicates = 0
        invalid = 0
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # التغيير هنا: استخدام : بدلاً من ,
            if ':' not in line:
                invalid += 1
                continue
            
            try:
                # تقسيم بناءً على :
                email, password = line.split(':', 1)
                email = email.strip()
                password = password.strip()
                
                if not re.match(EMAIL_REGEX, email):
                    invalid += 1
                    continue
                
                if email.lower() in existing_emails:
                    duplicates += 1
                    continue
                
                accounts.append({'email': email, 'password': password})
                existing_emails.add(email.lower())
                added += 1
                
            except Exception:
                invalid += 1
                continue
        
        if added > 0:
            if save_email_accounts(accounts, update.effective_user.id):
                save_status = '✅'
            else:
                save_status = '⚠️'
        else:
            save_status = '❌'
        
        response = f'{save_status} <b>نتيجة الإضافة</b>\n\n'
        response += f'• تمت إضافة: {added} إيميل\n'
        response += f'• مكرر (تم تخطيه): {duplicates}\n'
        response += f'• غير صالح (تم تخطيه): {invalid}\n'
        
        if added == 0:
            response += '\n❌ لم تتم إضافة أي إيميلات جديدة. تأكد من التنسيق (email:password).'

        response += '\n\n📥 <b>أرسل المزيد من الإيميلات لإضافتها</b>\n' \
                    'أو اضغط "رجوع" للعودة.'
        
        await update.message.reply_text(
            response,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🔙 رجوع', callback_data='email_manage_emails')]])
        )
        
        return ADD_EMAILS
        
    except Exception as e:
        logger.error(f"خطأ في process_add_emails: {e}")
        await update.message.reply_text(
            f'❌ حدث خطأ أثناء معالجة الإيميلات: {str(e)}',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🔙 رجوع', callback_data='email_manage_emails')]])
        )
        return ADD_EMAILS

async def delete_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء عملية حذف إيميل"""
    query = update.callback_query
    await query.answer()
    
    accounts = load_email_accounts(update.effective_user.id)
    
    if not accounts:
        await query.edit_message_text(
            '📭 <b>لا توجد إيميلات مخزنة</b>\n\n'
            'لا يمكن حذف إيميلات حيث لا توجد إيميلات مخزنة.',
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🔙 رجوع', callback_data='email_manage_emails')]])
        )
        return MANAGE_EMAILS_MENU
    
    # إنشاء قائمة بأزرار الإيميلات
    keyboard = []
    for account in accounts:
        keyboard.append([InlineKeyboardButton(account['email'], callback_data=f'delete_{account["email"]}')])
    
    keyboard.append([InlineKeyboardButton('🔙 رجوع', callback_data='email_manage_emails')])
    
    await query.edit_message_text(
        '🗑️ <b>حذف إيميل</b>\n\n'
        'اختر الإيميل الذي تريد حذفه:',
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return DELETE_EMAIL

async def process_delete_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """معالجة حذف الإيميل المحدد"""
    query = update.callback_query
    await query.answer()
    
    email_to_delete = query.data.replace('delete_', '')
    
    accounts = load_email_accounts(update.effective_user.id)
    new_accounts = [acc for acc in accounts if acc['email'] != email_to_delete]
    
    if len(new_accounts) < len(accounts):
        if save_email_accounts(new_accounts, update.effective_user.id):
            await query.edit_message_text(
                f'✅ تم حذف الإيميل: {email_to_delete}\n\n'
                f'• الإيميلات المتبقية: {len(new_accounts)}',
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🔙 رجوع', callback_data='email_manage_emails')]])
            )
        else:
            await query.edit_message_text(
                f'❌ فشل حفظ التغييرات بعد الحذف.\n'
                f'الإيميل: {email_to_delete}',
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🔙 رجوع', callback_data='email_manage_emails')]])
            )
    else:
        await query.edit_message_text(
            f'⚠️ الإيميل غير موجود: {email_to_delete}',
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🔙 رجوع', callback_data='email_manage_emails')]])
        )
    
    return MANAGE_EMAILS_MENU

# =========== دوال إلغاء وإرجاع ===========
async def cancel_email_operation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إلغاء العملية والعودة للقائمة الرئيسية للإيميل"""
    # تنظيف المرفقات المؤقتة
    if 'attachments' in context.user_data:
        for attachment in context.user_data['attachments']:
            try:
                if os.path.exists(attachment):
                    os.remove(attachment)
            except Exception as e:
                logger.error(f"فشل حذف المرفق {attachment}: {e}")
    
    # تنظيف البيانات
    context.user_data.clear()
    
    # إلغاء أي عملية إرسال جارية
    EMAIL_CANCEL_EVENT.set()
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            '❌ تم إلغاء العملية.',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🔙 القائمة الرئيسية للإيميل', callback_data='email_reports')]])
        )
    elif update.message:
        await update.message.reply_text(
            '❌ تم إلغاء العملية.',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🔙 القائمة الرئيسية للإيميل', callback_data='email_reports')]])
        )
    
    return ConversationHandler.END

# =========== معالج المحادثة الرئيسي ===========
email_conv_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(start_email, pattern='^email_reports$'),
    ],
    states={
        EMAIL_MENU: [
            CallbackQueryHandler(external_upload_callback, pattern='^email_external_upload$'),
            CallbackQueryHandler(manage_emails, pattern='^email_manage_emails$'),
            CallbackQueryHandler(back_to_email_menu, pattern='^back_to_email_menu$'),
            CallbackQueryHandler(cancel_email_operation, pattern='^cancel$'),
        ],
        
        # حالة لوحة التحكم
        EMAIL_DASHBOARD: [
            CallbackQueryHandler(dash_handler),
        ],
        
        # حالات الإدخال للوحة التحكم
        GET_NUMBER: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_number),
            CallbackQueryHandler(email_dashboard, pattern='^back_to_dashboard$'),
            CallbackQueryHandler(back_to_email_menu, pattern='^back_to_email_menu$'),
            CallbackQueryHandler(cancel_email_operation, pattern='^cancel$'),
        ],
        GET_EMAILS: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_emails),
            CallbackQueryHandler(email_dashboard, pattern='^back_to_dashboard$'),
            CallbackQueryHandler(back_to_email_menu, pattern='^back_to_email_menu$'),
            CallbackQueryHandler(cancel_email_operation, pattern='^cancel$'),
        ],
        GET_SUBJECT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_subject),
            CallbackQueryHandler(email_dashboard, pattern='^back_to_dashboard$'),
            CallbackQueryHandler(back_to_email_menu, pattern='^back_to_email_menu$'),
            CallbackQueryHandler(cancel_email_operation, pattern='^cancel$'),
        ],
        GET_BODY: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_body),
            CommandHandler('skip', get_body),
            CallbackQueryHandler(email_dashboard, pattern='^back_to_dashboard$'),
            CallbackQueryHandler(back_to_email_menu, pattern='^back_to_email_menu$'),
            CallbackQueryHandler(cancel_email_operation, pattern='^cancel$'),
        ],
        GET_ATTACHMENTS: [
            MessageHandler(
                filters.Document.ALL | filters.PHOTO | filters.VIDEO | 
                filters.AUDIO | filters.VOICE | filters.ANIMATION | 
                filters.VIDEO_NOTE | filters.Sticker.ALL,
                get_attachments
            ),
            CommandHandler('skip', get_attachments),
            CallbackQueryHandler(email_dashboard, pattern='^back_to_dashboard$'),
            CallbackQueryHandler(back_to_email_menu, pattern='^back_to_email_menu$'),
            CallbackQueryHandler(cancel_email_operation, pattern='^cancel$'),
        ],
        GET_DELAY: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_delay),
            CallbackQueryHandler(email_dashboard, pattern='^back_to_dashboard$'),
            CallbackQueryHandler(back_to_email_menu, pattern='^back_to_email_menu$'),
            CallbackQueryHandler(cancel_email_operation, pattern='^cancel$'),
        ],
        CONFIRM_SEND: [
            CallbackQueryHandler(start_sending, pattern='^start_sending$'),
            CallbackQueryHandler(stop_sending_handler, pattern='^stop_sending_now$'), # handler for stop button
            CallbackQueryHandler(external_upload_callback, pattern='^email_external_upload$'),
            CallbackQueryHandler(back_to_email_menu, pattern='^back_to_email_menu$'),
            CallbackQueryHandler(email_dashboard, pattern='^back_to_dashboard$'), # Added just in case
            CallbackQueryHandler(cancel_email_operation, pattern='^cancel$'),
            CallbackQueryHandler(lambda u, c: None, pattern='^noop$'),
        ],
        
        # حالة إدارة الإيميلات
        MANAGE_EMAILS_MENU: [
            CallbackQueryHandler(show_emails, pattern='^show_emails$'),
            CallbackQueryHandler(add_emails, pattern='^add_emails$'),
            CallbackQueryHandler(delete_email, pattern='^delete_email$'),
            CallbackQueryHandler(manage_emails, pattern='^email_manage_emails$'),
            CallbackQueryHandler(back_to_email_menu, pattern='^back_to_email_menu$'),
            CallbackQueryHandler(cancel_email_operation, pattern='^cancel$'),
        ],
        ADD_EMAILS: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, process_add_emails),
            CallbackQueryHandler(manage_emails, pattern='^email_manage_emails$'),
            CallbackQueryHandler(back_to_email_menu, pattern='^back_to_email_menu$'),
            CallbackQueryHandler(cancel_email_operation, pattern='^cancel$'),
        ],
        DELETE_EMAIL: [
            CallbackQueryHandler(process_delete_email, pattern='^delete_'),
            CallbackQueryHandler(manage_emails, pattern='^email_manage_emails$'),
            CallbackQueryHandler(back_to_email_menu, pattern='^back_to_email_menu$'),
            CallbackQueryHandler(cancel_email_operation, pattern='^cancel$'),
        ],
    },
    fallbacks=[
        CommandHandler('cancel', cancel_email_operation),
        CallbackQueryHandler(cancel_email_operation, pattern='^cancel$'),
        CallbackQueryHandler(back_to_email_menu, pattern='^back_to_email_menu$'),
    ],
    per_user=True,
    per_chat=True,
    allow_reentry=True
)