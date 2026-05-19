import os
import sys
from datetime import datetime, timedelta

from sqlalchemy import inspect, text
from sqlalchemy.orm import sessionmaker
from werkzeug.security import generate_password_hash

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import Base, engine
from models import Activity, Admin, Category, Organizer, Registration, User


def add_column_if_missing(table_name, column_name, ddl):
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    if column_name not in columns:
        with engine.begin() as connection:
            connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {ddl}"))


def migrate_existing_sqlite_schema():
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "activity" in tables:
        add_column_if_missing("activity", "current_participants", "current_participants INTEGER NOT NULL DEFAULT 0")
    if "registration" in tables:
        add_column_if_missing("registration", "slot_release_at", "slot_release_at DATETIME")


def seed_categories(session):
    categories = [
        (1, "Academic", 0, 1, 1),
        (2, "Culture and Sports", 0, 1, 2),
        (3, "Public Service", 0, 1, 3),
        (4, "Career", 0, 1, 4),
        (5, "Social", 0, 1, 5),
        (6, "Training", 0, 1, 6),
        (7, "Other", 0, 1, 7),
        (101, "Lecture", 1, 2, 1),
        (102, "Competition", 1, 2, 2),
        (103, "Salon", 1, 2, 3),
        (201, "Sports Meet", 2, 2, 1),
        (202, "Sports Competition", 2, 2, 2),
        (203, "Performance", 2, 2, 3),
        (301, "Volunteer Service", 3, 2, 1),
        (302, "Donation", 3, 2, 2),
        (401, "Recruitment", 4, 2, 1),
        (402, "Career Talk", 4, 2, 2),
        (403, "Internship Sharing", 4, 2, 3),
        (404, "Resume Coaching", 4, 2, 4),
        (501, "Meetup", 5, 2, 1),
        (502, "Club Recruitment", 5, 2, 2),
        (503, "Orientation", 5, 2, 3),
        (601, "Skill Training", 6, 2, 1),
        (602, "Language Training", 6, 2, 2),
        (603, "Exam Coaching", 6, 2, 3),
    ]
    existing_ids = {row[0] for row in session.query(Category.id).all()}
    for category_id, name, parent_id, level, sort_order in categories:
        if category_id not in existing_ids:
            session.add(Category(id=category_id, name=name, parent_id=parent_id, level=level, sort_order=sort_order))


def seed_accounts(session):
    admin = session.query(Admin).filter(Admin.admin_no == "000001").first()
    if not admin:
        admin = Admin(
            admin_no="000001",
            email="admin@example.com",
            password=generate_password_hash(os.getenv("ADMIN_PASSWORD", "Admin123456")),
            username="Super Admin",
            role="super_admin",
            status="active",
        )
        session.add(admin)
    elif not str(admin.password).startswith(("pbkdf2:", "scrypt:")):
        admin.password = generate_password_hash(os.getenv("ADMIN_PASSWORD", "Admin123456"))
        admin.email = admin.email or "admin@example.com"
        admin.username = admin.username or "Super Admin"
        admin.status = "active"

    organizer = session.query(Organizer).filter(Organizer.email == "org@example.com").first()
    if not organizer:
        session.add(
            Organizer(
                email="org@example.com",
                org_name="Student Union",
                password=generate_password_hash("password123"),
                org_proof_text="Demo approved organizer",
                status="approved",
            )
        )

    user = session.query(User).filter(User.student_id == "2024000001").first()
    if not user:
        session.add(
            User(
                student_id="2024000001",
                email="user@example.com",
                username="Demo Student",
                password=generate_password_hash("password123"),
                gender="male",
                college="Computer School",
                major="Computer Science",
                grade="2024",
                phone="13800138000",
                status="active",
            )
        )


def seed_demo_activity(session):
    organizer = session.query(Organizer).filter(Organizer.email == "org@example.com").first()
    user = session.query(User).filter(User.student_id == "2024000001").first()
    if not organizer or not user:
        return

    activity = session.query(Activity).filter(Activity.name == "AI Frontiers Lecture").first()
    if not activity:
        start = datetime.utcnow() + timedelta(minutes=10)
        activity = Activity(
            organizer_id=organizer.id,
            category_id=101,
            name="AI Frontiers Lecture",
            start_time=start,
            end_time=start + timedelta(hours=3),
            campus="Liangxiang",
            location="Library Auditorium",
            max_participants=100,
            current_participants=0,
            registration_deadline=start - timedelta(minutes=5),
            cancel_deadline=start - timedelta(minutes=5),
            description="Demo activity for registration and check-in integration.",
            status="open",
        )
        session.add(activity)
        session.flush()

    row = session.query(Registration).filter(Registration.activity_id == activity.id, Registration.user_id == user.id).first()
    if not row:
        session.add(Registration(activity_id=activity.id, user_id=user.id, status="registered"))
        activity.current_participants = 1


def init_database():
    Base.metadata.create_all(bind=engine)
    migrate_existing_sqlite_schema()

    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        seed_categories(session)
        seed_accounts(session)
        session.commit()
        seed_demo_activity(session)
        session.commit()
        print("Database initialized and demo data seeded.")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    init_database()
