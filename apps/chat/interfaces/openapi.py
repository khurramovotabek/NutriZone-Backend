"""
Chat OpenAPI tag registration.

Two tags, matching the "X / X Admin" convention already used by
Loyalty/Reviews (this module has no separate Ledger/Rewards-style
sub-area). WebSocket protocol is documented in this module's own
Interfaces certification report, not via OpenAPI/Swagger, since
OpenAPI's schema format has no native representation for a
persistent-connection, bidirectional-message protocol like this
one -- documenting it there would misrepresent it as a set of
discrete request/response HTTP operations, which it is not.
"""
from __future__ import annotations

CHAT_TAG = "Chat"
CHAT_ADMIN_TAG = "Chat Admin"

ALL_CHAT_TAGS = (CHAT_TAG, CHAT_ADMIN_TAG)
