from src.checkout_bundle import OrderBundle, split_update_pages


def test_empty_page_groups_are_not_queued_for_customer_updates():
    order = OrderBundle("order-7", "checkout.pdf", "fulfillment.pdf", "receipt.pdf", ((1, 2), (), (4,)))
    assert split_update_pages(order) == [(1, 2), (4,)]
