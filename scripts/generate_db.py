"""Sinh CSDL bán hàng SQLite theo docs/schema.md.

Chạy: python scripts/generate_db.py --seed 42

Thiết kế:
- Một random.Random(seed) duy nhất truyền qua mọi hàm + Faker.seed_instance(seed)
  → cùng seed cho ra cùng DB (tái lập thí nghiệm).
- Tiền là INTEGER VND, unit_price bội 1000 → line_total luôn nguyên, total_amount khớp tuyệt đối.
- Phân phối lệch: Pareto cho khách hàng, Zipf cho sản phẩm, mùa vụ cho ngày đặt hàng.

Script này GHI DB nên dùng sqlite3 trực tiếp; SQL do model sinh vẫn phải đi qua src/db/executor.py.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import math
import random
import sqlite3
import sys
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Sequence, TypeVar

from faker import Faker

T = TypeVar("T")

START_DATE = date(2023, 1, 1)
END_DATE = date(2025, 12, 31)

# --------------------------------------------------------------------------- schema

DDL = """
CREATE TABLE categories (
    category_id INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    parent_id   INTEGER REFERENCES categories(category_id)
);
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    full_name   TEXT NOT NULL,
    email       TEXT NOT NULL,
    phone       TEXT,
    gender      TEXT NOT NULL CHECK (gender IN ('M', 'F')),
    birth_date  TEXT,
    city        TEXT NOT NULL,
    segment     TEXT NOT NULL CHECK (segment IN ('retail', 'wholesale', 'vip')),
    created_at  TEXT NOT NULL
);
CREATE TABLE products (
    product_id     INTEGER PRIMARY KEY,
    name           TEXT NOT NULL,
    category_id    INTEGER NOT NULL REFERENCES categories(category_id),
    brand          TEXT NOT NULL,
    unit_price     INTEGER NOT NULL,
    cost_price     INTEGER NOT NULL,
    stock_quantity INTEGER NOT NULL,
    is_active      INTEGER NOT NULL CHECK (is_active IN (0, 1)),
    created_at     TEXT NOT NULL
);
CREATE TABLE orders (
    order_id       INTEGER PRIMARY KEY,
    customer_id    INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date     TEXT NOT NULL,
    status         TEXT NOT NULL
        CHECK (status IN ('pending', 'shipped', 'delivered', 'cancelled', 'returned')),
    payment_method TEXT NOT NULL
        CHECK (payment_method IN ('cod', 'bank_transfer', 'credit_card', 'e_wallet')),
    shipping_city  TEXT NOT NULL,
    total_amount   INTEGER NOT NULL
);
CREATE TABLE order_items (
    order_item_id INTEGER PRIMARY KEY,
    order_id      INTEGER NOT NULL REFERENCES orders(order_id),
    product_id    INTEGER NOT NULL REFERENCES products(product_id),
    quantity      INTEGER NOT NULL CHECK (quantity >= 1),
    unit_price    INTEGER NOT NULL,
    discount_pct  INTEGER NOT NULL CHECK (discount_pct IN (0, 5, 10, 15, 20)),
    UNIQUE (order_id, product_id)
);
CREATE TABLE reviews (
    review_id   INTEGER PRIMARY KEY,
    product_id  INTEGER NOT NULL REFERENCES products(product_id),
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    order_id    INTEGER NOT NULL REFERENCES orders(order_id),
    rating      INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment     TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_date ON orders(order_date);
CREATE INDEX idx_items_order ON order_items(order_id);
CREATE INDEX idx_items_product ON order_items(product_id);
"""

# --------------------------------------------------------------------------- dữ liệu tham chiếu

# Tên tỉnh/thành chính thức (cố tình khác cách nói thường ngày: "Sài Gòn", "Huế", "Vũng Tàu").
CITY_WEIGHTS: dict[str, float] = {
    "TP. Hồ Chí Minh": 30, "Hà Nội": 25, "Đà Nẵng": 8, "Hải Phòng": 6, "Cần Thơ": 5,
    "Bình Dương": 5, "Đồng Nai": 5, "Thừa Thiên Huế": 4, "Bà Rịa - Vũng Tàu": 4,
    "Khánh Hòa": 3, "Nghệ An": 3, "Quảng Ninh": 2,
}

# danh mục gốc -> {danh mục con: (tên gốc sản phẩm, thương hiệu, (giá min, giá max) VND)}
CATALOG: dict[str, dict[str, tuple[list[str], list[str], tuple[int, int]]]] = {
    "Điện tử": {
        "Điện thoại": (["Điện thoại"], ["Samsung", "Apple", "Xiaomi", "Oppo", "Vivo"], (2_500_000, 35_000_000)),
        "Laptop": (["Laptop"], ["Dell", "Asus", "Lenovo", "HP", "Acer"], (9_000_000, 45_000_000)),
        "Phụ kiện điện tử": (["Tai nghe", "Sạc dự phòng", "Ốp lưng", "Chuột không dây", "Cáp sạc"],
                             ["Anker", "Baseus", "Logitech", "Sony", "Ugreen"], (80_000, 3_000_000)),
    },
    "Thời trang": {
        "Thời trang nam": (["Áo sơ mi nam", "Quần jean nam", "Áo thun nam", "Áo khoác nam"],
                           ["Owen", "Routine", "Việt Tiến", "Coolmate"], (150_000, 1_200_000)),
        "Thời trang nữ": (["Đầm nữ", "Áo kiểu nữ", "Chân váy", "Quần tây nữ"],
                          ["Ivy Moda", "Elise", "Canifa", "NEM"], (200_000, 1_800_000)),
        "Giày dép": (["Giày thể thao", "Sandal", "Giày tây", "Dép"],
                     ["Biti's", "Nike", "Adidas", "Ananas"], (150_000, 3_500_000)),
    },
    "Nhà cửa": {
        "Đồ gia dụng": (["Nồi cơm điện", "Máy xay sinh tố", "Ấm siêu tốc", "Nồi chiên không dầu"],
                        ["Sunhouse", "Philips", "Kangaroo", "Lock&Lock"], (250_000, 4_000_000)),
        "Nội thất": (["Bàn làm việc", "Ghế xoay", "Kệ sách", "Tủ quần áo"],
                     ["Hòa Phát", "IKEA", "Xuân Hòa"], (500_000, 8_000_000)),
    },
    "Sức khỏe & Làm đẹp": {
        "Mỹ phẩm": (["Kem chống nắng", "Son môi", "Sữa rửa mặt", "Serum"],
                    ["La Roche-Posay", "Innisfree", "Cocoon", "L'Oréal"], (90_000, 1_200_000)),
        "Chăm sóc cá nhân": (["Dầu gội", "Sữa tắm", "Kem đánh răng", "Bàn chải điện"],
                             ["Dove", "P/S", "Clear", "Oral-B"], (40_000, 1_500_000)),
    },
    "Thực phẩm": {
        "Đồ uống": (["Cà phê", "Trà xanh", "Nước ép"], ["Trung Nguyên", "Highlands", "Phúc Long"], (30_000, 400_000)),
        "Thực phẩm khô": (["Hạt điều", "Mì gói", "Bánh quy"], ["Vinamit", "Acecook", "Kinh Đô"], (20_000, 500_000)),
    },
}

MIDDLE_NAMES_M = ["Văn", "Đức", "Minh", "Quang", "Hữu", "Thành", "Công", "Hoàng"]
MIDDLE_NAMES_F = ["Thị", "Ngọc", "Thu", "Thanh", "Kim", "Mai", "Phương", "Bảo"]

STATUS_WEIGHTS = {"delivered": 80, "cancelled": 9, "returned": 4, "shipped": 4, "pending": 3}
RECENT_STATUS_WEIGHTS = {"pending": 40, "shipped": 50, "cancelled": 10}  # đơn trong 14 ngày cuối
PAYMENT_WEIGHTS = {"cod": 40, "e_wallet": 25, "bank_transfer": 20, "credit_card": 15}
DISCOUNT_WEIGHTS = {0: 60, 5: 15, 10: 12, 15: 8, 20: 5}
SALE_DAY_DISCOUNT_WEIGHTS = {0: 20, 5: 15, 10: 25, 15: 20, 20: 20}
RATING_WEIGHTS = {1: 5, 2: 5, 3: 12, 4: 28, 5: 50}  # hình chữ J
PRICE_FACTOR_BY_YEAR = {2023: 0.90, 2024: 0.95, 2025: 1.00}  # giá lúc mua thấp hơn giá hiện tại

COMMENTS: dict[int, list[str]] = {
    1: ["Hàng lỗi, rất thất vọng", "Không giống mô tả", "Giao sai sản phẩm"],
    2: ["Chất lượng kém", "Đóng gói cẩu thả", "Không đáng tiền"],
    3: ["Tạm được", "Bình thường, giao hơi chậm", "Dùng ổn"],
    4: ["Sản phẩm tốt", "Giao hàng nhanh", "Đáng tiền"],
    5: ["Rất hài lòng", "Tuyệt vời, sẽ mua lại", "Chất lượng xuất sắc"],
}

# --------------------------------------------------------------------------- tiện ích ngẫu nhiên


def weighted_choice(rng: random.Random, weights: dict[T, float]) -> T:
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def poisson(rng: random.Random, lam: float) -> int:
    """Thuật toán Knuth (stdlib không có Poisson; tránh phụ thuộc numpy)."""
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def geometric(rng: random.Random, p: float) -> int:
    """Số lần thử tới khi thành công, ≥ 1. p lớn → đa số giá trị 1–2."""
    k = 1
    while rng.random() > p:
        k += 1
    return k


def random_date(rng: random.Random, start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def round_1000(x: float) -> int:
    return max(1000, int(round(x / 1000)) * 1000)


def ascii_slug(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return "".join(ch for ch in text.lower() if ch.isalnum())


class CumulativeSampler:
    """Chọn ngẫu nhiên theo trọng số nhiều lần. Tính cum_weights một lần thay vì mỗi lần gọi
    rng.choices(weights=...) (O(n) mỗi lần) → nhanh hơn nhiều khi sinh 20.000 đơn."""

    def __init__(self, items: Sequence[T], weights: Sequence[float]) -> None:
        pairs = [(it, w) for it, w in zip(items, weights) if w > 0]
        self.items = [it for it, _ in pairs]
        self.cum = list(itertools.accumulate(w for _, w in pairs))

    def sample(self, rng: random.Random) -> T:
        return rng.choices(self.items, cum_weights=self.cum)[0]


# --------------------------------------------------------------------------- sinh từng bảng


@dataclass
class Customer:
    customer_id: int
    full_name: str
    email: str
    phone: str | None
    gender: str
    birth_date: str | None
    city: str
    segment: str
    created_at: str = ""
    weight: float = 0.0  # trọng số mua hàng (không lưu vào DB)


@dataclass
class Product:
    product_id: int
    name: str
    category_id: int
    brand: str
    unit_price: int
    cost_price: int
    stock_quantity: int
    is_active: int
    created_at: str
    weight: float = 0.0  # độ phổ biến (không lưu vào DB)


def gen_categories() -> tuple[list[tuple], dict[str, int]]:
    """Trả về (rows, {tên danh mục con: category_id})."""
    rows: list[tuple] = []
    leaf_ids: dict[str, int] = {}
    next_id = 1
    for root, children in CATALOG.items():
        root_id = next_id
        rows.append((root_id, root, None))
        next_id += 1
        for child in children:
            rows.append((next_id, child, root_id))
            leaf_ids[child] = next_id
            next_id += 1
    return rows, leaf_ids


def gen_customers(rng: random.Random, fake: Faker, n: int) -> list[Customer]:
    city_sampler = CumulativeSampler(list(CITY_WEIGHTS), list(CITY_WEIGHTS.values()))
    customers: list[Customer] = []
    for cid in range(1, n + 1):
        gender = "M" if rng.random() < 0.48 else "F"
        # Faker vi_VN.middle_name() không phân biệt giới tính ("Văn" có thể ra cho nữ) → tự chọn
        if gender == "M":
            middle, first = rng.choice(MIDDLE_NAMES_M), fake.first_name_male()
        else:
            middle, first = rng.choice(MIDDLE_NAMES_F), fake.first_name_female()
        full_name = f"{fake.last_name()} {middle} {first}"
        email = f"{ascii_slug(full_name)}{cid}@{rng.choice(['gmail.com', 'yahoo.com', 'outlook.com'])}"
        phone = None if rng.random() < 0.05 else rng.choice(["09", "03", "08", "07"]) + f"{rng.randint(0, 99_999_999):08d}"
        birth = None if rng.random() < 0.08 else random_date(rng, date(1960, 1, 1), date(2005, 12, 31)).isoformat()
        customers.append(Customer(cid, full_name, email, phone, gender, birth, city_sampler.sample(rng), "retail"))
    assign_customer_weights(rng, customers)
    return customers


def assign_customer_weights(rng: random.Random, customers: list[Customer]) -> None:
    """Pareto: w ~ Pareto(α=1.16) → ~20% khách tạo ~80% doanh thu.
    Cắt trần 60 để không có 1 khách chiếm hàng nghìn đơn. ~7% khách w=0 (chưa từng mua).
    Phân khúc suy ra từ hành vi: top 6% trọng số → 'vip'; 8% ngẫu nhiên → 'wholesale'."""
    for c in customers:
        c.weight = 0.0 if rng.random() < 0.07 else min(rng.paretovariate(1.16), 60.0)
    for c in customers:
        if c.weight > 0 and rng.random() < 0.08:
            c.segment = "wholesale"
    buyers = sorted((c for c in customers if c.weight > 0 and c.segment == "retail"),
                    key=lambda c: (-c.weight, c.customer_id))
    for c in buyers[: int(len(customers) * 0.06)]:
        c.segment = "vip"


def gen_products(rng: random.Random, n: int, leaf_ids: dict[str, int]) -> list[Product]:
    leaves = [(leaf, spec) for children in CATALOG.values() for leaf, spec in children.items()]
    seen: set[str] = set()  # chỉ để kiểm tra trùng tên, không duyệt
    products: list[Product] = []
    for pid in range(1, n + 1):
        leaf, (bases, brands, (lo, hi)) = leaves[(pid - 1) % len(leaves)]  # chia đều cho các danh mục con
        while True:
            brand = rng.choice(brands)
            name = f"{rng.choice(bases)} {brand} {rng.choice('ABCDEFGHKMNPSTX')}{rng.randint(10, 99)}"
            if name not in seen:
                seen.add(name)
                break
        # giá phân phối log-uniform: nhiều hàng rẻ, ít hàng đắt
        price = round_1000(math.exp(rng.uniform(math.log(lo), math.log(hi))))
        cost = round_1000(price * rng.uniform(0.55, 0.8))
        products.append(Product(pid, name, leaf_ids[leaf], brand, price, cost,
                                rng.randint(0, 500), 0 if rng.random() < 0.08 else 1,
                                random_date(rng, date(2022, 1, 1), date(2022, 12, 31)).isoformat() + " 09:00:00"))
    assign_product_weights(rng, products)
    return products


def assign_product_weights(rng: random.Random, products: list[Product]) -> None:
    """Zipf: xáo thứ hạng, w = 1/rank. ~7.5% sản phẩm w=0 → không bao giờ bán.
    Sản phẩm không bán được coi là mới ra mắt gần đây (created_at 2025)."""
    ranks = list(range(1, len(products) + 1))
    rng.shuffle(ranks)
    n_unsold = max(1, round(len(products) * 0.075))
    for p, rank in zip(products, ranks):
        p.weight = 1.0 / rank
    for p in rng.sample(products, n_unsold):
        p.weight = 0.0
        p.created_at = random_date(rng, date(2025, 1, 1), END_DATE).isoformat() + " 09:00:00"


def day_weight(d: date) -> float:
    """Tăng trưởng theo năm × mùa vụ (Tết, cuối năm) × ngày sale (11/11, 12/12)."""
    growth = 1.0 + 0.3 * (d.year - START_DATE.year)
    season = {1: 1.3, 2: 1.2, 11: 1.4, 12: 1.3}.get(d.month, 1.0)
    sale = 4.0 if (d.month, d.day) in {(11, 11), (12, 12)} else 1.0
    return growth * season * sale


def gen_order_datetimes(rng: random.Random, n: int) -> list[datetime]:
    days = [START_DATE + timedelta(days=i) for i in range((END_DATE - START_DATE).days + 1)]
    day_sampler = CumulativeSampler(days, [day_weight(d) for d in days])
    hour_weights = [1, 1, 1, 1, 1, 1, 2, 3, 5, 6, 7, 8, 8, 7, 6, 6, 7, 8, 10, 12, 13, 12, 8, 4]
    hour_sampler = CumulativeSampler(list(range(24)), hour_weights)
    stamps = [
        datetime.combine(day_sampler.sample(rng), datetime.min.time()).replace(
            hour=hour_sampler.sample(rng), minute=rng.randint(0, 59), second=rng.randint(0, 59))
        for _ in range(n)
    ]
    return sorted(stamps)  # order_id tăng theo thời gian


def gen_orders_and_items(rng: random.Random, customers: list[Customer], products: list[Product],
                         n: int) -> tuple[list[tuple], list[tuple]]:
    cust_sampler = CumulativeSampler(customers, [c.weight for c in customers])
    prod_sampler = CumulativeSampler(products, [p.weight for p in products])
    max_items = min(8, len(prod_sampler.items))
    orders: list[tuple] = []
    items: list[tuple] = []
    for oid, ts in enumerate(gen_order_datetimes(rng, n), start=1):
        cust = cust_sampler.sample(rng)
        chosen = pick_distinct(rng, prod_sampler, min(1 + poisson(rng, 2.0), max_items))
        total = 0
        for prod in chosen:
            qty, price, disc = make_line(rng, cust, prod, ts)
            items.append((len(items) + 1, oid, prod.product_id, qty, price, disc))
            total += line_total(qty, price, disc)
        city = cust.city if rng.random() < 0.9 else rng.choice(list(CITY_WEIGHTS))
        orders.append((oid, cust.customer_id, ts.strftime("%Y-%m-%d %H:%M:%S"), pick_status(rng, ts),
                       weighted_choice(rng, PAYMENT_WEIGHTS), city, total))
    return orders, items


def pick_distinct(rng: random.Random, sampler: CumulativeSampler, k: int) -> list:
    chosen: list = []
    while len(chosen) < k:
        item = sampler.sample(rng)
        if item not in chosen:
            chosen.append(item)
    return chosen


def make_line(rng: random.Random, cust: Customer, prod: Product, ts: datetime) -> tuple[int, int, int]:
    qty = min(geometric(rng, 0.6), 10)
    if cust.segment == "wholesale":
        qty *= rng.randint(3, 8)
    price = round_1000(prod.unit_price * PRICE_FACTOR_BY_YEAR[ts.year])
    sale_day = (ts.month, ts.day) in {(11, 11), (12, 12)}
    disc = weighted_choice(rng, SALE_DAY_DISCOUNT_WEIGHTS if sale_day else DISCOUNT_WEIGHTS)
    return qty, price, disc


def line_total(qty: int, price: int, disc: int) -> int:
    value = qty * price * (100 - disc)
    if value % 100:  # không xảy ra vì price bội 1000; kiểm tra để bắt lỗi sớm
        raise ValueError(f"line_total không nguyên: {qty}, {price}, {disc}")
    return value // 100


def pick_status(rng: random.Random, ts: datetime) -> str:
    recent = (END_DATE - ts.date()).days < 14
    return weighted_choice(rng, RECENT_STATUS_WEIGHTS if recent else STATUS_WEIGHTS)


def assign_signup_dates(rng: random.Random, customers: list[Customer], orders: list[tuple]) -> None:
    """Ngày đăng ký phải trước đơn đầu tiên. Khách chưa mua: ngày ngẫu nhiên."""
    first_order: dict[int, str] = {}
    for _, cid, odate, *_ in orders:  # orders đã sắp theo thời gian
        first_order.setdefault(cid, odate)
    for c in customers:
        if c.customer_id in first_order:
            first = datetime.strptime(first_order[c.customer_id], "%Y-%m-%d %H:%M:%S")
            signup = first - timedelta(days=rng.randint(0, 120), hours=rng.randint(1, 23))
        else:
            signup = datetime.combine(random_date(rng, date(2022, 1, 1), END_DATE), datetime.min.time())
        c.created_at = signup.strftime("%Y-%m-%d %H:%M:%S")


def gen_reviews(rng: random.Random, orders: list[tuple], items: list[tuple]) -> list[tuple]:
    """Chỉ đơn delivered; mỗi dòng hàng có 25% được review; rating hình chữ J."""
    delivered = {o[0]: (o[1], o[2]) for o in orders if o[3] == "delivered"}
    reviews: list[tuple] = []
    for _, oid, pid, *_ in items:
        if oid not in delivered or rng.random() >= 0.25:
            continue
        cid, odate = delivered[oid]
        rating = weighted_choice(rng, RATING_WEIGHTS)
        comment = None if rng.random() < 0.3 else rng.choice(COMMENTS[rating])
        created = datetime.strptime(odate, "%Y-%m-%d %H:%M:%S") + timedelta(days=rng.randint(3, 30))
        reviews.append((len(reviews) + 1, pid, cid, oid, rating, comment, created.strftime("%Y-%m-%d %H:%M:%S")))
    return reviews


# --------------------------------------------------------------------------- ghi DB + kiểm tra


def insert_all(conn: sqlite3.Connection, tables: dict[str, list[tuple]]) -> None:
    with conn:  # một transaction: nhanh và không để DB dở dang nếu lỗi
        for table, rows in tables.items():
            if rows:
                placeholders = ", ".join("?" * len(rows[0]))
                conn.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)


def validate(conn: sqlite3.Connection) -> dict[str, float]:
    """Kiểm tra bất biến của DB; raise ValueError nếu sai. Trả về thống kê tóm tắt."""
    def scalar(sql: str) -> float:
        return conn.execute(sql).fetchone()[0]

    checks = {
        "total_amount lệch tổng order_items": """
            SELECT COUNT(*) FROM orders o
            WHERE o.total_amount != (SELECT COALESCE(SUM(quantity * unit_price * (100 - discount_pct) / 100), 0)
                                     FROM order_items i WHERE i.order_id = o.order_id)""",
        "đơn không có dòng hàng": "SELECT COUNT(*) FROM orders WHERE order_id NOT IN (SELECT order_id FROM order_items)",
        "review không thuộc đơn delivered": """
            SELECT COUNT(*) FROM reviews r JOIN orders o USING (order_id) WHERE o.status != 'delivered'""",
        "đơn trước ngày đăng ký": """
            SELECT COUNT(*) FROM orders o JOIN customers c USING (customer_id) WHERE o.order_date < c.created_at""",
    }
    errors = [name for name, sql in checks.items() if scalar(sql) != 0]
    if conn.execute("PRAGMA foreign_key_check").fetchall():
        errors.append("vi phạm khóa ngoại")

    stats = {
        "customers": scalar("SELECT COUNT(*) FROM customers"),
        "products": scalar("SELECT COUNT(*) FROM products"),
        "orders": scalar("SELECT COUNT(*) FROM orders"),
        "order_items": scalar("SELECT COUNT(*) FROM order_items"),
        "reviews": scalar("SELECT COUNT(*) FROM reviews"),
        "unsold_products": scalar("SELECT COUNT(*) FROM products WHERE product_id NOT IN (SELECT product_id FROM order_items)"),
        "customers_no_order": scalar("SELECT COUNT(*) FROM customers WHERE customer_id NOT IN (SELECT customer_id FROM orders)"),
        "top20_revenue_share": top_customer_share(conn, 0.2),
    }
    if stats["unsold_products"] == 0:
        errors.append("không có sản phẩm nào chưa bán")
    if stats["customers_no_order"] == 0:
        errors.append("không có khách nào chưa mua")
    if errors:
        raise ValueError("DB không hợp lệ: " + "; ".join(errors))
    return stats


def top_customer_share(conn: sqlite3.Connection, frac: float) -> float:
    """Tỉ lệ doanh thu (đơn không bị hủy) của top `frac` khách hàng (tính trên tổng số khách)."""
    spend = [r[0] for r in conn.execute(
        "SELECT SUM(total_amount) AS s FROM orders WHERE status != 'cancelled' GROUP BY customer_id ORDER BY s DESC")]
    n_customers = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    total = sum(spend)
    return sum(spend[: int(n_customers * frac)]) / total if total else 0.0


def db_fingerprint(path: Path) -> str:
    """Hash nội dung (không phải file bytes) để kiểm tra tái lập."""
    with sqlite3.connect(path) as conn:
        dump = "\n".join(conn.iterdump())
    return hashlib.sha256(dump.encode()).hexdigest()


# --------------------------------------------------------------------------- main


def build_database(out: Path, seed: int, n_customers: int = 2000, n_products: int = 200,
                   n_orders: int = 20000) -> dict[str, float]:
    rng = random.Random(seed)
    fake = Faker("vi_VN")
    fake.seed_instance(seed)

    category_rows, leaf_ids = gen_categories()
    customers = gen_customers(rng, fake, n_customers)
    products = gen_products(rng, n_products, leaf_ids)
    orders, items = gen_orders_and_items(rng, customers, products, n_orders)
    assign_signup_dates(rng, customers, orders)
    reviews = gen_reviews(rng, orders, items)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    conn = sqlite3.connect(out)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(DDL)
        insert_all(conn, {
            "categories": category_rows,
            "customers": [(c.customer_id, c.full_name, c.email, c.phone, c.gender, c.birth_date,
                           c.city, c.segment, c.created_at) for c in customers],
            "products": [(p.product_id, p.name, p.category_id, p.brand, p.unit_price, p.cost_price,
                          p.stock_quantity, p.is_active, p.created_at) for p in products],
            "orders": orders,
            "order_items": items,
            "reviews": reviews,
        })
        return validate(conn)
    finally:
        conn.close()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sinh data/sales.db theo docs/schema.md")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=Path("data/sales.db"))
    parser.add_argument("--customers", type=int, default=2000)
    parser.add_argument("--products", type=int, default=200)
    parser.add_argument("--orders", type=int, default=20000)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # console Windows mặc định cp1252
    args = parse_args(argv)
    stats = build_database(args.out, args.seed, args.customers, args.products, args.orders)
    print(f"Đã tạo {args.out} (seed={args.seed})")
    for key, value in stats.items():
        print(f"  {key:<22} {value:.3f}" if isinstance(value, float) else f"  {key:<22} {value}")
    print(f"  fingerprint            {db_fingerprint(args.out)[:16]}")


if __name__ == "__main__":
    main()
