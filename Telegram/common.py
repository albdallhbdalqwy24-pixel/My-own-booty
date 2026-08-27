# DrKhayal/Telegram/common.py

import asyncio
import sqlite3
import base64
import logging
import time
import random
import re
from urllib.parse import urlparse, parse_qs

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes, ConversationHandler

from telethon import TelegramClient, functions, types, utils
from telethon.errors import (
    AuthKeyDuplicatedError,
    FloodWaitError,
    PeerFloodError,
    SessionPasswordNeededError,
    RPCError  
)
# Removed MTProto proxy import - now using Socks5
from telethon.sessions import StringSession
from encryption import decrypt_session
from config import API_ID, API_HASH
from add import safe_db_query

logger = logging.getLogger(__name__)
# استيراد DB_PATH من config.py
try:
    from config import DB_PATH
except ImportError:
    DB_PATH = 'accounts.db'  # قيمة افتراضية

# استثناءات مخصصة
class TemporaryFailure(Exception):
    """فشل مؤقت يمكن إعادة المحاولة عليه"""
    pass

class SessionExpired(Exception):
    """انتهت صلاحية الجلسة"""
    pass

class PermanentFailure(Exception):
    """فشل دائم يتطلب تخطي الحساب"""
    pass
    
# --- الثوابت المشتركة ---
REPORT_TYPES = {
    2: ("رسائل مزعجة", types.InputReportReasonSpam()),
    3: ("إساءة أطفال", types.InputReportReasonChildAbuse()),
    4: ("محتوى جنسي", types.InputReportReasonPornography()),
    5: ("عنف", types.InputReportReasonViolence()),
    6: ("انتهاك خصوصية", types.InputReportReasonPersonalDetails()),
    7: ("مخدرات", types.InputReportReasonIllegalDrugs()),
    8: ("حساب مزيف", types.InputReportReasonFake()),
    9: ("حقوق النشر", types.InputReportReasonCopyright()),
    11: ("أخرى", types.InputReportReasonOther()),
}

# --- دوال مساعدة مشتركة محسنة ---

def parse_message_link(link: str) -> dict | None:
    """تحليل رابط رسالة تليجرام المحسن"""
    try:
        # النمط الأساسي: https://t.me/channel/123
        base_pattern = r"https?://t\.me/([a-zA-Z0-9_]+)/(\d+)"
        match = re.search(base_pattern, link)
        if match:
            return {
                "channel": match.group(1),
                "message_id": int(match.group(2))
            }
        
        # النمط مع المعرف الخاص: https://t.me/c/1234567890/123
        private_pattern = r"https?://t\.me/c/(\d+)/(\d+)"
        match = re.search(private_pattern, link)
        if match:
            return {
                "channel": int(match.group(1)),
                "message_id": int(match.group(2))
            }
        
        # دعم الروابط بدون بروتوكول
        no_protocol_pattern = r"t\.me/([a-zA-Z0-9_]+)/(\d+)"
        match = re.search(no_protocol_pattern, link)
        if match:
            return {
                "channel": match.group(1),
                "message_id": int(match.group(2))
            }
            
        return None
    except Exception as e:
        logger.error(f"خطأ في تحليل رابط الرسالة: {e}")
        return None

# --- دوال قاعدة البيانات ---
def get_categories(user_id=None):
    """استرجاع قائمة الفئات مع عدد الحسابات في كل منها الخاصة بالمستخدم"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    query = """
        SELECT c.id, c.name, COUNT(a.id) 
        FROM categories c
        LEFT JOIN accounts a ON c.id = a.category_id AND a.is_active = 1
        WHERE c.is_active = 1
    """
    
    params = []
    if user_id:
        query += " AND c.owner_id = ?"
        params.append(user_id)
        # إضافة شرط لتصفية الحسابات حسب owner_id أيضاً
        query = query.replace(
            "LEFT JOIN accounts a ON c.id = a.category_id AND a.is_active = 1",
            "LEFT JOIN accounts a ON c.id = a.category_id AND a.is_active = 1 AND a.owner_id = ?"
        )
        params.insert(0, user_id)  # إضافة user_id للـ JOIN
        
    query += """
        GROUP BY c.id
        ORDER BY c.created_at DESC
    """
    
    cursor.execute(query, tuple(params))
    categories = cursor.fetchall()
    conn.close()
    return categories

def get_accounts(category_id, user_id=None):
    if category_id == "all":
        query = """
            SELECT id, session_str, phone, device_info, 
                   proxy_type, proxy_server, proxy_port, proxy_secret
            FROM accounts
            WHERE is_active = 1
        """
        params = []
    else:
        query = """
            SELECT id, session_str, phone, device_info, 
                   proxy_type, proxy_server, proxy_port, proxy_secret
            FROM accounts
            WHERE category_id = ? AND is_active = 1
        """
        params = [category_id]
    
    if user_id is not None and category_id != "all":
        query += " AND owner_id = ?"
        params.append(user_id)
        
    results = safe_db_query(query, tuple(params), is_write=False)
    
    accounts = []
    for row in results:
        try:
            decrypted_session = decrypt_session(row[1])
            accounts.append({
                "id": row[0],
                "session": decrypted_session,
                "phone": row[2],
                "device_info": eval(row[3]) if row[3] else {},
                "proxy_type": row[4],
                "proxy_server": row[5],
                "proxy_port": row[6],
                "proxy_secret": row[7],
            })
        except Exception as e:
            logging.error(f"خطأ في فك تشفير الجلسة للحساب {row[0]}: {str(e)}")
    
    return accounts

def parse_proxy(proxy_string: str) -> dict | None:
    """
    يحلل البروكسي من صيغ مختلفة (Socks5 أو MTProto)
    الصيغ المدعومة:
    1. IP:PORT (Socks5)
    2. IP:PORT:SECRET (MTProto)
    3. https://t.me/proxy?server=IP&port=PORT&secret=SECRET (MTProto Link)
    """
    try:
        proxy_string = proxy_string.strip()
        
        # 1. التحقق من روابط MTProto
        if "t.me/proxy?" in proxy_string or "tg://proxy?" in proxy_string:
            parsed_url = urlparse(proxy_string)
            params = parse_qs(parsed_url.query)
            server = params.get('server', [None])[0]
            port = params.get('port', [None])[0]
            secret = params.get('secret', [None])[0]
            
            if server and port and secret:
                return {
                    'host': server,
                    'port': int(port),
                    'secret': secret,
                    'type': 'mtproto'
                }
        
        # 2. التحقق من الصيغ النصية IP:PORT[:SECRET]
        if ':' in proxy_string:
            parts = proxy_string.split(':')
            if len(parts) == 2:
                # Socks5: IP:PORT
                return {
                    'host': parts[0].strip(),
                    'port': int(parts[1].strip()),
                    'type': 'socks5'
                }
            elif len(parts) == 3:
                # MTProto: IP:PORT:SECRET
                return {
                    'host': parts[0].strip(),
                    'port': int(parts[1].strip()),
                    'secret': parts[2].strip(),
                    'type': 'mtproto'
                }
                
        return None
    except Exception as e:
        logger.error(f"خطأ في تحليل البروكسي: {e}")
        return None

# للحفاظ على التوافق مع الكود القديم
def parse_socks5_proxy(proxy_string: str) -> dict | None:
    return parse_proxy(proxy_string)

def validate_socks5_proxy(proxy_info: dict) -> bool:
    """
    يتحقق من صحة معلومات بروكسي Socks5
    """
    if not isinstance(proxy_info, dict):
        return False
        
    if 'host' not in proxy_info or 'port' not in proxy_info:
        return False
        
    try:
        port = int(proxy_info['port'])
        return 1 <= port <= 65535 and len(proxy_info['host'].strip()) > 0
    except (ValueError, TypeError):
        return False

# --- نظام فحص بروكسي Socks5 ---
class Socks5ProxyChecker:
    def __init__(self):
        self.proxy_stats = {}
        self.check_intervals = [5, 10, 15, 30, 60]  # ثواني بين الفحوصات
        
    async def check_proxy(self, session_str: str, proxy_info: dict) -> dict:
        """فحص بروكسي Socks5"""
        import socks
        import socket
        
        start_time = time.time()
        client = None
        result = proxy_info.copy()
        
        try:
            # إعداد البروكسي في النظام
            socks.set_default_proxy(socks.SOCKS5, proxy_info['host'], proxy_info['port'])
            socket.socket = socks.socksocket
            
            # إعداد معلمات العميل
            params = {
                "api_id": API_ID,
                "api_hash": API_HASH,
                "timeout": 10,
            }
            
            # إنشاء العميل والتوصيل
            client = TelegramClient(StringSession(session_str), **params)
            await client.connect()
            
            # قياس سرعة الاتصال
            connect_time = time.time() - start_time
            
            # فحص فعالية البروكسي
            start_req = time.time()
            await client.get_me()
            response_time = time.time() - start_req
            
            result.update({
                "ping": int(connect_time * 1000),
                "response_time": int(response_time * 1000),
                "last_check": int(time.time()),
                "status": "active"
            })
            
        except Exception as e:
            result.update({
                "ping": 0,
                "response_time": 0,
                "last_check": int(time.time()),
                "status": "error",
                "error": str(e)
            })
        finally:
            # إعادة تعيين الإعدادات
            socks.set_default_proxy()
            import socket as original_socket
            socket.socket = original_socket.socket
            
            if client and client.is_connected():
                await client.disconnect()
        
        # تحديث إحصائيات البروكسي
        proxy_key = f"{proxy_info['host']}:{proxy_info['port']}"
        self.proxy_stats[proxy_key] = result
        return result

    def get_best_proxy(self, proxies: list) -> dict:
        """الحصول على أفضل بروكسي بناءً على الإحصائيات"""
        if not proxies:
            return None
            
        # تصفية البروكسيات النشطة فقط
        active_proxies = [p for p in proxies if p.get('status') == 'active']
        
        if not active_proxies:
            return None
        
        # اختيار البروكسي مع أفضل وقت استجابة
        return min(active_proxies, key=lambda x: x.get('ping', 10000))

    def needs_check(self, proxy_info: dict) -> bool:
        """تحديد إذا كان البروكسي يحتاج فحصًا"""
        last_check = proxy_info.get('last_check', 0)
        interval = random.choice(self.check_intervals)
        return (time.time() - last_check) > interval

    def rotate_proxy(self, proxies: list, current_proxy: dict) -> dict:
        """تدوير البروكسي بشكل ذكي"""
        if not proxies or len(proxies) < 2:
            return current_proxy
            
        # استبعاد البروكسي الحالي
        available_proxies = [p for p in proxies if p != current_proxy]
        
        # تصنيف البروكسي حسب الجودة
        active_proxies = sorted(
            [p for p in available_proxies if p.get('status') == 'active'],
            key=lambda x: x['response_time']
        )
        
        if not active_proxies:
            return current_proxy
            
        # إذا كانت هناك بروكسي أفضل بنسبة 20% على الأقل
        if current_proxy and active_proxies[0]['response_time'] < current_proxy.get('response_time', 10000) * 0.8:
            return active_proxies[0]
            
        # إذا كان البروكسي الحالي بطيئًا جدًا
        if current_proxy and current_proxy.get('response_time', 0) > 5000:  # أكثر من 5 ثواني
            return active_proxies[0]
            
        return current_proxy if current_proxy else active_proxies[0]

# إنشاء نسخة عامة من مدقق البروكسي
socks5_proxy_checker = Socks5ProxyChecker()

# --- الفئة الأساسية المحسنة لتنفيذ البلاغات ---
class AdvancedReporter:
    """فئة مخصصة لتنظيم وتنفيذ عمليات الإبلاغ مع دعم تدوير البروكسي"""
    def __init__(self, client: TelegramClient, context: ContextTypes.DEFAULT_TYPE):
        self.client = client
        self.context = context
        self.stats = {"success": 0, "failed": 0, "last_report": None}

    async def dynamic_delay(self, delay: float):
        """تضمن وجود فاصل زمني بين عمليات الإبلاغ مع تقليل زمن الانتظار"""
        if self.stats["last_report"]:
            elapsed = time.time() - self.stats["last_report"]
            if elapsed < delay:
                wait = delay - elapsed
                logger.info(f"⏳ تأخير {wait:.1f} ثانية")
                await asyncio.sleep(wait)
        self.stats["last_report"] = time.time()

    async def resolve_target(self, target: str | dict):
        """تحول الهدف (رابط، يوزر) إلى كائن يمكن استخدامه في تيليثون"""
        try:
            # إذا كان الرابط يحتوي على معرف رسالة
            if isinstance(target, str) and 't.me/' in target:
                parsed = parse_message_link(target)
                if parsed:
                    entity = await self.client.get_entity(parsed["channel"])
                    return {
                        "channel": utils.get_input_peer(entity),
                        "message_id": parsed["message_id"]
                    }
            
            # إذا كان الهدف معرف قناة/دردشة
            if isinstance(target, str):
                entity = await self.client.get_entity(target)
                return utils.get_input_peer(entity)
            
            # إذا كان الهدف كائنًا جاهزًا
            if isinstance(target, dict) and "message_id" in target:
                entity = await self.client.get_entity(target["channel"])
                return {
                    "channel": utils.get_input_peer(entity),
                    "message_id": target["message_id"]
                }
                
            return None
        except Exception as e:
            logger.error(f"❌ خطأ في حل الهدف {target}: {e}")
            return None

    async def execute_report(self, target, reason_obj, method_type, message, reports_per_account, cycle_delay):
        """تنفذ بلاغًا فرديًا مع تحسينات في معالجة الأخطاء"""
        target_obj = await self.resolve_target(target)
        if not target_obj:
            self.stats["failed"] += reports_per_account
            return False

        for _ in range(reports_per_account):
            if not self.context.user_data.get("active", True): 
                return False
            try:
                await self.dynamic_delay(cycle_delay)

                if method_type == "peer":
                    # حساب الإبلاغ عن المستخدم/القناة باستخدام reason ككائن TL
                    await self.client(functions.account.ReportPeerRequest(
                        peer=target_obj,
                        reason=reason_obj,
                        message=message
                    ))
                    self.stats["success"] += 1
                    logger.info(f"✅ تم الإبلاغ بنجاح على {target}")

                elif method_type == "message":
                    # الإبلاغ عن رسالة مع اختيار السبب ديناميكيًا
                    peer = target_obj["channel"]
                    msg_id = target_obj["message_id"]

                    # الخطوة الأولى: طلب الخيارات دون رسالة نصية (empty)
                    result = await self.client(functions.messages.ReportRequest(
                        peer=peer,
                        id=[msg_id],
                        option=b'',
                        message=''
                    ))
                    # إذا لزم الاختيار:
                    if isinstance(result, types.ReportResultChooseOption):
                        # محاولة العثور على الخيار المناسب بناءً على reason_obj
                        chosen_option = None
                        # نطابق اسم السبب العربي أو المفتاح؟ هنا نطابق حسب النوع
                        for opt in result.options:
                            # opt.text قد يحتوي نص الخيار (مثل "Spam", "Child Abuse", إلخ.)
                            if reason_obj.__class__.__name__.lower().find(opt.text.lower()) != -1 or reason_obj.__class__.__name__.lower() == opt.text.lower():
                                chosen_option = opt.option
                                break
                        # إذا لم نجد تطابقًا، نأخذ الخيار الأول افتراضيًا
                        if not chosen_option and result.options:
                            chosen_option = result.options[0].option

                        # الخطوة الثانية: إرسال البلاغ مع الخيار المحدد ونص الرسالة
                        await self.client(functions.messages.ReportRequest(
                            peer=peer,
                            id=[msg_id],
                            option=chosen_option or b'',
                            message=message
                        ))
                    # في حال تم الإبلاغ مباشرة أو إضافة تعليق:
                    self.stats["success"] += 1
                    logger.info(f"✅ تم الإبلاغ بنجاح على الرسالة {msg_id}")

                elif method_type == "photo":
                    photos = await self.client.get_profile_photos(target_obj, limit=1)
                    if not photos:
                        logger.error(f"❌ لا توجد صورة للملف الشخصي للهدف: {target}")
                        self.stats["failed"] += 1
                        continue
                    photo_input = types.InputPhoto(
                        id=photos[0].id,
                        access_hash=photos[0].access_hash,
                        file_reference=photos[0].file_reference
                    )
                    await self.client(functions.account.ReportProfilePhotoRequest(
                        peer=target_obj,
                        photo_id=photo_input,
                        reason=reason_obj,
                        message=message
                    ))
                    self.stats["success"] += 1
                    logger.info(f"✅ تم الإبلاغ بنجاح على صورة الملف الشخصي لـ {target}")

                elif method_type == "sponsored":
                    # الإبلاغ عن منشور ممول ديناميكيًا
                    random_id = base64.urlsafe_b64decode(target)
                    # الخطوة الأولى: طلب خيارات البلاغ دون تحديد الخيار
                    result = await self.client(functions.messages.ReportSponsoredMessageRequest(
                        random_id=random_id,
                        option=b''
                    ))
                    # إذا لزم الأمر اختيار خيار:
                    if isinstance(result, types.SponsoredMessageReportResultChooseOption):
                        # اختر أول خيار (أو بناءً على شيء محدد)
                        if result.options:
                            chosen_option = result.options[0].option
                            await self.client(functions.messages.ReportSponsoredMessageRequest(
                                random_id=random_id,
                                option=chosen_option
                            ))
                    self.stats["success"] += 1
                    logger.info(f"✅ تم الإبلاغ بنجاح على المنشور الممول {target}")

            except (FloodWaitError, PeerFloodError) as e:
                wait_time = e.seconds if isinstance(e, FloodWaitError) else 300  # افتراضي 5 دقائق للـ PeerFlood
                logger.warning(f"⏳ توقف بسبب {type(e).__name__}. سيتم الانتظار لـ {wait_time} ثانية.")
                await asyncio.sleep(wait_time + 5)
            except Exception as e:
                self.stats["failed"] += 1
                logger.error(f"❌ فشل الإبلاغ: {type(e).__name__} - {e}")

        return True

    async def execute_mass_report(self, targets, reason_obj, message):
        """تنفذ بلاغًا جماعيًا على عدة منشورات دفعة واحدة مع تحسين الأداء"""
        if not targets:
            return
        
        try:
            # استخراج اسم القناة وكائناتها وقائمة الرسائل
            channel_username = targets[0]["channel"]
            entity = await self.client.get_entity(channel_username)
            peer = utils.get_input_peer(entity)
            message_ids = [t["message_id"] for t in targets]

            # إرسال الطلب الأولي للحصول على خيارات البلاغ
            result = await self.client(functions.messages.ReportRequest(
                peer=peer,
                id=message_ids,
                option=b'',
                message=''
            ))
            # إذا تم إرجاع خيارات، اختر المناسب وأعد الطلب
            if isinstance(result, types.ReportResultChooseOption):
                chosen_option = None
                for opt in result.options:
                    if reason_obj.__class__.__name__.lower().find(opt.text.lower()) != -1 or reason_obj.__class__.__name__.lower() == opt.text.lower():
                        chosen_option = opt.option
                        break
                if not chosen_option and result.options:
                    chosen_option = result.options[0].option
                await self.client(functions.messages.ReportRequest(
                    peer=peer,
                    id=message_ids,
                    option=chosen_option or b'',
                    message=message
                ))

            count = len(message_ids)
            self.stats["success"] += count
            logger.info(f"✅ تم إرسال بلاغ جماعي ناجح على {count} منشور.")
        except Exception as e:
            self.stats["failed"] += len(targets)
            logger.error(f"❌ فشل البلاغ الجماعي: {type(e).__name__} - {e}", exc_info=True)

# --- دوال تشغيل العملية المحسنة ---
async def do_session_report(session_data: dict, config: dict, context: ContextTypes.DEFAULT_TYPE):
    """تنفذ جميع البلاغات المطلوبة لحساب (جلسة) واحد مع إدارة أفضل للموارد"""
    session_str = session_data.get("session")
    proxies = config.get("proxies", [])
    client, connected = None, False
    
    # تدوير البروكسي - اختيار الأفضل
    current_proxy = None
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries and context.user_data.get("active", True):
        # تدوير البروكسي
        current_proxy = socks5_proxy_checker.rotate_proxy(proxies, current_proxy)
        
        try:
            # إعداد معلمات العميل
            params = {
                "api_id": API_ID,
                "api_hash": API_HASH,
                "timeout": 15,
                "device_model": "Reporter Bot",
                "system_version": "1.0",
                "app_version": "1.0"
            }
            
            if current_proxy:
                if current_proxy.get('type') == 'mtproto':
                    # إعداد بروكسي MTProto لـ Telethon
                    # ملاحظة: Telethon يتطلب البروكسي كـ tuple: (host, port, secret)
                    params["proxy"] = {
                        'proxy_type': 'mtproto',
                        'addr': current_proxy['host'],
                        'port': current_proxy['port'],
                        'secret': current_proxy['secret']
                    }
                    logger.info(f"Using MTProto proxy: {current_proxy['host']}:{current_proxy['port']}")
                else:
                    # إعداد بروكسي Socks5 لـ Telethon
                    import socks
                    params["proxy"] = {
                        'proxy_type': socks.SOCKS5,
                        'addr': current_proxy['host'],
                        'port': current_proxy['port']
                    }
                    logger.info(f"Using Socks5 proxy: {current_proxy['host']}:{current_proxy['port']}")
            
            client = TelegramClient(StringSession(session_str), **params)
            # تقليل المهلة لـ 7 ثوانٍ لتخطي البروكسيات البطيئة فوراً وضمان سرعة الإبلاغ
            await asyncio.wait_for(client.connect(), timeout=7)
            
            # التحقق من تفعيل الجلسة ومعالجة الجلسات الملغاة
            try:
                if not await client.is_user_authorized():
                    logger.warning(f"⚠️ الجلسة غير مصرح لها للحساب {session_data.get('phone')}")
                    # تعطيل الحساب في قاعدة البيانات
                    try:
                        with sqlite3.connect(DB_PATH) as conn:
                            conn.execute("UPDATE accounts SET is_active = 0 WHERE phone = ?", (session_data.get('phone'),))
                            conn.commit()
                    except: pass
                    return
            except RPCError as e:
                if any(err in str(e) for err in ["AUTH_KEY_UNREGISTERED", "USER_DEACTIVATED", "SESSION_REVOKED", "SESSION_EXPIRED"]):
                    logger.error(f"❌ الجلسة ملغاة (Invalidated) للحساب {session_data.get('phone')}: {e}")
                    try:
                        with sqlite3.connect(DB_PATH) as conn:
                            conn.execute("UPDATE accounts SET is_active = 0 WHERE phone = ?", (session_data.get('phone'),))
                            conn.commit()
                    except: pass
                    return
                raise e
            
            connected = True
            reporter = AdvancedReporter(client, context)
            method_type = config.get("method_type")
            targets_list = config.get("targets", [])
            reports_per_account = config.get("reports_per_account", 1)
            cycle_delay = config.get("cycle_delay", 1)

            # تنفيذ الإبلاغ حسب النوع
            if method_type == "mass":
                await reporter.execute_mass_report(targets_list, config["reason_obj"], config.get("message", ""))
            else:
                for _ in range(reports_per_account):
                    if not context.user_data.get("active", True): 
                        break
                    
                    for target in targets_list:
                        if not context.user_data.get("active", True):
                            break
                        
                        await reporter.execute_report(
                            target, config["reason_obj"], method_type,
                            config.get("message", ""), 1, cycle_delay
                        )

            # تحديث الإحصائيات
            lock = context.bot_data.setdefault('progress_lock', asyncio.Lock())
            async with lock:
                context.user_data["progress_success"] = context.user_data.get("progress_success", 0) + reporter.stats["success"]
                context.user_data["progress_failed"] = context.user_data.get("progress_failed", 0) + reporter.stats["failed"]
            
            break  # الخروج عند النجاح

        except (RPCError, TimeoutError, asyncio.TimeoutError) as e:
            retry_count += 1
            if current_proxy:
                current_proxy['status'] = 'connection_failed'
                current_proxy['error'] = str(e)
                logger.warning(f"❌ فشل الاتصال بالبروكسي: {e}")
            
            if retry_count >= max_retries:
                # تسجيل الفشل في الإحصائيات الحية لتظهر للمستخدم
                async with config["lock"]:
                    config["progress_failed"] = config.get("progress_failed", 0) + (len(config.get("targets", [])) * config.get("reports_per_account", 1))
                
                # إشعار المستخدم بتخطي البروكسي بسبب البطء
                try:
                    await context.bot.send_message(
                        chat_id=context.user_data.get("chat_id", update.effective_chat.id),
                        text=f"⚠️ تم تخطي بروكسي بطيء (تجاوز 7 ثوانٍ) والاستمرار في العملية."
                    )
                except:
                    pass
                    
                logger.error(f"❌ فشل الاتصال بعد {max_retries} محاولات (بروكسي بطيء). تم تسجيل الفشل والاستمرار.")
                break
            
            await asyncio.sleep(1)
        except (AuthKeyDuplicatedError, SessionPasswordNeededError) as e:
            logger.error(f"❌ مشكلة في الجلسة: {type(e).__name__}")
            break
        except Exception as e:
            logger.error(f"❌ خطأ فادح في جلسة: {e}", exc_info=True)
            break
        finally:
            if client and client.is_connected():
                await client.disconnect()

async def run_report_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = context.user_data
    sessions = config.get("accounts", [])
    if not sessions:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ لا توجد حسابات صالحة لبدء العملية.")
        return

    targets = config.get("targets", [])
    reports_per_account = config.get("reports_per_account", 1)

    total_reports = len(sessions) * len(targets) * reports_per_account

    # تهيئة متغيرات التتبع
    config["total_reports"] = total_reports
    config["progress_success"] = 0
    config["progress_failed"] = 0
    config["active"] = True
    config["lock"] = asyncio.Lock()  # قفل للعمليات المتزامنة
    config["failed_reports"] = 0  # للإبلاغات الفاشلة المؤقتة

    proxies = config.get("proxies", [])
    
    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        stop_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🛑 إيقاف العملية", callback_data="cancel_operation")]])
        
        # عرض القائمة الحية فوراً
        text = (
            f"📊 <b>تقدم الإبلاغات</b>\n\n"
            f"[□□□□□□□□□□□□□□□□□□□□] 0%\n\n"
            f"▫️ الإجمالي المطلوب: {total_reports}\n"
            f"✅ الناجحة: 0\n"
            f"❌ الفاشلة: 0\n"
            f"⏳ المتبقية: {total_reports}\n"
            f"⏱ الوقت المتوقع: تقدير..."
        )
        
        progress_message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            parse_mode="HTML",
            reply_markup=stop_keyboard
        )
        context.user_data["progress_message"] = progress_message
    except Exception as e:
        logger.error(f"فشل في إرسال رسالة التقدم: {str(e)}")
        return
    
    session_tasks = []
    monitor_task = None
    
    try:
        # تأخير بسيط لضمان استقرار الواجهة قبل بدء المهام الثقيلة
        await asyncio.sleep(1)
        
        # إنشاء مهام مع التعامل الفردي مع كل جلسة
        for session in sessions:
            task = asyncio.create_task(
                process_single_account(
                    session, 
                    targets, 
                    reports_per_account,
                    config,
                    context
                )
            )
            session_tasks.append(task)
        
        context.user_data["tasks"] = session_tasks

        # مراقبة البروكسي (إن وجد)
        if proxies:
            async def monitor_proxies():
                while config.get("active", True):
                    try:
                        await asyncio.sleep(30)
                        current_proxies = config.get("proxies", [])
                        for proxy in current_proxies:
                            if socks5_proxy_checker.needs_check(proxy):
                                updated = await socks5_proxy_checker.check_proxy(sessions[0]["session"], proxy)
                                proxy.update(updated)
                    except asyncio.CancelledError:
                        logger.info("تم إلغاء مهمة مراقبة البروكسي")
                        return
                    except Exception as e:
                        logger.warning(f"خطأ في فحص البروكسي: {str(e)}")
        
            monitor_task = asyncio.create_task(monitor_proxies())

        start_timestamp = time.time()
        last_update_timestamp = start_timestamp
        
        if monitor_task:
        	context.user_data["monitor_task"] = monitor_task  # حفظ المرجع للإلغاء
        
        # تحديث التقدم الرئيسي
        while config.get("active", True) and any(not t.done() for t in session_tasks):
            async with config["lock"]:
                success = config["progress_success"]
                failed = config["progress_failed"]
                temp_failed = config["failed_reports"]
                total_failed = failed + temp_failed
                
            completed = success + total_failed
            total = config.get("total_reports", 1)
            progress_percent = min(100, int((completed / total) * 100))
            
            remaining = total - completed
            
            current_timestamp = time.time()
            elapsed = current_timestamp - start_timestamp
            
            if completed > 0 and elapsed > 0:
                speed = completed / elapsed
                eta_seconds = remaining / speed if speed > 0 else 0
                
                hours, remainder = divmod(eta_seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                
                if hours > 0:
                    eta_str = f"{int(hours)}:{int(minutes):02d}:{int(seconds):02d}"
                else:
                    eta_str = f"{int(minutes)}:{int(seconds):02d}"
            else:
                eta_str = "تقدير..."
            
            filled_length = int(20 * (progress_percent / 100))
            progress_bar = "[" + "■" * filled_length + "□" * (20 - filled_length) + "]"
            
            text = (
                f"📊 <b>تقدم الإبلاغات</b>\n\n"
                f"{progress_bar} {progress_percent}%\n\n"
                f"▫️ الإجمالي المطلوب: {total}\n"
                f"✅ الناجحة: {success}\n"
                f"❌ الفاشلة: {total_failed} (مؤقتة: {temp_failed})\n"
                f"⏳ المتبقية: {max(0, remaining)}\n"
                f"⏱ الوقت المتوقع: {eta_str}"
            )
            
            try:
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                stop_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🛑 إيقاف العملية", callback_data="cancel_operation")]])
                
                await context.bot.edit_message_text(
                    chat_id=progress_message.chat_id, 
                    message_id=progress_message.message_id, 
                    text=text,
                    parse_mode="HTML",
                    reply_markup=stop_keyboard
                )
                last_update_timestamp = current_timestamp
            except BadRequest as e:
                if "Message is not modified" not in str(e):
                    if "Message to edit not found" in str(e):
                        logger.warning("رسالة التقدم غير موجودة، توقف التحديثات")
                        break
                    logger.warning(f"فشل تحديث رسالة التقدم: {e}")
            except Exception as e:
                logger.error(f"خطأ غير متوقع أثناء تحديث التقدم: {e}")
                if current_timestamp - last_update_timestamp > 10:
                    logger.error("فشل متكرر في تحديث التقدم، إيقاف التحديثات")
                    break
            
            await asyncio.sleep(5)

        # الحساب النهائي بعد اكتمال المهام
        async with config["lock"]:
            success = config["progress_success"]
            failed = config["progress_failed"]
            temp_failed = config["failed_reports"]
            total_failed = failed + temp_failed
            
        total = config.get("total_reports", 1)
        success_rate = (success / total) * 100 if total > 0 else 0
        
        elapsed_time = time.time() - start_timestamp
        minutes = int(elapsed_time // 60)
        seconds = int(elapsed_time % 60)
        time_str = f"{minutes}:{seconds:02d}"
        
        final_text = (
            f"✅ <b>اكتملت عمليات الإبلاغ!</b>\n\n"
            f"• الحسابات المستخدمة: {len(sessions)}\n"
            f"• الإبلاغات الناجحة: {success} ({success_rate:.1f}%)\n"
            f"• الإبلاغات الفاشلة: {total_failed}\n"
            f"• الوقت المستغرق: {time_str}"
        )
        
        try:
            await context.bot.edit_message_text(
                chat_id=progress_message.chat_id, 
                message_id=progress_message.message_id, 
                text=final_text,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"فشل تحديث الرسالة النهائية: {str(e)}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=final_text,
                parse_mode="HTML"
            )
            
    except asyncio.CancelledError:
        logger.info("تم إلغاء العملية")
    finally:
        config["active"] = False
        
        # إلغاء المهام المتبقية
        for task in session_tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(f"خطأ أثناء إلغاء مهمة: {str(e)}")
        
        if monitor_task and not monitor_task.done():
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"خطأ أثناء إلغاء مراقبة البروكسي: {str(e)}")
        
        # تنظيف البيانات المؤقتة
        config.pop("tasks", None)
        config.pop("active", None)
        config.pop("lock", None)

# الدالة المساعدة لمعالجة الحساب الفردي
async def process_single_account(session, targets, reports_per_account, config, context):
    session_id = session.get("id", "unknown")
    total_reports_for_account = len(targets) * reports_per_account
    account_success = 0
    account_temp_failures = 0
    
    try:
        for target in targets:
            for _ in range(reports_per_account):
                try:
                    # تنفيذ عملية الإبلاغ الفعلية
                    await do_session_report(session, {
                        "targets": [target],
                        "reports_per_account": 1,
                        "reason_obj": config["reason_obj"],
                        "method_type": config["method_type"],
                        "message": config.get("message", ""),
                        "cycle_delay": config.get("cycle_delay", 1),
                        "proxies": config.get("proxies", [])
                    }, context)
                    
                    account_success += 1
                    async with config["lock"]:
                        config["progress_success"] += 1
                        
                except (FloodWaitError, PeerFloodError) as e:
                    # أخطاء مؤقتة من تيليثون
                    logger.warning(f"فشل مؤقت للحساب {session_id}: {str(e)}")
                    account_temp_failures += 1
                    async with config["lock"]:
                        config["failed_reports"] += 1
                        
                except (AuthKeyDuplicatedError, SessionPasswordNeededError) as e:
                    # أخطاء دائمة في الجلسة
                    logger.error(f"فشل دائم للحساب {session_id}: {str(e)}")
                    remaining = total_reports_for_account - (account_success + account_temp_failures)
                    async with config["lock"]:
                        config["progress_failed"] += remaining
                    return
                        
                except Exception as e:
                    # أخطاء عامة
                    logger.error(f"خطأ غير متوقع للحساب {session_id}: {str(e)}")
                    account_temp_failures += 1
                    async with config["lock"]:
                        config["failed_reports"] += 1
                    
    except Exception as e:
        logger.error(f"خطأ جسيم في معالجة الحساب {session_id}: {str(e)}")
        remaining = total_reports_for_account - (account_success + account_temp_failures)
        async with config["lock"]:
            config["progress_failed"] += remaining

async def cancel_operation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تلغي العملية الحالية وتنهي المحادثة وتعود للقائمة الرئيسية."""
    query = update.callback_query
    if query:
        try:
            await query.answer("🛑 تم الإلغاء")
        except Exception:
            pass
    
    user_data = context.user_data
    user_data["active"] = False
    
    # إلغاء المهام الجارية
    tasks = user_data.get("tasks", [])
    for task in tasks:
        if not task.done():
            task.cancel()
    
    # تنظيف البيانات المؤقتة فقط
    keys_to_remove = [
        "tasks", "active", "lock", "failed_reports",
        "progress_message", "monitor_task", "targets", 
        "reason_obj", "method_type", "reports_per_account", "cycle_delay"
    ]
    for key in keys_to_remove:
        user_data.pop(key, None)
    
    # استيراد دالة start من الملف الرئيسي بشكل ديناميكي لتجنب التعليق
    try:
        from khayal import start
        await start(update, context)
    except Exception as e:
        logger.error(f"Error returning to start: {e}")
        if query:
            await query.edit_message_text("🛑 تم إلغاء العملية. أرسل /start للعودة للقائمة.")
    
    return ConversationHandler.END