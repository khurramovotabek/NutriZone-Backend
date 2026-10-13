"""
Fake implementation of Reviews' one Application-layer Port.
"""
from __future__ import annotations


class FakeReviewRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, review_id):
        return self.by_id.get(review_id)

    def list_for_product(self, product_id, status, page, page_size):
        results = [r for r in self.by_id.values() if r.product_id == product_id]
        if status:
            results = [r for r in results if r.status.value == status]
        return results[(page - 1) * page_size : page * page_size], len(results)

    def list_for_customer(self, customer_id, page, page_size):
        results = [r for r in self.by_id.values() if r.customer_id == customer_id]
        return results[(page - 1) * page_size : page * page_size], len(results)

    def save(self, review):
        self.by_id[review.id] = review
        return review

    def list_for_admin(self, status, page, page_size):
        results = list(self.by_id.values())
        if status:
            results = [r for r in results if r.status.value == status]
        return results[(page - 1) * page_size : page * page_size], len(results)
