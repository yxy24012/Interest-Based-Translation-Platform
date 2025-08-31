# -*- coding: utf-8 -*-
"""PostgreSQL-safe initialization (creates tables if missing)."""
import os, sys
from datetime import datetime
from app import app, db

# Import models to register them with SQLAlchemy (edit if needed)
try:
    from app import models  # if you have an app/models.py
except Exception:
    pass

def seed_if_needed():
    try:
        from app.models import User
    except Exception:
        User = None
    if User:
        admin = db.session.execute(db.select(User).filter_by(username='admin')).scalar_one_or_none()
        if not admin:
            admin = User(username='admin', email='admin@example.com', is_admin=True, created_at=datetime.utcnow())
            # If you have set_password: admin.set_password('changeme')
            db.session.add(admin)
            print('✔ Inserted default admin user')

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print('⚠ Seed commit failed:', e)
        raise

def main():
    db_url = os.getenv('DATABASE_URL', app.config.get('SQLALCHEMY_DATABASE_URI', ''))
    print('Using DATABASE_URL:', (db_url[:80] + '...') if db_url else '(empty)')
    with app.app_context():
        print('Creating all tables if not exist ...')
        db.create_all()
        seed_if_needed()
        print('✅ init_db finished.')

if __name__ == '__main__':
    try:
        main(); sys.exit(0)
    except Exception as e:
        print('❌ init_db failed:', e, file=sys.stderr); sys.exit(1)
