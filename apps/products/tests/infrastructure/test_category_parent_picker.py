"""Kategoriya → "Ota kategoriya": the picker shows tree paths and never offers the category itself or one of its
descendants (that would cut a whole branch out of the tree); a forged POST is rejected the same way."""
from __future__ import annotations

import uuid

import pytest

from apps.products.infrastructure import models as orm
from apps.products.infrastructure.admin import CategoryAdminForm, _category_subtree_ids

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _cat(name, parent=None):
    c = orm.Category.objects.create(id=uuid.uuid4(), parent=parent, is_active=True, sort_order=1)
    orm.CategoryTranslation.objects.create(id=uuid.uuid4(), category=c, locale_code="uz", name=name, slug=f"c-{uuid.uuid4().hex[:8]}")
    return c


@pytest.fixture
def tree():
    root = _cat("Sport")
    mid = _cat("Proteinlar", root)
    leaf = _cat("Whey", mid)
    other = _cat("Vitaminlar")
    return root, mid, leaf, other


def _choice_ids(form):
    return {str(getattr(v, "value", v)) for v, _ in form.fields["parent"].choices if v}


def test_subtree_contains_root_and_all_descendants(tree):
    root, mid, leaf, other = tree
    assert _category_subtree_ids(root.pk) >= {root.pk, mid.pk, leaf.pk}
    assert other.pk not in _category_subtree_ids(root.pk)


def test_picker_excludes_self_and_descendants_and_shows_paths(tree):
    root, mid, leaf, other = tree
    form = CategoryAdminForm(instance=mid)
    ids = _choice_ids(form)
    assert str(mid.pk) not in ids and str(leaf.pk) not in ids
    assert str(root.pk) in ids and str(other.pk) in ids
    labels = dict((str(getattr(v, "value", v)), l) for v, l in form.fields["parent"].choices if v)
    assert labels[str(root.pk)] == "Sport"


@pytest.mark.parametrize("target", ["self", "descendant"])
def test_cycle_is_rejected(tree, target):
    root, mid, leaf, other = tree
    parent = mid if target == "self" else leaf
    form = CategoryAdminForm(instance=mid, data={"parent": str(parent.pk), "sort_order": 1, "is_active": "on"})
    assert not form.is_valid()
    assert "parent" in form.errors


def test_moving_under_another_branch_is_allowed(tree):
    root, mid, leaf, other = tree
    form = CategoryAdminForm(instance=mid, data={"parent": str(other.pk), "sort_order": 1, "is_active": "on"})
    assert form.is_valid(), form.errors
