"""Thống kê so sánh cấu hình — Python thuần (không cần numpy/scipy), tất định nhờ seed.

Đơn vị lấy mẫu là CÂU HỎI, không phải từng lần chạy: các lần lặp của cùng một câu không độc lập (cùng độ khó),
nên gộp mỗi câu thành một con số (tỉ lệ đúng qua các lần lặp) rồi mới bootstrap.

Hai cấu hình chạy trên CÙNG bộ câu → dữ liệu ghép cặp:
- McNemar: chỉ nhìn các câu hai bên bất đồng (b = A sai B đúng, c = A đúng B sai).
- Bootstrap ghép cặp: lấy mẫu lại câu hỏi, tính chênh lệch trên cùng các câu đó.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Iterable

N_BOOTSTRAP = 10_000
SEED = 0


def per_question(records: Iterable[dict]) -> dict[str, float]:
    """id → tỉ lệ đúng qua các lần lặp (1 lần lặp → 0.0 hoặc 1.0)."""
    hits: dict[str, list[bool]] = defaultdict(list)
    for r in records:
        hits[r["id"]].append(bool(r["correct"]))
    return {qid: sum(v) / len(v) for qid, v in hits.items()}


def majority(records: Iterable[dict]) -> dict[str, bool]:
    """id → đúng theo đa số lần lặp (≥ một nửa). Dùng cho McNemar, vốn cần mỗi câu một kết quả đúng/sai.
    Lưu ý: số lần lặp chẵn mà hòa (1/2) thì tính là ĐÚNG — kế hoạch dùng 3 lần lặp (lẻ) nên không có hòa."""
    return {qid: rate >= 0.5 for qid, rate in per_question(records).items()}


def bootstrap_ci(values: list[float], n: int = N_BOOTSTRAP, seed: int = SEED,
                 alpha: float = 0.05) -> tuple[float, float, float]:
    """(trung bình, cận dưới, cận trên) — khoảng tin cậy phân vị: lấy mẫu lại có hoàn lại n lần."""
    if not values:
        raise ValueError("Không có giá trị nào để bootstrap.")
    rng = random.Random(seed)
    size = len(values)
    means = sorted(sum(rng.choices(values, k=size)) / size for _ in range(n))
    lo = means[int(alpha / 2 * n)]              # n=10.000 → phần tử thứ 250 và 9.750 (đánh số từ 1)
    hi = means[int((1 - alpha / 2) * n) - 1]
    return sum(values) / size, lo, hi


def paired_bootstrap_diff(a: dict[str, float], b: dict[str, float], n: int = N_BOOTSTRAP,
                          seed: int = SEED, alpha: float = 0.05) -> tuple[float, float, float]:
    """Chênh lệch B − A với CI, lấy mẫu lại CÂU HỎI (giữ cặp). Hai bên phải cùng tập câu hỏi."""
    if a.keys() != b.keys():
        raise ValueError(f"Hai lượt chạy khác tập câu hỏi ({len(a.keys() ^ b.keys())} câu lệch) — không ghép cặp được.")
    ids = sorted(a)
    return bootstrap_ci([b[i] - a[i] for i in ids], n=n, seed=seed, alpha=alpha)


def discordant(a: dict[str, bool], b: dict[str, bool]) -> tuple[int, int]:
    """(b, c) của McNemar: số câu A sai mà B đúng, số câu A đúng mà B sai."""
    if a.keys() != b.keys():
        raise ValueError("Hai lượt chạy khác tập câu hỏi — không ghép cặp được.")
    return (sum(not a[i] and b[i] for i in a), sum(a[i] and not b[i] for i in a))


def mcnemar_exact(b: int, c: int) -> float:
    """p hai phía của McNemar chính xác: nếu hai cấu hình như nhau, mỗi câu bất đồng nghiêng về bên nào
    cũng 50/50 → số câu nghiêng về một bên ~ Binomial(b + c, 0.5)."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def holm(pvalues: list[float]) -> list[float]:
    """Hiệu chỉnh Holm–Bonferroni cho nhiều so sánh cùng lúc. Trả p đã hiệu chỉnh theo đúng thứ tự đầu vào."""
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[i]))  # giữ đơn điệu: p nhỏ hơn không vượt p sau
        adjusted[i] = running
    return adjusted
