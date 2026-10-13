# Cart Module — Phase 3 (Interfaces) Certification Report

**Every number in this report was counted directly from source during this phase — no number is reused from Phase 1 or Phase 2's reports.**

---

## Step 1 — Architecture Review Findings

Verified directly, not assumed:

| Check | Result |
|---|---|
| `apps/cart/interfaces/` scaffold exists | ✓ Confirmed — empty `__init__.py` tree only |
| Phase 2 Infrastructure compiles | ✓ Confirmed — `apps/cart/infrastructure/*.py` recompiled fresh before any new code was written |
| Every Application Service has a Composition factory | ✓ Confirmed — 28 services (Phase 1's count), 31 factories, before this phase's own additions |
| Repository construction only inside Composition Root | ✓ Confirmed against Pricing's `composition.py` |
| Response envelope / pagination location | ✓ Confirmed at `common/responses/envelope.py` (a package, not a single file — an initial grep against the wrong path shape returned nothing, worth double-checking rather than concluding it was missing, the same lesson already learned in Pricing's Phase 3 review) |
| OpenAPI conventions | ✓ Confirmed `core/openapi` is a package exposing `STANDARD_ERROR_RESPONSES` via its `__init__.py`, same shape as `common.responses` |
| Routing conventions | ✓ Confirmed against Pricing's `urls.py` (public routes at top level, admin-scoped routes prefixed) |

### Two real inconsistencies discovered during Interfaces implementation, and resolved

Both were found only once actual endpoint-by-endpoint implementation began — Step 1's own convention checks didn't surface them, since they're gaps in *what Phase 1 built*, not in *how Phase 2/3 follow convention*. Both are reported with the same rigor as a Step 1 finding, per this phase's explicit instruction to never silently work around an inconsistency.

**Inconsistency 1 — no way to resolve a cart by `code`.** Every required endpoint in this phase's brief uses `{code}` as the URL identifier (`GET /cart/{code}/`, etc.), but the `CartRepository` Port from Phase 1 only ever defined `get_by_id`/`get_by_token`/`get_active_for_customer` — there is no `get_by_code`. Building the routes as specified was otherwise impossible without either violating "no ORM in views" (querying `CartModel.objects.get(code=...)` directly from a view) or silently changing the URL scheme away from what was explicitly requested. **Resolution:** added one method, `get_by_code()`, to the `CartRepository` Port and its concrete `DjangoCartRepository` implementation — the minimum necessary fix, following the exact shape of the existing `get_by_token()`. `LoadCart`'s `execute()` signature was extended to accept an optional `code` parameter for the same reason.

**Inconsistency 2 — three required endpoints had no backing Application Service, and I caught myself about to violate this phase's own rules to work around it.** `POST /cart/{code}/lock/`, `POST /cart/{code}/unlock/`, and `PATCH /cart/{code}/` (note/gift_message) all lacked a corresponding service in Phase 1's 28-service set. My first draft of the views called `Cart.lock()`/`Cart.unlock()` and constructed `CartNote`/`GiftMessage` value objects directly inside the view, then saved via the repository — which is exactly the "business logic in views" / "aggregate construction in views" violation this phase's own validation gates explicitly forbid. **Resolution:** added three minimal Application Services — `LockCart`, `UnlockCart`, `UpdateCartDetails` — each following the identical shape of every other simple lifecycle service in `application/services/lifecycle.py`, and rewired all three views to call them through composition instead. This was caught and fixed before this report, not left in.

**A third, narrower gap, disclosed rather than silently patched over:** `POST /cart/{code}/convert/` is a required endpoint, but no `Cart.convert()` domain method or `ConvertCart` service exists anywhere — and none should be invented here, since a genuine conversion (Cart → Order) is conceptually Ordering's responsibility, not something Cart's Phase 1 domain was ever designed to perform itself. Rather than fabricate a fake "conversion," `ConvertCartView` is implemented as an explicitly documented placeholder that performs the closest legitimate action available today (locking the cart via the newly-added `LockCart` service) — its OpenAPI summary literally says "[Placeholder]" and its description explains why, so this is visible to any API consumer, not just to someone reading this report.

**No other architectural inconsistency was discovered.**

---

## 1. Folder Tree

```
apps/cart/interfaces/api/v1/
├── permissions.py
├── filters.py
├── serializers.py
├── views.py
└── urls.py
```

---

## 2. Files Created

5 new files under `apps/cart/interfaces/api/v1/`, plus `config/urls/v1.py` updated to mount them at `/api/v1/cart/`, plus the minimum-necessary Phase 1/2 additions documented above (`CartRepository.get_by_code`, `DjangoCartRepository.get_by_code`, `LoadCart.execute(code=...)`, and three new Application Services: `LockCart`, `UnlockCart`, `UpdateCartDetails`, each with a composition factory).

---

## 3. API Endpoint Summary

**16 view classes, 23 HTTP methods, 16 URL routes** — matching this phase's required endpoint list exactly:

| Group | Endpoints |
|---|---|
| Cart | list+create (merged), detail (GET/PATCH/DELETE) |
| Items | create, detail (PATCH/DELETE), clear |
| Coupon | apply (POST) / remove (DELETE) — one view, two methods |
| Reservation | attach (POST) / detach (DELETE) — one view, two methods |
| Price Snapshot | attach (POST) / detach (DELETE) — one view, two methods |
| Merge | merge |
| Lifecycle | lock, unlock, convert (placeholder, see above) |
| Validation | validate |
| Search | search |
| Audit | audit trail |
| Snapshot History | snapshot history |

**Every collection endpoint merges GET+POST into one view class** (`CartListCreateView`), avoiding the routing bug class already found and fixed in Products, by construction.

---

## 4. Serializer Summary

**21 serializers** across read shapes (`Cart`, `CartItem`, `PriceSnapshotReference`, `ReservationReference`, `CartSnapshot`, `CartAuditEntry`, `ValidationIssue`), response shapes (`CartSummary`, `CartCalculation` — a reserved, not-yet-populated shape per this phase's explicit list; no Application Service computes cart totals yet, since that's Pricing's job — `ValidationResult`), and 15 command DTOs. Every format-validating field delegates to domain value objects (`Quantity`, `CartNote`, `GiftMessage`) — no regex duplicated between serializer and value object.

---

## 5. Permission Summary

**16 classes** (exactly matching this phase's expected list), all reusing Identity's `HasPermissionCode.resolver`: `CanViewCart`, `CanManageCart`, `CanCreateCart`, `CanUpdateCart`, `CanDeleteCart`, `CanManageCartItems`, `CanMergeCart`, `CanLockCart`, `CanConvertCart`, `CanAttachCoupon`, `CanAttachReservation`, `CanAttachPriceSnapshot`, `CanValidateCart`, `CanViewCartAudit`, `CanManageGuestCart`, `CanSearchCart`.

---

## 6. Filter Summary

Pagination (page/page_size, capped at 100), status filter, cart_type filter, ownership filter (`customer_id`), locked filter, abandoned filter, converted filter (normalized to `filter[status]=converted` rather than a redundant second boolean), created/updated date-range filters, ordering. `is_abandoned`/`is_locked` are parsed and available as `CartListParams` fields; wiring them into `AdminListCarts`'s actual query is deferred (the underlying repository's `list_for_admin()` currently accepts only `status`/`cart_type`) — disclosed here rather than silently claimed complete.

---

## 7. OpenAPI Coverage

**23 `@extend_schema` decorators for 23 HTTP methods across 16 view classes — 100% coverage, verified by count.**

---

## 8. URL Structure

`/api/v1/cart/` is the mount point. Zero duplicate route patterns (verified by script). `search` is declared before `<str:code>` so the literal segment resolves correctly ahead of the variable one, matching the same ordering discipline used in every prior module's `urls.py`.

---

## 9. Architecture Validation

| Gate | Status |
|---|---|
| ✓ No ORM usage inside Views | Pass — one docstring match describing what's forbidden, not a real import |
| ✓ No Repository construction outside Composition | Pass |
| ✓ No Aggregate construction inside Views | Pass — grep initially flagged permission class names like `CanCreateCart()` as false positives (substring match on "Cart("); a precise recheck for real `Cart(...)` construction confirmed zero matches |
| ✓ No business logic inside Views | Pass — verified after the Inconsistency 2 fix; zero direct domain-method calls remain in `views.py` |
| ✓ Filters compile | Pass |
| ✓ Serializers compile | Pass |
| ✓ Permissions compile | Pass |
| ✓ URLs contain no duplicates | Pass |
| ✓ Pagination wired | Pass |
| ✓ Response envelope used everywhere | Pass |
| ✓ OpenAPI coverage 100% | Pass — 23/23 |
| ✓ Zero forward dependency on Wallet/Loyalty/Ordering/Fulfillment/Analytics/POS | Pass — re-verified fresh across the entire `apps/cart/` tree including all new Interfaces and the Phase 1/2 additions |

---

## 10. Interfaces Certification

**Mistakes and inconsistencies found this phase, reported honestly, per this explicit instruction:**

1. **Two genuine architectural gaps in Phase 1's original service/port design**, both found only once real endpoint work began, both resolved with the minimum necessary addition rather than a workaround — detailed in Step 1 above.
2. **A near-miss self-caught rule violation**: my own first draft of `LockCartView`/`UnlockCartView`/`CartDetailView.patch()` would have violated this exact phase's own "no business logic / no aggregate construction in views" gates. Caught and fixed before this report, not discovered by an external check afterward.
3. **A drafting mistake within the fix itself**: the first version of the `LockCartView` fix used `__import__("apps.cart.domain.enums", fromlist=["CartLockReason"])` instead of a normal import — the seventh occurrence of this exact pattern across this entire build (previously: Store, three places in Inventory, once in Pricing, once in Cart's own Phase 2). Fixed immediately, and the whole `apps/cart/` tree was swept again afterward to confirm no other instance remained. None did.
4. **No duplicated routes, duplicated serializers, duplicated business logic, or repository leaks were found.**

**The Cart Interfaces layer is complete, internally consistent, and ready for the Testing phase** — with one explicitly-disclosed, intentionally incomplete endpoint (`convert`) that cannot be genuinely completed without a future Ordering module's own Domain/Application work, and one explicitly-disclosed filter gap (`is_abandoned`/`is_locked` parsed but not yet wired into the admin query). Neither is hidden; both are stated here and in the code itself (the `convert` endpoint's own OpenAPI description says so to any API consumer). As with every module in this build, this is verified-correct-by-static-inspection and compile check (1209/1209 repository-wide files), not verified-passing-against-a-live-server.

**Stopping here per the explicit "do not begin Phase 4" instruction.**
