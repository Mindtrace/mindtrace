from mindtrace.database import UnifiedMindtraceODM


def update_database(database: UnifiedMindtraceODM, sort_key: str, find_key: str, update_dict: dict):
    entries = database.find(getattr(database.redis_backend.model_cls, sort_key) == find_key)
    if len(entries) != 1:
        raise ValueError(f"Expected 1 entry for {sort_key} == {find_key}, got {len(entries)}")
    entry = entries[0]
    for key, value in update_dict.items():
        curr_entry = entry
        while "." in key:
            key, subkey = key.split(".", 1)
            curr_entry = getattr(curr_entry, key)
            key = subkey
        setattr(curr_entry, key, value)
    database.insert(entry)
    return entry
