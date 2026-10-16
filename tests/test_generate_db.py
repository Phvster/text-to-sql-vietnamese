"""Test cho scripts/generate_db.py, chạy trên DB nhỏ để nhanh."""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

# scripts/ không phải package → nạp module theo đường dẫn
_spec = importlib.util.spec_from_file_location(
    "generate_db", Path(__file__).resolve().parents[1] / "scripts" / "generate_db.py")
gen = importlib.util.module_from_spec(_spec)
sys.modules["generate_db"] = gen  # @dataclass cần tra module trong sys.modules
_spec.loader.exec_module(gen)

SMALL = dict(n_customers=300, n_products=60, n_orders=2000)


@pytest.fixture(scope="module")
def small_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("db") / "sales.db"
    gen.build_database(path, seed=7, **SMALL)
    return path


def query(path: Path, sql: str) -> list[tuple]:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        return conn.execute(sql).fetchall()


def test_same_seed_same_content(tmp_path: Path) -> None:
    a, b = tmp_path / "a.db", tmp_path / "b.db"
    gen.build_database(a, seed=1, **SMALL)
    gen.build_database(b, seed=1, **SMALL)
    assert gen.db_fingerprint(a) == gen.db_fingerprint(b)


def test_different_seed_different_content(tmp_path: Path) -> None:
    a, b = tmp_path / "a.db", tmp_path / "b.db"
    gen.build_database(a, seed=1, **SMALL)
    gen.build_database(b, seed=2, **SMALL)
    assert gen.db_fingerprint(a) != gen.db_fingerprint(b)


def test_total_amount_matches_items(small_db: Path) -> None:
    rows = query(small_db, """
        SELECT o.order_id FROM orders o
        JOIN order_items i USING (order_id)
        GROUP BY o.order_id
        HAVING o.total_amount != SUM(i.quantity * i.unit_price * (100 - i.discount_pct) / 100)""")
    assert rows == []


def test_no_orphan_foreign_keys(small_db: Path) -> None:
    assert query(small_db, "PRAGMA foreign_key_check") == []


def test_has_unsold_products_and_idle_customers(small_db: Path) -> None:
    unsold = query(small_db, "SELECT COUNT(*) FROM products p "
                             "WHERE NOT EXISTS (SELECT 1 FROM order_items i WHERE i.product_id = p.product_id)")
    idle = query(small_db, "SELECT COUNT(*) FROM customers c "
                           "WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = c.customer_id)")
    assert unsold[0][0] > 0
    assert idle[0][0] > 0


def test_customer_revenue_is_skewed(small_db: Path) -> None:
    with sqlite3.connect(small_db) as conn:
        share = gen.top_customer_share(conn, 0.2)
    assert share >= 0.6  # phân phối đều sẽ cho ~0.2


def test_value_mismatch_codes_present(small_db: Path) -> None:
    cities = {r[0] for r in query(small_db, "SELECT DISTINCT city FROM customers")}
    statuses = {r[0] for r in query(small_db, "SELECT DISTINCT status FROM orders")}
    assert "TP. Hồ Chí Minh" in cities
    assert "Sài Gòn" not in cities
    assert "delivered" in statuses


def test_line_total_rejects_fractional() -> None:
    assert gen.line_total(3, 15_000, 5) == 42_750
    with pytest.raises(ValueError):
        gen.line_total(1, 1_550, 5)
