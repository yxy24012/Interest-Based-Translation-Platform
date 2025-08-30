import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

def _debug_enabled() -> bool:
    return os.environ.get('EMAIL_DEBUG', 'false').lower() in ['1', 'true', 'yes']


def is_smtp_configured() -> bool:
    return bool(os.environ.get('SMTP_HOST') and os.environ.get('SMTP_PORT') and os.environ.get('SMTP_USER') and os.environ.get('SMTP_PASS') and os.environ.get('FROM_EMAIL'))


def get_from_name_by_lang(lang: str = 'zh') -> str:
    """根据语言获取发件者名称"""
    from_names = {
        'zh': '基于兴趣的翻译平台',
        'ja': '興味ベースの翻訳プラットフォーム',
        'en': 'Interest-Based Translation Platform',
        'ru': 'Платформа перевода на основе интересов',
        'ko': '관심 기반 번역 플랫폼',
        'fr': 'Plateforme de traduction basée sur les intérêts'
    }
    return from_names.get(lang, from_names['zh'])


def create_simple_text_email(content: str, message_type: str = 'general', user_lang: str = 'zh') -> str:
    """创建简洁易懂的纯文本邮件模板"""
    
    # 根据消息类型和语言选择不同的标题
    if message_type == 'friend':
        if user_lang == 'zh':
            title = '好友通知'
        elif user_lang == 'ja':
            title = '友達通知'
        elif user_lang == 'en':
            title = 'Friend Notification'
        elif user_lang == 'ru':
            title = 'Уведомление о друге'
        elif user_lang == 'ko':
            title = '친구 알림'
        elif user_lang == 'fr':
            title = 'Notification d\'ami'
        else:
            title = '好友通知'
        icon = '👥'
    elif message_type == 'translation':
        if user_lang == 'zh':
            title = '翻译通知'
        elif user_lang == 'ja':
            title = '翻訳通知'
        elif user_lang == 'en':
            title = 'Translation Notification'
        elif user_lang == 'ru':
            title = 'Уведомление о переводе'
        elif user_lang == 'ko':
            title = '번역 알림'
        elif user_lang == 'fr':
            title = 'Notification de traduction'
        else:
            title = '翻译通知'
        icon = '🌐'
    elif message_type == 'system':
        if user_lang == 'zh':
            title = '系统通知'
        elif user_lang == 'ja':
            title = 'システム通知'
        elif user_lang == 'en':
            title = 'System Notification'
        elif user_lang == 'ru':
            title = 'Системное уведомление'
        elif user_lang == 'ko':
            title = '시스템 알림'
        elif user_lang == 'fr':
            title = 'Notification système'
        else:
            title = '系统通知'
        icon = '🔔'
    else:
        if user_lang == 'zh':
            title = '平台通知'
        elif user_lang == 'ja':
            title = 'プラットフォーム通知'
        elif user_lang == 'en':
            title = 'Platform Notification'
        elif user_lang == 'ru':
            title = 'Уведомление платформы'
        elif user_lang == 'ko':
            title = '플랫폼 알림'
        elif user_lang == 'fr':
            title = 'Notification de plateforme'
        else:
            title = '平台通知'
        icon = '📧'
    
    # 根据语言获取发件者名称
    from_name = get_from_name_by_lang(user_lang)
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # 根据语言获取时间戳标签
    if user_lang == 'zh':
        time_label = '发送时间'
        sender_label = '发件者'
        disclaimer = '此邮件由系统自动发送，请勿直接回复。'
    elif user_lang == 'ja':
        time_label = '送信時間'
        sender_label = '送信者'
        disclaimer = 'このメールはシステムによって自動送信されています。直接返信しないでください。'
    elif user_lang == 'en':
        time_label = 'Sent Time'
        sender_label = 'Sender'
        disclaimer = 'This email is automatically sent by the system. Please do not reply directly.'
    elif user_lang == 'ru':
        time_label = 'Время отправки'
        sender_label = 'Отправитель'
        disclaimer = 'Это письмо автоматически отправляется системой. Пожалуйста, не отвечайте напрямую.'
    elif user_lang == 'ko':
        time_label = '전송 시간'
        sender_label = '발신자'
        disclaimer = '이 이메일은 시스템에 의해 자동으로 전송됩니다. 직접 회신하지 마세요.'
    elif user_lang == 'fr':
        time_label = 'Heure d\'envoi'
        sender_label = 'Expéditeur'
        disclaimer = 'Cet e-mail est automatiquement envoyé par le système. Veuillez ne pas répondre directement.'
    else:
        time_label = '发送时间'
        sender_label = '发件者'
        disclaimer = '此邮件由系统自动发送，请勿直接回复。'
    
    # 创建简洁的纯文本邮件模板
    text_template = f"""
{icon} {title}
{'=' * 50}

{content}

{'=' * 50}
{time_label}: {current_time}
{sender_label}: {from_name}

---
{disclaimer}
"""
    
    return text_template.strip()


def send_email(to_email: str, subject: str, text_body: str, html_body: str = None, message_type: str = 'general', user_lang: str = 'zh') -> None:
    if not to_email:
        return
    if not is_smtp_configured():
        if _debug_enabled():
            print('[EMAIL_DEBUG] SMTP not configured, skip sending')
        return

    host = os.environ.get('SMTP_HOST')
    port = int(os.environ.get('SMTP_PORT', '587'))
    user = os.environ.get('SMTP_USER')
    password = os.environ.get('SMTP_PASS')
    use_tls = os.environ.get('SMTP_USE_TLS', 'true').lower() in ['1', 'true', 'yes']
    use_ssl = os.environ.get('SMTP_USE_SSL', 'false').lower() in ['1', 'true', 'yes']
    from_email = os.environ.get('FROM_EMAIL')
    # 根据用户语言偏好设置发件者名称
    from_name = get_from_name_by_lang(user_lang)

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"{from_name} <{from_email}>"
    msg['To'] = to_email

    # 使用简洁的纯文本邮件模板
    if text_body:
        formatted_text = create_simple_text_email(text_body, message_type, user_lang)
        msg.attach(MIMEText(formatted_text, 'plain', 'utf-8'))
    
    # 不再使用HTML内容，只发送纯文本邮件
    # 注释掉HTML相关代码
    # if not html_body:
    #     html_body = create_html_email(text_body, message_type)
    # if html_body:
    #     msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    server = None
    try:
        if _debug_enabled():
            print(f"[EMAIL_DEBUG] Connect SMTP host={host} port={port} ssl={use_ssl} tls={use_tls}")
        if use_ssl:
            server = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            server.ehlo()
            if use_tls:
                server.starttls()
                server.ehlo()
        if user and password:
            if _debug_enabled():
                print(f"[EMAIL_DEBUG] Login as {user}")
            server.login(user, password)
        if _debug_enabled():
            print(f"[EMAIL_DEBUG] Send mail from={from_email} to={to_email} subject={subject}")
        server.sendmail(from_email, [to_email], msg.as_string())
        if _debug_enabled():
            print("[EMAIL_DEBUG] Send mail OK")
    finally:
        if server:
            try:
                server.quit()
            except Exception:
                pass


