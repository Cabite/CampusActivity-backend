from models import Notification


def create_notification(session, receiver_type, receiver_id, title, content, notice_type, related_id=None):
    notification = Notification(
        receiver_type=receiver_type,
        receiver_id=receiver_id,
        title=title,
        content=content,
        type=notice_type,
        related_id=related_id,
        is_read=False,
    )
    session.add(notification)
    return notification
