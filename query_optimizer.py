# -*- coding: utf-8 -*-
"""
查询优化工具
减少N+1查询问题，提升查询性能
"""

from sqlalchemy.orm import joinedload
from sqlalchemy import func
from app import db

def get_optimized_hot_works(limit=6):
    """获取优化的热门作品查询"""
    from app import Work, Like
    
    # 使用子查询优化
    subquery = db.session.query(
        Work.id,
        func.count(Like.id).label('like_count')
    ).outerjoin(Like, db.and_(
        Work.id == Like.target_id,
        Like.target_type == 'work'
    )).group_by(Work.id).subquery()
    
    # 主查询
    works = db.session.query(Work).join(
        subquery, Work.id == subquery.c.id
    ).order_by(subquery.c.like_count.desc()).limit(limit).all()
    
    return works

def get_optimized_recent_works(limit=6):
    """获取优化的最新作品查询"""
    from app import Work
    
    return Work.query.options(
        joinedload(Work.creator)
    ).order_by(Work.created_at.desc()).limit(limit).all()

def get_optimized_works_with_pagination(page=1, per_page=10, **filters):
    """获取优化的分页作品查询"""
    from app import Work
    
    query = Work.query
    
    # 应用过滤器
    if filters.get('search'):
        search = filters['search']
        query = query.filter(
            db.or_(
                Work.title.contains(search),
                Work.content.contains(search)
            )
        )
    
    if filters.get('category'):
        query = query.filter(Work.category == filters['category'])
    
    if filters.get('status'):
        query = query.filter(Work.status == filters['status'])
    
    if filters.get('original_language'):
        query = query.filter(Work.original_language == filters['original_language'])
    
    if filters.get('target_language'):
        query = query.filter(Work.target_language == filters['target_language'])
    
    if filters.get('allow_multiple_translators'):
        query = query.filter(Work.allow_multiple_translators == True)
    
    # 预加载关联数据（减少N+1查询）
    query = query.options(
        joinedload(Work.creator)
    )
    
    # 排序和分页
    query = query.order_by(Work.created_at.desc())
    
    return query.paginate(
        page=page, 
        per_page=per_page, 
        error_out=False
    )
