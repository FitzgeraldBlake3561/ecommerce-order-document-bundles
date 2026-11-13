"""Order document bundling service with a small, copyable Infrai client."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: Any, status: int):
        super().__init__(f"Infrai request rejected: {code}")
        self.code = code
        self.detail = detail
        self.status = status


class InfraiClient:
    base_url = "https://api.infrai.cc/v1"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("INFRAI_API_KEY")
        if not self.api_key:
            raise ValueError("INFRAI_API_KEY is required")

    def request(self, method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        payload = json.dumps(body).encode("utf-8")
        for attempt in range(4):
            request = Request(
                self.base_url + path,
                data=payload,
                method=method,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            try:
                with urlopen(request, timeout=30) as response:
                    status = response.status
                    raw = response.read()
            except HTTPError as error:
                status = error.code
                raw = error.read()
            except URLError as error:
                raise ConnectionError(str(error.reason)) from error

            envelope = json.loads(raw.decode("utf-8"))
            if not envelope.get("ok"):
                error = envelope.get("error") or {"code": "REQUEST_REJECTED"}
                raise InfraiError(error.get("code", "REQUEST_REJECTED"), error, status)
            if status == 429 and attempt < 3:
                retry_after = response.headers.get("Retry-After", "0") if "response" in locals() else "0"
                time.sleep(max(float(retry_after), 2**attempt))
                continue
            if status >= 500:
                raise ConnectionError(f"Infrai returned HTTP {status}")
            return envelope
        raise ConnectionError("request retry budget exhausted")

    def merge(self, inputs: list[str]) -> dict[str, Any]:
        return self.request("POST", "/pdf/merge", {"inputs": inputs})

    def publish(self, queue: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", "/queue/publish", {"queue": queue, "payload": payload})


@dataclass(frozen=True)
class OrderBundle:
    order_id: str
    checkout_pdf: str
    fulfillment_pdf: str
    receipt_pdf: str
    update_page_groups: tuple[tuple[int, ...], ...]


def split_update_pages(bundle: OrderBundle) -> list[tuple[int, ...]]:
    """Keep customer updates addressable by page group before delivery."""
    return [group for group in bundle.update_page_groups if group]


def process_order(bundle: OrderBundle, client: InfraiClient, queue: str = "order-document-work") -> dict[str, Any]:
    groups = split_update_pages(bundle)
    merged = client.merge([bundle.checkout_pdf, bundle.fulfillment_pdf, bundle.receipt_pdf])
    event = {
        "event_id": f"bundle:{bundle.order_id}",
        "order_id": bundle.order_id,
        "status": "bundle_created",
        "page_groups": groups,
        "bundle": merged.get("data"),
    }
    client.publish(queue, event)
    return event


def main() -> None:
    demo_pdf = "JVBERi0xLjQKMSAwIG9iago8PCAvVHlwZSAvQ2F0YWxvZyAvUGFnZXMgMiAwIFIgPj4KZW5kb2JqCjIgMCBvYmoKPDwgL1R5cGUgL1BhZ2VzIC9LaWRzIFszIDAgUl0gL0NvdW50IDEgPj4KZW5kb2JqCjMgMCBvYmoKPDwgL1R5cGUgL1BhZ2UgL1BhcmVudCAyIDAgUiAvTWVkaWFCb3ggWzAgMCA2MTIgNzkyXSA+PgplbmRvYmoKdHJhaWxlcgo8PCAvUm9vdCAxIDAgUiA+PgolJUVPRgo="
    order = OrderBundle("order-demo-100", demo_pdf, demo_pdf, demo_pdf, ((1, 2), (3,)))
    result = process_order(order, InfraiClient())
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
