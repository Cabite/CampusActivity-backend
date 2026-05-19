from sqlalchemy import asc, select

from models import Category


def list_category_tree(session):
    categories = session.execute(
        select(Category).order_by(asc(Category.level), asc(Category.sort_order), asc(Category.id))
    ).scalars().all()

    roots = []
    children_by_parent = {}
    for category in categories:
        item = {
            "id": category.id,
            "name": category.name,
            "level": category.level,
            "sort_order": category.sort_order,
        }
        if category.parent_id == 0:
            item["children"] = []
            roots.append(item)
        else:
            children_by_parent.setdefault(category.parent_id, []).append(item)

    for root in roots:
        root["children"] = children_by_parent.get(root["id"], [])

    return roots
