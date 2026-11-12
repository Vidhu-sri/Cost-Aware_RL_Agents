"""Classify known resource failures; unrelated code failures must stay visible."""
def gpu_memory_failure(text):
    text=text.lower()
    return any(marker in text for marker in (
        'cuda out of memory',
        'larger than the available kv cache memory',
        'no available memory for the cache blocks',
        'free memory on device',
        'insufficient gpu free memory',
    ))
