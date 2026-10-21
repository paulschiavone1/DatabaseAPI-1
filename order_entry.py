"""order_entry.py - Interactive order entry backed by Supabase.

Flow: show customers/products -> collect + validate input -> confirm ->
insert order -> re-query the saved order to verify it.
"""
from datetime import date
from decimal import Decimal, InvalidOperation

from Database import get_client, get_customers, get_products

# --- Table / column names (match sql/01_create_tables.sql in the class repo) ---
CUSTOMERS, CUST_ID, CUST_NAME = "customers", "customer_id", "name"
PRODUCTS, PROD_ID, PROD_NAME, PROD_PRICE = "products", "product_id", "product_name", "price"
ORDERS, ORDER_ID = "orders", "order_id"


def money(value) -> Decimal:
    """Convert a database number to a Decimal rounded to cents."""
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except InvalidOperation:
        return Decimal("0.00")


# ---------- Database reads ----------
def fetch_customers(client):
    return get_customers()  # from database.py (ordered by customer_id)


def fetch_products(client):
    return get_products()  # from database.py (ordered by product_id)


# ---------- Display ----------
def print_customers(customers):
    print("\nCUSTOMERS")
    print(f"{'ID':<6}{'Name'}")
    print("-" * 40)
    for c in customers:
        print(f"{c[CUST_ID]:<6}{c[CUST_NAME]}")


def print_products(products):
    print("\nPRODUCTS")
    print(f"{'ID':<6}{'Product':<30}{'Price':>10}")
    print("-" * 46)
    for p in products:
        print(f"{p[PROD_ID]:<6}{p[PROD_NAME]:<30}{money(p[PROD_PRICE]):>10}")


# ---------- Input + validation ----------
def prompt_for_record(label, records, id_col):
    """Ask until the user enters an integer ID that exists in `records`."""
    by_id = {r[id_col]: r for r in records}
    while True:
        raw = input(f"\nEnter {label} ID: ").strip()
        try:
            record_id = int(raw)
        except ValueError:
            print(f"'{raw}' is not a valid number. Please enter a whole-number {label} ID.")
            continue
        if record_id not in by_id:
            print(f"No {label} found with ID {record_id}. Choose an ID from the table above.")
            continue
        return by_id[record_id]


def prompt_for_quantity():
    """Ask until the user enters a positive whole number."""
    while True:
        raw = input("\nEnter quantity: ").strip()
        try:
            qty = int(raw)  # rejects "1.5" and "hello"
        except ValueError:
            print(f"'{raw}' is not a whole number. Enter a positive whole number such as 3.")
            continue
        if qty <= 0:
            print("Quantity must be greater than zero.")
            continue
        return qty


def prompt_yes_no(message):
    """Return True for Y/y, False for N/n; reprompt otherwise."""
    while True:
        answer = input(message).strip().lower()
        if answer in ("y", "n"):
            return answer == "y"
        print("Please enter Y or N.")


def show_summary(customer, product, qty):
    price = money(product[PROD_PRICE])
    print("\nORDER SUMMARY")
    print("-" * 30)
    print(f"Customer:   {customer[CUST_NAME]}")
    print(f"Product:    {product[PROD_NAME]}")
    print(f"Quantity:   {qty}")
    print(f"Unit price: ${price}")
    print(f"Total:      ${price * qty}")


# ---------- Insert + verify ----------
def insert_order(client, customer, product, qty):
    """Insert the order; return the generated order ID or None on failure."""
    row = {
        "customer_id": customer[CUST_ID],
        "product_id": product[PROD_ID],
        "quantity": qty,
        "order_date": date.today().isoformat(),
        "unit_price": product[PROD_PRICE],  # price as returned by the database
    }
    try:
        response = client.table(ORDERS).insert(row).execute()
        if not response.data:
            print("The database did not confirm the insertion. The order was NOT saved.")
            return None
        return response.data[0][ORDER_ID]
    except Exception as exc:  # do not print exc details; they could include request info
        print(f"Could not save the order ({type(exc).__name__}). Nothing was saved.")
        return None


def fetch_saved_order(client, order_id):
    """Query the database again for the specific order; return a display row or None."""
    try:
        rows = (client.table(ORDERS)
                .select("*, customers(name), products(product_name)")
                .eq(ORDER_ID, order_id).execute().data)
        if not rows:
            return None
        o = rows[0]
        return {
            "order_id": o[ORDER_ID],
            "customer": (o.get("customers") or {}).get("name", "(unknown)"),
            "product": (o.get("products") or {}).get("product_name", "(unknown)"),
            "quantity": o["quantity"],
            "unit_price": money(o["unit_price"]),  # stored price, not current price
            "order_date": o["order_date"],
        }
    except Exception as exc:
        print(f"Verification query failed ({type(exc).__name__}).")
        return None


def print_saved_order(o):
    total = o["unit_price"] * o["quantity"]
    print("\nSAVED ORDER (retrieved from database)")
    header = f"{'Order ID':<10}{'Customer':<20}{'Product':<24}{'Qty':>5}{'Unit Price':>12}{'Total':>12}  {'Order Date'}"
    print(header)
    print("-" * len(header))
    print(f"{o['order_id']:<10}{o['customer']:<20}{o['product']:<24}{o['quantity']:>5}"
          f"{o['unit_price']:>12}{total:>12.2f}  {o['order_date']}")


# ---------- One order ----------
def enter_order(client, customers, products):
    # All values are local to this call, so nothing carries over between orders.
    customer = prompt_for_record("customer", customers, CUST_ID)
    product = prompt_for_record("product", products, PROD_ID)
    qty = prompt_for_quantity()

    show_summary(customer, product, qty)
    if not prompt_yes_no("\nConfirm this purchase? (Y/N): "):
        print("Order cancelled. Nothing was saved.")
        return

    order_id = insert_order(client, customer, product, qty)
    if order_id is None:
        return
    print(f"\nSuccess! Order {order_id} was saved.")

    saved = fetch_saved_order(client, order_id)
    if saved is None:
        print("Verification could not be completed. The order was not re-inserted.")
    else:
        print_saved_order(saved)


def main():
    try:
        client = get_client()  # config/credentials handled by config.py
        customers = fetch_customers(client)
        products = fetch_products(client)
    except ValueError as exc:  # config.py messages never include the key
        print(exc)
        return
    except Exception as exc:
        print(f"Could not load data from Supabase ({type(exc).__name__}). Check your .env settings (SUPABASE_URL, SUPABASE_SECRET_KEY).")
        return

    while True:
        print_customers(customers)
        print_products(products)
        enter_order(client, customers, products)
        if not prompt_yes_no("\nEnter another order? (Y/N): "):
            print("Goodbye!")
            break


if __name__ == "__main__":
    main()