"""
Channels configuration component (Django Implementation Blueprint §9).

Redis-backed channel layer, shared with the presence mechanism (no
second Redis usage pattern invented for presence specifically). No
business consumers/routing are registered here -- config/asgi.py wires
an empty per-app routing composition point, ready for `chat` and
`notifications` to add their own `interfaces/routing.py` when built.
"""
from __future__ import annotations

import os

ASGI_APPLICATION = "config.asgi.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [os.environ.get("CHANNELS_REDIS_URL", os.environ.get("REDIS_URL", "redis://localhost:6379/1"))],
        },
    },
}
