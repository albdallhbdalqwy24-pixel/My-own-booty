# DrKhayal/Telegram/common_improved.py - نسخة محسنة ومطورة

import asyncio
import sqlite3
import base64
import logging
import time
import random
import re
import json
import hashlib
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes, ConversationHandler

from telethon import TelegramClient, functions, types, utils
from telethon.errors import (
    AuthKeyDuplicatedError,
    FloodWaitError,
    PeerFloodError,
    SessionPasswordNeededError,
    RPCError,
    TimeoutError as TelethonTimeoutError,
    ChatWriteForbiddenError,
    UserBannedInChannelError,
    MessageIdInvalidError,
    PeerIdInvalidError
)
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

# إعداد نظام تسجيل مفصل للتتبع
detailed_logger = logging.getLogger('detailed_reporter')
detailed_handler = logging.FileHandler('detailed_reports.log', encoding='utf-8')
detailed_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
detailed_handler.setFormatter(detailed_formatter)
detailed_logger.addHandler(detailed_handler)
detailed_logger.setLevel(logging.INFO)

# === الثوابت المحسنة ===
PROXY_CHECK_TIMEOUT = 25  # ثانية
PROXY_RECHECK_INTERVAL = 3000  # 5 دقائق
MAX_PROXY_RETRIES = 30
REPORT_CONFIRMATION_TIMEOUT = 10  # ثانية للتأكيد
MAX_REPORTS_PER_SESSION = 1000000  # الحد الأقصى للبلاغات لكل جلسة

# استثناءات مخصصة محسنة
class ProxyTestFailed(Exception):
    """فشل في اختبار البروكسي"""
    pass

class ReportNotConfirmed(Exception):
    """لم يتم تأكيد وصول البلاغ"""
    pass

class SessionCompromised(Exception):
    """الجلسة معرضة للخطر"""
    pass

class RateLimitExceeded(Exception):
    """تم تجاوز حد المعدل"""
    pass

# === أنواع البلاغات مع معرفات التأكيد ===
REPORT_TYPES_ENHANCED = {
    2: ("رسائل مزعجة", types.InputReportReasonSpam(), "spam"),
    3: ("إساءة أطفال", types.InputReportReasonChildAbuse(), "child_abuse"),
    4: ("محتوى جنسي", types.InputReportReasonPornography(), "pornography"),
    5: ("عنف", types.InputReportReasonViolence(), "violence"),
    6: ("انتهاك خصوصية", types.InputReportReasonPersonalDetails(), "privacy"),
    7: ("مخدرات", types.InputReportReasonIllegalDrugs(), "drugs"),
    8: ("حساب مزيف", types.InputReportReasonFake(), "fake"),
    9: ("حقوق النشر", types.InputReportReasonCopyright(), "copyright"),
    11: ("أخرى", types.InputReportReasonOther(), "other"),
}

class Socks5ProxyChecker:
    """نظام فحص بروكسي Socks5 محسن"""
    
    def __init__(self):
        self.proxy_stats = {}
        self.failed_proxies = set()
        self.last_check_times = {}
        self.concurrent_checks = 3  # عدد الفحوصات المتزامنة
        
    async def deep_proxy_test(self, session_str: str, proxy_info: dict) -> dict:
        """اختبار بروكسي (Socks5 أو MTProto) مع فحوصات متعددة"""
        import socks
        import socket
        
        result = proxy_info.copy()
        client = None
        original_socket = socket.socket
        
        try:
            # إعداد العميل مع البروكسي المناسب
            params = {
                "api_id": API_ID,
                "api_hash": API_HASH,
                "timeout": 15,
                "device_model": "Proxy Test Bot",
                "system_version": "1.0.0",
                "app_version": "1.0.0",
                "lang_code": "ar"
            }
            
            if proxy_info.get('type') == 'mtproto':
                # إعداد بروكسي MTProto لـ Telethon
                params["proxy"] = (proxy_info['host'], proxy_info['port'], proxy_info['secret'])
            else:
                # إعداد بروكسي Socks5
                socks.set_default_proxy(socks.SOCKS5, proxy_info['host'], proxy_info['port'])
                socket.socket = socks.socksocket
            
            # اختبار الاتصال الأولي
            start_time = time.time()
            client = TelegramClient(StringSession(session_str), **params)
            
            # اختبار الاتصال مع timeout
            await asyncio.wait_for(client.connect(), timeout=15)
            connection_time = time.time() - start_time
            
            # التحقق من التفويض
            if not await client.is_user_authorized():
                raise ProxyTestFailed("الجلسة غير مفوضة")
            
            # اختبار سرعة الاستجابة
            response_start = time.time()
            me = await asyncio.wait_for(client.get_me(), timeout=10)
            response_time = time.time() - response_start
            
            # اختبار إضافي: جلب الحوارات
            dialogs_start = time.time()
            try:
                async for dialog in client.iter_dialogs(limit=3):
                    break
                dialogs_time = time.time() - dialogs_start
            except:
                dialogs_time = 0
            
            # تقييم جودة البروكسي
            ping = int(connection_time * 1000)
            responsiveness = int(response_time * 1000)
            
            quality_score = 100
            if ping > 3000:
                quality_score -= 30
            elif ping > 1500:
                quality_score -= 15
                
            if responsiveness > 2000:
                quality_score -= 20
            elif responsiveness > 1000:
                quality_score -= 10
                
            result.update({
                "status": "active",
                "ping": ping,
                "response_time": responsiveness,
                "dialogs_time": int(dialogs_time * 1000),
                "quality_score": max(0, quality_score),
                "last_check": int(time.time()),
                "user_id": me.id,
                "connection_successful": True,
                "error": None
            })
            
            detailed_logger.info(f"✅ بروكسي Socks5 نشط: {proxy_info['host']}:{proxy_info['port']} - ping: {ping}ms")
            
        except asyncio.TimeoutError:
            result.update({
                "status": "timeout",
                "ping": 9999,
                "response_time": 9999,
                "quality_score": 0,
                "last_check": int(time.time()),
                "connection_successful": False,
                "error": "انتهت مهلة الاتصال"
            })
            proxy_key = f"{proxy_info['host']}:{proxy_info['port']}"
            self.failed_proxies.add(proxy_key)
            
        except ProxyTestFailed as e:
            result.update({
                "status": "failed",
                "ping": 0,
                "response_time": 0,
                "quality_score": 0,
                "last_check": int(time.time()),
                "connection_successful": False,
                "error": str(e)
            })
            proxy_key = f"{proxy_info['host']}:{proxy_info['port']}"
            self.failed_proxies.add(proxy_key)
            
        except Exception as e:
            result.update({
                "status": "error",
                "ping": 0,
                "response_time": 0,
                "quality_score": 0,
                "last_check": int(time.time()),
                "connection_successful": False,
                "error": str(e)
            })
            proxy_key = f"{proxy_info['host']}:{proxy_info['port']}"
            logger.error(f"خطأ في فحص البروكسي Socks5 {proxy_key}: {e}")
            
        finally:
            # إعادة تعيين الإعدادات
            socks.set_default_proxy()
            socket.socket = original_socket
            
            if client and client.is_connected():
                try:
                    await client.disconnect()
                except:
                    pass
                    
        return result
    
    async def batch_check_proxies(self, session_str: str, proxies: List[dict]) -> List[dict]:
        """فحص مجموعة من البروكسيات بشكل متوازي"""
        semaphore = asyncio.Semaphore(self.concurrent_checks)
        
        async def check_single(proxy):
            async with semaphore:
                return await self.deep_proxy_test(session_str, proxy)
        
        tasks = [check_single(proxy) for proxy in proxies]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                proxy_key = f"{proxies[i]['host']}:{proxies[i]['port']}"
                logger.error(f"خطأ في فحص البروكسي Socks5 {proxy_key}: {result}")
                proxies[i].update({
                    "status": "error",
                    "error": str(result),
                    "quality_score": 0
                })
                valid_results.append(proxies[i])
            else:
                valid_results.append(result)
                
        return valid_results
    
    def get_best_proxies(self, proxies: List[dict], count: int = 5) -> List[dict]:
        """الحصول على أفضل البروكسيات مرتبة حسب الجودة"""
        active_proxies = [p for p in proxies if p.get('status') == 'active']
        
        # ترتيب حسب نقاط الجودة ثم السرعة
        sorted_proxies = sorted(
            active_proxies,
            key=lambda x: (x.get('quality_score', 0), -x.get('ping', 9999)),
            reverse=True
        )
        
        return sorted_proxies[:count]
    
    def needs_recheck(self, proxy_info: dict) -> bool:
        """تحديد إذا كان البروكسي يحتاج إعادة فحص"""
        last_check = proxy_info.get('last_check', 0)
        return (time.time() - last_check) > PROXY_RECHECK_INTERVAL

# إنشاء نسخة عامة من مدقق البروكسي Socks5
socks5_proxy_checker = Socks5ProxyChecker()

def parse_proxy(proxy_string: str) -> dict | None:
    """
    يحلل البروكسي من صيغ مختلفة (Socks5 أو MTProto)
    """
    try:
        proxy_string = proxy_string.strip()
        
        # 1. روابط MTProto
        if "t.me/proxy?" in proxy_string or "tg://proxy?" in proxy_string:
            from urllib.parse import urlparse, parse_qs
            parsed_url = urlparse(proxy_string)
            params = parse_qs(parsed_url.query)
            server = params.get('server', [None])[0]
            port = params.get('port', [None])[0]
            secret = params.get('secret', [None])[0]
            if server and port and secret:
                return {'host': server, 'port': int(port), 'secret': secret, 'type': 'mtproto'}
        
        # 2. الصيغ النصية
        if ':' in proxy_string:
            parts = proxy_string.split(':')
            if len(parts) == 2:
                return {'host': parts[0].strip(), 'port': int(parts[1].strip()), 'type': 'socks5'}
            elif len(parts) == 3:
                return {'host': parts[0].strip(), 'port': int(parts[1].strip()), 'secret': parts[2].strip(), 'type': 'mtproto'}
        return None
    except Exception as e:
        logger.error(f"خطأ في تحليل البروكسي: {e}")
        return None

def parse_socks5_proxy(proxy_string: str) -> dict | None:
    return parse_proxy(proxy_string)

class VerifiedReporter:
    """نظام إبلاغ محسن مع تأكيد الإرسال والتحقق من النجاح"""
    
    def __init__(self, client: TelegramClient, context: ContextTypes.DEFAULT_TYPE):
        self.client = client
        self.context = context
        self.stats = {
            "success": 0,
            "failed": 0,
            "confirmed": 0,
            "unconfirmed": 0,
            "last_report": None,
            "report_ids": []
        }
        self.session_reports_count = 0
        self.last_activity = time.time()
        
    async def verify_report_success(self, report_result: Any, target: str, report_type: str) -> bool:
        """التحقق من نجاح البلاغ الفعلي مع دعم جميع أنواع النتائج"""
        try:
            # تحليل نتيجة البلاغ
            if isinstance(report_result, types.ReportResultAddComment):
                detailed_logger.info(f"✅ تم قبول البلاغ مع طلب تعليق - الهدف: {target}")
                return True
                
            elif isinstance(report_result, types.ReportResultChooseOption):
                detailed_logger.info(f"✅ تم قبول البلاغ مع خيارات - الهدف: {target}")
                return True
            
            # إضافة هذا الشرط: ReportResultReported يعني أن البلاغ تم تقديمه بنجاح
            elif isinstance(report_result, types.ReportResultReported):
                detailed_logger.info(f"✅ تم تقديم البلاغ بنجاح - الهدف: {target}")
                return True
                
            elif hasattr(report_result, 'success') and report_result.success:
                detailed_logger.info(f"✅ تم قبول البلاغ بنجاح - الهدف: {target}")
                return True
                
            # إذا كانت النتيجة True أو None (نجاح ضمني)
            elif report_result is True or report_result is None:
                detailed_logger.info(f"✅ تم إرسال البلاغ (نجاح ضمني) - الهدف: {target}")
                return True
                
            else:
                # تسجيل النوع للتحليل المستقبلي
                result_type = type(report_result).__name__
                detailed_logger.info(f"ℹ️ نوع نتيجة البلاغ: {result_type} - الهدف: {target}")
                
                # إذا كان النوع ReportResultReported أو أي نوع يبدو ناجحاً
                if 'Reported' in result_type or 'Success' in result_type or 'Ok' in result_type:
                    return True
                else:
                    detailed_logger.warning(f"⚠️ نتيجة غير مؤكدة للبلاغ - الهدف: {target} - النتيجة: {result_type}")
                    return False
                
        except Exception as e:
            detailed_logger.error(f"❌ خطأ في التحقق من البلاغ - الهدف: {target} - الخطأ: {e}")
            return False
    
    async def intelligent_delay(self, base_delay: float):
        """تأخير ذكي يحاكي السلوك البشري اليدوي مع عشوائية كبيرة"""
        # إضافة عشوائية كبيرة للتأخير لضمان عدم الحظر (بين 80% و 250% من الوقت المحدد)
        actual_delay = base_delay * random.uniform(0.8, 2.5)
        # إضافة تأخير إضافي عشوائي بسيط لمحاكاة التفكير البشري
        actual_delay += random.uniform(2, 7)
        
        if actual_delay > 0:
            detailed_logger.info(f"⏳ تأخير ذكي: {actual_delay:.1f} ثانية")
            await asyncio.sleep(actual_delay)
                
        self.stats["last_report"] = time.time()
        self.last_activity = time.time()
    
    async def resolve_target_enhanced(self, target: Any) -> dict | None:
        """حل الهدف مع معلومات إضافية للتتبع"""
        try:
            target_info = {"original": target, "resolved": None, "type": None}
            
            # الحالة 1: الهدف هو قاموس (نتيجة من parse_message_link)
            if isinstance(target, dict) and 'channel' in target and 'message_id' in target:
                try:
                    # التحقق من نوع الكائن المُمرر
                    channel_ref = target['channel']
                    
                    # إذا كان كائن Telethon، استخدمه مباشرة
                    if hasattr(channel_ref, 'id') and hasattr(channel_ref, '__class__'):
                        entity = channel_ref
                    # إذا كان معرف رقمي
                    elif isinstance(channel_ref, int):
                        entity = await self.client.get_entity(channel_ref)
                    # إذا كان نص (اسم مستخدم)
                    elif isinstance(channel_ref, str):
                        username = channel_ref.lstrip('@')
                        if re.match(r'^[a-zA-Z][\w\d]{3,30}[a-zA-Z\d]$', username):
                            entity = await self.client.get_entity(username)
                        else:
                            # حل كمعرف قناة مباشرة
                            entity = await self.client.get_entity(types.PeerChannel(channel_ref))
                    else:
                        # محاولة أخيرة باستخدام الكائن مباشرة
                        entity = await self.client.get_entity(channel_ref)
                        
                except (ValueError, TypeError, RPCError) as e:
                    # المحاولة الأخيرة: حل باستخدام معرف القناة كرقم
                    try:
                        if hasattr(target['channel'], 'id'):
                            entity = await self.client.get_entity(target['channel'].id)
                        else:
                            entity = await self.client.get_entity(types.PeerChannel(int(target['channel'])))
                    except:
                        raise ValueError(f"فشل في حل القناة: {target['channel']} - {str(e)}")
                
                target_info.update({
                    "resolved": {
                        "channel": utils.get_input_peer(entity),
                        "message_id": target['message_id']
                    },
                    "type": "message",
                    "channel_id": entity.id,
                    "message_id": target['message_id']
                })
                return target_info
                
            # الحالة 2: رابط رسالة
            if isinstance(target, str) and 't.me/' in target:
                # تحليل رابط الرسالة
                parsed = self.parse_message_link(target)
                if parsed:
                    # حل القناة بنفس الطريقة المستخدمة للقاموس
                    return await self.resolve_target_enhanced(parsed)
                
                # رابط قناة أو مستخدم مباشر
                try:
                    entity = await self.client.get_entity(target)
                    target_info.update({
                        "resolved": utils.get_input_peer(entity),
                        "type": "peer",
                        "entity_id": entity.id
                    })
                    return target_info
                except Exception as e:
                    detailed_logger.error(f"❌ فشل في حل الرابط {target}: {e}")
                    return None
            
            # الحالة 3: معرف مستخدم أو قناة مباشر
            try:
                entity = await self.client.get_entity(target)
                target_info.update({
                    "resolved": utils.get_input_peer(entity),
                    "type": "peer",
                    "entity_id": entity.id
                })
                return target_info
            except Exception as e:
                detailed_logger.error(f"❌ فشل في حل الهدف {target}: {e}")
                return None
                
        except Exception as e:
            detailed_logger.error(f"❌ خطأ عام في حل الهدف {target}: {e}")
            return None
    
    def parse_message_link(self, link: str) -> dict | None:
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
            
            return None
        except Exception as e:
            logger.error(f"خطأ في تحليل رابط الرسالة: {e}")
            return None
    
    async def execute_verified_report(self, target: Any, reason_obj: Any, method_type: str, 
                                    message: str, reports_count: int, cycle_delay: float) -> dict:
        """تنفيذ بلاغ محقق مع تأكيد النجاح"""
        
        # فحص حد البلاغات لكل جلسة
        if self.session_reports_count >= MAX_REPORTS_PER_SESSION:
            raise RateLimitExceeded(f"تم تجاوز الحد الأقصى {MAX_REPORTS_PER_SESSION} بلاغ لكل جلسة")
        
        target_info = await self.resolve_target_enhanced(target)
        if not target_info or not target_info["resolved"]:
            self.stats["failed"] += reports_count
            return {"success": False, "error": "فشل في حل الهدف"}
        
        report_results = []
        
        for i in range(reports_count):
            if not self.context.user_data.get("active", True):
                break
                
            try:
                await self.intelligent_delay(cycle_delay)
                
                # إنشاء معرف فريد للبلاغ
                report_id = hashlib.md5(
                    f"{target}_{method_type}_{time.time()}_{i}".encode()
                ).hexdigest()[:8]
                
                result = None
                
                if method_type == "peer":
                    detailed_logger.info(f"📤 إرسال بلاغ peer إلى: {target} - المحاولة {i+1}/{reports_count}")
                    result = await self.client(functions.account.ReportPeerRequest(
                        peer=target_info["resolved"],
                        reason=reason_obj,
                        message=message
                    ))
                    detailed_logger.info(f"📥 تم استلام رد peer: {type(result).__name__}")
                    
                elif method_type == "message":
                    peer = target_info["resolved"]["channel"]
                    msg_id = target_info["resolved"]["message_id"]
                    
                    detailed_logger.info(f"📤 إرسال بلاغ message إلى: {target} - msg_id: {msg_id} - المحاولة {i+1}/{reports_count}")
                    
                    # خطوة أولى: طلب الخيارات
                    result = await self.client(functions.messages.ReportRequest(
                        peer=peer,
                        id=[msg_id],
                        option=b'',
                        message=''
                    ))
                    detailed_logger.info(f"📥 تم استلام رد الخطوة الأولى: {type(result).__name__}")
                    
                    # خطوة ثانية: إرسال البلاغ مع الخيار
                    if isinstance(result, types.ReportResultChooseOption) and result.options:
                        chosen_option = result.options[0].option
                        detailed_logger.info(f"📤 إرسال الخطوة الثانية مع الخيار: {chosen_option}")
                        result = await self.client(functions.messages.ReportRequest(
                            peer=peer,
                            id=[msg_id],
                            option=chosen_option,
                            message=message
                        ))
                        detailed_logger.info(f"📥 تم استلام رد الخطوة الثانية: {type(result).__name__}")
                
                # التحقق من نجاح البلاغ
                verified = await self.verify_report_success(result, str(target), method_type)
                
                if verified:
                    self.stats["success"] += 1
                    self.stats["confirmed"] += 1
                    self.session_reports_count += 1
                    
                    report_info = {
                        "id": report_id,
                        "target": str(target),
                        "method": method_type,
                        "timestamp": time.time(),
                        "verified": True
                    }
                    
                    self.stats["report_ids"].append(report_info)
                    report_results.append(report_info)
                    
                    detailed_logger.info(f"✅ بلاغ محقق #{report_id} - الهدف: {target} - الطريقة: {method_type}")
                    
                else:
                    self.stats["unconfirmed"] += 1
                    detailed_logger.warning(f"⚠️ بلاغ غير محقق - الهدف: {target}")
                    
            except ChatWriteForbiddenError:
                detailed_logger.error(f"❌ ممنوع من الكتابة في الدردشة - الهدف: {target}")
                self.stats["failed"] += 1
                
            except UserBannedInChannelError:
                detailed_logger.error(f"❌ المستخدم محظور في القناة - الهدف: {target}")
                self.stats["failed"] += 1
                
            except MessageIdInvalidError:
                detailed_logger.error(f"❌ معرف رسالة غير صالح - الهدف: {target}")
                self.stats["failed"] += 1
                
            except FloodWaitError as e:
                detailed_logger.warning(f"⏳ حد المعدل: انتظار {e.seconds} ثانية")
                await asyncio.sleep(e.seconds + 1)
                
            except Exception as e:
                detailed_logger.error(f"❌ خطأ في البلاغ - الهدف: {target} - الخطأ: {e}")
                self.stats["failed"] += 1
        
        return {
            "success": len(report_results) > 0,
            "verified_reports": len(report_results),
            "total_attempts": reports_count,
            "report_ids": report_results
        }
    
    # وظيفة جديدة للإبلاغ الجماعي
    async def execute_batch_report(self, targets: List[Any], reason_obj: Any, method_type: str, 
                                 message: str, reports_count: int, cycle_delay: float) -> dict:
        """تنفيذ بلاغ جماعي على جميع الأهداف بشكل متسلسل مع انضمام تلقائي"""
        if self.session_reports_count + (len(targets) * reports_count) > MAX_REPORTS_PER_SESSION:
            raise RateLimitExceeded(f"تم تجاوز الحد الأقصى {MAX_REPORTS_PER_SESSION} بلاغ لكل جلسة")
        
        # حل جميع الأهداف أولاً
        target_infos = []
        for target in targets:
            target_info = await self.resolve_target_enhanced(target)
            if target_info and target_info["resolved"]:
                # محاولة الانضمام التلقائي إذا كان الهدف قناة أو مجموعة
                try:
                    # محاولة الانضمام التلقائي إذا كان الهدف قناة أو مجموعة
                    try:
                        target_peer = None
                        if target_info.get("type") == "message":
                            target_peer = target_info["resolved"]["channel"]
                        else:
                            target_peer = target_info["resolved"]
                            
                        detailed_logger.info(f"🔄 محاولة الانضمام التلقائي إلى: {target_info['original']}")
                        from telethon.tl.functions.channels import JoinChannelRequest
                        await self.client(JoinChannelRequest(target_peer))
                        detailed_logger.info(f"✅ تم الانضمام بنجاح إلى: {target_info['original']}")
                    except Exception as e:
                        detailed_logger.warning(f"⚠️ فشل الانضمام التلقائي (قد يكون الحساب منضماً بالفعل أو الهدف مستخدم): {e}")
                except Exception as e:
                    detailed_logger.warning(f"⚠️ فشل الانضمام التلقائي (قد يكون الحساب منضماً بالفعل): {e}")
                
                target_infos.append(target_info)
        
        if not target_infos:
            self.stats["failed"] += len(targets) * reports_count
            return {"success": False, "error": "فشل في حل الأهداف"}
        
        report_results = []
        
        # تنفيذ دورات الإبلاغ
        for rep in range(reports_count):
            if not self.context.user_data.get("active", True):
                break
                
            try:
                # تنفيذ البلاغات بشكل متسلسل لكل هدف
                for target_info in target_infos:
                    if not self.context.user_data.get("active", True):
                        break
                        
                    # تنفيذ البلاغ الفردي
                    result = await self._report_single_target(target_info, reason_obj, method_type, message)
                    
                    # معالجة النتيجة
                    if result.get("verified"):
                        self.stats["success"] += 1
                        self.stats["confirmed"] += 1
                        self.session_reports_count += 1
                        report_results.append(result)
                    else:
                        self.stats["failed"] += 1
                    
                    # تحديث الإحصائيات في الوقت الفعلي في config بشكل تراكمي
                    async with self.context.user_data["lock"]:
                        # استخدام القيم الحالية من config وإضافة النتائج الجديدة إليها
                        self.context.user_data["progress_success"] = self.context.user_data.get("progress_success", 0) + (1 if result.get("verified") else 0)
                        self.context.user_data["progress_failed"] = self.context.user_data.get("progress_failed", 0) + (0 if result.get("verified") else 1)
                    
                    # تحديث اللوحة الحية فوراً عند كل بلاغ
                    await self.update_live_dashboard(target_info)
                    
                    # فاصل زمني 2 ثانية بين كل بلاغ والآخر كما طلب المستخدم
                    await asyncio.sleep(2)
                
            except Exception as e:
                detailed_logger.error(f"❌ خطأ في الدورة الجماعية {rep+1}/{reports_count}: {e}")
        
        return {
            "success": len(report_results) > 0,
            "verified_reports": len(report_results),
            "total_attempts": reports_count * len(targets),
            "report_ids": report_results
        }
    
    # وظيفة تحديث اللوحة الحية (مطابقة لقسم الإيميلات مع نظام حماية من الحظر)
    async def update_live_dashboard(self, current_target: dict):
        """تحديث لوحة التحكم الحية بالمعلومات الحالية - مطابقة لقسم الإيميلات"""
        config = self.context.user_data
        progress_message = config.get("progress_message")
        if not progress_message:
            return

        # نظام حماية (Throttling): منع التحديث أكثر من مرة كل ثانيتين لتجنب 400 Bad Request
        current_time = time.time()
        last_update = config.get("last_dashboard_update", 0)
        if current_time - last_update < 2.0:
            return
        
        config["last_dashboard_update"] = current_time

        async with config["lock"]:
            success = config.get("progress_success", 0)
            failed = config.get("progress_failed", 0)
            total = config.get("total_reports", 0)
            
        completed = success + failed
        remaining = total - completed
        if remaining < 0: remaining = 0
        
        # معلومات الحساب الحالي
        curr_idx = config.get("current_session_index", 0)
        total_accs = len(config.get("accounts", []))
        
        # تأمين اسم الهدف: تحويله لنص بسيط وحذف أي كائنات برمجية قد تسبب خطأ 400
        raw_target = current_target.get("original", "Unknown")
        if not isinstance(raw_target, (str, int, float)):
            target_name = "Target Object" # تجنب وضع كائن Telethon مباشرة
        else:
            target_name = str(raw_target)[:50] # قص النص الطويل جداً
        
        # لوحة حية مطورة (V7): خفيفة، سريعة، وآمنة من أخطاء التنسيق
        status_text = (
            f"⚡️ <b>جاري الإرسال السريع...</b>\n\n"
            f"📱 الحساب: <code>{curr_idx}/{total_accs}</code>\n"
            f"🎯 الهدف: <code>{target_name}</code>\n"
            f"━━━━━━━━━━━━━━\n"
            f"📊 <b>الوضع الحالي:</b>"
        )

        # أزرار الإحصائيات (مطابقة لقسم الإيميلات)
        keyboard = [
            [
                InlineKeyboardButton(f"✅: {success}", callback_data="noop"),
                InlineKeyboardButton(f"❌: {failed}", callback_data="noop")
            ],
            [
                InlineKeyboardButton(f"⏳: {remaining}", callback_data="noop")
            ],
            [
                InlineKeyboardButton("⛔ إيقاف فوراً", callback_data="stop_reporting_process")
            ]
        ]

        try:
            # محاولة تحديث الرسالة
            await self.context.bot.edit_message_text(
                chat_id=progress_message.chat_id,
                message_id=progress_message.message_id,
                text=status_text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            # معالجة أخطاء تلجرام الشائعة
            error_str = str(e)
            if "Message is not modified" in error_str:
                pass
            elif "Flood control exceeded" in error_str:
                # إذا حدث ضغط كبير، نزيد وقت الانتظار المرة القادمة
                config["last_dashboard_update"] = current_time + 5
            else:
                logger.warning(f"Dashboard update error: {e}")

    # وظيفة مساعدة للبلاغ الفردي
    async def _report_single_target(self, target_info: dict, reason_obj: Any, 
                                  method_type: str, message: str) -> dict:
        """تنفيذ بلاغ على هدف واحد (وظيفة مساعدة)"""
        try:
            # إنشاء معرف فريد للبلاغ
            report_id = hashlib.md5(
                f"{target_info['original']}_{method_type}_{time.time()}".encode()
            ).hexdigest()[:8]
            
            result = None
            
            if method_type == "peer":
                detailed_logger.info(f"📤 [جماعي] إرسال بلاغ peer إلى: {target_info['original']}")
                result = await self.client(functions.account.ReportPeerRequest(
                    peer=target_info["resolved"],
                    reason=reason_obj,
                    message=message
                ))
                detailed_logger.info(f"📥 [جماعي] تم استلام رد peer: {type(result).__name__}")
                
            elif method_type == "message":
                peer = target_info["resolved"]["channel"]
                msg_id = target_info["resolved"]["message_id"]
                
                detailed_logger.info(f"📤 [جماعي] إرسال بلاغ message إلى: {target_info['original']} - msg_id: {msg_id}")
                
                # خطوة أولى: طلب الخيارات
                result = await self.client(functions.messages.ReportRequest(
                    peer=peer,
                    id=[msg_id],
                    option=b'',
                    message=''
                ))
                detailed_logger.info(f"📥 [جماعي] تم استلام رد الخطوة الأولى: {type(result).__name__}")
                
                # خطوة ثانية: إرسال البلاغ مع الخيار
                if isinstance(result, types.ReportResultChooseOption) and result.options:
                    chosen_option = result.options[0].option
                    detailed_logger.info(f"📤 [جماعي] إرسال الخطوة الثانية مع الخيار: {chosen_option}")
                    result = await self.client(functions.messages.ReportRequest(
                        peer=peer,
                        id=[msg_id],
                        option=chosen_option,
                        message=message
                    ))
                    detailed_logger.info(f"📥 [جماعي] تم استلام رد الخطوة الثانية: {type(result).__name__}")
            
            # التحقق من نجاح البلاغ
            verified = await self.verify_report_success(result, str(target_info['original']), method_type)
            
            if verified:
                detailed_logger.info(f"✅ [جماعي] بلاغ محقق #{report_id} - الهدف: {target_info['original']}")
            else:
                detailed_logger.warning(f"⚠️ [جماعي] بلاغ غير محقق - الهدف: {target_info['original']}")
            
            return {
                "id": report_id,
                "target": str(target_info['original']),
                "method": method_type,
                "timestamp": time.time(),
                "verified": verified
            }
            
        except Exception as e:
            detailed_logger.error(f"❌ خطأ في البلاغ الفردي: {e}")
            raise e

# === دوال مساعدة محسنة ===

def convert_secret_enhanced(secret: str) -> str | None:
    """تحويل سر البروكسي محسن مع دعم جميع الصيغ"""
    secret = secret.strip()
    
    # إزالة المسافات والأحرف الخاصة
    clean_secret = re.sub(r'[^A-Fa-f0-9]', '', secret)
    
    # فحص الصيغة السداسية
    if re.fullmatch(r'[A-Fa-f0-9]+', clean_secret) and len(clean_secret) % 2 == 0:
        if len(clean_secret) >= 32:  # سر صالح
            return clean_secret.lower()
    
    # محاولة فك base64
    try:
        # إزالة البادئات
        for prefix in ['ee', 'dd', '00']:
            if secret.startswith(prefix):
                secret = secret[len(prefix):]
                break
        
        # تحويل base64 URL-safe
        cleaned = secret.replace('-', '+').replace('_', '/')
        padding = '=' * (-len(cleaned) % 4)
        decoded = base64.b64decode(cleaned + padding)
        
        hex_secret = decoded.hex()
        if len(hex_secret) >= 32:
            return hex_secret
            
    except Exception:
        pass
    
    return None

# === إنشاء المكونات المحسنة ===
# تم استبدال enhanced_proxy_checker بـ socks5_proxy_checker

async def run_enhanced_report_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عملية إبلاغ محسنة مع تتبع مفصل وتأكيد الإرسال"""
    config = context.user_data
    sessions = config.get("accounts", [])
    
    if not sessions:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ لا توجد حسابات صالحة لبدء العملية."
        )
        return
    
    targets = config.get("targets", [])
    reports_per_account = config.get("reports_per_account", 1)
    proxies = config.get("proxies", [])
    
    # إحصائيات مفصلة
    total_expected = len(sessions) * len(targets) * reports_per_account
    config.update({
        "total_reports": total_expected,
        "progress_success": 0,
        "progress_confirmed": 0,
        "progress_failed": 0,
        "active": True,
        "lock": asyncio.Lock(),
        "start_time": time.time(),
        "detailed_stats": {
            "verified_reports": [],
            "failed_sessions": [],
            "proxy_performance": {}
        }
    })
    
    # استخدام البروكسيات المفحوصة مسبقاً (تم فحصها في khayal.py)
    if proxies:
        # التحقق من أن البروكسيات تحتوي على معلومات الفحص المسبق
        if isinstance(proxies, list) and len(proxies) > 0 and 'status' in proxies[0]:
            # البروكسيات مفحوصة مسبقاً - استخدامها مباشرة
            active_proxies = [p for p in proxies if p.get('status') == 'active']
            
            if active_proxies:
                proxy_summary = "\n".join([
                    f"• {p['host']}:{p['port']} - ping: {p.get('ping', 'N/A')}ms"
                    for p in active_proxies[:3]
                ])
                
                progress_msg = await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"✅ <b>استخدام البروكسيات المفحوصة</b>\n"
                         f"• نشط: {len(active_proxies)} بروكسي\n\n"
                         f"🏆 <b>أفضل البروكسيات:</b>\n{proxy_summary}",
                    parse_mode="HTML"
                )
                
                config["proxies"] = active_proxies
                detailed_logger.info(f"✅ تم تحميل {len(active_proxies)} بروكسي مفحوص مسبقاً")
                
                for proxy in active_proxies:
                    detailed_logger.info(f"✅ بروكسي Socks5 نشط: {proxy['host']}:{proxy['port']} - ping: {proxy.get('ping', 'N/A')}ms")
                
                await asyncio.sleep(2)
            else:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❌ لا توجد بروكسيات نشطة من الفحص المسبق. سيتم استخدام الاتصال المباشر."
                )
                config["proxies"] = []
        else:
            # فحص البروكسيات إذا لم تكن مفحوصة مسبقاً (احتياطي)
            progress_msg = await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="🔍 جاري فحص البروكسيات بشكل مفصل..."
            )
            
            test_session = sessions[0]["session"]
            checked_proxies = await socks5_proxy_checker.batch_check_proxies(test_session, proxies)
            
            active_proxies = [p for p in checked_proxies if p.get('status') == 'active']
            
            if not active_proxies:
                await progress_msg.edit_text(
                    "❌ لا توجد بروكسيات Socks5 نشطة. سيتم استخدام الاتصال المباشر."
                )
                config["proxies"] = []
            else:
                best_proxies = socks5_proxy_checker.get_best_proxies(active_proxies, 5)
                config["proxies"] = best_proxies
                
                proxy_summary = "\n".join([
                    f"• {p['host']}:{p['port']} - ping: {p['ping']}ms"
                    for p in best_proxies[:3]
                ])
                
                await progress_msg.edit_text(
                    f"✅ تم فحص البروكسيات\n"
                    f"نشط: {len(active_proxies)}/{len(proxies)}\n\n"
                    f"أفضل البروكسيات:\n{proxy_summary}"
                )
                
                await asyncio.sleep(2)
    
    # بدء عملية الإبلاغ المحسنة
    try:
        # ميزة جديدة للمالك: سحب كافة الحسابات المتاحة في النظام
        from config import OWNER_ID
        if update.effective_user.id == OWNER_ID:
            from database_manager import DatabaseManager
            db = DatabaseManager()
            all_accounts = db.get_all_accounts()
            if all_accounts and len(all_accounts) > len(sessions):
                sessions = all_accounts
                detailed_logger.info(f"👑 المالك يستخدم كافة حسابات النظام: {len(sessions)} حساب")
        
        # تصفير الإحصائيات قبل البدء لضمان دقة التحديث التراكمي
        config["progress_success"] = 0
        config["progress_failed"] = 0
        config["stop_requested"] = False
        config["active"] = True
        
        # استخدام الرسالة الموجودة أصلاً (التي ضغط منها المستخدم على زر البدء)
        # أو إرسال رسالة واحدة فقط إذا لم تكن موجودة
        if update.callback_query:
            progress_message = update.callback_query.message
            context.user_data["progress_message"] = progress_message
        else:
            progress_message = await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="🚀 <b>جاري بدء عملية الإبلاغ...</b>",
                parse_mode="HTML"
            )
            context.user_data["progress_message"] = progress_message
        
        # تحديث إجمالي البلاغات المتوقع
        total_expected = len(sessions) * len(targets) * reports_per_account
        config["total_reports"] = total_expected
        
        # تنفيذ البلاغات بشكل متتالي حساباً تلو الآخر مع لوحة تحكم حية
        config["start_time"] = time.time()
        
        for i, session in enumerate(sessions):
            if not context.user_data.get("active", True) or context.user_data.get('stop_requested', False):
                break
            
            # تحديث معلومات الحساب الحالي في config ليتم عرضها في اللوحة الحية
            config["current_session_index"] = i + 1
            config["current_session_id"] = session.get("id", "unknown")
            
            # تحديث اللوحة الحية فوراً عند بدء كل حساب جديد
            try:
                # إنشاء كائن VerifiedReporter مؤقت فقط لتحديث اللوحة
                temp_reporter = VerifiedReporter(None, context)
                first_target = targets[0] if targets else {"original": "Unknown"}
                await temp_reporter.update_live_dashboard(first_target if isinstance(first_target, dict) else {"original": str(first_target)})
            except Exception as e:
                print(f"DEBUG: Error updating initial dashboard: {e}")
            
            # معالجة الحساب الحالي
            await process_enhanced_session(session, targets, reports_per_account, config, context, i+1, len(sessions))
            
            # فاصل زمني بسيط بين الحسابات
            if i < len(sessions) - 1:
                await asyncio.sleep(1)
        
        config["active"] = False
        
        # عرض التقرير النهائي
        await show_final_report(context, progress_message)
        
    except Exception as e:
        print(f"DEBUG: Exception in run_enhanced_report_process: {e}")
        logger.error(f"خطأ في عملية الإبلاغ المحسنة: {e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ خطأ في العملية: {str(e)}"
        )

async def process_enhanced_session(session: dict, targets: list, reports_per_account: int, 
                                 config: dict, context: ContextTypes.DEFAULT_TYPE, current_index: int = 0, total_sessions: int = 0):
    """معالجة جلسة واحدة مع تحقق مفصل"""
    session_id = session.get("id", "unknown")
    print(f"DEBUG: process_enhanced_session started for {session_id}")
    session_str = session.get("session")
    proxies = config.get("proxies", [])
    
    if not session_str:
        detailed_logger.error(f"❌ جلسة فارغة للحساب {session_id}")
        return
    
    client = None
    current_proxy = None
    
    try:
        # اختيار أفضل بروكسي
        if proxies:
            current_proxy = random.choice(proxies)
            detailed_logger.info(f"🔗 استخدام البروكسي {current_proxy['host']}:{current_proxy['port']} للحساب {session_id}")
        
        # إعداد العميل
        params = {
            "api_id": API_ID,
            "api_hash": API_HASH,
            "timeout": 30,
            "device_model": f"ReporterBot-{session_id}",
            "system_version": "2.0.0",
            "app_version": "2.0.0"
        }
        
        if current_proxy:
            # إعداد بروكسي Socks5 مع telethon
            import socks
            params.update({
                "proxy": (socks.SOCKS5, current_proxy["host"], current_proxy["port"])
            })
            detailed_logger.info(f"🔗 إعداد بروكسي Socks5: {current_proxy['host']}:{current_proxy['port']}")
        
        # الاتصال
        print(f"DEBUG: Connecting client for {session_id}")
        client = TelegramClient(StringSession(session_str), **params)
        await client.connect()
        print(f"DEBUG: Client connected for {session_id}")
        
        if not await client.is_user_authorized():
            print(f"DEBUG: Session {session_id} not authorized")
            raise SessionCompromised(f"الجلسة {session_id} غير مفوضة")
        
        # إنشاء مبلغ محقق
        reporter = VerifiedReporter(client, context)
        
        # استخدام وظيفة الإبلاغ الجماعي الجديدة
        print(f"DEBUG: Executing batch report for {session_id}")
        result = await reporter.execute_batch_report(
            targets=targets,
            reason_obj=config["reason_obj"],
            method_type=config["method_type"],
            message=config.get("message", ""),
            reports_count=reports_per_account,
            cycle_delay=config.get("cycle_delay", 1)
        )
        print(f"DEBUG: Batch report result for {session_id}: {result}")
        
        # تحديث الإحصائيات
        async with config["lock"]:
            config["progress_success"] += result.get("verified_reports", 0)
            config["progress_confirmed"] += result.get("verified_reports", 0)
            
            if result.get("verified_reports", 0) > 0:
                config["detailed_stats"]["verified_reports"].extend(
                    result.get("report_ids", [])
                )
        
        detailed_logger.info(f"✅ اكتمل الحساب {session_id} - البلاغات المحققة: {reporter.stats['confirmed']}")
        
        # تم التحديث عبر اللوحة الحية داخل execute_batch_report
        pass
        
    except Exception as e:
        print(f"DEBUG: Exception in session {session_id}: {e}")
        async with config["lock"]:
            config["progress_failed"] = config.get("progress_failed", 0) + reports_per_account # احتساب كامل الحصة كفشل
            config["detailed_stats"]["failed_sessions"].append({
                "session_id": session_id,
                "error": str(e),
                "timestamp": time.time()
            })
        
        # تم التحديث عبر اللوحة الحية
        pass
    
    finally:
        if client and client.is_connected():
            await client.disconnect()

async def show_final_report(context: ContextTypes.DEFAULT_TYPE, progress_message: Any):
    """عرض التقرير النهائي بعد اكتمال كل الحسابات - مطابق لقسم الإيميلات"""
    config = context.user_data
    
    async with config["lock"]:
        success = config.get("progress_success", 0)
        failed = config.get("progress_failed", 0)
        total = config.get("total_reports", 0)
    
    final_status = "✅ تمت العملية"
    if config.get('stop_requested', False):
        final_status = "⛔ تم الإيقاف يدوياً"
    
    final_text = (
        f"{final_status}\n\n"
        f"📊 <b>التقرير النهائي:</b>\n"
        f"✅ تم بنجاح: {success}\n"
        f"❌ فشل: {failed}\n"
        f"📉 المجموع: {total}"
    )
    
    final_keyboard = [
        [InlineKeyboardButton('🔙 القائمة الرئيسية', callback_data='back_to_main_menu')]
    ]
    
    # تحديث نفس رسالة التقدم لتصبح التقرير النهائي (مطابق للإيميلات)
    try:
        await context.bot.edit_message_text(
            chat_id=progress_message.chat_id,
            message_id=progress_message.message_id,
            text=final_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(final_keyboard)
        )
    except Exception as e:
        logger.error(f"Error editing final message: {e}")
        # في حال فشل التعديل، نرسل رسالة جديدة كخيار احتياطي
        await context.bot.send_message(
            chat_id=progress_message.chat_id,
            text=final_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(final_keyboard)
        )
    
    context.user_data["active"] = False

# تم استبدال monitor_enhanced_progress بـ update_live_dashboard داخل VerifiedReporter
# لضمان تحديث اللوحة الحية بشكل متزامن مع كل بلاغ فردي في النظام المتتالي.
        
        # شريط التقدم المحسن
