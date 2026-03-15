def to_dict(item):
    return item.model_dump() if hasattr(item, "model_dump") else item


def to_dict_list(items):
    return [
        item.model_dump() if hasattr(item, "model_dump") else item for item in items
    ]
