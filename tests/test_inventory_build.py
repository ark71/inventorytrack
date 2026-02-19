def test_inventory_total_calculation():
    item_price = 9.99
    tax = 0.70
    shipping = 5.37
    handling = 3.50
    donation = 0.11
    fees = 0.00

    total = round(
        item_price + tax + shipping + handling + donation + fees,
        2
    )

    assert total == 19.67

