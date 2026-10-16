"""Identifier generation.

Ids are `<prefix>_<millis-hex><random-hex>`: readable in logs, unique, and roughly
time-ordered so lexical sorting follows creation order.
"""

import secrets
import time


def new_id(prefix: str) -> str:
    millis = time.time_ns() // 1_000_000
    return f"{prefix}_{millis:011x}{secrets.token_hex(4)}"
