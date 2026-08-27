# DrKhayal/config_enhanced.py - إعدادات النظام المحسن

import os
from dataclasses import dataclass
from typing import List, Dict, Optional

@dataclass
class ProxySettings:
    """إعدادات البروكسي المحسنة"""
    check_timeout: int = 15  # ثانية لاختبار البروكسي
    recheck_interval: int = 300  # 5 دقائق
    max_retries: int = 3
    concurrent_checks: int = 3  # فحوصات متزامنة
    quality_threshold: int = 50  # الحد الأدنى لنقائق الجودة
    max_ping: int = 5000  # أقصى ping مقبول بالملي ثانية

@dataclass
class ReportSettings:
    """إعدادات البلاغات المحسنة"""
    confirmation_timeout: int = 10  # ثانية للتأكيد
    max_reports_per_session: int = 50  # الحد الأقصى للبلاغات لكل جلسة
    min_delay_between_reports: float = 1.5  # الحد الأدنى للتأخير بين البلاغات
    max_delay_between_reports: float = 5.0  # الحد الأقصى للتأخير
    retry_failed_reports: bool = True
    max_report_retries: int = 2
    
@dataclass
class SessionSettings:
    """إعدادات الجلسات المحسنة"""
    connection_timeout: int = 30  # ثانية
    max_concurrent_sessions: int = 10  # عدد الجلسات المتزامنة
    session_health_check: bool = True
    auto_disconnect_inactive: bool = True
    inactive_timeout: int = 300  # 5 دقائق
    
@dataclass
class LoggingSettings:
    """إعدادات التسجيل المحسنة"""
    detailed_logging: bool = True
    log_file_path: str = "detailed_reports.log"
    max_log_size_mb: int = 100
    backup_log_count: int = 5
    log_level: str = "INFO"
    include_proxy_performance: bool = True
    include_session_stats: bool = True

@dataclass
class GPT5Settings:
    """إعدادات نموذج GPT-5 المتقدمة"""
    enable_gpt5_for_all_clients: bool = True  # تفعيل GPT-5 لجميع العملاء
    gpt5_model: str = "gpt-5"
    gpt5_api_version: str = "v2"
    max_tokens_per_request: int = 2048
    temperature: float = 0.7
    top_p: float = 0.9
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    enable_gpt5_caching: bool = True
    cache_ttl: int = 3600  # ثانية
    fallback_to_gpt4: bool = True  # الرجوع لـ GPT-4 في حالة الخطأ
    
@dataclass
class SecuritySettings:
    """إعدادات الأمان المحسنة"""
    rate_limit_enabled: bool = True
    max_reports_per_hour: int = 1000
    max_reports_per_day: int = 5000
    detect_suspicious_activity: bool = True
    auto_pause_on_errors: bool = True
    error_threshold: int = 10  # عدد الأخطاء المتتالية قبل الإيقاف
    
@dataclass
class EnhancedConfig:
    """التكوين الشامل للنظام المحسن"""
    proxy: ProxySettings
    report: ReportSettings
    session: SessionSettings
    logging: LoggingSettings
    security: SecuritySettings
    gpt5: GPT5Settings
    
    # إعدادات عامة
    debug_mode: bool = False
    test_mode: bool = False  # وضع اختبار بدون إرسال بلاغات حقيقية
    api_id: int = int(os.getenv('TG_API_ID', '26924046'))
    api_hash: str = os.getenv('TG_API_HASH', '4c6ef4cee5e129b7a674de156e2bcc15')
    bot_token: str = os.getenv('BOT_TOKEN', '8574090608:AAGjzWfRslJHnZghRiyUiRPeJT5iNb4vW9I')
    
    @classmethod
    def create_default(cls) -> 'EnhancedConfig':
        """إنشاء تكوين افتراضي محسن"""
        return cls(
            proxy=ProxySettings(),
            report=ReportSettings(),
            session=SessionSettings(),
            logging=LoggingSettings(),
            security=SecuritySettings(),
            gpt5=GPT5Settings()
        )
    
    @classmethod
    def create_production(cls) -> 'EnhancedConfig':
        """إنشاء تكوين للبيئة الإنتاجية"""
        config = cls.create_default()
        
        # إعدادات أكثر تحفظاً للإنتاج
        config.proxy.check_timeout = 20
        config.proxy.concurrent_checks = 2
        config.report.max_reports_per_session = 30
        config.report.min_delay_between_reports = 2.0
        config.report.max_delay_between_reports = 8.0
        config.session.max_concurrent_sessions = 5
        config.security.max_reports_per_hour = 500
        config.security.error_threshold = 5
        
        return config
    
    @classmethod
    def create_testing(cls) -> 'EnhancedConfig':
        """إنشاء تكوين للاختبار"""
        config = cls.create_default()
        
        # إعدادات للاختبار
        config.test_mode = True
        config.debug_mode = True
        config.proxy.check_timeout = 10
        config.proxy.concurrent_checks = 1
        config.report.max_reports_per_session = 5
        config.session.max_concurrent_sessions = 2
        config.logging.log_level = "DEBUG"
        
        return config
    
    def validate(self) -> List[str]:
        """التحقق من صحة الإعدادات"""
        errors = []
        
        if self.proxy.check_timeout <= 0:
            errors.append("مهلة فحص البروكسي يجب أن تكون أكبر من صفر")
            
        if self.proxy.concurrent_checks <= 0:
            errors.append("عدد الفحوصات المتزامنة يجب أن يكون أكبر من صفر")
            
        if self.report.max_reports_per_session <= 0:
            errors.append("الحد الأقصى للبلاغات يجب أن يكون أكبر من صفر")
            
        if self.report.min_delay_between_reports < 0:
            errors.append("الحد الأدنى للتأخير لا يمكن أن يكون سالباً")
            
        if self.report.min_delay_between_reports > self.report.max_delay_between_reports:
            errors.append("الحد الأدنى للتأخير لا يمكن أن يكون أكبر من الحد الأقصى")
            
        if self.session.max_concurrent_sessions <= 0:
            errors.append("عدد الجلسات المتزامنة يجب أن يكون أكبر من صفر")
            
        if not self.api_id or not self.api_hash:
            errors.append("API ID و API Hash مطلوبان")
        
        # التحقق من إعدادات GPT-5
        if self.gpt5.max_tokens_per_request <= 0:
            errors.append("الحد الأقصى للـ tokens يجب أن يكون أكبر من صفر")
            
        if not 0 <= self.gpt5.temperature <= 2:
            errors.append("قيمة temperature يجب أن تكون بين 0 و 2")
            
        if not 0 <= self.gpt5.top_p <= 1:
            errors.append("قيمة top_p يجب أن تكون بين 0 و 1")
            
        return errors

# إنشاء التكوين الافتراضي
default_config = EnhancedConfig.create_default()

# التحقق من متغير البيئة لتحديد نوع التكوين
env_mode = os.getenv('ENHANCED_MODE', 'default').lower()

if env_mode == 'production':
    enhanced_config = EnhancedConfig.create_production()
elif env_mode == 'testing':
    enhanced_config = EnhancedConfig.create_testing()
else:
    enhanced_config = default_config

# التحقق من صحة التكوين
config_errors = enhanced_config.validate()
if config_errors:
    print("⚠️ أخطاء في التكوين:")
    for error in config_errors:
        print(f"  - {error}")

# معلومات التكوين الحالي
print(f"✅ تم تحميل التكوين: {env_mode}")
print(f"📊 الإعدادات:")
print(f"  - فحص البروكسي: {enhanced_config.proxy.concurrent_checks} متزامن، timeout: {enhanced_config.proxy.check_timeout}s")
print(f"  - البلاغات: حد أقصى {enhanced_config.report.max_reports_per_session}/جلسة")
print(f"  - الجلسات: حد أقصى {enhanced_config.session.max_concurrent_sessions} متزامن")
print(f"  - الأمان: {enhanced_config.security.max_reports_per_hour} بلاغ/ساعة")
print(f"🤖 GPT-5:")
print(f"  - مفعّل لجميع العملاء: {'✅ نعم' if enhanced_config.gpt5.enable_gpt5_for_all_clients else '❌ لا'}")
print(f"  - النموذج: {enhanced_config.gpt5.gpt5_model}")
print(f"  - إصدار API: {enhanced_config.gpt5.gpt5_api_version}")
print(f"  - الحد الأقصى للـ tokens: {enhanced_config.gpt5.max_tokens_per_request}")
print(f"  - Temperature: {enhanced_config.gpt5.temperature}")
print(f"  - التخزين المؤقت: {'✅ مفعّل' if enhanced_config.gpt5.enable_gpt5_caching else '❌ معطّل'}")