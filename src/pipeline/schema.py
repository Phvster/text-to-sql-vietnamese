"""Thông tin schema đưa vào prompt.

- C0: DDL (câu CREATE TABLE) của các bảng.
- C1: thêm dòng dữ liệu mẫu và giá trị phân biệt của các cột chữ ít giá trị — giúp model biết DB lưu
  'TP. Hồ Chí Minh' chứ không phải 'Sài Gòn' (lỗi lệch giá trị).

Mọi truy vấn đọc DB ở đây đều đi qua executor (cùng cổng với SQL của model), không mở sqlite3 riêng.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import sqlglot
from sqlglot import exp

from src.db.executor import DEFAULT_DB, execute

MAX_DISTINCT = 50  # cột chữ có ≤ 50 giá trị khác nhau thì liệt kê hết (city 12, brand 47, status 5...)
SAMPLE_ROWS = 3
MAX_CELL_CHARS = 40


@dataclass(frozen=True)
class TableInfo:
    name: str
    ddl: str
    columns: tuple[str, ...]
    text_columns: tuple[str, ...]
    sample_header: tuple[str, ...] = ()
    sample_rows: tuple[tuple, ...] = ()
    distinct_values: dict[str, tuple[str, ...]] = field(default_factory=dict)


def _run(sql: str, db_path: Path) -> list[tuple]:
    result = execute(sql, db_path)
    if result.error is not None:
        raise RuntimeError(f"Không đọc được schema: {result.error}")
    return result.rows


def _columns_from_ddl(ddl: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(mọi cột, các cột kiểu TEXT) — đọc từ câu CREATE TABLE bằng sqlglot (PRAGMA bị executor chặn)."""
    tree = sqlglot.parse_one(ddl, read="sqlite")
    columns, text_columns = [], []
    for col in tree.find_all(exp.ColumnDef):
        columns.append(col.name)
        kind = col.args.get("kind")
        if kind is not None and kind.is_type(exp.DataType.Type.TEXT, exp.DataType.Type.VARCHAR):
            text_columns.append(col.name)
    return tuple(columns), tuple(text_columns)


@lru_cache(maxsize=4)
def load_schema(db_path: Path = DEFAULT_DB) -> tuple[TableInfo, ...]:
    """Đọc schema + dữ liệu mẫu một lần cho mỗi DB (lru_cache), dùng lại cho mọi câu hỏi."""
    tables = []
    for name, ddl in _run("SELECT name, sql FROM sqlite_master WHERE type = 'table' ORDER BY name", db_path):
        columns, text_columns = _columns_from_ddl(ddl)
        sample = execute(f'SELECT * FROM "{name}" LIMIT {SAMPLE_ROWS}', db_path)
        tables.append(TableInfo(
            name=name, ddl=ddl.strip(), columns=columns, text_columns=text_columns,
            sample_header=tuple(sample.columns), sample_rows=tuple(sample.rows),
            distinct_values=_distinct_values(name, text_columns, db_path),
        ))
    return tuple(tables)


def _distinct_values(table: str, text_columns: tuple[str, ...], db_path: Path) -> dict[str, tuple[str, ...]]:
    values: dict[str, tuple[str, ...]] = {}
    for col in text_columns:
        (count,), = _run(f'SELECT COUNT(DISTINCT "{col}") FROM "{table}"', db_path)
        if 0 < count <= MAX_DISTINCT:
            rows = _run(f'SELECT DISTINCT "{col}" FROM "{table}" WHERE "{col}" IS NOT NULL ORDER BY 1', db_path)
            values[col] = tuple(str(r[0]) for r in rows)
    return values


def table_names(schema: tuple[TableInfo, ...]) -> list[str]:
    return [t.name for t in schema]


def select_tables(schema: tuple[TableInfo, ...], names: list[str] | None) -> tuple[TableInfo, ...]:
    """names=None → toàn bộ schema. Giữ thứ tự cố định (theo tên) để prompt ổn định, cache được."""
    if names is None:
        return schema
    wanted = set(names)
    return tuple(t for t in schema if t.name in wanted)


def ddl_text(tables: tuple[TableInfo, ...]) -> str:
    return "\n\n".join(t.ddl + ";" for t in tables)


def overview_text(tables: tuple[TableInfo, ...]) -> str:
    """Dạng gọn: bảng(cột, cột, ...) — dùng cho bước chọn bảng ở C2."""
    return "\n".join(f"{t.name}({', '.join(t.columns)})" for t in tables)


def samples_text(tables: tuple[TableInfo, ...]) -> str:
    """C1: dòng mẫu + giá trị phân biệt của từng bảng."""
    parts = []
    for t in tables:
        lines = [f"-- {t.name}: {SAMPLE_ROWS} dòng mẫu", " | ".join(t.sample_header)]
        lines += [" | ".join(_cell(v) for v in row) for row in t.sample_rows]
        for col, values in t.distinct_values.items():
            lines.append(f"-- {t.name}.{col} chỉ có các giá trị: " + ", ".join(repr(v) for v in values))
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def _cell(value: object) -> str:
    text = "NULL" if value is None else str(value)
    return text if len(text) <= MAX_CELL_CHARS else text[: MAX_CELL_CHARS - 1] + "…"
