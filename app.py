# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from sqlalchemy import or_, and_, func
from sqlalchemy import event
from mail_utils import send_email, is_smtp_configured

# 加载 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///forum.db'
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'my-very-strong-and-unique-secret-key-2024')
app.config['UPLOAD_FOLDER'] = 'uploads'
db = SQLAlchemy(app)

# 确保上传文件夹存在
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# 启动时自动补充缺失列（SQLite 简易处理）
try:
    with app.app_context():
        inspector = db.inspect(db.engine)
        user_cols = [c['name'] for c in inspector.get_columns('user')]
        if 'email_notifications_enabled' not in user_cols:
            with db.engine.connect() as conn:
                conn.execute(db.text('ALTER TABLE user ADD COLUMN email_notifications_enabled BOOLEAN DEFAULT 1'))
        if 'is_reviewer' not in user_cols:
            with db.engine.connect() as conn:
                conn.execute(db.text('ALTER TABLE user ADD COLUMN is_reviewer BOOLEAN DEFAULT 0'))
        if 'is_creator' not in user_cols:
            with db.engine.connect() as conn:
                conn.execute(db.text('ALTER TABLE user ADD COLUMN is_creator BOOLEAN DEFAULT 0'))
        if 'experience' not in user_cols:
            with db.engine.connect() as conn:
                conn.execute(db.text('ALTER TABLE user ADD COLUMN experience INTEGER DEFAULT 0'))
        if 'preferred_language' not in user_cols:
            with db.engine.connect() as conn:
                conn.execute(db.text('ALTER TABLE user ADD COLUMN preferred_language VARCHAR(10) DEFAULT \'zh\''))
except Exception:
    pass



# 支持的语言列表（用于自动检测和校验）
SUPPORTED_LANGS = ['zh', 'ja', 'en', 'ru', 'ko', 'fr']


def _normalize_lang_code(lang_code: str) -> str:
    """将类似 zh-CN, en-US 的语言代码归一到 zh, en 等。

    只保留主语言部分，并确保在支持列表中。
    """
    if not lang_code:
        return ''
    primary = lang_code.split('-')[0].lower()
    return primary if primary in SUPPORTED_LANGS else ''


def detect_best_language_from_request() -> str:
    """从请求的 Accept-Language 中选择最佳支持语言，若无匹配则返回 en。"""
    try:
        # request.accept_languages 是一个 (lang, quality) 的序列，已按质量降序
        for lang, _q in request.accept_languages:
            normalized = _normalize_lang_code(lang)
            if normalized:
                return normalized
    except Exception:
        pass
    # 没有匹配则回退英语
    return 'en'


@app.before_request
def ensure_session_language():
    """在未登录情况下，根据浏览器语言自动设置会话语言。

    - 若会话中无语言或语言不受支持，则根据 Accept-Language 设定。
    - 已登录用户不在此处强制覆盖，保持其个人偏好逻辑。
    """
    try:
        if not is_logged_in():
            lang_in_session = session.get('lang')
            if not lang_in_session or lang_in_session not in SUPPORTED_LANGS:
                session['lang'] = detect_best_language_from_request()
    except Exception:
        # 任何异常均回退到英语，避免阻断请求
        session['lang'] = 'en'


# 多语言消息函数
def get_message(key, lang=None, **kwargs):
    if lang is None:
        # 优先使用用户的偏好语言，如果没有则使用会话语言
        if is_logged_in():
            user = get_current_user()
            lang = getattr(user, 'preferred_language', 'zh')
        else:
            lang = session.get('lang', 'zh')
    
    messages = {
        'username_exists': {
            'zh': '用户名已存在',
            'ja': 'ユーザー名は既に存在します',
            'en': 'Username already exists',
            'ru': 'Имя пользователя уже существует',
            'ko': '사용자명이 이미 존재합니다',
            'fr': 'Le nom d\'utilisateur existe déjà'
        },
        'email_exists': {
            'zh': '邮箱已被注册',
            'ja': 'メールアドレスは既に登録されています',
            'en': 'Email has already been registered',
            'ru': 'Электронная почта уже зарегистрирована',
            'ko': '이메일이 이미 등록되어 있습니다',
            'fr': 'L\'email a déjà été enregistré'
        },
        'register_success': {
            'zh': '注册成功，已自动登录',
            'ja': '登録成功、自動ログインしました',
            'en': 'Registration successful, automatically logged in',
            'ru': 'Регистрация успешна, автоматический вход выполнен',
            'ko': '등록 성공, 자동 로그인되었습니다',
            'fr': 'Inscription réussie, connexion automatique effectuée'
        },
        'welcome_back': {
            'zh': '欢迎回来，{}！',
            'ja': 'おかえりなさい、{}さん！',
            'en': 'Welcome back, {}!',
            'ru': 'Добро пожаловать обратно, {}!',
            'ko': '다시 오신 것을 환영합니다, {}!',
            'fr': 'Bon retour, {}!'
        },
        'login': {
            'zh': '登录',
            'ja': 'ログイン',
            'en': 'Login',
            'ru': 'Вход',
            'ko': '로그인',
            'fr': 'Connexion'
        },
        'username': {
            'zh': '用户名',
            'ja': 'ユーザー名',
            'en': 'Username',
            'ru': 'Имя пользователя',
            'ko': '사용자 이름',
            'fr': 'Nom d\'utilisateur'
        },
        'password': {
            'zh': '密码',
            'ja': 'パスワード',
            'en': 'Password',
            'ru': 'Пароль',
            'ko': '비밀번호',
            'fr': 'Mot de passe'
        },
        'enter_username': {
            'zh': '请输入用户名',
            'ja': 'ユーザー名を入力',
            'en': 'Enter username',
            'ru': 'Введите имя пользователя',
            'ko': '사용자 이름 입력',
            'fr': 'Entrez le nom d\'utilisateur'
        },
        'enter_password': {
            'zh': '请输入密码',
            'ja': 'パスワードを入力',
            'en': 'Enter password',
            'ru': 'Введите пароль',
            'ko': '비밀번호 입력',
            'fr': 'Entrez le mot de passe'
        },
        'no_account': {
            'zh': '还没有账户？',
            'ja': 'アカウントをお持ちでない場合',
            'en': 'Don\'t have an account?',
            'ru': 'Нет аккаунта?',
            'ko': '계정이 없으신가요?',
            'fr': 'Vous n\'avez pas de compte?'
        },
        'register_now': {
            'zh': '立即注册',
            'ja': '新規登録',
            'en': 'Register Now',
            'ru': 'Зарегистрироваться',
            'ko': '지금 등록',
            'fr': 'S\'inscrire maintenant'
        },
        'please_enter_username': {
            'zh': '请输入用户名',
            'ja': 'ユーザー名を入力してください',
            'en': 'Please enter username',
            'ru': 'Пожалуйста, введите имя пользователя',
            'ko': '사용자 이름을 입력해 주세요',
            'fr': 'Veuillez entrer le nom d\'utilisateur'
        },
        'please_enter_password': {
            'zh': '请输入密码',
            'ja': 'パスワードを入力してください',
            'en': 'Please enter password',
            'ru': 'Пожалуйста, введите пароль',
            'ko': '비밀번호를 입력해 주세요',
            'fr': 'Veuillez entrer le mot de passe'
        },
        'login_error': {
            'zh': '用户名或密码错误',
            'ja': 'ユーザー名またはパスワードが間違っています',
            'en': 'Incorrect username or password',
            'ru': 'Неверное имя пользователя или пароль',
            'ko': '잘못된 사용자명 또는 비밀번호',
            'fr': 'Nom d\'utilisateur ou mot de passe incorrect'
        },
        'logout_success': {
            'zh': '已成功登出',
            'ja': 'ログアウトしました',
            'en': 'Successfully logged out',
            'ru': 'Успешно вышли из системы',
            'ko': '성공적으로 로그아웃되었습니다',
            'fr': 'Déconnexion réussie'
        },
        'profile_updated': {
            'zh': '资料已更新',
            'ja': 'プロフィールが更新されました',
            'en': 'Profile has been updated',
            'ru': 'Профиль обновлен',
            'ko': '프로필이 업데이트되었습니다',
            'fr': 'Le profil a été mis à jour'
        },
        'please_login': {
            'zh': '请先登录',
            'ja': '先にログインしてください',
            'en': 'Please log in first',
            'ru': 'Пожалуйста, сначала войдите в систему',
            'ko': '먼저 로그인해 주세요',
            'fr': 'Veuillez d\'abord vous connecter'
        },
        'upload_success': {
            'zh': '作品上传成功！',
            'ja': '作品のアップロードが成功しました！',
            'en': 'Work uploaded successfully!',
            'ru': 'Работа успешно загружена!',
            'ko': '작품이 성공적으로 업로드되었습니다!',
            'fr': 'Travail téléchargé avec succès!'
        },
        'comment_success': {
            'zh': '评论添加成功！',
            'ja': 'コメントが追加されました！',
            'en': 'Comment added successfully!',
            'ru': 'Комментарий успешно добавлен!',
            'ko': '댓글이 성공적으로 추가되었습니다!',
            'fr': 'Commentaire ajouté avec succès!'
        },
        'comment_notification': {
            'zh': '您收到了新的评论通知',
            'ja': '新しいコメント通知を受信しました',
            'en': 'You have received a new comment notification',
            'ru': 'Вы получили новое уведомление о комментарии',
            'ko': '새로운 댓글 알림을 받았습니다',
            'fr': 'Vous avez reçu une nouvelle notification de commentaire'
        },
        'no_permission_translate': {
            'zh': '您没有权限提交翻译',
            'ja': '翻訳を提出する権限がありません',
            'en': 'You do not have permission to submit translations',
            'ru': 'У вас нет разрешения на отправку переводов',
            'ko': '번역을 제출할 권한이 없습니다',
            'fr': 'Vous n\'avez pas la permission de soumettre des traductions'
        },
        'translate_success': {
            'zh': '翻译提交成功！',
            'ja': '翻訳が提出されました！',
            'en': 'Translation submitted successfully!',
            'ru': 'Перевод успешно отправлен!',
            'ko': '번역이 성공적으로 제출되었습니다!',
            'fr': 'Traduction soumise avec succès!'
        },
        'only_translator': {
            'zh': '只有翻译者可以翻译',
            'ja': '翻訳者のみが翻訳できます',
            'en': 'Only translators can translate',
            'ru': 'Только переводчики могут переводить',
            'ko': '번역가만 번역할 수 있습니다',
            'fr': 'Seuls les traducteurs peuvent traduire'
        },
        'wait_author_approval': {
            'zh': '请等待作者同意你的期待/要求',
            'en': 'Please wait for the author to approve your expectations/requirements',
            'ru': 'Пожалуйста, дождитесь одобрения ваших ожиданий/требований автором',
            'ko': '작가가 귀하의 기대/요구사항을 승인할 때까지 기다려 주세요',
            'ja': '作者の承認をお待ちください',
            'fr': 'Veuillez attendre que l\'auteur approuve vos attentes/exigences'
        },
        'contact_author_first': {
            'zh': '本作品要求翻译前请先私信作者，或获得作者信任。',
            'ja': 'この作品は翻訳前に作者にメッセージを送信するか、作者の信頼を得る必要があります。',
            'en': 'This work requires contacting the author before translation, or gaining the author\'s trust.',
            'ru': 'Эта работа требует связи с автором перед переводом или получения доверия автора.',
            'ko': '이 작품은 번역 전에 작가에게 연락하거나 작가의 신뢰를 얻어야 합니다.',
            'fr': 'Cette œuvre nécessite de contacter l\'auteur avant la traduction, ou d\'obtenir la confiance de l\'auteur.'
        },
        'work_already_translating': {
            'zh': '该作品正在翻译中，其他翻译者无法进行翻译。',
            'ja': 'この作品は翻訳中です。他の翻訳者は翻訳できません。',
            'en': 'This work is currently being translated. Other translators cannot translate it.',
            'ru': 'Эта работа в настоящее время переводится. Другие переводчики не могут её переводить.',
            'ko': '이 작품은 현재 번역 중입니다. 다른 번역가는 번역할 수 없습니다.',
            'fr': 'Cette œuvre est actuellement en cours de traduction. D\'autres traducteurs ne peuvent pas la traduire.'
        },
        'approved_translator': {
            'zh': '您已获得作者同意，可以开始翻译。',
            'ja': '作者の承認を得ました。翻訳を開始できます。',
            'en': 'You have been approved by the author and can start translating.',
            'ru': 'Вы получили одобрение автора и можете начать перевод.',
            'ko': '작가의 승인을 받았습니다. 번역을 시작할 수 있습니다.',
            'fr': 'Vous avez été approuvé par l\'auteur et pouvez commencer à traduire.'
        },
        'need_translator_qualification': {
            'zh': '只有通过翻译者资格的用户才能翻译',
            'ja': '翻訳者資格を取得したユーザーのみが翻訳できます',
            'en': 'Only users with translator qualification can translate',
            'ru': 'Только пользователи с квалификацией переводчика могут переводить',
            'ko': '번역가 자격을 갖춘 사용자만 번역할 수 있습니다',
            'fr': 'Seuls les utilisateurs ayant une qualification de traducteur peuvent traduire'
        },
        'no_permission_request': {
            'zh': '您没有权限处理此请求',
            'ja': 'このリクエストを処理する権限がありません',
            'en': 'You do not have permission to process this request',
            'ru': 'У вас нет разрешения на обработку этого запроса',
            'ko': '이 요청을 처리할 권한이 없습니다',
            'fr': 'Vous n\'avez pas la permission de traiter cette demande'
        },
        'request_processed': {
            'zh': '此请求已被处理',
            'ja': 'このリクエストは既に処理されています',
            'en': 'This request has already been processed',
            'ru': 'Этот запрос уже обработан',
            'ko': '이 요청은 이미 처리되었습니다',
            'fr': 'Cette demande a déjà été traitée'
        },
        'request_approved': {
            'zh': '翻译请求已同意',
            'ja': '翻訳リクエストが承認されました',
            'en': 'Translation request approved',
            'ru': 'Запрос на перевод одобрен',
            'ko': '번역 요청이 승인되었습니다',
            'fr': 'Demande de traduction approuvée'
        },
        'correction_success': {
            'zh': '校正提交成功！',
            'ja': '校正が提出されました！',
            'en': 'Correction submitted successfully!',
            'ru': 'Исправление успешно отправлено!',
            'ko': '교정이 성공적으로 제출되었습니다!',
            'fr': 'Correction soumise avec succès!'
        },
        'correction_submitted_to_creator': {
            'zh': '校正提交通知',
            'ja': '校正提出通知',
            'en': 'Correction Submission Notification',
            'ru': 'Уведомление об отправке исправления',
            'ko': '교정 제출 알림',
            'fr': 'Notification de soumission de correction'
        },
        'correction_submitted_to_translator': {
            'zh': '校正提交通知',
            'ja': '校正提出通知',
            'en': 'Correction Submission Notification',
            'ru': 'Уведомление об отправке исправления',
            'ko': '교정 제출 알림',
            'fr': 'Notification de soumission de correction'
        },
        'correction_deleted': {
            'zh': '校正已删除',
            'ja': '校正が削除されました',
            'en': 'Correction deleted',
            'ru': 'Исправление удалено',
            'ko': '교정이 삭제되었습니다',
            'fr': 'Correction supprimée'
        },
        'no_permission_correct': {
            'zh': '您没有权限进行校正',
            'ja': '校正する権限がありません',
            'en': 'You do not have permission to make corrections',
            'ru': 'У вас нет разрешения на внесение исправлений',
            'ko': '교정할 권한이 없습니다',
            'fr': 'Vous n\'avez pas la permission de faire des corrections'
        },
        'only_reviewer': {
            'zh': '只有校正者可以进行校正',
            'ja': '校正者のみが校正できます',
            'en': 'Only reviewers can make corrections',
            'ru': 'Только рецензенты могут вносить исправления',
            'ko': '검토자만 교정할 수 있습니다',
            'fr': 'Seuls les correcteurs peuvent faire des corrections'
        },
        'request_rejected': {
            'zh': '翻译请求已拒绝',
            'ja': '翻訳リクエストが拒否されました',
            'en': 'Translation request rejected',
            'ru': 'Запрос на перевод отклонен',
            'ko': '번역 요청이 거부되었습니다',
            'fr': 'Demande de traduction rejetée'
        },
        'password_changed': {
            'zh': '密码修改成功',
            'ja': 'パスワードが正常に変更されました',
            'en': 'Password changed successfully',
            'ru': 'Пароль успешно изменен',
            'ko': '비밀번호가 성공적으로 변경되었습니다',
            'fr': 'Mot de passe modifié avec succès'
        },
        'current_password_incorrect': {
            'zh': '当前密码不正确',
            'ja': '現在のパスワードが正しくありません',
            'en': 'Current password is incorrect',
            'ru': 'Текущий пароль неверен',
            'ko': '현재 비밀번호가 올바르지 않습니다',
            'fr': 'Le mot de passe actuel est incorrect'
        },
        'password_too_short': {
            'zh': '新密码长度至少为8位',
            'ja': '新しいパスワードは8文字以上である必要があります',
            'en': 'New password must be at least 8 characters long',
            'ru': 'Новый пароль должен содержать не менее 8 символов',
            'ko': '새 비밀번호는 최소 8자 이상이어야 합니다',
            'fr': 'Le nouveau mot de passe doit contenir au moins 8 caractères'
        },
        'password_mismatch': {
            'zh': '新密码和确认密码不匹配',
            'ja': '新しいパスワードと確認パスワードが一致しません',
            'en': 'New password and confirmation password do not match',
            'ru': 'Новый пароль и подтверждение пароля не совпадают',
            'ko': '새 비밀번호와 확인 비밀번호가 일치하지 않습니다',
            'fr': 'Le nouveau mot de passe et la confirmation ne correspondent pas'
        },
        'no_admin_permission': {
            'zh': '您没有管理员权限',
            'ja': '管理者権限がありません',
            'en': 'You do not have administrator privileges',
            'ru': 'У вас нет прав администратора',
            'ko': '관리자 권한이 없습니다',
            'fr': 'Vous n\'avez pas de privilèges d\'administrateur'
        },
        'role_updated': {
            'zh': '用户 {} 的角色已更新',
            'ja': 'ユーザー {} の役割が更新されました',
            'en': 'User {} role has been updated',
            'ru': 'Роль пользователя {} обновлена',
            'ko': '사용자 {}의 역할이 업데이트되었습니다',
            'fr': 'Le rôle de l\'utilisateur {} a été mis à jour'
        },
        'message_sent': {
            'zh': '消息发送成功',
            'ja': 'メッセージが送信されました',
            'en': 'Message sent successfully',
            'ru': 'Сообщение успешно отправлено',
            'ko': '메시지가 성공적으로 전송되었습니다',
            'fr': 'Message envoyé avec succès'
        },
        'invalid_image_format': {
            'zh': '不支持的图片格式，请使用 PNG、JPG、JPEG、GIF 或 WEBP 格式',
            'ja': 'サポートされていない画像形式です。PNG、JPG、JPEG、GIF、またはWEBP形式を使用してください',
            'en': 'Unsupported image format. Please use PNG, JPG, JPEG, GIF, or WEBP format',
            'ru': 'Неподдерживаемый формат изображения. Используйте формат PNG, JPG, JPEG, GIF или WEBP',
            'ko': '지원되지 않는 이미지 형식입니다. PNG, JPG, JPEG, GIF 또는 WEBP 형식을 사용하세요',
            'fr': 'Format d\'image non pris en charge. Veuillez utiliser le format PNG, JPG, JPEG, GIF ou WEBP'
        },
        'message_content_required': {
            'zh': '请输入消息内容或上传图片',
            'ja': 'メッセージ内容を入力するか、画像をアップロードしてください',
            'en': 'Please enter message content or upload an image',
            'ru': 'Пожалуйста, введите содержимое сообщения или загрузите изображение',
            'ko': '메시지 내용을 입력하거나 이미지를 업로드하세요',
            'fr': 'Veuillez saisir le contenu du message ou télécharger une image'
        },
        'image_upload_hint': {
            'zh': '支持 PNG、JPG、JPEG、GIF、WEBP 格式，最大5MB',
            'ja': 'PNG、JPG、JPEG、GIF、WEBP形式をサポート、最大5MB',
            'en': 'Supports PNG, JPG, JPEG, GIF, WEBP format, max 5MB',
            'ru': 'Поддерживает форматы PNG, JPG, JPEG, GIF, WEBP, макс. 5MB',
            'ko': 'PNG, JPG, JPEG, GIF, WEBP 형식 지원, 최대 5MB',
            'fr': 'Prend en charge les formats PNG, JPG, JPEG, GIF, WEBP, max 5MB'
        },
        'view_image': {
            'zh': '查看图片',
            'ja': '画像を表示',
            'en': 'View Image',
            'ru': 'Просмотр изображения',
            'ko': '이미지 보기',
            'fr': 'Voir l\'image'
        },
        'file_too_large': {
            'zh': '文件大小不能超过5MB',
            'ja': 'ファイルサイズは5MB以下にしてください',
            'en': 'File size cannot exceed 5MB',
            'ru': 'Размер файла не может превышать 5MB',
            'ko': '파일 크기는 5MB를 초과할 수 없습니다',
            'fr': 'La taille du fichier ne peut pas dépasser 5MB'
        },
        'message_read': {
            'zh': '消息已标记为已读',
            'ja': 'メッセージが既読としてマークされました',
            'en': 'Message marked as read',
            'ru': 'Сообщение отмечено как прочитанное',
            'ko': '메시지가 읽음으로 표시되었습니다',
            'fr': 'Message marqué comme lu'
        },
        'admin_work_deleted': {
            'zh': '管理员删除了您的作品',
            'ja': '管理者があなたの作品を削除しました',
            'en': 'Administrator deleted your work',
            'ru': 'Администратор удалил вашу работу',
            'ko': '관리자가 귀하의 작품을 삭제했습니다',
            'fr': 'L\'administrateur a supprimé votre œuvre'
        },
        'admin_work_edited': {
            'zh': '管理员编辑了您的作品',
            'ja': '管理者があなたの作品を編集しました',
            'en': 'Administrator edited your work',
            'ru': 'Администратор отредактировал вашу работу',
            'ko': '관리자가 귀하의 작품을 편집했습니다',
            'fr': 'L\'administrateur a modifié votre œuvre'
        },
        'already_translator': {
            'zh': '你已经是翻译者，无需重复申请。',
            'ja': '既に翻訳者です。重複申請は不要です。',
            'en': 'You are already a translator, no need to apply again.',
            'ru': 'Вы уже переводчик, нет необходимости подавать заявку снова.',
            'ko': '이미 번역가입니다. 다시 신청할 필요가 없습니다.',
            'fr': 'Vous êtes déjà traducteur, pas besoin de postuler à nouveau.'
        },
        'become_translator': {
            'zh': '恭喜你成为翻译者！',
            'ja': '翻訳者になりました！おめでとうございます！',
            'en': 'Congratulations on becoming a translator!',
            'ru': 'Поздравляем с тем, что стали переводчиком!',
            'ko': '번역가가 되신 것을 축하합니다!',
            'fr': 'Félicitations pour être devenu traducteur!'
        },
        'need_translator_first': {
            'zh': '请先成为翻译者后再申请校正者。',
            'ja': '先に翻訳者になってから校正者を申請してください。',
            'en': 'Please become a translator first before applying to be a reviewer.',
            'ru': 'Пожалуйста, сначала станьте переводчиком, прежде чем подавать заявку на рецензента.',
            'ko': '검토자 신청 전에 먼저 번역가가 되어 주세요.',
            'fr': 'Veuillez d\'abord devenir traducteur avant de postuler pour être correcteur.'
        },
        'already_reviewer': {
            'zh': '你已经是校正者，无需重复申请。',
            'ja': '既に校正者です。重複申請は不要です。',
            'en': 'You are already a reviewer, no need to apply again.',
            'ru': 'Вы уже рецензент, нет необходимости подавать заявку снова.',
            'ko': '이미 검토자입니다. 다시 신청할 필요가 없습니다.',
            'fr': 'Vous êtes déjà correcteur, pas besoin de postuler à nouveau.'
        },
        'become_reviewer': {
            'zh': '恭喜你成为校正者！',
            'ja': '校正者になりました！おめでとうございます！',
            'en': 'Congratulations on becoming a reviewer!',
            'ru': 'Поздравляем с тем, что стали рецензентом!',
            'ko': '검토자가 되신 것을 축하합니다!',
            'fr': 'Félicitations pour être devenu correcteur!'
        },
        'no_edit_permission': {
            'zh': '您没有权限编辑该作品',
            'ja': 'この作品を編集する権限がありません',
            'en': 'You do not have permission to edit this work',
            'ru': 'У вас нет разрешения на редактирование этой работы',
            'ko': '이 작품을 편집할 권한이 없습니다',
            'fr': 'Vous n\'avez pas la permission de modifier cette œuvre'
        },
        'edit_success': {
            'zh': '作品编辑成功！',
            'ja': '作品の編集が成功しました！',
            'en': 'Work edited successfully!',
            'ru': 'Работа успешно отредактирована!',
            'ko': '작품이 성공적으로 편집되었습니다!',
            'fr': 'Œuvre modifiée avec succès!'
        },
        'no_delete_permission': {
            'zh': '您没有权限删除该作品',
            'ja': 'この作品を削除する権限がありません',
            'en': 'You do not have permission to delete this work',
            'ru': 'У вас нет разрешения на удаление этой работы',
            'ko': '이 작품을 삭제할 권한이 없습니다',
            'fr': 'Vous n\'avez pas la permission de supprimer cette œuvre'
        },
        'delete_success': {
            'zh': '作品已删除',
            'ja': '作品が削除されました',
            'en': 'Work deleted',
            'ru': 'Работа удалена',
            'ko': '작품이 삭제되었습니다',
            'fr': 'Œuvre supprimée'
        },
        'cannot_trust_self': {
            'zh': '不能信赖自己',
            'ja': '自分を信頼することはできません',
            'en': 'Cannot trust yourself',
            'ru': 'Нельзя доверять самому себе',
            'ko': '자신을 신뢰할 수 없습니다',
            'fr': 'Ne peut pas se faire confiance'
        },
        'message_center': {
            'zh': '消息中心',
            'ja': 'メッセージセンター',
            'en': 'Message Center',
            'ru': 'Центр сообщений',
            'ko': '메시지 센터',
            'fr': 'Centre de messages'
        },
        'system_notifications': {
            'zh': '系统通知',
            'ja': 'システム通知',
            'en': 'System Notifications',
            'ru': 'Системные уведомления',
            'ko': '시스템 알림',
            'fr': 'Notifications système'
        },
        'mark_as_read': {
            'zh': '标记已读',
            'ja': '既読にする',
            'en': 'Mark as Read',
            'ru': 'Отметить как прочитанное',
            'ko': '읽음으로 표시',
            'fr': 'Marquer comme lu'
        },
        'friend_requests': {
            'zh': '好友请求',
            'ja': '友達リクエスト',
            'en': 'Friend Requests',
            'ru': 'Запросы в друзья',
            'ko': '친구 요청',
            'fr': 'Demandes d\'ami'
        },
        'requests_to_add_friend': {
            'zh': '请求添加您为好友',
            'ja': 'があなたを友達に追加することをリクエストしました',
            'en': 'requests to add you as a friend',
            'ru': 'запрашивает добавить вас в друзья',
            'ko': '가 당신을 친구로 추가하려고 요청했습니다',
            'fr': 'demande à vous ajouter comme ami'
        },
        'agree': {
            'zh': '同意',
            'ja': '同意',
            'en': 'Agree',
            'ru': 'Согласиться',
            'ko': '동의',
            'fr': 'Accepter'
        },
        'reject': {
            'zh': '拒绝',
            'ja': '拒否',
            'en': 'Reject',
            'ru': 'Отклонить',
            'ko': '거부',
            'fr': 'Rejeter'
        },
        'site_name': {
            'zh': '翻译平台', 'ja': '興味に基づいた翻訳プラットフォーム', 'en': 'Interest-driven Translation Platform', 'ru': 'Платформа перевода по интересам', 'ko': '관심 기반 번역 플랫폼', 'fr': 'Plateforme de traduction basée sur les intérêts'
        },
        'send_private_message': {
            'zh': '发送私信', 'ja': 'メッセージを送信', 'en': 'Send Message', 'ru': 'Отправить сообщение', 'ko': '쪽지 보내기', 'fr': 'Envoyer un message'
        },
        'notice': {
            'zh': '提示', 'ja': 'お知らせ', 'en': 'Notice', 'ru': 'Уведомление', 'ko': '알림', 'fr': 'Avis'
        },
        'confirm': {
            'zh': '确定', 'ja': '確定', 'en': 'Confirm', 'ru': 'Подтвердить', 'ko': '확인', 'fr': 'Confirmer'
        },
        'sending': {
            'zh': '发送中...', 'ja': '送信中...', 'en': 'Sending...', 'ru': 'Отправка...', 'ko': '전송 중...', 'fr': 'Envoi...'
        },
        'request_sent': {
            'zh': '已发送请求', 'ja': 'リクエストを送信済み', 'en': 'Request Sent', 'ru': 'Запрос отправлен', 'ko': '요청 전송됨', 'fr': 'Demande envoyée'
        },
        'add_friend': {
            'zh': '添加好友', 'ja': '友達を追加', 'en': 'Add Friend', 'ru': 'Добавить в друзья', 'ko': '친구 추가', 'fr': 'Ajouter un ami'
        },
        'send_success': {
            'zh': '发送成功', 'ja': '送信成功', 'en': 'Sent successfully', 'ru': 'Отправлено успешно', 'ko': '전송 성공', 'fr': 'Envoyé avec succès'
        },
        'send_failed': {
            'zh': '发送失败', 'ja': '送信失敗', 'en': 'Send failed', 'ru': 'Не удалось отправить', 'ko': '전송 실패', 'fr': 'Échec de l\'envoi'
        },
        'network_error': {
            'zh': '网络错误，请检查网络连接后重试', 'ja': 'ネットワークエラー、接続を確認して再試行してください', 'en': 'Network error, please check your connection and try again', 'ru': 'Ошибка сети, проверьте подключение и попробуйте снова', 'ko': '네트워크 오류, 연결을 확인하고 다시 시도하세요', 'fr': 'Erreur réseau, veuillez vérifier votre connexion et réessayer'
        },
        'friend_request_sent_toast': {
            'zh': '好友请求已发送！等待对方同意。', 'ja': '友達リクエストが送信されました！相手の同意をお待ちください。', 'en': 'Friend request sent! Please wait for approval.', 'ru': 'Заявка в друзья отправлена! Ожидайте подтверждения.', 'ko': '친구 요청이 전송되었습니다! 승인을 기다려주세요.', 'fr': 'Demande d\'ami envoyée ! Veuillez attendre l\'approbation.'
        },
        'send_request_failed': {
            'zh': '发送好友请求失败，请稍后重试。', 'ja': '友達リクエストの送信に失敗しました。後でもう一度お試しください。', 'en': 'Failed to send friend request. Please try again later.', 'ru': 'Не удалось отправить запрос в друзья. Попробуйте позже.', 'ko': '친구 요청 전송에 실패했습니다. 나중에 다시 시도하세요.', 'fr': 'Échec de l\'envoi de la demande d\'ami. Veuillez réessayer plus tard.'
        },
        'no_matching_users': {
            'zh': '未找到匹配的用户', 'ja': 'ユーザーが見つかりません', 'en': 'No matching users found', 'ru': 'Подходящие пользователи не найдены', 'ko': '일치하는 사용자를 찾을 수 없습니다', 'fr': 'Aucun utilisateur correspondant trouvé'
        },
        'user': {
            'zh': '用户', 'ja': 'ユーザー', 'en': 'User', 'ru': 'Пользователь', 'ko': '사용자', 'fr': 'Utilisateur'
        },
        'label_work_likes': {
            'zh': '作品点赞', 'ja': '作品いいね', 'en': 'Work Likes', 'ru': 'Лайки работ', 'ko': '작품 좋아요', 'fr': 'J\'aime de l\'œuvre'
        },
        'label_translation_likes': {
            'zh': '翻译点赞', 'ja': '翻訳いいね', 'en': 'Translation Likes', 'ru': 'Лайки переводов', 'ko': '번역 좋아요', 'fr': 'J\'aime des traductions'
        },
        'label_comment_likes': {
            'zh': '评论点赞', 'ja': 'コメントいいね', 'en': 'Comment Likes', 'ru': 'Лайки комментариев', 'ko': '댓글 좋아요', 'fr': 'J\'aime des commentaires'
        },
        'label_author_likes': {
            'zh': '作者点赞', 'ja': '作者いいね', 'en': 'Author Likes', 'ru': 'Лайки автора', 'ko': '작가 좋아요', 'fr': 'J\'aime de l\'auteur'
        },
        'label_correction_likes': {
            'zh': '校正点赞', 'ja': '校正いいね', 'en': 'Correction Likes', 'ru': 'Лайки исправлений', 'ko': '교정 좋아요', 'fr': 'J\'aime des corrections'
        },
        'label_translator_likes': {
            'zh': '翻译者点赞', 'ja': '翻訳者いいね', 'en': 'Translator Likes', 'ru': 'Лайки переводчика', 'ko': '번역가 좋아요', 'fr': 'J\'aime du traducteur'
        },
        'label_reviewer_likes': {
            'zh': '校正者点赞', 'ja': '校正者いいね', 'en': 'Reviewer Likes', 'ru': 'Лайки рецензента', 'ko': '검토자 좋아요', 'fr': 'J\'aime du correcteur'
        },
        'like_translator': {
            'zh': '为翻译者点赞', 'ja': '翻訳者にいいね', 'en': 'Like Translator', 'ru': 'Лайк переводчику', 'ko': '번역가 좋아요', 'fr': 'Aimer le traducteur'
        },
        'like_reviewer': {
            'zh': '为校正者点赞', 'ja': '校正者にいいね', 'en': 'Like Reviewer', 'ru': 'Лайк рецензенту', 'ko': '검토자 좋아요', 'fr': 'Aimer le correcteur'
        },
        'cannot_like_self': {
            'zh': '不能给自己点赞', 'ja': '自分にいいねはできません', 'en': 'Cannot like yourself', 'ru': 'Нельзя лайкать себя', 'ko': '자신에게 좋아요를 할 수 없습니다', 'fr': 'Ne peut pas s\'aimer soi-même'
        },
        'user_not_translated': {
            'zh': '该用户没有翻译这个作品', 'ja': 'このユーザーはこの作品を翻訳していません', 'en': 'This user has not translated this work', 'ru': 'Этот пользователь не переводил эту работу', 'ko': '이 사용자는 이 작품을 번역하지 않았습니다', 'fr': 'Cet utilisateur n\'a pas traduit cette œuvre'
        },
        'user_not_reviewed': {
            'zh': '该用户没有校正这个作品', 'ja': 'このユーザーはこの作品を校正していません', 'en': 'This user has not reviewed this work', 'ru': 'Этот пользователь не рецензировал эту работу', 'ko': '이 사용자는 이 작품을 검토하지 않았습니다', 'fr': 'Cet utilisateur n\'a pas révisé cette œuvre'
        },
        'section_recent_works': {
            'zh': '最近上传的作品', 'ja': '最近アップロードした作品', 'en': 'Recently Uploaded Works', 'ru': 'Недавно загруженные работы', 'ko': '최근 업로드한 작품', 'fr': 'Œuvres récemment téléchargées'
        },
        'section_works': {
            'zh': '作品', 'ja': '作品', 'en': 'Works', 'ru': 'Работы', 'ko': '작품', 'fr': 'Œuvres'
        },
        'btn_upload_work': {
            'zh': '上传作品', 'ja': '作品をアップロード', 'en': 'Upload Work', 'ru': 'Загрузить работу', 'ko': '작품 업로드', 'fr': 'Téléverser une œuvre'
        },
        'btn_view_all_works': {
            'zh': '查看所有作品', 'ja': 'すべての作品を見る', 'en': 'View All Works', 'ru': 'Посмотреть все работы', 'ko': '모든 작품 보기', 'fr': 'Voir toutes les œuvres'
        },
        'view_works': {
            'zh': '查看作品', 'ja': '作品を見る', 'en': 'View Works', 'ru': 'Посмотреть работы', 'ko': '작품 보기', 'fr': 'Voir les œuvres'
        },
        'filtered': {
            'zh': '已筛选', 'ja': '絞り込み済み', 'en': 'Filtered', 'ru': 'Отфильтровано', 'ko': '필터 적용됨', 'fr': 'Filtré'
        },
        'no_works': {
            'zh': '暂无作品', 'ja': '作品なし', 'en': 'No works yet', 'ru': 'Пока нет работ', 'ko': '작품이 없습니다', 'fr': 'Pas encore d\'œuvres'
        },
        'btn_upload_first_work': {
            'zh': '上传第一个作品', 'ja': '最初の作品をアップロード', 'en': 'Upload First Work', 'ru': 'Загрузить первую работу', 'ko': '첫 작품 업로드', 'fr': 'Téléverser la première œuvre'
        },
        'section_translations': {
            'zh': '翻译作品', 'ja': '翻訳作品', 'en': 'Translations', 'ru': 'Переводы', 'ko': '번역 작품', 'fr': 'Traductions'
        },
        'section_recent_translations': {
            'zh': '最近的翻译', 'ja': '最近の翻訳', 'en': 'Recent Translations', 'ru': 'Недавние переводы', 'ko': '최근 번역', 'fr': 'Traductions récentes'
        },
        'btn_view_all_translations': {
            'zh': '查看所有翻译', 'ja': 'すべての翻訳を見る', 'en': 'View All Translations', 'ru': 'Посмотреть все переводы', 'ko': '모든 번역 보기', 'fr': 'Voir toutes les traductions'
        },
        'no_translations': {
            'zh': '暂无翻译', 'ja': '翻訳なし', 'en': 'No translations yet', 'ru': 'Пока нет переводов', 'ko': '번역이 없습니다', 'fr': 'Pas encore de traductions'
        },
        'find_translations': {
            'zh': '寻找翻译作品', 'ja': '翻訳する作品を探す', 'en': 'Find Works to Translate', 'ru': 'Найти работы для перевода', 'ko': '번역할 작품 찾기', 'fr': 'Trouver des œuvres à traduire'
        },
        'author_evaluation': {
            'zh': '作者评价', 'ja': '作者評価', 'en': "Author's Evaluation", 'ru': 'Оценка автора', 'ko': '작가 평가', 'fr': "Évaluation de l'auteur"
        },
        'translation': {
            'zh': '翻译', 'ja': '翻訳', 'en': 'Translation', 'ru': 'Перевод', 'ko': '번역', 'fr': 'Traduction'
        },
        'correction': {
            'zh': '校正', 'ja': '校正', 'en': 'Correction', 'ru': 'Исправление', 'ko': '교정', 'fr': 'Correction'
        },
        'already_friends': {
            'zh': '已是好友', 'ja': '既に友達', 'en': 'Already friends', 'ru': 'Уже друзья', 'ko': '이미 친구', 'fr': 'Déjà amis'
        },
        'waiting_for_approval': {
            'zh': '等待对方同意', 'ja': '相手の承認待ち', 'en': 'Waiting for approval', 'ru': 'Ожидание подтверждения', 'ko': '승인 대기 중', 'fr': "En attente d\'approbation"
        },
        'approve_friend_request': {
            'zh': '同意好友请求', 'ja': '友達リクエスト承認', 'en': 'Approve friend request', 'ru': 'Одобрить заявку в друзья', 'ko': '친구 요청 승인', 'fr': 'Approuver la demande d\'ami'
        },
        'add_as_friend': {
            'zh': '加为好友', 'ja': '友達追加', 'en': 'Add as friend', 'ru': 'Добавить в друзья', 'ko': '친구로 추가', 'fr': 'Ajouter comme ami'
        },
        'apply_admin': {
            'zh': '申请管理员', 'ja': '管理者申請', 'en': 'Apply for Admin', 'ru': 'Подать заявку на администратора', 'ko': '관리자 신청', 'fr': 'Postuler en tant qu\'administrateur'
        },
        'language_zh': {
            'zh': '中文', 'ja': '中国語', 'en': 'Chinese', 'ru': 'Китайский', 'ko': '중국어', 'fr': 'Chinois'
        },
        'language_ja': {
            'zh': '日文', 'ja': '日本語', 'en': 'Japanese', 'ru': 'Японский', 'ko': '일본어', 'fr': 'Japonais'
        },
        'language_en': {
            'zh': '英文', 'ja': '英語', 'en': 'English', 'ru': 'Английский', 'ko': '영어', 'fr': 'Anglais'
        },
        'language_ru': {
            'zh': '俄文', 'ja': 'ロシア語', 'en': 'Russian', 'ru': 'Русский', 'ko': '러시아어', 'fr': 'Russe'
        },
        'language_ko': {
            'zh': '韩文', 'ja': '韓国語', 'en': 'Korean', 'ru': 'Корейский', 'ko': '한국어', 'fr': 'Coréen'
        },
        'language_fr': {
            'zh': '法文', 'ja': 'フランス語', 'en': 'French', 'ru': 'Французский', 'ko': '프랑스어', 'fr': 'Français'
        },
        'translation_requests': {
            'zh': '翻译请求',
            'ja': '翻訳リクエスト',
            'en': 'Translation Requests',
            'ru': 'Запросы на перевод',
            'ko': '번역 요청',
            'fr': 'Demandes de traduction'
        },
        'new_translation_request': {
            'zh': '新的翻译请求',
            'ja': '新しい翻訳リクエスト',
            'en': 'New Translation Request',
            'ru': 'Новый запрос на перевод',
            'ko': '새로운 번역 요청',
            'fr': 'Nouvelle demande de traduction'
        },
        'new_translator_request': {
            'zh': '新的翻译者请求',
            'ja': '新しい翻訳者リクエスト',
            'en': 'New Translator Request',
            'ru': 'Новый запрос переводчика',
            'ko': '새로운 번역가 요청',
            'fr': 'Nouvelle demande de traducteur'
        },
        'new_translation_submitted': {
            'zh': '新的翻译提交',
            'ja': '新しい翻訳提出',
            'en': 'New Translation Submitted',
            'ru': 'Новый перевод отправлен',
            'ko': '새로운 번역 제출',
            'fr': 'Nouvelle traduction soumise'
        },
        'translation_accepted_notification': {
            'zh': '翻译已被接受',
            'ja': '翻訳が承認されました',
            'en': 'Translation Accepted',
            'ru': 'Перевод принят',
            'ko': '번역 승인됨',
            'fr': 'Traduction acceptée'
        },
        'translation_rejected_notification': {
            'zh': '翻译已被拒绝',
            'ja': '翻訳が拒否されました',
            'en': 'Translation Rejected',
            'ru': 'Перевод отклонен',
            'ko': '번역 거부됨',
            'fr': 'Traduction rejetée'
        },
        'requests_to_translate_work': {
            'zh': '请求翻译您的作品',
            'ja': 'があなたの作品の翻訳をリクエストしました',
            'en': 'requests to translate your work',
            'ru': 'запрашивает перевести вашу работу',
            'ko': '가 당신의 작품을 번역하려고 요청했습니다',
            'fr': 'demande à traduire votre travail'
        },
        'expectation_requirement': {
            'zh': '期待/要求：',
            'ja': '期待/要求：',
            'en': 'Expectation/Requirement: ',
            'ru': 'Ожидание/Требование: ',
            'ko': '기대/요구사항: ',
            'fr': 'Attente/Exigence: '
        },
        'private_messages': {
            'zh': '私信列表',
            'ja': 'プライベートメッセージ',
            'en': 'Private Messages',
            'ru': 'Личные сообщения',
            'ko': '개인 메시지',
            'fr': 'Messages privés'
        },
        'enter_conversation': {
            'zh': '进入对话',
            'ja': '会話に入る',
            'en': 'Enter Conversation',
            'ru': 'Войти в разговор',
            'ko': '대화 참여',
            'fr': 'Entrer dans la conversation'
        },
        'no_private_messages': {
            'zh': '暂无私信',
            'ja': 'プライベートメッセージはありません',
            'en': 'No private messages',
            'ru': 'Нет личных сообщений',
            'ko': '개인 메시지 없음',
            'fr': 'Aucun message privé'
        },
        'no_private_messages_desc': {
            'zh': '您还没有与任何用户进行私信交流',
            'ja': 'まだどのユーザーともプライベートメッセージのやり取りをしていません',
            'en': 'You have not had private message exchanges with any users yet',
            'ru': 'У вас пока нет обмена личными сообщениями с пользователями',
            'ko': '아직 어떤 사용자와도 개인 메시지를 주고받지 않았습니다',
            'fr': 'Vous n\'avez pas encore échangé de messages privés avec des utilisateurs'
        },
        'unread_messages': {
            'zh': '未读消息',
            'ja': '未読メッセージ',
            'en': 'Unread Messages',
            'ru': 'Непрочитанные сообщения',
            'ko': '읽지 않은 메시지',
            'fr': 'Messages non lus'
        },
        'conversation_with': {
            'zh': '与 {} 的私信',
            'ja': '{}とのメッセージ',
            'en': 'Private messages with {}',
            'ru': 'Личные сообщения с {}',
            'ko': '{}와의 개인 메시지',
            'fr': 'Messages privés avec {}'
        },
        'avatar': {
            'zh': '头像',
            'ja': 'アバター',
            'en': 'Avatar',
            'ru': 'Аватар',
            'ko': '아바타',
            'fr': 'Avatar'
        },
        'input_message': {
            'zh': '输入消息...',
            'ja': 'メッセージを入力...',
            'en': 'Enter message...',
            'ru': 'Введите сообщение...',
            'ko': '메시지 입력...',
            'fr': 'Entrez le message...'
        },
        'send': {
            'zh': '发送',
            'ja': '送信',
            'en': 'Send',
            'ru': 'Отправить',
            'ko': '보내기',
            'fr': 'Envoyer'
        },
        'back_to_message_list': {
            'zh': '返回私信列表',
            'ja': 'メッセージリストに戻る',
            'en': 'Back to Message List',
            'ru': 'Вернуться к списку сообщений',
            'ko': '메시지 목록으로 돌아가기',
            'fr': 'Retour à la liste des messages'
        },
        'trusted_translator': {
            'zh': '已信任该翻译者',
            'ja': 'この翻訳者を信頼しました',
            'en': 'Translator trusted',
            'ru': 'Переводчик проверен',
            'ko': '번역가를 신뢰함',
            'fr': 'Traducteur approuvé'
        },
        'already_trusted': {
            'zh': '已信任该翻译者',
            'ja': '既にこの翻訳者を信頼しています',
            'en': 'Translator trusted',
            'ru': 'Переводчик проверен',
            'ko': '번역가를 신뢰함',
            'fr': 'Traducteur approuvé'
        },
        'untrusted': {
            'zh': '已取消信任',
            'ja': '信頼を解除しました',
            'en': 'Trust removed',
            'ru': 'Доверие снято',
            'ko': '신뢰를 해제했습니다',
            'fr': 'Confiance retirée'
        },
        'not_trusted': {
            'zh': '未信任该翻译者',
            'ja': 'この翻訳者を信頼していません',
            'en': 'Not trusting this translator',
            'ru': 'Не доверяем этому переводчику',
            'ko': '이 번역가를 신뢰하지 않습니다',
            'fr': 'Ne fait pas confiance à ce traducteur'
        },
        'trust_this_translator': {
            'zh': '信任该翻译者',
            'ja': 'この翻訳者を信頼',
            'en': 'Trust this translator',
            'ru': 'Доверять этому переводчику',
            'ko': '이 번역가 신뢰하기',
            'fr': 'Faire confiance à ce traducteur'
        },
        'untrust_this_translator': {
            'zh': '取消信任',
            'ja': '信頼解除',
            'en': 'Remove trust',
            'ru': 'Снять доверие',
            'ko': '신뢰 해제',
            'fr': 'Retirer la confiance'
        },
        'invalid_operation': {
            'zh': '操作无效',
            'ja': '操作が無効です',
            'en': 'Invalid operation',
            'ru': 'Недопустимая операция',
            'ko': '잘못된 작업입니다',
            'fr': 'Opération invalide'
        },
        'friend_request_sent': {
            'zh': '已发送好友请求，等待对方同意',
            'ja': '友達リクエストを送信しました。相手の承認をお待ちください',
            'en': 'Friend request sent, waiting for approval',
            'ru': 'Запрос в друзья отправлен, ожидание одобрения',
            'ko': '친구 요청을 보냈습니다. 승인을 기다리고 있습니다',
            'fr': 'Demande d\'ami envoyée, en attente d\'approbation'
        },
        'already_friends': {
            'zh': '你们已经是好友',
            'ja': '既に友達です',
            'en': 'You are already friends',
            'ru': 'Вы уже друзья',
            'ko': '이미 친구입니다',
            'fr': 'Vous êtes déjà amis'
        },
        'friend_request_rejected': {
            'zh': '好友请求已被拒绝',
            'ja': '友達リクエストが拒否されました',
            'en': 'Friend request rejected',
            'ru': 'Запрос в друзья отклонен',
            'ko': '친구 요청이 거부되었습니다',
            'fr': 'Demande d\'ami rejetée'
        },
        'friend_request_success': {
            'zh': '好友请求已发送',
            'ja': '友達リクエストが送信されました',
            'en': 'Friend request sent',
            'ru': 'Запрос в друзья отправлен',
            'ko': '친구 요청이 전송되었습니다',
            'fr': 'Demande d\'ami envoyée'
        },
        'invalid_friend_request': {
            'zh': '无效的好友请求',
            'ja': '無効な友達リクエストです',
            'en': 'Invalid friend request',
            'ru': 'Недействительный запрос в друзья',
            'ko': '잘못된 친구 요청입니다',
            'fr': 'Demande d\'ami invalide'
        },
        'friend_accepted': {
            'zh': '已同意好友请求',
            'ja': '友達リクエストを承認しました',
            'en': 'Friend request accepted',
            'ru': 'Запрос в друзья принят',
            'ko': '친구 요청을 승인했습니다',
            'fr': 'Demande d\'ami acceptée'
        },
        'friend_request_not_found': {
            'zh': '好友请求不存在或已被处理',
            'ja': '友達リクエストが存在しないか、既に処理されています',
            'en': 'Friend request not found or already processed',
            'ru': 'Запрос в друзья не найден или уже обработан',
            'ko': '친구 요청이 존재하지 않거나 이미 처리되었습니다',
            'fr': 'Demande d\'ami introuvable ou déjà traitée'
        },
        'friend_rejected': {
            'zh': '已拒绝好友请求',
            'ja': '友達リクエストを拒否しました',
            'en': 'Friend request rejected',
            'ru': 'Запрос в друзья отклонен',
            'ko': '친구 요청을 거부했습니다',
            'fr': 'Demande d\'ami rejetée'
        },
        'friend_deleted': {
            'zh': '好友已删除',
            'ja': '友達を削除しました',
            'en': 'Friend deleted',
            'ru': 'Друг удален',
            'ko': '친구가 삭제되었습니다',
            'fr': 'Ami supprimé'
        },
        'friend_not_found': {
            'zh': '好友关系不存在',
            'ja': '友達関係が存在しません',
            'en': 'Friend relationship not found',
            'ru': 'Дружеские отношения не найдены',
            'ko': '친구 관계가 존재하지 않습니다',
            'fr': 'Relation d\'ami introuvable'
        },
        'delete_friend': {
            'zh': '删除好友',
            'ja': '友達を削除',
            'en': 'Delete Friend',
            'ru': 'Удалить друга',
            'ko': '친구 삭제',
            'fr': 'Supprimer l\'ami'
        },
        'confirm_delete_friend': {
            'zh': '确认删除好友',
            'ja': '友達削除の確認',
            'en': 'Confirm Delete Friend',
            'ru': 'Подтвердить удаление друга',
            'ko': '친구 삭제 확인',
            'fr': 'Confirmer la suppression de l\'ami'
        },
        'confirm_delete_friend_generic': {
            'zh': '确定要删除好友吗？此操作不可撤销。',
            'ja': '友達を削除してもよろしいですか？この操作は取り消せません。',
            'en': 'Are you sure you want to delete friend? This action cannot be undone.',
            'ru': 'Вы уверены, что хотите удалить друга? Это действие нельзя отменить.',
            'ko': '친구를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.',
            'fr': 'Êtes-vous sûr de vouloir supprimer l\'ami? Cette action ne peut pas être annulée.'
        },
        'delete_friend_failed': {
            'zh': '删除好友失败',
            'ja': '友達削除に失敗しました',
            'en': 'Failed to delete friend',
            'ru': 'Не удалось удалить друга',
            'ko': '친구 삭제 실패',
            'fr': 'Échec de la suppression de l\'ami'
        },
        'confirm_delete_friend_message': {
            'zh': '确定要删除好友 "{friend_name}" 吗？此操作不可撤销。',
            'ja': '友達 "{friend_name}" を削除してもよろしいですか？この操作は取り消せません。',
            'en': 'Are you sure you want to delete friend "{friend_name}"? This action cannot be undone.',
            'ru': 'Вы уверены, что хотите удалить друга "{friend_name}"? Это действие нельзя отменить.',
            'ko': '친구 "{friend_name}"을(를) 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.',
            'fr': 'Êtes-vous sûr de vouloir supprimer l\'ami "{friend_name}" ? Cette action ne peut pas être annulée.'
        },
        'deleting_friend': {
            'zh': '删除中...',
            'ja': '削除中...',
            'en': 'Deleting...',
            'ru': 'Удаление...',
            'ko': '삭제 중...',
            'fr': 'Suppression...'
        },
        'friend_deleted_success': {
            'zh': '已成功删除好友 "{friend_name}"',
            'ja': '友達 "{friend_name}" を正常に削除しました',
            'en': 'Successfully deleted friend "{friend_name}"',
            'ru': 'Друг "{friend_name}" успешно удален',
            'ko': '친구 "{friend_name}"이(가) 성공적으로 삭제되었습니다',
            'fr': 'Ami "{friend_name}" supprimé avec succès'
        },
        'friend_deleted_generic': {
            'zh': '已成功删除好友',
            'ja': '友達を正常に削除しました',
            'en': 'Successfully deleted friend',
            'ru': 'Друг успешно удален',
            'ko': '친구가 성공적으로 삭제되었습니다',
            'fr': 'Ami supprimé avec succès'
        },
        'no_translation': {
            'zh': '您没有翻译过这个作品',
            'ja': 'この作品を翻訳していません',
            'en': 'You have not translated this work',
            'ru': 'Вы не переводили эту работу',
            'ko': '이 작품을 번역하지 않았습니다',
            'fr': 'Vous n\'avez pas traduit cette œuvre'
        },
        'translation_updated': {
            'zh': '翻译已更新',
            'ja': '翻訳が更新されました',
            'en': 'Translation updated',
            'ru': 'Перевод обновлен',
            'ko': '번역이 업데이트되었습니다',
            'fr': 'Traduction mise à jour'
        },
        'translation_deleted': {
            'zh': '翻译已删除',
            'ja': '翻訳が削除されました',
            'en': 'Translation deleted',
            'ru': 'Перевод удален',
            'ko': '번역이 삭제되었습니다',
            'fr': 'Traduction supprimée'
        },
        'only_author_accept': {
            'zh': '只有作品作者可以接受翻译',
            'ja': '作品の作者のみが翻訳を承認できます',
            'en': 'Only the work author can accept translation',
            'ru': 'Только автор работы может принять перевод',
            'ko': '작품 작가만 번역을 승인할 수 있습니다',
            'fr': 'Seul l\'auteur de l\'œuvre peut accepter la traduction'
        },
        'no_translation_for_work': {
            'zh': '该作品还没有翻译',
            'ja': 'この作品にはまだ翻訳がありません',
            'en': 'No translation for this work',
            'ru': 'Нет перевода для этой работы',
            'ko': '이 작품에 대한 번역이 없습니다',
            'fr': 'Aucune traduction pour ce travail'
        },
        'home': {
            'zh': '首页',
            'ja': 'ホーム',
            'en': 'Home',
            'ru': 'Главная',
            'ko': '홈',
            'fr': 'Accueil'
        },
        'me': {
            'zh': '我',
            'ja': '私',
            'en': 'Me',
            'ru': 'Я',
            'ko': '나',
            'fr': 'Moi'
        },
        'edit': {
            'zh': '编辑',
            'ja': '編集',
            'en': 'Edit',
            'ru': 'Редактировать',
            'ko': '편집',
            'fr': 'Modifier'
        },
        'delete': {
            'zh': '删除',
            'ja': '削除',
            'en': 'Delete',
            'ru': 'Удалить',
            'ko': '삭제',
            'fr': 'Supprimer'
        },
        'translate': {
            'zh': '翻译',
            'ja': '翻訳',
            'en': 'Translate',
            'ru': 'Перевести',
            'ko': '번역',
            'fr': 'Traduire'
        },
        'comment': {
            'zh': '评论',
            'ja': 'コメント',
            'en': 'Comment',
            'ru': 'Комментарий',
            'ko': '댓글',
            'fr': 'Commentaire'
        },
        'like': {
            'zh': '点赞',
            'ja': 'いいね',
            'en': 'Like',
            'ru': 'Нравится',
            'ko': '좋아요',
            'fr': 'J\'aime'
        },
        'unlike': {
            'zh': '取消点赞',
            'ja': 'いいねを取り消す',
            'en': 'Unlike',
            'ru': 'Не нравится',
            'ko': '좋아요 취소',
            'fr': 'Je n\'aime plus'
        },
        'submit': {
            'zh': '提交',
            'ja': '提出',
            'en': 'Submit',
            'ru': 'Отправить',
            'ko': '제출',
            'fr': 'Soumettre'
        },
        'cancel': {
            'zh': '取消',
            'ja': 'キャンセル',
            'en': 'Cancel',
            'ru': 'Отмена',
            'ko': '취소',
            'fr': 'Annuler'
        },
        'save': {
            'zh': '保存',
            'ja': '保存',
            'en': 'Save',
            'ru': 'Сохранить',
            'ko': '저장',
            'fr': 'Enregistrer'
        },
        'back': {
            'zh': '返回',
            'ja': '戻る',
            'en': 'Back',
            'ru': 'Назад',
            'ko': '뒤로',
            'fr': 'Retour'
        },
        'next': {
            'zh': '下一页',
            'ja': '次へ',
            'en': 'Next',
            'ru': 'Следующая',
            'ko': '다음',
            'fr': 'Suivant'
        },
        'previous': {
            'zh': '上一页',
            'ja': '前へ',
            'en': 'Previous',
            'ru': 'Предыдущая',
            'ko': '이전',
            'fr': 'Précédent'
        },
        'loading': {
            'zh': '加载中...',
            'ja': '読み込み中...',
            'en': 'Loading...',
            'ru': 'Загрузка...',
            'ko': '로딩 중...',
            'fr': 'Chargement...'
        },
        'no_data': {
            'zh': '暂无数据',
            'ja': 'データがありません',
            'en': 'No data',
            'ru': 'Нет данных',
            'ko': '데이터 없음',
            'fr': 'Aucune donnée'
        },
        'error': {
            'zh': '错误',
            'ja': 'エラー',
            'en': 'Error',
            'ru': 'Ошибка',
            'ko': '오류',
            'fr': 'Erreur'
        },
        'success': {
            'zh': '成功',
            'ja': '成功',
            'en': 'Success',
            'ru': 'Успех',
            'ko': '성공',
            'fr': 'Succès'
        },
        'warning': {
            'zh': '警告',
            'ja': '警告',
            'en': 'Warning',
            'ru': 'Предупреждение',
            'ko': '경고',
            'fr': 'Avertissement'
        },
        'info': {
            'zh': '信息',
            'ja': '情報',
            'en': 'Info',
            'ru': 'Информация',
            'ko': '정보',
            'fr': 'Info'
        },
        'status_pending': {
            'zh': '待翻译',
            'ja': '翻訳待ち',
            'en': 'Pending Translation',
            'ru': 'Ожидает перевода',
            'ko': '번역 대기',
            'fr': 'En attente de traduction'
        },
        'status_translating': {
            'zh': '翻译中',
            'ja': '翻訳中',
            'en': 'Translating',
            'ru': 'Переводится',
            'ko': '번역 중',
            'fr': 'En cours de traduction'
        },
        'status_completed': {
            'zh': '已完成',
            'ja': '完了',
            'en': 'Completed',
            'ru': 'Завершено',
            'ko': '완료',
            'fr': 'Terminé'
        },
        'status_draft': {
            'zh': '草稿', 'ja': '下書き', 'en': 'Draft', 'ru': 'Черновик', 'ko': '초안', 'fr': 'Brouillon'
        },
        'status_submitted': {
            'zh': '已提交', 'ja': '提出済み', 'en': 'Submitted', 'ru': 'Отправлено', 'ko': '제출됨', 'fr': 'Soumis'
        },
        'status_approved': {
            'zh': '已通过', 'ja': '承認済み', 'en': 'Approved', 'ru': 'Одобрено', 'ko': '승인됨', 'fr': 'Approuvé'
        },
        'status_rejected': {
            'zh': '已拒绝', 'ja': '却下', 'en': 'Rejected', 'ru': 'Отклонено', 'ko': '거부됨', 'fr': 'Rejeté'
        },
        'category_post_article': {
            'zh': '投稿・文章',
            'ja': '投稿・文章',
            'en': 'Post/Article',
            'ru': 'Пост/Статья',
            'ko': '게시물/기사',
            'fr': 'Publication/Article'
        },
        'category_novel': {
            'zh': '小说',
            'ja': '小説',
            'en': 'Novel',
            'ru': 'Роман',
            'ko': '소설',
            'fr': 'Roman'
        },
        'category_image': {
            'zh': '图片',
            'ja': '画像',
            'en': 'Image',
            'ru': 'Изображение',
            'ko': '이미지',
            'fr': 'Image'
        },
        'category_comic': {
            'zh': '漫画',
            'ja': '漫画',
            'en': 'Comic',
            'ru': 'Комикс',
            'ko': '만화',
            'fr': 'Bande dessinée'
        },
        'admin_edit': {
            'zh': '管理员编辑',
            'ja': '管理者編集',
            'en': 'Admin Edit',
            'ru': 'Редактировать (админ)',
            'ko': '관리자 편집',
            'fr': 'Modifier (admin)'
        },
        'admin_delete': {
            'zh': '管理员删除',
            'ja': '管理者削除',
            'en': 'Admin Delete',
            'ru': 'Удалить (админ)',
            'ko': '관리자 삭제',
            'fr': 'Supprimer (admin)'
        },
        'category_audio': {
            'zh': '音声', 'ja': '音声', 'en': 'Audio', 'ru': 'Аудио', 'ko': '오디오', 'fr': 'Audio'
        },
        'category_video_animation': {
            'zh': '视频・动画', 'ja': '動画・アニメ', 'en': 'Video/Animation', 'ru': 'Видео/Анимация', 'ko': '비디오/애니메이션', 'fr': 'Vidéo/Animation'
        },
        'category_chat': {
            'zh': '闲聊', 'ja': '雑談', 'en': 'Chat', 'ru': 'Чат', 'ko': '잡담', 'fr': 'Discussion'
        },
        'category_other': {
            'zh': '其他', 'ja': 'その他', 'en': 'Other', 'ru': 'Другое', 'ko': '기타', 'fr': 'Autre'
        },
        'all_languages': {
            'zh': '所有语言', 'ja': 'すべての言語', 'en': 'All Languages', 'ru': 'Все языки', 'ko': '모든 언어', 'fr': 'Toutes les langues'
        },
        'language_other': {
            'zh': '其他', 'ja': 'その他', 'en': 'Other', 'ru': 'Другое', 'ko': '기타', 'fr': 'Autre'
        },
        'creator': {
            'zh': '创作者', 'ja': 'クリエイター', 'en': 'Creator', 'ru': 'Создатель', 'ko': '창작자', 'fr': 'Créateur'
        },
        'edit_work': {
            'zh': '编辑作品', 'ja': '作品編集', 'en': 'Edit Work', 'ru': 'Редактировать работу', 'ko': '작품 편집', 'fr': "Modifier l'œuvre"
        },
        'admin_edit_reason': {
            'zh': '管理员编辑理由：', 'ja': '管理者編集理由：', 'en': 'Admin edit reason: ', 'ru': 'Причина правки администратором: ', 'ko': '관리자 편집 사유: ', 'fr': "Raison de modification par admin : "
        },
        'label_title': {
            'zh': '标题', 'ja': '作品タイトル', 'en': 'Title', 'ru': 'Заголовок', 'ko': '제목', 'fr': 'Titre'
        },
        'label_category': {
            'zh': '分类', 'ja': 'カテゴリー', 'en': 'Category', 'ru': 'Категория', 'ko': '카테고리', 'fr': 'Catégorie'
        },
        'choose_category': {
            'zh': '选择分类', 'ja': 'カテゴリーを選択', 'en': 'Choose category', 'ru': 'Выберите категорию', 'ko': '카테고리 선택', 'fr': 'Choisir une catégorie'
        },
        'original_language': {
            'zh': '原文语言', 'ja': '原文言語', 'en': 'Original Language', 'ru': 'Исходный язык', 'ko': '원본 언어', 'fr': 'Langue originale'
        },
        'target_language': {
            'zh': '目标语言', 'ja': '目標言語', 'en': 'Target Language', 'ru': 'Целевой язык', 'ko': '목표 언어', 'fr': 'Langue cible'
        },
        'body_content': {
            'zh': '正文内容', 'ja': '本文内容', 'en': 'Body Content', 'ru': 'Содержимое текста', 'ko': '본문 내용', 'fr': 'Contenu du texte'
        },
        'enter_work_content_placeholder': {
            'zh': '请输入作品内容...', 'ja': '作品の内容を入力してください...', 'en': 'Please enter the work content...', 'ru': 'Введите содержимое работы...', 'ko': '작품 내용을 입력하세요...', 'fr': "Veuillez saisir le contenu de l'œuvre..."
        },
        'content_hint': {
            'zh': '请提供清晰、结构化的内容，以便翻译者更好地理解', 'ja': '翻訳者が理解しやすいように、明確で構造化された内容を提供してください', 'en': 'Provide clear, structured content to help translators understand better', 'ru': 'Предоставьте четкое, структурированное содержимое, чтобы переводчикам было легче понять', 'ko': '번역가가 잘 이해할 수 있도록 명확하고 구조화된 내용을 제공하세요', 'fr': 'Fournissez un contenu clair et structuré pour faciliter la compréhension des traducteurs'
        },
        'upload_media': {
            'zh': '上传多媒体文件（图片、音频、视频，选填）', 'ja': 'マルチメディアファイルをアップロード（画像、音声、動画、オプション）', 'en': 'Upload media files (images, audio, video, optional)', 'ru': 'Загрузите медиафайлы (изображения, аудио, видео, необязательно)', 'ko': '미디어 파일 업로드 (이미지, 오디오, 비디오, 선택 사항)', 'fr': 'Téléverser des fichiers média (images, audio, vidéo, optionnel)'
        },
        'uploaded_file': {
            'zh': '当前已上传文件：', 'ja': '現在アップロード済みファイル：', 'en': 'Uploaded file: ', 'ru': 'Загруженный файл: ', 'ko': '업로드된 파일: ', 'fr': 'Fichier téléversé : '
        },
        'translation_expectation_optional': {
            'zh': '对翻译的期待（选填）', 'ja': '翻訳への期待（オプション）', 'en': 'Translation expectations (optional)', 'ru': 'Ожидания от перевода (необязательно)', 'ko': '번역에 대한 기대 (선택 사항)', 'fr': 'Attentes de traduction (optionnel)'
        },
        'translation_expectation_placeholder': {
            'zh': '如：希望译文更有文学性、希望译者多与我沟通等', 'ja': '例：より文学的な翻訳を希望、翻訳者とのコミュニケーションを希望など', 'en': 'e.g., more literary style, prefer more communication with translator, etc.', 'ru': 'например, более литературный стиль, больше общения с переводчиком и т.п.', 'ko': '예: 보다 문학적인 스타일, 번역가와의 소통을 선호 등', 'fr': 'ex. style plus littéraire, préférer plus de communication avec le traducteur, etc.'
        },
        'translation_requirements_checkbox': {
            'zh': '我希望翻译者能完成以下要求：', 'ja': '翻訳者に以下の要求を完成してもらいたい：', 'en': 'I want the translator to meet the following requirements:', 'ru': 'Я хочу, чтобы переводчик выполнил следующие требования:', 'ko': '번역가가 다음 요구 사항을 충족하길 바랍니다:', 'fr': 'Je souhaite que le traducteur respecte les exigences suivantes :'
        },
        'translation_requirements_note': {
            'zh': '（翻译者必须同意该要求才能进行翻译）', 'ja': '（翻訳者はこの要求に同意する必要があります）', 'en': '(The translator must agree to these requirements to proceed)', 'ru': '(Переводчик должен согласиться с этими требованиями, чтобы продолжить)', 'ko': '(번역가는 계속하려면 이 요구 사항에 동의해야 합니다)', 'fr': '(Le traducteur doit accepter ces exigences pour continuer)'
        },
        'translation_requirements': {
            'zh': '对翻译的要求', 'ja': '翻訳への要求', 'en': 'Translation requirements', 'ru': 'Требования к переводу', 'ko': '번역 요구사항', 'fr': 'Exigences de traduction'
        },
        'translation_requirements_placeholder': {
            'zh': '要求翻译者不要擅自进行传播、用于商业用途等', 'ja': '翻訳者に無断での配布、商業利用などを禁止するよう要求', 'en': 'Require translators not to distribute without permission or use for commercial purposes, etc.', 'ru': 'Требовать от переводчиков не распространять без разрешения или использовать в коммерческих целях и т.д.', 'ko': '번역자에게 무단 배포, 상업적 이용 등을 금지하도록 요구', 'fr': 'Exiger des traducteurs de ne pas distribuer sans autorisation ou utiliser à des fins commerciales, etc.'
        },
        'contact_before_translate_checkbox': {
            'zh': '我需要翻译者在翻译前提前联系我', 'ja': '翻訳前に翻訳者に連絡してもらいたい', 'en': 'I need the translator to contact me before translating', 'ru': 'Мне нужно, чтобы переводчик связался со мной перед переводом', 'ko': '번역 전에 번역가가 미리 연락해 주길 바랍니다', 'fr': 'J\'ai besoin que le traducteur me contacte avant de traduire'
        },
        'save_changes': {
            'zh': '保存修改', 'ja': '変更を保存', 'en': 'Save changes', 'ru': 'Сохранить изменения', 'ko': '변경 사항 저장', 'fr': 'Enregistrer les modifications'
        },
        'cancel': {
            'zh': '取消', 'ja': 'キャンセル', 'en': 'Cancel', 'ru': 'Отмена', 'ko': '취소', 'fr': 'Annuler'
        },
        'translate_page_title': {
            'zh': '翻译', 'ja': '翻訳', 'en': 'Translate', 'ru': 'Перевод', 'ko': '번역', 'fr': 'Traduire'
        },
        'video_not_supported': {
            'zh': '您的浏览器不支持视频播放。', 'ja': 'お使いのブラウザは動画再生をサポートしていません。', 'en': 'Your browser does not support video playback.', 'ru': 'Ваш браузер не поддерживает воспроизведение видео.', 'ko': '브라우저가 비디오 재생을 지원하지 않습니다.', 'fr': 'Votre navigateur ne prend pas en charge la lecture vidéo.'
        },
        'audio_not_supported': {
            'zh': '您的浏览器不支持音频播放。', 'ja': 'お使いのブラウザは音声再生をサポートしていません。', 'en': 'Your browser does not support audio playback.', 'ru': 'Ваш браузер не поддерживает воспроизведение аудио.', 'ko': '브라우저가 오디오 재생을 지원하지 않습니다.', 'fr': 'Votre navigateur ne prend pas en charge la lecture audio.'
        },
        'file_type': {
            'zh': '文件类型：', 'ja': 'ファイルタイプ：', 'en': 'File type: ', 'ru': 'Тип файла: ', 'ko': '파일 유형: ', 'fr': 'Type de fichier : '
        },
        'download': {
            'zh': '下载', 'ja': 'ダウンロード', 'en': 'Download', 'ru': 'Скачать', 'ko': '다운로드', 'fr': 'Télécharger'
        },
        'creator_expectation': {
            'zh': '创作者对翻译的期待', 'ja': 'クリエイターの翻訳への期待', 'en': "Creator's Translation Expectations", 'ru': 'Ожидания создателя от перевода', 'ko': '창작자의 번역 기대', 'fr': 'Attentes du créateur pour la traduction'
        },
        'creator_requirements': {
            'zh': '创作者对翻译的要求', 'ja': 'クリエイターの翻訳への要求', 'en': "Creator's Translation Requirements", 'ru': 'Требования создателя к переводу', 'ko': '창작자의 번역 요구사항', 'fr': 'Exigences du créateur pour la traduction'
        },
        'translation_content_label': {
            'zh': '翻译内容', 'ja': '翻訳内容', 'en': 'Translation content', 'ru': 'Содержимое перевода', 'ko': '번역 내용', 'fr': 'Contenu de la traduction'
        },
        'translation_content_placeholder': {
            'zh': '请在此输入翻译内容...', 'ja': 'ここに翻訳内容を入力してください...', 'en': 'Please enter the translation here...', 'ru': 'Введите здесь перевод...', 'ko': '여기에 번역 내용을 입력하세요...', 'fr': 'Veuillez saisir la traduction ici...'
        },
        'translation_attachment_label': {
            'zh': '翻译附件', 'ja': '翻訳添付ファイル', 'en': 'Translation attachments', 'ru': 'Вложения к переводу', 'ko': '번역 첨부 파일', 'fr': 'Pièces jointes de traduction'
        },
        'supported_formats': {
            'zh': '支持格式：图片、视频、音频、PDF、Word、文本文件', 'ja': 'サポート形式：画像、動画、音声、PDF、Word、テキストファイル', 'en': 'Supported formats: images, video, audio, PDF, Word, text files', 'ru': 'Поддерживаемые форматы: изображения, видео, аудио, PDF, Word, текстовые файлы', 'ko': '지원 형식: 이미지, 비디오, 오디오, PDF, Word, 텍스트 파일', 'fr': 'Formats pris en charge : images, vidéo, audio, PDF, Word, fichiers texte'
        },
        'submit_translation': {
            'zh': '提交翻译', 'ja': '翻訳を提出', 'en': 'Submit translation', 'ru': 'Отправить перевод', 'ko': '번역 제출', 'fr': 'Soumettre la traduction'
        },
        'save_as_draft': {
            'zh': '保存为草稿', 'ja': '下書きとして保存', 'en': 'Save as draft', 'ru': 'Сохранить как черновик', 'ko': '임시 저장', 'fr': 'Enregistrer comme brouillon'
        },
        'translation_guide': {
            'zh': '翻译指南', 'ja': '翻訳ガイド', 'en': 'Translation Guide', 'ru': 'Руководство по переводу', 'ko': '번역 가이드', 'fr': 'Guide de traduction'
        },
        'translation_tips': {
            'zh': '翻译技巧', 'ja': '翻訳のコツ', 'en': 'Translation Tips', 'ru': 'Советы по переводу', 'ko': '번역 팁', 'fr': 'Conseils de traduction'
        },
        'tip_understand': {
            'zh': '准确理解原文含义', 'ja': '原文の意味を正確に理解する', 'en': 'Understand the original accurately', 'ru': 'Точно понимать исходный текст', 'ko': '원문 의미를 정확히 이해', 'fr': 'Comprendre précisément le texte original'
        },
        'tip_natural': {
            'zh': '保持自然流畅的翻译', 'ja': '自然で読みやすい翻訳にする', 'en': 'Keep the translation natural and readable', 'ru': 'Делайте перевод естественным и читаемым', 'ko': '자연스럽고 읽기 쉽게 번역', 'fr': 'Rendre la traduction naturelle et lisible'
        },
        'tip_terms': {
            'zh': '注意专业术语统一', 'ja': '専門用語の統一を心がける', 'en': 'Keep terminology consistent', 'ru': 'Соблюдайте единообразие терминологии', 'ko': '전문 용어 일관성 유지', 'fr': 'Maintenir une terminologie cohérente'
        },
        'tip_culture': {
            'zh': '考虑文化差异', 'ja': '文化的な違いを考慮する', 'en': 'Consider cultural differences', 'ru': 'Учитывайте культурные различия', 'ko': '문화적 차이 고려', 'fr': 'Prendre en compte les différences culturelles'
        },
        'notes': {
            'zh': '注意事项', 'ja': '注意事項', 'en': 'Notes', 'ru': 'Примечания', 'ko': '주의 사항', 'fr': 'Remarques'
        },
        'note_avoid_mt': {
            'zh': '避免直接使用机器翻译', 'ja': '機械翻訳の直接使用は避ける', 'en': 'Avoid direct use of machine translation', 'ru': 'Избегайте прямого использования машинного перевода', 'ko': '기계 번역의 직접 사용을 피하세요', 'fr': 'Éviter l\'utilisation directe de la traduction automatique'
        },
        'note_not_distort': {
            'zh': '不要歪曲原文意图', 'ja': '原文の意図を歪めない', 'en': 'Do not distort the original intent', 'ru': 'Не искажайте замысел оригинала', 'ko': '원래 의도를 왜곡하지 마세요', 'fr': "Ne pas déformer l'intention originale"
        },
        'note_politeness': {
            'zh': '注意使用适当的敬语', 'ja': '適切な敬語の使用を心がける', 'en': 'Use appropriate politeness', 'ru': 'Используйте соответствующую вежливость', 'ko': '적절한 경어 사용', 'fr': 'Utiliser des marques de politesse appropriées'
        },
        'work_info': {
            'zh': '作品信息', 'ja': '作品情報', 'en': 'Work Info', 'ru': 'Информация о работе', 'ko': '작품 정보', 'fr': 'Informations sur l\'œuvre'
        },
        'language_pair': {
            'zh': '语言对：', 'ja': '言語ペア：', 'en': 'Language pair: ', 'ru': 'Пара языков: ', 'ko': '언어 쌍: ', 'fr': 'Paire de langues : '
        },
        'created_at_label': {
            'zh': '创建时间：', 'ja': '作成日：', 'en': 'Created at: ', 'ru': 'Дата создания: ', 'ko': '작성일: ', 'fr': 'Date de création : '
        },
        'original_copied': {
            'zh': '原文已复制到剪贴板', 'ja': '原文がクリップボードにコピーされました', 'en': 'Original text copied to clipboard', 'ru': 'Исходный текст скопирован в буфер обмена', 'ko': '원문이 클립보드에 복사되었습니다', 'fr': "Le texte original a été copié dans le presse-papiers"
        },
        'characters': {
            'zh': '字符数：', 'ja': '文字数：', 'en': 'Characters: ', 'ru': 'Символов: ', 'ko': '문자 수: ', 'fr': 'Caractères : '
        },
        'words': {
            'zh': '词数：', 'ja': '単語数：', 'en': 'Words: ', 'ru': 'Слов: ', 'ko': '단어 수: ', 'fr': 'Mots : '
        },
        'attachment': {
            'zh': '附件', 'ja': '添付ファイル', 'en': 'Attachment', 'ru': 'Вложение', 'ko': '첨부파일', 'fr': 'Pièce jointe'
        },
        'download_attachment': {
            'zh': '下载附件', 'ja': '添付ファイルをダウンロード', 'en': 'Download Attachment', 'ru': 'Скачать вложение', 'ko': '첨부파일 다운로드', 'fr': 'Télécharger la pièce jointe'
        },
        'contact_before_translate_title': {
            'zh': '翻译前需要联系', 'ja': '翻訳前の連絡が必要', 'en': 'Contact Required Before Translation', 'ru': 'Требуется связь перед переводом', 'ko': '번역 전 연락 필요', 'fr': 'Contact requis avant traduction'
        },
        'contact_before_translate_desc': {
            'zh': '本作品创作者要求：翻译前请先私信联系作者！', 'ja': 'この作品のクリエイターは要求します：翻訳前に作者にメッセージを送信してください！', 'en': 'The creator of this work requires: Please message the author before translating!', 'ru': 'Создатель этой работы требует: Пожалуйста, напишите автору перед переводом!', 'ko': '이 작품의 창작자가 요구합니다: 번역하기 전에 먼저 작가에게 메시지를 보내주세요!', 'fr': 'Le créateur de cette œuvre exige : Veuillez contacter l\'auteur avant de traduire !'
        },
        'original_content': {
            'zh': '原文内容', 'ja': '原文内容', 'en': 'Original Content', 'ru': 'Исходное содержимое', 'ko': '원문 내용', 'fr': 'Contenu original'
        },
        'creator_expectation': {
            'zh': '创作者对翻译的期待', 'ja': 'クリエイターの翻訳への期待', 'en': 'Creator\'s Translation Expectations', 'ru': 'Ожидания создателя от перевода', 'ko': '창작자의 번역 기대', 'fr': 'Attentes du créateur pour la traduction'
        },
        'creator_requirements': {
            'zh': '创作者对翻译的要求', 'ja': 'クリエイターの翻訳への要求', 'en': 'Creator\'s Translation Requirements', 'ru': 'Требования создателя к переводу', 'ko': '창작자의 번역 요구사항', 'fr': 'Exigences du créateur pour la traduction'
        },
        'translator': {
            'zh': '翻译者', 'ja': '翻訳者', 'en': 'Translator', 'ru': 'Переводчик', 'ko': '번역가', 'fr': 'Traducteur'
        },
        'translator_expectation': {
            'zh': '对作者的期待/要求', 'ja': 'のクリエイターへの期待/要求', 'en': 'Expectations/Requirements for Creator', 'ru': 'Ожидания/Требования к создателю', 'ko': '작가에 대한 기대/요구사항', 'fr': 'Attentes/Exigences pour le créateur'
        },
        'translation_content': {
            'zh': '翻译内容', 'ja': '翻訳内容', 'en': 'Translation Content', 'ru': 'Содержимое перевода', 'ko': '번역 내용', 'fr': 'Contenu de la traduction'
        },
        'multiple_translators': {
            'zh': '多人翻译', 'ja': '複数翻訳者', 'en': 'Multiple Translators', 'ru': 'Несколько переводчиков', 'ko': '다중 번역가', 'fr': 'Traducteurs multiples'
        },
        'author_like': {
            'zh': '收到作者的赞', 'ja': '作者からもらったいいね', 'en': 'Received Author\'s Like', 'ru': 'Получен лайк от автора', 'ko': '작가로부터 받은 좋아요', 'fr': 'J\'aime reçu de l\'auteur'
        },
        'accept': {
            'zh': '接受', 'ja': '承認', 'en': 'Accept', 'ru': 'Принять', 'ko': '수락', 'fr': 'Accepter'
        },
        'add_correction': {
            'zh': '添加校正', 'ja': '校正を追加', 'en': 'Add Correction', 'ru': 'Добавить исправление', 'ko': '교정 추가', 'fr': 'Ajouter une correction'
        },
        'cannot_correct_own': {
            'zh': '您无法对自己的翻译进行校正', 'ja': '自分自身の翻訳を校正することはできません', 'en': 'You cannot correct your own translation', 'ru': 'Вы не можете исправлять свой собственный перевод', 'ko': '자신의 번역을 교정할 수 없습니다', 'fr': 'Vous ne pouvez pas corriger votre propre traduction'
        },
        'correction_content': {
            'zh': '校正内容', 'ja': '校正内容', 'en': 'Correction Content', 'ru': 'Содержимое исправления', 'ko': '교정 내용', 'fr': 'Contenu de la correction'
        },
        'correction_content_label': {
            'zh': '校正内容：', 'ja': '校正内容：', 'en': 'Correction Content:', 'ru': 'Содержимое исправления:', 'ko': '교정 내용:', 'fr': 'Contenu de la correction:'
        },
        'correction_content_placeholder': {
            'zh': '请输入校正内容...', 'ja': '校正内容を入力...', 'en': 'Enter correction content...', 'ru': 'Введите содержимое исправления...', 'ko': '교정 내용을 입력하세요...', 'fr': 'Entrez le contenu de la correction...'
        },
        'correction_notes_label': {
            'zh': '校正说明：', 'ja': '校正说明：', 'en': 'Correction Notes:', 'ru': 'Примечания к исправлению:', 'ko': '교정 설명:', 'fr': 'Notes de correction:'
        },
        'correction_notes_placeholder': {
            'zh': '请输入校正说明（可选）...', 'ja': '校正说明を入力（任意）...', 'en': 'Enter correction notes (optional)...', 'ru': 'Введите примечания к исправлению (необязательно)...', 'ko': '교정 설명을 입력하세요 (선택사항)...', 'fr': 'Entrez les notes de correction (optionnel)...'
        },
        'submit_correction': {
            'zh': '提交校正', 'ja': '校正を提出', 'en': 'Submit Correction', 'ru': 'Отправить исправление', 'ko': '교정 제출', 'fr': 'Soumettre la correction'
        },
        'correction_list': {
            'zh': '校正列表', 'ja': '校正一覧', 'en': 'Correction List', 'ru': 'Список исправлений', 'ko': '교정 목록', 'fr': 'Liste des corrections'
        },
        'corrections_for': {
            'zh': '对', 'ja': 'に対する', 'en': 'Corrections for', 'ru': 'Исправления для', 'ko': '에 대한', 'fr': 'Corrections pour'
        },
        'translation_corrections': {
            'zh': '的校正', 'ja': 'の校正', 'en': '\'s Translation', 'ru': 'Перевод', 'ko': '의 번역', 'fr': 'Traduction de'
        },
        'translation_attachments': {
            'zh': '翻译附件', 'ja': '翻訳添付ファイル', 'en': 'Translation Attachments', 'ru': 'Вложения перевода', 'ko': '번역 첨부파일', 'fr': 'Pièces jointes de traduction'
        },
        'admin_operations': {
            'zh': '管理员操作', 'ja': '管理者操作', 'en': 'Admin Operations', 'ru': 'Операции администратора', 'ko': '관리자 작업', 'fr': 'Opérations d\'administrateur'
        },
        'confirm_delete_correction': {
            'zh': '确定要删除这个校正吗？', 'ja': 'この校正を削除しますか？', 'en': 'Are you sure you want to delete this correction?', 'ru': 'Вы уверены, что хотите удалить это исправление?', 'ko': '이 교정을 삭제하시겠습니까?', 'fr': 'Êtes-vous sûr de vouloir supprimer cette correction?'
        },
        'correction_comments': {
            'zh': '校正评论', 'ja': '校正コメント', 'en': 'Correction Comments', 'ru': 'Комментарии к исправлению', 'ko': '교정 댓글', 'fr': 'Commentaires de correction'
        },
        'correction_comment_placeholder': {
            'zh': '输入对校正的评论...', 'ja': '校正についてコメントを入力...', 'en': 'Enter comments about the correction...', 'ru': 'Введите комментарии к исправлению...', 'ko': '교정에 대한 댓글을 입력하세요...', 'fr': 'Entrez des commentaires sur la correction...'
        },
        'post_comment': {
            'zh': '发表评论', 'ja': 'コメントを投稿', 'en': 'Post Comment', 'ru': 'Оставить комментарий', 'ko': '댓글 작성', 'fr': 'Publier un commentaire'
        },
        'translation_comments': {
            'zh': '翻译评论', 'ja': '翻訳コメント', 'en': 'Translation Comments', 'ru': 'Комментарии к переводу', 'ko': '번역 댓글', 'fr': 'Commentaires de traduction'
        },
        'translator_work_section': {
            'zh': '翻译者工作区域', 'ja': '翻訳者の作業エリア', 'en': 'Translator Work Section', 'ru': 'Рабочая область переводчика', 'ko': '번역가 작업 영역', 'fr': 'Section de travail du traducteur'
        },
        'translator_corrections': {
            'zh': '的校正', 'ja': 'の校正', 'en': '\'s Corrections', 'ru': 'Исправления', 'ko': '의 교정', 'fr': 'Corrections de'
        },
        'translator_comments': {
            'zh': '的评论', 'ja': 'のコメント', 'en': '\'s Comments', 'ru': 'Комментарии', 'ko': '의 댓글', 'fr': 'Commentaires de'
        },
        'translation_comment_note': {
            'zh': '', 'ja': '', 'en': '', 'ru': '', 'ko': '', 'fr': ''
        },
        'translation_comment_placeholder': {
            'zh': '输入对翻译的评论...', 'ja': '翻訳についてコメントを入力...', 'en': 'Enter comments about the translation...', 'ru': 'Введите комментарии к переводу...', 'ko': '번역에 대한 댓글을 입력하세요...', 'fr': 'Entrez des commentaires sur la traduction...'
        },
        'post_translation_comment': {
            'zh': '发表翻译评论', 'ja': '翻訳コメントを投稿', 'en': 'Post Translation Comment', 'ru': 'Оставить комментарий к переводу', 'ko': '번역 댓글 작성', 'fr': 'Publier un commentaire de traduction'
        },
        'download_translation_attachment': {
            'zh': '下载翻译附件', 'ja': '翻訳添付ファイルをダウンロード', 'en': 'Download Translation Attachment', 'ru': 'Скачать вложение перевода', 'ko': '번역 첨부파일 다운로드', 'fr': 'Télécharger la pièce jointe de traduction'
        },
        'start_translation': {
            'zh': '开始翻译', 'ja': '翻訳を開始', 'en': 'Start Translation', 'ru': 'Начать перевод', 'ko': '번역 시작', 'fr': 'Commencer la traduction'
        },
        'start_translation_desc': {
            'zh': '如果您想翻译这个作品，请点击翻译按钮。', 'ja': 'この作品を翻訳したい場合は、翻訳ボタンをクリックしてください。', 'en': 'If you want to translate this work, please click the translate button.', 'ru': 'Если вы хотите перевести эту работу, нажмите кнопку перевода.', 'ko': '이 작품을 번역하고 싶다면 번역 버튼을 클릭하세요.', 'fr': 'Si vous voulez traduire cette œuvre, veuillez cliquer sur le bouton de traduction.'
        },
        'translation_request': {
            'zh': '翻译请求', 'ja': '翻訳リクエスト', 'en': 'Translation Request', 'ru': 'Запрос на перевод', 'ko': '번역 요청', 'fr': 'Demande de traduction'
        },
        'translator_expectation_label': {
            'zh': '翻译者的期待/要求：', 'ja': '翻訳者の期待/要求：', 'en': 'Translator\'s Expectations/Requirements:', 'ru': 'Ожидания/Требования переводчика:', 'ko': '번역가의 기대/요구사항:', 'fr': 'Attentes/Exigences du traducteur:'
        },
        'approve': {
            'zh': '同意', 'ja': '承認', 'en': 'Approve', 'ru': 'Одобрить', 'ko': '승인', 'fr': 'Approuver'
        },
        'confirm_reject_request': {
            'zh': '确定要拒绝这个翻译请求吗？', 'ja': 'この翻訳リクエストを却下しますか？', 'en': 'Are you sure you want to reject this translation request?', 'ru': 'Вы уверены, что хотите отклонить этот запрос на перевод?', 'ko': '이 번역 요청을 거부하시겠습니까?', 'fr': 'Êtes-vous sûr de vouloir rejeter cette demande de traduction?'
        },
        'confirm_untrust_translator': {
            'zh': '确定要取消信赖该翻译者吗？', 'ja': 'この翻訳者の信頼を解除しますか？', 'en': 'Are you sure you want to remove trust from this translator?', 'ru': 'Вы уверены, что хотите снять доверие с этого переводчика?', 'ko': '이 번역가에 대한 신뢰를 해제하시겠습니까?', 'fr': 'Êtes-vous sûr de vouloir retirer la confiance de ce traducteur?'
        },
        'confirm_delete_translation': {
            'zh': '确定要删除这个翻译吗？', 'ja': 'この翻訳を削除しますか？', 'en': 'Are you sure you want to delete this translation?', 'ru': 'Вы уверены, что хотите удалить этот перевод?', 'ko': '이 번역을 삭제하시겠습니까?', 'fr': 'Êtes-vous sûr de vouloir supprimer cette traduction?'
        },
        'general_request': {
            'zh': '的一般要求', 'ja': 'の一般要求', 'en': '\'s General Request', 'ru': 'Общий запрос', 'ko': '의 일반 요청', 'fr': 'Demande générale de'
        },
        'confirm_delete_comment': {
            'zh': '确定要删除这个评论吗？', 'ja': 'このコメントを削除しますか？', 'en': 'Are you sure you want to delete this comment?', 'ru': 'Вы уверены, что хотите удалить этот комментарий?', 'ko': '이 댓글을 삭제하시겠습니까?', 'fr': 'Êtes-vous sûr de vouloir supprimer ce commentaire?'
        },
        'confirm_delete_work': {
            'zh': '确定要删除这个作品吗？', 'ja': 'この作品を削除しますか？', 'en': 'Are you sure you want to delete this work?', 'ru': 'Вы уверены, что хотите удалить эту работу?', 'ko': '이 작품을 삭제하시겠습니까?', 'fr': 'Êtes-vous sûr de vouloir supprimer cette œuvre?'
        },
        'confirm_clear_translation': {
            'zh': '确定要清空翻译内容吗？', 'ja': '翻訳内容をクリアしますか？', 'en': 'Are you sure you want to clear the translation content?', 'ru': 'Вы уверены, что хотите очистить содержимое перевода?', 'ko': '번역 내용을 지우시겠습니까?', 'fr': 'Êtes-vous sûr de vouloir effacer le contenu de la traduction?'
        },
        'confirm_delete_translation_irreversible': {
            'zh': '确定要删除这个翻译吗？此操作不可撤销。', 'ja': 'この翻訳を削除しますか？この操作は取り消せません。', 'en': 'Are you sure you want to delete this translation? This action cannot be undone.', 'ru': 'Вы уверены, что хотите удалить этот перевод? Это действие нельзя отменить.', 'ko': '이 번역을 삭제하시겠습니까? 이 작업은 취소할 수 없습니다.', 'fr': 'Êtes-vous sûr de vouloir supprimer cette traduction? Cette action ne peut pas être annulée.'
        },
        'confirm_clear_all_data': {
            'zh': '确定要清理所有数据吗？此操作不可恢复！', 'ja': 'すべてのデータをクリアしますか？この操作は復元できません！', 'en': 'Are you sure you want to clear all data? This operation cannot be restored!', 'ru': 'Вы уверены, что хотите очистить все данные? Эта операция не может быть восстановлена!', 'ko': '모든 데이터를 지우시겠습니까? 이 작업은 복원할 수 없습니다!', 'fr': 'Êtes-vous sûr de vouloir effacer toutes les données? Cette operation ne peut pas être restaurée!'
        },
        'alert_enter_deletion_reason': {
            'zh': '请输入删除理由', 'ja': '削除理由を入力してください', 'en': 'Please enter a deletion reason', 'ru': 'Пожалуйста, введите причину удаления', 'ko': '삭제 이유를 입력해 주세요', 'fr': 'Veuillez entrer une raison de suppression'
        },
        'already_admin': {
            'zh': '您已经是管理员了', 'ja': 'あなたは既に管理者です', 'en': 'You are already an administrator', 'ru': 'Вы уже администратор', 'ko': '이미 관리자입니다', 'fr': 'Vous êtes déjà administrateur'
        },
        'admin_request_pending': {
            'zh': '您已经有一个待审核的管理员申请', 'ja': '審査待ちの管理者申請が既にあります', 'en': 'You already have a pending administrator application', 'ru': 'У вас уже есть заявка на администратора на рассмотрении', 'ko': '이미 대기 중인 관리자 신청이 있습니다', 'fr': 'Vous avez déjà une demande d\'administrateur en attente'
        },
        'please_enter_reason': {
            'zh': '请填写申请理由', 'ja': '申請理由を入力してください', 'en': 'Please enter application reason', 'ru': 'Пожалуйста, введите причину заявки', 'ko': '신청 이유를 입력해 주세요', 'fr': 'Veuillez entrer la raison de la demande'
        },
        'admin_request_submitted': {
            'zh': '管理员申请已提交，请等待审核', 'ja': '管理者申請が提出されました、審査をお待ちください', 'en': 'Administrator application submitted, please wait for review', 'ru': 'Заявка на администратора подана, пожалуйста, ждите рассмотрения', 'ko': '관리자 신청이 제출되었습니다. 검토를 기다려 주세요', 'fr': 'Demande d\'administrateur soumise, veuillez attendre l\'examen'
        },
        'insufficient_permissions': {
            'zh': '权限不足', 'ja': '権限が不足しています', 'en': 'Insufficient permissions', 'ru': 'Недостаточно прав', 'ko': '권한이 부족합니다', 'fr': 'Permissions insuffisantes'
        },
        'request_already_processed': {
            'zh': '该申请已经被处理过了', 'ja': 'この申請は既に処理されています', 'en': 'This request has already been processed', 'ru': 'Эта заявка уже обработана', 'ko': '이 신청은 이미 처리되었습니다', 'fr': 'Cette demande a déjà été traitée'
        },
        'admin_request_approved': {
            'zh': '已批准 {} 的管理员申请',
            'ja': '{}の管理者申請が承認されました',
            'en': 'Approved {} administrator application',
            'ru': 'Одобрена заявка {} на администратора',
            'ko': '{}의 관리자 신청이 승인되었습니다',
            'fr': 'Demande d\'administrateur de {} approuvée'
        },
        'admin_request_rejected': {
            'zh': '已拒绝 {} 的管理员申请',
            'ja': '{}の管理者申請が拒否されました',
            'en': 'Rejected {} administrator application',
            'ru': 'Отклонена заявка {} на администратора',
            'ko': '{}의 관리자 신청이 거부되었습니다',
            'fr': 'Demande d\'administrateur de {} rejetée'
        },
        'completed_work_cannot_edit': {
            'zh': '已完成的作品不能编辑',
            'ja': '完了した作品は編集できません',
            'en': 'Completed works cannot be edited',
            'ru': 'Завершенные работы нельзя редактировать',
            'ko': '완료된 작품은 편집할 수 없습니다',
            'fr': 'Les œuvres terminées ne peuvent pas être modifiées'
        },
        'completed_work_cannot_delete': {
            'zh': '已完成的作品不能删除',
            'ja': '完了した作品は削除できません',
            'en': 'Completed works cannot be deleted',
            'ru': 'Завершенные работы нельзя удалять',
            'ko': '완료된 작품은 삭제할 수 없습니다',
            'fr': 'Les œuvres terminées ne peuvent pas être supprimées'
        },
        'delete_work_error': {
            'zh': '删除作品时出错: {}',
            'ja': '作品削除中にエラーが発生しました: {}',
            'en': 'Error deleting work: {}',
            'ru': 'Ошибка при удалении работы: {}',
            'ko': '작품 삭제 중 오류 발생: {}',
            'fr': 'Erreur lors de la suppression de l\'œuvre: {}'

        },
        'completed_work_translation_cannot_edit': {
            'zh': '已完成的作品的翻译不能编辑',
            'ja': '完了した作品の翻訳は編集できません',
            'en': 'Translation of completed works cannot be edited',
            'ru': 'Перевод завершенных работ нельзя редактировать',
            'ko': '완료된 작품의 번역은 편집할 수 없습니다',
            'fr': 'La traduction des œuvres terminées ne peut pas être modifiée'
        },
        'completed_work_translation_cannot_delete': {
            'zh': '已完成的作品的翻译不能删除', 'ja': '完了した作品の翻訳は削除できません', 'en': 'Translation of completed works cannot be deleted', 'ru': 'Перевод завершенных работ нельзя удалять', 'ko': '완료된 작품의 번역은 삭제할 수 없습니다', 'fr': 'La traduction des œuvres terminées ne peut pas être supprimée'
        },
        'comments': {
            'zh': '评论', 'ja': 'コメント', 'en': 'Comments', 'ru': 'Комментарии', 'ko': '댓글', 'fr': 'Commentaires'
        },
        'work_comment_note': {
            'zh': '此评论针对整个作品内容', 'ja': 'このコメントは作品全体について表示されます', 'en': 'This comment is for the entire work content', 'ru': 'Этот комментарий для всего содержимого работы', 'ko': '이 댓글은 전체 작품 내용에 대한 것입니다', 'fr': 'Ce commentaire est pour l\'ensemble du contenu de l\'œuvre'
        },
        'comment_placeholder': {
            'zh': '输入评论...', 'ja': 'コメントを入力...', 'en': 'Enter comment...', 'ru': 'Введите комментарий...', 'ko': '댓글을 입력하세요...', 'fr': 'Entrez un commentaire...'
        },
        'post_work_comment': {
            'zh': '发表作品评论', 'ja': '作品コメントを投稿', 'en': 'Post Work Comment', 'ru': 'Оставить комментарий к работе', 'ko': '작품 댓글 작성', 'fr': 'Publier un commentaire sur l\'œuvre'
        },
        'no_comments': {
            'zh': '暂无评论', 'ja': 'まだコメントがありません', 'en': 'No comments yet', 'ru': 'Пока нет комментариев', 'ko': '아직 댓글이 없습니다', 'fr': 'Aucun commentaire pour le moment'
        },
        'translation_operations': {
            'zh': '翻译操作', 'ja': '翻訳操作', 'en': 'Translation Operations', 'ru': 'Операции перевода', 'ko': '번역 작업', 'fr': 'Opérations de traduction'
        },
        'message_author': {
            'zh': '私信作者', 'ja': '作者にメッセージ', 'en': 'Message Author', 'ru': 'Написать автору', 'ko': '작가에게 메시지', 'fr': 'Message à l\'auteur'
        },
        'need_contact_author': {
            'zh': '翻译前需要联系作者', 'ja': '翻訳前に作者に連絡が必要です', 'en': 'Need to contact author before translation', 'ru': 'Нужно связаться с автором перед переводом', 'ko': '번역 전에 작가와 연락해야 합니다', 'fr': 'Besoin de contacter l\'auteur avant la traduction'
        },
        'confirm_translation_requirements': {
            'zh': '确认翻译要求', 'ja': '翻訳要求確認', 'en': 'Confirm Translation Requirements', 'ru': 'Подтвердить требования к переводу', 'ko': '번역 요구사항 확인', 'fr': 'Confirmer les exigences de traduction'
        },
        'need_agree_requirements': {
            'zh': '需要同意翻译要求', 'ja': '翻訳要求に同意する必要があります', 'en': 'Need to agree to translation requirements', 'ru': 'Нужно согласиться с требованиями к переводу', 'ko': '번역 요구사항에 동의해야 합니다', 'fr': 'Besoin d\'accepter les exigences de traduction'
        },
        'trusted_translator': {
            'zh': '作为被信任的翻译者', 'ja': '信頼された翻訳者として', 'en': 'As a trusted translator', 'ru': 'Как доверенный переводчик', 'ko': '신뢰받는 번역가로서', 'fr': 'En tant que traducteur de confiance'
        },
        'already_translated': {
            'zh': '该作品已有翻译', 'ja': 'この作品は既に翻訳されています', 'en': 'This work has already been translated', 'ru': 'Эта работа уже переведена', 'ko': '이 작품은 이미 번역되었습니다', 'fr': 'Cette œuvre a déjà été traduite'
        },
        'you_already_translated': {
            'zh': '您已经翻译过这个作品', 'ja': 'この作品は既に翻訳済みです', 'en': 'You have already translated this work', 'ru': 'Вы уже перевели эту работу', 'ko': '이미 이 작품을 번역했습니다', 'fr': 'Vous avez déjà traduit cette œuvre'
        },
        'multiple_translators_allowed': {
            'zh': '允许多人翻译', 'ja': '複数の翻訳者を許可', 'en': 'Multiple translators allowed', 'ru': 'Разрешено несколько переводчиков', 'ko': '여러 번역가 허용', 'fr': 'Plusieurs traducteurs autorisés'
        },
        'need_translator_qualification': {
            'zh': '需要翻译者资格', 'ja': '翻訳者資格が必要です', 'en': 'Need translator qualification', 'ru': 'Нужна квалификация переводчика', 'ko': '번역가 자격이 필요합니다', 'fr': 'Besoin d\'une qualification de traducteur'
        },
        'apply_translator': {
            'zh': '申请成为翻译者', 'ja': '翻訳者申請', 'en': 'Apply to become a translator', 'ru': 'Подать заявку на переводчика', 'ko': '번역가 신청', 'fr': 'Postuler pour devenir traducteur'
        },
        'work_info': {
            'zh': '作品信息', 'ja': '作品情報', 'en': 'Work Information', 'ru': 'Информация о работе', 'ko': '작품 정보', 'fr': 'Informations sur l\'œuvre'
        },
        'language': {
            'zh': '语言：', 'ja': '言語：', 'en': 'Language:', 'ru': 'Язык:', 'ko': '언어:', 'fr': 'Langue:'
        },
        'category': {
            'zh': '分类：', 'ja': 'カテゴリー：', 'en': 'Category:', 'ru': 'Категория:', 'ko': '카테고리:', 'fr': 'Catégorie:'
        },
        'created_date': {
            'zh': '创建时间：', 'ja': '作成日：', 'en': 'Created Date:', 'ru': 'Дата создания:', 'ko': '생성 날짜:', 'fr': 'Date de création:'
        },
        'status': {
            'zh': '状态：', 'ja': 'ステータス：', 'en': 'Status:', 'ru': 'Статус:', 'ko': '상태:', 'fr': 'Statut:'
        },
        'author_info': {
            'zh': '作者信息', 'ja': '作者情報', 'en': 'Author Information', 'ru': 'Информация об авторе', 'ko': '작가 정보', 'fr': 'Informations sur l\'auteur'
        },
        'reviewer': {
            'zh': '校正者', 'ja': '校正者', 'en': 'Reviewer', 'ru': 'Рецензент', 'ko': '검토자', 'fr': 'Réviseur'
        },
        'admin': {
            'zh': '管理员', 'ja': '管理者', 'en': 'Administrator', 'ru': 'Администратор', 'ko': '관리자', 'fr': 'Administrateur'
        },
        'works': {
            'zh': '作品', 'ja': '作品', 'en': 'Works', 'ru': 'Работы', 'ko': '작품', 'fr': 'Œuvres'
        },
        'translations': {
            'zh': '翻译', 'ja': '翻訳', 'en': 'Translations', 'ru': 'Переводы', 'ko': '번역', 'fr': 'Traductions'
        },
        'likes': {
            'zh': '点赞', 'ja': 'いいね', 'en': 'Likes', 'ru': 'Лайки', 'ko': '좋아요', 'fr': 'J\'aime'
        },
        'registration_date': {
            'zh': '注册时间：', 'ja': '登録日：', 'en': 'Registration Date:', 'ru': 'Дата регистрации:', 'ko': '가입 날짜:', 'fr': 'Date d\'inscription:'
        },
        'preferred_language': {
            'zh': '偏好语言：', 'ja': '好みの言語：', 'en': 'Preferred Language:', 'ru': 'Предпочитаемый язык:', 'ko': '선호 언어:', 'fr': 'Langue préférée:'
        },
        'chinese': {
            'zh': '中文', 'ja': '中国語', 'en': 'Chinese', 'ru': 'Китайский', 'ko': '중국어', 'fr': 'Chinois'
        },
        'japanese': {
            'zh': '日文', 'ja': '日本語', 'en': 'Japanese', 'ru': 'Японский', 'ko': '일본어', 'fr': 'Japonais'
        },
        'english': {
            'zh': '英文', 'ja': '英語', 'en': 'English', 'ru': 'Английский', 'ko': '영어', 'fr': 'Anglais'
        },
        'russian': {
            'zh': '俄文', 'ja': 'ロシア語', 'en': 'Russian', 'ru': 'Русский', 'ko': '러시아어', 'fr': 'Russe'
        },
        'korean': {
            'zh': '韩文', 'ja': '韓国語', 'en': 'Korean', 'ru': 'Корейский', 'ko': '한국어', 'fr': 'Coréen'
        },
        'french': {
            'zh': '法文', 'ja': 'フランス語', 'en': 'French', 'ru': 'Французский', 'ko': '프랑스어', 'fr': 'Français'
        },
        'view_profile': {
            'zh': '查看资料', 'ja': 'プロフィール', 'en': 'View Profile', 'ru': 'Просмотр профиля', 'ko': '프로필 보기', 'fr': 'Voir le profil'
        },
        'accept_translation': {
            'zh': '接受翻译', 'ja': '翻訳を承認', 'en': 'Accept Translation', 'ru': 'Принять перевод', 'ko': '번역 수락', 'fr': 'Accepter la traduction'
        },
        'evaluation_optional': {
            'zh': '评价（可选）', 'ja': '評価（オプション）', 'en': 'Evaluation (Optional)', 'ru': 'Оценка (необязательно)', 'ko': '평가 (선택사항)', 'fr': 'Évaluation (optionnel)'
        },
        'evaluation_placeholder': {
            'zh': '请输入对翻译的评价...', 'ja': '翻訳についての評価を入力してください...', 'en': 'Please enter your evaluation of the translation...', 'ru': 'Пожалуйста, введите вашу оценку перевода...', 'ko': '번역에 대한 평가를 입력하세요...', 'fr': 'Veuillez entrer votre évaluation de la traduction...'
        },
        'add_like_to_translation': {
            'zh': '为翻译点赞', 'ja': '翻訳にいいねを追加', 'en': 'Add like to translation', 'ru': 'Добавить лайк к переводу', 'ko': '번역에 좋아요 추가', 'fr': 'Ajouter un j\'aime à la traduction'
        },
        'already_accepted': {
            'zh': '您已经接受过这个翻译了',
            'ja': '既にこの翻訳を承認しています',
            'en': 'You have already accepted this translation',
            'ru': 'Вы уже приняли этот перевод',
            'ko': '이미 이 번역을 승인했습니다',
            'fr': 'Vous avez déjà accepté cette traduction'
        },
        'translation_accepted': {
            'zh': '翻译已接受！',
            'ja': '翻訳が承認されました！',
            'en': 'Translation accepted!',
            'ru': 'Перевод принят!',
            'ko': '번역이 승인되었습니다!',
            'fr': 'Traduction acceptée!'
        },
        'only_author_unaccept': {
            'zh': '只有作品作者可以取消接受翻译',
            'ja': '作品の作者のみが翻訳の承認を取り消すことができます',
            'en': 'Only the work author can unaccept translation',
            'ru': 'Только автор работы может отменить принятие перевода',
            'ko': '작품 작가만 번역 승인을 취소할 수 있습니다',
            'fr': 'Seul l\'auteur de l\'œuvre peut annuler l\'acceptation de la traduction'
        },
        'not_accepted': {
            'zh': '您还没有接受过这个翻译',
            'ja': 'まだこの翻訳を承認していません',
            'en': 'You have not accepted this translation yet',
            'ru': 'Вы еще не приняли этот перевод',
            'ko': '아직 이 번역을 승인하지 않았습니다',
            'fr': 'Vous n\'avez pas encore accepté cette traduction'
        },
        'translation_unaccepted': {
            'zh': '已取消接受翻译。',
            'ja': '翻訳の承認を取り消しました。',
            'en': 'Translation acceptance has been cancelled.',
            'ru': 'Принятие перевода было отменено.',
            'ko': '번역 승인이 취소되었습니다.',
            'fr': 'L\'acceptation de la traduction a été annulée.'
        },
        'author_accept_irreversible': {
            'zh': '作者已承认翻译不可取消，请重新考虑。',
            'ja': '作者は翻訳の取り消しができないことを承認しました。再考してください。',
            'en': 'The author has acknowledged that the translation cannot be cancelled, please reconsider.',
            'ru': 'Автор признал, что перевод нельзя отменить, пожалуйста, пересмотрите.',
            'ko': '작가는 번역을 취소할 수 없다는 것을 인정했습니다. 다시 고려해 주세요.',
            'fr': 'L\'auteur a reconnu que la traduction ne peut pas être annulée, veuillez reconsidérer.'
        },
        'translation_content_required': {
            'zh': '翻译内容不能为空',
            'ja': '翻訳内容は空にできません',
            'en': 'Translation content cannot be empty',
            'ru': 'Содержание перевода не может быть пустым',
            'ko': '번역 내용은 비워둘 수 없습니다',
            'fr': 'Le contenu de la traduction ne peut pas être vide'
        },
        'category_required': {
            'zh': '请选择作品分类',
            'ja': '作品のカテゴリーを選択してください',
            'en': 'Please select a work category',
            'ru': 'Пожалуйста, выберите категорию работы',
            'ko': '작품 카테고리를 선택해 주세요',
            'fr': 'Veuillez sélectionner une catégorie d\'œuvre'
        },
                         'languages_cannot_be_same': {
                     'zh': '原始语言和目标语言不能相同（除了"其他"）',
                     'ja': '原文言語と目標言語は同じにできません（「その他」を除く）',
                     'en': 'Original language and target language cannot be the same (except "Other")',
                     'ru': 'Исходный язык и целевой язык не могут быть одинаковыми (кроме "Другое")',
                     'ko': '원본 언어와 목표 언어는 같을 수 없습니다 ("기타" 제외)',
                     'fr': 'La langue originale et la langue cible ne peuvent pas être identiques (sauf "Autre")'
                 },
                 'validation_error': {
                     'zh': '验证错误',
                     'ja': '検証エラー',
                     'en': 'Validation Error',
                     'ru': 'Ошибка валидации',
                     'ko': '검증 오류',
                     'fr': 'Erreur de validation'
                 },
                 'file_too_large_title': {
                     'zh': '文件过大',
                     'ja': 'ファイルが大きすぎます',
                     'en': 'File Too Large',
                     'ru': 'Файл слишком большой',
                     'ko': '파일이 너무 큽니다',
                     'fr': 'Fichier trop volumineux'
                 },
        'draft_saved': {
            'zh': '草稿已保存',
            'ja': '草稿が保存されました',
            'en': 'Draft saved',
            'ru': 'Черновик сохранен',
            'ko': '초안이 저장되었습니다',
            'fr': 'Brouillon sauvegardé'
        },
                                'translation_rejected': {
                            'zh': '翻译已拒绝',
                            'ja': '翻訳が拒否されました',
                            'en': 'Translation rejected',
                            'ru': 'Перевод отклонен',
                            'ko': '번역이 거부되었습니다',
                            'fr': 'Traduction rejetée'
                        },
                        'admin_request_approved': {
            'zh': '您的管理员申请已获得批准',
            'ja': '管理者申請が承認されました',
            'en': f'Congratulations! Your admin application has been approved. You now have admin privileges.',
            'ru': f'Поздравляем! Ваша заявка на администратора была одобрена. Теперь у вас есть права администратора.',
            'ko': f'축하합니다! 관리자 신청이 승인되었습니다. 이제 관리자 권한을 가지고 있습니다.',
            'fr': f'Félicitations ! Votre demande d\'administrateur a été approuvée. Vous avez maintenant les privilèges d\'administrateur.',
        },
                                'admin_request_rejected': {
            'zh': '您的管理员申请被拒绝了',
            'ja': '管理者申請が拒否されました',
            'en': f'Sorry, your admin application was rejected.',
            'ru': f'Извините, ваша заявка на администратора была отклонена.',
            'ko': f'죄송합니다. 관리자 신청이 거부되었습니다.',
            'fr': f'Désolé, votre demande d\'administrateur a été rejetée.',
        },
        'comment_added': {
            'zh': '评论添加成功',
            'ja': 'コメントが追加されました',
            'en': 'Comment added successfully',
            'ru': 'Комментарий успешно добавлен',
            'ko': '댓글이 성공적으로 추가되었습니다',
            'fr': 'Commentaire ajouté avec succès'
        },
        'comment_deleted': {
            'zh': '评论已删除',
            'ja': 'コメントが削除されました',
            'en': 'Comment deleted',
            'ru': 'Комментарий удален',
            'ko': '댓글이 삭제되었습니다',
            'fr': 'Commentaire supprimé'
        },
        'no_permission_delete_comment': {
            'zh': '您没有权限删除此评论',
            'ja': 'このコメントを削除する権限がありません',
            'en': 'You do not have permission to delete this comment',
            'ru': 'У вас нет разрешения на удаление этого комментария',
            'ko': '이 댓글을 삭제할 권한이 없습니다',
            'fr': 'Vous n\'avez pas la permission de supprimer ce commentaire'
        },
        'admin_comment_deleted': {
            'zh': '管理员删除了您的评论',
            'ja': '管理者があなたのコメントを削除しました',
            'en': f'Admin {kwargs.get("admin_name", "")} has deleted your comment in the work "{kwargs.get("work_title", "")}".',
            'ru': f'Администратор {kwargs.get("admin_name", "")} удалил ваш комментарий в работе "{kwargs.get("work_title", "")}".',
            'ko': f'관리자 {kwargs.get("admin_name", "")}가 작품 "{kwargs.get("work_title", "")}"에서 귀하의 댓글을 삭제했습니다.',
            'fr': f'L\'administrateur {kwargs.get("admin_name", "")} a supprimé votre commentaire dans l\'œuvre "{kwargs.get("work_title", "")}".',
        },
        'cannot_correct_own_translation': {
            'zh': '您无法对自己的翻译进行校正',
            'ja': '自分自身の翻訳を校正することはできません',
            'en': 'You cannot correct your own translation',
            'ru': 'Вы не можете исправлять свой собственный перевод',
            'ko': '자신의 번역을 교정할 수 없습니다',
            'fr': 'Vous ne pouvez pas corriger votre propre traduction'
        },
        'received_like': {
            'zh': '您收到了一个点赞',
            'ja': 'いいねをもらいました',
            'en': 'You received a like',
            'ru': 'Вы получили лайк',
            'ko': '좋아요를 받았습니다',
            'fr': 'Vous avez reçu un j\'aime'
        },
        # 邮件通知相关
        'email_new_message_subject': {
            'zh': '您有一条新消息',
            'ja': '新しいメッセージがあります',
            'en': 'You have a new message',
            'ru': 'У вас новое сообщение',
            'ko': '새 메시지가 있습니다',
            'fr': 'Vous avez un nouveau message'
        },
        'email_greeting': {
            'zh': '您好，{username}',
            'ja': '{username} 様',
            'en': 'Hello, {username}',
            'ru': 'Здравствуйте, {username}',
            'ko': '안녕하세요, {username}님',
            'fr': 'Bonjour, {username}'
        },
        'email_from': {
            'zh': '来自',
            'ja': '送信者',
            'en': 'From',
            'ru': 'От',
            'ko': '보낸 사람',
            'fr': 'De'
        },
        'email_time': {
            'zh': '时间',
            'ja': '時間',
            'en': 'Time',
            'ru': 'Время',
            'ko': '시간',
            'fr': 'Heure'
        },
        'email_footer': {
            'zh': '请登录平台查看详情。',
            'ja': '詳細はプラットフォームにログインしてご確認ください。',
            'en': 'Please log in to the platform to view details.',
            'ru': 'Пожалуйста, войдите на платформу, чтобы посмотреть подробности.',
            'ko': '자세한 내용은 플랫폼에 로그인하여 확인하세요.',
            'fr': 'Veuillez vous connecter à la plateforme pour voir les détails.'
        },
        'email_notifications_label': {
            'zh': '邮件通知（收到消息时发送到邮箱）',
            'ja': 'メール通知（メッセージ受信時にメール送信）',
            'en': 'Email notifications (send to inbox when you receive messages)',
            'ru': 'Уведомления по почте (отправлять письмо при получении сообщений)',
            'ko': '이메일 알림 (메시지 수신 시 메일 발송)',
            'fr': 'Notifications par e-mail (envoyer un mail lors de la réception de messages)'
        },
        'work': {
            'zh': '作品',
            'ja': '作品',
            'en': 'work',
            'ru': 'работа',
            'ko': '작품',
            'fr': 'œuvre'
        },
        'translation': {
            'zh': '翻译',
            'ja': '翻訳',
            'en': 'translation',
            'ru': 'перевод',
            'ko': '번역',
            'fr': 'traduction'
        },
        'comment': {
            'zh': '评论',
            'ja': 'コメント',
            'en': 'comment',
            'ru': 'комментарий',
            'ko': '댓글',
            'fr': 'commentaire'
        },
        'correction': {
            'zh': '校正',
            'ja': '校正',
            'en': 'correction',
            'ru': 'исправление',
            'ko': '교정',
            'fr': 'correction'
        },
        'like_milestone_10': {
            'zh': '恭喜！您获得了10个点赞里程碑',
            'ja': 'おめでとうございます！10いいねのマイルストーンに到達しました',
            'en': 'Congratulations! You reached the 10 likes milestone',
            'ru': 'Поздравляем! Вы достигли рубежа в 10 лайков',
            'ko': '축하합니다! 좋아요 10개 이정표를 달성했습니다',
            'fr': 'Félicitations! Vous avez atteint le jalon de 10 j\'aime'

        },
        'like_milestone_100': {
            'zh': '恭喜！您获得了100个点赞里程碑',
            'ja': 'おめでとうございます！100いいねのマイルストーンに到達しました',
            'en': 'Congratulations! You reached the 100 likes milestone',
            'ru': 'Поздравляем! Вы достигли рубежа в 100 лайков',
            'ko': '축하합니다! 좋아요 100개 이정표를 달성했습니다',
            'fr': 'Félicitations! Vous avez atteint le jalon de 100 j\'aime'

        },
        'like_milestone_1000': {
            'zh': '恭喜！您获得了1000个点赞里程碑',
            'ja': 'おめでとうございます！1000いいねのマイルストーンに到達しました',
            'en': 'Congratulations! You reached the 1000 likes milestone',
            'ru': 'Поздравляем! Вы достигли рубежа в 1000 лайков',
            'ko': '축하합니다! 좋아요 1000개 이정표를 달성했습니다',
            'fr': 'Félicitations! Vous avez atteint le jalon de 1000 j\'aime'

        },
        # Upload page messages
        'upload_work': {
            'zh': '上传作品',
            'ja': '作品をアップロード',
            'en': 'Upload Work',
            'ru': 'Загрузить работу',
            'ko': '작품 업로드',
            'fr': 'Télécharger l\'œuvre'
        },
        'title': {
            'zh': '标题', 'ja': '作品タイトル', 'en': 'Title', 'ru': 'Название', 'ko': '제목', 'fr': 'Titre'
        },
        'enter_work_title': {
            'zh': '请输入作品标题', 'ja': '作品のタイトルを入力', 'en': 'Enter work title', 'ru': 'Введите название работы', 'ko': '작품 제목을 입력하세요', 'fr': 'Entrez le titre de l\'œuvre'
        },
        'category': {
            'zh': '分类', 'ja': 'カテゴリー', 'en': 'Category', 'ru': 'Категория', 'ko': '카테고리', 'fr': 'Catégorie'
        },
        'select_category': {
            'zh': '选择分类', 'ja': 'カテゴリーを選択', 'en': 'Select category', 'ru': 'Выберите категорию', 'ko': '카테고리 선택', 'fr': 'Sélectionner une catégorie'
        },
        'original_language': {
            'zh': '原文语言', 'ja': '原文言語', 'en': 'Original Language', 'ru': 'Исходный язык', 'ko': '원본 언어', 'fr': 'Langue originale'
        },
        'target_language': {
            'zh': '目标语言', 'ja': '目標言語', 'en': 'Target Language', 'ru': 'Целевой язык', 'ko': '목표 언어', 'fr': 'Langue cible'
        },
        'content': {
            'zh': '正文内容', 'ja': '本文内容', 'en': 'Content', 'ru': 'Содержание', 'ko': '내용', 'fr': 'Contenu'
        },
        'enter_work_content': {
            'zh': '请输入作品内容...', 'ja': '作品の内容を入力してください...', 'en': 'Enter work content...', 'ru': 'Введите содержание работы...', 'ko': '작품 내용을 입력하세요...', 'fr': 'Entrez le contenu de l\'œuvre...'
        },
        'content_help': {
            'zh': '请提供清晰、结构化的内容，以便翻译者更好地理解', 'ja': '翻訳者が理解しやすいように、明確で構造化された内容を提供してください', 'en': 'Please provide clear, structured content for better translator understanding', 'ru': 'Предоставьте четкое, структурированное содержание для лучшего понимания переводчиком', 'ko': '번역자가 이해하기 쉽도록 명확하고 구조화된 내용을 제공해 주세요', 'fr': 'Veuillez fournir un contenu clair et structuré pour une meilleure compréhension du traducteur'
        },
        'multimedia_files': {
            'zh': '上传多媒体文件（图片、音频、视频，选填）', 'ja': 'マルチメディアファイルをアップロード（画像、音声、動画、オプション）', 'en': 'Upload multimedia files (images, audio, video, optional)', 'ru': 'Загрузить мультимедийные файлы (изображения, аудио, видео, опционально)', 'ko': '멀티미디어 파일 업로드 (이미지, 오디오, 비디오, 선택사항)', 'fr': 'Télécharger des fichiers multimédias (images, audio, vidéo, optionnel)'
        },
        'supported_formats': {
            'zh': '支持格式：JPG, PNG, GIF, MP3, MP4, AVI 等（最大10MB）', 'ja': 'サポート形式：JPG, PNG, GIF, MP3, MP4, AVI など（最大10MB）', 'en': 'Supported formats: JPG, PNG, GIF, MP3, MP4, AVI, etc. (max 10MB)', 'ru': 'Поддерживаемые форматы: JPG, PNG, GIF, MP3, MP4, AVI и др. (макс. 10МБ)', 'ko': '지원 형식: JPG, PNG, GIF, MP3, MP4, AVI 등 (최대 10MB)', 'fr': 'Formats supportés: JPG, PNG, GIF, MP3, MP4, AVI, etc. (max 10MB)'
        },
        'translation_expectation': {
            'zh': '对翻译的期待（选填）', 'ja': '翻訳への期待（オプション）', 'en': 'Translation Expectations (Optional)', 'ru': 'Ожидания от перевода (опционально)', 'ko': '번역에 대한 기대 (선택사항)', 'fr': 'Attentes de traduction (optionnel)'
        },
        'translation_expectation_placeholder': {
            'zh': '如：希望译文更有文学性、希望译者多与我沟通等', 'ja': '例：より文学的な翻訳を希望、翻訳者とのコミュニケーションを希望など', 'en': 'e.g., Hope for more literary translation, hope to communicate with translator, etc.', 'ru': 'например: Надеюсь на более литературный перевод, надеюсь на общение с переводчиком и т.д.', 'ko': '예: 더 문학적인 번역을 희망, 번역자와의 소통을 희망 등', 'fr': 'ex: Espère une traduction plus littéraire, espère communiquer avec le traducteur, etc.'
        },
        'translation_expectation_help': {
            'zh': '如果有想告诉翻译者的期待或希望，请在此填写', 'ja': '翻訳者に伝えたい期待や希望があれば記入してください', 'en': 'Please fill in any expectations or hopes you want to tell the translator', 'ru': 'Пожалуйста, заполните любые ожидания или надежды, которые вы хотите сообщить переводчику', 'ko': '번역자에게 전하고 싶은 기대나 희망이 있으면 기입해 주세요', 'fr': 'Veuillez remplir toutes les attentes ou espoirs que vous souhaitez dire au traducteur'
        },
        'translation_requirements': {
            'zh': '我希望翻译者能完成以下要求：', 'ja': '翻訳者に以下の要求を完成してもらいたい：', 'en': 'I want the translator to complete the following requirements:', 'ru': 'Я хочу, чтобы переводчик выполнил следующие требования:', 'ko': '번역자가 다음 요구사항을 완료하기를 원합니다:', 'fr': 'Je veux que le traducteur complète les exigences suivantes:'
        },
        'requirements_note': {
            'zh': '（翻译者必须同意该要求才能进行翻译）', 'ja': '（翻訳者はこの要求に同意する必要があります）', 'en': '(The translator must agree to this requirement to proceed)', 'ru': '(Переводчик должен согласиться с этим требованием для продолжения)', 'ko': '(번역자는 이 요구사항에 동의해야 진행할 수 있습니다)', 'fr': '(Le traducteur doit accepter cette exigence pour procéder)'
        },
        'requirements_placeholder': {
            'zh': '要求翻译者不要擅自进行传播、用于商业用途等', 'ja': '翻訳者に無断での配布、商業利用などを禁止するよう要求', 'en': 'Require translators not to distribute without permission or use for commercial purposes, etc.', 'ru': 'Требовать от переводчиков не распространять без разрешения или использовать в коммерческих целях и т.д.', 'ko': '번역자에게 무단 배포, 상업적 이용 등을 금지하도록 요구', 'fr': 'Exiger des traducteurs de ne pas distribuer sans autorisation ou utiliser à des fins commerciales, etc.'
        },
        'contact_before_translate': {
            'zh': '我需要翻译者在翻译前提前私信我', 'ja': '翻訳前に翻訳者に連絡してもらいたい', 'en': 'I need the translator to contact me before translation', 'ru': 'Мне нужно, чтобы переводчик связался со мной перед переводом', 'ko': '번역 전에 번역자가 저에게 연락하기를 원합니다', 'fr': 'J\'ai besoin que le traducteur me contacte avant la traduction'
        },
        'contact_before_translate_help': {
            'zh': '选择此选项，在私信沟通后，请在个人界面设置信赖的翻译者，对方才能翻译您的作品', 'ja': 'このオプションを選択すると、メッセージでのコミュニケーション後、個人画面で信頼する翻訳者を設定してください。その後、相手があなたの作品を翻訳できます', 'en': 'If you select this option, after communication via messages, please set trusted translators in your personal interface. Then the other party can translate your work', 'ru': 'Если вы выберете эту опцию, после общения через сообщения, пожалуйста, установите доверенных переводчиков в вашем личном интерфейсе. Затем другая сторона сможет перевести вашу работу', 'ko': '이 옵션을 선택하면 메시지를 통한 소통 후 개인 화면에서 신뢰하는 번역자를 설정해 주세요. 그 후 상대방이 당신의 작품을 번역할 수 있습니다', 'fr': 'Si vous sélectionnez cette option, après communication via messages, veuillez définir des traducteurs de confiance dans votre interface personnelle. Ensuite, l\'autre partie pourra traduire votre travail'
        },
        'allow_multiple_translators': {
            'zh': '允许多人翻译', 'ja': '複数の翻訳者による翻訳を許可', 'en': 'Allow multiple translators', 'ru': 'Разрешить нескольких переводчиков', 'ko': '여러 번역자의 번역 허용', 'fr': 'Autoriser plusieurs traducteurs'
        },
        'allow_multiple_translators_help': {
            'zh': '选择此选项，允许多个翻译者同时翻译这个作品。每个翻译者的翻译将独立显示', 'ja': 'このオプションを選択すると、複数の翻訳者が同時にこの作品を翻訳できます。各翻訳者の翻訳は独立して表示されます', 'en': 'If you select this option, multiple translators can translate this work simultaneously. Each translator\'s translation will be displayed independently', 'ru': 'Если вы выберете эту опцию, несколько переводчиков смогут одновременно переводить эту работу. Перевод каждого переводчика будет отображаться независимо', 'ko': '이 옵션을 선택하면 여러 번역자가 동시에 이 작품을 번역할 수 있습니다. 각 번역자의 번역은 독립적으로 표시됩니다', 'fr': 'Si vous sélectionnez cette option, plusieurs traducteurs peuvent traduire ce travail simultanément. La traduction de chaque traducteur sera affichée indépendamment'
        },
        'cancel': {
            'zh': '取消', 'ja': 'キャンセル', 'en': 'Cancel', 'ru': 'Отмена', 'ko': '취소', 'fr': 'Annuler'
        },
        'upload_guide': {
            'zh': '上传指南', 'ja': 'アップロードガイド', 'en': 'Upload Guide', 'ru': 'Руководство по загрузке', 'ko': '업로드 가이드', 'fr': 'Guide de téléchargement'
        },
        'good_examples': {
            'zh': '好的例子', 'ja': '良い例', 'en': 'Good Examples', 'ru': 'Хорошие примеры', 'ko': '좋은 예시', 'fr': 'Bons exemples'
        },
        'clear_structured_content': {
            'zh': '清晰、结构化的内容', 'ja': '明確で構造化された内容', 'en': 'Clear and structured content', 'ru': 'Четкое и структурированное содержание', 'ko': '명확하고 구조화된 내용', 'fr': 'Contenu clair et structuré'
        },
        'appropriate_category': {
            'zh': '选择合适的分类', 'ja': '適切なカテゴリー選択', 'en': 'Appropriate category selection', 'ru': 'Правильный выбор категории', 'ko': '적절한 카테고리 선택', 'fr': 'Sélection de catégorie appropriée'
        },
        'specific_requirements': {
            'zh': '具体的翻译要求', 'ja': '具体的な翻訳要求', 'en': 'Specific translation requirements', 'ru': 'Конкретные требования к переводу', 'ko': '구체적인 번역 요구사항', 'fr': 'Exigences de traduction spécifiques'
        },
        'should_avoid': {
            'zh': '应该避免', 'ja': '避けるべき', 'en': 'Should Avoid', 'ru': 'Следует избегать', 'ko': '피해야 할 것', 'fr': 'À éviter'
        },
        'vague_content': {
            'zh': '模糊、不明确的内容', 'ja': '曖昧で不明確な内容', 'en': 'Vague and unclear content', 'ru': 'Расплывчатое и неясное содержание', 'ko': '모호하고 불명확한 내용', 'fr': 'Contenu vague et peu clair'
        },
        'copyright_infringing': {
            'zh': '侵犯版权的内容', 'ja': '著作権侵害の内容', 'en': 'Copyright infringing content', 'ru': 'Контент, нарушающий авторские права', 'ko': '저작권 침해 내용', 'fr': 'Contenu violant les droits d\'auteur'
        },
        'inappropriate_content': {
            'zh': '不当内容', 'ja': '不適切な内容', 'en': 'Inappropriate content', 'ru': 'Неприемлемый контент', 'ko': '부적절한 내용', 'fr': 'Contenu inapproprié'
        },
        'file_too_large': {
            'zh': '文件大小过大，请选择10MB以下的文件。', 'ja': 'ファイルサイズが大きすぎます。10MB以下にしてください。', 'en': 'File size is too large. Please select a file under 10MB.', 'ru': 'Размер файла слишком большой. Пожалуйста, выберите файл менее 10МБ.', 'ko': '파일 크기가 너무 큽니다. 10MB 이하의 파일을 선택해 주세요.', 'fr': 'La taille du fichier est trop grande. Veuillez sélectionner un fichier de moins de 10MB.'
        },
        'chinese': {
            'zh': '中文', 'ja': '中国語', 'en': 'Chinese', 'ru': 'Китайский', 'ko': '중국어', 'fr': 'Chinois'
        },
        'japanese': {
            'zh': '日文', 'ja': '日本語', 'en': 'Japanese', 'ru': 'Японский', 'ko': '일본어', 'fr': 'Japonais'
        }
    ,
        'register': {
            'zh': '注册',
            'ja': '新規登録',
            'en': 'Register',
            'ru': 'Регистрация',
            'ko': '등록',
            'fr': 'S\'inscrire',
        },
        'attention': {
            'zh': '注意',
            'ja': '注意',
            'en': 'Attention',
            'ru': 'Внимание',
            'ko': '주의',
            'fr': 'Attention',
        },
        'security_warning': {
            'zh': '目前该测试版本缺乏安全防护，请勿在其中输入重要信息！',
            'ja': '現在のテストバージョンはセキュリティ保護が不十分です。重要な情報を入力しないでください！',
            'en': 'The current test version lacks security protection. Please do not enter important information!',
            'ru': 'Текущая тестовая версия не имеет защиты. Пожалуйста, не вводите важную информацию!',
            'ko': '현재 테스트 버전은 보안 보호가 부족합니다. 중요한 정보를 입력하지 마세요!',
            'fr': 'La version de test actuelle manque de protection de sécurité. Veuillez ne pas entrer d\'informations importantes!',
        },
        'email': {
            'zh': '邮箱',
            'ja': 'メールアドレス',
            'en': 'Email',
            'ru': 'Электронная почта',
            'ko': '이메일',
            'fr': 'Email',
        },
        'enter_email': {
            'zh': '请输入邮箱',
            'ja': 'メールアドレスを入力',
            'en': 'Enter email',
            'ru': 'Введите email',
            'ko': '이메일 입력',
            'fr': 'Entrez l\'email',
        },
        'confirm_password': {
            'zh': '确认密码',
            'ja': 'パスワード確認',
            'en': 'Confirm Password',
            'ru': 'Подтвердите пароль',
            'ko': '비밀번호 확인',
            'fr': 'Confirmer le mot de passe',
        },
        're_enter_password': {
            'zh': '请再次输入密码',
            'ja': 'パスワードを再入力',
            'en': 'Re-enter password',
            'ru': 'Повторите пароль',
            'ko': '비밀번호를 다시 입력하세요',
            'fr': 'Retaper le mot de passe',
        },
        'password_mismatch': {
            'zh': '密码不匹配',
            'ja': 'パスワードが一致しません',
            'en': 'Passwords do not match',
            'ru': 'Пароли не совпадают',
            'ko': '비밀번호가 일치하지 않습니다',
            'fr': 'Les mots de passe ne correspondent pas',
        },
        'please_enter_username': {
            'zh': '请输入用户名',
            'ja': 'ユーザー名を入力してください',
            'en': 'Please enter username',
            'ru': 'Пожалуйста, введите имя пользователя',
            'ko': '사용자 이름을 입력해 주세요',
            'fr': 'Veuillez entrer le nom d\'utilisateur',
        },
        'please_enter_email': {
            'zh': '请输入邮箱',
            'ja': 'メールアドレスを入力してください',
            'en': 'Please enter email',
            'ru': 'Пожалуйста, введите email',
            'ko': '이메일을 입력해 주세요',
            'fr': 'Veuillez entrer l\'email',
        },
        'username_or_email': {
            'zh': '用户名或邮箱',
            'ja': 'ユーザー名またはメールアドレス',
            'en': 'Username or Email',
            'ru': 'Имя пользователя или Email',
            'ko': '사용자명 또는 이메일',
            'fr': 'Nom d\'utilisateur ou Email',
        },
        'enter_username_or_email': {
            'zh': '请输入用户名或邮箱',
            'ja': 'ユーザー名またはメールアドレスを入力',
            'en': 'Enter username or email',
            'ru': 'Введите имя пользователя или email',
            'ko': '사용자명 또는 이메일 입력',
            'fr': 'Entrez le nom d\'utilisateur ou l\'email',
        },
        'please_enter_username_or_email': {
            'zh': '请输入用户名或邮箱',
            'ja': 'ユーザー名またはメールアドレスを入力してください',
            'en': 'Please enter username or email',
            'ru': 'Пожалуйста, введите имя пользователя или email',
            'ko': '사용자명 또는 이메일을 입력해 주세요',
            'fr': 'Veuillez entrer le nom d\'utilisateur ou l\'email',
        },
        'please_enter_password': {
            'zh': '请输入密码',
            'ja': 'パスワードを入力してください',
            'en': 'Please enter password',
            'ru': 'Пожалуйста, введите пароль',
            'ko': '비밀번호를 입력해 주세요',
            'fr': 'Veuillez entrer le mot de passe',
        },
        'avatar': {
            'zh': '头像',
            'ja': 'アバター',
            'en': 'Avatar',
            'ru': 'Аватар',
            'ko': '아바타',
            'fr': 'Avatar',
        },
        'no_bio': {
            'zh': '暂无简介',
            'ja': '自己紹介なし',
            'en': 'No bio',
            'ru': 'Нет биографии',
            'ko': '소개 없음',
            'fr': 'Aucune bio',
        },
        'preferred_language': {
            'zh': '偏好语言',
            'ja': '偏好言語',
            'en': 'Preferred Language',
            'ru': 'Предпочитаемый язык',
            'ko': '선호 언어',
            'fr': 'Langue préférée',
        },
        'admin': {
            'zh': '管理员',
            'ja': '管理者',
            'en': 'Administrator',
            'ru': 'Администратор',
            'ko': '관리자',
            'fr': 'Administrateur',
        },
        'creator': {
            'zh': '创作者',
            'ja': '創作者',
            'en': 'Creator',
            'ru': 'Создатель',
            'ko': '창작자',
            'fr': 'Créateur',
        },
        'translator': {
            'zh': '翻译者',
            'ja': '翻訳者',
            'en': 'Translator',
            'ru': 'Переводчик',
            'ko': '번역가',
            'fr': 'Traducteur',
        },
        'reviewer': {
            'zh': '校正者',
            'ja': '校正者',
            'en': 'Reviewer',
            'ru': 'Рецензент',
            'ko': '검토자',
            'fr': 'Réviseur',
        },
        'registration_date': {
            'zh': '注册时间',
            'ja': '登録日',
            'en': 'Registration Date',
            'ru': 'Дата регистрации',
            'ko': '등록 날짜',
            'fr': 'Date d\'inscription',
        },
        'quick_actions': {
            'zh': '快速操作',
            'ja': 'クイックアクション',
            'en': 'Quick Actions',
            'ru': 'Быстрые действия',
            'ko': '빠른 작업',
            'fr': 'Actions rapides',
        },
        'edit_profile': {
            'zh': '编辑资料',
            'ja': 'プロフィール編集',
            'en': 'Edit Profile',
            'ru': 'Редактировать профиль',
            'ko': '프로필 편집',
            'fr': 'Modifier le profil',
        },
        'change_password': {
            'zh': '修改密码',
            'ja': 'パスワード変更',
            'en': 'Change Password',
            'ru': 'Изменить пароль',
            'ko': '비밀번호 변경',
            'fr': 'Changer le mot de passe',
        },
        'become_translator': {
            'zh': '通过测试，成为翻译者',
            'ja': 'テストに合格して翻訳者になる',
            'en': 'Pass test to become translator',
            'ru': 'Пройдите тест, чтобы стать переводчиком',
            'ko': '번역가가 되기 위해 테스트를 통과하세요',
            'fr': 'Passez le test pour devenir traducteur',
        },
        'become_reviewer': {
            'zh': '通过测试，成为校正者',
            'ja': 'テストに合格して校正者になる',
            'en': 'Pass test to become reviewer',
            'ru': 'Пройдите тест, чтобы стать рецензентом',
            'ko': '검토자가 되기 위해 테스트를 통과하세요',
            'fr': 'Passez le test pour devenir réviseur',
        },
        'my_friends': {
            'zh': '我的好友',
            'ja': '私の友達',
            'en': 'My Friends',
            'ru': 'Мои друзья',
            'ko': '내 친구들',
            'fr': 'Mes amis',
        },
        'search_by_username': {
            'zh': '通过用户名搜索...',
            'ja': 'ユーザー名で検索...',
            'en': 'Search by username...',
            'ru': 'Поиск по имени пользователя...',
            'ko': '사용자 이름으로 검색...',
            'fr': 'Rechercher par nom d\'utilisateur...',
        },
        'search_results': {
            'zh': '搜索结果',
            'ja': '検索結果',
            'en': 'Search Results',
            'ru': 'Результаты поиска',
            'ko': '검색 결과',
            'fr': 'Résultats de recherche',
        },
        'no_friends': {
            'zh': '暂无好友',
            'ja': '友達なし',
            'en': 'No friends',
            'ru': 'Нет друзей',
            'ko': '친구 없음',
            'fr': 'Aucun ami',
        },
        'you_have_no_friends': {
            'zh': '您还没有添加任何好友',
            'ja': 'まだ友達を追加していません',
            'en': 'You haven\'t added any friends yet',
            'ru': 'Вы еще не добавили друзей',
            'ko': '아직 친구를 추가하지 않았습니다',
            'fr': 'Vous n\'avez pas encore ajouté d\'amis',
        },
        'find_friends': {
            'zh': '寻找好友',
            'ja': '友達を探す',
            'en': 'Find Friends',
            'ru': 'Найти друзей',
            'ko': '친구 찾기',
            'fr': 'Trouver des amis',
        },
        'please_enter_user_id': {
            'zh': '请输入用户ID',
            'ja': 'ユーザーIDを入力してください',
            'en': 'Please enter user ID',
            'ru': 'Пожалуйста, введите ID пользователя',
            'ko': '사용자 ID를 입력해 주세요',
            'fr': 'Veuillez entrer l\'ID utilisateur',
        },
        'invalid_user_id': {
            'zh': '无效的用户ID',
            'ja': '無効なユーザーID',
            'en': 'Invalid user ID',
            'ru': 'Недействительный ID пользователя',
            'ko': '잘못된 사용자 ID',
            'fr': 'ID utilisateur invalide',
        },
        'user_not_found': {
            'zh': '用户不存在',
            'ja': 'ユーザーが見つかりません',
            'en': 'User not found',
            'ru': 'Пользователь не найден',
            'ko': '사용자를 찾을 수 없습니다',
            'fr': 'Utilisateur introuvable',
        },
        'cannot_add_yourself': {
            'zh': '不能添加自己为好友',
            'ja': '自分を友達として追加することはできません',
            'en': 'Cannot add yourself as friend',
            'ru': 'Нельзя добавить себя в друзья',
            'ko': '자신을 친구로 추가할 수 없습니다',
            'fr': 'Impossible de s\'ajouter soi-même comme ami',
        },
        'search_and_add_friend': {
            'zh': '搜索并添加好友',
            'ja': '友達を検索して追加',
            'en': 'Search and Add Friend',
            'ru': 'Поиск и добавление друга',
            'ko': '친구 검색 및 추가',
            'fr': 'Rechercher et ajouter un ami',
        },
        'search_by_username_or_id': {
            'zh': '输入用户名或用户ID...',
            'ja': 'ユーザー名またはユーザーIDを入力...',
            'en': 'Enter username or user ID...',
            'ru': 'Введите имя пользователя или ID...',
            'ko': '사용자명 또는 사용자 ID 입력...',
            'fr': 'Entrez le nom d\'utilisateur ou l\'ID...',
        },

        'pleaseEnterUsernameOrId': {
            'zh': '请输入用户名或用户ID',
            'ja': 'ユーザー名またはユーザーIDを入力してください',
            'en': 'Please enter username or user ID',
            'ru': 'Пожалуйста, введите имя пользователя или ID',
            'ko': '사용자명 또는 사용자 ID를 입력해 주세요',
            'fr': 'Veuillez entrer le nom d\'utilisateur ou l\'ID',
        },
        'searching': {
            'zh': '搜索中...',
            'ja': '検索中...',
            'en': 'Searching...',
            'ru': 'Поиск...',
            'ko': '검색 중...',
            'fr': 'Recherche...',
        },
        'multipleUsersFound': {
            'zh': '找到多个用户，请从搜索结果中选择',
            'ja': '複数のユーザーが見つかりました。検索結果から選択してください',
            'en': 'Multiple users found, please select from search results',
            'ru': 'Найдено несколько пользователей, выберите из результатов поиска',
            'ko': '여러 사용자가 발견되었습니다. 검색 결과에서 선택하세요',
            'fr': 'Plusieurs utilisateurs trouvés, veuillez sélectionner dans les résultats',
        },
        'info': {
            'zh': '提示',
            'ja': 'ヒント',
            'en': 'Info',
            'ru': 'Информация',
            'ko': '정보',
            'fr': 'Info',
        },
        'trusted_translators': {
            'zh': '信赖翻译者',
            'ja': '信頼翻訳者',
            'en': 'Trusted Translators',
            'ru': 'Доверенные переводчики',
            'ko': '신뢰할 수 있는 번역가',
            'fr': 'Traducteurs de confiance',
        },
        'my_trusted_translators': {
            'zh': '我信赖的翻译者',
            'ja': '私が信頼する翻訳者',
            'en': 'My Trusted Translators',
            'ru': 'Мои доверенные переводчики',
            'ko': '내가 신뢰하는 번역가',
            'fr': 'Mes traducteurs de confiance',
        },
        'no_trusted_translators': {
            'zh': '暂无信赖的翻译者',
            'ja': '信頼する翻訳者なし',
            'en': 'No trusted translators',
            'ru': 'Нет доверенных переводчиков',
            'ko': '신뢰할 수 있는 번역가 없음',
            'fr': 'Aucun traducteur de confiance',
        },
        'you_have_no_trusted_translators': {
            'zh': '您还没有信赖任何翻译者',
            'ja': 'まだ信頼する翻訳者はいません',
            'en': 'You haven\'t trusted any translators yet',
            'ru': 'Вы еще не доверяете ни одному переводчику',
            'ko': '아직 신뢰하는 번역가가 없습니다',
            'fr': 'Vous n\'avez encore confiance à aucun traducteur',
        },
        'find_translators': {
            'zh': '寻找翻译者',
            'ja': '翻訳者を探す',
            'en': 'Find Translators',
            'ru': 'Найти переводчиков',
            'ko': '번역가 찾기',
            'fr': 'Trouver des traducteurs',
        },
        'creators_who_trust_me': {
            'zh': '信赖我的创作者',
            'ja': '私を信頼するクリエイター',
            'en': 'Creators Who Trust Me',
            'ru': 'Создатели, которые доверяют мне',
            'ko': '나를 신뢰하는 창작자',
            'fr': 'Créateurs qui me font confiance',
        },
        'no_creators_trust_me': {
            'zh': '暂无信赖我的创作者',
            'ja': '私を信頼するクリエイターなし',
            'en': 'No creators trust me',
            'ru': 'Нет создателей, которые доверяют мне',
            'ko': '나를 신뢰하는 창작자 없음',
            'fr': 'Aucun créateur ne me fait confiance',
        },
        'no_creators_trust_you': {
            'zh': '还没有创作者信赖您',
            'ja': 'まだあなたを信頼するクリエイターはいません',
            'en': 'No creators trust you yet',
            'ru': 'Пока нет создателей, которые доверяют вам',
            'ko': '아직 당신을 신뢰하는 창작자가 없습니다',
            'fr': 'Aucun créateur ne vous fait encore confiance',
        },
        'keep_providing_quality_service': {
            'zh': '继续提供优质的翻译服务，会有更多创作者信赖您！',
            'ja': '質の高い翻訳サービスを提供し続ければ、より多くのクリエイターがあなたを信頼するようになります！',
            'en': 'Keep providing quality translation services, and more creators will trust you!',
            'ru': 'Продолжайте предоставлять качественные услуги перевода, и больше создателей будут доверять вам!',
            'ko': '양질의 번역 서비스를 계속 제공하면 더 많은 창작자가 당신을 신뢰할 것입니다!',
            'fr': 'Continuez à fournir des services de traduction de qualité, et plus de créateurs vous feront confiance !',
        },
        'system_notifications': {
            'zh': '系统通知',
            'ja': 'システム通知',
            'en': 'System Notifications',
            'ru': 'Системные уведомления',
            'ko': '시스템 알림',
            'fr': 'Notifications système',
        },
        'mark_as_read': {
            'zh': '标记为已读',
            'ja': '既読にする',
            'en': 'Mark as Read',
            'ru': 'Отметить как прочитанное',
            'ko': '읽음으로 표시',
            'fr': 'Marquer comme lu',
        },
        'friend_requests': {
            'zh': '好友请求',
            'ja': '友達リクエスト',
            'en': 'Friend Requests',
            'ru': 'Запросы в друзья',
            'ko': '친구 요청',
            'fr': 'Demandes d\'ami',
        },
        'requests_to_add_friend': {
            'zh': '请求添加您为好友',
            'ja': 'があなたを友達に追加しようとしています',
            'en': 'requests to add you as friend',
            'ru': 'запрашивает добавить вас в друзья',
            'ko': '가 당신을 친구로 추가하려고 요청했습니다',
            'fr': 'demande à vous ajouter comme ami',
        },
        'agree': {
            'zh': '同意',
            'ja': '同意',
            'en': 'Agree',
            'ru': 'Согласиться',
            'ko': '동의',
            'fr': 'Accepter',
        },
        'security_warning': {
            'zh': '目前该测试版本缺乏安全防护，请勿在其中输入重要信息！',
            'ja': '現在のテストバージョンはセキュリティ保護が不十分です。重要な情報を入力しないでください！',
            'en': 'The current test version lacks security protection. Please do not enter important information!',
            'ru': 'Текущая тестовая версия не имеет защиты. Пожалуйста, не вводите важную информацию!',
            'ko': '현재 테스트 버전은 보안 보호가 부족합니다. 중요한 정보를 입력하지 마세요!',
            'fr': 'La version de test actuelle manque de protection de sécurité. Veuillez ne pas entrer d\'informations importantes!',
        },
        'email': {
            'zh': '邮箱',
            'ja': 'メールアドレス',
            'en': 'Email',
            'ru': 'Электронная почта',
            'ko': '이메일',
            'fr': 'Email',
        },
        'enter_email': {
            'zh': '请输入邮箱',
            'ja': 'メールアドレスを入力',
            'en': 'Enter email',
            'ru': 'Введите email',
            'ko': '이메일 입력',
            'fr': 'Entrez l\'email',
        },
        'confirm_password': {
            'zh': '确认密码',
            'ja': 'パスワード確認',
            'en': 'Confirm Password',
            'ru': 'Подтвердите пароль',
            'ko': '비밀번호 확인',
            'fr': 'Confirmer le mot de passe',
        },
        're_enter_password': {
            'zh': '请再次输入密码',
            'ja': 'パスワードを再入力',
            'en': 'Re-enter password',
            'ru': 'Повторите пароль',
            'ko': '비밀번호를 다시 입력하세요',
            'fr': 'Retaper le mot de passe',
        },
        'password_mismatch': {
            'zh': '密码不匹配',
            'ja': 'パスワードが一致しません',
            'en': 'Passwords do not match',
            'ru': 'Пароли не совпадают',
            'ko': '비밀번호가 일치하지 않습니다',
            'fr': 'Les mots de passe ne correspondent pas',
        },
        'please_enter_username': {
            'zh': '请输入用户名',
            'ja': 'ユーザー名を入力してください',
            'en': 'Please enter username',
            'ru': 'Пожалуйста, введите имя пользователя',
            'ko': '사용자 이름을 입력해 주세요',
            'fr': 'Veuillez entrer le nom d\'utilisateur',
        },
        'please_enter_email': {
            'zh': '请输入邮箱',
            'ja': 'メールアドレスを入力してください',
            'en': 'Please enter email',
            'ru': 'Пожалуйста, введите email',
            'ko': '이메일을 입력해 주세요',
            'fr': 'Veuillez entrer l\'email',
        },
        'please_enter_password': {
            'zh': '请输入密码',
            'ja': 'パスワードを入力してください',
            'en': 'Please enter password',
            'ru': 'Пожалуйста, введите пароль',
            'ko': '비밀번호를 입력해 주세요',
            'fr': 'Veuillez entrer le mot de passe',
        },
        'avatar': {
            'zh': '头像',
            'ja': 'アバター',
            'en': 'Avatar',
            'ru': 'Аватар',
            'ko': '아바타',
            'fr': 'Avatar',
        },
        'no_bio': {
            'zh': '暂无简介',
            'ja': '自己紹介なし',
            'en': 'No bio',
            'ru': 'Нет биографии',
            'ko': '소개 없음',
            'fr': 'Aucune bio',
        },
        'preferred_language': {
            'zh': '偏好语言',
            'ja': '好みの言語',
            'en': 'Preferred Language',
            'ru': 'Предпочитаемый язык',
            'ko': '선호 언어',
            'fr': 'Langue préférée',
        },
        'admin': {
            'zh': '管理员',
            'ja': '管理者',
            'en': 'Administrator',
            'ru': 'Администратор',
            'ko': '관리자',
            'fr': 'Administrateur',
        },
        'creator': {
            'zh': '创作者',
            'ja': '創作者',
            'en': 'Creator',
            'ru': 'Создатель',
            'ko': '창작자',
            'fr': 'Créateur',
        },
        'translator': {
            'zh': '翻译者',
            'ja': '翻訳者',
            'en': 'Translator',
            'ru': 'Переводчик',
            'ko': '번역가',
            'fr': 'Traducteur',
        },
        'reviewer': {
            'zh': '校正者',
            'ja': '校正者',
            'en': 'Reviewer',
            'ru': 'Рецензент',
            'ko': '검토자',
            'fr': 'Réviseur',
        },
        'registration_date': {
            'zh': '注册时间',
            'ja': '登録日',
            'en': 'Registration Date',
            'ru': 'Дата регистрации',
            'ko': '등록 날짜',
            'fr': 'Date d\'inscription',
        },
        'quick_actions': {
            'zh': '快速操作',
            'ja': 'クイックアクション',
            'en': 'Quick Actions',
            'ru': 'Быстрые действия',
            'ko': '빠른 작업',
            'fr': 'Actions rapides',
        },
        'edit_profile': {
            'zh': '编辑资料',
            'ja': 'プロフィール編集',
            'en': 'Edit Profile',
            'ru': 'Редактировать профиль',
            'ko': '프로필 편집',
            'fr': 'Modifier le profil',
        },
        'change_password': {
            'zh': '修改密码',
            'ja': 'パスワード変更',
            'en': 'Change Password',
            'ru': 'Изменить пароль',
            'ko': '비밀번호 변경',
            'fr': 'Changer le mot de passe',
        },
        'become_translator': {
            'zh': '通过测试，成为翻译者',
            'ja': 'テストに合格して翻訳者になる',
            'en': 'Pass test to become translator',
            'ru': 'Пройдите тест, чтобы стать переводчиком',
            'ko': '번역가가 되기 위해 테스트를 통과하세요',
            'fr': 'Passez le test pour devenir traducteur',
        },
        'become_reviewer': {
            'zh': '通过测试，成为校正者',
            'ja': 'テストに合格して校正者になる',
            'en': 'Pass test to become reviewer',
            'ru': 'Пройдите тест, чтобы стать рецензентом',
            'ko': '검토자가 되기 위해 테스트를 통과하세요',
            'fr': 'Passez le test pour devenir réviseur',
        },
        'my_friends': {
            'zh': '我的好友',
            'ja': '私の友達',
            'en': 'My Friends',
            'ru': 'Мои друзья',
            'ko': '내 친구들',
            'fr': 'Mes amis',
        },
        'search_by_username': {
            'zh': '通过用户名搜索...',
            'ja': 'ユーザー名で検索...',
            'en': 'Search by username...',
            'ru': 'Поиск по имени пользователя...',
            'ko': '사용자 이름으로 검색...',
            'fr': 'Rechercher par nom d\'utilisateur...',
        },
        'search_results': {
            'zh': '搜索结果',
            'ja': '検索結果',
            'en': 'Search Results',
            'ru': 'Результаты поиска',
            'ko': '검색 결과',
            'fr': 'Résultats de recherche',
        },
        'no_friends': {
            'zh': '暂无好友',
            'ja': '友達なし',
            'en': 'No friends',
            'ru': 'Нет друзей',
            'ko': '친구 없음',
            'fr': 'Aucun ami',
        },
        'you_have_no_friends': {
            'zh': '您还没有添加任何好友',
            'ja': 'まだ友達を追加していません',
            'en': 'You haven\'t added any friends yet',
            'ru': 'Вы еще не добавили друзей',
            'ko': '아직 친구를 추가하지 않았습니다',
            'fr': 'Vous n\'avez pas encore ajouté d\'amis',
        },
        'find_friends': {
            'zh': '寻找好友',
            'ja': '友達を探す',
            'en': 'Find Friends',
            'ru': 'Найти друзей',
            'ko': '친구 찾기',
            'fr': 'Trouver des amis',
        },
        'trusted_translators': {
            'zh': '信赖翻译者',
            'ja': '信頼翻訳者',
            'en': 'Trusted Translators',
            'ru': 'Доверенные переводчики',
            'ko': '신뢰할 수 있는 번역가',
            'fr': 'Traducteurs de confiance',
        },
        'my_trusted_translators': {
            'zh': '我信赖的翻译者',
            'ja': '私が信頼する翻訳者',
            'en': 'My Trusted Translators',
            'ru': 'Мои доверенные переводчики',
            'ko': '내가 신뢰하는 번역가',
            'fr': 'Mes traducteurs de confiance',
        },
        'no_trusted_translators': {
            'zh': '暂无信赖的翻译者',
            'ja': '信頼する翻訳者なし',
            'en': 'No trusted translators',
            'ru': 'Нет доверенных переводчиков',
            'ko': '신뢰할 수 있는 번역가 없음',
            'fr': 'Aucun traducteur de confiance',
        },
        'you_have_no_trusted_translators': {
            'zh': '您还没有信赖任何翻译者',
            'ja': 'まだ信頼する翻訳者はいません',
            'en': 'You haven\'t trusted any translators yet',
            'ru': 'Вы еще не доверяете ни одному переводчику',
            'ko': '아직 신뢰하는 번역가가 없습니다',
            'fr': 'Vous n\'avez encore confiance à aucun traducteur',
        },
        'find_translators': {
            'zh': '寻找翻译者',
            'ja': '翻訳者を探す',
            'en': 'Find Translators',
            'ru': 'Найти переводчиков',
            'ko': '번역가 찾기',
            'fr': 'Trouver des traducteurs',
        },
        'creators_who_trust_me': {
            'zh': '信赖我的创作者',
            'ja': '私を信頼するクリエイター',
            'en': 'Creators Who Trust Me',
            'ru': 'Создатели, которые доверяют мне',
            'ko': '나를 신뢰하는 창작자',
            'fr': 'Créateurs qui me font confiance',
        },
        'no_creators_trust_me': {
            'zh': '暂无信赖我的创作者',
            'ja': '私を信頼するクリエイターなし',
            'en': 'No creators trust me',
            'ru': 'Нет создателей, которые доверяют мне',
            'ko': '나를 신뢰하는 창작자 없음',
            'fr': 'Aucun créateur ne me fait confiance',
        },
        'no_creators_trust_you': {
            'zh': '还没有创作者信赖您',
            'ja': 'まだあなたを信頼するクリエイターはいません',
            'en': 'No creators trust you yet',
            'ru': 'Пока нет создателей, которые доверяют вам',
            'ko': '아직 당신을 신뢰하는 창작자가 없습니다',
            'fr': 'Aucun créateur ne vous fait encore confiance',
        },
        'system_notifications': {
            'zh': '系统通知',
            'ja': 'システム通知',
            'en': 'System Notifications',
            'ru': 'Системные уведомления',
            'ko': '시스템 알림',
            'fr': 'Notifications système',
        },
        'mark_as_read': {
            'zh': '标记为已读',
            'ja': '既読にする',
            'en': 'Mark as Read',
            'ru': 'Отметить как прочитанное',
            'ko': '읽음으로 표시',
            'fr': 'Marquer comme lu',
        },
        'friend_requests': {
            'zh': '好友请求',
            'ja': '友達リクエスト',
            'en': 'Friend Requests',
            'ru': 'Запросы в друзья',
            'ko': '친구 요청',
            'fr': 'Demandes d\'ami',
        },
        'requests_to_add_friend': {
            'zh': '请求添加您为好友',
            'ja': 'があなたを友達に追加しようとしています',
            'en': 'requests to add you as friend',
            'ru': 'запрашивает добавить вас в друзья',
            'ko': '가 당신을 친구로 추가하려고 요청했습니다',
            'fr': 'demande à vous ajouter comme ami',
        },
        'agree': {
            'zh': '同意',
            'ja': '同意',
            'en': 'Agree',
            'ru': 'Согласиться',
            'ko': '동의',
            'fr': 'Accepter',
        },
        'reject': {
            'zh': '拒绝',
            'ja': '拒否',
            'en': 'Reject',
            'ru': 'Отклонить',
            'ko': '거부',
            'fr': 'Rejeter',
        },
        # 翻译确认界面消息
        'confirm_translate_title': {
            'zh': '翻译请求确认',
            'ja': '翻訳リクエスト確認',
            'en': 'Translation Request Confirmation',
            'ru': 'Подтверждение запроса на перевод',
            'ko': '번역 요청 확인',
            'fr': 'Confirmation de demande de traduction'
        },
        'please_reconfirm_requirements': {
            'zh': '请再次确认翻译要求。',
            'ja': '翻訳要求を再確認してください。',
            'en': 'Please reconfirm the translation requirements.',
            'ru': 'Пожалуйста, подтвердите требования к переводу еще раз.',
            'ko': '번역 요구사항을 다시 확인해 주세요.',
            'fr': 'Veuillez reconfirmer les exigences de traduction.'
        },
        'translate_request_sent': {
            'zh': '翻译请求已发送，请等待作者同意。',
            'ja': '翻訳リクエストが送信されました。作者の承認をお待ちください。',
            'en': 'Translation request sent, please wait for author approval.',
            'ru': 'Запрос на перевод отправлен, пожалуйста, ждите одобрения автора.',
            'ko': '번역 요청이 전송되었습니다. 작가의 승인을 기다려 주세요.',
            'fr': 'Demande de traduction envoyée, veuillez attendre l\'approbation de l\'auteur.'
        },
        'have_expectations_for_creator': {
            'zh': '我对作者有期待/要求',
            'ja': '作者に期待/要求があります',
            'en': 'I have expectations/requirements for the creator',
            'ru': 'У меня есть ожидания/требования к создателю',
            'ko': '작가에 대한 기대/요구사항이 있습니다',
            'fr': 'J\'ai des attentes/exigences pour le créateur'
        },
        'explain_expectations_then_translate': {
            'zh': '向作者表达期待或要求后再开始翻译',
            'ja': '作者に期待や要求を伝えてから翻訳を開始',
            'en': 'Express expectations or requirements to the author before starting translation',
            'ru': 'Выразить ожидания или требования автору перед началом перевода',
            'ko': '작가에게 기대나 요구사항을 표현한 후 번역 시작',
            'fr': 'Exprimer les attentes ou exigences à l\'auteur avant de commencer la traduction'
        },
        'agree_and_start_translation': {
            'zh': '同意要求并开始翻译',
            'ja': '要求に同意して翻訳を開始',
            'en': 'Agree to requirements and start translation',
            'ru': 'Согласиться с требованиями и начать перевод',
            'ko': '요구사항에 동의하고 번역 시작',
            'fr': 'Accepter les exigences et commencer la traduction'
        },
        'agree_and_go_to_translate_page': {
            'zh': '同意作者要求并进入翻译页面',
            'ja': '作者の要求に同意して翻訳ページに移動',
            'en': 'Agree to author requirements and go to translation page',
            'ru': 'Согласиться с требованиями автора и перейти на страницу перевода',
            'ko': '작가의 요구사항에 동의하고 번역 페이지로 이동',
            'fr': 'Accepter les exigences de l\'auteur et aller à la page de traduction'
        },
        'expectations_for_creator': {
            'zh': '对作者的期待/要求',
            'ja': '作者への期待/要求',
            'en': 'Expectations/Requirements for Creator',
            'ru': 'Ожидания/Требования к создателю',
            'ko': '작가에 대한 기대/요구사항',
            'fr': 'Attentes/Exigences pour le créateur'
        },
        'enter_expectations_for_translation': {
            'zh': '请输入您对翻译的期待或要求',
            'ja': '翻訳への期待や要求を入力してください',
            'en': 'Please enter your expectations or requirements for translation',
            'ru': 'Пожалуйста, введите ваши ожидания или требования к переводу',
            'ko': '번역에 대한 기대나 요구사항을 입력해 주세요',
            'fr': 'Veuillez entrer vos attentes ou exigences pour la traduction'
        },
        'expectations_placeholder': {
            'zh': '例如：翻译风格、术语统一、文化考虑等...',
            'ja': '例：翻訳スタイル、用語統一、文化的配慮など...',
            'en': 'e.g., Translation style, terminology consistency, cultural considerations, etc...',
            'ru': 'например: Стиль перевода, единообразие терминологии, культурные соображения и т.д...',
            'ko': '예: 번역 스타일, 용어 통일, 문화적 고려사항 등...',
            'fr': 'ex: Style de traduction, cohérence terminologique, considérations culturelles, etc...'
        },
        'empty_then_direct_translate': {
            'zh': '留空则直接开始翻译',
            'ja': '空欄の場合は直接翻訳を開始',
            'en': 'Leave empty to start translation directly',
            'ru': 'Оставьте пустым, чтобы начать перевод напрямую',
            'ko': '비워두면 직접 번역 시작',
            'fr': 'Laisser vide pour commencer la traduction directement'
        },
        'send_request_to_creator': {
            'zh': '向作者发送请求',
            'ja': '作者にリクエストを送信',
            'en': 'Send request to creator',
            'ru': 'Отправить запрос создателю',
            'ko': '작가에게 요청 보내기',
            'fr': 'Envoyer la demande au créateur'
        },
        'choose_action': {
            'zh': '选择操作',
            'ja': '操作を選択',
        },
        # 翻译者请求相关消息
        'make_request_title': {
            'zh': '向作者提出要求',
            'ja': '作者に要求を提出',
            'en': 'Make Request to Creator',
            'ru': 'Предъявить требования к создателю',
            'ko': '작가에게 요청하기',
            'fr': 'Faire une demande au créateur'
        },
        'make_request_info': {
            'zh': '您可以向作者表达您的期待或要求，这将帮助作者更好地了解您的需求。',
            'ja': '作者に期待や要求を表現でき、作者があなたのニーズをよりよく理解するのに役立ちます。',
            'en': 'You can express your expectations or requirements to the author, which will help the author better understand your needs.',
            'ru': 'Вы можете выразить свои ожидания или требования автору, что поможет автору лучше понять ваши потребности.',
            'ko': '작가에게 기대나 요구사항을 표현할 수 있으며, 이는 작가가 귀하의 요구사항을 더 잘 이해하는 데 도움이 됩니다.',
            'fr': 'Vous pouvez exprimer vos attentes ou exigences à l\'auteur, ce qui aidera l\'auteur à mieux comprendre vos besoins.'
        },
        'request_sent_success': {
            'zh': '您的要求已发送给作者，请等待作者回复。',
            'ja': 'あなたの要求が作者に送信されました。作者の返信をお待ちください。',
            'en': 'Your request has been sent to the author, please wait for the author\'s response.',
            'ru': 'Ваш запрос отправлен автору, пожалуйста, ждите ответа автора.',
            'ko': '귀하의 요청이 작가에게 전송되었습니다. 작가의 답변을 기다려 주세요.',
            'fr': 'Votre demande a été envoyée à l\'auteur, veuillez attendre la réponse de l\'auteur.'
        },
        'your_expectations_for_creator': {
            'zh': '您对作者的期待/要求',
            'ja': '作者への期待/要求',
            'en': 'Your Expectations/Requirements for Creator',
            'ru': 'Ваши ожидания/Требования к создателю',
            'ko': '작가에 대한 귀하의 기대/요구사항',
            'fr': 'Vos attentes/exigences pour le créateur'
        },
        'enter_expectations_for_creator': {
            'zh': '请输入您对作者的期待或要求',
            'ja': '作者への期待や要求を入力してください',
            'en': 'Please enter your expectations or requirements for the creator',
            'ru': 'Пожалуйста, введите ваши ожидания или требования к создателю',
            'ko': '작가에 대한 기대나 요구사항을 입력해 주세요',
            'fr': 'Veuillez entrer vos attentes ou exigences pour le créateur'
        },
        'expectations_for_creator_placeholder': {
            'zh': '例如：希望自己能作为翻译者署名、能够进行二次传播等...',
            'ja': '例：自分が翻訳者として署名できることを希望、二次配布ができることを希望など...',
            'en': 'e.g., Hope to be credited as a translator, hope to be able to redistribute the work, etc...',
            'ru': 'например: Надеюсь быть указанным как переводчик, надеюсь иметь возможность распространять работу и т.д...',
            'ko': '예: 번역가로 기여자 표시되기를 바람, 작품을 재배포할 수 있기를 바람 등...',
            'fr': 'ex: Espérer être crédité comme traducteur, espérer pouvoir redistribuer l\'œuvre, etc...'
        },
        'request_help_text': {
            'zh': '请详细描述您的需求，这将帮助作者更好地理解您的期望。',
            'ja': 'あなたのニーズを詳しく説明してください。これにより作者があなたの期待をよりよく理解できます。',
            'en': 'Please describe your needs in detail, which will help the author better understand your expectations.',
            'ru': 'Пожалуйста, подробно опишите ваши потребности, это поможет автору лучше понять ваши ожидания.',
            'ko': '귀하의 요구사항을 자세히 설명해 주세요. 이는 작가가 귀하의 기대를 더 잘 이해하는 데 도움이 됩니다.',
            'fr': 'Veuillez décrire vos besoins en détail, ce qui aidera l\'auteur à mieux comprendre vos attentes.'
        },
        'make_request_to_creator': {
            'zh': '向作者提出要求',
            'ja': '作者に要求を提出',
            'en': 'Make Request to Creator',
            'ru': 'Предъявить требования к создателю',
            'ko': '작가에게 요청하기',
            'fr': 'Faire une demande au créateur'
        },
        'make_request_desc': {
            'zh': '向作者表达您的期待或要求',
            'ja': '作者に期待や要求を表現',
            'en': 'Express your expectations or requirements to the author',
            'ru': 'Выразить ваши ожидания или требования автору',
            'ko': '작가에게 기대나 요구사항 표현',
            'fr': 'Exprimer vos attentes ou exigences à l\'auteur'
        },
        'request_content_required': {
            'zh': '请输入您的要求内容',
            'ja': '要求内容を入力してください',
            'en': 'Please enter your request content',
            'ru': 'Пожалуйста, введите содержание вашего запроса',
            'ko': '요청 내용을 입력해 주세요',
            'fr': 'Veuillez entrer le contenu de votre demande'
        },
        'translator_requests': {
            'zh': '翻译者请求',
            'ja': '翻訳者リクエスト',
            'en': 'Translator Requests',
            'ru': 'Запросы переводчика',
            'ko': '번역가 요청',
            'fr': 'Demandes de traducteur'
        },
        'translator_request': {
            'zh': '翻译者请求',
            'ja': '翻訳者リクエスト',
            'en': 'Translator Request',
            'ru': 'Запрос переводчика',
            'ko': '번역가 요청',
            'fr': 'Demande de traducteur'
        },
        'requests_author_help': {
            'zh': '向您提出要求',
            'ja': 'あなたに要求を提出',
            'en': 'Requests your help',
            'ru': 'Просит вашей помощи',
            'ko': '도움을 요청합니다',
            'fr': 'Demande votre aide'
        },
        'translator_request_content': {
            'zh': '要求内容',
            'ja': '要求内容',
            'en': 'Request content',
            'ru': 'Содержание запроса',
            'ko': '요청 내용',
            'fr': 'Contenu de la demande'
        },
        'respond_to_translator_request': {
            'zh': '回复翻译者请求',
            'ja': '翻訳者リクエストに返信',
            'en': 'Respond to Translator Request',
            'ru': 'Ответить на запрос переводчика',
            'ko': '번역가 요청에 답변',
            'fr': 'Répondre à la demande du traducteur'
        },
        'your_response': {
            'zh': '您的回复',
            'ja': 'あなたの返信',
            'en': 'Your response',
            'ru': 'Ваш ответ',
            'ko': '귀하의 답변',
            'fr': 'Votre réponse'
        },
        'response_placeholder': {
            'zh': '请输入您的回复...',
            'ja': '返信を入力してください...',
            'en': 'Please enter your response...',
            'ru': 'Пожалуйста, введите ваш ответ...',
            'ko': '답변을 입력해 주세요...',
            'fr': 'Veuillez entrer votre réponse...'
        },
        'send_response': {
            'zh': '发送回复',
            'ja': '返信を送信',
            'en': 'Send response',
            'ru': 'Отправить ответ',
            'ko': '답변 보내기',
            'fr': 'Envoyer la réponse'
        },
        'response_required': {
            'zh': '请输入回复内容',
            'ja': '返信内容を入力してください',
            'en': 'Please enter response content',
            'ru': 'Пожалуйста, введите содержание ответа',
            'ko': '답변 내용을 입력해 주세요',
            'fr': 'Veuillez entrer le contenu de la réponse'
        },
        'response_sent': {
            'zh': '回复已发送',
            'ja': '返信が送信されました',
            'en': 'Response sent',
            'ru': 'Ответ отправлен',
            'ko': '답변이 전송되었습니다',
            'fr': 'Réponse envoyée'
        },
        'translator_request_approved_msg': {
            'zh': '已同意翻译者的要求',
            'ja': '翻訳者の要求を承認しました',
            'en': 'Translator request approved',
            'ru': 'Запрос переводчика одобрен',
            'ko': '번역가 요청 승인됨',
            'fr': 'Demande de traducteur approuvée'
        },
        'translator_request_rejected_msg': {
            'zh': '已拒绝翻译者的要求',
            'ja': '翻訳者の要求を拒否しました',
            'en': 'Translator request rejected',
            'ru': 'Запрос переводчика отклонен',
            'ko': '번역가 요청 거부됨',
            'fr': 'Demande de traducteur rejetée'
        },
        'choose_action': {
            'zh': '选择操作',
            'ja': '操作を選択',
            'en': 'Choose Action',
            'ru': 'Выберите действие',
            'ko': '작업 선택',
            'fr': 'Choisir l\'action'
        },
        'your_expectation': {
            'zh': '您的期待',
            'ja': 'あなたの期待',
            'en': 'Your Expectation',
            'ru': 'Ваше ожидание',
            'ko': '당신의 기대',
            'fr': 'Votre attente'
        },
        # 基础模板消息
                       'site_name': {
                   'zh': '基于兴趣的翻译平台',
                   'ja': '興味に基づいた翻訳プラットフォーム',
                   'en': 'Interest-Based Translation Platform',
                   'ru': 'Платформа переводов на основе интересов',
                   'ko': '관심사 기반 번역 플랫폼',
                   'fr': 'Plateforme de traduction basée sur les intérêts'
               },
               'site_description': {
                   'zh': '连接创作者与翻译者的专业平台',
                   'ja': 'クリエイターと翻訳者をつなぐ専門プラットフォーム',
                   'en': 'Professional platform connecting creators and translators',
                   'ru': 'Профессиональная платформа, соединяющая создателей и переводчиков',
                   'ko': '창작자와 번역가를 연결하는 전문 플랫폼',
                   'fr': 'Plateforme professionnelle connectant créateurs et traducteurs'
               },
        'works': {
            'zh': '作品',
            'ja': '作品',
            'en': 'Works',
            'ru': 'Работы',
            'ko': '작품',
            'fr': 'Œuvres'
        },
        'translate': {
            'zh': '翻译',
            'ja': '翻訳',
            'en': 'Translate',
            'ru': 'Перевести',
            'ko': '번역',
            'fr': 'Traduire'
        },
        'upload': {
            'zh': '上传',
            'ja': 'アップロード',
            'en': 'Upload',
            'ru': 'Загрузить',
            'ko': '업로드',
            'fr': 'Télécharger'
        },
        'messages': {
            'zh': '私信',
            'ja': 'メッセージ',
            'en': 'Messages',
            'ru': 'Сообщения',
            'ko': '메시지',
            'fr': 'Messages'
        },
        'profile': {
            'zh': '个人资料',
            'ja': 'プロフィール',
            'en': 'Profile',
            'ru': 'Профиль',
            'ko': '프로필',
            'fr': 'Profil'
        },
        'friends': {
            'zh': '好友',
            'ja': '友達',
            'en': 'Friends',
            'ru': 'Друзья',
            'ko': '친구',
            'fr': 'Amis'
        },
        'trusted_translators': {
            'zh': '信赖翻译者',
            'ja': '信頼翻訳者',
            'en': 'Trusted Translators',
            'ru': 'Доверенные переводчики',
            'ko': '신뢰하는 번역가',
            'fr': 'Traducteurs de confiance'
        },
        'admin_panel': {
            'zh': '管理面板',
            'ja': '管理パネル',
            'en': 'Admin Panel',
            'ru': 'Панель администратора',
            'ko': '관리 패널',
            'fr': 'Panneau d\'administration'
        },
        'logout': {
            'zh': '登出',
            'ja': 'ログアウト',
            'en': 'Logout',
            'ru': 'Выйти',
            'ko': '로그아웃',
            'fr': 'Déconnexion'
        },
        'login': {
            'zh': '登录',
            'ja': 'ログイン',
            'en': 'Login',
            'ru': 'Войти',
            'ko': '로그인',
            'fr': 'Connexion'
        },
        'register': {
            'zh': '注册',
            'ja': '登録',
            'en': 'Register',
            'ru': 'Регистрация',
            'ko': '등록',
            'fr': 'S\'inscrire'
        },
        'language': {
            'zh': '中文',
            'ja': '日本語',
            'en': 'English',
            'ru': 'Русский',
            'ko': '한국어',
            'fr': 'Français'
        },
        'chinese_lang': {
            'zh': '中文',
            'ja': '中国語',
            'en': 'Chinese',
            'ru': 'Китайский',
            'ko': '중국어',
            'fr': 'Chinois'
        },
        'japanese_lang': {
            'zh': '日文',
            'ja': '日本語',
            'en': 'Japanese',
            'ru': 'Японский',
            'ko': '일본어',
            'fr': 'Japonais'
        },
        'english_lang': {
            'zh': '英文',
            'ja': '英語',
            'en': 'English',
            'ru': 'Английский',
            'ko': '영어',
            'fr': 'Anglais'
        },
        'russian_lang': {
            'zh': '俄文',
            'ja': 'ロシア語',
            'en': 'Russian',
            'ru': 'Русский',
            'ko': '러시아어',
            'fr': 'Russe'
        },
        'korean_lang': {
            'zh': '韩文',
            'ja': '韓国語',
            'en': 'Korean',
            'ru': 'Корейский',
            'ko': '한국어',
            'fr': 'Coréen'
        },
                               'french_lang': {
            'zh': '法文',
            'ja': 'フランス語',
            'en': 'French',
            'ru': 'Французский',
            'ko': '프랑스어',
            'fr': 'Français'
        },
        # 收藏功能相关消息
        'favorites': {
            'zh': '我的收藏',
            'ja': 'お気に入り',
            'en': 'My Favorites',
            'ru': 'Мои избранные',
            'ko': '내 즐겨찾기',
            'fr': 'Mes favoris'
        },
        'add_to_favorites': {
            'zh': '收藏',
            'ja': 'お気に入りに追加',
            'en': 'Add to Favorites',
            'ru': 'Добавить в избранное',
            'ko': '즐겨찾기에 추가',
            'fr': 'Ajouter aux favoris'
        },
        'remove_from_favorites': {
            'zh': '取消收藏',
            'ja': 'お気に入りから削除',
            'en': 'Remove from Favorites',
            'ru': 'Удалить из избранного',
            'ko': '즐겨찾기에서 제거',
            'fr': 'Retirer des favoris'
        },
        'favorite_added': {
            'zh': '已添加到收藏',
            'ja': 'お気に入りに追加されました',
            'en': 'Added to favorites',
            'ru': 'Добавлено в избранное',
            'ko': '즐겨찾기에 추가되었습니다',
            'fr': 'Ajouté aux favoris'
        },
        'favorite_removed': {
            'zh': '已从收藏中移除',
            'ja': 'お気に入りから削除されました',
            'en': 'Removed from favorites',
            'ru': 'Удалено из избранного',
            'ko': '즐겨찾기에서 제거되었습니다',
            'fr': 'Retiré des favoris'
        },
        'no_favorites': {
            'zh': '暂无收藏作品',
            'ja': 'お気に入りの作品がありません',
            'en': 'No favorite works',
            'ru': 'Нет избранных работ',
            'ko': '즐겨찾기 작품이 없습니다',
            'fr': 'Aucune œuvre favorite'
        },
        'favorites_description': {
            'zh': '您收藏的所有作品',
            'ja': 'お気に入りに追加したすべての作品',
            'en': 'All your favorite works',
            'ru': 'Все ваши избранные работы',
            'ko': '즐겨찾기에 추가한 모든 작품',
            'fr': 'Toutes vos œuvres favorites'
        },
        'no_favorites_description': {
            'zh': '您还没有收藏任何作品。浏览作品时点击收藏按钮即可添加到收藏列表。',
            'ja': 'まだお気に入りの作品がありません。作品を閲覧する際にハートボタンをクリックしてお気に入りに追加してください。',
            'en': 'You haven\'t favorited any works yet. Click the heart button when browsing works to add them to your favorites.',
            'ru': 'У вас пока нет избранных работ. Нажмите кнопку сердца при просмотре работ, чтобы добавить их в избранное.',
            'ko': '아직 즐겨찾기한 작품이 없습니다. 작품을 둘러볼 때 하트 버튼을 클릭하여 즐겨찾기에 추가하세요.',
            'fr': 'Vous n\'avez pas encore d\'œuvres favorites. Cliquez sur le bouton cœur lors de la navigation pour les ajouter à vos favoris.'
        },
        'favorited_on': {
            'zh': '收藏于',
            'ja': 'お気に入りに追加日',
            'en': 'Favorited on',
            'ru': 'Добавлено в избранное',
            'ko': '즐겨찾기 추가일',
            'fr': 'Ajouté aux favoris le'
        },
        'confirm_remove_favorite': {
            'zh': '确定要取消收藏这个作品吗？',
            'ja': 'この作品をお気に入りから削除しますか？',
            'en': 'Are you sure you want to remove this work from favorites?',
            'ru': 'Вы уверены, что хотите удалить эту работу из избранного?',
            'ko': '이 작품을 즐겨찾기에서 제거하시겠습니까?',
            'fr': 'Êtes-vous sûr de vouloir retirer cette œuvre de vos favoris?'
        },
        'favorites_pagination': {
            'zh': '收藏作品分页',
            'ja': 'お気に入り作品のページネーション',
            'en': 'Favorites pagination',
            'ru': 'Пагинация избранных работ',
            'ko': '즐겨찾기 작품 페이지네이션',
            'fr': 'Pagination des favoris'
        },
        'browse_works': {
            'zh': '浏览作品',
            'ja': '作品を閲覧',
            'en': 'Browse Works',
            'ru': 'Просмотр работ',
            'ko': '작품 둘러보기',
            'fr': 'Parcourir les œuvres'
        },
               # 作品列表页面消息
               'works_list': {
                   'zh': '作品列表',
                   'ja': '作品リスト',
                   'en': 'Works',
                   'ru': 'Работы',
                   'ko': '작품 목록',
                   'fr': 'Œuvres'
               },
               'filter': {
                   'zh': '筛选',
                   'ja': 'フィルター',
                   'en': 'Filter',
                   'ru': 'Фильтр',
                   'ko': '필터',
                   'fr': 'Filtre'
               },
               'search': {
                   'zh': '搜索',
                   'ja': '検索',
                   'en': 'Search',
                   'ru': 'Поиск',
                   'ko': '검색',
                   'fr': 'Recherche'
               },
               'search_placeholder': {
                   'zh': '搜索标题或内容...',
                   'ja': 'タイトルや内容で検索...',
                   'en': 'Search by title or content...',
                   'ru': 'Поиск по названию или содержанию...',
                   'ko': '제목이나 내용으로 검색...',
                   'fr': 'Rechercher par titre ou contenu...'
               },
               'category': {
                   'zh': '分类',
                   'ja': 'カテゴリー',
                   'en': 'Category',
                   'ru': 'Категория',
                   'ko': '카테고리',
                   'fr': 'Catégorie'
               },
               'all_categories': {
                   'zh': '所有分类',
                   'ja': 'すべてのカテゴリー',
                   'en': 'All Categories',
                   'ru': 'Все категории',
                   'ko': '모든 카테고리',
                   'fr': 'Toutes les catégories'
               },
               'all_languages': {
                   'zh': '所有语言',
                   'ja': 'すべての言語',
                   'en': 'All Languages',
                   'ru': 'Все языки',
                   'ko': '모든 언어',
                   'fr': 'Toutes les langues'
               },
               'original_language': {
                   'zh': '原文语言',
                   'ja': '原文言語',
                   'en': 'Original Language',
                   'ru': 'Исходный язык',
                   'ko': '원본 언어',
                   'fr': 'Langue originale'
               },
               'target_language': {
                   'zh': '目标语言',
                   'ja': '翻訳言語',
                   'en': 'Target Language',
                   'ru': 'Целевой язык',
                   'ko': '번역 언어',
                   'fr': 'Langue cible'
               },
               'status': {
                   'zh': '状态',
                   'ja': 'ステータス',
                   'en': 'Status',
                   'ru': 'Статус',
                   'ko': '상태',
                   'fr': 'Statut'
               },
               'all_status': {
                   'zh': '所有状态',
                   'ja': 'すべてのステータス',
                   'en': 'All Status',
                   'ru': 'Все статусы',
                   'ko': '모든 상태',
                   'fr': 'Tous les statuts'
               },
               'pending': {
                   'zh': '待翻译',
                   'ja': '翻訳待ち',
                   'en': 'Pending',
                   'ru': 'Ожидает',
                   'ko': '대기 중',
                   'fr': 'En attente'
               },
               'translating': {
                   'zh': '翻译中',
                   'ja': '翻訳中',
                   'en': 'Translating',
                   'ru': 'Переводится',
                   'ko': '번역 중',
                   'fr': 'En cours'
               },
               'completed': {
                   'zh': '已完成',
                   'ja': '完了',
                   'en': 'Completed',
                   'ru': 'Завершено',
                   'ko': '완료',
                   'fr': 'Terminé'
               },
               'tags': {
                   'zh': '标签',
                   'ja': 'タグ',
                   'en': 'Tags',
                   'ru': 'Теги',
                   'ko': '태그',
                   'fr': 'Étiquettes'
               },
               'all_tags': {
                   'zh': '所有标签',
                   'ja': 'すべてのタグ',
                   'en': 'All Tags',
                   'ru': 'Все теги',
                   'ko': '모든 태그',
                   'fr': 'Toutes les étiquettes'
               },
               'tag_multiple_translators': {
                   'zh': '多人翻译',
                   'ja': '複数翻訳者',
                   'en': 'Multiple Translators',
                   'ru': 'Множественные переводчики',
                   'ko': '다중 번역가',
                   'fr': 'Traducteurs multiples'
               },
               'apply_filter': {
                   'zh': '应用筛选',
                   'ja': 'フィルターを適用',
                   'en': 'Apply Filter',
                   'ru': 'Применить фильтр',
                   'ko': '필터 적용',
                   'fr': 'Appliquer le filtre'
               },
               'clear_filter': {
                   'zh': '清除筛选',
                   'ja': 'フィルターをクリア',
                   'en': 'Clear Filter',
                   'ru': 'Очистить фильтр',
                   'ko': '필터 지우기',
                   'fr': 'Effacer le filtre'
               },
               'sort_by': {
                   'zh': '排序方式',
                   'ja': '並び順',
                   'en': 'Sort By',
                   'ru': 'Сортировать по',
                   'ko': '정렬 기준',
                   'fr': 'Trier par'
               },
               'latest': {
                   'zh': '最新',
                   'ja': '最新',
                   'en': 'Latest',
                   'ru': 'Новые',
                   'ko': '최신',
                   'fr': 'Plus récent'
               },
               'oldest': {
                   'zh': '最早',
                   'ja': '最古',
                   'en': 'Oldest',
                   'ru': 'Старые',
                   'ko': '오래된',
                   'fr': 'Plus ancien'
               },
               'most_liked': {
                   'zh': '最多点赞',
                   'ja': 'いいね最多',
                   'en': 'Most Liked',
                   'ru': 'Больше лайков',
                   'ko': '좋아요 최다',
                   'fr': 'Plus aimé'
               },
               'most_commented': {
                   'zh': '最多评论',
                   'ja': 'コメント最多',
                   'en': 'Most Commented',
                   'ru': 'Больше комментариев',
                   'ko': '댓글 최다',
                   'fr': 'Plus commenté'
               },
               'no_works_found': {
                   'zh': '未找到作品',
                   'ja': '作品が見つかりません',
                   'en': 'No works found',
                   'ru': 'Работы не найдены',
                   'ko': '작품을 찾을 수 없습니다',
                   'fr': 'Aucune œuvre trouvée'
               },
               'try_different_filters': {
                   'zh': '请尝试不同的筛选条件',
                   'ja': '異なるフィルター条件を試してください',
                   'en': 'Try different filter criteria',
                   'ru': 'Попробуйте другие критерии фильтра',
                   'ko': '다른 필터 조건을 시도해 보세요',
                   'fr': 'Essayez des critères de filtre différents'
               },

               'target_language_label': {
                   'zh': '目标语言',
                   'ja': '目標言語',
                   'en': 'Target Language',
                   'ru': 'Целевой язык',
                   'ko': '목표 언어',
                   'fr': 'Langue cible'
               },
               # 管理面板消息
               'admin_panel_title': {
                   'zh': '管理面板',
                   'ja': '管理パネル',
                   'en': 'Admin Panel',
                   'ru': 'Панель администратора',
                   'ko': '관리 패널',
                   'fr': 'Panneau d\'administration'
               },
               'total_users': {
                   'zh': '总用户数',
                   'ja': '総ユーザー数',
                   'en': 'Total Users',
                   'ru': 'Всего пользователей',
                   'ko': '총 사용자 수',
                   'fr': 'Total des utilisateurs'
               },
               'total_works': {
                   'zh': '总作品数',
                   'ja': '総作品数',
                   'en': 'Total Works',
                   'ru': 'Всего работ',
                   'ko': '총 작품 수',
                   'fr': 'Total des œuvres'
               },
               'total_translations': {
                   'zh': '总翻译数',
                   'ja': '総翻訳数',
                   'en': 'Total Translations',
                   'ru': 'Всего переводов',
                   'ko': '총 번역 수',
                   'fr': 'Total des traductions'
               },
               'total_comments': {
                   'zh': '总评论数',
                   'ja': '総コメント数',
                   'en': 'Total Comments',
                   'ru': 'Всего комментариев',
                   'ko': '총 댓글 수',
                   'fr': 'Total des commentaires'
               },
               'match_rate': {
                   'zh': '匹配率（已翻译比例）',
                   'ja': 'マッチ率（翻訳済み比率）',
                   'en': 'Match Rate (Translated %)',
                   'ru': 'Коэффициент соответствия (%)',
                   'ko': '매치율 (번역 완료 비율)',
                   'fr': 'Taux de correspondance (%)'
               },
               'avg_match_speed': {
                   'zh': '平均匹配速度',
                   'ja': '平均マッチ速度',
                   'en': 'Average Match Speed',
                   'ru': 'Средняя скорость соответствия',
                   'ko': '평균 매치 속도',
                   'fr': 'Vitesse de correspondance moyenne'
               },
               'match_stats_details': {
                   'zh': '匹配统计详情',
                   'ja': 'マッチ統計詳細',
                   'en': 'Match Statistics Details',
                   'ru': 'Детали статистики соответствия',
                   'ko': '매치 통계 상세',
                   'fr': 'Détails des statistiques de correspondance'
               },
               'match_rate_stats': {
                   'zh': '匹配率统计',
                   'ja': 'マッチ率統計',
                   'en': 'Match Rate Statistics',
                   'ru': 'Статистика коэффициента соответствия',
                   'ko': '매치율 통계',
                   'fr': 'Statistiques du taux de correspondance'
               },
               'match_speed_stats': {
                   'zh': '匹配速度统计',
                   'ja': 'マッチ速度統計',
                   'en': 'Match Speed Statistics',
                   'ru': 'Статистика скорости соответствия',
                   'ko': '매치 속도 통계',
                   'fr': 'Statistiques de vitesse de correspondance'
               },
               'total_works_exclude_seed': {
                   'zh': '总作品数（排除种子数据）',
                   'ja': '総作品数（シードデータ除く）',
                   'en': 'Total Works (Exclude Seed Data)',
                   'ru': 'Всего работ (исключая тестовые данные)',
                   'ko': '총 작품 수 (시드 데이터 제외)',
                   'fr': 'Total des œuvres (hors données de test)'
               },
               'completed_translations': {
                   'zh': '已完成翻译',
                   'ja': '翻訳完了',
                   'en': 'Completed Translations',
                   'ru': 'Завершенные переводы',
                   'ko': '번역 완료',
                   'fr': 'Traductions terminées'
               },
               'match_rate_percent': {
                   'zh': '匹配率',
                   'ja': 'マッチ率',
                   'en': 'Match Rate',
                   'ru': 'Коэффициент соответствия',
                   'ko': '매치율',
                   'fr': 'Taux de correspondance'
               },
               'avg_match_speed_hours': {
                   'zh': '平均匹配速度',
                   'ja': '平均マッチ速度',
                   'en': 'Average Match Speed',
                   'ru': 'Средняя скорость соответствия',
                   'ko': '평균 매치 속도',
                   'fr': 'Vitesse de correspondance moyenne'
               },
               'fastest_match': {
                   'zh': '最快匹配',
                   'ja': '最速マッチ',
                   'en': 'Fastest Match',
                   'ru': 'Самое быстрое соответствие',
                   'ko': '최고속 매치',
                   'fr': 'Correspondance la plus rapide'
               },
               'slowest_match': {
                   'zh': '最慢匹配',
                   'ja': '最遅マッチ',
                   'en': 'Slowest Match',
                   'ru': 'Самое медленное соответствие',
                   'ko': '최저속 매치',
                   'fr': 'Correspondance la plus lente'
               },
               'hours': {
                   'zh': '小时',
                   'ja': '時間',
                   'en': 'hours',
                   'ru': 'часов',
                   'ko': '시간',
                   'fr': 'heures'
               },
               'user_management': {
                   'zh': '用户管理',
                   'ja': 'ユーザー管理',
                   'en': 'User Management',
                   'ru': 'Управление пользователями',
                   'ko': '사용자 관리',
                   'fr': 'Gestion des utilisateurs'
               },
               'admin_requests_management': {
                   'zh': '管理员申请管理',
                   'ja': '管理者申請管理',
                   'en': 'Admin Requests Management',
                   'ru': 'Управление заявками администратора',
                   'ko': '관리자 신청 관리',
                   'fr': 'Gestion des demandes d\'administrateur'
               },
               'user_id': {
                   'zh': 'ID',
                   'ja': 'ID',
                   'en': 'ID',
                   'ru': 'ID',
                   'ko': 'ID',
                   'fr': 'ID'
               },
               'username': {
                   'zh': '用户名',
                   'ja': 'ユーザー名',
                   'en': 'Username',
                   'ru': 'Имя пользователя',
                   'ko': '사용자 이름',
                   'fr': 'Nom d\'utilisateur'
               },
               'email': {
                   'zh': '邮箱',
                   'ja': 'メール',
                   'en': 'Email',
                   'ru': 'Электронная почта',
                   'ko': '이메일',
                   'fr': 'E-mail'
               },
               'role': {
                   'zh': '角色',
                   'ja': '役割',
                   'en': 'Role',
                   'ru': 'Роль',
                   'ko': '역할',
                   'fr': 'Rôle'
               },
               'registration_date': {
                   'zh': '注册时间',
                   'ja': '登録日',
                   'en': 'Registration Date',
                   'ru': 'Дата регистрации',
                   'ko': '가입일',
                   'fr': 'Date d\'inscription'
               },
               'actions': {
                   'zh': '操作',
                   'ja': '操作',
                   'en': 'Actions',
                   'ru': 'Действия',
                   'ko': '작업',
                   'fr': 'Actions'
               },
               'role_admin': {
                   'zh': '管理员',
                   'ja': '管理者',
                   'en': 'Admin',
                   'ru': 'Администратор',
                   'ko': '관리자',
                   'fr': 'Administrateur'
               },
               'role_translator': {
                   'zh': '翻译者',
                   'ja': '翻訳者',
                   'en': 'Translator',
                   'ru': 'Переводчик',
                   'ko': '번역가',
                   'fr': 'Traducteur'
               },
               'role_user': {
                   'zh': '普通用户',
                   'ja': '一般ユーザー',
                   'en': 'User',
                   'ru': 'Пользователь',
                   'ko': '일반 사용자',
                   'fr': 'Utilisateur'
               },
               'change_role': {
                   'zh': '切换角色',
                   'ja': '役割変更',
                   'en': 'Change Role',
                   'ru': 'Изменить роль',
                   'ko': '역할 변경',
                   'fr': 'Changer le rôle'
               },
               'work_management': {
                   'zh': '作品管理',
                   'ja': '作品管理',
                   'en': 'Work Management',
                   'ru': 'Управление работами',
                   'ko': '작품 관리',
                   'fr': 'Gestion des œuvres'
               },
               'title': {
                   'zh': '标题',
                   'ja': 'タイトル',
                   'en': 'Title',
                   'ru': 'Название',
                   'ko': '제목',
                   'fr': 'Titre'
               },
               'creator': {
                   'zh': '创作者',
                   'ja': 'クリエイター',
                   'en': 'Creator',
                   'ru': 'Создатель',
                   'ko': '창작자',
                   'fr': 'Créateur'
               },
               'language': {
                   'zh': '语言',
                   'ja': '言語',
                   'en': 'Language',
                   'ru': 'Язык',
                   'ko': '언어',
                   'fr': 'Langue'
               },
               'creation_date': {
                   'zh': '创建时间',
                   'ja': '作成日',
                   'en': 'Creation Date',
                   'ru': 'Дата создания',
                   'ko': '생성일',
                   'fr': 'Date de création'
               },
               'view': {
                   'zh': '查看',
                   'ja': '詳細',
                   'en': 'View',
                   'ru': 'Просмотр',
                   'ko': '보기',
                   'fr': 'Voir'
               },
               'translation_management': {
                   'zh': '翻译管理',
                   'ja': '翻訳管理',
                   'en': 'Translation Management',
                   'ru': 'Управление переводами',
                   'ko': '번역 관리',
                   'fr': 'Gestion des traductions'
               },
               'work': {
                   'zh': '作品',
                   'ja': '作品',
                   'en': 'Work',
                   'ru': 'Работа',
                   'ko': '작품',
                   'fr': 'Œuvre'
               },
               'translator': {
                   'zh': '翻译者',
                   'ja': '翻訳者',
                   'en': 'Translator',
                   'ru': 'Переводчик',
                   'ko': '번역가',
                   'fr': 'Traducteur'
               },
               'status_draft': {
                   'zh': '草稿',
                   'ja': '下書き',
                   'en': 'Draft',
                   'ru': 'Черновик',
                   'ko': '초안',
                   'fr': 'Brouillon'
               },
               'status_submitted': {
                   'zh': '已提交',
                   'ja': '提出済み',
                   'en': 'Submitted',
                   'ru': 'Отправлено',
                   'ko': '제출됨',
                   'fr': 'Soumis'
               },
               'status_approved': {
                   'zh': '已通过',
                   'ja': '承認済み',
                   'en': 'Approved',
                   'ru': 'Одобрено',
                   'ko': '승인됨',
                   'fr': 'Approuvé'
               },
               'status_rejected': {
                   'zh': '已拒绝',
                   'ja': '却下',
                   'en': 'Rejected',
                   'ru': 'Отклонено',
                   'ko': '거부됨',
                   'fr': 'Rejeté'
               },
               'export_development': {
                   'zh': '导出功能开发中...',
                   'ja': 'エクスポート機能は開発中です...',
                   'en': 'Export feature is under development...',
                   'ru': 'Функция экспорта в разработке...',
                   'ko': '내보내기 기능 개발 중...',
                   'fr': 'La fonction d\'exportation est en cours de développement...'
               },
               'clear_development': {
                   'zh': '清理功能开发中...',
                   'ja': 'クリア機能は開発中です...',
                   'en': 'Clear feature is under development...',
                   'ru': 'Функция очистки в разработке...',
                   'ko': '정리 기능 개발 중...',
                   'fr': 'La fonction de nettoyage est en cours de développement...'
               },
               'confirm_clear_all_data': {
                   'zh': '确认清除所有数据？',
                   'ja': 'すべてのデータをクリアしますか？',
                   'en': 'Confirm clear all data?',
                   'ru': 'Подтвердить очистку всех данных?',
                   'ko': '모든 데이터를 지우시겠습니까?',
                   'fr': 'Confirmer l\'effacement de toutes les données?'
               },
               # 分类消息
               'category_novel': {
                   'zh': '小说',
                   'ja': '小説',
                   'en': 'Novel',
                   'ru': 'Роман',
                   'ko': '소설',
                   'fr': 'Roman'
               },
               'category_image': {
                   'zh': '图片',
                   'ja': '画像',
                   'en': 'Image',
                   'ru': 'Изображение',
                   'ko': '이미지',
                   'fr': 'Image'
               },
               'category_video': {
                   'zh': '视频・动画',
                   'ja': '動画・アニメ',
                   'en': 'Video & Animation',
                   'ru': 'Видео и анимация',
                   'ko': '비디오・애니메이션',
                   'fr': 'Vidéo et animation'
               },
               'category_chat': {
                   'zh': '闲聊',
                   'ja': '雑談',
                   'en': 'Chat',
                   'ru': 'Чат',
                   'ko': '잡담',
                   'fr': 'Chat'
               },
               'category_other': {
                   'zh': '其他',
                   'ja': 'その他',
                   'en': 'Other',
                   'ru': 'Другое',
                   'ko': '기타',
                   'fr': 'Autre'
               },
               # works.html 需要的额外消息键
               'category_post_article': {
                   'zh': '投稿・文章',
                   'ja': '投稿・文章',
                   'en': 'Post/Article',
                   'ru': 'Пост/Статья',
                   'ko': '게시물/기사',
                   'fr': 'Publication/Article'
               },
               'category_comic': {
                   'zh': '漫画',
                   'ja': '漫画',
                   'en': 'Comic',
                   'ru': 'Комикс',
                   'ko': '만화',
                   'fr': 'Bande dessinée'
               },
               'category_audio': {
                   'zh': '音声',
                   'ja': '音声',
                   'en': 'Audio',
                   'ru': 'Аудио',
                   'ko': '오디오',
                   'fr': 'Audio'
               },
               'category_video_animation': {
                   'zh': '视频・动画',
                   'ja': '動画・アニメ',
                   'en': 'Video/Animation',
                   'ru': 'Видео/Анимация',
                   'ko': '비디오/애니메이션',
                   'fr': 'Vidéo/Animation'
               },
               'category_discussion': {
                   'zh': '闲聊',
                   'ja': '雑談',
                   'en': 'Chat',
                   'ru': 'Чат',
                   'ko': '잡담',
                   'fr': 'Discussion'
               },
               'all_status': {
                   'zh': '所有状态',
                   'ja': 'すべてのステータス',
                   'en': 'All Status',
                   'ru': 'Все статусы',
                   'ko': '모든 상태',
                   'fr': 'Tous les statuts'
               },
               'status_pending': {
                   'zh': '待翻译',
                   'ja': '翻訳待ち',
                   'en': 'Pending Translation',
                   'ru': 'Ожидает перевода',
                   'ko': '번역 대기',
                   'fr': 'En attente de traduction'
               },
               'status_translating': {
                   'zh': '翻译中',
                   'ja': '翻訳中',
                   'en': 'Translating',
                   'ru': 'Переводится',
                   'ko': '번역 중',
                   'fr': 'En cours de traduction'
               },
               'status_completed': {
                   'zh': '已完成',
                   'ja': '完了',
                   'en': 'Completed',
                   'ru': 'Завершено',
                   'ko': '완료',
                   'fr': 'Terminé'
               },
               'apply_filter': {
                   'zh': '应用筛选',
                   'ja': 'フィルターを適用',
                   'en': 'Apply Filter',
                   'ru': 'Применить фильтр',
                   'ko': '필터 적용',
                   'fr': 'Appliquer le filtre'
               },
               'clear_filter': {
                   'zh': '清除筛选',
                   'ja': 'フィルターをクリア',
                   'en': 'Clear Filter',
                   'ru': 'Очистить фильтр',
                   'ko': '필터 지우기',
                   'fr': 'Effacer le filtre'
               },
               'section_works': {
                   'zh': '作品',
                   'ja': '作品',
                   'en': 'Works',
                   'ru': 'Работы',
                   'ko': '작품',
                   'fr': 'Œuvres'
               },
               'filtered': {
                   'zh': '已筛选',
                   'ja': 'フィルター済み',
                   'en': 'Filtered',
                   'ru': 'Отфильтровано',
                   'ko': '필터됨',
                   'fr': 'Filtré'
               },
               'upload_work': {
                   'zh': '上传作品',
                   'ja': '作品をアップロード',
                   'en': 'Upload Work',
                   'ru': 'Загрузить работу',
                   'ko': '작품 업로드',
                   'fr': 'Télécharger une œuvre'
               },
               'avatar_alt': {
                   'zh': '头像',
                   'ja': 'アバター',
                   'en': 'Avatar',
                   'ru': 'Аватар',
                   'ko': '아바타',
                   'fr': 'Avatar'
               },
               'previous_page': {
                   'zh': '上一页',
                   'ja': '前へ',
                   'en': 'Previous',
                   'ru': 'Предыдущая',
                   'ko': '이전',
                   'fr': 'Précédent'
               },
               'next_page': {
                   'zh': '下一页',
                   'ja': '次へ',
                   'en': 'Next',
                   'ru': 'Следующая',
                   'ko': '다음',
                   'fr': 'Suivant'
               },
               'no_works_found': {
                   'zh': '暂无作品',
                   'ja': '作品が見つかりません',
                   'en': 'No works found',
                   'ru': 'Работы не найдены',
                   'ko': '작품을 찾을 수 없습니다',
                   'fr': 'Aucune œuvre trouvée'
               },
               'no_works_description': {
                   'zh': '没有找到符合条件的作品',
                   'ja': '条件に合う作品がありません',
                   'en': 'No works match your criteria',
                   'ru': 'Работы, соответствующие вашим критериям, не найдены',
                   'ko': '조건에 맞는 작품이 없습니다',
                   'fr': 'Aucune œuvre ne correspond à vos critères'
               },
               'upload_first_work': {
                   'zh': '上传第一个作品',
                   'ja': '最初の作品をアップロード',
                   'en': 'Upload your first work',
                   'ru': 'Загрузите свою первую работу',
                   'ko': '첫 번째 작품을 업로드하세요',
                   'fr': 'Téléchargez votre première œuvre'
               },
               # work_detail.html 需要的额外消息键
               'edit': {
                   'zh': '编辑',
                   'ja': '編集',
                   'en': 'Edit',
                   'ru': 'Редактировать',
                   'ko': '편집',
                   'fr': 'Modifier'
               },
               'delete': {
                   'zh': '删除',
                   'ja': '削除',
                   'en': 'Delete',
                   'ru': 'Удалить',
                   'ko': '삭제',
                   'fr': 'Supprimer'
               },
               'admin_edit': {
                   'zh': '管理员编辑',
                   'ja': '管理者編集',
                   'en': 'Admin Edit',
                   'ru': 'Редактирование администратора',
                   'ko': '관리자 편집',
                   'fr': 'Modification admin'
               },
               'admin_delete': {
                   'zh': '管理员删除',
                   'ja': '管理者削除',
                   'en': 'Admin Delete',
                   'ru': 'Удаление администратора',
                   'ko': '관리자 삭제',
                   'fr': 'Suppression admin'
               },
               'creator': {
                   'zh': '创作者',
                   'ja': 'クリエイター',
                   'en': 'Creator',
                   'ru': 'Создатель',
                   'ko': '창작자',
                   'fr': 'Créateur'
               },
               # admin_requests.html 需要的额外消息键
               'admin_requests_management': {
                   'zh': '管理员申请管理',
                   'ja': '管理者申請管理',
                   'en': 'Admin Requests Management',
                   'ru': 'Управление заявками администратора',
                   'ko': '관리자 신청 관리',
                   'fr': 'Gestion des demandes d\'administrateur'
               },
               'pending_requests': {
                   'zh': '待审核申请',
                   'ja': '待审核申請',
                   'en': 'Pending Requests',
                   'ru': 'Ожидающие заявки',
                   'ko': '대기 중인 신청',
                   'fr': 'Demandes en attente'
               },
               'approve': {
                   'zh': '批准',
                   'ja': '承認',
                   'en': 'Approve',
                   'ru': 'Одобрить',
                   'ko': '승인',
                   'fr': 'Approuver'
               },
               'reject': {
                   'zh': '拒绝',
                   'ja': '却下',
                   'en': 'Reject',
                   'ru': 'Отклонить',
                   'ko': '거부',
                   'fr': 'Rejeter'
               },
               'application_reason': {
                   'zh': '申请理由：',
                   'ja': '申請理由：',
                   'en': 'Application Reason:',
                   'ru': 'Причина заявки:',
                   'ko': '신청 이유:',
                   'fr': 'Raison de la demande:'
               },
               'approved_requests': {
                   'zh': '已批准申请',
                   'ja': '承認済み申請',
                   'en': 'Approved Requests',
                   'ru': 'Одобренные заявки',
                   'ko': '승인된 신청',
                   'fr': 'Demandes approuvées'
               },
               'approved': {
                   'zh': '已批准',
                   'ja': '承認済み',
                   'en': 'Approved',
                   'ru': 'Одобрено',
                   'ko': '승인됨',
                   'fr': 'Approuvé'
               },
               'review_notes': {
                   'zh': '审核备注：',
                   'ja': '審査メモ：',
                   'en': 'Review Notes:',
                   'ru': 'Заметки проверки:',
                   'ko': '검토 메모:',
                   'fr': 'Notes de révision:'
               },
               'rejected_requests': {
                   'zh': '已拒绝申请',
                   'ja': '却下済み申請',
                   'en': 'Rejected Requests',
                   'ru': 'Отклоненные заявки',
                   'ko': '거부된 신청',
                   'fr': 'Demandes rejetées'
               },
               'rejected': {
                   'zh': '已拒绝',
                   'ja': '却下済み',
                   'en': 'Rejected',
                   'ru': 'Отклонено',
                   'ko': '거부됨',
                   'fr': 'Rejeté'
               },
               'rejection_reason': {
                   'zh': '拒绝理由：',
                   'ja': '却下理由：',
                   'en': 'Rejection Reason:',
                   'ru': 'Причина отклонения:',
                   'ko': '거부 이유:',
                   'fr': 'Raison du rejet:'
               },
               'no_admin_requests': {
                   'zh': '暂无管理员申请',
                   'ja': '管理者申請がありません',
                   'en': 'No admin requests',
                   'ru': 'Нет заявок администратора',
                   'ko': '관리자 신청이 없습니다',
                   'fr': 'Aucune demande d\'administrateur'
               },
               'approve_application': {
                   'zh': '批准申请',
                   'ja': '申請を承認',
                   'en': 'Approve Application',
                   'ru': 'Одобрить заявку',
                   'ko': '신청 승인',
                   'fr': 'Approuver la demande'
               },
               'review_notes_optional': {
                   'zh': '审核备注（可选）',
                   'ja': '審査メモ（オプション）',
                   'en': 'Review Notes (Optional)',
                   'ru': 'Заметки проверки (необязательно)',
                   'ko': '검토 메모 (선택사항)',
                   'fr': 'Notes de révision (optionnel)'
               },
               'cancel': {
                   'zh': '取消',
                   'ja': 'キャンセル',
                   'en': 'Cancel',
                   'ru': 'Отмена',
                   'ko': '취소',
                   'fr': 'Annuler'
               },
               'reject_application': {
                   'zh': '拒绝申请',
                   'ja': '申請を却下',
                   'en': 'Reject Application',
                   'ru': 'Отклонить заявку',
                   'ko': '신청 거부',
                   'fr': 'Rejeter la demande'
               },
               'rejection_reason_optional': {
                   'zh': '拒绝理由（可选）',
                   'ja': '却下理由（オプション）',
                   'en': 'Rejection Reason (Optional)',
                   'ru': 'Причина отклонения (необязательно)',
                   'ko': '거부 이유 (선택사항)',
                   'fr': 'Raison du rejet (optionnel)'
               },
               # index.html 需要的额外消息键
               'home': {
                   'zh': '首页',
                   'ja': 'ホーム',
                   'en': 'Home',
                   'ru': 'Главная',
                   'ko': '홈',
                   'fr': 'Accueil'
               },
               'hero_title': {
                   'zh': '基于兴趣的翻译平台',
                   'ja': '興味に基づいた翻訳プラットフォーム',
                   'en': 'Interest-Based Translation Platform',
                   'ru': 'Платформа переводов на основе интересов',
                   'ko': '관심사 기반 번역 플랫폼',
                   'fr': 'Plateforme de traduction basée sur les intérêts'
               },
               'hero_subtitle': {
                   'zh': '根据您的兴趣，翻译和分享来自世界各地的精彩内容',
                   'ja': 'あなたの興味に合わせて、世界中の素晴らしいコンテンツを翻訳し、共有しましょう',
                   'en': 'Translate and share amazing content from around the world based on your interests',
                   'ru': 'Переводите и делитесь удивительным контентом со всего мира на основе ваших интересов',
                   'ko': '당신의 관심사에 따라 전 세계의 놀라운 콘텐츠를 번역하고 공유하세요',
                   'fr': 'Traduisez et partagez du contenu incroyable du monde entier basé sur vos intérêts'
               },
               'get_started': {
                   'zh': '立即开始',
                   'ja': '今すぐ始める',
                   'en': 'Get Started',
                   'ru': 'Начать',
                   'ko': '시작하기',
                   'fr': 'Commencer'
               },
               'explore_works': {
                   'zh': '探索作品',
                   'ja': '作品を探す',
                   'en': 'Explore Works',
                   'ru': 'Исследовать работы',
                   'ko': '작품 탐색',
                   'fr': 'Explorer les œuvres'
               },
               'platform_features': {
                   'zh': '平台特色',
                   'ja': 'プラットフォームの特徴',
                   'en': 'Platform Features',
                   'ru': 'Особенности платформы',
                   'ko': '플랫폼 특징',
                   'fr': 'Fonctionnalités de la plateforme'
               },
               'interest_driven': {
                   'zh': '兴趣驱动',
                   'ja': '趣味ベース',
                   'en': 'Interest Driven',
                   'ru': 'Интерес',
                   'ko': '관심사 주도',
                   'fr': 'Intérêt'
               },
               'interest_driven_desc': {
                   'zh': '来自世界各地的翻译者、创作者和读者，因为相同的兴趣汇聚于此',
                   'ja': '世界中の翻訳者、クリエイター、読者が同じ興味で集まる',
                   'en': 'Translators, creators, and readers from around the world gather here because of shared interests',
                   'ru': 'Переводчики, создатели и читатели со всего мира собираются здесь из-за общих интересов',
                   'ko': '전 세계의 번역가, 크리에이터, 독자들이 같은 관심사로 모입니다',
                   'fr': 'Traducteurs, créateurs et lecteurs du monde entier se rassemblent ici grâce à des intérêts communs'
               },
               'completely_free': {
                   'zh': '完全免费',
                   'ja': '完全無料',
                   'en': 'Completely Free',
                   'ru': 'Полностью бесплатно',
                   'ko': '완전 무료',
                   'fr': 'Entièrement gratuit'
               },
               'completely_free_desc': {
                   'zh': '在这里，翻译者可以获得喜爱创作者的正式授权。而创作者也可以得到翻译者们为爱发电的翻译',
                   'ja': 'ここでは、翻訳者は好きなクリエイターの正式な許可を得ることができ、クリエイターも翻訳者たちの愛情あふれる翻訳を得ることができます',
                   'en': 'Here, translators can get official authorization from their favorite creators, and creators can receive passionate translations from translators',
                   'ru': 'Здесь переводчики могут получить официальное разрешение от своих любимых создателей, а создатели могут получить страстные переводы от переводчиков',
                   'ko': '여기서 번역가들은 좋아하는 크리에이터의 공식 허가를 받을 수 있고, 크리에이터들도 번역가들의 열정적인 번역을 받을 수 있습니다',
                   'fr': 'Ici, les traducteurs peuvent obtenir l\'autorisation officielle de leurs créateurs préférés, et les créateurs peuvent recevoir des traductions passionnées des traducteurs'
               },
               'quality_assurance': {
                   'zh': '质量保证',
                   'ja': '品質保証',
                   'en': 'Quality Assurance',
                   'ru': 'Контроль качества',
                   'ko': '품질 보증',
                   'fr': 'Assurance qualité'
               },
               'quality_assurance_desc': {
                   'zh': '通过高水平的翻译者和读者的点评保证翻译质量，刚入门的翻译家也能在此获得成长',
                   'ja': '高レベルの翻訳者と読者のレビューによる翻訳品質の保証、初心者翻訳者もここで成長できます',
                   'en': 'Translation quality guaranteed through high-level translators and reader reviews, beginner translators can also grow here',
                   'ru': 'Качество перевода гарантируется высококлассными переводчиками и отзывами читателей, начинающие переводчики также могут расти здесь',
                   'ko': '고수준의 번역가와 독자들의 리뷰를 통한 번역 품질 보장, 초보 번역가들도 여기서 성장할 수 있습니다',
                   'fr': 'Qualité de traduction garantie par des traducteurs de haut niveau et des critiques de lecteurs, les traducteurs débutants peuvent aussi grandir ici'
               },
               'popular_works': {
                   'zh': '最热作品',
                   'ja': '人気の作品',
                   'en': 'Popular Works',
                   'ru': 'Популярные работы',
                   'ko': '인기 작품',
                   'fr': 'Œuvres populaires'
               },
               'view_all': {
                   'zh': '查看全部',
                   'ja': 'すべて見る',
                   'en': 'View All',
                   'ru': 'Посмотреть все',
                   'ko': '모두 보기',
                   'fr': 'Voir tout'
               },
               'recent_works': {
                   'zh': '最新作品',
                   'ja': '最新の作品',
                   'en': 'Recent Works',
                   'ru': 'Недавние работы',
                   'ko': '최근 작품',
                   'fr': 'Œuvres récentes'
               },
               'get_started_today': {
                   'zh': '立即开始',
                   'ja': '今すぐ始めましょう',
                   'en': 'Get Started Today',
                   'ru': 'Начните сегодня',
                   'ko': '오늘 시작하세요',
                   'fr': 'Commencez aujourd\'hui'
               },
               'get_started_today_desc': {
                   'zh': '发现来自世界各地的精彩内容，加入我们的翻译社区',
                   'ja': '世界中の素晴らしいコンテンツを発見し、翻訳コミュニティに参加しましょう',
                   'en': 'Discover amazing content from around the world and join our translation community',
                   'ru': 'Откройте для себя удивительный контент со всего мира и присоединяйтесь к нашему сообществу переводчиков',
                   'ko': '전 세계의 놀라운 콘텐츠를 발견하고 번역 커뮤니티에 참여하세요',
                   'fr': 'Découvrez du contenu incroyable du monde entier et rejoignez notre communauté de traduction'
               },
               # work_detail.html 需要的状态消息键
               'status_draft': {
                   'zh': '草稿',
                   'ja': '下書き',
                   'en': 'Draft',
                   'ru': 'Черновик',
                   'ko': '초안',
                   'fr': 'Brouillon'
               },
               'status_submitted': {
                   'zh': '已提交',
                   'ja': '提出済み',
                   'en': 'Submitted',
                   'ru': 'Отправлено',
                   'ko': '제출됨',
                   'fr': 'Soumis'
               },
               'status_approved': {
                   'zh': '已通过',
                   'ja': '承認済み',
                   'en': 'Approved',
                   'ru': 'Одобрено',
                   'ko': '승인됨',
                   'fr': 'Approuvé'
               },
               'status_rejected': {
                   'zh': '已拒绝',
                   'ja': '却下',
                   'en': 'Rejected',
                   'ru': 'Отклонено',
                   'ko': '거부됨',
                   'fr': 'Rejeté'
               },
               # change_password.html 需要的消息键
               'change_password': {
                   'zh': '修改密码',
                   'ja': 'パスワード変更',
                   'en': 'Change Password',
                   'ru': 'Изменить пароль',
                   'ko': '비밀번호 변경',
                   'fr': 'Changer le mot de passe'
               },
               'current_password': {
                   'zh': '当前密码',
                   'ja': '現在のパスワード',
                   'en': 'Current Password',
                   'ru': 'Текущий пароль',
                   'ko': '현재 비밀번호',
                   'fr': 'Mot de passe actuel'
               },
               'new_password': {
                   'zh': '新密码',
                   'ja': '新しいパスワード',
                   'en': 'New Password',
                   'ru': 'Новый пароль',
                   'ko': '새 비밀번호',
                   'fr': 'Nouveau mot de passe'
               },
               'confirm_new_password': {
                   'zh': '确认新密码',
                   'ja': '新しいパスワード確認',
                   'en': 'Confirm New Password',
                   'ru': 'Подтвердить новый пароль',
                   'ko': '새 비밀번호 확인',
                   'fr': 'Confirmer le nouveau mot de passe'
               },
               'change_password_btn': {
                   'zh': '修改密码',
                   'ja': 'パスワードを変更',
                   'en': 'Change Password',
                   'ru': 'Изменить пароль',
                   'ko': '비밀번호 변경',
                   'fr': 'Changer le mot de passe'
               },
               'back': {
                   'zh': '返回',
                   'ja': '戻る',
                   'en': 'Back',
                   'ru': 'Назад',
                   'ko': '돌아가기',
                   'fr': 'Retour'
               },
               'password_mismatch': {
                   'zh': '新密码和确认密码不匹配',
                   'ja': '新しいパスワードと確認パスワードが一致しません',
                   'en': 'New password and confirmation password do not match',
                   'ru': 'Новый пароль и подтверждение пароля не совпадают',
                   'ko': '새 비밀번호와 확인 비밀번호가 일치하지 않습니다',
                   'fr': 'Le nouveau mot de passe et la confirmation ne correspondent pas'
               },
               'password_min_length': {
                   'zh': '密码长度至少为8位',
                   'ja': 'パスワードは8文字以上である必要があります',
                   'en': 'Password must be at least 8 characters long',
                   'ru': 'Пароль должен содержать не менее 8 символов',
                   'ko': '비밀번호는 최소 8자 이상이어야 합니다',
                   'fr': 'Le mot de passe doit contenir au moins 8 caractères'
               },
               # edit_translation.html 需要的消息键
               'save_changes': {
                   'zh': '保存修改',
                   'ja': '変更を保存',
                   'en': 'Save Changes',
                   'ru': 'Сохранить изменения',
                   'ko': '변경사항 저장',
                   'fr': 'Enregistrer les modifications'
               },
               'delete_translation': {
                   'zh': '删除翻译',
                   'ja': '翻訳を削除',
                   'en': 'Delete Translation',
                   'ru': 'Удалить перевод',
                   'ko': '번역 삭제',
                   'fr': 'Supprimer la traduction'
               },
               'edit_tips': {
                   'zh': '编辑提示',
                   'ja': '編集ヒント',
                   'en': 'Edit Tips',
                   'ru': 'Советы по редактированию',
                   'ko': '편집 팁',
                   'fr': 'Conseils d\'édition'
               },
               'edit_tip_1': {
                   'zh': '修改后翻译状态将重置为"草稿"',
                   'ja': '変更後、翻訳ステータスは「下書き」にリセットされます',
                   'en': 'Translation status will be reset to "Draft" after modification',
                   'ru': 'Статус перевода будет сброшен на "Черновик" после изменения',
                   'ko': '수정 후 번역 상태가 "초안"으로 재설정됩니다',
                   'fr': 'Le statut de traduction sera remis à "Brouillon" après modification'
               },
               'edit_tip_2': {
                   'zh': '保持原文的语调和风格',
                   'ja': '原文の語調とスタイルを保持する',
                   'en': 'Maintain the tone and style of the original text',
                   'ru': 'Сохраняйте тон и стиль оригинального текста',
                   'ko': '원문의 어조와 스타일을 유지하세요',
                   'fr': 'Maintenez le ton et le style du texte original'
               },
               'edit_tip_3': {
                   'zh': '确保翻译准确无误',
                   'ja': '翻訳の正確性を確保する',
                   'en': 'Ensure translation accuracy',
                   'ru': 'Обеспечьте точность перевода',
                   'ko': '번역의 정확성을 보장하세요',
                   'fr': 'Assurez-vous de la précision de la traduction'
               },
               'edit_tip_4': {
                   'zh': '注意文化差异和表达习惯',
                   'ja': '文化的な違いと表現習慣に注意する',
                   'en': 'Pay attention to cultural differences and expression habits',
                   'ru': 'Обратите внимание на культурные различия и привычки выражения',
                   'ko': '문화적 차이와 표현 습관에 주의하세요',
                   'fr': 'Faites attention aux différences culturelles et aux habitudes d\'expression'
               },
               'edit_tip_5': {
                   'zh': '保持段落结构和格式',
                   'ja': '段落構造とフォーマットを保持する',
                   'en': 'Maintain paragraph structure and formatting',
                   'ru': 'Сохраняйте структуру абзацев и форматирование',
                   'ko': '단락 구조와 형식을 유지하세요',
                   'fr': 'Maintenez la structure des paragraphes et le formatage'
               },
               'edit_tools': {
                   'zh': '编辑工具',
                   'ja': '編集ツール',
                   'en': 'Edit Tools',
                   'ru': 'Инструменты редактирования',
                   'ko': '편집 도구',
                   'fr': 'Outils d\'édition'
               },
               'copy_original': {
                   'zh': '复制原文',
                   'ja': '原文をコピー',
                   'en': 'Copy Original',
                   'ru': 'Скопировать оригинал',
                   'ko': '원문 복사',
                   'fr': 'Copier l\'original'
               },
               'clear_translation': {
                   'zh': '清空翻译',
                   'ja': '翻訳をクリア',
                   'en': 'Clear Translation',
                   'ru': 'Очистить перевод',
                   'ko': '번역 지우기',
                   'fr': 'Effacer la traduction'
               },
               'word_count': {
                   'zh': '字数统计',
                   'ja': '文字数統計',
                   'en': 'Word Count',
                   'ru': 'Подсчет слов',
                   'ko': '단어 수 통계',
                   'fr': 'Comptage de mots'
               },
               'statistics': {
                   'zh': '统计信息',
                   'ja': '統計情報',
                   'en': 'Statistics',
                   'ru': 'Статистика',
                   'ko': '통계 정보',
                   'fr': 'Statistiques'
               },
               'original_characters': {
                   'zh': '原文字符',
                   'ja': '原文文字',
                   'en': 'Original Characters',
                   'ru': 'Символы оригинала',
                   'ko': '원문 문자',
                   'fr': 'Caractères originaux'
               },
               'translation_characters': {
                   'zh': '翻译字符',
                   'ja': '翻訳文字',
                   'en': 'Translation Characters',
                   'ru': 'Символы перевода',
                   'ko': '번역 문자',
                   'fr': 'Caractères de traduction'
               },
        # 个人信息编辑界面消息
        'bio': {
            'zh': '个人简介',
            'ja': '自己紹介',
            'en': 'Bio',
            'ru': 'Биография',
            'ko': '자기소개',
            'fr': 'Biographie'
        },
        'bio_placeholder': {
            'zh': '请输入个人简介（例如：翻译工作者，擅长中文、日文、英文翻译）',
            'ja': '自己紹介を入力してください（例：翻訳者として活動中。日本語、英語、中国語ができます）',
            'en': 'Enter your bio (e.g., Translator specializing in Chinese, Japanese, and English)',
            'ru': 'Введите биографию (например: Переводчик, специализирующийся на китайском, японском и английском языках)',
            'ko': '자기소개를 입력하세요 (예: 중국어, 일본어, 영어 번역 전문가)',
            'fr': 'Entrez votre biographie (ex: Traducteur spécialisé en chinois, japonais et anglais)'
        },
        'bio_help_text': {
            'zh': '请描述您的语言能力和专业领域',
            'ja': 'あなたの言語能力や専門分野について書いてください',
            'en': 'Please describe your language skills and areas of expertise',
            'ru': 'Пожалуйста, опишите ваши языковые навыки и области экспертизы',
            'ko': '언어 능력과 전문 분야를 설명해 주세요',
            'fr': 'Veuillez décrire vos compétences linguistiques et domaines d\'expertise'
        },
        'avatar_help_text': {
            'zh': '请选择图片文件（JPG、PNG、GIF）',
            'ja': '画像ファイルを選択してください（JPG、PNG、GIF）',
            'en': 'Please select an image file (JPG, PNG, GIF)',
            'ru': 'Пожалуйста, выберите файл изображения (JPG, PNG, GIF)',
            'ko': '이미지 파일을 선택해 주세요 (JPG, PNG, GIF)',
            'fr': 'Veuillez sélectionner un fichier image (JPG, PNG, GIF)'
        },
        'preferred_language_help_text': {
            'zh': '请选择网站显示语言',
            'ja': 'サイトの表示言語を選択してください',
            'en': 'Please select the site display language',
            'ru': 'Пожалуйста, выберите язык отображения сайта',
            'ko': '사이트 표시 언어를 선택해 주세요',
            'fr': 'Veuillez sélectionner la langue d\'affichage du site'
        },
        'save_changes': {
            'zh': '保存修改',
            'ja': '変更を保存',
            'en': 'Save Changes',
            'ru': 'Сохранить изменения',
            'ko': '변경사항 저장',
            'fr': 'Enregistrer les modifications'
        },
        # work_detail.html 需要的消息键
        'reject_translation': {
            'zh': '拒绝翻译',
            'ja': '翻訳を却下',
            'en': 'Reject Translation',
            'ru': 'Отклонить перевод',
            'ko': '번역 거부',
            'fr': 'Rejeter la traduction'
        },
        'reject_reason': {
            'zh': '拒绝理由（可选）',
            'ja': '却下理由（オプション）',
            'en': 'Rejection Reason (Optional)',
            'ru': 'Причина отклонения (необязательно)',
            'ko': '거부 이유 (선택사항)',
            'fr': 'Raison du rejet (optionnel)'
        },
        'reject_reason_placeholder': {
            'zh': '请输入拒绝翻译的理由...',
            'ja': '翻訳を却下する理由を入力してください...',
            'en': 'Please enter the reason for rejecting the translation...',
            'ru': 'Пожалуйста, введите причину отклонения перевода...',
            'ko': '번역을 거부하는 이유를 입력하세요...',
            'fr': 'Veuillez entrer la raison du rejet de la traduction...'
        },
        'edit_reason': {
            'zh': '编辑理由',
            'ja': '編集理由',
            'en': 'Edit Reason',
            'ru': 'Причина редактирования',
            'ko': '편집 이유',
            'fr': 'Raison de la modification'
        },
        'edit_reason_placeholder': {
            'zh': '请输入编辑理由...',
            'ja': '編集理由を入力してください...',
            'en': 'Please enter the edit reason...',
            'ru': 'Пожалуйста, введите причину редактирования...',
            'ko': '편집 이유를 입력하세요...',
            'fr': 'Veuillez entrer la raison de la modification...'
        },
        'notify_creator_and_translator': {
            'zh': '此操作将通知作品作者和翻译者。',
            'ja': 'この操作は作品の作者と翻訳者に通知します。',
            'en': 'This action will notify the creator and translator.',
            'ru': 'Это действие уведомит автора и переводчика.',
            'ko': '이 작업은 작품의 작성자와 번역자에게 알림을 보냅니다.',
            'fr': 'Cette action informera le créateur et le traducteur.'
        },
        'delete_reason': {
            'zh': '删除理由',
            'ja': '削除理由',
            'en': 'Delete Reason',
            'ru': 'Причина удаления',
            'ko': '삭제 이유',
            'fr': 'Raison de la suppression'
        },
        'delete_reason_placeholder': {
            'zh': '请输入删除理由...',
            'ja': '削除理由を入力してください...',
            'en': 'Please enter the delete reason...',
            'ru': 'Пожалуйста, введите причину удаления...',
            'ko': '삭제 이유를 입력하세요...',
            'fr': 'Veuillez entrer la raison de la suppression...'
        },
        'comment_required': {
            'zh': '请输入评论内容',
            'ja': 'コメント内容を入力してください',
            'en': 'Please enter comment content',
            'ru': 'Пожалуйста, введите содержание комментария',
            'ko': '댓글 내용을 입력하세요',
            'fr': 'Veuillez entrer le contenu du commentaire'
        },
        'translation_not_found': {
            'zh': '未找到翻译',
            'ja': '翻訳が見つかりません',
            'en': 'Translation not found',
            'ru': 'Перевод не найден',
            'ko': '번역을 찾을 수 없습니다',
            'fr': 'Traduction introuvable'
        },
        'comment_submit_failed': {
            'zh': '评论提交失败，请重试',
            'ja': 'コメントの送信に失敗しました。再試行してください',
            'en': 'Comment submission failed, please try again',
            'ru': 'Отправка комментария не удалась, попробуйте еще раз',
            'ko': '댓글 제출에 실패했습니다. 다시 시도해 주세요',
            'fr': 'Échec de la soumission du commentaire, veuillez réessayer'
        },
        'no_comments_yet': {
            'zh': '暂无评论',
            'ja': 'まだコメントがありません',
            'en': 'No comments yet',
            'ru': 'Пока нет комментариев',
            'ko': '아직 댓글이 없습니다',
            'fr': 'Aucun commentaire pour le moment'
        },
        'delete_comment': {
            'zh': '删除',
            'ja': '削除',
            'en': 'Delete',
            'ru': 'Удалить',
            'ko': '삭제',
            'fr': 'Supprimer'
        },
        'operation_failed': {
            'zh': '操作失败，请重试',
            'ja': '操作に失敗しました。再試行してください',
            'en': 'Operation failed, please try again',
            'ru': 'Операция не удалась, попробуйте еще раз',
            'ko': '작업에 실패했습니다. 다시 시도해 주세요',
            'fr': 'L\'opération a échoué, veuillez réessayer'
        },
        # apply_admin.html 需要的消息键
        'admin_application': {
            'zh': '管理员申请',
            'ja': '管理者申請',
            'en': 'Admin Application',
            'ru': 'Заявка на администратора',
            'ko': '관리자 신청',
            'fr': 'Demande d\'administrateur'
        },
        'application_description': {
            'zh': '申请说明',
            'ja': '申請について',
            'en': 'Application Description',
            'ru': 'Описание заявки',
            'ko': '신청 설명',
            'fr': 'Description de la demande'
        },
        'admin_application_reason': {
            'zh': '申请管理员权限需要详细说明以下理由：',
            'ja': '管理者権限を申請するには、以下の理由を詳しく説明してください：',
            'en': 'To apply for admin privileges, please explain the following reasons in detail:',
            'ru': 'Для подачи заявки на права администратора, пожалуйста, подробно объясните следующие причины:',
            'ko': '관리자 권한을 신청하려면 다음 이유를 자세히 설명해 주세요:',
            'fr': 'Pour demander les privilèges d\'administrateur, veuillez expliquer en détail les raisons suivantes:'
        },
        'why_admin_reason': {
            'zh': '为什么想要成为管理员',
            'ja': 'なぜ管理者になりたいのか',
            'en': 'Why you want to become an admin',
            'ru': 'Почему вы хотите стать администратором',
            'ko': '왜 관리자가 되고 싶은지',
            'fr': 'Pourquoi vous voulez devenir administrateur'
        },
        'what_contribution': {
            'zh': '能够做出什么样的贡献',
            'ja': 'どのような貢献ができるのか',
            'en': 'What kind of contribution you can make',
            'ru': 'Какой вклад вы можете внести',
            'ko': '어떤 기여를 할 수 있는지',
            'fr': 'Quel type de contribution vous pouvez apporter'
        },
        'how_improve_community': {
            'zh': '如何致力于改善社区',
            'ja': 'コミュニティの改善にどのように取り組むか',
            'en': 'How you will work to improve the community',
            'ru': 'Как вы будете работать над улучшением сообщества',
            'ko': '커뮤니티 개선을 위해 어떻게 노력할 것인지',
            'fr': 'Comment vous travaillerez à améliorer la communauté'
        },
        'application_reason': {
            'zh': '申请理由',
            'ja': '申請理由',
            'en': 'Application Reason',
            'ru': 'Причина заявки',
            'ko': '신청 이유',
            'fr': 'Raison de la demande'
        },
        'application_reason_placeholder': {
            'zh': '请详细填写申请理由...',
            'ja': '申請理由を詳しく記入してください...',
            'en': 'Please fill in the application reason in detail...',
            'ru': 'Пожалуйста, подробно заполните причину заявки...',
            'ko': '신청 이유를 자세히 작성해 주세요...',
            'fr': 'Veuillez remplir en détail la raison de la demande...'
        },
        'submit_application': {
            'zh': '提交申请',
            'ja': '申請を提出',
            'en': 'Submit Application',
            'ru': 'Отправить заявку',
            'ko': '신청 제출',
            'fr': 'Soumettre la demande'
        },
        # apply_reviewer.html 需要的消息键
        'reviewer_application': {
            'zh': '校正者申请',
            'ja': '校正者申請',
            'en': 'Reviewer Application',
            'ru': 'Заявка на рецензента',
            'ko': '교정자 신청',
            'fr': 'Demande de correcteur'
        },
        'reviewer_role': {
            'zh': '校正者的职责：',
            'ja': '校正者の役割：',
            'en': 'Reviewer Role:',
            'ru': 'Роль рецензента:',
            'ko': '교정자의 역할:',
            'fr': 'Rôle du correcteur:'
        },
        'reviewer_role_1': {
            'zh': '对翻译者的翻译内容进行校正和改进',
            'ja': '翻訳者の翻訳内容を校正・改善する',
            'en': 'Review and improve translators\' translation content',
            'ru': 'Рецензировать и улучшать содержание переводов переводчиков',
            'ko': '번역가의 번역 내용을 교정하고 개선합니다',
            'fr': 'Réviser et améliorer le contenu des traductions des traducteurs'
        },
        'reviewer_role_2': {
            'zh': '为翻译质量提升做出贡献',
            'ja': '翻訳の品質向上に貢献する',
            'en': 'Contribute to improving translation quality',
            'ru': 'Вносить вклад в улучшение качества перевода',
            'ko': '번역 품질 향상에 기여합니다',
            'fr': 'Contribuer à l\'amélioration de la qualité de traduction'
        },
        'reviewer_role_3': {
            'zh': '其他用户可以对校正内容进行点赞',
            'ja': '他のユーザーが校正内容にいいねできる',
            'en': 'Other users can like the review content',
            'ru': 'Другие пользователи могут лайкать содержание рецензии',
            'ko': '다른 사용자가 교정 내용에 좋아요를 할 수 있습니다',
            'fr': 'D\'autres utilisateurs peuvent aimer le contenu de révision'
        },
        'reviewer_role_4': {
            'zh': '为翻译社区发展做出贡献',
            'ja': '翻訳コミュニティの発展に寄与する',
            'en': 'Contribute to the development of the translation community',
            'ru': 'Вносить вклад в развитие сообщества переводчиков',
            'ko': '번역 커뮤니티 발전에 기여합니다',
            'fr': 'Contribuer au développement de la communauté de traduction'
        },
        'reviewer_responsibility': {
            'zh': '校正者的责任：',
            'ja': '校正者の責任：',
            'en': 'Reviewer Responsibilities:',
            'ru': 'Обязанности рецензента:',
            'ko': '교정자의 책임:',
            'fr': 'Responsabilités du correcteur:'
        },
        'reviewer_resp_1': {
            'zh': '提供准确和适当的校正',
            'ja': '正確で適切な校正を提供する',
            'en': 'Provide accurate and appropriate corrections',
            'ru': 'Предоставлять точные и подходящие исправления',
            'ko': '정확하고 적절한 교정을 제공합니다',
            'fr': 'Fournir des corrections précises et appropriées'
        },
        'reviewer_resp_2': {
            'zh': '提供建设性和有用的反馈',
            'ja': '建設的で役立つフィードバックを提供する',
            'en': 'Provide constructive and useful feedback',
            'ru': 'Предоставлять конструктивную и полезную обратную связь',
            'ko': '건설적이고 유용한 피드백을 제공합니다',
            'fr': 'Fournir des commentaires constructifs et utiles'
        },
        'reviewer_resp_3': {
            'zh': '尊重翻译者的努力',
            'ja': '翻訳者の努力を尊重する',
            'en': 'Respect the efforts of translators',
            'ru': 'Уважать усилия переводчиков',
            'ko': '번역가의 노력을 존중합니다',
            'fr': 'Respecter les efforts des traducteurs'
        },
        'reviewer_resp_4': {
            'zh': '遵守社区规则',
            'ja': 'コミュニティのルールに従う',
            'en': 'Follow community rules',
            'ru': 'Соблюдать правила сообщества',
            'ko': '커뮤니티 규칙을 따릅니다',
            'fr': 'Suivre les règles de la communauté'
        },
        'become_reviewer': {
            'zh': '成为校正者',
            'ja': '校正者になる',
            'en': 'Become a Reviewer',
            'ru': 'Стать рецензентом',
            'ko': '교정자가 되기',
            'fr': 'Devenir correcteur'
        },
        # apply_translator.html 需要的消息键
        'translator_test': {
            'zh': '翻译者测试',
            'ja': '翻訳者テスト',
            'en': 'Translator Test',
            'ru': 'Тест переводчика',
            'ko': '번역가 테스트',
            'fr': 'Test de traducteur'
        },
        'test_not_ready': {
            'zh': '目前测验内容尚未准备，点击下方确认按钮即可成为翻译者。',
            'ja': '現在テスト内容はまだ準備されていません。下の確認ボタンをクリックすると翻訳者になれます。',
            'en': 'The test content is not ready yet. Click the confirm button below to become a translator.',
            'ru': 'Содержание теста пока не готово. Нажмите кнопку подтверждения ниже, чтобы стать переводчиком.',
            'ko': '현재 테스트 내용이 아직 준비되지 않았습니다. 아래 확인 버튼을 클릭하면 번역가가 될 수 있습니다.',
            'fr': 'Le contenu du test n\'est pas encore prêt. Cliquez sur le bouton de confirmation ci-dessous pour devenir traducteur.'
        },
        # apply_reviewer.html 需要的消息键
        'reviewer_test': {
            'zh': '校正者测试',
            'ja': '校正者テスト',
            'en': 'Reviewer Test',
            'ru': 'Тест рецензента',
            'ko': '교정자 테스트',
            'fr': 'Test de correcteur'
        },
        'reviewer_test_not_ready': {
            'zh': '目前测验内容尚未准备，点击下方确认按钮即可成为校正者。',
            'ja': '現在テスト内容はまだ準備されていません。下の確認ボタンをクリックすると校正者になれます。',
            'en': 'The test content is not ready yet. Click the confirm button below to become a reviewer.',
            'ru': 'Содержание теста пока не готово. Нажмите кнопку подтверждения ниже, чтобы стать рецензентом.',
            'ko': '현재 테스트 내용이 아직 준비되지 않았습니다. 아래 확인 버튼을 클릭하면 교정자가 될 수 있습니다.',
            'fr': 'Le contenu du test n\'est pas encore prêt. Cliquez sur le bouton de confirmation ci-dessous pour devenir correcteur.'
        },
        'confirm': {
            'zh': '确认',
            'ja': '確認',
            'en': 'Confirm',
            'ru': 'Подтвердить',
            'ko': '확인',
            'fr': 'Confirmer'
        },
        }
    
    # 获取消息模板
    message_template = messages.get(key, {}).get(lang, messages.get(key, {}).get('zh', key))
    
    # 只对好友请求相关消息进行调试
    if key in ['friend_request_accepted', 'friend_request_rejected', 'friend_request_sent']:
        print(f"DEBUG get_message: key = {key}, lang = {lang}")
        print(f"DEBUG get_message: message_template = {message_template}")
        print(f"DEBUG get_message: kwargs = {kwargs}")
    
    # 如果消息模板包含格式化占位符，则进行格式化
    if isinstance(message_template, str) and kwargs:
        try:
            formatted_message = message_template.format(**kwargs)
            if key in ['friend_request_accepted', 'friend_request_rejected', 'friend_request_sent']:
                print(f"DEBUG get_message: formatted_message = {formatted_message}")
            return formatted_message
        except (KeyError, ValueError) as e:
            # 如果格式化失败，返回原始模板
            if key in ['friend_request_accepted', 'friend_request_rejected', 'friend_request_sent']:
                print(f"DEBUG get_message: formatting failed with error: {e}")
            return message_template
    
    return message_template

# 根据用户偏好语言生成系统消息
def get_system_message(message_type, user_id, **kwargs):
    """根据用户偏好语言生成系统消息"""
    user = User.query.get(user_id)
    # 优先使用用户的语言偏好，如果没有则使用会话语言
    lang = getattr(user, 'preferred_language', 'zh') if user else session.get('lang', 'zh')
    
    system_messages = {
        'translation_request_to_author': {
            'zh': f'用户 {kwargs.get("translator_name", "")} 申请翻译你的作品《{kwargs.get("work_title", "")}》，期待/要求：{kwargs.get("expectation", "无")}，请前往作品详情页同意或拒绝。',
            'ja': f'ユーザー {kwargs.get("translator_name", "")} があなたの作品《{kwargs.get("work_title", "")}》の翻訳を申請しました。期待/要求：{kwargs.get("expectation", "なし")}。作品詳細ページで承認または拒否してください。',
            'en': f'User {kwargs.get("translator_name", "")} has requested to translate your work "{kwargs.get("work_title", "")}". Expectation/Requirements: {kwargs.get("expectation", "None")}. Please go to the work detail page to approve or reject.',
            'ru': f'Пользователь {kwargs.get("translator_name", "")} запросил перевод вашей работы "{kwargs.get("work_title", "")}". Ожидания/Требования: {kwargs.get("expectation", "Нет")}. Пожалуйста, перейдите на страницу деталей работы для одобрения или отклонения.',
            'ko': f'사용자 {kwargs.get("translator_name", "")}가 귀하의 작품 "{kwargs.get("work_title", "")}" 번역을 요청했습니다. 기대/요구사항: {kwargs.get("expectation", "없음")}. 작품 상세 페이지에서 승인 또는 거부해 주세요.',
            'fr': f'L\'utilisateur {kwargs.get("translator_name", "")} a demandé à traduire votre œuvre "{kwargs.get("work_title", "")}". Attentes/Exigences: {kwargs.get("expectation", "Aucune")}. Veuillez aller à la page de détails de l\'œuvre pour approuver ou rejeter.'
        },
        'translation_request_to_translator': {
            'en': f'You have successfully submitted a translation request for the work "{kwargs.get("work_title", "")}". Waiting for author processing.',
            'ru': f'Вы успешно отправили запрос на перевод работы "{kwargs.get("work_title", "")}". Ожидание обработки автором.',
            'ko': f'작품 "{kwargs.get("work_title", "")}" 번역 요청을 성공적으로 제출했습니다. 저자 처리 대기 중입니다.',
            'fr': f'Vous avez soumis avec succès une demande de traduction pour l\'œuvre "{kwargs.get("work_title", "")}". En attente du traitement par l\'auteur.',
            'zh': f'作品《{kwargs.get("work_title", "")}》的翻译申请，等待作者处理。',
            'ja': f'作品《{kwargs.get("work_title", "")}》の翻訳申請を正常に提出しました。作者の処理をお待ちください。'
        },
        'request_approved_to_translator': {
            'en': f'Your translation request has been approved. Work: {kwargs.get("work_title", "")}',
            'ru': f'Ваш запрос на перевод был одобрен. Работа: {kwargs.get("work_title", "")}',
            'ko': f'번역 요청이 승인되었습니다. 작품: {kwargs.get("work_title", "")}',
            'fr': f'Votre demande de traduction a été approuvée. Œuvre: {kwargs.get("work_title", "")}',
            'zh': f'您的翻译请求已获得批准。作品：{kwargs.get("work_title", "")}',
            'ja': f'翻訳リクエストが承認されました。作品：{kwargs.get("work_title", "")}'
        },
        'request_rejected_to_translator': {
            'en': f'Your translation request was rejected. Work: {kwargs.get("work_title", "")}',
            'ru': f'Ваш запрос на перевод был отклонен. Работа: {kwargs.get("work_title", "")}',
            'ko': f'번역 요청이 거부되었습니다. 작품: {kwargs.get("work_title", "")}',
            'fr': f'Votre demande de traduction a été rejetée. Œuvre: {kwargs.get("work_title", "")}',
            'zh': f'您的翻译请求被拒绝了。作品：{kwargs.get("work_title", "")}',
            'ja': f'翻訳リクエストが拒否されました。作品：{kwargs.get("work_title", "")}'
        },
        'trusted_by_author': {
            'en': f'User {kwargs.get("author_name", "")} has set you as a trusted translator.',
            'ru': f'Пользователь {kwargs.get("author_name", "")} назначил вас доверенным переводчиком.',
            'ko': f'사용자 {kwargs.get("author_name", "")}가 귀하를 신뢰할 수 있는 번역자로 설정했습니다.',
            'fr': f'L\'utilisateur {kwargs.get("author_name", "")} vous a défini comme traducteur de confiance.',
            'zh': f'用户 {kwargs.get("author_name", "")} 已将您设为信赖的翻译者。',
            'ja': f'ユーザー {kwargs.get("author_name", "")} があなたを信頼できる翻訳者として設定しました。'
        },
        'untrusted_by_author': {
            'en': f'User {kwargs.get("author_name", "")} has removed you from trusted translators.',
            'ru': f'Пользователь {kwargs.get("author_name", "")} удалил вас из доверенных переводчиков.',
            'ko': f'사용자 {kwargs.get("author_name", "")}가 신뢰할 수 있는 번역자 목록에서 귀하를 제거했습니다.',
            'fr': f'L\'utilisateur {kwargs.get("author_name", "")} vous a retiré des traducteurs de confiance.',
            'zh': f'用户 {kwargs.get("author_name", "")} 已取消对您的信赖。',
            'ja': f'ユーザー {kwargs.get("author_name", "")} があなたへの信頼を解除しました。'
        },
        'friend_request_sent': {
            'en': 'User {sender_name} has sent you a friend request.',
            'ru': 'Пользователь {sender_name} отправил вам запрос в друзья.',
            'ko': '사용자 {sender_name}가 귀하에게 친구 요청을 보냈습니다.',
            'fr': 'L\'utilisateur {sender_name} vous a envoyé une demande d\'ami.',
            'zh': '用户 {sender_name} 向您发送了好友请求。',
            'ja': 'ユーザー {sender_name} があなたに友達リクエストを送信しました。'
        },
        'friend_request_accepted': {
            'en': 'Your friend request has been accepted by {receiver_name}.',
            'ru': 'Ваш запрос в друзья был принят пользователем {receiver_name}.',
            'ko': '친구 요청이 {receiver_name}에 의해 승인되었습니다.',
            'fr': 'Votre demande d\'ami a été acceptée par {receiver_name}.',
            'zh': '用户 {receiver_name} 已接受您的好友请求。',
            'ja': 'あなたの友達リクエストが {receiver_name} によって承認されました。'
        },
        'friend_request_rejected': {
            'en': 'Your friend request has been rejected by {receiver_name}.',
            'ru': 'Ваш запрос в друзья был отклонен пользователем {receiver_name}.',
            'ko': '친구 요청이 {receiver_name}에 의해 거부되었습니다.',
            'fr': 'Votre demande d\'ami a été rejetée par {receiver_name}.',
            'zh': '用户 {receiver_name} 拒绝了您的好友请求。',
            'ja': 'ユーザー {receiver_name} があなたの友達リクエストを拒否しました。'
        },
        'translation_accepted_by_author': {
            'en': f'Congratulations! Your translation "{kwargs.get("work_title", "")}" has been accepted by the author and liked!',
            'ru': f'Поздравляем! Ваш перевод "{kwargs.get("work_title", "")}" был принят автором и получил лайк!',
            'ko': f'축하합니다! 귀하의 번역 "{kwargs.get("work_title", "")}"이 저자에 의해 승인되고 좋아요를 받았습니다!',
            'fr': f'Félicitations ! Votre traduction "{kwargs.get("work_title", "")}" a été acceptée par l\'auteur et aimée !',
            'zh': f'恭喜！您的翻译《{kwargs.get("work_title", "")}》已被作者接受并点赞！',
            'ja': f'おめでとうございます！あなたの翻訳《{kwargs.get("work_title", "")}》が作者によって承認され、いいねされました！'
        },
        'like_milestone': {
            'en': f'Congratulations! Your {kwargs.get("content_type", "")} has received {kwargs.get("like_count", "")} likes!',
            'ru': f'Поздравляем! Ваш {kwargs.get("content_type", "")} получил {kwargs.get("like_count", "")} лайков!',
            'ko': f'축하합니다! 귀하의 {kwargs.get("content_type", "")}가 {kwargs.get("like_count", "")}개의 좋아요를 받았습니다!',
            'fr': f'Félicitations ! Votre {kwargs.get("content_type", "")} a reçu {kwargs.get("like_count", "")} j\'aime !',
            'zh': f'恭喜！您的{kwargs.get("content_type", "")}获得了{kwargs.get("like_count", "")}个点赞！',
            'ja': f'おめでとうございます！あなたの{kwargs.get("content_type", "")}が{kwargs.get("like_count", "")}個のいいねを獲得しました！'
        },
        'translation_submitted_to_author': {
            'en': f'User {kwargs.get("translator_name", "")} has submitted a translation for your work "{kwargs.get("work_title", "")}".',
            'ru': f'Пользователь {kwargs.get("translator_name", "")} отправил перевод для вашей работы "{kwargs.get("work_title", "")}".',
            'ko': f'사용자 {kwargs.get("translator_name", "")}가 귀하의 작품 "{kwargs.get("work_title", "")}"에 대한 번역을 제출했습니다.',
            'fr': f'L\'utilisateur {kwargs.get("translator_name", "")} a soumis une traduction pour votre œuvre "{kwargs.get("work_title", "")}".',
            'zh': f'用户 {kwargs.get("translator_name", "")} 为您的作品《{kwargs.get("work_title", "")}》提交了翻译。',
            'ja': f'ユーザー {kwargs.get("translator_name", "")} があなたの作品《{kwargs.get("work_title", "")}》の翻訳を提出しました。'
        },
        'translation_accepted_to_author': {
            'en': f'You have accepted the translation of "{kwargs.get("work_title", "")}" by user {kwargs.get("translator_name", "")}.',
            'ru': f'Вы приняли перевод работы "{kwargs.get("work_title", "")}" пользователя {kwargs.get("translator_name", "")}.',
            'ko': f'사용자 {kwargs.get("translator_name", "")}의 "{kwargs.get("work_title", "")}" 번역을 승인했습니다.',
            'fr': f'Vous avez accepté la traduction de "{kwargs.get("work_title", "")}" par l\'utilisateur {kwargs.get("translator_name", "")}.',
            'zh': f'您已接受用户 {kwargs.get("translator_name", "")} 对作品《{kwargs.get("work_title", "")}》的翻译。',
            'ja': f'ユーザー {kwargs.get("translator_name", "")} の作品《{kwargs.get("work_title", "")}》の翻訳を承認しました。'
        },
        'translation_rejected_by_author': {
            'zh': f'您的翻译《{kwargs.get("work_title", "")}》被作者 {kwargs.get("author_name", "")} 拒绝了。',
            'ja': f'あなたの翻訳《{kwargs.get("work_title", "")}》が作者 {kwargs.get("author_name", "")} によって拒否されました。',
            'en': f'Your translation "{kwargs.get("work_title", "")}" was rejected by the author {kwargs.get("author_name", "")}.',
            'ru': f'Ваш перевод "{kwargs.get("work_title", "")}" был отклонен автором {kwargs.get("author_name", "")}.',
            'ko': f'귀하의 번역 "{kwargs.get("work_title", "")}"이 저자 {kwargs.get("author_name", "")}에 의해 거부되었습니다.',
            'fr': f'Votre traduction "{kwargs.get("work_title", "")}" a été rejetée par l\'auteur {kwargs.get("author_name", "")}.'
        },
        # 翻译者请求相关系统消息
        'translator_request_sent': {
            'zh': f'您已成功向作者发送要求，作品《{kwargs.get("work_title", "")}》。等待作者回复。',
            'ja': f'作者への要求を正常に送信しました。作品《{kwargs.get("work_title", "")}》。作者の返信をお待ちください。',
            'en': f'You have successfully sent a request to the author for the work "{kwargs.get("work_title", "")}". Waiting for author response.',
            'ru': f'Вы успешно отправили запрос автору для работы "{kwargs.get("work_title", "")}". Ожидание ответа автора.',
            'ko': f'작품 "{kwargs.get("work_title", "")}"에 대해 작가에게 요청을 성공적으로 보냈습니다. 작가의 답변을 기다리고 있습니다.',
            'fr': f'Vous avez envoyé avec succès une demande à l\'auteur pour l\'œuvre "{kwargs.get("work_title", "")}". En attente de la réponse de l\'auteur.'
        },
        'translator_request_received': {
            'zh': f'翻译者 {kwargs.get("translator_name", "")} 对您的作品《{kwargs.get("work_title", "")}》提出了要求，请前往消息中心查看并回复。',
            'ja': f'翻訳者 {kwargs.get("translator_name", "")} があなたの作品《{kwargs.get("work_title", "")}》に要求を提出しました。メッセージセンターで確認して返信してください。',
            'en': f'Translator {kwargs.get("translator_name", "")} has made a request for your work "{kwargs.get("work_title", "")}". Please go to the message center to view and respond.',
            'ru': f'Переводчик {kwargs.get("translator_name", "")} предъявил требования к вашей работе "{kwargs.get("work_title", "")}". Пожалуйста, перейдите в центр сообщений для просмотра и ответа.',
            'ko': f'번역가 {kwargs.get("translator_name", "")}가 귀하의 작품 "{kwargs.get("work_title", "")}"에 대해 요청을 제출했습니다. 메시지 센터에서 확인하고 답변해 주세요.',
            'fr': f'Le traducteur {kwargs.get("translator_name", "")} a fait une demande pour votre œuvre "{kwargs.get("work_title", "")}". Veuillez aller au centre de messages pour voir et répondre.'
        },

        'translator_request_approved': {
            'zh': f'作者 {kwargs.get("author_name", "")} 已同意您对作品《{kwargs.get("work_title", "")}》的要求。',
            'ja': f'作者 {kwargs.get("author_name", "")} があなたの作品《{kwargs.get("work_title", "")}》への要求を承認しました。',
            'en': f'Author {kwargs.get("author_name", "")} has approved your request for the work "{kwargs.get("work_title", "")}".',
            'ru': f'Автор {kwargs.get("author_name", "")} одобрил ваш запрос к работе "{kwargs.get("work_title", "")}".',
            'ko': f'작가 {kwargs.get("author_name", "")}가 귀하의 작품 "{kwargs.get("work_title", "")}"에 대한 요청을 승인했습니다.',
            'fr': f'L\'auteur {kwargs.get("author_name", "")} a approuvé votre demande pour l\'œuvre "{kwargs.get("work_title", "")}".'
        },
        'translator_request_rejected': {
            'zh': f'作者 {kwargs.get("author_name", "")} 已拒绝您对作品《{kwargs.get("work_title", "")}》的要求。',
            'ja': f'作者 {kwargs.get("author_name", "")} があなたの作品《{kwargs.get("work_title", "")}》への要求を拒否しました。',
            'en': f'Author {kwargs.get("author_name", "")} has rejected your request for the work "{kwargs.get("work_title", "")}".',
            'ru': f'Автор {kwargs.get("author_name", "")} отклонил ваш запрос к работе "{kwargs.get("work_title", "")}".',
            'ko': f'작가 {kwargs.get("author_name", "")}가 귀하의 작품 "{kwargs.get("work_title", "")}"에 대한 요청을 거부했습니다.',
            'fr': f'L\'auteur {kwargs.get("author_name", "")} a rejeté votre demande pour l\'œuvre "{kwargs.get("work_title", "")}".'
        },
        'translation_rejected_to_translator': {
            'zh': f'您的翻译《{kwargs.get("work_title", "")}》被作者拒绝了。',
            'ja': f'あなたの翻訳《{kwargs.get("work_title", "")}》が作者によって拒否されました。',
            'en': f'Your translation "{kwargs.get("work_title", "")}" was rejected by the author.',
            'ru': f'Ваш перевод "{kwargs.get("work_title", "")}" был отклонен автором.',
            'ko': f'귀하의 번역 "{kwargs.get("work_title", "")}"이 저자에 의해 거부되었습니다.',
            'fr': f'Votre traduction "{kwargs.get("work_title", "")}" a été rejetée par l\'auteur.'
        },
        'translation_rejected_to_author': {
            'en': f'You have rejected the translation of "{kwargs.get("work_title", "")}" by user {kwargs.get("translator_name", "")}.',
            'ru': f'Вы отклонили перевод работы "{kwargs.get("work_title", "")}" пользователя {kwargs.get("translator_name", "")}.',
            'ko': f'사용자 {kwargs.get("translator_name", "")}의 "{kwargs.get("work_title", "")}" 번역을 거부했습니다.',
            'fr': f'Vous avez rejeté la traduction de "{kwargs.get("work_title", "")}" par l\'utilisateur {kwargs.get("translator_name", "")}.',
            'zh': f'您已拒绝用户 {kwargs.get("translator_name", "")} 对作品《{kwargs.get("work_title", "")}》的翻译。',
            'ja': f'ユーザー {kwargs.get("translator_name", "")} の作品《{kwargs.get("work_title", "")}》の翻訳を拒否しました。'
        },
                        'admin_request_approved': {
                            'zh': '恭喜！您的管理员申请已获得批准，现在您拥有管理员权限。',
                            'ja': 'おめでとうございます！管理者申請が承認されました。現在管理者権限をお持ちです。'
                        },
                        'admin_request_rejected': {
                            'zh': '很抱歉，您的管理员申请被拒绝了。',
                            'ja': '申し訳ございませんが、管理者申請が拒否されました。'
                        },
                        'admin_work_deleted': {
                            'zh': f'管理员 {kwargs.get("admin_name", "")} 删除了您的作品《{kwargs.get("work_title", "")}》。',
                            'ja': f'管理者 {kwargs.get("admin_name", "")} があなたの作品《{kwargs.get("work_title", "")}》を削除しました。'
                        },
                        'admin_work_edited': {
                            'zh': f'管理员 {kwargs.get("admin_name", "")} 编辑了您的作品《{kwargs.get("work_title", "")}》。',
                            'ja': f'管理者 {kwargs.get("admin_name", "")} があなたの作品《{kwargs.get("work_title", "")}》を編集しました。'
                        },
                                'admin_comment_deleted': {
            'zh': f'管理员 {kwargs.get("admin_name", "")} 删除了您在作品《{kwargs.get("work_title", "")}》中的评论。',
            'ja': f'管理者 {kwargs.get("admin_name", "")} があなたの作品《{kwargs.get("work_title", "")}》のコメントを削除しました。'
        },
        'correction_submitted_to_creator': {
            'zh': f'校正者 {kwargs.get("reviewer_name", "")} 为您的作品《{kwargs.get("work_title", "")}》提交了校正。',
            'ja': f'校正者 {kwargs.get("reviewer_name", "")} があなたの作品《{kwargs.get("work_title", "")}》の校正を提出しました。',
            'en': f'Reviewer {kwargs.get("reviewer_name", "")} has submitted a correction for your work "{kwargs.get("work_title", "")}".',
            'ru': f'Рецензент {kwargs.get("reviewer_name", "")} отправил исправление для вашей работы "{kwargs.get("work_title", "")}".',
            'ko': f'교정자 {kwargs.get("reviewer_name", "")}가 귀하의 작품 "{kwargs.get("work_title", "")}"에 대한 교정을 제출했습니다.',
            'fr': f'Le réviseur {kwargs.get("reviewer_name", "")} a soumis une correction pour votre œuvre "{kwargs.get("work_title", "")}".'
        },
        'work_comment_received': {
            'zh': f'用户 {kwargs.get("commenter_name", "")} 对您的作品《{kwargs.get("work_title", "")}》发表了评论："{kwargs.get("comment_content", "")}"',
            'ja': f'ユーザー {kwargs.get("commenter_name", "")} があなたの作品《{kwargs.get("work_title", "")}》にコメントを投稿しました：「{kwargs.get("comment_content", "")}」',
            'en': f'User {kwargs.get("commenter_name", "")} commented on your work "{kwargs.get("work_title", "")}": "{kwargs.get("comment_content", "")}"',
            'ru': f'Пользователь {kwargs.get("commenter_name", "")} прокомментировал вашу работу "{kwargs.get("work_title", "")}": "{kwargs.get("comment_content", "")}"',
            'ko': f'사용자 {kwargs.get("commenter_name", "")}가 귀하의 작품 "{kwargs.get("work_title", "")}"에 댓글을 달았습니다: "{kwargs.get("comment_content", "")}"',
            'fr': f'L\'utilisateur {kwargs.get("commenter_name", "")} a commenté votre œuvre "{kwargs.get("work_title", "")}": "{kwargs.get("comment_content", "")}"'
        },
        'translation_comment_received': {
            'zh': f'用户 {kwargs.get("commenter_name", "")} 对您在作品《{kwargs.get("work_title", "")}》中的翻译发表了评论："{kwargs.get("comment_content", "")}"',
            'ja': f'ユーザー {kwargs.get("commenter_name", "")} があなたの作品《{kwargs.get("work_title", "")}》の翻訳にコメントを投稿しました：「{kwargs.get("comment_content", "")}」',
            'en': f'User {kwargs.get("commenter_name", "")} commented on your translation of "{kwargs.get("work_title", "")}": "{kwargs.get("comment_content", "")}"',
            'ru': f'Пользователь {kwargs.get("commenter_name", "")} прокомментировал ваш перевод работы "{kwargs.get("work_title", "")}": "{kwargs.get("comment_content", "")}"',
            'ko': f'사용자 {kwargs.get("commenter_name", "")}가 귀하의 "{kwargs.get("work_title", "")}" 번역에 댓글을 달았습니다: "{kwargs.get("comment_content", "")}"',
            'fr': f'L\'utilisateur {kwargs.get("commenter_name", "")} a commenté votre traduction de "{kwargs.get("work_title", "")}": "{kwargs.get("comment_content", "")}"'
        },
        'correction_comment_received': {
            'zh': f'用户 {kwargs.get("commenter_name", "")} 对您在作品《{kwargs.get("work_title", "")}》中的校正发表了评论："{kwargs.get("comment_content", "")}"',
            'ja': f'ユーザー {kwargs.get("commenter_name", "")} があなたの作品《{kwargs.get("work_title", "")}》の校正にコメントを投稿しました：「{kwargs.get("comment_content", "")}」',
            'en': f'User {kwargs.get("commenter_name", "")} commented on your correction of "{kwargs.get("work_title", "")}": "{kwargs.get("comment_content", "")}"',
            'ru': f'Пользователь {kwargs.get("commenter_name", "")} прокомментировал вашу правку работы "{kwargs.get("work_title", "")}": "{kwargs.get("comment_content", "")}"',
            'ko': f'사용자 {kwargs.get("commenter_name", "")}가 귀하의 "{kwargs.get("work_title", "")}" 교정에 댓글을 달았습니다: "{kwargs.get("comment_content", "")}"',
            'fr': f'L\'utilisateur {kwargs.get("commenter_name", "")} a commenté votre correction de "{kwargs.get("work_title", "")}": "{kwargs.get("comment_content", "")}"'
        },
        'correction_submitted_to_translator': {
            'zh': f'校正者 {kwargs.get("reviewer_name", "")} 为您的翻译《{kwargs.get("work_title", "")}》提交了校正。',
            'ja': f'校正者 {kwargs.get("reviewer_name", "")} があなたの翻訳《{kwargs.get("work_title", "")}》の校正を提出しました。',
            'en': f'Reviewer {kwargs.get("reviewer_name", "")} has submitted a correction for your translation "{kwargs.get("work_title", "")}".',
            'ru': f'Рецензент {kwargs.get("reviewer_name", "")} отправил исправление для вашего перевода "{kwargs.get("work_title", "")}".',
            'ko': f'교정자 {kwargs.get("reviewer_name", "")}가 귀하의 번역 "{kwargs.get("work_title", "")}"에 대한 교정을 제출했습니다.',
            'fr': f'Le réviseur {kwargs.get("reviewer_name", "")} a soumis une correction pour votre traduction "{kwargs.get("work_title", "")}".'
        }
    }
    
    message_template = system_messages.get(message_type, {}).get(lang, system_messages.get(message_type, {}).get('zh', ''))
    
    # 处理占位符替换
    if message_template:
        # 替换好友相关的占位符
        if '{sender_name}' in message_template:
            message_template = message_template.replace('{sender_name}', kwargs.get('sender_name', ''))
        if '{receiver_name}' in message_template:
            message_template = message_template.replace('{receiver_name}', kwargs.get('receiver_name', ''))
    
    return message_template

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user')  # admin, creator, translator, user
    bio = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    avatar = db.Column(db.String(200))
    is_translator = db.Column(db.Boolean, default=False)
    is_reviewer = db.Column(db.Boolean, default=False)
    is_creator = db.Column(db.Boolean, default=False)
    preferred_language = db.Column(db.String(10), default='zh')  # zh/ja
    experience = db.Column(db.Integer, default=0)  # 经验值字段
    email_notifications_enabled = db.Column(db.Boolean, default=True)  # 邮件通知开关
    
    # 关系
    works = db.relationship('Work', backref='creator', lazy=True)
    translations = db.relationship(
        'Translation',
        backref='translator',
        lazy=True,
        foreign_keys='Translation.translator_id'
    )
    reviews = db.relationship(
        'Translation',
        backref='reviewer',
        lazy=True,
        foreign_keys='Translation.reviewer_id'
    )
    comments = db.relationship('Comment', backref='author', lazy=True)
    sent_messages = db.relationship('Message', backref='sender', foreign_keys='Message.sender_id')
    received_messages = db.relationship('Message', backref='receiver', foreign_keys='Message.receiver_id')
    favorites = db.relationship('Favorite', backref='user', lazy=True)
    
    def get_level(self):
        """计算用户等级"""
        return min(self.experience, 999)
    
    def get_level_display(self):
        """获取等级显示文本"""
        level = self.get_level()
        return f"Lv.{level}"
    
    def add_experience(self, amount):
        """添加经验值"""
        self.experience = min(self.experience + amount, 999)
        db.session.commit()
    
    def get_display_id(self):
        """获取用户显示ID"""
        if self.role == 'admin':
            return "1000"
        elif self.role == 'system' and self.username == 'system':
            return str(self.id)
        elif self.email.endswith('@example.com') and self.username != 'admin':
            # 测试用户（默认系统用户）显示ID从1001开始
            return str(self.id)
        else:
            # 真实用户显示ID从10001开始
            return str(self.id)

class Work(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    original_language = db.Column(db.String(50), nullable=False, default='中文')
    target_language = db.Column(db.String(50), nullable=False, default='英文')
    category = db.Column(db.String(100))
    status = db.Column(db.String(20), default='pending')  # pending, translating, completed
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    media_filename = db.Column(db.String(200))
    translation_requirements = db.Column(db.Text)  # 新增字段
    translation_expectation = db.Column(db.Text)  # 新增字段
    contact_before_translate = db.Column(db.Boolean, default=False)  # 新增字段
    allow_multiple_translators = db.Column(db.Boolean, default=False)  # 允许多人翻译
    tags = db.Column(db.Text)  # 标签字段，存储JSON格式的标签列表
    
    # 关系
    translations = db.relationship('Translation', backref='work', lazy=True)
    comments = db.relationship('Comment', backref='work', lazy=True)
    favorites = db.relationship('Favorite', backref='work', lazy=True)

class Translation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    work_id = db.Column(db.Integer, db.ForeignKey('work.id'), nullable=False)
    translator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='draft')  # draft, submitted, approved, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    reviewer_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    review_notes = db.Column(db.Text)
    media_filename = db.Column(db.String(200))  # 新增字段：多媒体文件名

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    work_id = db.Column(db.Integer, db.ForeignKey('work.id'), nullable=False)
    translation_id = db.Column(db.Integer, db.ForeignKey('translation.id'), nullable=True)  # 新增：关联翻译
    correction_id = db.Column(db.Integer, db.ForeignKey('correction.id'), nullable=True)  # 新增：关联校正
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 关系
    translation = db.relationship('Translation', backref='comments')
    correction = db.relationship('Correction', backref='comments')

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image_filename = db.Column(db.String(255), nullable=True)  # 新增：图片文件名
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    type = db.Column(db.String(20), default='private')  # 新增字段，private/system
    work_id = db.Column(db.Integer, db.ForeignKey('work.id'), nullable=True)  # 新增字段，关联作品ID
    liker_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # 新增字段，关联点赞者ID

@event.listens_for(db.session, 'after_flush')
def collect_new_messages(session, flush_context):
    # 在 flush 阶段收集新增的 Message，以便 commit 成功后再发送
    new_messages = session.info.setdefault('new_messages', [])
    for obj in session.new:
        if isinstance(obj, Message):
            new_messages.append(obj)


@event.listens_for(db.session, 'after_commit')
def send_email_on_new_message(session):
    if not is_smtp_configured():
        # 清理队列，避免下次事务污染
        session.info.pop('new_messages', None)
        return
    new_messages = session.info.pop('new_messages', []) or []
    for obj in new_messages:
        try:
            # 检查是否已经手动发送过邮件（避免重复发送）
            if hasattr(obj, '_email_sent') and obj._email_sent:
                continue
                
            # 使用新的session来查询用户信息
            from app import app
            with app.app_context():
                receiver = User.query.get(obj.receiver_id)
                sender = User.query.get(obj.sender_id)
                if not receiver or not receiver.email:
                    continue
                # 尊重用户开关
                if hasattr(receiver, 'email_notifications_enabled') and not receiver.email_notifications_enabled:
                    continue
                # 仅对私信和系统消息发送邮件（多语言）
                lang = getattr(receiver, 'preferred_language', 'zh') or 'zh'
                subject = get_message('email_new_message_subject', lang=lang)
                text_lines = []
                greeting = get_message('email_greeting', lang=lang).format(username=receiver.username)
                text_lines.append(greeting)
                # 处理发送者信息，系统消息的sender_id可能不存在
                sender_name = sender.username if sender else '系统'
                if sender:
                    text_lines.append(f"{get_message('email_from', lang=lang)}: {sender.username}")
                else:
                    text_lines.append(f"{get_message('email_from', lang=lang)}: 系统")
                text_lines.append(f"{get_message('email_time', lang=lang)}: {obj.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
                # 截断内容，避免过长
                preview = (obj.content or '').strip()
                if len(preview) > 200:
                    preview = preview[:200] + '...'
                text_lines.append("")
                text_lines.append(preview or '(图片/系统通知)')
                text_lines.append("")
                text_lines.append(get_message('email_footer', lang=lang))
                text_body = "\n".join(text_lines)

                # 预处理预览内容，将换行符替换为HTML标签
                preview_html = (preview or '(图片/系统通知)').replace('\n','<br/>')
                html_body = f"""
                <p>{greeting}</p>
                <p>{get_message('email_from', lang=lang)}: <strong>{sender_name}</strong></p>
                <p>{get_message('email_time', lang=lang)}: {obj.created_at.strftime('%Y-%m-%d %H:%M:%S')}</p>
                <hr/>
                <p>{preview_html}</p>
                <p style=\"color:#666;\">{get_message('email_footer', lang=lang)}</p>
                """
                # 根据消息类型选择邮件样式
                message_type = 'system' if obj.type == 'system' else 'general'
                send_email(receiver.email, subject, text_body, html_body, message_type, lang)
        except Exception as e:
            # 邮件失败不影响主流程，但记录错误
            print(f"[EMAIL_ERROR] 发送邮件失败: {e}")
            import traceback
            traceback.print_exc()

class TranslationRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    work_id = db.Column(db.Integer, db.ForeignKey('work.id'), nullable=False)
    translator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=True)  # 翻译者的期待/要求
    status = db.Column(db.String(20), default='pending')  # pending/approved/rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 关系
    translator = db.relationship('User', foreign_keys=[translator_id], backref='translation_requests')
    author = db.relationship('User', foreign_keys=[author_id], backref='received_translation_requests')
    work = db.relationship('Work', backref='translation_requests')

class TranslatorRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    work_id = db.Column(db.Integer, db.ForeignKey('work.id'), nullable=False)
    translator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)  # 翻译者对作者的要求
    status = db.Column(db.String(20), default='pending')  # pending/approved/rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    responded_at = db.Column(db.DateTime)  # 作者回复时间
    response = db.Column(db.Text)  # 作者的回复
    
    # 关系
    translator = db.relationship('User', foreign_keys=[translator_id], backref='translator_requests')
    author = db.relationship('User', foreign_keys=[author_id], backref='received_translator_requests')
    work = db.relationship('Work', backref='translator_requests')

class TrustedTranslator(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # 作者ID
    translator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # 被信任的翻译者ID
    __table_args__ = (db.UniqueConstraint('user_id', 'translator_id', name='unique_trust'),)

class Friend(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    friend_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending/accepted/rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'friend_id', name='unique_friend'),)

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    target_type = db.Column(db.String(20), nullable=False)  # work, comment, translation
    target_id = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'target_type', 'target_id', name='unique_like'),)

class AuthorLike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # 作者ID
    translation_id = db.Column(db.Integer, db.ForeignKey('translation.id'), nullable=False)  # 翻译ID
    correction_id = db.Column(db.Integer, db.ForeignKey('correction.id'), nullable=True)  # 校正ID（新增）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('author_id', 'translation_id', 'correction_id', name='unique_author_like'),)

class AdminRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # 申请者ID
    reason = db.Column(db.Text, nullable=False)  # 申请理由
    status = db.Column(db.String(20), default='pending')  # pending/approved/rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime)  # 审核时间
    reviewer_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # 审核者ID
    review_notes = db.Column(db.Text)  # 审核备注
    
    # 关系
    user = db.relationship('User', foreign_keys=[user_id], backref='admin_requests')
    reviewer = db.relationship('User', foreign_keys=[reviewer_id], backref='reviewed_admin_requests')

class Correction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    translation_id = db.Column(db.Integer, db.ForeignKey('translation.id'), nullable=False)
    reviewer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)  # 校正内容
    notes = db.Column(db.Text)  # 校正说明/注解
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    translation = db.relationship('Translation', backref='corrections')
    reviewer = db.relationship('User', backref='corrections')

class CorrectionLike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    correction_id = db.Column(db.Integer, db.ForeignKey('correction.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'correction_id', name='unique_correction_like'),)

class TranslatorLike(db.Model):
    """对翻译者的点赞"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # 点赞者ID
    translator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # 被点赞的翻译者ID
    work_id = db.Column(db.Integer, db.ForeignKey('work.id'), nullable=False)  # 作品ID
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'translator_id', 'work_id', name='unique_translator_like'),)

class ReviewerLike(db.Model):
    """对校正者的点赞"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # 点赞者ID
    reviewer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # 被点赞的校正者ID
    work_id = db.Column(db.Integer, db.ForeignKey('work.id'), nullable=False)  # 作品ID
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'reviewer_id', 'work_id', name='unique_reviewer_like'),)

class Favorite(db.Model):
    """用户收藏作品"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # 收藏者ID
    work_id = db.Column(db.Integer, db.ForeignKey('work.id'), nullable=False)  # 被收藏的作品ID
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'work_id', name='unique_favorite'),)

# 辅助函数
def get_user_by_id(user_id):
    return User.query.get(user_id)

def is_logged_in():
    return 'user_id' in session

def get_current_user():
    if is_logged_in():
        return db.session.get(User, int(session['user_id']))
    return None

def has_role(role):
    return is_logged_in() and session.get('role') == role

def has_any_role(*roles):
    return is_logged_in() and session.get('role') in roles

# Jinja模板辅助函数
@app.context_processor
def utility_processor():
    def get_username(user_id):
        user = User.query.get(user_id)
        return user.username if user else 'Unknown User'
    
    def get_work_title(work_id):
        work = Work.query.get(work_id)
        return work.title if work else 'Unknown Work'
    
    def get_user_by_id(user_id):
        return User.query.get(user_id)
    
    def get_user_language_display_name(user):
        """根据用户的偏好语言代码返回对应的显示名称"""
        if not user or not hasattr(user, 'preferred_language'):
            return '中文'
        
        language_names = {
            'zh': {'zh': '中文', 'ja': '中国語', 'en': 'Chinese', 'ru': 'Китайский', 'ko': '중국어', 'fr': 'Chinois'},
            'ja': {'zh': '日文', 'ja': '日本語', 'en': 'Japanese', 'ru': 'Японский', 'ko': '일본어', 'fr': 'Japonais'},
            'en': {'zh': '英文', 'ja': '英語', 'en': 'English', 'ru': 'Английский', 'ko': '영어', 'fr': 'Anglais'},
            'ru': {'zh': '俄文', 'ja': 'ロシア語', 'en': 'Russian', 'ru': 'Русский', 'ko': '러시아어', 'fr': 'Russe'},
            'ko': {'zh': '韩文', 'ja': '韓国語', 'en': 'Korean', 'ru': 'Корейский', 'ko': '한국어', 'fr': 'Coréen'},
            'fr': {'zh': '法文', 'ja': 'フランス語', 'en': 'French', 'ru': 'Французский', 'ko': '프랑스어', 'fr': 'Français'}
        }
        
        # 获取当前界面语言
        current_lang = session.get('lang', 'zh')
        user_lang = user.preferred_language
        
        # 如果用户偏好语言在映射中，返回对应的显示名称
        if user_lang in language_names:
            return language_names[user_lang].get(current_lang, language_names[user_lang]['zh'])
        
        return '中文'  # 默认返回中文
    
    def format_message_content(content, work_id=None, message_id=None, liker_id=None):
        """格式化消息内容，将作品标题和用户名转换为超链接"""
        import re
        
        # 只对 friend_request_accepted 消息进行调试
        if content == 'friend_request_accepted':
            print(f"DEBUG format_message_content: Processing friend_request_accepted message")
            print(f"DEBUG format_message_content: work_id = {work_id}, message_id = {message_id}, liker_id = {liker_id}")
        
        # 处理作品标题链接
        if work_id:
            work = Work.query.get(work_id)
            if work:
                work_title = work.title
                
                # 添加点击事件，标记消息为已读
                onclick_attr = ""
                if message_id:
                    onclick_attr = f' onclick="markMessageAsRead({message_id})"'
                
                # 匹配中文书名号《》
                content = re.sub(
                    rf'《{re.escape(work_title)}》',
                    f'<a href="{url_for("work_detail", work_id=work_id)}" class="text-decoration-none fw-bold"{onclick_attr}>{work_title}</a>',
                    content
                )
                
                # 匹配英文双引号""
                content = re.sub(
                    rf'"{re.escape(work_title)}"',
                    f'<a href="{url_for("work_detail", work_id=work_id)}" class="text-decoration-none fw-bold"{onclick_attr}>{work_title}</a>',
                    content
                )
                
                # 匹配冒号格式（如：作品：标题）
                content = re.sub(
                    rf'作品：{re.escape(work_title)}',
                    f'作品：<a href="{url_for("work_detail", work_id=work_id)}" class="text-decoration-none fw-bold"{onclick_attr}>{work_title}</a>',
                    content
                )
                
                # 匹配英文冒号格式（如：Work: title）
                content = re.sub(
                    rf'Work: {re.escape(work_title)}',
                    f'Work: <a href="{url_for("work_detail", work_id=work_id)}" class="text-decoration-none fw-bold"{onclick_attr}>{work_title}</a>',
                    content
                )
        
        # 处理用户名链接
        if liker_id:
            liker = User.query.get(liker_id)
            if liker:
                liker_name = liker.username
                
                # 匹配各种语言中的用户名
                # 中文格式：收到了张三的点赞
                content = re.sub(
                    rf'收到了{re.escape(liker_name)}的点赞',
                    f'收到了<a href="{url_for("user_profile", user_id=liker_id)}" class="text-decoration-none fw-bold">{liker_name}</a>的点赞',
                    content
                )
                
                # 日文格式：张三さんがいいねをしました
                content = re.sub(
                    rf'{re.escape(liker_name)}さんがいいねをしました',
                    f'<a href="{url_for("user_profile", user_id=liker_id)}" class="text-decoration-none fw-bold">{liker_name}</a>さんがいいねをしました',
                    content
                )
                
                # 英文格式：from 张三 on your
                content = re.sub(
                    rf'from {re.escape(liker_name)} on your',
                    f'from <a href="{url_for("user_profile", user_id=liker_id)}" class="text-decoration-none fw-bold">{liker_name}</a> on your',
                    content
                )
                
                # 俄文格式：от 张三 за ваш
                content = re.sub(
                    rf'от {re.escape(liker_name)} за ваш',
                    f'от <a href="{url_for("user_profile", user_id=liker_id)}" class="text-decoration-none fw-bold">{liker_name}</a> за ваш',
                    content
                )
                
                # 韩文格式：张三님이 좋아요를 했습니다
                content = re.sub(
                    rf'{re.escape(liker_name)}님이 좋아요를 했습니다',
                    f'<a href="{url_for("user_profile", user_id=liker_id)}" class="text-decoration-none fw-bold">{liker_name}</a>님이 좋아요를 했습니다',
                    content
                )
                
                # 法文格式：de 张三 sur votre
                content = re.sub(
                    rf'de {re.escape(liker_name)} sur votre',
                    f'de <a href="{url_for("user_profile", user_id=liker_id)}" class="text-decoration-none fw-bold">{liker_name}</a> sur votre',
                    content
                )
        
        # 处理好友请求相关消息中的用户名链接（不需要work_id或liker_id）
        # 从消息内容中提取用户名并创建链接
        # 中文格式：用户 张三 已接受您的好友请求。
        # 英文格式：Your friend request has been accepted by 张三.
        # 俄文格式：Ваш запрос в друзья был принят пользователем 张三.
        # 日文格式：あなたの友達リクエストが 张三 によって承認されました。
        # 韩文格式：친구 요청이 张三에 의해 승인되었습니다.
        # 法文格式：Votre demande d'ami a été acceptée par 张三.
        
        # 查找消息中的用户名模式
        username_pattern = r'用户\s+([^\s]+)\s+已接受您的好友请求'
        match = re.search(username_pattern, content)
        if match:
            username = match.group(1)
            user = User.query.filter_by(username=username).first()
            if user:
                content = re.sub(
                    rf'用户\s+{re.escape(username)}\s+已接受您的好友请求',
                    f'用户 <a href="{url_for("user_profile", user_id=user.id)}" class="text-decoration-none fw-bold">{username}</a> 已接受您的好友请求',
                    content
                )
        
        # 英文格式
        username_pattern = r'Your friend request has been accepted by\s+([^\s]+)'
        match = re.search(username_pattern, content)
        if match:
            username = match.group(1)
            user = User.query.filter_by(username=username).first()
            if user:
                content = re.sub(
                    rf'Your friend request has been accepted by\s+{re.escape(username)}',
                    f'Your friend request has been accepted by <a href="{url_for("user_profile", user_id=user.id)}" class="text-decoration-none fw-bold">{username}</a>',
                    content
                )
        
        # 俄文格式
        username_pattern = r'Ваш запрос в друзья был принят пользователем\s+([^\s]+)'
        match = re.search(username_pattern, content)
        if match:
            username = match.group(1)
            user = User.query.filter_by(username=username).first()
            if user:
                content = re.sub(
                    rf'Ваш запрос в друзья был принят пользователем\s+{re.escape(username)}',
                    f'Ваш запрос в друзья был принят пользователем <a href="{url_for("user_profile", user_id=user.id)}" class="text-decoration-none fw-bold">{username}</a>',
                    content
                )
        
        # 日文格式
        username_pattern = r'あなたの友達リクエストが\s+([^\s]+)\s+によって承認されました'
        match = re.search(username_pattern, content)
        if match:
            username = match.group(1)
            user = User.query.filter_by(username=username).first()
            if user:
                content = re.sub(
                    rf'あなたの友達リクエストが\s+{re.escape(username)}\s+によって承認されました',
                    f'あなたの友達リクエストが <a href="{url_for("user_profile", user_id=user.id)}" class="text-decoration-none fw-bold">{username}</a> によって承認されました',
                    content
                )
        
        # 韩文格式
        username_pattern = r'친구 요청이\s+([^\s]+)에\s+의해\s+승인되었습니다'
        match = re.search(username_pattern, content)
        if match:
            username = match.group(1)
            user = User.query.filter_by(username=username).first()
            if user:
                content = re.sub(
                    rf'친구 요청이\s+{re.escape(username)}에\s+의해\s+승인되었습니다',
                    f'친구 요청이 <a href="{url_for("user_profile", user_id=user.id)}" class="text-decoration-none fw-bold">{username}</a>에 의해 승인되었습니다',
                    content
                )
        
        # 法文格式
        username_pattern = r'Votre demande d\'ami a été acceptée par\s+([^\s]+)'
        match = re.search(username_pattern, content)
        if match:
            username = match.group(1)
            user = User.query.filter_by(username=username).first()
            if user:
                content = re.sub(
                    rf'Votre demande d\'ami a été acceptée par\s+{re.escape(username)}',
                    f'Votre demande d\'ami a été acceptée par <a href="{url_for("user_profile", user_id=user.id)}" class="text-decoration-none fw-bold">{username}</a>',
                    content
                )
        
        # 处理好友请求拒绝的消息
        # 中文格式：用户 张三 拒绝了您的好友请求。
        username_pattern = r'用户\s+([^\s]+)\s+拒绝了您的好友请求'
        match = re.search(username_pattern, content)
        if match:
            username = match.group(1)
            user = User.query.filter_by(username=username).first()
            if user:
                content = re.sub(
                    rf'用户\s+{re.escape(username)}\s+拒绝了您的好友请求',
                    f'用户 <a href="{url_for("user_profile", user_id=user.id)}" class="text-decoration-none fw-bold">{username}</a> 拒绝了您的好友请求',
                    content
                )
        
        # 英文格式：Your friend request has been rejected by 张三.
        username_pattern = r'Your friend request has been rejected by\s+([^\s]+)'
        match = re.search(username_pattern, content)
        if match:
            username = match.group(1)
            user = User.query.filter_by(username=username).first()
            if user:
                content = re.sub(
                    rf'Your friend request has been rejected by\s+{re.escape(username)}',
                    f'Your friend request has been rejected by <a href="{url_for("user_profile", user_id=user.id)}" class="text-decoration-none fw-bold">{username}</a>',
                    content
                )
        
        # 处理评论内容中的换行符，转换为HTML的<br>标签
        content = content.replace('\n', '<br>')
        
        print(f"DEBUG format_message_content: final content = {content}")
        return content
    
    return {
        'get_username': get_username,
        'get_work_title': get_work_title,
        'get_user_by_id': get_user_by_id,
        'get_user_language_display_name': get_user_language_display_name,
        'get_message': get_message,
        'format_message_content': format_message_content,
        'TrustedTranslator': TrustedTranslator,
        'Friend': Friend,
        'Like': Like,
        'AuthorLike': AuthorLike
    }

@app.route('/')
def index():
    # 未登录且未显式选择语言时，首页默认使用英文
    if not is_logged_in() and 'lang' not in session:
        session['lang'] = 'en'
    # 获取最新作品（用于预览）
    recent_works = Work.query.order_by(Work.created_at.desc()).limit(6).all()
    
    # 获取最热作品（按点赞数排序）
    hot_works = db.session.query(Work, func.count(Like.id).label('like_count')).\
        outerjoin(Like, Work.id == Like.target_id).\
        filter(Like.target_type == 'work').\
        group_by(Work.id).\
        order_by(func.count(Like.id).desc()).\
        limit(6).all()
    
    # 提取作品对象
    hot_works = [work for work, like_count in hot_works]
    
    return render_template('index.html', recent_works=recent_works, hot_works=hot_works)

@app.route('/works')
def works():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    category = request.args.get('category', '')
    original_language = request.args.get('original_language', '')
    target_language = request.args.get('target_language', '')
    status = request.args.get('status', '')
    tags = request.args.get('tags', '')
    
    query = Work.query
    
    if search:
        query = query.filter(Work.title.contains(search) | Work.content.contains(search))
    if category:
        query = query.filter(Work.category == category)
    if original_language:
        query = query.filter(Work.original_language == original_language)
    if target_language:
        query = query.filter(Work.target_language == target_language)
    if status:
        query = query.filter(Work.status == status)
    if tags:
        # 处理标签筛选 - 支持多个标签值
        tag_list = request.args.getlist('tags') if isinstance(request.args.getlist('tags'), list) else [tags]
        for tag in tag_list:
            if tag == 'multiple_translators':
                query = query.filter(Work.allow_multiple_translators == True)
            # 可以扩展其他标签筛选逻辑
    
    works = query.order_by(Work.created_at.desc()).paginate(
        page=page, per_page=10, error_out=False
    )
    
    categories = db.session.query(Work.category).distinct().all()
    categories = [cat[0] for cat in categories if cat[0]]
    
    return render_template('works.html', works=works, categories=categories, search=search, category=category, original_language=original_language, target_language=target_language, status=status, tags=tags, AuthorLike=AuthorLike, Like=Like)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        # 检查用户是否已存在
        if User.query.filter_by(username=username).first():
            flash(get_message('username_exists'), 'error')
            return render_template('register.html')
        
        # 检查邮箱是否已存在（管理员邮箱除外）
        if email != 'lafengnidaye@gmail.com' and User.query.filter_by(email=email).first():
            flash(get_message('email_exists'), 'error')
            return render_template('register.html')
        
        # 获取当前会话中的语言设置，如果没有则默认为中文
        current_lang = session.get('lang', 'zh')
        
        # 为真实用户分配ID，从10001开始
        max_real_user_id = db.session.query(db.func.max(User.id)).filter(
            ~User.email.endswith('@example.com'),
            User.role != 'admin',
            User.role != 'system'
        ).scalar() or 10000
        
        next_real_user_id = max(max_real_user_id + 1, 10001)
        
        # 注册时强制为普通用户，使用当前选择的语言
        user = User(
            id=next_real_user_id,
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            role='user',
            preferred_language=current_lang,  # 使用当前选择的语言
            email_notifications_enabled=True if request.form.get('email_notifications_enabled') else False
        )
        db.session.add(user)
        db.session.commit()
        # 注册后自动登录
        session['user_id'] = user.id
        session['role'] = user.role
        session['username'] = user.username
        session['lang'] = user.preferred_language  # 设置用户的语言偏好
        flash(get_message('register_success'), 'success')
        return redirect(url_for('index'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username_or_email = request.form['username']
        password = request.form['password']
        
        # 尝试通过用户名或邮箱查找用户
        user = User.query.filter_by(username=username_or_email).first()
        if not user:
            user = User.query.filter_by(email=username_or_email).first()
        
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['role'] = user.role
            session['username'] = user.username
            # 设置用户的语言偏好（暂时使用默认值）
            session['lang'] = getattr(user, 'preferred_language', 'zh')
            flash(get_message('welcome_back').format(user.username), 'success')
            return redirect(url_for('index'))
        else:
            flash(get_message('login_error'), 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    # 在清除会话之前保存当前语言设置
    current_lang = session.get('lang', 'zh')
    if is_logged_in():
        user = get_current_user()
        if user and hasattr(user, 'preferred_language'):
            current_lang = user.preferred_language
    
    session.clear()
    flash(get_message('logout_success', lang=current_lang), 'success')
    return redirect(url_for('index'))

@app.route('/profile')
def profile():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))
    user_works = Work.query.filter_by(creator_id=user.id).order_by(Work.created_at.desc()).limit(5).all()
    user_translations = Translation.query.filter_by(translator_id=user.id).order_by(Translation.created_at.desc()).limit(5).all()
    # 获取所有翻译用于点赞统计
    all_user_translations = Translation.query.filter_by(translator_id=user.id).all()
    user_comments = Comment.query.filter_by(author_id=user.id).order_by(Comment.created_at.desc()).limit(5).all()
    
    # 计算点赞统计
    work_likes = 0
    translation_likes = 0
    comment_likes = 0
    author_likes = 0
    
    # 计算作品点赞数
    for work in user.works:
        work_likes += Like.query.filter_by(target_type='work', target_id=work.id).count()
    
    # 计算翻译点赞数
    for translation in user.translations:
        translation_likes += Like.query.filter_by(target_type='translation', target_id=translation.id).count()
    
    # 计算评论点赞数
    for comment in user.comments:
        comment_likes += Like.query.filter_by(target_type='comment', target_id=comment.id).count()
    
    # 计算作者点赞数（作者对翻译的点赞 + 作者对校正的点赞）
    for translation in user.translations:
        author_likes += AuthorLike.query.filter_by(translation_id=translation.id, correction_id=None).count()
    
    # 计算校正点赞数（只计算普通用户对校正的点赞）
    correction_likes = 0
    for correction in user.corrections:
        # 计算普通点赞数量
        correction_likes += CorrectionLike.query.filter_by(correction_id=correction.id).count()
        # 作者对校正的点赞也计入作者点赞总数
        author_likes += AuthorLike.query.filter_by(translation_id=correction.translation_id, correction_id=correction.id).count()
    
    # 获取最近收到的作者评价
    recent_author_likes = []
    for translation in user.translations:
        # 获取作者对翻译的评价
        translation_author_likes = AuthorLike.query.filter_by(translation_id=translation.id, correction_id=None).all()
        for like in translation_author_likes:
            author = User.query.get(like.author_id)
            if author:
                recent_author_likes.append({
                    'type': 'translation',
                    'author': author,
                    'work': translation.work,
                    'translation': translation,
                    'correction': None,
                    'created_at': like.created_at
                })
    
    # 获取作者对校正的评价
    for correction in user.corrections:
        correction_author_likes = AuthorLike.query.filter_by(translation_id=correction.translation_id, correction_id=correction.id).all()
        for like in correction_author_likes:
            author = User.query.get(like.author_id)
            if author:
                recent_author_likes.append({
                    'type': 'correction',
                    'author': author,
                    'work': correction.translation.work,
                    'translation': correction.translation,
                    'correction': correction,
                    'created_at': like.created_at
                })
    
    # 按时间排序，取最近的5个
    recent_author_likes.sort(key=lambda x: x['created_at'], reverse=True)
    recent_author_likes = recent_author_likes[:5]
    
    # 好友列表
    friends = Friend.query.filter(
        ((Friend.user_id == user.id) | (Friend.friend_id == user.id)) & (Friend.status == 'accepted')
    ).all()
    # 信赖者列表
    trusted = TrustedTranslator.query.filter_by(user_id=user.id).all()
    return render_template('profile.html', user=user, works=user_works, translations=user_translations, all_user_translations=all_user_translations, comments=user_comments, friends=friends, trusted=trusted, work_likes=work_likes, translation_likes=translation_likes, comment_likes=comment_likes, author_likes=author_likes, correction_likes=correction_likes, recent_author_likes=recent_author_likes, AuthorLike=AuthorLike, Like=Like, TrustedTranslator=TrustedTranslator, Friend=Friend)

@app.route('/profile/edit', methods=['GET', 'POST'])
def edit_profile():
    if not is_logged_in():
        return redirect(url_for('login'))
    user = get_current_user()
    if request.method == 'POST':
        # 处理用户名更新
        new_username = request.form.get('username', '').strip()
        if new_username and new_username != user.username:
            # 检查用户名是否已存在
            existing_user = User.query.filter_by(username=new_username).first()
            if existing_user and existing_user.id != user.id:
                flash(get_message('username_exists'), 'error')
                return render_template('edit_profile.html', user=user)
            user.username = new_username
            # 更新session中的用户名
            session['username'] = new_username
        
        # 处理邮箱更新
        new_email = request.form.get('email', '').strip()
        if new_email and new_email != user.email:
            # 检查邮箱是否已存在（管理员邮箱除外）
            if new_email != 'lafengnidaye@gmail.com':
                existing_user = User.query.filter_by(email=new_email).first()
                if existing_user and existing_user.id != user.id:
                    flash(get_message('email_exists'), 'error')
                    return render_template('edit_profile.html', user=user)
            user.email = new_email
        
        # 处理个人简介
        bio = request.form.get('bio', '')
        user.bio = bio
        
        # 处理邮件通知开关
        email_flag = request.form.get('email_notifications_enabled')
        user.email_notifications_enabled = True if email_flag else False

        # 处理语言设置
        preferred_language = request.form.get('preferred_language', 'zh')
        user.preferred_language = preferred_language
        # 直接更新session中的语言设置
        session['lang'] = preferred_language
        
        # 处理头像上传
        file = request.files.get('avatar')
        if file and file.filename:
            filename = secure_filename(file.filename)
            ext = filename.rsplit('.', 1)[-1].lower()
            avatar_filename = f"avatar_{user.id}.{ext}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], avatar_filename))
            user.avatar = avatar_filename
        
        db.session.commit()
        
        # 更新session中的语言设置
        session['lang'] = preferred_language
        
        flash(get_message('profile_updated'), 'success')
        return redirect(url_for('profile'))
    return render_template('edit_profile.html', user=user)

@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if not is_logged_in():
        return redirect(url_for('login'))
    
    user = get_current_user()
    
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # 验证当前密码
        if not check_password_hash(user.password_hash, current_password):
            flash(get_message('current_password_incorrect'), 'error')
            return render_template('change_password.html')
        
        # 验证新密码长度
        if len(new_password) < 8:
            flash(get_message('password_too_short'), 'error')
            return render_template('change_password.html')
        
        # 验证新密码确认
        if new_password != confirm_password:
            flash(get_message('password_mismatch'), 'error')
            return render_template('change_password.html')
        
        # 更新密码
        user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        
        flash(get_message('password_changed'), 'success')
        return redirect(url_for('profile'))
    
    return render_template('change_password.html')

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if not is_logged_in():
        flash(get_message('please_login'), 'error')
        return redirect(url_for('login'))
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        original_language = request.form['original_language']
        target_language = request.form['target_language']
        category = request.form['category']
        
        # 验证必填字段
        if not category or category.strip() == '':
            flash(get_message('category_required'), 'error')
            user = get_current_user()
            return render_template('upload.html', user=user)
        
        # 验证原始语言和目标语言不能相同（除了"其他"）
        if original_language == target_language and original_language != '其他':
            flash(get_message('languages_cannot_be_same'), 'error')
            user = get_current_user()
            return render_template('upload.html', user=user)
        media_filename = None
        file = request.files.get('media_file')
        if file and file.filename:
            filename = secure_filename(file.filename)
            ext = filename.rsplit('.', 1)[-1].lower()
            media_filename = f"work_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{session['user_id']}.{ext}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], media_filename))
        translation_requirements = request.form.get('translation_requirements', '')
        translation_expectation = request.form.get('translation_expectation', '')
        contact_before_translate = request.form.get('contact_before_translate') == 'on' # 修正布尔类型
        allow_multiple_translators = request.form.get('allow_multiple_translators') == 'on' # 允许多人翻译
        work = Work(
            title=title,
            content=content,
            original_language=original_language,
            target_language=target_language,
            category=category,
            creator_id=session['user_id'],
            media_filename=media_filename,
            translation_requirements=translation_requirements,
            translation_expectation=translation_expectation,
            contact_before_translate=contact_before_translate, # 保存勾选状态
            allow_multiple_translators=allow_multiple_translators # 保存允许多人翻译状态
        )
        db.session.add(work)
        
        # 检查用户是否还没有创作者称号，如果有作品则自动获得
        user = get_current_user()
        if not user.is_creator:
            user.is_creator = True
        
        db.session.commit()
        flash(get_message('upload_success'), 'success')
        return redirect(url_for('work_detail', work_id=work.id))
    user = get_current_user()
    return render_template('upload.html', user=user)

@app.route('/work/<int:work_id>', methods=['GET', 'POST'])
def work_detail(work_id):
    work = Work.query.get_or_404(work_id)
    # 获取所有翻译（支持多人翻译）
    translations = Translation.query.filter_by(work_id=work_id).order_by(Translation.created_at.desc()).all()
    # 为了向后兼容，保留translation变量（取第一个翻译）
    translation = translations[0] if translations else None
    comments = Comment.query.filter_by(work_id=work_id).order_by(Comment.created_at.desc()).all()
    current_user = get_current_user()
    translation_requests = []
    # 查找已同意的请求，显示翻译者的要求（无论谁访问都查找）
    approved_req = TranslationRequest.query.filter_by(work_id=work_id, status='approved').first()
    translator_expectation = approved_req.content if approved_req else None
    
    # 查找已同意的一般要求，显示翻译者的要求（无论谁访问都查找）
    approved_general_req = TranslatorRequest.query.filter_by(work_id=work_id, status='approved').first()
    general_expectation = approved_general_req.content if approved_general_req else None
    
    # 为当前用户查找已同意的翻译请求（用于模板中的权限检查）
    current_user_approved_req = None
    current_user_approved_translator_req = None
    if current_user:
        current_user_approved_req = TranslationRequest.query.filter_by(work_id=work_id, translator_id=current_user.id, status='approved').first()
        current_user_approved_translator_req = TranslatorRequest.query.filter_by(work_id=work_id, translator_id=current_user.id, status='approved').first()
    if current_user and work.creator_id == current_user.id:
        translation_requests = TranslationRequest.query.filter_by(work_id=work_id, status='pending').all()
        translator_requests = TranslatorRequest.query.filter_by(work_id=work_id, status='pending').all()
    else:
        translator_requests = []
    if request.method == 'POST':
        if 'add_comment' in request.form:
            if not current_user:
                flash(get_message('please_login'), 'error')
                return redirect(url_for('login'))
            content = request.form['content']
            comment = Comment(
                content=content,
                author_id=current_user.id,
                work_id=work_id
            )
            db.session.add(comment)
            
            # 发送评论通知给作品作者
            if work.creator_id != current_user.id:
                message_content = get_system_message('work_comment_received', work.creator_id,
                                                   commenter_name=current_user.username,
                                                   work_title=work.title,
                                                   comment_content=content)
                
                system_message = Message(
                    sender_id=1,  # 系统用户ID
                    receiver_id=work.creator_id,
                    content=message_content,
                    type='system',
                    work_id=work_id
                )
                db.session.add(system_message)
                
                # 发送邮件通知
                creator_user = User.query.get(work.creator_id)
                if creator_user and creator_user.email_notifications_enabled:
                    from mail_utils import send_email
                    # 使用作者的语言偏好
                    creator_lang = getattr(creator_user, 'preferred_language', 'zh') or 'zh'
                    subject = get_message('comment_notification', lang=creator_lang)
                    
                    # 发送简洁的纯文本邮件
                    send_email(creator_user.email, subject, message_content, message_type='system', user_lang=creator_lang)
            
            db.session.commit()
            flash(get_message('comment_success'), 'success')
        # 移除重复的翻译提交处理逻辑，翻译提交应该通过专门的翻译页面处理
        # elif 'submit_translation' in request.form:
        #     # 这个逻辑已经移到 handle_translation_submit 函数中处理
        #     pass
        return redirect(url_for('work_detail', work_id=work_id))
    # 获取作者的统计信息
    author = work.creator
    author_stats = {
        'works_count': Work.query.filter_by(creator_id=author.id).count(),
        'translations_count': Translation.query.filter_by(translator_id=author.id).count(),
        'comments_count': Comment.query.filter_by(author_id=author.id).count(),
        'total_likes': 0
    }
    
    # 计算作者获得的总点赞数
    for work_item in author.works:
        author_stats['total_likes'] += Like.query.filter_by(target_type='work', target_id=work_item.id).count()
    
    for translation in author.translations:
        author_stats['total_likes'] += Like.query.filter_by(target_type='translation', target_id=translation.id).count()
    
    for comment in author.comments:
        author_stats['total_likes'] += Like.query.filter_by(target_type='comment', target_id=comment.id).count()
    
    # 获取校正数据（获取所有翻译的校正）
    corrections = []
    if translations:
        # 获取所有翻译的校正
        for translation_item in translations:
            translation_corrections = Correction.query.filter_by(translation_id=translation_item.id).order_by(Correction.created_at.desc()).all()
            corrections.extend(translation_corrections)
        # 按创建时间排序
        corrections.sort(key=lambda x: x.created_at, reverse=True)
    
    return render_template('work_detail.html', work=work, translation=translation, translations=translations, comments=comments, current_user=current_user, translation_requests=translation_requests, translator_requests=translator_requests, translator_expectation=translator_expectation, general_expectation=general_expectation, approved_req=approved_req, approved_general_req=approved_general_req, current_user_approved_req=current_user_approved_req, current_user_approved_translator_req=current_user_approved_translator_req, author_stats=author_stats, corrections=corrections, CorrectionLike=CorrectionLike, Like=Like, AuthorLike=AuthorLike, Comment=Comment)

@app.route('/work/<int:work_id>/translate', methods=['GET', 'POST'])
def translate_work(work_id):
    work = Work.query.get_or_404(work_id)
    current_user = get_current_user()
    
    # 检查是否被作者信任
    trusted = TrustedTranslator.query.filter_by(user_id=work.creator_id, translator_id=current_user.id).first()
    
    # 如果被信赖，直接允许翻译（即使不是翻译者）
    if trusted:
        translation = Translation.query.filter_by(work_id=work_id).first()
        if request.method == 'POST':
            return handle_translation_submit(work_id, current_user)
        return render_template('translate.html', work=work, translation=translation)
    
    # 如果未被信赖，则必须要是翻译者
    if not current_user or not current_user.is_translator:
        flash(get_message('only_translator'), 'error')
        return redirect(url_for('work_detail', work_id=work_id))
    
    # 检查是否有已同意的请求（包括TranslationRequest和TranslatorRequest）
    approved_req = TranslationRequest.query.filter_by(work_id=work_id, translator_id=current_user.id, status='approved').first()
    approved_translator_req = TranslatorRequest.query.filter_by(work_id=work_id, translator_id=current_user.id, status='approved').first()
    
    # 调试信息
    print(f"DEBUG: work_id={work_id}, translator_id={current_user.id}")
    print(f"DEBUG: approved_req={approved_req}")
    print(f"DEBUG: approved_translator_req={approved_translator_req}")
    print(f"DEBUG: work.status={work.status}")
    
    if approved_req or approved_translator_req:
        print(f"DEBUG: Found approved request, allowing translation")
        translation = Translation.query.filter_by(work_id=work_id).first()
        if request.method == 'POST':
            return handle_translation_submit(work_id, current_user)
        return render_template('translate.html', work=work, translation=translation)
    
    # 检查作品是否已经在翻译中（只有在没有已同意请求且不允许多人翻译的情况下才检查）
    if work.status == 'translating' and not work.allow_multiple_translators:
        flash(get_message('work_already_translating'), 'warning')
        return redirect(url_for('work_detail', work_id=work_id))
    
    # 检查是否从确认页面跳转过来（没有填写期待/要求的情况）
    session_key = f'confirm_translate_{work_id}'
    if session.get(session_key):
        # 清除session标记
        session.pop(session_key, None)
        translation = Translation.query.filter_by(work_id=work_id).first()
        if request.method == 'POST':
            return handle_translation_submit(work_id, current_user)
        return render_template('translate.html', work=work, translation=translation)
    
    # 检查是否有未被同意的请求（包括TranslationRequest和TranslatorRequest）
    req = TranslationRequest.query.filter_by(work_id=work_id, translator_id=current_user.id, status='pending').first()
    translator_req = TranslatorRequest.query.filter_by(work_id=work_id, translator_id=current_user.id, status='pending').first()
    if req or translator_req:
        flash(get_message('wait_author_approval'), 'warning')
        return redirect(url_for('work_detail', work_id=work_id))
    
    # 若作品要求私信且未被信任，则不允许翻译
    if work.contact_before_translate:
        flash(get_message('contact_author_first'), 'warning')
        return redirect(url_for('work_detail', work_id=work_id))
    
    # 其他情况允许翻译
    # 检查当前用户是否已有翻译（排除被拒绝的翻译）
    current_user_translation = None
    if current_user:
        current_user_translation = Translation.query.filter_by(work_id=work_id, translator_id=current_user.id).filter(Translation.status != 'rejected').first()
    
    if request.method == 'POST':
        return handle_translation_submit(work_id, current_user)
    return render_template('translate.html', work=work, translation=current_user_translation)

def handle_translation_submit(work_id, current_user):
    work = Work.query.get_or_404(work_id)
    
    if 'submit' in request.form:
        # 提交翻译
        content = request.form.get('content', '').strip()
        if not content:
            flash(get_message('translation_content_required'), 'error')
            return redirect(url_for('translate_work', work_id=work_id))
        
        # 处理多媒体文件上传
        media_filename = None
        file = request.files.get('media')
        if file and file.filename:
            filename = secure_filename(file.filename)
            ext = filename.rsplit('.', 1)[-1].lower()
            media_filename = f"translation_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{current_user.id}.{ext}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], media_filename))
        
        # 检查是否已有翻译（当前用户的翻译，排除被拒绝的翻译）
        existing_translation = Translation.query.filter_by(work_id=work_id, translator_id=current_user.id).filter(Translation.status != 'rejected').first()
        
        # 如果作品允许多人翻译，或者当前用户还没有有效翻译，则允许创建新翻译
        if work.allow_multiple_translators or not existing_translation:
            if existing_translation:
                # 更新现有翻译
                existing_translation.content = content
                existing_translation.status = 'submitted'
                existing_translation.updated_at = datetime.utcnow()
                if media_filename:
                    existing_translation.media_filename = media_filename
            else:
                # 创建新翻译
                translation = Translation(
                    work_id=work_id,
                    translator_id=current_user.id,
                    content=content,
                    status='submitted',
                    media_filename=media_filename
                )
                db.session.add(translation)
        else:
            # 如果不允许多人翻译且已有其他翻译，则不允许
            flash(get_message('only_one_translation_allowed'), 'error')
            return redirect(url_for('translate_work', work_id=work_id))
        
        # 更新作品状态
        work.status = 'translating'
        work.updated_at = datetime.utcnow()
        
                # 发送系统消息给作者
        if work.creator_id != current_user.id:  # 避免给自己发送消息
            # 创建系统消息（用于平台内显示，但不触发邮件）
            system_message = Message(
                sender_id=1,  # 系统用户ID
                receiver_id=work.creator_id,
                content=get_system_message('translation_submitted_to_author', work.creator_id, 
                                        translator_name=current_user.username, 
                                        work_title=work.title,
                                        work_id=work.id),
                type='system',
                work_id=work.id
            )
            db.session.add(system_message)
            
            # 检查是否需要发送邮件通知
            author_user = User.query.get(work.creator_id)
            if author_user and author_user.email_notifications_enabled:
                # 直接发送邮件，不创建额外的系统消息
                from mail_utils import send_email
                # 使用作者的语言偏好
                author_lang = getattr(author_user, 'preferred_language', 'zh') or 'zh'
                subject = get_message('new_translation_submitted', lang=author_lang)
                body = get_system_message('translation_submitted_to_author', work.creator_id, 
                                        translator_name=current_user.username, 
                                        work_title=work.title, 
                                        work_id=work.id)
                
                # 发送简洁的纯文本邮件
                send_email(author_user.email, subject, body, message_type='translation', user_lang=author_lang)
                
                # 标记这个系统消息已经发送过邮件，避免重复发送
                system_message._email_sent = True
        
        db.session.commit()
        flash(get_message('translate_success'), 'success')
        return redirect(url_for('work_detail', work_id=work_id))
    
    elif 'save_draft' in request.form:
        # 保存草稿
        content = request.form.get('content', '').strip()
        
        # 处理多媒体文件上传
        media_filename = None
        file = request.files.get('media')
        if file and file.filename:
            filename = secure_filename(file.filename)
            ext = filename.rsplit('.', 1)[-1].lower()
            media_filename = f"translation_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{current_user.id}.{ext}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], media_filename))
        
        # 检查是否已有翻译（排除被拒绝的翻译）
        existing_translation = Translation.query.filter_by(work_id=work_id, translator_id=current_user.id).filter(Translation.status != 'rejected').first()
        if existing_translation:
            # 更新现有翻译
            existing_translation.content = content
            existing_translation.status = 'draft'
            existing_translation.updated_at = datetime.utcnow()
            if media_filename:
                existing_translation.media_filename = media_filename
        else:
            # 创建新翻译
            translation = Translation(
                work_id=work_id,
                translator_id=current_user.id,
                content=content,
                status='draft',
                media_filename=media_filename
            )
            db.session.add(translation)
        
        db.session.commit()
        flash(get_message('draft_saved'), 'success')
        return redirect(url_for('work_detail', work_id=work_id))
    
    return redirect(url_for('work_detail', work_id=work_id))

@app.route('/work/<int:work_id>/confirm_translate', methods=['GET', 'POST'])
def confirm_translate(work_id):
    work = Work.query.get_or_404(work_id)
    current_user = get_current_user()
    if not current_user or not current_user.is_translator:
        flash(get_message('need_translator_qualification'), 'error')
        return redirect(url_for('work_detail', work_id=work_id))
    
    # 检查作品是否已经在翻译中
    if work.status == 'translating':
        # 检查当前用户是否有已同意的翻译请求（包括TranslationRequest和TranslatorRequest）
        approved_req = TranslationRequest.query.filter_by(work_id=work_id, translator_id=current_user.id, status='approved').first()
        approved_translator_req = TranslatorRequest.query.filter_by(work_id=work_id, translator_id=current_user.id, status='approved').first()
        if not approved_req and not approved_translator_req:
            flash(get_message('work_already_translating'), 'warning')
            return redirect(url_for('work_detail', work_id=work_id))
    
    # 检查是否被作者信任
    trusted = TrustedTranslator.query.filter_by(user_id=work.creator_id, translator_id=current_user.id).first()
    
    submitted = False
    author_expectation = work.translation_expectation
    author_requirement = work.translation_requirements
    translator_expectation = None
    
    # 查找已同意的请求（包括TranslationRequest和TranslatorRequest）
    approved_req = TranslationRequest.query.filter_by(work_id=work_id, translator_id=current_user.id, status='approved').first()
    approved_translator_req = TranslatorRequest.query.filter_by(work_id=work_id, translator_id=current_user.id, status='approved').first()
    if approved_req:
        translator_expectation = approved_req.content
    elif approved_translator_req:
        translator_expectation = approved_translator_req.content
    
    if request.method == 'POST':
        action_type = request.form.get('action_type', 'request')
        expectation = request.form.get('content', '').strip()
        
        # 如果选择直接翻译且没有填写期待/要求，直接进入翻译页面
        # 注意：即使选择直接翻译，如果作品有翻译要求，仍然需要确认
        if action_type == 'direct' and not expectation:
            session[f'confirm_translate_{work_id}'] = True
            return redirect(url_for('translate_work', work_id=work_id))
        
        # 检查是否已存在待处理请求（包括TranslationRequest和TranslatorRequest）
        existing_req = TranslationRequest.query.filter_by(work_id=work_id, translator_id=current_user.id, status='pending').first()
        existing_translator_req = TranslatorRequest.query.filter_by(work_id=work_id, translator_id=current_user.id, status='pending').first()
        if existing_req or existing_translator_req:
            submitted = True
        else:
            # 创建请求
            tr = TranslationRequest(
                work_id=work_id,
                translator_id=current_user.id,
                author_id=work.creator_id,
                content=expectation,
                status='pending'
            )
            db.session.add(tr)
            db.session.commit()
            
            # 发送邮件通知给作者（不创建系统消息，因为已有卡片提醒）
            author_user = User.query.get(work.creator_id)
            if author_user and author_user.email_notifications_enabled:
                # 直接发送邮件，不创建系统消息
                from mail_utils import send_email
                # 使用作者的语言偏好
                author_lang = getattr(author_user, 'preferred_language', 'zh') or 'zh'
                subject = get_message('new_translation_request', lang=author_lang)
                body = get_system_message('translation_request_to_author', work.creator_id,
                                        translator_name=current_user.username,
                                        work_title=work.title,
                                        expectation=expectation)
                
                # 发送简洁的纯文本邮件
                send_email(author_user.email, subject, body, message_type='translation', user_lang=author_lang)
            
            submitted = True
        
        return render_template('confirm_translate.html', work=work, submitted=submitted, author_expectation=author_expectation, author_requirement=author_requirement, translator_expectation=translator_expectation)
    
    return render_template('confirm_translate.html', work=work, submitted=submitted, author_expectation=author_expectation, author_requirement=author_requirement, translator_expectation=translator_expectation)

@app.route('/work/<int:work_id>/make_request', methods=['GET', 'POST'])
def make_request(work_id):
    work = Work.query.get_or_404(work_id)
    current_user = get_current_user()
    if not current_user or not current_user.is_translator:
        flash(get_message('need_translator_qualification'), 'error')
        return redirect(url_for('work_detail', work_id=work_id))
    
    # 检查是否被作者信任
    trusted = TrustedTranslator.query.filter_by(user_id=work.creator_id, translator_id=current_user.id).first()
    
    submitted = False
    
    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        
        if not content:
            flash(get_message('request_content_required') if get_message('request_content_required') else '请输入您的要求内容', 'error')
            return render_template('make_request.html', work=work, submitted=submitted)
        
        # 检查是否已存在待处理请求（包括TranslationRequest和TranslatorRequest）
        existing_req = TranslatorRequest.query.filter_by(work_id=work_id, translator_id=current_user.id, status='pending').first()
        existing_translation_req = TranslationRequest.query.filter_by(work_id=work_id, translator_id=current_user.id, status='pending').first()
        if existing_req or existing_translation_req:
            submitted = True
        else:
            # 创建请求
            tr = TranslatorRequest(
                work_id=work_id,
                translator_id=current_user.id,
                author_id=work.creator_id,
                content=content,
                status='pending'
            )
            db.session.add(tr)
            db.session.commit()
            
            # 发送邮件通知给作者（不创建系统消息，因为已有卡片提醒）
            author_user = User.query.get(work.creator_id)
            if author_user and author_user.email_notifications_enabled:
                # 直接发送邮件，不创建系统消息
                from mail_utils import send_email
                # 使用作者的语言偏好
                author_lang = getattr(author_user, 'preferred_language', 'zh') or 'zh'
                subject = get_message('new_translator_request', lang=author_lang)
                body = get_system_message('translator_request_received', work.creator_id,
                                        translator_name=current_user.username,
                                        work_title=work.title)
                
                # 发送简洁的纯文本邮件
                send_email(author_user.email, subject, body, message_type='translation', user_lang=author_lang)
            
            submitted = True
        
        return render_template('make_request.html', work=work, submitted=submitted)
    
    return render_template('make_request.html', work=work, submitted=submitted)

@app.route('/work/<int:work_id>/approve_request/<int:req_id>', methods=['POST'])
def approve_translation_request(work_id, req_id):
    current_user = get_current_user()
    if not current_user:
        flash(get_message('please_login'), 'error')
        return redirect(url_for('message_list'))
    
    req = TranslationRequest.query.get_or_404(req_id)
    if req.author_id != current_user.id:
        flash(get_message('no_permission_request'), 'error')
        return redirect(url_for('message_list'))
    
    if req.status != 'pending':
        flash(get_message('request_processed'), 'info')
        return redirect(url_for('message_list'))
    
    req.status = 'approved'
    
    # 获取作品并更新状态为翻译中
    work = Work.query.get_or_404(work_id)
    work.status = 'translating'
    
    # 发送系统消息给翻译者通知请求被同意
    translator_user = User.query.get(req.translator_id)
    if translator_user and translator_user.email_notifications_enabled:
        system_message = Message(
            sender_id=1,  # 系统用户ID
            receiver_id=req.translator_id,
            content=get_system_message('request_approved_to_translator', req.translator_id, 
                                    author_name=current_user.username, 
                                    work_title=work.title,
                                    work_id=work.id),
            type='system',
            work_id=work.id
        )
        db.session.add(system_message)
    
    db.session.commit()
    
    flash(get_message('request_approved'), 'success')
    
    # 检查来源，如果是从作品详情页面来的，则不跳转
    source = request.form.get('source')
    if source == 'work_detail':
        return redirect(url_for('work_detail', work_id=work_id))
    else:
        return redirect(url_for('message_list'))

@app.route('/work/<int:work_id>/reject_request/<int:req_id>', methods=['POST'])
def reject_translation_request(work_id, req_id):
    current_user = get_current_user()
    if not current_user:
        flash(get_message('please_login'), 'error')
        return redirect(url_for('message_list'))
    
    req = TranslationRequest.query.get_or_404(req_id)
    if req.author_id != current_user.id:
        flash(get_message('no_permission_request'), 'error')
        return redirect(url_for('message_list'))
    
    if req.status != 'pending':
        flash(get_message('request_processed'), 'info')
        return redirect(url_for('message_list'))
    
    req.status = 'rejected'
    
    # 获取作品信息
    work = Work.query.get_or_404(work_id)
    
    # 发送系统消息给翻译者通知请求被拒绝
    translator_user = User.query.get(req.translator_id)
    if translator_user and translator_user.email_notifications_enabled:
        system_message = Message(
            sender_id=1,  # 系统用户ID
            receiver_id=req.translator_id,
            content=get_system_message('request_rejected_to_translator', req.translator_id, 
                                    author_name=current_user.username, 
                                    work_title=work.title,
                                    work_id=work.id),
            type='system',
            work_id=work.id
        )
        db.session.add(system_message)
    
    db.session.commit()
    
    flash(get_message('request_rejected'), 'info')
    
    # 检查来源，如果是从作品详情页面来的，则不跳转
    source = request.form.get('source')
    if source == 'work_detail':
        return redirect(url_for('work_detail', work_id=work_id))
    else:
        return redirect(url_for('message_list'))

@app.route('/work/<int:work_id>/approve_translator_request/<int:req_id>', methods=['POST'])
def approve_translator_request(work_id, req_id):
    print(f"DEBUG: Entering approve_translator_request with work_id={work_id}, req_id={req_id}")  # 调试输出
    current_user = get_current_user()
    if not current_user:
        flash(get_message('please_login'), 'error')
        return redirect(url_for('message_list'))
    
    req = TranslatorRequest.query.get_or_404(req_id)
    if req.author_id != current_user.id:
        flash(get_message('no_permission_request'), 'error')
        return redirect(url_for('message_list'))
    
    if req.status != 'pending':
        flash(get_message('request_processed'), 'info')
        return redirect(url_for('message_list'))
    
    req.status = 'approved'
    req.responded_at = datetime.utcnow()
    
    # 获取作品并更新状态为翻译中
    work = Work.query.get_or_404(work_id)
    work.status = 'translating'
    
    # 调试信息
    print(f"DEBUG: Updated TranslatorRequest {req_id} status to 'approved'")
    print(f"DEBUG: Updated work {work_id} status to 'translating'")
    print(f"DEBUG: req.translator_id={req.translator_id}, req.work_id={req.work_id}")
    
    # 发送系统消息给翻译者通知请求被同意
    translator_user = User.query.get(req.translator_id)
    if translator_user and translator_user.email_notifications_enabled:
        system_message = Message(
            sender_id=1,  # 系统用户ID
            receiver_id=req.translator_id,
            content=get_system_message('request_approved_to_translator', req.translator_id, 
                                    author_name=current_user.username, 
                                    work_title=work.title,
                                    work_id=work.id),
            type='system',
            work_id=work.id
        )
        db.session.add(system_message)
    
    db.session.commit()
    
    flash(get_message('translator_request_approved_msg') if get_message('translator_request_approved_msg') else '已同意翻译者的要求', 'success')
    
    # 检查来源，如果是从作品详情页面来的，则重定向回作品详情页面
    source = request.form.get('source')
    print(f"DEBUG approve: source = {source}")  # 调试输出
    if source == 'work_detail':
        print(f"DEBUG approve: Redirecting to work_detail page")  # 调试输出
        return redirect(url_for('work_detail', work_id=work_id))
    else:
        print(f"DEBUG approve: Redirecting to message_list page")  # 调试输出
        return redirect(url_for('message_list'))

@app.route('/work/<int:work_id>/reject_translator_request/<int:req_id>', methods=['POST'])
def reject_translator_request(work_id, req_id):
    print(f"DEBUG: Entering reject_translator_request with work_id={work_id}, req_id={req_id}")  # 调试输出
    current_user = get_current_user()
    if not current_user:
        flash(get_message('please_login'), 'error')
        return redirect(url_for('message_list'))
    
    req = TranslatorRequest.query.get_or_404(req_id)
    if req.author_id != current_user.id:
        flash(get_message('no_permission_request'), 'error')
        return redirect(url_for('message_list'))
    
    if req.status != 'pending':
        flash(get_message('request_processed'), 'info')
        return redirect(url_for('message_list'))
    
    req.status = 'rejected'
    req.responded_at = datetime.utcnow()
    
    # 获取作品信息
    work = Work.query.get_or_404(work_id)
    
    # 发送系统消息给翻译者通知请求被拒绝
    translator_user = User.query.get(req.translator_id)
    if translator_user and translator_user.email_notifications_enabled:
        system_message = Message(
            sender_id=1,  # 系统用户ID
            receiver_id=req.translator_id,
            content=get_system_message('request_rejected_to_translator', req.translator_id, 
                                    author_name=current_user.username, 
                                    work_title=work.title,
                                    work_id=work.id),
            type='system',
            work_id=work.id
        )
        db.session.add(system_message)
    
    db.session.commit()
    
    flash(get_message('translator_request_rejected_msg') if get_message('translator_request_rejected_msg') else '已拒绝翻译者的要求', 'info')
    
    # 检查来源，如果是从作品详情页面来的，则重定向回作品详情页面
    source = request.form.get('source')
    print(f"DEBUG reject: source = {source}")  # 调试输出
    if source == 'work_detail':
        print(f"DEBUG reject: Redirecting to work_detail page")  # 调试输出
        return redirect(url_for('work_detail', work_id=work_id))
    else:
        print(f"DEBUG reject: Redirecting to message_list page")  # 调试输出
        return redirect(url_for('message_list'))



@app.route('/admin')
def admin_panel():
    if not has_role('admin'):
        flash(get_message('no_admin_permission'), 'error')
        return redirect(url_for('index'))
    
    # 过滤掉admin账号，不显示在用户列表中
    users = User.query.filter(User.username != 'admin').all()
    works = Work.query.all()
    translations = Translation.query.all()
    
    # 计算匹配速度和匹配率统计（排除seed_data的帖子，ID为1和2）
    # 排除seed_data的作品
    non_seed_works = Work.query.filter(~Work.id.in_([1, 2])).all()
    
    # 计算匹配率：已翻译作品的比例
    completed_works = [work for work in non_seed_works if work.status == 'completed']
    match_rate = len(completed_works) / len(non_seed_works) * 100 if non_seed_works else 0
    
    # 计算匹配速度：从发帖到翻译完成的时间
    match_speeds = []
    for work in completed_works:
        # 找到该作品最早的已通过翻译
        earliest_translation = Translation.query.filter_by(
            work_id=work.id, 
            status='approved'
        ).order_by(Translation.created_at.asc()).first()
        
        if earliest_translation:
            # 计算从发帖到翻译完成的时间差（小时）
            time_diff = earliest_translation.created_at - work.created_at
            hours = time_diff.total_seconds() / 3600
            match_speeds.append(hours)
    
    # 计算平均匹配速度
    avg_match_speed = sum(match_speeds) / len(match_speeds) if match_speeds else 0
    
    # 统计信息
    stats = {
        'total_works': len(non_seed_works),
        'completed_works': len(completed_works),
        'match_rate': round(match_rate, 2),
        'avg_match_speed': round(avg_match_speed, 2),
        'match_speeds': match_speeds
    }
    
    return render_template('admin.html', users=users, works=works, translations=translations, 
                         current_user=get_current_user(), stats=stats)

@app.route('/admin/user/<int:user_id>/toggle_role')
def toggle_user_role(user_id):
    current_user = get_current_user()
    
    # 只有admin账号才能使用此功能
    if not current_user or current_user.username != 'admin':
        flash(get_message('no_admin_permission'), 'error')
        return redirect(url_for('index'))
    
    user = User.query.get_or_404(user_id)
    if user.role == 'admin':
        user.role = 'user'
    else:
        user.role = 'admin'
    
    db.session.commit()
    flash(get_message('role_updated').format(user.username), 'success')
    return redirect(url_for('admin_panel'))

@app.route('/api/search')
def api_search():
    query = request.args.get('q', '')
    if not query:
        return jsonify([])
    
    works = Work.query.filter(
        Work.title.contains(query) | Work.content.contains(query)
    ).limit(10).all()
    
    results = []
    for work in works:
        results.append({
            'id': work.id,
            'title': work.title,
            'category': work.category,
            'status': work.status
        })
    
    return jsonify(results)

@app.route('/api/search_users')
def api_search_users():
    query = request.args.get('q', '')
    if not query:
        return jsonify([])
    
    # 检查是否为数字ID
    if query.isdigit():
        # 如果是数字，同时搜索ID和用户名
        results = []
        seen_ids = set()  # 用于去重
        
        # 1. 按ID搜索
        user_by_id = User.query.get(int(query))
        if user_by_id and user_by_id.username != 'system':
            results.append({
                'id': user_by_id.id,
                'username': user_by_id.username,
                'avatar': user_by_id.avatar,
                'role': user_by_id.role,
                'is_translator': user_by_id.is_translator,
                'is_reviewer': user_by_id.is_reviewer,
                'is_creator': user_by_id.is_creator
            })
            seen_ids.add(user_by_id.id)
        
        # 2. 按用户名搜索（精确匹配）
        users_by_username = User.query.filter(
            User.username == query,
            User.username != 'system'
        ).all()
        
        for user in users_by_username:
            if user.id not in seen_ids:
                results.append({
                    'id': user.id,
                    'username': user.username,
                    'avatar': user.avatar,
                    'role': user.role,
                    'is_translator': user.is_translator,
                    'is_reviewer': user.is_reviewer,
                    'is_creator': user.is_creator
                })
                seen_ids.add(user.id)
    else:
        # 如果不是数字，按用户名搜索
        users = User.query.filter(
            User.username.contains(query),
            User.username != 'system'
        ).limit(10).all()
        
        results = []
        for user in users:
            results.append({
                'id': user.id,
                'username': user.username,
                'avatar': user.avatar,
                'role': user.role,
                'is_translator': user.is_translator,
                'is_reviewer': user.is_reviewer,
                'is_creator': user.is_creator
            })
    
    return jsonify(results)

@app.route('/setlang/<lang>')
def set_language(lang):
    if lang in ['zh', 'ja', 'en', 'ru', 'ko', 'fr']:
        session['lang'] = lang
        # 如果用户已登录，同时更新用户的偏好语言设置
        if is_logged_in():
            user = get_current_user()
            user.preferred_language = lang
            db.session.commit()
    return redirect(request.referrer or url_for('index'))

@app.route('/messages/unread_count')
def unread_message_count():
    if not is_logged_in():
        return jsonify({'count': 0})
    user = get_current_user()
    
    # 计算未读消息数量
    unread_messages = Message.query.filter_by(receiver_id=user.id, is_read=False).count()
    
    # 计算未处理的翻译请求数量
    pending_translation_requests = TranslationRequest.query.filter_by(
        author_id=user.id, 
        status='pending'
    ).count()
    
    # 计算未处理的翻译者请求数量
    pending_translator_requests = TranslatorRequest.query.filter_by(
        author_id=user.id, 
        status='pending'
    ).count()
    
    # 计算未处理的好友请求数量
    pending_friend_requests = Friend.query.filter_by(
        friend_id=user.id, 
        status='pending'
    ).count()
    
    # 总计数 = 未读消息 + 未处理翻译请求 + 未处理翻译者请求 + 未处理好友请求
    total_count = unread_messages + pending_translation_requests + pending_translator_requests + pending_friend_requests
    
    return jsonify({'count': total_count})

@app.route('/messages')
def message_list():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))
    
    # 获取有私信的用户列表，并包含未读消息信息
    users_with_messages = []
    
    # 获取所有与当前用户有私信的用户（只包括private类型的消息）
    users = db.session.query(User).join(Message, or_(
        and_(Message.sender_id == User.id, Message.receiver_id == user.id),
        and_(Message.receiver_id == User.id, Message.sender_id == user.id)
    )).filter(
        User.id != user.id,
        Message.type == 'private'
    ).distinct().all()
    
    for u in users:
        # 获取未读消息数量（只统计private类型的消息）
        unread_count = Message.query.filter_by(
            sender_id=u.id, 
            receiver_id=user.id, 
            is_read=False,
            type='private'
        ).count()
        
        # 获取最新消息（只获取private类型的消息）
        latest_message = Message.query.filter(
            or_(
                and_(Message.sender_id == u.id, Message.receiver_id == user.id),
                and_(Message.sender_id == user.id, Message.receiver_id == u.id)
            ),
            Message.type == 'private'
        ).order_by(Message.created_at.desc()).first()
        
        users_with_messages.append({
            'user': u,
            'unread_count': unread_count,
            'latest_message': latest_message,
            'has_unread': unread_count > 0
        })
    
    # 按最新消息时间排序，有未读消息的优先显示
    users_with_messages.sort(key=lambda x: (not x['has_unread'], x['latest_message'].created_at if x['latest_message'] else datetime.min), reverse=True)
    
    # 获取系统消息（只显示未读消息）
    system_messages = Message.query.filter_by(
        receiver_id=user.id, 
        type='system',
        is_read=False
    ).order_by(Message.created_at.desc()).all()
    
    # 只调试包含 friend_request_accepted 的系统消息
    for msg in system_messages:
        if msg.content == 'friend_request_accepted':
            print(f"DEBUG message_list: Found problematic message - ID {msg.id}, content: {msg.content}")
    
    # 获取通知消息（用于点赞等提醒）
    notification_messages = Message.query.filter_by(
        receiver_id=user.id,
        type='notification',
        is_read=False
    ).order_by(Message.created_at.desc()).all()
    
    # 获取待处理的好友请求（只显示发送给当前用户的请求）
    pending_friend_requests = Friend.query.filter_by(
        friend_id=user.id, 
        status='pending'
    ).all()
    
    # 获取待处理的翻译请求
    pending_translation_requests = TranslationRequest.query.filter_by(
        author_id=user.id, 
        status='pending'
    ).all()
    
    # 获取待处理的翻译者请求
    pending_translator_requests = TranslatorRequest.query.filter_by(
        author_id=user.id, 
        status='pending'
    ).all()
    
    return render_template('messages.html', 
                         users_with_messages=users_with_messages, 
                         system_messages=system_messages,
                         notification_messages=notification_messages,
                         pending_friend_requests=pending_friend_requests,
                         pending_translation_requests=pending_translation_requests,
                         pending_translator_requests=pending_translator_requests)

@app.route('/messages/<int:user_id>', methods=['GET', 'POST'])
def conversation(user_id):
    if not is_logged_in():
        return redirect(url_for('login'))
    user = get_current_user()
    other = User.query.get_or_404(user_id)
    if request.method == 'POST':
        content = request.form.get('content', '')
        image_filename = None
        
        # 处理图片上传
        if 'image' in request.files:
            image_file = request.files['image']
            if image_file and image_file.filename:
                # 检查文件类型
                allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                if '.' in image_file.filename and image_file.filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                    # 生成安全的文件名
                    filename = secure_filename(image_file.filename)
                    image_filename = f"msg_img_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{user.id}_{filename}"
                    image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))
                else:
                    flash(get_message('invalid_image_format'), 'error')
                    return redirect(url_for('conversation', user_id=other.id))
        
        # 确保至少有一个内容（文字或图片）
        if not content.strip() and not image_filename:
            flash(get_message('message_content_required'), 'error')
            return redirect(url_for('conversation', user_id=other.id))
        
        msg = Message(
            sender_id=user.id, 
            receiver_id=other.id, 
            content=content, 
            image_filename=image_filename,
            type='private'
        )
        db.session.add(msg)
        db.session.commit()
        flash(get_message('message_sent'), 'success')
        return redirect(url_for('conversation', user_id=other.id))
    # 获取双方的私信消息（不包括系统消息）
    msgs = Message.query.filter(
        ((Message.sender_id==user.id)&(Message.receiver_id==other.id))|
        ((Message.sender_id==other.id)&(Message.receiver_id==user.id))
    ).filter_by(type='private').order_by(Message.created_at.asc()).all()
    # 标记私信为已读
    Message.query.filter_by(receiver_id=user.id, sender_id=other.id, type='private', is_read=False).update({'is_read': True})
    db.session.commit()
    return render_template('conversation.html', other=other, messages=msgs)

@app.route('/user/<int:user_id>')
def user_profile(user_id):
    user = User.query.get_or_404(user_id)
    works = Work.query.filter_by(creator_id=user.id).order_by(Work.created_at.desc()).all()
    translations = Translation.query.filter_by(translator_id=user.id).order_by(Translation.created_at.desc()).all()
    comments = Comment.query.filter_by(author_id=user.id).order_by(Comment.created_at.desc()).all()
    
    # 计算点赞统计
    work_likes = 0
    translation_likes = 0
    comment_likes = 0
    author_likes = 0
    
    # 计算作品点赞数
    for work in user.works:
        work_likes += Like.query.filter_by(target_type='work', target_id=work.id).count()
    
    # 计算翻译点赞数
    for translation in user.translations:
        translation_likes += Like.query.filter_by(target_type='translation', target_id=translation.id).count()
    
    # 计算评论点赞数
    for comment in user.comments:
        comment_likes += Like.query.filter_by(target_type='comment', target_id=comment.id).count()
    
    # 计算作者点赞数（作者对翻译的点赞 + 作者对校正的点赞）
    for translation in user.translations:
        author_likes += AuthorLike.query.filter_by(translation_id=translation.id, correction_id=None).count()
    
    # 计算校正点赞数（只计算普通用户对校正的点赞）
    correction_likes = 0
    for correction in user.corrections:
        # 计算普通点赞数量
        correction_likes += CorrectionLike.query.filter_by(correction_id=correction.id).count()
        # 作者对校正的点赞也计入作者点赞总数
        author_likes += AuthorLike.query.filter_by(translation_id=correction.translation_id, correction_id=correction.id).count()
    
    # 获取最近收到的作者评价
    recent_author_likes = []
    for translation in user.translations:
        # 获取作者对翻译的评价
        translation_author_likes = AuthorLike.query.filter_by(translation_id=translation.id, correction_id=None).all()
        for like in translation_author_likes:
            author = User.query.get(like.author_id)
            if author:
                recent_author_likes.append({
                    'type': 'translation',
                    'author': author,
                    'work': translation.work,
                    'translation': translation,
                    'correction': None,
                    'created_at': like.created_at
                })
    
    # 获取作者对校正的评价
    for correction in user.corrections:
        correction_author_likes = AuthorLike.query.filter_by(translation_id=correction.translation_id, correction_id=correction.id).all()
        for like in correction_author_likes:
            author = User.query.get(like.author_id)
            if author:
                recent_author_likes.append({
                    'type': 'correction',
                    'author': author,
                    'work': correction.translation.work,
                    'translation': correction.translation,
                    'correction': correction,
                    'created_at': like.created_at
                })
    
    # 按时间排序，取最近的5个
    recent_author_likes.sort(key=lambda x: x['created_at'], reverse=True)
    recent_author_likes = recent_author_likes[:5]
    
    # 好友列表
    friends = Friend.query.filter(
        ((Friend.user_id == user.id) | (Friend.friend_id == user.id)) & (Friend.status == 'accepted')
    ).all()
    # 信赖者列表
    trusted = TrustedTranslator.query.filter_by(user_id=user.id).all()
    return render_template('user_profile.html', user=user, works=works, translations=translations, comments=comments, friends=friends, trusted=trusted, work_likes=work_likes, translation_likes=translation_likes, comment_likes=comment_likes, author_likes=author_likes, correction_likes=correction_likes, recent_author_likes=recent_author_likes, AuthorLike=AuthorLike, Like=Like, TrustedTranslator=TrustedTranslator, Friend=Friend)

@app.route('/friends')
def friends_list():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))
    
    # 获取当前用户的好友列表
    friends = Friend.query.filter(
        ((Friend.user_id == user.id) | (Friend.friend_id == user.id)) & (Friend.status == 'accepted')
    ).all()
    
    return render_template('friends_list.html', friends=friends, user=user)

@app.route('/trusted')
def trusted_list():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))
    
    # 获取当前用户信赖的翻译者列表
    trusted = TrustedTranslator.query.filter_by(user_id=user.id).all()
    
    # 获取信赖当前用户的创作者列表
    trusted_by = TrustedTranslator.query.filter_by(translator_id=user.id).all()
    
    return render_template('trusted_list.html', trusted=trusted, trusted_by=trusted_by, user=user)

@app.route('/messages/<int:message_id>/read', methods=['POST'])
def mark_message_read(message_id):
    user = get_current_user()
    if not user:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': '请先登录'})
        return redirect(url_for('login'))
    
    message = Message.query.get_or_404(message_id)
    if message.receiver_id == user.id:
        message.is_read = True
        db.session.commit()
        
        # 如果是AJAX请求，返回JSON响应
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': get_message('message_read')})
        
        flash(get_message('message_read'), 'success')
    
    return redirect(url_for('message_list'))

@app.route('/apply/translator', methods=['GET', 'POST'])
def apply_translator():
    if not is_logged_in():
        return redirect(url_for('login'))
    user = get_current_user()
    if user.is_translator:
        flash(get_message('already_translator'), 'info')
        return redirect(url_for('profile'))
    if request.method == 'POST':
        user.is_translator = True
        db.session.commit()
        flash(get_message('become_translator'), 'success')
        return redirect(url_for('profile'))
    return render_template('apply_translator.html')

@app.route('/apply/reviewer', methods=['GET', 'POST'])
def apply_reviewer():
    if not is_logged_in():
        return redirect(url_for('login'))
    user = get_current_user()
    if not user.is_translator:
        flash(get_message('need_translator_first'), 'warning')
        return redirect(url_for('profile'))
    if user.is_reviewer:
        flash(get_message('already_reviewer'), 'info')
        return redirect(url_for('profile'))
    if request.method == 'POST':
        user.is_reviewer = True
        db.session.commit()
        flash(get_message('become_reviewer'), 'success')
        return redirect(url_for('profile'))
    return render_template('apply_reviewer.html')

@app.route('/apply/admin', methods=['GET', 'POST'])
def apply_admin():
    current_user = get_current_user()
    if not current_user:
        flash(get_message('please_login'), 'error')
        return redirect(url_for('login'))
    
    # 检查是否已经是管理员
    if current_user.role == 'admin':
        flash(get_message('already_admin'), 'info')
        return redirect(url_for('profile'))
    
    # 检查是否已经有待审核的申请
    existing_request = AdminRequest.query.filter_by(user_id=current_user.id, status='pending').first()
    if existing_request:
        flash(get_message('admin_request_pending'), 'warning')
        return redirect(url_for('profile'))
    
    if request.method == 'POST':
        reason = request.form.get('reason', '').strip()
        if not reason:
            flash(get_message('please_enter_reason'), 'error')
            return render_template('apply_admin.html')
        
        # 创建管理员申请
        admin_request = AdminRequest(
            user_id=current_user.id,
            reason=reason
        )
        db.session.add(admin_request)
        db.session.commit()
        
        flash(get_message('admin_request_submitted'), 'success')
        return redirect(url_for('profile'))
    
    return render_template('apply_admin.html')

@app.route('/admin/requests')
def admin_requests():
    current_user = get_current_user()
    if not current_user or current_user.role != 'admin':
        flash(get_message('insufficient_permissions'), 'error')
        return redirect(url_for('index'))
    
    # 获取所有待审核的管理员申请
    pending_requests = AdminRequest.query.filter_by(status='pending').order_by(AdminRequest.created_at.desc()).all()
    approved_requests = AdminRequest.query.filter_by(status='approved').order_by(AdminRequest.reviewed_at.desc()).limit(10).all()
    rejected_requests = AdminRequest.query.filter_by(status='rejected').order_by(AdminRequest.reviewed_at.desc()).limit(10).all()
    
    return render_template('admin_requests.html', 
                         pending_requests=pending_requests,
                         approved_requests=approved_requests,
                         rejected_requests=rejected_requests)

@app.route('/admin/request/<int:request_id>/approve', methods=['POST'])
def approve_admin_request(request_id):
    current_user = get_current_user()
    if not current_user or current_user.role != 'admin':
        flash(get_message('insufficient_permissions'), 'error')
        return redirect(url_for('index'))
    
    admin_request = AdminRequest.query.get_or_404(request_id)
    if admin_request.status != 'pending':
        flash(get_message('request_already_processed'), 'warning')
        return redirect(url_for('admin_requests'))
    
    # 批准申请
    admin_request.status = 'approved'
    admin_request.reviewer_id = current_user.id
    admin_request.reviewed_at = datetime.utcnow()
    admin_request.review_notes = request.form.get('review_notes', '').strip()
    
    # 将用户升级为管理员
    user = User.query.get(admin_request.user_id)
    user.role = 'admin'
    
    db.session.commit()
    
    # 发送系统消息给申请者
    system_message = Message(
        sender_id=1,  # 系统用户ID
        receiver_id=user.id,
        content=get_system_message('admin_request_approved', user.id),
        type='system'
    )
    db.session.add(system_message)
    db.session.commit()
    
    flash(get_message('admin_request_approved').format(user.username), 'success')
    return redirect(url_for('admin_requests'))

@app.route('/admin/request/<int:request_id>/reject', methods=['POST'])
def reject_admin_request(request_id):
    current_user = get_current_user()
    if not current_user or current_user.role != 'admin':
        flash(get_message('insufficient_permissions'), 'error')
        return redirect(url_for('index'))
    
    admin_request = AdminRequest.query.get_or_404(request_id)
    if admin_request.status != 'pending':
        flash(get_message('request_already_processed'), 'warning')
        return redirect(url_for('admin_requests'))
    
    # 拒绝申请
    admin_request.status = 'rejected'
    admin_request.reviewer_id = current_user.id
    admin_request.reviewed_at = datetime.utcnow()
    admin_request.review_notes = request.form.get('review_notes', '').strip()
    
    db.session.commit()
    
    # 发送系统消息给申请者
    user = User.query.get(admin_request.user_id)
    system_message = Message(
        sender_id=1,  # 系统用户ID
        receiver_id=user.id,
        content=get_system_message('admin_request_rejected', user.id),
        type='system'
    )
    db.session.add(system_message)
    db.session.commit()
    
    flash(get_message('admin_request_rejected').format(user.username), 'success')
    return redirect(url_for('admin_requests'))

@app.route('/test/translator', methods=['GET', 'POST'])
def test_translator():
    if not is_logged_in():
        return redirect(url_for('login'))
    user = get_current_user()
    if user.is_translator:
        flash(get_message('already_translator'), 'info')
        return redirect(url_for('profile'))
    if request.method == 'POST':
        user.is_translator = True
        db.session.commit()
        flash(get_message('become_translator'), 'success')
        return redirect(url_for('profile'))
    return render_template('test_translator.html')



@app.route('/work/<int:work_id>/edit', methods=['GET', 'POST'])
def edit_work(work_id):
    work = Work.query.get_or_404(work_id)
    current_user = get_current_user()
    
    # 检查权限：只有作者或管理员可以编辑
    if not current_user or (current_user.id != work.creator_id and current_user.role != 'admin'):
        flash(get_message('no_edit_permission'), 'error')
        return redirect(url_for('work_detail', work_id=work_id))
    
    # 检查作品状态：已完成的作品只有管理员可以编辑
    if work.status == 'completed' and current_user.role != 'admin':
        flash(get_message('completed_work_cannot_edit'), 'error')
        return redirect(url_for('work_detail', work_id=work_id))
    
    # 获取管理员编辑理由
    admin_reason = request.args.get('admin_reason', '')
    
    if request.method == 'POST':
        # 保存原始信息用于发送消息
        original_title = work.title
        work_creator_id = work.creator_id
        work_translators = [t.translator_id for t in work.translations]
        
        work.title = request.form['title']
        work.content = request.form['content']
        original_language = request.form['original_language']
        target_language = request.form['target_language']
        work.original_language = original_language
        work.target_language = target_language
        category = request.form['category']
        
        # 验证必填字段
        if not category or category.strip() == '':
            flash(get_message('category_required'), 'error')
            return render_template('edit_work.html', work=work, admin_reason=admin_reason)
        
        # 验证原始语言和目标语言不能相同（除了"其他"）
        if original_language == target_language and original_language != '其他':
            flash(get_message('languages_cannot_be_same'), 'error')
            return render_template('edit_work.html', work=work, admin_reason=admin_reason)
        
        work.category = category
        work.translation_expectation = request.form.get('translation_expectation', '')
        
        # 处理翻译要求：如果勾选框未选中，则清空翻译要求内容
        show_requirements = request.form.get('show_requirements') == 'on'
        if show_requirements:
            work.translation_requirements = request.form.get('translation_requirements', '')
        else:
            work.translation_requirements = ''
        file = request.files.get('media_file')
        if file and file.filename:
            filename = secure_filename(file.filename)
            ext = filename.rsplit('.', 1)[-1].lower()
            media_filename = f"work_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{current_user.id}.{ext}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], media_filename))
            work.media_filename = media_filename
        
        db.session.commit()
        
        # 如果是管理员编辑，发送消息给作者和翻译者
        if current_user.role == 'admin' and admin_reason:
            # 发送消息给作者
            author_message_content = get_system_message('admin_work_edited', work_creator_id, 
                                                    work_title=work.title, admin_name=current_user.username)
            if admin_reason:
                author_message_content += f"\n\n编辑理由：{admin_reason}"
            
            author_message = Message(
                sender_id=1,  # 系统用户ID
                receiver_id=work_creator_id,
                content=author_message_content,
                type='system',
                work_id=work.id
            )
            db.session.add(author_message)
            
            # 发送消息给所有翻译者
            for translator_id in work_translators:
                if translator_id != work_creator_id:  # 避免重复发送给作者
                    translator_message_content = get_system_message('admin_work_edited', translator_id, 
                                                                work_title=work.title, admin_name=current_user.username)
                    if admin_reason:
                        translator_message_content += f"\n\n编辑理由：{admin_reason}"
                    
                    translator_message = Message(
                        sender_id=1,  # 系统用户ID
                        receiver_id=translator_id,
                        content=translator_message_content,
                        type='system',
                        work_id=work.id
                    )
                    db.session.add(translator_message)
            
            db.session.commit()
        
        flash(get_message('edit_success'), 'success')
        return redirect(url_for('work_detail', work_id=work.id))
    
    return render_template('edit_work.html', work=work, admin_reason=admin_reason)

@app.route('/work/<int:work_id>/delete', methods=['POST'])
def delete_work(work_id):
    work = Work.query.get_or_404(work_id)
    current_user = get_current_user()
    
    # 检查权限：只有作者或管理员可以删除
    if not current_user or (current_user.id != work.creator_id and current_user.role != 'admin'):
        if request.headers.get('Content-Type') == 'application/json':
            return jsonify({'success': False, 'message': get_message('no_delete_permission')})
        else:
            flash(get_message('no_delete_permission'), 'error')
            return redirect(url_for('work_detail', work_id=work_id))
    
    # 检查作品状态：已完成的作品只有管理员可以删除
    if work.status == 'completed' and current_user.role != 'admin':
        if request.headers.get('Content-Type') == 'application/json':
            return jsonify({'success': False, 'message': get_message('completed_work_cannot_delete')})
        else:
            flash(get_message('completed_work_cannot_delete'), 'error')
            return redirect(url_for('work_detail', work_id=work_id))
    
    # 获取管理员删除理由
    admin_reason = ""
    if current_user.role == 'admin' and request.headers.get('Content-Type') == 'application/json':
        try:
            data = request.get_json()
            admin_reason = data.get('admin_reason', '').strip()
        except:
            pass
    

    
    # 保存作品信息用于发送消息
    work_title = work.title
    work_creator_id = work.creator_id
    work_translators = [t.translator_id for t in work.translations]
    
    try:
        # 先删除关联的点赞
        Like.query.filter_by(target_type='work', target_id=work.id).delete()
        
        # 删除关联的翻译请求
        TranslationRequest.query.filter_by(work_id=work_id).delete()
        
        # 删除关联的评论点赞
        for comment in work.comments:
            Like.query.filter_by(target_type='comment', target_id=comment.id).delete()
        
        # 删除关联的翻译点赞
        for translation in work.translations:
            Like.query.filter_by(target_type='translation', target_id=translation.id).delete()
            # 删除作者点赞
            AuthorLike.query.filter_by(translation_id=translation.id).delete()
        
        # 删除关联的评论
        Comment.query.filter_by(work_id=work_id).delete()
        
        # 删除关联的翻译
        Translation.query.filter_by(work_id=work_id).delete()
        
        # 删除关联的收藏
        Favorite.query.filter_by(work_id=work_id).delete()
        
        # 最后删除作品
        db.session.delete(work)
        db.session.commit()
        
        # 如果是管理员删除，发送消息给作者和翻译者
        if current_user.role == 'admin':
            # 发送消息给作者
            author_message_content = get_system_message('admin_work_deleted', work_creator_id, 
                                                    work_title=work_title, admin_name=current_user.username)
            if admin_reason:
                author_message_content += f"\n\n删除理由：{admin_reason}"
            
            author_message = Message(
                sender_id=1,  # 系统用户ID
                receiver_id=work_creator_id,
                content=author_message_content,
                type='system'
            )
            db.session.add(author_message)
            
            # 发送消息给所有翻译者
            for translator_id in work_translators:
                if translator_id != work_creator_id:  # 避免重复发送给作者
                    translator_message_content = get_system_message('admin_work_deleted', translator_id, 
                                                                work_title=work_title, admin_name=current_user.username)
                    if admin_reason:
                        translator_message_content += f"\n\n删除理由：{admin_reason}"
                    
                    translator_message = Message(
                        sender_id=1,  # 系统用户ID
                        receiver_id=translator_id,
                        content=translator_message_content,
                        type='system'
                    )
                    db.session.add(translator_message)
            
            db.session.commit()
        
    except Exception as e:
        db.session.rollback()
        if request.headers.get('Content-Type') == 'application/json':
            return jsonify({'success': False, 'message': get_message('delete_work_error').format(str(e))})
        else:
            flash(get_message('delete_work_error').format(str(e)), 'error')
            return redirect(url_for('work_detail', work_id=work_id))
    
    if request.headers.get('Content-Type') == 'application/json':
        return jsonify({'success': True, 'message': get_message('delete_success')})
    else:
        flash(get_message('delete_success'), 'success')
        return redirect(url_for('index'))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/trust/<int:translator_id>', methods=['POST'])
def trust_translator(translator_id):
    current_user = get_current_user()
    if not current_user:
        flash(get_message('please_login'), 'error')
        return redirect(url_for('user_profile', user_id=translator_id))
    
    if current_user.id == translator_id:
        flash(get_message('cannot_trust_self'), 'error')
        return redirect(url_for('user_profile', user_id=translator_id))
    
    # 检查是否已经是信赖的翻译者
    existing = TrustedTranslator.query.filter_by(user_id=current_user.id, translator_id=translator_id).first()
    if not existing:
        trust = TrustedTranslator(user_id=current_user.id, translator_id=translator_id)
        db.session.add(trust)
        db.session.commit()
        
        # 发送系统消息给被信赖的翻译者
        translator = User.query.get(translator_id)
        msg = Message(
            sender_id=1,  # 系统用户ID
            receiver_id=translator_id,
            content=get_system_message('trusted_by_author', translator_id, 
                                    author_name=current_user.username),
            type='system'
        )
        db.session.add(msg)
        db.session.commit()
        
        flash(get_message('trusted_translator'), 'success')
    else:
        flash(get_message('already_trusted'), 'info')
    return redirect(url_for('user_profile', user_id=translator_id))

@app.route('/untrust/<int:translator_id>', methods=['POST'])
def untrust_translator(translator_id):
    current_user = get_current_user()
    if not current_user:
        flash(get_message('please_login'), 'error')
        return redirect(url_for('user_profile', user_id=translator_id))
    
    trust = TrustedTranslator.query.filter_by(user_id=current_user.id, translator_id=translator_id).first()
    if trust:
        db.session.delete(trust)
        db.session.commit()
        
        # 不再发送系统消息和邮件通知
        # 取消信赖是静默操作，不需要通知被取消信赖的用户
        
        flash(get_message('untrusted'), 'info')
    else:
        flash(get_message('not_trusted'), 'warning')
    return redirect(url_for('user_profile', user_id=translator_id))

@app.route('/friend_request/<int:user_id>', methods=['POST'])
def friend_request(user_id):
    current_user = get_current_user()
    
    # 检查是否为AJAX请求
    is_ajax = request.headers.get('Content-Type') == 'application/x-www-form-urlencoded' or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if not current_user or current_user.id == user_id:
        if is_ajax:
            return jsonify({'success': False, 'message': get_message('invalid_operation')})
        flash(get_message('invalid_operation'), 'error')
        return redirect(url_for('user_profile', user_id=user_id))
    
    # 检查是否已是好友或有请求
    existing = Friend.query.filter_by(user_id=current_user.id, friend_id=user_id).first()
    if existing:
        if existing.status == 'pending':
            message = get_message('friend_request_sent')
        elif existing.status == 'accepted':
            message = get_message('already_friends')
        else:
            message = get_message('friend_request_rejected')
        
        if is_ajax:
            return jsonify({'success': False, 'message': message})
        flash(message, 'info' if existing.status == 'pending' else 'warning')
        return redirect(url_for('user_profile', user_id=user_id))
    
    # 创建好友请求
    req = Friend(user_id=current_user.id, friend_id=user_id, status='pending')
    db.session.add(req)
    
    # 发送系统消息邮件通知给被请求的用户
    target_user = User.query.get(user_id)
    if target_user and target_user.email_notifications_enabled:
        system_message = Message(
            sender_id=1,  # admin用户ID
            receiver_id=user_id,
            content=get_system_message('friend_request_sent', user_id, 
                                    sender_name=current_user.username),
            type='system'
        )
        db.session.add(system_message)
    
    db.session.commit()
    
    if is_ajax:
        return jsonify({'success': True, 'message': get_message('friend_request_success')})
    flash(get_message('friend_request_success'), 'success')
    return redirect(url_for('user_profile', user_id=user_id))

@app.route('/accept_friend/<int:friend_id>', methods=['POST'])
def accept_friend(friend_id):
    current_user = get_current_user()
    if not current_user:
        flash(get_message('please_login'), 'error')
        return redirect(url_for('message_list'))
    
    # 查找待处理的好友请求
    req = Friend.query.filter_by(id=friend_id, friend_id=current_user.id, status='pending').first()
    
    # 如果没有找到，尝试查找用户ID（用于用户资料页面）
    if not req:
        req = Friend.query.filter_by(user_id=friend_id, friend_id=current_user.id, status='pending').first()
    if not req:
        flash(get_message('invalid_friend_request'), 'error')
        return redirect(url_for('message_list'))
    
    # 更新好友请求状态
    req.status = 'accepted'
    
    # 删除相关的系统消息（好友请求通知）
    system_messages = Message.query.filter(
        Message.sender_id == 1,  # 系统用户ID
        Message.receiver_id == current_user.id,
        Message.type == 'system',
        Message.content.contains('friend request')
    ).all()
    for msg in system_messages:
        db.session.delete(msg)
    
    # 删除所有包含 "friend_request_accepted" 的系统消息
    old_messages = Message.query.filter(
        Message.sender_id == 1,  # 系统用户ID
        Message.type == 'system',
        Message.content == 'friend_request_accepted'
    ).all()
    for msg in old_messages:
        db.session.delete(msg)
    
    # 发送系统消息邮件通知给发送请求的用户
    requester_user = User.query.get(req.user_id)
    if requester_user and requester_user.email_notifications_enabled:
        system_message = Message(
            sender_id=1,  # admin用户ID
            receiver_id=req.user_id,
            content=get_system_message('friend_request_accepted', req.user_id, 
                                    receiver_name=current_user.username),
            type='system'
        )
        db.session.add(system_message)
    
    db.session.commit()
    
    flash(get_message('friend_accepted'), 'success')
    return redirect(url_for('message_list'))

@app.route('/reject_friend/<int:friend_id>', methods=['POST'])
def reject_friend(friend_id):
    if not is_logged_in():
        flash(get_message('please_login'), 'error')
        return redirect(url_for('login'))
    
    current_user = get_current_user()
    
    # 首先尝试查找Friend记录的ID
    friend_request = Friend.query.filter_by(id=friend_id, friend_id=current_user.id, status='pending').first()
    
    # 如果没有找到，尝试查找用户ID（用于用户资料页面）
    if not friend_request:
        friend_request = Friend.query.filter_by(user_id=friend_id, friend_id=current_user.id, status='pending').first()
    
    if not friend_request:
        flash(get_message('friend_request_not_found'), 'error')
        return redirect(url_for('message_list'))
    
    # 删除相关的系统消息（好友请求通知）
    Message.query.filter(
        Message.sender_id == 1,  # 系统用户ID
        Message.receiver_id == current_user.id,
        Message.type == 'system',
        Message.content.contains('friend request')
    ).delete()
    
    friend_request.status = 'rejected'
    
    # 发送系统消息邮件通知给发送请求的用户
    requester_user = User.query.get(friend_request.user_id)
    if requester_user and requester_user.email_notifications_enabled:
        system_message = Message(
            sender_id=1,  # admin用户ID
            receiver_id=friend_request.user_id,
            content=get_system_message('friend_request_rejected', friend_request.user_id, 
                                    receiver_name=current_user.username),
            type='system'
        )
        db.session.add(system_message)
    
    db.session.commit()
    
    flash(get_message('friend_rejected'), 'success')
    return redirect(url_for('message_list'))

@app.route('/delete_friend/<int:friend_id>', methods=['POST'])
def delete_friend(friend_id):
    current_user = get_current_user()
    if not current_user:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': get_message('please_login')})
        flash(get_message('please_login'), 'error')
        return redirect(url_for('friends_list'))
    
    # 查找好友关系（双向查找）
    friend_relation = Friend.query.filter(
        ((Friend.user_id == current_user.id) & (Friend.friend_id == friend_id)) |
        ((Friend.user_id == friend_id) & (Friend.friend_id == current_user.id))
    ).filter(Friend.status == 'accepted').first()
    
    if not friend_relation:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': get_message('friend_not_found')})
        flash(get_message('friend_not_found'), 'error')
        return redirect(url_for('friends_list'))
    
    # 获取被删除好友的用户信息
    deleted_friend_id = friend_relation.friend_id if friend_relation.user_id == current_user.id else friend_relation.user_id
    deleted_friend = User.query.get(deleted_friend_id)
    
    # 删除好友关系
    db.session.delete(friend_relation)
    db.session.commit()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': get_message('friend_deleted')})
    
    flash(get_message('friend_deleted'), 'success')
    return redirect(url_for('friends_list'))

@app.route('/add_friend_by_id', methods=['POST'])
def add_friend_by_id():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'success': False, 'message': get_message('please_login')})
    
    user_id = request.form.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': get_message('please_enter_user_id')})
    
    try:
        user_id = int(user_id)
    except ValueError:
        return jsonify({'success': False, 'message': get_message('invalid_user_id')})
    
    # 检查用户是否存在
    target_user = User.query.get(user_id)
    if not target_user:
        return jsonify({'success': False, 'message': get_message('user_not_found')})
    
    # 检查是否是自己
    if current_user.id == user_id:
        return jsonify({'success': False, 'message': get_message('cannot_add_yourself')})
    
    # 检查是否已是好友或有请求
    existing = Friend.query.filter_by(user_id=current_user.id, friend_id=user_id).first()
    if existing:
        if existing.status == 'pending':
            return jsonify({'success': False, 'message': get_message('friend_request_sent')})
        elif existing.status == 'accepted':
            return jsonify({'success': False, 'message': get_message('already_friends')})
        else:
            return jsonify({'success': False, 'message': get_message('friend_request_rejected')})
    
    # 创建好友请求
    req = Friend(user_id=current_user.id, friend_id=user_id, status='pending')
    db.session.add(req)
    
    # 发送系统消息邮件通知给被请求的用户
    if target_user.email_notifications_enabled:
        system_message = Message(
            sender_id=1,  # admin用户ID
            receiver_id=user_id,
            content=get_system_message('friend_request_sent', user_id, 
                                    sender_name=current_user.username),
            type='system'
        )
        db.session.add(system_message)
    
    db.session.commit()
    
    return jsonify({'success': True, 'message': get_message('friend_request_success')})

@app.route('/like/<target_type>/<int:target_id>', methods=['POST'])
def like_content(target_type, target_id):
    if not is_logged_in():
        return jsonify({'success': False, 'message': get_message('please_login')})
    
    current_user = get_current_user()
    
    # 检查是否已经点赞
    existing_like = Like.query.filter_by(
        user_id=current_user.id,
        target_type=target_type,
        target_id=target_id
    ).first()
    
    if existing_like:
        # 取消点赞
        db.session.delete(existing_like)
        db.session.commit()
        return jsonify({'success': True, 'action': 'unliked'})
    else:
        # 添加点赞
        new_like = Like(
            user_id=current_user.id,
            target_type=target_type,
            target_id=target_id
        )
        db.session.add(new_like)
        db.session.commit()
        
        # 获取被点赞的内容信息
        target_user_id = None
        if target_type == 'work':
            work = Work.query.get(target_id)
            if work:
                target_user_id = work.creator_id
        elif target_type == 'comment':
            comment = Comment.query.get(target_id)
            if comment:
                target_user_id = comment.author_id
        elif target_type == 'translation':
            translation = Translation.query.get(target_id)
            if translation:
                target_user_id = translation.translator_id
        
        # 点赞通知：创建通知类型消息（自发自收），用于消息中心"通知消息"卡片
        if target_user_id and target_user_id != current_user.id:
            receiver = User.query.get(target_user_id)
            receiver_lang = getattr(receiver, 'preferred_language', 'zh') if receiver else 'zh'
            liker_name = current_user.username
            
            # 获取作品信息和类型信息
            work_info = ""
            work_id = None
            content_type = ""
            
            if target_type == 'work':
                work = Work.query.get(target_id)
                if work:
                    work_info = work.title
                    work_id = work.id
                    content_type = get_message('work', lang=receiver_lang) if get_message('work', lang=receiver_lang) else '作品'
            elif target_type == 'translation':
                translation = Translation.query.get(target_id)
                if translation:
                    work_info = translation.work.title
                    work_id = translation.work.id
                    content_type = get_message('translation', lang=receiver_lang) if get_message('translation', lang=receiver_lang) else '翻译'
            elif target_type == 'comment':
                comment = Comment.query.get(target_id)
                if comment and comment.work_id:
                    work_info = comment.work.title
                    work_id = comment.work_id
                    content_type = get_message('comment', lang=receiver_lang) if get_message('comment', lang=receiver_lang) else '评论'
            
            # 生成包含作品信息和类型信息的消息内容
            if work_info and content_type:
                # 对于评论，获取评论内容
                comment_content = ""
                if target_type == 'comment' and comment:
                    # 截断评论内容，避免过长
                    comment_content = comment.content.strip()
                    if len(comment_content) > 100:
                        comment_content = comment_content[:100] + "..."
                
                # 根据用户语言偏好生成多语言消息
                if target_type == 'comment' and comment_content:
                    # 评论点赞消息包含评论内容
                    if receiver_lang == 'zh':
                        notification_content = f"您在《{work_info}》作品中的评论收到了{liker_name}的点赞\n\n评论内容：{comment_content}"
                    elif receiver_lang == 'ja':
                        notification_content = f"あなたの《{work_info}》作品のコメントに{liker_name}さんがいいねをしました\n\nコメント内容：{comment_content}"
                    elif receiver_lang == 'en':
                        notification_content = f"You received a like from {liker_name} on your comment in the work 《{work_info}》\n\nComment: {comment_content}"
                    elif receiver_lang == 'ru':
                        notification_content = f"Вы получили лайк от {liker_name} за ваш комментарий в работе 《{work_info}》\n\nКомментарий: {comment_content}"
                    elif receiver_lang == 'ko':
                        notification_content = f"당신의 《{work_info}》 작품의 댓글에 {liker_name}님이 좋아요를 했습니다\n\n댓글 내용: {comment_content}"
                    elif receiver_lang == 'fr':
                        notification_content = f"Vous avez reçu un j'aime de {liker_name} sur votre commentaire dans l'œuvre 《{work_info}》\n\nCommentaire: {comment_content}"
                    else:
                        # 默认中文
                        notification_content = f"您在《{work_info}》作品中的评论收到了{liker_name}的点赞\n\n评论内容：{comment_content}"
                else:
                    # 其他类型的内容点赞消息
                    if receiver_lang == 'zh':
                        notification_content = f"您在《{work_info}》作品中的{content_type}收到了{liker_name}的点赞"
                    elif receiver_lang == 'ja':
                        notification_content = f"あなたの《{work_info}》作品の{content_type}に{liker_name}さんがいいねをしました"
                    elif receiver_lang == 'en':
                        notification_content = f"You received a like from {liker_name} on your {content_type} in the work 《{work_info}》"
                    elif receiver_lang == 'ru':
                        notification_content = f"Вы получили лайк от {liker_name} за ваш {content_type} в работе 《{work_info}》"
                    elif receiver_lang == 'ko':
                        notification_content = f"당신의 《{work_info}》 작품의 {content_type}에 {liker_name}님이 좋아요를 했습니다"
                    elif receiver_lang == 'fr':
                        notification_content = f"Vous avez reçu un j'aime de {liker_name} sur votre {content_type} dans l'œuvre 《{work_info}》"
                    else:
                        # 默认中文
                        notification_content = f"您在《{work_info}》作品中的{content_type}收到了{liker_name}的点赞"
            else:
                notification_content = f"{get_message('received_like', lang=receiver_lang)} - {liker_name}"
            
            if receiver:
                notification = Message(
                    sender_id=receiver.id,
                    receiver_id=receiver.id,
                    content=notification_content,
                    type='notification',
                    work_id=work_id,
                    liker_id=current_user.id
                )
                db.session.add(notification)
                db.session.commit()
        
        return jsonify({'success': True, 'action': 'liked'})

@app.route('/likes/<target_type>/<int:target_id>')
def get_likes_count(target_type, target_id):
    count = Like.query.filter_by(target_type=target_type, target_id=target_id).count()
    return jsonify({'count': count})

@app.route('/work/<int:work_id>/edit_translation', methods=['GET', 'POST'])
def edit_translation(work_id):
    work = Work.query.get_or_404(work_id)
    current_user = get_current_user()
    
    if not current_user:
        flash(get_message('please_login'), 'error')
        return redirect(url_for('login'))
    
    # 检查是否有翻译
    translation = Translation.query.filter_by(work_id=work_id, translator_id=current_user.id).first()
    if not translation:
        flash(get_message('no_translation'), 'error')
        return redirect(url_for('work_detail', work_id=work_id))
    
    # 检查作品状态：已完成的作品只有管理员可以编辑翻译
    if work.status == 'completed' and current_user.role != 'admin':
        flash(get_message('completed_work_translation_cannot_edit'), 'error')
        return redirect(url_for('work_detail', work_id=work_id))
    
    if request.method == 'POST':
        if 'update_translation' in request.form:
            content = request.form['translation_content']
            
            # 处理多媒体文件上传
            media_filename = None
            file = request.files.get('translation_media_file')
            if file and file.filename:
                filename = secure_filename(file.filename)
                ext = filename.rsplit('.', 1)[-1].lower()
                media_filename = f"translation_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{current_user.id}.{ext}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], media_filename))
            
            # 更新翻译
            translation.content = content
            translation.status = 'draft'  # 修改后重置为草稿状态
            translation.updated_at = datetime.utcnow()
            if media_filename:
                translation.media_filename = media_filename
            
            db.session.commit()
            flash(get_message('translation_updated'), 'success')
            return redirect(url_for('work_detail', work_id=work_id))
    
    return render_template('edit_translation.html', work=work, translation=translation)

@app.route('/work/<int:work_id>/delete_translation', methods=['POST'])
def delete_translation(work_id):
    work = Work.query.get_or_404(work_id)
    current_user = get_current_user()
    
    if not current_user:
        if request.headers.get('Content-Type') == 'application/json':
            return jsonify({'success': False, 'message': get_message('please_login')})
        else:
            flash(get_message('please_login'), 'error')
            return redirect(url_for('login'))
    
    # 获取指定的翻译ID
    translation_id = None
    if request.headers.get('Content-Type') == 'application/json':
        try:
            data = request.get_json()
            translation_id = data.get('translation_id')
        except:
            pass
    else:
        translation_id = request.form.get('translation_id')
    
    # 获取翻译
    if translation_id:
        translation = Translation.query.filter_by(id=translation_id, work_id=work_id).first()
    else:
        # 向后兼容：如果没有指定翻译ID，则获取当前用户的翻译
        translation = Translation.query.filter_by(work_id=work_id, translator_id=current_user.id).first()
    
    if not translation:
        if request.headers.get('Content-Type') == 'application/json':
            return jsonify({'success': False, 'message': get_message('no_translation')})
        else:
            flash(get_message('no_translation'), 'error')
            return redirect(url_for('work_detail', work_id=work_id))
    
    # 检查权限：只有翻译作者或管理员可以删除
    if translation.translator_id != current_user.id and current_user.role != 'admin':
        if request.headers.get('Content-Type') == 'application/json':
            return jsonify({'success': False, 'message': get_message('no_permission_delete_translation')})
        else:
            flash(get_message('no_permission_delete_translation'), 'error')
            return redirect(url_for('work_detail', work_id=work_id))
    
    # 检查作品状态：已完成的作品只有管理员可以删除翻译
    if work.status == 'completed' and current_user.role != 'admin':
        if request.headers.get('Content-Type') == 'application/json':
            return jsonify({'success': False, 'message': get_message('completed_work_translation_cannot_delete')})
        else:
            flash(get_message('completed_work_translation_cannot_delete'), 'error')
            return redirect(url_for('work_detail', work_id=work_id))
    
    # 删除翻译
    db.session.delete(translation)
    db.session.commit()
    
    if request.headers.get('Content-Type') == 'application/json':
        return jsonify({'success': True, 'message': get_message('translation_deleted')})
    else:
        flash(get_message('translation_deleted'), 'success')
        return redirect(url_for('work_detail', work_id=work_id))

@app.route('/work/<int:work_id>/accept_translation', methods=['POST'])
def accept_translation(work_id):
    work = Work.query.get_or_404(work_id)
    current_user = get_current_user()
    
    if not current_user:
        if request.headers.get('Content-Type') == 'application/json':
            return jsonify({'success': False, 'message': get_message('please_login')})
        else:
            flash(get_message('please_login'), 'error')
            return redirect(url_for('work_detail', work_id=work_id))
    
    # 检查是否是作品作者
    if current_user.id != work.creator_id:
        if request.headers.get('Content-Type') == 'application/json':
            return jsonify({'success': False, 'message': get_message('only_author_accept')})
        else:
            flash(get_message('only_author_accept'), 'error')
            return redirect(url_for('work_detail', work_id=work_id))
    
    # 获取指定的翻译ID
    translation_id = None
    if request.headers.get('Content-Type') == 'application/json':
        try:
            data = request.get_json()
            translation_id = data.get('translation_id')
        except:
            pass
    else:
        translation_id = request.form.get('translation_id')
    
    # 获取翻译
    if translation_id:
        translation = Translation.query.filter_by(id=translation_id, work_id=work_id).first()
    else:
        translation = Translation.query.filter_by(work_id=work_id).first()
    
    if not translation:
        if request.headers.get('Content-Type') == 'application/json':
            return jsonify({'success': False, 'message': get_message('no_translation_for_work')})
        else:
            flash(get_message('no_translation_for_work'), 'error')
            return redirect(url_for('work_detail', work_id=work_id))
    
    # 检查是否已经接受过
    existing_author_like = AuthorLike.query.filter_by(
        author_id=current_user.id, 
        translation_id=translation.id
    ).first()
    
    if existing_author_like:
        if request.headers.get('Content-Type') == 'application/json':
            return jsonify({'success': False, 'message': get_message('already_accepted')})
        else:
            flash(get_message('already_accepted'), 'info')
            return redirect(url_for('work_detail', work_id=work_id))
    
    # 获取评价和点赞选择
    evaluation = ""
    add_like = True
    
    if request.headers.get('Content-Type') == 'application/json':
        try:
            data = request.get_json()
            evaluation = data.get('evaluation', '').strip()
            add_like = data.get('addLike', True)
        except:
            pass
    
    # 如果选择点赞，创建作者点赞
    if add_like:
        author_like = AuthorLike(
            author_id=current_user.id,
            translation_id=translation.id
        )
        db.session.add(author_like)
    
    # 更新翻译状态为已通过
    translation.status = 'approved'
    translation.updated_at = datetime.utcnow()
    
    # 更新作品状态为已完成
    work.status = 'completed'
    work.updated_at = datetime.utcnow()
    
    
    
    # 发送系统消息给翻译者（包含评价）
    system_message_content = get_system_message('translation_accepted_by_author', translation.translator_id, 
                                            work_title=work.title)
    if evaluation:
        system_message_content += f"\n\n作者评价：{evaluation}"
    
    # 创建系统消息（用于平台内显示）
    system_message = Message(
        sender_id=1,  # 系统用户ID
        receiver_id=translation.translator_id,
        content=system_message_content,
        type='system',
        work_id=work.id
    )
    db.session.add(system_message)
    
    # 检查是否需要发送邮件通知
    translator_user = User.query.get(translation.translator_id)
    if translator_user and translator_user.email_notifications_enabled:
        # 直接发送邮件，不创建额外的系统消息
        from mail_utils import send_email
        # 使用翻译者的语言偏好
        translator_lang = getattr(translator_user, 'preferred_language', 'zh') or 'zh'
        subject = get_message('translation_accepted_notification', lang=translator_lang)
        
        # 发送简洁的纯文本邮件
        send_email(translator_user.email, subject, system_message_content, message_type='system', user_lang=translator_lang)
    
    db.session.commit()
    
    # 检查是否是AJAX请求
    if request.headers.get('Content-Type') == 'application/json':
        return jsonify({'success': True, 'message': get_message('translation_accepted')})
    else:
        flash(get_message('translation_accepted'), 'success')
        return redirect(url_for('work_detail', work_id=work_id))

@app.route('/work/<int:work_id>/reject_translation', methods=['POST'])
def reject_translation(work_id):
    work = Work.query.get_or_404(work_id)
    current_user = get_current_user()
    
    if not current_user:
        if request.headers.get('Content-Type') == 'application/json':
            return jsonify({'success': False, 'message': get_message('please_login')})
        else:
            flash(get_message('please_login'), 'error')
            return redirect(url_for('work_detail', work_id=work_id))
    
    # 检查是否是作品作者
    if current_user.id != work.creator_id:
        if request.headers.get('Content-Type') == 'application/json':
            return jsonify({'success': False, 'message': get_message('only_author_accept')})
        else:
            flash(get_message('only_author_accept'), 'error')
            return redirect(url_for('work_detail', work_id=work_id))
    
    # 获取指定的翻译ID
    translation_id = None
    if request.headers.get('Content-Type') == 'application/json':
        try:
            data = request.get_json()
            translation_id = data.get('translation_id')
        except:
            pass
    else:
        translation_id = request.form.get('translation_id')
    
    # 获取翻译
    if translation_id:
        translation = Translation.query.filter_by(id=translation_id, work_id=work_id).first()
    else:
        translation = Translation.query.filter_by(work_id=work_id).first()
    
    if not translation:
        if request.headers.get('Content-Type') == 'application/json':
            return jsonify({'success': False, 'message': get_message('no_translation_for_work')})
        else:
            flash(get_message('no_translation_for_work'), 'error')
            return redirect(url_for('work_detail', work_id=work_id))
    
    # 获取拒绝评价
    evaluation = ""
    
    if request.headers.get('Content-Type') == 'application/json':
        try:
            data = request.get_json()
            evaluation = data.get('evaluation', '').strip()
        except:
            pass
    
    # 更新翻译状态为已拒绝
    translation.status = 'rejected'
    translation.updated_at = datetime.utcnow()
    
    # 将作品状态重新设置为待翻译
    work.status = 'pending'
    work.updated_at = datetime.utcnow()
    
    # 发送系统消息给翻译者（包含拒绝理由）
    system_message_content = get_system_message('translation_rejected_by_author', translation.translator_id, 
                                            work_title=work.title,
                                            author_name=work.creator.username)
    if evaluation:
        system_message_content += f"\n\n拒绝理由：{evaluation}"
    
    # 创建系统消息（用于平台内显示）
    system_message = Message(
        sender_id=1,  # 系统用户ID
        receiver_id=translation.translator_id,
        content=system_message_content,
        type='system',
        work_id=work.id
    )
    db.session.add(system_message)
    
    # 检查是否需要发送邮件通知
    translator_user = User.query.get(translation.translator_id)
    if translator_user and translator_user.email_notifications_enabled:
        # 直接发送邮件，不创建额外的系统消息
        from mail_utils import send_email
        # 使用翻译者的语言偏好
        translator_lang = getattr(translator_user, 'preferred_language', 'zh') or 'zh'
        subject = get_message('translation_rejected_notification', lang=translator_lang)
        
        # 发送简洁的纯文本邮件
        send_email(translator_user.email, subject, system_message_content, message_type='system', user_lang=translator_lang)
    
    # 不需要给作者发送确认消息，因为作者已经知道自己的操作
    
    db.session.commit()
    
    # 检查是否是AJAX请求
    if request.headers.get('Content-Type') == 'application/json':
        return jsonify({'success': True, 'message': get_message('translation_rejected')})
    else:
        flash(get_message('translation_rejected'), 'success')
        return redirect(url_for('work_detail', work_id=work_id))

@app.route('/work/<int:work_id>/unaccept_translation', methods=['POST'])
def unaccept_translation(work_id):
    # 作者承认是不可取消的
    flash(get_message('author_accept_irreversible'), 'error')
    return redirect(url_for('work_detail', work_id=work_id))

# create_default_admin函数已移至seed_data.py中

# 校正者相关路由
@app.route('/work/<int:work_id>/add_correction', methods=['POST'])
def add_correction(work_id):
    """添加校正"""
    if not is_logged_in():
        flash(get_message('please_login'), 'error')
        return redirect(url_for('work_detail', work_id=work_id))
    
    current_user = get_current_user()
    
    # 检查是否是校正者
    if not current_user.is_reviewer:
        flash(get_message('only_reviewer'), 'error')
        return redirect(url_for('work_detail', work_id=work_id))
    
    # 获取作品和翻译
    work = Work.query.get_or_404(work_id)
    
    # 获取指定的翻译ID，如果没有指定则使用第一个翻译
    translation_id = request.form.get('translation_id')
    if translation_id:
        translation = Translation.query.filter_by(id=translation_id, work_id=work_id).first()
    else:
        translation = Translation.query.filter_by(work_id=work_id).first()
    
    if not translation:
        flash('没有找到翻译', 'error')
        return redirect(url_for('work_detail', work_id=work_id))
    
    # 检查翻译者不能对自己进行校正
    if current_user.id == translation.translator_id:
        flash(get_message('cannot_correct_own_translation'), 'error')
        return redirect(url_for('work_detail', work_id=work_id))
    
    # 获取表单数据
    content = request.form.get('content', '').strip()
    notes = request.form.get('notes', '').strip()
    
    if not content:
        flash('校正内容不能为空', 'error')
        return redirect(url_for('work_detail', work_id=work_id))
    
    # 创建校正
    correction = Correction(
        translation_id=translation.id,
        reviewer_id=current_user.id,
        content=content,
        notes=notes
    )
    
    db.session.add(correction)
    db.session.commit()
    
    # 发送系统消息给作品创作者
    creator_user = User.query.get(work.creator_id)
    if creator_user and creator_user.email_notifications_enabled:
        creator_message = Message(
            sender_id=1,  # 系统用户ID
            receiver_id=work.creator_id,
            content=get_system_message('correction_submitted_to_creator', work.creator_id, 
                                    reviewer_name=current_user.username, 
                                    work_title=work.title,
                                    work_id=work.id),
            type='system',
            work_id=work.id
        )
        db.session.add(creator_message)
    
    # 发送系统消息给翻译者
    translator_user = User.query.get(translation.translator_id)
    if translator_user and translator_user.email_notifications_enabled:
        translator_message = Message(
            sender_id=1,  # 系统用户ID
            receiver_id=translation.translator_id,
            content=get_system_message('correction_submitted_to_translator', translation.translator_id, 
                                    reviewer_name=current_user.username, 
                                    work_title=work.title,
                                    work_id=work.id),
            type='system',
            work_id=work.id
        )
        db.session.add(translator_message)
    
    # 发送邮件通知
    from mail_utils import send_email
    
    # 给创作者发送邮件
    if creator_user and creator_user.email and creator_user.email_notifications_enabled:
        try:
            subject = get_message('correction_submitted_to_creator', lang=creator_user.preferred_language or 'zh')
            body = get_system_message('correction_submitted_to_creator', work.creator_id, 
                                    reviewer_name=current_user.username, 
                                    work_title=work.title,
                                    work_id=work.id)
            
            # 发送简洁的纯文本邮件
            send_email(creator_user.email, subject, body, message_type='system', user_lang=creator_user.preferred_language or 'zh')
        except Exception as e:
            print(f"Failed to send email to creator: {e}")
    
    # 给翻译者发送邮件
    if translator_user and translator_user.email and translator_user.email_notifications_enabled:
        try:
            subject = get_message('correction_submitted_to_translator', lang=translator_user.preferred_language or 'zh')
            body = get_system_message('correction_submitted_to_translator', translation.translator_id, 
                                    reviewer_name=current_user.username, 
                                    work_title=work.title,
                                    work_id=work.id)
            
            # 发送简洁的纯文本邮件
            send_email(translator_user.email, subject, body, message_type='system', user_lang=translator_user.preferred_language or 'zh')
        except Exception as e:
            print(f"Failed to send email to translator: {e}")
    
    db.session.commit()
    
    flash(get_message('correction_success'), 'success')
    return redirect(url_for('work_detail', work_id=work_id))

@app.route('/work/<int:work_id>/delete_correction/<int:correction_id>', methods=['POST'])
def delete_correction(work_id, correction_id):
    """删除校正"""
    if not is_logged_in():
        flash(get_message('please_login'), 'error')
        return redirect(url_for('work_detail', work_id=work_id))
    
    current_user = get_current_user()
    correction = Correction.query.get_or_404(correction_id)
    
    # 检查权限：只有校正者本人或管理员可以删除
    if correction.reviewer_id != current_user.id and current_user.role != 'admin':
        flash('没有权限删除此校正', 'error')
        return redirect(url_for('work_detail', work_id=work_id))
    
    db.session.delete(correction)
    db.session.commit()
    
    flash(get_message('correction_deleted'), 'success')
    return redirect(url_for('work_detail', work_id=work_id))

@app.route('/correction/<int:correction_id>/like', methods=['POST'])
def like_correction(correction_id):
    """对校正点赞 - 作者点赞计入作者点赞，普通用户点赞计入普通点赞"""
    if not is_logged_in():
        return jsonify({'success': False, 'message': get_message('please_login')})
    
    current_user = get_current_user()
    correction = Correction.query.get_or_404(correction_id)
    work = Work.query.get_or_404(correction.translation.work_id)
    
    # 检查是否是作品作者
    is_author = current_user.id == work.creator_id
    
    # 检查是否已经点赞
    existing_correction_like = CorrectionLike.query.filter_by(
        user_id=current_user.id, 
        correction_id=correction_id
    ).first()
    
    existing_author_like = AuthorLike.query.filter_by(
        author_id=current_user.id,
        translation_id=correction.translation_id,
        correction_id=correction_id
    ).first()
    
    if existing_correction_like:
        # 取消普通点赞
        db.session.delete(existing_correction_like)
        liked = False
    elif existing_author_like:
        # 取消作者点赞
        db.session.delete(existing_author_like)
        liked = False
    else:
        # 添加点赞
        if is_author:
            # 作者点赞
            like = AuthorLike(
                author_id=current_user.id,
                translation_id=correction.translation_id,
                correction_id=correction_id
            )
        else:
            # 普通点赞
            like = CorrectionLike(
                user_id=current_user.id,
                correction_id=correction_id
            )
        db.session.add(like)
        liked = True
    
    try:
        db.session.commit()
        

        
        # 点赞通知：创建通知类型消息（自发自收），用于消息中心"通知消息"卡片
        if liked and current_user.id != correction.reviewer_id:
            receiver = User.query.get(correction.reviewer_id)
            receiver_lang = getattr(receiver, 'preferred_language', 'zh') if receiver else 'zh'
            liker_name = current_user.username
            
            # 生成包含作品信息和类型信息的消息内容
            work_info = correction.translation.work.title
            content_type = get_message('correction', lang=receiver_lang) if get_message('correction', lang=receiver_lang) else '校正'
            
            # 根据用户语言偏好生成多语言消息
            if receiver_lang == 'zh':
                notification_content = f"您在《{work_info}》作品中的{content_type}收到了{liker_name}的点赞"
            elif receiver_lang == 'ja':
                notification_content = f"あなたの《{work_info}》作品の{content_type}に{liker_name}さんがいいねをしました"
            elif receiver_lang == 'en':
                notification_content = f"You received a like from {liker_name} on your {content_type} in the work 《{work_info}》"
            elif receiver_lang == 'ru':
                notification_content = f"Вы получили лайк от {liker_name} за ваш {content_type} в работе 《{work_info}》"
            elif receiver_lang == 'ko':
                notification_content = f"당신의 《{work_info}》 작품의 {content_type}에 {liker_name}님이 좋아요를 했습니다"
            elif receiver_lang == 'fr':
                notification_content = f"Vous avez reçu un j'aime de {liker_name} sur votre {content_type} dans l'œuvre 《{work_info}》"
            else:
                # 默认中文
                notification_content = f"您在《{work_info}》作品中的{content_type}收到了{liker_name}的点赞"
            
            if receiver:
                notification = Message(
                    sender_id=receiver.id,
                    receiver_id=receiver.id,
                    content=notification_content,
                    type='notification',
                    work_id=correction.translation.work.id,
                    liker_id=current_user.id
                )
                db.session.add(notification)
                db.session.commit()
                
    except Exception as e:
        db.session.rollback()
        # 如果作者点赞失败，尝试普通点赞
        if is_author and not existing_correction_like:
            like = CorrectionLike(
                user_id=current_user.id,
                correction_id=correction_id
            )
            db.session.add(like)
            db.session.commit()
            liked = True
    
    # 获取总点赞数量（包括普通点赞和作者点赞）
    correction_likes = CorrectionLike.query.filter_by(correction_id=correction_id).count()
    author_likes = AuthorLike.query.filter_by(
        translation_id=correction.translation_id,
        correction_id=correction_id
    ).count()
    total_likes = correction_likes + author_likes
    
    return jsonify({
        'success': True,
        'liked': liked,
        'likes_count': total_likes
    })

@app.route('/correction/<int:correction_id>/likes_count')
def get_correction_likes_count(correction_id):
    """获取校正点赞数量（包括普通点赞和作者点赞）"""
    correction = Correction.query.get_or_404(correction_id)
    
    # 获取普通点赞数量
    correction_likes = CorrectionLike.query.filter_by(correction_id=correction_id).count()
    
    # 获取作者点赞数量
    author_likes = AuthorLike.query.filter_by(
        translation_id=correction.translation_id,
        correction_id=correction_id
    ).count()
    
    # 总点赞数量
    total_likes = correction_likes + author_likes
    
    return jsonify({'likes_count': total_likes})

@app.route('/correction/<int:correction_id>/author_like', methods=['POST'])
def author_like_correction(correction_id):
    """作者对校正点赞 - 全部计入作者点赞"""
    if not is_logged_in():
        return jsonify({'success': False, 'message': get_message('please_login')})
    
    current_user = get_current_user()
    correction = Correction.query.get_or_404(correction_id)
    work = Work.query.get_or_404(correction.translation.work_id)
    
    # 检查是否是作品作者
    if current_user.id != work.creator_id:
        return jsonify({'success': False, 'message': '只有作者可以对校正进行点赞'})
    
    # 检查是否已经点赞（包括普通点赞和作者点赞）
    existing_correction_like = CorrectionLike.query.filter_by(
        user_id=current_user.id,
        correction_id=correction_id
    ).first()
    
    existing_author_like = AuthorLike.query.filter_by(
        author_id=current_user.id,
        translation_id=correction.translation_id,
        correction_id=correction_id
    ).first()
    
    if existing_correction_like:
        # 如果已经有普通点赞，删除它并添加作者点赞
        db.session.delete(existing_correction_like)
        like = AuthorLike(
            author_id=current_user.id,
            translation_id=correction.translation_id,
            correction_id=correction_id
        )
        db.session.add(like)
        liked = True
    elif existing_author_like:
        # 如果已经有作者点赞，删除它
        db.session.delete(existing_author_like)
        liked = False
    else:
        # 添加作者点赞
        like = AuthorLike(
            author_id=current_user.id,
            translation_id=correction.translation_id,
            correction_id=correction_id
        )
        db.session.add(like)
        liked = True
    
    try:
        db.session.commit()
        
        # 如果点赞成功，给校正者添加经验值
        if liked:
            correction_user = User.query.get(correction.reviewer_id)
            if correction_user and correction_user.is_reviewer:
                # 校正者获得校正点赞时1经验
                correction_user.add_experience(1)
            # 点赞通知：创建通知类型消息（自发自收），用于消息中心"通知消息"卡片
            if current_user.id != correction.reviewer_id:
                receiver = User.query.get(correction.reviewer_id)
                receiver_lang = getattr(receiver, 'preferred_language', 'zh') if receiver else 'zh'
                liker_name = current_user.username
                
                # 生成包含作品信息和类型信息的消息内容
                work_info = correction.translation.work.title
                content_type = get_message('correction', lang=receiver_lang) if get_message('correction', lang=receiver_lang) else '校正'
                
                # 根据用户语言偏好生成多语言消息
                if receiver_lang == 'zh':
                    notification_content = f"您在《{work_info}》作品中的{content_type}收到了{liker_name}的点赞"
                elif receiver_lang == 'ja':
                    notification_content = f"あなたの《{work_info}》作品の{content_type}に{liker_name}さんがいいねをしました"
                elif receiver_lang == 'en':
                    notification_content = f"You received a like from {liker_name} on your {content_type} in the work 《{work_info}》"
                elif receiver_lang == 'ru':
                    notification_content = f"Вы получили лайк от {liker_name} за ваш {content_type} в работе 《{work_info}》"
                elif receiver_lang == 'ko':
                    notification_content = f"당신의 《{work_info}》 작품의 {content_type}에 {liker_name}님이 좋아요를 했습니다"
                elif receiver_lang == 'fr':
                    notification_content = f"Vous avez reçu un j'aime de {liker_name} sur votre {content_type} dans l'œuvre 《{work_info}》"
                else:
                    # 默认中文
                    notification_content = f"您在《{work_info}》作品中的{content_type}收到了{liker_name}的点赞"
                
                if receiver:
                    notification = Message(
                        sender_id=receiver.id,
                        receiver_id=receiver.id,
                        content=notification_content,
                        type='notification',
                        work_id=correction.translation.work.id,
                        liker_id=current_user.id
                    )
                    db.session.add(notification)
                    db.session.commit()
        
    except Exception as e:
        db.session.rollback()
        # 如果作者点赞失败，尝试普通点赞
        if not existing_correction_like:
            like = CorrectionLike(
                user_id=current_user.id,
                correction_id=correction_id
            )
            db.session.add(like)
            db.session.commit()
            liked = True
            

    
    # 获取总点赞数量（普通点赞 + 作者点赞）
    correction_likes = CorrectionLike.query.filter_by(correction_id=correction_id).count()
    author_likes = AuthorLike.query.filter_by(
        translation_id=correction.translation_id,
        correction_id=correction_id
    ).count()
    total_likes = correction_likes + author_likes
    

    
    return jsonify({
        'success': True,
        'liked': liked,
        'likes_count': total_likes
    })

@app.route('/translation/<int:translation_id>/author_like', methods=['POST'])
def author_like_translation(translation_id):
    """作者对翻译点赞"""
    if not is_logged_in():
        return jsonify({'success': False, 'message': get_message('please_login')})
    
    current_user = get_current_user()
    translation = Translation.query.get_or_404(translation_id)
    work = Work.query.get_or_404(translation.work_id)
    
    # 检查是否是作品作者
    if current_user.id != work.creator_id:
        return jsonify({'success': False, 'message': '只有作者可以对翻译进行点赞'})
    
    # 检查是否已经点赞（包括普通点赞和作者点赞）
    existing_translation_like = Like.query.filter_by(
        user_id=current_user.id,
        target_type='translation',
        target_id=translation_id
    ).first()
    
    existing_author_like = AuthorLike.query.filter_by(
        author_id=current_user.id,
        translation_id=translation_id,
        correction_id=None
    ).first()
    
    if existing_translation_like:
        # 如果已经有普通点赞，删除它并添加作者点赞
        db.session.delete(existing_translation_like)
        like = AuthorLike(
            author_id=current_user.id,
            translation_id=translation_id,
            correction_id=None
        )
        db.session.add(like)
        liked = True
    elif existing_author_like:
        # 如果已经有作者点赞，删除它
        db.session.delete(existing_author_like)
        liked = False
    else:
        # 添加作者点赞
        like = AuthorLike(
            author_id=current_user.id,
            translation_id=translation_id,
            correction_id=None
        )
        db.session.add(like)
        liked = True
    
    try:
        db.session.commit()
        
        # 如果点赞成功，给翻译者添加经验值
        if liked:
            translator_user = User.query.get(translation.translator_id)
            if translator_user and translator_user.is_translator:
                # 翻译者获得作者点赞时2经验
                translator_user.add_experience(2)
            # 点赞通知：创建通知类型消息（自发自收），用于消息中心"通知消息"卡片
            if current_user.id != translation.translator_id:
                receiver = User.query.get(translation.translator_id)
                receiver_lang = getattr(receiver, 'preferred_language', 'zh') if receiver else 'zh'
                liker_name = current_user.username
                
                # 生成包含作品信息和类型信息的消息内容
                work_info = work.title
                content_type = get_message('translation', lang=receiver_lang) if get_message('translation', lang=receiver_lang) else '翻译'
                
                # 根据用户语言偏好生成多语言消息
                if receiver_lang == 'zh':
                    notification_content = f"您在《{work_info}》作品中的{content_type}收到了{liker_name}的点赞"
                elif receiver_lang == 'ja':
                    notification_content = f"あなたの《{work_info}》作品の{content_type}に{liker_name}さんがいいねをしました"
                elif receiver_lang == 'en':
                    notification_content = f"You received a like from {liker_name} on your {content_type} in the work 《{work_info}》"
                elif receiver_lang == 'ru':
                    notification_content = f"Вы получили лайк от {liker_name} за ваш {content_type} в работе 《{work_info}》"
                elif receiver_lang == 'ko':
                    notification_content = f"당신의 《{work_info}》 작품의 {content_type}에 {liker_name}님이 좋아요를 했습니다"
                elif receiver_lang == 'fr':
                    notification_content = f"Vous avez reçu un j'aime de {liker_name} sur votre {content_type} dans l'œuvre 《{work_info}》"
                else:
                    # 默认中文
                    notification_content = f"您在《{work_info}》作品中的{content_type}收到了{liker_name}的点赞"
                
                if receiver:
                    notification = Message(
                        sender_id=receiver.id,
                        receiver_id=receiver.id,
                        content=notification_content,
                        type='notification',
                        work_id=work.id,
                        liker_id=current_user.id
                    )
                    db.session.add(notification)
                    db.session.commit()
        
    except Exception as e:
        db.session.rollback()
        # 如果作者点赞失败，尝试普通点赞
        if not existing_translation_like:
            like = Like(
                user_id=current_user.id,
                target_type='translation',
                target_id=translation_id
            )
            db.session.add(like)
            db.session.commit()
            liked = True
    
    # 获取作者点赞数量
    author_likes = AuthorLike.query.filter_by(
        translation_id=translation_id,
        correction_id=None
    ).count()
    
    return jsonify({
        'success': True,
        'liked': liked,
        'likes_count': author_likes
    })

@app.route('/translator/<int:translator_id>/work/<int:work_id>/like', methods=['POST'])
def like_translator(translator_id, work_id):
    """对翻译者点赞"""
    if not is_logged_in():
        return jsonify({'success': False, 'message': get_message('please_login')})
    
    current_user = get_current_user()
    
    # 检查作品是否存在
    work = Work.query.get_or_404(work_id)
    
    # 检查翻译者是否存在且确实翻译了这个作品
    translator = User.query.get_or_404(translator_id)
    translation = Translation.query.filter_by(work_id=work_id, translator_id=translator_id).first()
    if not translation:
        return jsonify({'success': False, 'message': get_message('user_not_translated')})
    
    # 不能给自己点赞
    if current_user.id == translator_id:
        return jsonify({'success': False, 'message': get_message('cannot_like_self')})
    
    # 检查是否已经点赞
    existing_like = TranslatorLike.query.filter_by(
        user_id=current_user.id,
        translator_id=translator_id,
        work_id=work_id
    ).first()
    
    if existing_like:
        # 取消点赞
        db.session.delete(existing_like)
        liked = False
    else:
        # 添加点赞
        new_like = TranslatorLike(
            user_id=current_user.id,
            translator_id=translator_id,
            work_id=work_id
        )
        db.session.add(new_like)
        liked = True
    
    try:
        db.session.commit()
        
        # 点赞通知
        if liked and current_user.id != translator_id:
            receiver = User.query.get(translator_id)
            receiver_lang = getattr(receiver, 'preferred_language', 'zh') if receiver else 'zh'
            liker_name = current_user.username
            notification_content = f"{get_message('received_like', lang=receiver_lang)} - {liker_name}"
            if receiver:
                notification = Message(
                    sender_id=receiver.id,
                    receiver_id=receiver.id,
                    content=notification_content,
                    type='notification'
                )
                db.session.add(notification)
                db.session.commit()
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': get_message('error')})
    
    # 获取点赞数量
    likes_count = TranslatorLike.query.filter_by(
        translator_id=translator_id,
        work_id=work_id
    ).count()
    
    return jsonify({
        'success': True,
        'liked': liked,
        'likes_count': likes_count
    })

@app.route('/reviewer/<int:reviewer_id>/work/<int:work_id>/like', methods=['POST'])
def like_reviewer(reviewer_id, work_id):
    """对校正者点赞"""
    if not is_logged_in():
        return jsonify({'success': False, 'message': get_message('please_login')})
    
    current_user = get_current_user()
    
    # 检查作品是否存在
    work = Work.query.get_or_404(work_id)
    
    # 检查校正者是否存在且确实校正了这个作品
    reviewer = User.query.get_or_404(reviewer_id)
    correction = Correction.query.join(Translation).filter(
        Translation.work_id == work_id,
        Correction.reviewer_id == reviewer_id
    ).first()
    if not correction:
        return jsonify({'success': False, 'message': get_message('user_not_reviewed')})
    
    # 不能给自己点赞
    if current_user.id == reviewer_id:
        return jsonify({'success': False, 'message': get_message('cannot_like_self')})
    
    # 检查是否已经点赞
    existing_like = ReviewerLike.query.filter_by(
        user_id=current_user.id,
        reviewer_id=reviewer_id,
        work_id=work_id
    ).first()
    
    if existing_like:
        # 取消点赞
        db.session.delete(existing_like)
        liked = False
    else:
        # 添加点赞
        new_like = ReviewerLike(
            user_id=current_user.id,
            reviewer_id=reviewer_id,
            work_id=work_id
        )
        db.session.add(new_like)
        liked = True
    
    try:
        db.session.commit()
        
        # 点赞通知
        if liked and current_user.id != reviewer_id:
            receiver = User.query.get(reviewer_id)
            receiver_lang = getattr(receiver, 'preferred_language', 'zh') if receiver else 'zh'
            liker_name = current_user.username
            notification_content = f"{get_message('received_like', lang=receiver_lang)} - {liker_name}"
            if receiver:
                notification = Message(
                    sender_id=receiver.id,
                    receiver_id=receiver.id,
                    content=notification_content,
                    type='notification'
                )
                db.session.add(notification)
                db.session.commit()
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': get_message('error')})
    
    # 获取点赞数量
    likes_count = ReviewerLike.query.filter_by(
        reviewer_id=reviewer_id,
        work_id=work_id
    ).count()
    
    return jsonify({
        'success': True,
        'liked': liked,
        'likes_count': likes_count
    })

@app.route('/translator/<int:translator_id>/work/<int:work_id>/likes_count')
def get_translator_likes_count(translator_id, work_id):
    """获取翻译者点赞数量"""
    count = TranslatorLike.query.filter_by(
        translator_id=translator_id,
        work_id=work_id
    ).count()
    return jsonify({'likes_count': count})

@app.route('/reviewer/<int:reviewer_id>/work/<int:work_id>/likes_count')
def get_reviewer_likes_count(reviewer_id, work_id):
    """获取校正者点赞数量"""
    count = ReviewerLike.query.filter_by(
        reviewer_id=reviewer_id,
        work_id=work_id
    ).count()
    return jsonify({'likes_count': count})

# 评论相关路由
@app.route('/comment/add', methods=['POST'])
def add_comment():
    """添加评论 - 支持对作品、翻译、校正的评论"""
    if not is_logged_in():
        return jsonify({'success': False, 'message': get_message('please_login')})
    
    current_user = get_current_user()
    content = request.form.get('content', '').strip()
    work_id = request.form.get('work_id', type=int)
    translation_id = request.form.get('translation_id', type=int)
    correction_id = request.form.get('correction_id', type=int)
    
    if not content:
        return jsonify({'success': False, 'message': '评论内容不能为空'})
    
    if not work_id:
        return jsonify({'success': False, 'message': '作品ID不能为空'})
    
    # 验证作品存在
    work = Work.query.get_or_404(work_id)
    
    # 验证翻译评论的完整性
    if translation_id:
        translation = Translation.query.get(translation_id)
        if not translation:
            return jsonify({'success': False, 'message': '指定的翻译不存在'})
        if translation.work_id != work_id:
            return jsonify({'success': False, 'message': '翻译与作品不匹配'})
    
    # 验证校正评论的完整性
    if correction_id:
        correction = Correction.query.get(correction_id)
        if not correction:
            return jsonify({'success': False, 'message': '指定的校正不存在'})
        if correction.translation.work_id != work_id:
            return jsonify({'success': False, 'message': '校正与作品不匹配'})
    
    # 创建评论
    comment = Comment(
        content=content,
        author_id=current_user.id,
        work_id=work_id,
        translation_id=translation_id,
        correction_id=correction_id
    )
    
    db.session.add(comment)
    
    # 确定被评论的作者ID
    target_author_id = None
    comment_type = ""
    
    if correction_id:
        # 校正评论 - 通知校正者
        correction = Correction.query.get(correction_id)
        if correction and correction.reviewer_id != current_user.id:
            target_author_id = correction.reviewer_id
            comment_type = "correction"
    elif translation_id:
        # 翻译评论 - 通知翻译者
        translation = Translation.query.get(translation_id)
        if translation and translation.translator_id != current_user.id:
            target_author_id = translation.translator_id
            comment_type = "translation"
    else:
        # 一般评论 - 通知作品作者
        if work.creator_id != current_user.id:
            target_author_id = work.creator_id
            comment_type = "work"
    
    # 发送消息给被评论的作者
    if target_author_id:
        # 获取相关用户信息
        target_user = User.query.get(target_author_id)
        
        if target_user:
            # 生成消息内容
            if comment_type == "correction":
                message_content = get_system_message('correction_comment_received', target_author_id,
                                                   commenter_name=current_user.username,
                                                   work_title=work.title,
                                                   comment_content=content)
            elif comment_type == "translation":
                message_content = get_system_message('translation_comment_received', target_author_id,
                                                   commenter_name=current_user.username,
                                                   work_title=work.title,
                                                   comment_content=content)
            else:  # work comment
                message_content = get_system_message('work_comment_received', target_author_id,
                                                   commenter_name=current_user.username,
                                                   work_title=work.title,
                                                   comment_content=content)
            
            # 创建系统消息
            system_message = Message(
                sender_id=1,  # 系统用户ID
                receiver_id=target_author_id,
                content=message_content,
                type='system',
                work_id=work_id
            )
            db.session.add(system_message)
            
            # 发送邮件通知
            if target_user.email_notifications_enabled:
                from mail_utils import send_email
                # 使用目标用户的语言偏好
                target_lang = getattr(target_user, 'preferred_language', 'zh') or 'zh'
                subject = get_message('comment_notification', lang=target_lang)
                
                # 发送简洁的纯文本邮件
                send_email(target_user.email, subject, message_content, message_type='system', user_lang=target_lang)
    
    db.session.commit()
    
    return jsonify({
        'success': True, 
        'message': get_message('comment_added'),
        'comment_id': comment.id,
        'author_name': current_user.username,
        'created_at': comment.created_at.strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/comment/<int:comment_id>/delete', methods=['POST'])
def delete_comment(comment_id):
    """删除评论 - 只有评论作者或管理员可以删除"""
    if not is_logged_in():
        return jsonify({'success': False, 'message': get_message('please_login')})
    
    current_user = get_current_user()
    comment = Comment.query.get_or_404(comment_id)
    
    # 检查权限：只有评论作者或管理员可以删除
    if comment.author_id != current_user.id and current_user.role != 'admin':
        return jsonify({'success': False, 'message': get_message('no_permission_delete_comment')})
    
    # 保存评论信息用于发送消息
    comment_author_id = comment.author_id
    work = Work.query.get(comment.work_id)
    work_title = work.title if work else "未知作品"
    
    # 删除评论
    db.session.delete(comment)
    db.session.commit()
    
    # 如果是管理员删除，发送系统消息给评论作者
    if current_user.role == 'admin' and comment_author_id != current_user.id:
        system_message = Message(
            sender_id=1,  # 系统用户ID
            receiver_id=comment_author_id,
            content=get_system_message('admin_comment_deleted', comment_author_id, 
                                    work_title=work_title, admin_name=current_user.username),
            type='system',
            work_id=work.id if work else None
        )
        db.session.add(system_message)
        db.session.commit()
    
    return jsonify({
        'success': True, 
        'message': get_message('comment_deleted')
    })

@app.route('/comments/<target_type>/<int:target_id>')
def get_comments(target_type, target_id):
    """获取评论列表 - 支持作品、翻译、校正的评论"""
    if target_type == 'work':
        comments = Comment.query.filter_by(work_id=target_id, translation_id=None, correction_id=None).order_by(Comment.created_at.desc()).all()
    elif target_type == 'translation':
        comments = Comment.query.filter_by(translation_id=target_id).order_by(Comment.created_at.desc()).all()
    elif target_type == 'correction':
        comments = Comment.query.filter_by(correction_id=target_id).order_by(Comment.created_at.desc()).all()
    else:
        return jsonify({'success': False, 'message': '无效的评论类型'})
    
    comments_data = []
    current_user = get_current_user() if is_logged_in() else None
    
    for comment in comments:
        author = User.query.get(comment.author_id)
        
        # 获取评论点赞数
        likes_count = Like.query.filter_by(target_type='comment', target_id=comment.id).count()
        
        # 检查当前用户是否已点赞
        user_liked = False
        if current_user:
            user_liked = Like.query.filter_by(
                target_type='comment', 
                target_id=comment.id, 
                user_id=current_user.id
            ).first() is not None
        
        comments_data.append({
            'id': comment.id,
            'content': comment.content,
            'author_name': author.username if author else '未知用户',
            'author_id': comment.author_id,
            'author_avatar': author.avatar if author else None,
            'created_at': comment.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'can_delete': is_logged_in() and (get_current_user().id == comment.author_id or get_current_user().role == 'admin'),
            'likes_count': likes_count,
            'user_liked': user_liked
        })
    
    return jsonify({
        'success': True,
        'comments': comments_data
    })

# 收藏功能路由
@app.route('/favorites')
def favorites_list():
    """用户收藏列表页面"""
    if not is_logged_in():
        flash(get_message('please_login'), 'warning')
        return redirect(url_for('login'))
    
    current_user = get_current_user()
    page = request.args.get('page', 1, type=int)
    per_page = 12
    
    # 获取用户的收藏作品
    favorites_query = Favorite.query.filter_by(user_id=current_user.id).order_by(Favorite.created_at.desc())
    favorites = favorites_query.paginate(page=page, per_page=per_page, error_out=False)
    
    # 获取收藏的作品详情
    favorite_works = []
    for favorite in favorites.items:
        work = Work.query.get(favorite.work_id)
        if work:  # 只显示仍然存在的作品
            favorite_works.append({
                'work': work,
                'favorite_date': favorite.created_at,
                'like_count': Like.query.filter_by(target_type='work', target_id=work.id).count(),
                'translation_count': Translation.query.filter_by(work_id=work.id).count()
            })
    
    return render_template('favorites.html', 
                         favorites=favorite_works, 
                         pagination=favorites,
                         current_user=current_user)

@app.route('/favorite/<int:work_id>/toggle', methods=['POST'])
def toggle_favorite(work_id):
    """切换收藏状态"""
    if not is_logged_in():
        return jsonify({'success': False, 'message': get_message('please_login')})
    
    current_user = get_current_user()
    work = Work.query.get_or_404(work_id)
    
    # 检查是否已经收藏
    existing_favorite = Favorite.query.filter_by(user_id=current_user.id, work_id=work_id).first()
    
    if existing_favorite:
        # 取消收藏
        db.session.delete(existing_favorite)
        db.session.commit()
        return jsonify({
            'success': True, 
            'message': get_message('favorite_removed'),
            'is_favorited': False
        })
    else:
        # 添加收藏
        new_favorite = Favorite(user_id=current_user.id, work_id=work_id)
        db.session.add(new_favorite)
        db.session.commit()
        return jsonify({
            'success': True, 
            'message': get_message('favorite_added'),
            'is_favorited': True
        })

@app.route('/favorite/<int:work_id>/status')
def check_favorite_status(work_id):
    """检查作品的收藏状态"""
    if not is_logged_in():
        return jsonify({'is_favorited': False})
    
    current_user = get_current_user()
    existing_favorite = Favorite.query.filter_by(user_id=current_user.id, work_id=work_id).first()
    
    return jsonify({'is_favorited': existing_favorite is not None})

# 错误处理路由
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

@app.errorhandler(Exception)
def handle_exception(e):
    db.session.rollback()
    return render_template('error.html', error=str(e)), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # create_default_admin() 已移至seed_data.py中
    
    # 获取端口，Render会提供PORT环境变量
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)