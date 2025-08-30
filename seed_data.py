#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from datetime import datetime
import json
import os
import shutil

from werkzeug.security import generate_password_hash, check_password_hash

from app import db, User, Work, Translation, Comment, Like, Favorite, Correction


def _generate_localized_username_and_bio(base_name: str, preferred_language: str):
    """基于偏好语言生成更自然的网名与自我介绍。"""
    nickname_map = {
        'alice': {
            'zh': '清风行者',
            'ja': '星屑アリス',
            'en': 'LunaRider'
        },
        'bob': {
            'zh': '木鱼与浪',
            'ja': '星屑ランナー',
            'en': 'NightOwlBob'
        },
        'carol': {
            'zh': '云端回响',
            'ja': '月影キャロル',
            'en': 'EchoWaves'
        },
        'dave': {
            'zh': '拾光旅人',
            'ja': '灯下デイブ',
            'en': 'DustyTrails'
        },
        'erin': {
            'zh': '南风知我意',
            'ja': '月影の散歩者',
            'en': 'WanderingErin'
        },
        'frank': {
            'zh': '雾里看花',
            'ja': '雨宿りのフランク',
            'en': 'PixelVoyager'
        }
    }
    name = nickname_map.get(base_name, {}).get(preferred_language)
    if not name:
        name = (base_name.capitalize() if preferred_language == 'en' else f"{base_name.capitalize()}_user")

    if preferred_language == 'zh':
        bio = f"这里是{name}，热爱分享与交流。"
    elif preferred_language == 'ja':
        bio = f"{name}です。気軽に声をかけてください。"
    elif preferred_language == 'en':
        bio = f"I'm {name}. Always up for a good chat."
    else:
        bio = f"I'm {name}."
    return name, bio


def _ensure_unique_username(desired_username: str, current_email: str) -> str:
    """确保用户名唯一；如冲突，添加短后缀。"""
    owner = User.query.filter_by(username=desired_username).first()
    if not owner:
        return desired_username
    if owner.email == current_email:
        return desired_username
    suffix = 1
    candidate = f"{desired_username}_{suffix}"
    while User.query.filter_by(username=candidate).first() is not None:
        suffix += 1
        candidate = f"{desired_username}_{suffix}"
    return candidate


def _assign_avatar_file(target_filename: str) -> str:
    """为用户分配头像文件：从 static/ 读取源图，复制到 uploads/ 下。
    若 static/ 中对应文件不存在，则用 static/default_avatar.png 占位。
    返回供模板使用的相对路径（仅文件名，模板会按 /uploads/<filename> 引用）。
    """
    try:
        project_root = os.path.dirname(os.path.abspath(__file__))
        static_dir = os.path.join(project_root, 'static')
        uploads_dir = os.path.join(project_root, 'uploads')
        os.makedirs(static_dir, exist_ok=True)
        os.makedirs(uploads_dir, exist_ok=True)

        prefer_src = os.path.join(static_dir, target_filename)
        fallback_src = os.path.join(static_dir, 'default_avatar.png')
        src = prefer_src if os.path.exists(prefer_src) else fallback_src
        if not os.path.exists(src):
            return None

        dst = os.path.join(uploads_dir, target_filename)
        if not os.path.exists(dst):
            shutil.copyfile(src, dst)

        return target_filename
    except Exception:
        return None


def _get_or_create_user(username, email, role='user', preferred_language='zh',
                        is_creator=False, is_translator=False, is_reviewer=False,
                        avatar_filename: str = None):
    # admin用户特殊处理 - 直接使用'admin'作为用户名
    if email == 'lafengnidaye@gmail.com':
        localized_username = 'admin'
        localized_bio = "这里是管理员，负责平台运营。"
    else:
        localized_username, localized_bio = _generate_localized_username_and_bio(username, preferred_language)
    user = User.query.filter_by(email=email).first()
    if user:
        if user.username != localized_username:
            user.username = _ensure_unique_username(localized_username, email)
            user.preferred_language = preferred_language
            user.role = role or user.role
            user.is_creator = is_creator
            user.is_translator = is_translator
            user.is_reviewer = is_reviewer
            if not user.bio:
                user.bio = localized_bio
            if not getattr(user, 'avatar', None) and avatar_filename:
                user.avatar = _assign_avatar_file(avatar_filename)
            db.session.commit()
        return user
    
    # 为测试账号设置特定的ID和角色
    test_user_id = None
    
    # admin用户特殊处理
    if email == 'lafengnidaye@gmail.com':
        test_user_id = 1000  # admin用户使用ID 1000
        role = 'admin'  # 确保admin角色
    # 其他测试账号处理
    elif email.endswith('@example.com'):
        if email == 'alice@example.com':
            test_user_id = 1  # 系统用户ID 1，显示ID为1001
        elif email == 'bob@example.com':
            test_user_id = 2  # 系统用户ID 2，显示ID为1002
        elif email == 'carol@example.com':
            test_user_id = 3  # 系统用户ID 3，显示ID为1003
        elif email == 'dave@example.com':
            test_user_id = 4  # 系统用户ID 4，显示ID为1004
        elif email == 'erin@example.com':
            test_user_id = 5  # 系统用户ID 5，显示ID为1005
        elif email == 'frank@example.com':
            test_user_id = 6  # 系统用户ID 6，显示ID为1006
        
        if test_user_id:
            # 检查ID是否已被使用
            existing_user = User.query.get(test_user_id)
            if existing_user:
                # 如果ID已被使用，使用自动分配的ID
                test_user_id = None
        
        # 为测试用户设置系统角色
        role = 'system'
    
    user = User(
        username=_ensure_unique_username(localized_username, email),
        email=email,
        password_hash=generate_password_hash('admin'),
        role=role,
        preferred_language=preferred_language,
        is_creator=is_creator,
        is_translator=is_translator,
        is_reviewer=is_reviewer,
        bio=localized_bio,
        avatar=None,
        email_notifications_enabled=True if email == 'lafengnidaye@gmail.com' else False  # admin用户启用邮件通知，其他测试账号默认禁用
    )
    
    # 如果指定了测试用户ID，手动设置
    if test_user_id:
        user.id = test_user_id
    
    db.session.add(user)
    db.session.commit()
    if not user.avatar and avatar_filename:
        user.avatar = _assign_avatar_file(avatar_filename)
        db.session.commit()
    return user


def _get_or_create_work(title, creator_id, content, original_language='中文', target_language='英文',
                        category='文学', status='pending', tags=None, translation_requirements=None,
                        translation_expectation=None, allow_multiple_translators=True):
    work = Work.query.filter_by(title=title, creator_id=creator_id).first()
    if work:
        return work
    work = Work(
        title=title,
        content=content,
        original_language=original_language,
        target_language=target_language,
        category=category,
        status=status,
        creator_id=creator_id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        translation_requirements=translation_requirements,
        translation_expectation=translation_expectation,
        allow_multiple_translators=allow_multiple_translators,
        tags=json.dumps(tags or ['示例', '练习'])
    )
    db.session.add(work)
    db.session.commit()
    return work


def _get_or_create_translation(work_id, translator_id, content, status='submitted', reviewer_id=None, review_notes=None):
    translation = Translation.query.filter_by(work_id=work_id, translator_id=translator_id).first()
    if translation:
        return translation
    translation = Translation(
        work_id=work_id,
        translator_id=translator_id,
        content=content,
        status=status,
        reviewer_id=reviewer_id,
        review_notes=review_notes,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.session.add(translation)
    db.session.commit()
    return translation


def _get_or_create_correction(translation_id, reviewer_id, content, notes=None):
    correction = Correction.query.filter_by(translation_id=translation_id, reviewer_id=reviewer_id).first()
    if correction:
        return correction
    correction = Correction(
        translation_id=translation_id,
        reviewer_id=reviewer_id,
        content=content,
        notes=notes,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.session.add(correction)
    db.session.commit()
    return correction


def _create_comment_if_absent(content, author_id, work_id, translation_id=None, correction_id=None):
    exists = Comment.query.filter_by(
        content=content,
        author_id=author_id,
        work_id=work_id,
        translation_id=translation_id,
        correction_id=correction_id
    ).first()
    if exists:
        return exists
    comment = Comment(
        content=content,
        author_id=author_id,
        work_id=work_id,
        translation_id=translation_id,
        correction_id=correction_id,
        created_at=datetime.utcnow()
    )
    db.session.add(comment)
    db.session.commit()
    return comment


def _like_once(user_id, target_type, target_id):
    exists = Like.query.filter_by(user_id=user_id, target_type=target_type, target_id=target_id).first()
    if exists:
        return exists
    like = Like(user_id=user_id, target_type=target_type, target_id=target_id, created_at=datetime.utcnow())
    db.session.add(like)
    db.session.commit()
    return like


def _favorite_once(user_id, work_id):
    exists = Favorite.query.filter_by(user_id=user_id, work_id=work_id).first()
    if exists:
        return exists
    fav = Favorite(user_id=user_id, work_id=work_id, created_at=datetime.utcnow())
    db.session.add(fav)
    db.session.commit()
    return fav


def seed_database():
    """插入示例种子数据：多语言用户、作品、翻译、校正、评论、点赞、收藏。"""
    # 用户
    # 创建admin用户
    admin = create_default_admin()
    
    alice = _get_or_create_user('alice', 'alice@example.com', preferred_language='zh', is_creator=True, avatar_filename='avatar_scenery.png')
    bob = _get_or_create_user('bob', 'bob@example.com', preferred_language='ja', is_translator=True, avatar_filename='avatar_anime.png')
    carol = _get_or_create_user('carol', 'carol@example.com', preferred_language='en', is_reviewer=True, avatar_filename='avatar_portrait.png')
    dave = _get_or_create_user('dave', 'dave@example.com', preferred_language='zh', avatar_filename='avatar_city.png')
    erin = _get_or_create_user('erin', 'erin@example.com', preferred_language='ja', avatar_filename='avatar_anime2.png')
    frank = _get_or_create_user('frank', 'frank@example.com', preferred_language='en', avatar_filename='avatar_landscape.png')

    # 作品
    work1 = _get_or_create_work(
        title='春日随想',
        creator_id=alice.id,
        content='春风十里，不如你。清晨薄雾映花香，思绪随云起。',
        original_language='中文',
        target_language='日文',
        category='诗歌',
        status='translating',
        tags=['中文', '日文', '诗歌']
    )

    work2 = _get_or_create_work(
        title='A Stroll at Dusk',
        creator_id=frank.id,
        content='The horizon blushes as the sun bows out; footsteps soften with the night.',
        original_language='英文',
        target_language='中文',
        category='Prose',
        status='pending',
        tags=['English', '中文', '散文']
    )

    # 翻译（含审核）
    trans1 = _get_or_create_translation(
        work_id=work1.id,
        translator_id=bob.id,
        content='春風の十里、君に及ばず。朝靄は花の香りを映し、思いは雲とともに昇る。',
        status='approved',
        reviewer_id=carol.id,
        review_notes='语气自然，意象贴合原文。'
    )

    trans2 = _get_or_create_translation(
        work_id=work2.id,
        translator_id=bob.id,
        content='地平線は夕日に染まり、夜とともに足音は柔らぐ。',
        status='submitted',
        reviewer_id=None,
        review_notes=None
    )

    # 校正
    corr1 = _get_or_create_correction(
        translation_id=trans1.id,
        reviewer_id=carol.id,
        content='「朝靄は花の香りを映し」を「朝もやは花の香を映し」に修正を提案。',
        notes='助词搭配更自然，读感更顺。'
    )

    # 评论（作品、翻译、校正）
    _create_comment_if_absent('好喜欢这个意境！', dave.id, work1.id)  # zh
    _create_comment_if_absent('翻訳がとても生き生きしていて、読みやすいです。', erin.id, work1.id, translation_id=trans1.id)  # ja
    _create_comment_if_absent('This correction feels more natural in everyday usage.', frank.id, work1.id, correction_id=corr1.id)  # en

    # 点赞（作品/评论/翻译）
    _like_once(dave.id, 'work', work1.id)
    _like_once(erin.id, 'translation', trans1.id)
    first_comment = Comment.query.filter_by(work_id=work1.id).order_by(Comment.id.asc()).first()
    if first_comment:
        _like_once(frank.id, 'comment', first_comment.id)

    # 收藏
    _favorite_once(dave.id, work1.id)
    _favorite_once(erin.id, work1.id)
    _favorite_once(frank.id, work2.id)

    db.session.commit()


def create_default_admin():
    """创建默认admin用户和系统用户"""
    # 1) 确保系统用户占用 ID=1，避免 UNIQUE(id) 冲突
    id1_user = User.query.get(1)
    if id1_user is None:
        # 数据库中没有 id=1，直接创建系统用户为 id=1
        system = User(
            id=1,
            username='system',
            email='system@example.com',
            password_hash=generate_password_hash('system_password'),
            role='system'
        )
        db.session.add(system)
        db.session.commit()
        print("已创建系统用户 (ID=1)")
    else:
        # 已存在 id=1 的用户，规范化为系统用户，防止后续代码使用 sender_id=1 产生语义偏差
        if id1_user.username != 'system' or id1_user.role != 'system':
            id1_user.username = 'system'
            id1_user.email = 'system@example.com'
            id1_user.password_hash = generate_password_hash('system_password')
            id1_user.role = 'system'
            db.session.commit()
            print("已规范化系统用户 (ID=1)")
    
    # 2) 确保 admin 用户存在
    admin_user = User.query.filter_by(email='lafengnidaye@gmail.com').first()
    if not admin_user:
        admin = _get_or_create_user('admin', 'lafengnidaye@gmail.com', role='admin', preferred_language='zh',
                                   is_creator=True, is_translator=True, is_reviewer=True, avatar_filename='avatar_portrait.png')
        print(f"已创建admin用户: {admin.username} ({admin.email})")
        return admin
    else:
        # 确保admin用户有正确的用户名、权限设置和密码
        needs_update = False
        
        # 确保用户名是'admin'
        if admin_user.username != 'admin':
            admin_user.username = 'admin'
            needs_update = True
            
        # 确保密码是'admin'
        if not check_password_hash(admin_user.password_hash, 'admin'):
            admin_user.password_hash = generate_password_hash('admin')
            needs_update = True
            
        # 确保有正确的权限设置
        if not admin_user.is_creator or not admin_user.is_translator or not admin_user.is_reviewer:
            admin_user.is_creator = True
            admin_user.is_translator = True
            admin_user.is_reviewer = True
            needs_update = True
            
        # 确保邮件通知已启用
        if not admin_user.email_notifications_enabled:
            admin_user.email_notifications_enabled = True
            needs_update = True
            
        if needs_update:
            db.session.commit()
            print(f"已更新admin用户设置: {admin_user.username} ({admin_user.email})")
        else:
            print(f"admin用户已存在且设置正确: {admin_user.username} ({admin_user.email})")
        return admin_user


