"""
`/api/public/` namespace root.

Reserved for future unauthenticated or API-key-authenticated endpoints
(REST API Blueprint §2) -- e.g. a future franchise/B2B external
integration feed. Empty at launch and at foundation stage; the
namespace exists now so it never needs retrofitting under a versioned
path later.
"""
from __future__ import annotations

app_name = "public"

urlpatterns: list = []
