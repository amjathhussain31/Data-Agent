# data/setup_db.py
import sqlite3
import random
from datetime import datetime, timedelta

DB_PATH = "data/sample.db"

REGIONS = ["North", "South", "East", "West", "Central"]
SEGMENTS = ["Consumer", "Corporate", "Home Office"]
CATEGORIES = ["Electronics", "Furniture", "Office Supplies", "Clothing", "Food"]
RETURN_REASONS = ["Defective", "Wrong item", "Changed mind", "Damaged in transit", "Not as described"]

PRODUCTS = [
    ("Laptop Pro 15", "Electronics", 1299.99),
    ("Wireless Mouse", "Electronics", 29.99),
    ("Standing Desk", "Furniture", 449.99),
    ("Office Chair", "Furniture", 299.99),
    ("Stapler Set", "Office Supplies", 12.99),
    ("Notebook Pack", "Office Supplies", 8.99),
    ("Polo Shirt", "Clothing", 34.99),
    ("Winter Jacket", "Clothing", 89.99),
    ("Coffee Beans 1kg", "Food", 18.99),
    ("Protein Bar Box", "Food", 24.99),
    ("USB-C Hub", "Electronics", 49.99),
    ("Monitor 27in", "Electronics", 349.99),
    ("Bookshelf", "Furniture", 199.99),
    ("Pen Set", "Office Supplies", 6.99),
    ("Sneakers", "Clothing", 69.99),
]

def random_date(start_days_ago=730, end_days_ago=0):
    start = datetime.now() - timedelta(days=start_days_ago)
    end = datetime.now() - timedelta(days=end_days_ago)
    delta = end - start
    random_seconds = random.randint(0, int(delta.total_seconds()))
    return (start + timedelta(seconds=random_seconds)).strftime("%Y-%m-%d")

def setup():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.executescript("""
        DROP TABLE IF EXISTS returns;
        DROP TABLE IF EXISTS orders;
        DROP TABLE IF EXISTS products;
        DROP TABLE IF EXISTS customers;

        CREATE TABLE customers (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            region      TEXT NOT NULL,
            segment     TEXT NOT NULL,
            joined_date TEXT NOT NULL
        );

        CREATE TABLE products (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            category    TEXT NOT NULL,
            price       REAL NOT NULL,
            stock       INTEGER NOT NULL DEFAULT 100
        );

        CREATE TABLE orders (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            product_id  INTEGER NOT NULL,
            quantity    INTEGER NOT NULL,
            total       REAL NOT NULL,
            order_date  TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(id),
            FOREIGN KEY (product_id)  REFERENCES products(id)
        );

        CREATE TABLE returns (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id    INTEGER NOT NULL,
            reason      TEXT NOT NULL,
            return_date TEXT NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(id)
        );
    """)

    # Seed customers — 100 rows
    first_names = ["Alice", "Priya", "Ravi", "Sara", "James", "Mei", "Carlos", "Fatima", "Tom", "Aisha"]
    last_names = ["Kumar", "Patel", "Singh", "Chen", "Smith", "Ali", "Johnson", "Lee", "Brown", "Das"]
    for i in range(100):
        name = f"{random.choice(first_names)} {random.choice(last_names)}"
        cur.execute(
            "INSERT INTO customers (name, region, segment, joined_date) VALUES (?,?,?,?)",
            (name, random.choice(REGIONS), random.choice(SEGMENTS), random_date(1095, 365))
        )

    # Seed products — 15 rows
    for name, cat, price in PRODUCTS:
        cur.execute(
            "INSERT INTO products (name, category, price, stock) VALUES (?,?,?,?)",
            (name, cat, price, random.randint(5, 200))
        )

    # Seed orders — 500 rows
    order_ids = []
    for _ in range(500):
        cust_id = random.randint(1, 100)
        prod_id = random.randint(1, 15)
        qty = random.randint(1, 5)
        price = PRODUCTS[prod_id - 1][2]
        total = round(qty * price, 2)
        date = random_date(730, 0)
        cur.execute(
            "INSERT INTO orders (customer_id, product_id, quantity, total, order_date) VALUES (?,?,?,?,?)",
            (cust_id, prod_id, qty, total, date)
        )
        order_ids.append(cur.lastrowid)

    # Seed returns — ~15% of orders
    for order_id in random.sample(order_ids, k=75):
        cur.execute(
            "INSERT INTO returns (order_id, reason, return_date) VALUES (?,?,?)",
            (order_id, random.choice(RETURN_REASONS), random_date(60, 0))
        )

    conn.commit()
    conn.close()
    print("Database created successfully.")
    print(f"  Location : {DB_PATH}")

def verify():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for table in ["customers", "products", "orders", "returns"]:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        print(f"  {table:<12} {count} rows")
    conn.close()

if __name__ == "__main__":
    setup()
    print("\nRow counts:")
    verify()