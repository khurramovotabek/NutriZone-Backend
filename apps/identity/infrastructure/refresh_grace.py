"""
Refresh-token reuse grace window (2026-11-20).

Refresh tokens are single-use: presenting a rotated-out token revokes the whole session family (theft signature).
But one browser legitimately sends the SAME refresh token several times at once -- parallel requests right after its
15-minute access cookie expired. The storefront deduplicated that inside its single Node.js process, which is why it
could never run more than one process. This makes the backend itself idempotent for a short window instead:

* the first presentation rotates as before and, after commit, remembers the new pair for GRACE_SECONDS under the
  presented token's hash;
* a presentation that arrives while that rotation is still running waits for it (Redis lock) and gets the same pair;
* a presentation within the window gets the same pair -- as long as the new session is still active (a logout or a
  reuse revocation in between ends the grace);
* after the window, reuse is reuse: the session family is revoked as before.

Same trade-off as Auth0's "reuse interval": someone holding the old token gets nothing the legitimate presenter
did not already get in those seconds. Pairs live only in Redis, keyed by the token's hash, never the raw token.
"""
from __future__ import annotations

import time

from django.core.cache import cache

GRACE_SECONDS = 30
_LOCK_SECONDS = 15
_RESULT = "identity:refresh_grace:result:"
_LOCK = "identity:refresh_grace:lock:"


class RedisRefreshGrace:
    def recall(self, token_hash: str) -> dict | None:
        return cache.get(_RESULT + token_hash)

    def claim(self, token_hash: str) -> bool:
        """True: this request rotates the token. False: another one is already doing it."""
        return cache.add(_LOCK + token_hash, 1, _LOCK_SECONDS)

    def wait(self, token_hash: str, timeout: float = 5.0) -> dict | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self.recall(token_hash)
            if result is not None:
                return result
            if cache.get(_LOCK + token_hash) is None:  # the other rotation gave up (failed / rolled back)
                return None
            time.sleep(0.05)
        return None

    def remember(self, token_hash: str, result: dict) -> None:
        cache.set(_RESULT + token_hash, result, GRACE_SECONDS)
        cache.delete(_LOCK + token_hash)

    def release(self, token_hash: str) -> None:
        cache.delete(_LOCK + token_hash)
