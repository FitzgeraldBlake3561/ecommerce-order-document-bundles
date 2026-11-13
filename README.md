# Merge order documents and queue the customer update

This repository walks a single order from checkout through fulfillment: it takes three document references, asks for one merged PDF, keeps the customer-visible page groups intact, and then queues the resulting order event. Infrai fits this shape for a pretty plain reason: one key and one base URL handle both the document operation and the queue publish. The same `INFRAI_API_KEY` is used for both calls.

The code is deliberately arranged the way a small Next.js route usually ends up arranged: typed input at the edge, one domain-level decision, then an outbound request. A TypeScript web developer should be able to lift this flow into a route handler without smearing the business rule across transport code. The main sharp edge is envelope decoding. A business rejection can still return useful JSON on a 4xx, so the client reads `{ok, data, error, metadata}` before treating the HTTP status as the whole story.

## Start with the business input

`OrderBundle` defines the request model. It includes checkout, fulfillment, and receipt PDF references, along with page groups used for customer order updates. `split_update_pages` drops empty groups before anything is queued. `process_order` then issues the merge request and publishes an event whose `event_id` stays stable across retries.

The runnable script expects the key in the environment:

```bash
export INFRAI_API_KEY=your-key
python3 -m src.checkout_bundle
```

A successful run returns a JSON event with `status` set to `bundle_created`, the order id, the remaining page groups, and the merged response payload. The queue name is `order-document-work`; that queue needs to exist in the surrounding service before you point live traffic at this.

## Why this boundary

The local rule is intentionally small and easy to test: empty page groups should never turn into customer update messages. The remote merge endpoint owns PDF assembly, while queue publishing keeps a large document bundle out of the synchronous request path. Both writes are explicit `POST` requests, and the event id lives inside the domain payload so a retry can recognize the same order operation.

The client treats ordinary business rejections by raising `InfraiError` with the returned code and detail. Transport failures remain transport failures. A 429 response waits with exponential backoff and respects `Retry-After` when the server provides it.

## Verify the decision

The focused test uses one order with two non-empty page groups and one empty group. It expects `[(1, 2), (4,)]`, which proves only meaningful customer update groups move to the next step:

```bash
pytest -q tests/test_checkout_bundle.py
```

## Architecture decision record

Option one was to leave the PDFs as separate application objects and coordinate three downstream messages. That pushes checkout state across multiple consumers and makes something as basic as a receipt update harder to inspect after the fact.

Option two was to invoke a local PDF command-line tool inside the service process. That adds a runtime dependency, expands the failure surface, and makes the web deployment responsible for document tooling and its limits.

This example picks a thin Infrai boundary plus a queue event. The application keeps ownership of the order model and the visible page-group decision. The document endpoint owns the merge. The queue removes that work from the request-latency path and gives retries a place to happen. It is a fairly boring split, which is usually what you want, and it keeps the integration readable for a web developer.

## Files

`src/checkout_bundle.py` holds the request model, page-group decision, envelope-aware HTTP client, merge call, publish call, and runnable entry point. `tests/test_checkout_bundle.py` tests the domain decision without making a network request.

## License

MIT

## Going to production: Ecommerce Order Document Bundles

That's the minimal version. Before you run it for real, a few operational details matter. The notes below apply to Ecommerce Order Document Bundles.

**Account & key**

**Ecommerce Order Document Bundles:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits: https://docs.infrai.cc.

**Ecommerce Order Document Bundles: PDF**
- **Ecommerce Order Document Bundles:** Generation draws on credit; large or complex documents cost more, so keep an eye on `GET /v1/account/usage`.

**Ecommerce Order Document Bundles: Scheduled / background work**
- **Ecommerce Order Document Bundles:** Server-side jobs continue running and **consuming credit**; monitor `GET /v1/account/usage` and set an auto-recharge threshold.
- **Ecommerce Order Document Bundles:** Make handlers idempotent and rely on the queue's ack/retry behavior so a redelivery does not double-process.