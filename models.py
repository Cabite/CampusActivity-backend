from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from config import Base

class User(Base):
    __tablename__ = 'user'
    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(String(20), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    username = Column(String(20), nullable=False)
    password = Column(String(255), nullable=False)
    gender = Column(String(10), nullable=False)
    college = Column(String(50), nullable=False)
    major = Column(String(50), nullable=False)
    grade = Column(String(20), nullable=False)
    phone = Column(String(11), nullable=True)
    avatar = Column(String(255), nullable=True)
    status = Column(String(20), default='active', index=True)  # active/deleted

class Organizer(Base):
    __tablename__ = 'organizer'
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    org_name = Column(String(50), nullable=False)
    password = Column(String(255), nullable=False)
    org_proof_text = Column(Text, nullable=False)
    org_proof_image = Column(String(255), nullable=True)
    avatar = Column(String(255), nullable=True)
    status = Column(String(20), default='pending', index=True)  # pending/approved/rejected/deleted
    reject_reason = Column(Text, nullable=True)

class Admin(Base):
    __tablename__ = 'admin'
    id = Column(Integer, primary_key=True, autoincrement=True)
    admin_no = Column(String(6), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=False)
    username = Column(String(50), nullable=False)
    avatar = Column(String(255), nullable=True)
    role = Column(String(20), default='admin')  # admin/super_admin
    status = Column(String(20), default='active')

class Category(Base):
    __tablename__ = 'category'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    parent_id = Column(Integer, default=0, index=True)
    level = Column(Integer, default=1, index=True)
    sort_order = Column(Integer, default=0)

class Activity(Base):
    __tablename__ = 'activity'
    id = Column(Integer, primary_key=True, autoincrement=True)
    organizer_id = Column(Integer, ForeignKey('organizer.id', ondelete='CASCADE'), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey('category.id'), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False)
    campus = Column(String(20), nullable=False, index=True)
    location = Column(String(100), nullable=False)
    max_participants = Column(Integer, nullable=False, default=1)
    registration_deadline = Column(DateTime, nullable=False)
    cancel_deadline = Column(DateTime, nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(20), default='draft', index=True)  # draft/pending/rejected/edit_pending/open/ongoing/ended/removed
    reject_reason = Column(Text, nullable=True)

class ActivityRevision(Base):
    __tablename__ = 'activity_revision'
    id = Column(Integer, primary_key=True, autoincrement=True)
    activity_id = Column(Integer, ForeignKey('activity.id', ondelete='CASCADE'), nullable=False, index=True)
    organizer_id = Column(Integer, ForeignKey('organizer.id', ondelete='CASCADE'), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey('category.id'), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False)
    campus = Column(String(20), nullable=False, index=True)
    location = Column(String(100), nullable=False)
    max_participants = Column(Integer, nullable=False, default=1)
    registration_deadline = Column(DateTime, nullable=False)
    cancel_deadline = Column(DateTime, nullable=False)
    description = Column(Text, nullable=False)
    reject_reason = Column(Text, nullable=True)

class Registration(Base):
    __tablename__ = 'registration'
    id = Column(Integer, primary_key=True, autoincrement=True)
    activity_id = Column(Integer, ForeignKey('activity.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey('user.id'), nullable=False, index=True)
    registration_time = Column(DateTime, default=func.now())
    status = Column(String(20), default='registered', index=True)  # registered/cancelled/rejected/re_registered/blocked
    reject_count = Column(Integer, default=0)
    last_reject_time = Column(DateTime, nullable=True)
    reject_reason = Column(Text, nullable=True)
    __table_args__ = (UniqueConstraint('activity_id', 'user_id', name='uniq_activity_user'),)

class Checkin(Base):
    __tablename__ = 'checkin'
    id = Column(Integer, primary_key=True, autoincrement=True)
    activity_id = Column(Integer, ForeignKey('activity.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey('user.id'), nullable=False, index=True)
    checkin_time = Column(DateTime, default=func.now())
    checkin_method = Column(String(20), nullable=False)  # code/manual
    operator_id = Column(Integer, nullable=True)  # 组织者ID
    __table_args__ = (UniqueConstraint('activity_id', 'user_id', name='uniq_checkin_activity_user'),)

class ActivityCheckinCode(Base):
    __tablename__ = 'activity_checkin_code'
    id = Column(Integer, primary_key=True, autoincrement=True)
    activity_id = Column(Integer, ForeignKey('activity.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    checkin_code = Column(String(6), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=func.now())

class Announcement(Base):
    __tablename__ = 'announcement'
    id = Column(Integer, primary_key=True, autoincrement=True)
    admin_id = Column(Integer, ForeignKey('admin.id'), nullable=False, index=True)
    title = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=func.now(), index=True)

class Notification(Base):
    __tablename__ = 'notification'
    id = Column(Integer, primary_key=True, autoincrement=True)
    receiver_type = Column(String(20), nullable=False)  # user/organizer
    receiver_id = Column(Integer, nullable=False, index=True)
    title = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    type = Column(String(30), nullable=False, index=True)  # registration_result/activity_audit_result/...
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now(), index=True)