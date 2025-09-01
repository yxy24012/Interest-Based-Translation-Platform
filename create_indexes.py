# -*- coding: utf-8 -*-
"""
数据库索引优化脚本
用于提高Vercel环境下的查询性能
"""

import os
from sqlalchemy import text
from app import app, db

def create_performance_indexes():
    """创建性能优化索引"""
    with app.app_context():
        try:
            # 用户相关索引
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
                CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
                CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at);
            """))
            
            # 作品相关索引
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_works_user_id ON works(user_id);
                CREATE INDEX IF NOT EXISTS idx_works_created_at ON works(created_at);
                CREATE INDEX IF NOT EXISTS idx_works_status ON works(status);
                CREATE INDEX IF NOT EXISTS idx_works_title ON works(title);
            """))
            
            # 翻译相关索引
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_translations_work_id ON translations(work_id);
                CREATE INDEX IF NOT EXISTS idx_translations_translator_id ON translations(translator_id);
                CREATE INDEX IF NOT EXISTS idx_translations_status ON translations(status);
                CREATE INDEX IF NOT EXISTS idx_translations_created_at ON translations(created_at);
            """))
            
            # 评论相关索引
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_comments_work_id ON comments(work_id);
                CREATE INDEX IF NOT EXISTS idx_comments_user_id ON comments(user_id);
                CREATE INDEX IF NOT EXISTS idx_comments_created_at ON comments(created_at);
            """))
            
            # 点赞相关索引
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_likes_target_type_target_id ON likes(target_type, target_id);
                CREATE INDEX IF NOT EXISTS idx_likes_user_id ON likes(user_id);
            """))
            
            # 收藏相关索引
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_favorites_user_id ON favorites(user_id);
                CREATE INDEX IF NOT EXISTS idx_favorites_work_id ON favorites(work_id);
                CREATE INDEX IF NOT EXISTS idx_favorites_created_at ON favorites(created_at);
            """))
            
            # 消息相关索引
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_messages_sender_id ON messages(sender_id);
                CREATE INDEX IF NOT EXISTS idx_messages_receiver_id ON messages(receiver_id);
                CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
                CREATE INDEX IF NOT EXISTS idx_messages_is_read ON messages(is_read);
            """))
            
            db.session.commit()
            print("✅ 数据库索引创建成功")
            
        except Exception as e:
            print(f"❌ 创建索引时出错: {e}")
            db.session.rollback()

if __name__ == '__main__':
    create_performance_indexes()
