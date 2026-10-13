"""
Phase 16: closes the exact root cause Phase 15's investigation proved --
the "customer" role (seeded by 0002_seed_customer_role.py) was never
granted any Wallet/Loyalty permission after those domains were built,
so every real customer received 403 PERMISSION_DENIED on their own
wallet/membership despite the RBAC and ownership architecture itself
being correct (proven by the existing, passing
test_wallet_idor_regression.py's own test_customer_can_view_own_wallet
case, which only succeeds when this exact grant is present).

Grants exactly 4 read-only, self-service permission codes -- confirmed
directly from the real permission class source, not guessed:

- wallet.wallet.view_own      (ViewOwnWallet -- WalletDetailView,
                                WalletBalanceView,
                                CustomerWalletHistoryView)
- wallet.ledger.view          (ViewLedger -- WalletTransactionsView)
- loyalty.membership.view_own (ViewOwnMembership -- MembershipDetailView,
                                CustomerMembershipView)
- loyalty.tier.view_history   (ViewTierHistory -- TierHistoryView)

Deliberately does NOT grant any mutation/admin permission (credit,
debit, transfer, reserve/release/capture, corrections, cashback/reward
management, suspend/reinstate/cancel, tier override, ViewAny/
statistics) -- minimum required privilege, per this phase's own
explicit rule.
"""
from __future__ import annotations

import uuid

from django.db import migrations

CUSTOMER_ROLE_CODE = "customer"

NEW_CUSTOMER_PERMISSION_CODES = [
    "wallet.wallet.view_own",
    "wallet.ledger.view",
    "loyalty.membership.view_own",
    "loyalty.tier.view_history",
]


def grant_wallet_loyalty_read_own(apps, schema_editor):
    Role = apps.get_model("identity", "Role")
    Permission = apps.get_model("identity", "Permission")
    RolePermission = apps.get_model("identity", "RolePermission")

    role = Role.objects.filter(code=CUSTOMER_ROLE_CODE).first()
    if role is None:
        return  # Fails open on missing seed data, matching 0002_seed_customer_role.py's own established convention -- a missing role is an ops/migration problem, not something this migration should create.

    for code in NEW_CUSTOMER_PERMISSION_CODES:
        permission, _ = Permission.objects.get_or_create(code=code, defaults={"id": uuid.uuid4(), "description": code})
        RolePermission.objects.get_or_create(role=role, permission=permission, defaults={"id": uuid.uuid4()})


def revoke_wallet_loyalty_read_own(apps, schema_editor):
    Role = apps.get_model("identity", "Role")
    Permission = apps.get_model("identity", "Permission")
    RolePermission = apps.get_model("identity", "RolePermission")

    role = Role.objects.filter(code=CUSTOMER_ROLE_CODE).first()
    if role is None:
        return

    RolePermission.objects.filter(role=role, permission__code__in=NEW_CUSTOMER_PERMISSION_CODES).delete()
    # Deliberately does NOT delete the Permission rows themselves -- they
    # may be referenced by other roles (e.g. staff roles) that already
    # existed independently of this migration; only the grant to the
    # customer role introduced here is removed.


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0009_telegramauthsession"),
    ]

    operations = [
        migrations.RunPython(grant_wallet_loyalty_read_own, revoke_wallet_loyalty_read_own),
    ]
