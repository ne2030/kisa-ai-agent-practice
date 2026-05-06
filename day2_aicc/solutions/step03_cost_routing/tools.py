"""Mock tools for the Day 2 AICC/e-commerce agent.

Every tool returns a dictionary so the graph can keep a simple tool trace.
No real commerce system is touched.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .mock_data import CUSTOMERS, ORDERS, POLICY_DOCS, POISONED_POLICY_DOC, SHIPMENTS, TODAY


def _ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, **data}


def _err(message: str) -> dict[str, Any]:
    return {"ok": False, "error": message}


def get_order(order_id: str) -> dict[str, Any]:
    order = ORDERS.get(order_id)
    if not order:
        return _err(f"unknown order_id: {order_id}")
    return _ok({"order": dict(order)})


def get_customer(customer_id: str) -> dict[str, Any]:
    customer = CUSTOMERS.get(customer_id)
    if not customer:
        return _err(f"unknown customer_id: {customer_id}")
    return _ok({"customer": dict(customer)})


def get_shipment(order_id: str) -> dict[str, Any]:
    shipment = SHIPMENTS.get(order_id)
    if not shipment:
        return _err(f"unknown shipment for order_id: {order_id}")
    return _ok({"shipment": dict(shipment)})


def retrieve_policy(intent: str, *, include_poisoned: bool = False, max_docs: int = 2) -> dict[str, Any]:
    docs = [dict(doc) for doc in POLICY_DOCS.get(intent, POLICY_DOCS["unknown"])[:max_docs]]
    if include_poisoned:
        # The poisoned doc is appended after normal retrieval so strict budgets still
        # demonstrate that "fewer docs" does not eliminate indirect injection risk.
        docs.append(dict(POISONED_POLICY_DOC))
    return _ok({"policy_docs": docs})


def update_shipping_address(order_id: str, new_address: str) -> dict[str, Any]:
    order = ORDERS.get(order_id)
    if not order:
        return _err(f"unknown order_id: {order_id}")
    # Real systems would commit a transaction. The lab keeps a mock event only.
    return _ok(
        {
            "event": "shipping_address_updated",
            "order_id": order_id,
            "old_address": order["shipping_address"],
            "new_address": new_address,
        }
    )


def cancel_order(order_id: str) -> dict[str, Any]:
    order = ORDERS.get(order_id)
    if not order:
        return _err(f"unknown order_id: {order_id}")
    return _ok({"event": "order_cancelled", "order_id": order_id, "refund_krw": order["total_krw"]})


def create_return_request(order_id: str, reason: str) -> dict[str, Any]:
    order = ORDERS.get(order_id)
    if not order:
        return _err(f"unknown order_id: {order_id}")
    return _ok({"event": "return_request_created", "order_id": order_id, "reason": reason})


def issue_coupon(customer_id: str, amount_krw: int, reason: str) -> dict[str, Any]:
    customer = CUSTOMERS.get(customer_id)
    if not customer:
        return _err(f"unknown customer_id: {customer_id}")
    return _ok(
        {
            "event": "coupon_issued",
            "customer_id": customer_id,
            "amount_krw": amount_krw,
            "reason": reason,
        }
    )


def create_support_ticket(customer_id: str, order_id: str, reason: str) -> dict[str, Any]:
    ts = datetime.combine(TODAY, datetime.min.time()).isoformat()
    return _ok(
        {
            "event": "support_ticket_created",
            "ticket_id": f"TCK-{customer_id[-3:]}-{order_id[-4:]}",
            "customer_id": customer_id,
            "order_id": order_id,
            "reason": reason,
            "created_at": ts,
        }
    )


TOOL_REGISTRY = {
    "update_shipping_address": update_shipping_address,
    "cancel_order": cancel_order,
    "create_return_request": create_return_request,
    "issue_coupon": issue_coupon,
    "create_support_ticket": create_support_ticket,
}
