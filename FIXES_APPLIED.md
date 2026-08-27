# التعديلات المطبقة على نظام الإبلاغ

## تاريخ التعديل
24 يناير 2026

## المشاكل التي تم إصلاحها

### 1. مشكلة التعليق في أزرار اختيار نوع الإبلاغ الداخلي

**الوصف:** عند استخدام أزرار الإبلاغ للمرة الثانية، كان البوت يتجمد ولا يستجيب رغم ظهور الاستجابة في Termux.

**السبب:** عدم وجود معالجات callback صحيحة لأزرار "رجوع" في جميع حالات المحادثة (ConversationHandler states).

**الحل المطبق:**
تم إضافة معالج `CallbackQueryHandler(cancel_operation, pattern='^cancel$')` لجميع حالات المحادثة في الملفات التالية:

1. **Telegram/report_peer.py** (بلاغ عضو)
   - SELECT_REASON
   - ENTER_TARGET
   - ENTER_DETAILS
   - تم إضافة معالجات الرجوع الصحيحة

2. **Telegram/report_message.py** (بلاغ رسالة)
   - SELECT_REASON
   - ENTER_TARGETS
   - ENTER_DETAILS
   - ENTER_REPORT_COUNT
   - ENTER_DELAY
   - تم إضافة معالجات الرجوع الصحيحة

3. **Telegram/report_photo.py** (صورة شخصية)
   - SELECT_REASON
   - ENTER_TARGET
   - ENTER_DETAILS
   - ENTER_REPORT_COUNT
   - ENTER_DELAY
   - تم إضافة معالجات الرجوع الصحيحة

4. **Telegram/report_sponsored.py** (إعلان ممول)
   - ENTER_TARGET
   - ENTER_REPORT_COUNT
   - ENTER_DELAY
   - تم إضافة معالجات الرجوع الصحيحة

5. **Telegram/report_bot_messages.py** (رسائل بوت)
   - SELECT_REASON
   - ENTER_BOT_USERNAME
   - ENTER_DETAILS
   - ENTER_REPORT_COUNT
   - ENTER_DELAY
   - تم إضافة معالجات الرجوع الصحيحة

6. **Telegram/report_mass.py** (بلاغ جماعي)
   - SELECT_REASON
   - ENTER_CHANNEL
   - SELECT_POSTS_OPTION
   - ENTER_MEDIA_LIMIT
   - ENTER_POSTS_NUMBER
   - ENTER_DAYS
   - ENTER_DETAILS
   - ENTER_REPORT_COUNT
   - ENTER_DELAY
   - تم إضافة معالجات الرجوع الصحيحة

7. **Telegram/research.py** (بلاغ بحث)
   - كان يحتوي بالفعل على المعالجات الصحيحة

### 2. تفعيل قائمة الإحصائيات

**الوصف:** قائمة الإحصائيات لم تكن تعمل بشكل صحيح.

**السبب:** دالة `user_stats_command` في `Telegram/admin_panel.py` كانت تحاول الوصول إلى فهارس خاطئة في صف قاعدة البيانات.

**الحل المطبق:**
تم تحديث دالة `user_stats_command` لتتوافق مع البنية الصحيحة لجدول users:
- العمود 6: total_email_reports
- العمود 7: total_telegram_reports
- العمود 8: external_emails_count

تم إضافة فحص آمن للتأكد من وجود الأعمدة قبل الوصول إليها لتجنب أخطاء IndexError.

## النتيجة النهائية (تحديث شامل)

✅ **إصلاح جذري للتعليق:** تم تعديل دالة `cancel_operation` و `back_to_main_menu` لتنهي المحادثة (ConversationHandler) بشكل قطعي وتعود للقائمة الرئيسية، مما يمنع تداخل الحالات الذي كان يسبب تعطل الأزرار عند الاستخدام المتكرر.
✅ **إصلاح الإحصائيات:** تم تعديل دالة `user_stats_command` لتجلب البيانات مباشرة من قاعدة البيانات باستخدام استعلام SQL محدد، مما يضمن ظهور الأرقام الصحيحة وتجنب أخطاء الفهارس.
✅ **استقرار الأزرار:** تم إضافة `query.answer()` لجميع معالجات الأزرار لمنع ظهور أيقونة الساعة (التعليق) في واجهة التليجرام.
✅ **تحسين التنقل:** زر "رجوع" الآن يعيد المستخدم دائماً إلى نقطة بداية مستقرة (القائمة الرئيسية) مع تنظيف البيانات المؤقتة فقط.
✅ **دعم بروكسيات MTProto:** تم تفعيل دعم بروكسيات MTProto بالكامل في نظام الإبلاغ، بما في ذلك الروابط المباشرة وصيغة `IP:PORT:SECRET`.
✅ **إصلاح تعليق البوت وتخطي البروكسي البطيء:** تم تحويل نظام الاتصال ليكون غير متزامناً (Async) بالكامل مع تقليل مهلة الانتظار (Timeout) إلى 7 ثوانٍ فقط. هذا يضمن أن البوت لن يضيع وقتاً على بروكسيات بطيئة، وسيقوم بتخطيها فوراً لضمان استمرار عملية الإبلاغ بسرعة عالية.

## ملاحظات للمطور

- **إصلاح التعليق:** تم إلغاء استخدام `socks.set_default_proxy()` و `socket.socket = socks.socksocket` لأنها كانت تسبب تجميداً للخيط الرئيسي (Main Thread). تم استبدالها بتمرير البروكسي مباشرة لـ `TelegramClient` لضمان اتصال غير متزامن بالكامل.
- **دعم MTProto:** تم تعديل `common.py` و `common_improved.py` ليتعرفا على نوع البروكسي تلقائياً. عند استخدام MTProto، يتم تمرير البروكسي لـ Telethon كـ Tuple `(host, port, secret)`.
- **صيغ البروكسي المدعومة:**
  1. `IP:PORT` (Socks5)
  2. `IP:PORT:SECRET` (MTProto)
  3. `https://t.me/proxy?server=...` (MTProto Link)

## نصائح حول البروكسي (للمستخدم)

1. **Socks5 (الأفضل):** يعتبر الأسرع والأكثر استقراراً لعمليات الإبلاغ المكثفة، خاصة إذا كان خاصاً (Private).
2. **MTProto:** جيد لتجاوز الحجب، لكنه قد يكون أبطأ في الاستجابة مقارنة بـ Socks5.
3. **تجنب البروكسيات العامة:** البروكسيات المجانية المنتشرة غالباً ما تكون بطيئة جداً وتسبب فشل البلاغات، يُفضل دائماً استخدام بروكسيات مدفوعة أو خاصة لضمان أفضل نتيجة.
