import os
import sys
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

# 确保可以导入 config 和 models
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import SQLALCHEMY_DATABASE_URL, Base, engine
from models import Category, Admin

def init_database():
    # 创建所有表
    Base.metadata.create_all(bind=engine)
    print("所有表已创建")

    Session = sessionmaker(bind=engine)
    session = Session()

    # 1. 插入分类数据
    categories_data = [
        # 一级分类
        (1, '学术类', 0, 1, 1),
        (2, '文体类', 0, 1, 2),
        (3, '公益类', 0, 1, 3),
        (4, '就业类', 0, 1, 4),
        (5, '社交类', 0, 1, 5),
        (6, '培训类', 0, 1, 6),
        (7, '其他', 0, 1, 7),
        # 二级分类
        (101, '讲座', 1, 2, 1),
        (102, '竞赛', 1, 2, 2),
        (103, '沙龙', 1, 2, 3),
        (201, '运动会', 2, 2, 1),
        (202, '体育竞赛', 2, 2, 2),
        (203, '文艺演出', 2, 2, 3),
        (301, '志愿服务', 3, 2, 1),
        (302, '捐赠活动', 3, 2, 2),
        (401, '招聘会', 4, 2, 1),
        (402, '宣讲会', 4, 2, 2),
        (403, '实习分享', 4, 2, 3),
        (404, '简历指导', 4, 2, 4),
        (501, '联谊会', 5, 2, 1),
        (502, '社团招新', 5, 2, 2),
        (503, '迎新会', 5, 2, 3),
        (601, '技能培训', 6, 2, 1),
        (602, '语言培训', 6, 2, 2),
        (603, '考证辅导', 6, 2, 3),
    ]

    existing_categories = session.query(Category.id).all()
    existing_ids = {c[0] for c in existing_categories}
    for cat_id, name, parent_id, level, sort_order in categories_data:
        if cat_id not in existing_ids:
            cat = Category(id=cat_id, name=name, parent_id=parent_id, level=level, sort_order=sort_order)
            session.add(cat)

    # 2. 插入 0 号超级管理员（如果不存在）
    admin_exists = session.query(Admin).filter_by(admin_no='000001').first()
    if not admin_exists:
        # 注意：密码此处存储明文，实际应用应使用 bcrypt 等哈希。此处仅为数据库初始化框架。
        # 后续您的同事可以自行修改密码哈希方式。
        super_admin = Admin(
            admin_no='000001',
            email='admin@campus.com',
            password='admin123',   # 明文，仅用于初始化示例，务必后续改为哈希
            username='超级管理员',
            role='super_admin',
            status='active'
        )
        session.add(super_admin)

    session.commit()
    print("初始化数据插入完成（分类 + 超级管理员）")
    session.close()

if __name__ == '__main__':
    init_database()