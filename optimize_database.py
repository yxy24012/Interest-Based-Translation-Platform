# -*- coding: utf-8 -*-
"""
数据库索引优化脚本
提升查询性能
"""

import os
from sqlalchemy import text
from app import app, db

def create_database_indexes():
    """创建数据库索引以优化查询性能"""
    
    with app.app_context():
        try:
            # 检测数据库类型
            backend = db.engine.url.get_backend_name()
            print(f"正在为 {backend} 数据库创建索引...")
            
            if backend.startswith('postgres'):
                # PostgreSQL 索引
                indexes = [
                    # 点赞表索引
                    "CREATE INDEX IF NOT EXISTS idx_like_target_type_id ON \"like\" (target_type, target_id)",
                    "CREATE INDEX IF NOT EXISTS idx_like_user_id ON \"like\" (user_id)",
                    
                    # 作品表索引
                    "CREATE INDEX IF NOT EXISTS idx_work_created_at ON work (created_at DESC)",
                    "CREATE INDEX IF NOT EXISTS idx_work_creator_id ON work (creator_id)",
                    "CREATE INDEX IF NOT EXISTS idx_work_status ON work (status)",
                    "CREATE INDEX IF NOT EXISTS idx_work_category ON work (category)",
                    "CREATE INDEX IF NOT EXISTS idx_work_languages ON work (original_language, target_language)",
                    
                    # 翻译表索引
                    "CREATE INDEX IF NOT EXISTS idx_translation_work_id ON translation (work_id)",
                    "CREATE INDEX IF NOT EXISTS idx_translation_translator_id ON translation (translator_id)",
                    "CREATE INDEX IF NOT EXISTS idx_translation_status ON translation (status)",
                    "CREATE INDEX IF NOT EXISTS idx_translation_created_at ON translation (created_at DESC)",
                    
                    # 消息表索引
                    "CREATE INDEX IF NOT EXISTS idx_message_receiver_type ON message (receiver_id, type, is_read)",
                    "CREATE INDEX IF NOT EXISTS idx_message_sender_id ON message (sender_id)",
                    "CREATE INDEX IF NOT EXISTS idx_message_created_at ON message (created_at DESC)",
                    
                    # 评论表索引
                    "CREATE INDEX IF NOT EXISTS idx_comment_target ON comment (target_type, target_id)",
                    "CREATE INDEX IF NOT EXISTS idx_comment_user_id ON comment (user_id)",
                    "CREATE INDEX IF NOT EXISTS idx_comment_created_at ON comment (created_at DESC)",
                    
                    # 用户表索引
                    "CREATE INDEX IF NOT EXISTS idx_user_username ON \"user\" (username)",
                    "CREATE INDEX IF NOT EXISTS idx_user_email ON \"user\" (email)",
                    "CREATE INDEX IF NOT EXISTS idx_user_role ON \"user\" (role)",
                    
                    # 好友关系表索引
                    "CREATE INDEX IF NOT EXISTS idx_friend_user_id ON friend (user_id)",
                    "CREATE INDEX IF NOT EXISTS idx_friend_friend_id ON friend (friend_id)",
                    "CREATE INDEX IF NOT EXISTS idx_friend_status ON friend (status)",
                    
                    # 收藏表索引
                    "CREATE INDEX IF NOT EXISTS idx_favorite_user_work ON favorite (user_id, work_id)",
                    "CREATE INDEX IF NOT EXISTS idx_favorite_created_at ON favorite (created_at DESC)",
                    
                    # 翻译请求表索引
                    "CREATE INDEX IF NOT EXISTS idx_translation_request_work_id ON translation_request (work_id)",
                    "CREATE INDEX IF NOT EXISTS idx_translation_request_translator_id ON translation_request (translator_id)",
                    "CREATE INDEX IF NOT EXISTS idx_translation_request_status ON translation_request (status)",
                    
                    # 翻译者请求表索引
                    "CREATE INDEX IF NOT EXISTS idx_translator_request_work_id ON translator_request (work_id)",
                    "CREATE INDEX IF NOT EXISTS idx_translator_request_translator_id ON translator_request (translator_id)",
                    "CREATE INDEX IF NOT EXISTS idx_translator_request_status ON translator_request (status)",
                    
                    # 校正表索引
                    "CREATE INDEX IF NOT EXISTS idx_correction_work_id ON correction (work_id)",
                    "CREATE INDEX IF NOT EXISTS idx_correction_reviewer_id ON correction (reviewer_id)",
                    "CREATE INDEX IF NOT EXISTS idx_correction_created_at ON correction (created_at DESC)"
                ]
                
            else:
                # SQLite 索引
                indexes = [
                    # 点赞表索引
                    "CREATE INDEX IF NOT EXISTS idx_like_target_type_id ON 'like' (target_type, target_id)",
                    "CREATE INDEX IF NOT EXISTS idx_like_user_id ON 'like' (user_id)",
                    
                    # 作品表索引
                    "CREATE INDEX IF NOT EXISTS idx_work_created_at ON work (created_at DESC)",
                    "CREATE INDEX IF NOT EXISTS idx_work_creator_id ON work (creator_id)",
                    "CREATE INDEX IF NOT EXISTS idx_work_status ON work (status)",
                    "CREATE INDEX IF NOT EXISTS idx_work_category ON work (category)",
                    "CREATE INDEX IF NOT EXISTS idx_work_languages ON work (original_language, target_language)",
                    
                    # 翻译表索引
                    "CREATE INDEX IF NOT EXISTS idx_translation_work_id ON translation (work_id)",
                    "CREATE INDEX IF NOT EXISTS idx_translation_translator_id ON translation (translator_id)",
                    "CREATE INDEX IF NOT EXISTS idx_translation_status ON translation (status)",
                    "CREATE INDEX IF NOT EXISTS idx_translation_created_at ON translation (created_at DESC)",
                    
                    # 消息表索引
                    "CREATE INDEX IF NOT EXISTS idx_message_receiver_type ON message (receiver_id, type, is_read)",
                    "CREATE INDEX IF NOT EXISTS idx_message_sender_id ON message (sender_id)",
                    "CREATE INDEX IF NOT EXISTS idx_message_created_at ON message (created_at DESC)",
                    
                    # 评论表索引
                    "CREATE INDEX IF NOT EXISTS idx_comment_target ON comment (target_type, target_id)",
                    "CREATE INDEX IF NOT EXISTS idx_comment_user_id ON comment (user_id)",
                    "CREATE INDEX IF NOT EXISTS idx_comment_created_at ON comment (created_at DESC)",
                    
                    # 用户表索引
                    "CREATE INDEX IF NOT EXISTS idx_user_username ON user (username)",
                    "CREATE INDEX IF NOT EXISTS idx_user_email ON user (email)",
                    "CREATE INDEX IF NOT EXISTS idx_user_role ON user (role)",
                    
                    # 好友关系表索引
                    "CREATE INDEX IF NOT EXISTS idx_friend_user_id ON friend (user_id)",
                    "CREATE INDEX IF NOT EXISTS idx_friend_friend_id ON friend (friend_id)",
                    "CREATE INDEX IF NOT EXISTS idx_friend_status ON friend (status)",
                    
                    # 收藏表索引
                    "CREATE INDEX IF NOT EXISTS idx_favorite_user_work ON favorite (user_id, work_id)",
                    "CREATE INDEX IF NOT EXISTS idx_favorite_created_at ON favorite (created_at DESC)",
                    
                    # 翻译请求表索引
                    "CREATE INDEX IF NOT EXISTS idx_translation_request_work_id ON translation_request (work_id)",
                    "CREATE INDEX IF NOT EXISTS idx_translation_request_translator_id ON translation_request (translator_id)",
                    "CREATE INDEX IF NOT EXISTS idx_translation_request_status ON translation_request (status)",
                    
                    # 翻译者请求表索引
                    "CREATE INDEX IF NOT EXISTS idx_translator_request_work_id ON translator_request (work_id)",
                    "CREATE INDEX IF NOT EXISTS idx_translator_request_translator_id ON translator_request (translator_id)",
                    "CREATE INDEX IF NOT EXISTS idx_translator_request_status ON translator_request (status)",
                    
                    # 校正表索引
                    "CREATE INDEX IF NOT EXISTS idx_correction_work_id ON correction (work_id)",
                    "CREATE INDEX IF NOT EXISTS idx_correction_reviewer_id ON correction (reviewer_id)",
                    "CREATE INDEX IF NOT EXISTS idx_correction_created_at ON correction (created_at DESC)"
                ]
            
            # 执行索引创建
            success_count = 0
            for index_sql in indexes:
                try:
                    with db.engine.connect() as conn:
                        conn.execute(text(index_sql))
                        conn.commit()
                    success_count += 1
                    print(f"✅ 创建索引成功: {index_sql[:50]}...")
                except Exception as e:
                    print(f"⚠️ 索引创建失败: {index_sql[:50]}... - {e}")
            
            print(f"\n🎉 索引创建完成！成功创建 {success_count}/{len(indexes)} 个索引")
            
            # 分析表统计信息
            if backend.startswith('postgres'):
                analyze_tables()
                
        except Exception as e:
            print(f"❌ 索引创建过程中发生错误: {e}")

def analyze_tables():
    """分析表统计信息（PostgreSQL）"""
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ANALYZE"))
            conn.commit()
        print("✅ 表统计信息已更新")
    except Exception as e:
        print(f"⚠️ 更新表统计信息失败: {e}")

def check_indexes():
    """检查现有索引"""
    with app.app_context():
        try:
            backend = db.engine.url.get_backend_name()
            
            if backend.startswith('postgres'):
                # PostgreSQL 查询索引
                with db.engine.connect() as conn:
                    result = conn.execute(text("""
                        SELECT 
                            schemaname,
                            tablename,
                            indexname,
                            indexdef
                        FROM pg_indexes 
                        WHERE schemaname = 'public'
                        ORDER BY tablename, indexname
                    """))
            else:
                # SQLite 查询索引
                with db.engine.connect() as conn:
                    result = conn.execute(text("""
                        SELECT 
                            name as indexname,
                            tbl_name as tablename,
                            sql as indexdef
                        FROM sqlite_master 
                        WHERE type = 'index'
                        ORDER BY tbl_name, name
                    """))
            
            print(f"\n📊 当前数据库索引列表 ({backend}):")
            print("-" * 80)
            
            current_table = ""
            for row in result:
                if row.tablename != current_table:
                    current_table = row.tablename
                    print(f"\n📋 表: {current_table}")
                
                print(f"  🔍 {row.indexname}")
            
            print("-" * 80)
            
        except Exception as e:
            print(f"❌ 检查索引失败: {e}")

if __name__ == '__main__':
    print("🚀 开始数据库索引优化...")
    create_database_indexes()
    check_indexes()
    print("✨ 数据库优化完成！")
