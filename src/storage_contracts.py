from pymongo import ASCENDING


def ensure_unique_key_index(collection, key_fields: tuple[str, ...]) -> str:
    """Create the canonical unique index for an immutable record key."""
    name = f"uq_{'_'.join(key_fields)}"
    return collection.create_index(
        [(field, ASCENDING) for field in key_fields],
        unique=True,
        name=name,
    )
