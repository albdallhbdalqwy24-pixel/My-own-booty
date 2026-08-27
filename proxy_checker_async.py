"""
وحدة فحص البروكسيات بشكل غير متزامن (Async)
تحل مشكلة تعليق البوت عند إضافة البروكسيات
"""

import asyncio
import time
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


async def check_single_proxy(proxy: Dict, timeout: int = 3) -> Dict:
    """
    فحص بروكسي واحد بشكل غير متزامن
    
    Args:
        proxy: معلومات البروكسي (host, port, type, etc.)
        timeout: المهلة الزمنية بالثواني
        
    Returns:
        البروكسي مع معلومات الحالة والسرعة
    """
    try:
        start_time = time.time()
        
        if proxy.get('type') == 'mtproto':
            # فحص MTProto: فحص أولي للاتصال بالمنفذ
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(proxy['host'], proxy['port']),
                    timeout=timeout
                )
                ping = int((time.time() - start_time) * 1000)
                writer.close()
                await writer.wait_closed()
                
                proxy['status'] = 'active'
                proxy['ping'] = ping
                proxy['last_check'] = time.time()
                return proxy
                
            except Exception as e:
                proxy['status'] = 'failed'
                proxy['error'] = str(e)
                proxy['last_check'] = time.time()
                return proxy
        else:
            # فحص Socks5 باستخدام PySocks
            try:
                import socks
                import socket
                
                # تشغيل الفحص في executor لأن PySocks ليس async
                loop = asyncio.get_event_loop()
                
                def sync_check():
                    s = socks.socksocket()
                    s.set_proxy(socks.SOCKS5, proxy['host'], proxy['port'])
                    s.settimeout(timeout)
                    s.connect(("8.8.8.8", 53))
                    ping = int((time.time() - start_time) * 1000)
                    s.close()
                    return ping
                
                ping = await asyncio.wait_for(
                    loop.run_in_executor(None, sync_check),
                    timeout=timeout + 1
                )
                
                proxy['status'] = 'active'
                proxy['ping'] = ping
                proxy['last_check'] = time.time()
                return proxy
                
            except Exception as e:
                proxy['status'] = 'failed'
                proxy['error'] = str(e)
                proxy['last_check'] = time.time()
                return proxy
                
    except Exception as e:
        logger.error(f"خطأ في فحص البروكسي {proxy.get('host')}:{proxy.get('port')}: {e}")
        proxy['status'] = 'failed'
        proxy['error'] = str(e)
        proxy['last_check'] = time.time()
        return proxy


async def check_proxies_batch(
    proxies: List[Dict],
    max_concurrent: int = 20,
    timeout: int = 3,
    progress_callback=None
) -> List[Dict]:
    """
    فحص مجموعة من البروكسيات بشكل متوازي
    
    Args:
        proxies: قائمة البروكسيات للفحص
        max_concurrent: الحد الأقصى للفحوصات المتزامنة
        timeout: المهلة الزمنية لكل فحص
        progress_callback: دالة callback لتحديث التقدم (optional)
        
    Returns:
        قائمة البروكسيات مع نتائج الفحص
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def check_with_semaphore(proxy: Dict, index: int) -> Dict:
        async with semaphore:
            result = await check_single_proxy(proxy, timeout)
            
            # استدعاء callback للتقدم إن وجد
            if progress_callback:
                try:
                    await progress_callback(index + 1, len(proxies), result)
                except Exception as e:
                    logger.error(f"خطأ في progress callback: {e}")
            
            return result
    
    # فحص جميع البروكسيات بشكل متوازي
    tasks = [check_with_semaphore(proxy, i) for i, proxy in enumerate(proxies)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # معالجة النتائج والاستثناءات
    checked_proxies = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"خطأ في فحص البروكسي {i}: {result}")
            proxies[i]['status'] = 'failed'
            proxies[i]['error'] = str(result)
            checked_proxies.append(proxies[i])
        else:
            checked_proxies.append(result)
    
    return checked_proxies


def get_proxy_statistics(proxies: List[Dict]) -> Dict:
    """
    حساب إحصائيات البروكسيات
    
    Args:
        proxies: قائمة البروكسيات المفحوصة
        
    Returns:
        dict يحتوي على الإحصائيات
    """
    total = len(proxies)
    active = [p for p in proxies if p.get('status') == 'active']
    failed = [p for p in proxies if p.get('status') == 'failed']
    
    stats = {
        'total': total,
        'active_count': len(active),
        'failed_count': len(failed),
        'success_rate': (len(active) / total * 100) if total > 0 else 0,
        'average_ping': sum(p.get('ping', 0) for p in active) / len(active) if active else 0,
        'best_proxies': sorted(active, key=lambda x: x.get('ping', 9999))[:5]
    }
    
    return stats


def format_proxy_results(stats: Dict) -> str:
    """
    تنسيق نتائج الفحص للعرض
    
    Args:
        stats: إحصائيات البروكسيات
        
    Returns:
        نص منسق للعرض
    """
    text = (
        f"✅ <b>تم اعتماد البروكسيات!</b>\n\n"
        f"📊 <b>نتائج الفحص:</b>\n"
        f"• الإجمالي: {stats['total']}\n"
        f"• ✅ تعمل: {stats['active_count']}\n"
        f"• ❌ معطلة: {stats['failed_count']}\n"
        f"• 📈 نسبة النجاح: {stats['success_rate']:.1f}%\n"
    )
    
    if stats['active_count'] > 0:
        text += f"• ⚡ متوسط السرعة: {stats['average_ping']:.0f}ms\n\n"
        text += "🏆 <b>أفضل 5 بروكسيات:</b>\n"
        for p in stats['best_proxies']:
            text += f"✓ {p['host']}:{p['port']} ⚡ {p['ping']}ms\n"
        text += "\nسيتم استخدامها في عملية الإبلاغ."
    else:
        text += "\n⚠️ لم يعمل أي بروكسي، سيتم استخدام الاتصال المباشر."
    
    return text
