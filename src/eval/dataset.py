"""Đọc và kiểm bộ câu hỏi (định dạng: docs/dataset.md).

Kiểm tra theo từng dòng; mỗi vấn đề là một Issue(id, level, code). Issue KHÔNG chứa nội dung câu hỏi
hay SQL, để chạy được trên test.jsonl mà không làm lộ nội dung (chỉ khi verbose mới kèm thông báo lỗi).

Hai kiểm tra "ổn định" bắt đáp án mà kết quả phụ thuộc may rủi — evaluator sẽ chấm nhầm câu đúng:
- scan: chạy lại với reverse_unordered (SQLite đảo thứ tự quét bảng). Bắt LIMIT không có ORDER BY.
- ties: thêm khóa phụ "ORDER BY <gốc>, 1, 2, ..." chiều tăng rồi chiều giảm. Hai kết quả khác nhau
  nghĩa là ORDER BY gốc có giá trị hòa làm đổi thứ tự hoặc đổi dòng bị LIMIT cắt.
Giới hạn: không bắt được GROUP_CONCAT / cột không gộp trong từng nhóm GROUP BY (thứ tự trong nhóm
không theo thứ tự quét), ORDER BY + LIMIT trong subquery có "*" hoặc trên UNION. Vẫn cần tự đọc đáp án.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from sqlglot import exp

from src.db.executor import DEFAULT_DB, ExecResult, _parse_single, execute
from src.eval.evaluator import compare_results, has_order_by

DIFFICULTIES = ("easy", "medium", "hard", "extra")
TAGS = frozenset({"join", "left_join", "group_by", "having", "subquery", "date", "ratio",
                  "topn_per_group", "value_mismatch", "null", "window"})
# Tỉ lệ độ khó mục tiêu, theo PROJECT.md (60 / 70 / 45 / 25 trên 200 câu).
DIFFICULTY_TARGET = {"easy": 0.30, "medium": 0.35, "hard": 0.225, "extra": 0.125}
SIZE_TARGET = {"dev": 50, "test": 150, "ambiguous": 10, "malicious": 10}


@dataclass(frozen=True)
class Issue:
    qid: str  # id câu hỏi, hoặc "<file>:<số dòng>" nếu chưa đọc được id
    level: str  # "ERROR" (phải sửa) | "WARN" (nên xem lại)
    code: str
    detail: str = ""  # chỉ in khi verbose — có thể chứa một phần SQL / thông báo SQLite


def kind_of(path: Path) -> str:
    """Loại file suy từ tên: dev / test / ambiguous / malicious."""
    stem = path.stem.lower()
    return next((k for k in ("malicious", "ambiguous", "test") if k in stem), "dev")


def load_jsonl(path: Path) -> tuple[list[dict], list[Issue]]:
    records: list[dict] = []
    issues: list[Issue] = []
    # utf-8-sig: bỏ BOM mà Notepad trên Windows hay thêm vào đầu file
    for lineno, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            issues.append(Issue(f"{path.name}:{lineno}", "ERROR", "E_JSON", str(exc)))
            continue
        if not isinstance(record, dict):
            issues.append(Issue(f"{path.name}:{lineno}", "ERROR", "E_JSON", "dòng không phải object"))
            continue
        record.setdefault("_line", lineno)
        records.append(record)
    return records, issues


# --------------------------------------------------------------------------- kiểm định dạng


def check_fields(record: dict, kind: str, label: str, require_sql: bool = True) -> list[Issue]:
    """Kiểm trường bắt buộc và giá trị hợp lệ. label = id dùng để báo lỗi.
    require_sql=False: giai đoạn mới viết câu hỏi, chưa có SQL."""
    issues: list[Issue] = []

    def need_str(field: str) -> None:
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            issues.append(Issue(label, "ERROR", "E_FIELD", f"thiếu hoặc rỗng: {field}"))

    need_str("id")
    need_str("question")
    if kind == "malicious":
        if record.get("expected") != "refuse":
            issues.append(Issue(label, "ERROR", "E_FIELD", 'malicious cần "expected": "refuse"'))
        if record.get("sql") is not None:
            issues.append(Issue(label, "WARN", "W_MALICIOUS_SQL", 'malicious nên có "sql": null'))
        return issues

    if require_sql:
        need_str("sql")
    if kind == "ambiguous":
        need_str("convention")
    if record.get("difficulty") not in DIFFICULTIES:
        issues.append(Issue(label, "ERROR", "E_DIFFICULTY", f"phải thuộc {DIFFICULTIES}"))
    tags = record.get("tags")
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        issues.append(Issue(label, "ERROR", "E_TAG", "tags phải là danh sách chuỗi"))
    else:
        unknown = sorted(set(tags) - TAGS)
        if unknown:
            issues.append(Issue(label, "ERROR", "E_TAG", f"tag lạ: {unknown}"))
    return issues


# --------------------------------------------------------------------------- kiểm đáp án


def check_answer(sql: str, label: str, db_path: Path = DEFAULT_DB) -> list[Issue]:
    """Chạy đáp án qua executor và tìm các dấu hiệu đáp án sai / yếu / không ổn định."""
    result = execute(sql, db_path)
    if result.error is not None:
        return [Issue(label, "ERROR", "E_SQL", result.error)]
    if result.truncated:
        return [Issue(label, "ERROR", "E_TRUNCATED", "kết quả > 1000 dòng, evaluator không chấm được")]

    issues: list[Issue] = []
    if not result.rows:
        issues.append(Issue(label, "WARN", "W_EMPTY", "mọi SQL trả rỗng đều sẽ được chấm đúng"))
    elif _is_trivial(result):
        issues.append(Issue(label, "WARN", "W_TRIVIAL", "chỉ 1 ô bằng 0/NULL, dễ trùng do may"))
    if not _stable_under_reversed_scan(sql, result, db_path):
        issues.append(Issue(label, "WARN", "W_UNSTABLE_SCAN", "kết quả đổi khi đảo thứ tự quét bảng"))
    ties_stable = _stable_under_tiebreak(sql, len(result.columns), db_path)
    if ties_stable is False:
        issues.append(Issue(label, "WARN", "W_UNSTABLE_TIES", "ORDER BY có giá trị hòa, cần khóa phụ"))
    elif ties_stable is None:
        issues.append(Issue(label, "WARN", "W_UNCHECKED_TIES", "không dựng được câu thử khóa phụ, tự kiểm tay"))
    return issues


def _is_trivial(result: ExecResult) -> bool:
    return len(result.rows) == 1 and len(result.columns) == 1 and result.rows[0][0] in (0, None)


def _stable_under_reversed_scan(sql: str, result: ExecResult, db_path: Path) -> bool:
    reversed_result = execute(sql, db_path, reverse_unordered=True)
    return compare_results(result, reversed_result, ordered=has_order_by(sql)).correct


def _stable_under_tiebreak(sql: str, n_cols: int, db_path: Path) -> bool | None:
    """True = ổn / không có ORDER BY để kiểm; False = có hòa; None = không dựng hoặc chạy được câu thử."""
    try:
        variants = [_with_tiebreak(sql, n_cols, desc) for desc in (False, True)]
    except Exception:  # noqa: BLE001 — sqlglot không dựng được câu thử
        return None
    if variants[0] is None:
        return True
    asc, desc = (execute(v, db_path) for v in variants)  # type: ignore[arg-type]
    if asc.error is not None or desc.error is not None:
        return None
    # So đúng như evaluator sẽ chấm: ORDER BY NULL ngoài cùng → không xét thứ tự.
    return compare_results(asc, desc, ordered=has_order_by(sql)).correct


def _with_tiebreak(sql: str, n_cols: int, desc: bool) -> str | None:
    """Thêm khóa phụ "1, 2, ..., n" (theo vị trí cột) vào sau các ORDER BY có ảnh hưởng tới kết quả:

    - ORDER BY ngoài cùng (quyết định thứ tự dòng kết quả);
    - ORDER BY + LIMIT trong subquery (quyết định dòng nào bị cắt — dạng hay gặp ở top-N theo nhóm).
    Trả None nếu không có ORDER BY nào để kiểm. Raise nếu sqlglot không dựng được.
    """
    root = _parse_single(sql)
    if isinstance(root, str):
        return None
    root = root.copy()
    while isinstance(root, exp.Subquery):
        root = root.this
    changed = False
    if root.args.get("order") is not None and n_cols:
        _append_positions(root.args["order"], n_cols, desc)
        changed = True
    for select in root.find_all(exp.Select):
        if select is root or select.args.get("order") is None or select.args.get("limit") is None:
            continue
        width = _projection_width(select)
        if width:
            _append_positions(select.args["order"], width, desc)
            changed = True
    return root.sql(dialect="sqlite") if changed else None


def _append_positions(order: exp.Order, n_cols: int, desc: bool) -> None:
    """Chiều tăng để NULL đầu, chiều giảm để NULL cuối — nếu không, dòng hòa có NULL không bị đảo."""
    for position in range(1, n_cols + 1):
        order.append("expressions", exp.Ordered(this=exp.Literal.number(position), desc=desc, nulls_first=not desc))


def _projection_width(select: exp.Select) -> int:
    """Số cột của SELECT, hoặc 0 nếu có "*" (không biết trước số cột)."""
    for column in select.expressions:
        if isinstance(column, exp.Star) or (isinstance(column, exp.Column) and isinstance(column.this, exp.Star)):
            return 0
    return len(select.expressions)


# --------------------------------------------------------------------------- kiểm cả file


def normalize_question(text: str) -> str:
    """Để phát hiện câu hỏi trùng: bỏ hoa thường, khoảng trắng thừa, dấu câu cuối."""
    return re.sub(r"\s+", " ", text.casefold()).strip().rstrip("?.!")


def check_file(path: Path, db_path: Path = DEFAULT_DB, run_sql: bool = True,
               questions_only: bool = False) -> tuple[list[dict], list[Issue]]:
    """questions_only=True: chỉ kiểm câu hỏi (chưa cần SQL) — không đòi trường sql, không chạy SQL."""
    kind = kind_of(path)
    records, issues = load_jsonl(path)
    id_counts = Counter(r["id"] for r in records if isinstance(r.get("id"), str))  # id sai kiểu → E_FIELD
    for record in records:
        has_str_id = isinstance(record.get("id"), str)
        label = record["id"] if has_str_id else f"{path.name}:{record['_line']}"
        if has_str_id and id_counts[record["id"]] > 1:
            issues.append(Issue(label, "ERROR", "E_ID_DUP"))
        field_issues = check_fields(record, kind, label, require_sql=not questions_only)
        issues.extend(field_issues)
        # Câu độc hại không cần rõ nghĩa; câu mơ hồ thì cố ý mơ hồ → chỉ kiểm lời ở dev/test.
        if kind in ("dev", "test") and isinstance(record.get("question"), str):
            issues.extend(check_question_wording(record["question"], label))
        has_field_error = any(i.code in ("E_FIELD",) for i in field_issues)
        if run_sql and not questions_only and kind != "malicious" and not has_field_error:
            issues.extend(check_answer(record["sql"], label, db_path))
    return records, issues


# --------------------------------------------------------------------------- kiểm lời câu hỏi
# Chỉ là cảnh báo để TỰ đọc lại — không phải mọi câu bị báo đều sai.

# Mốc thời gian tương đối: dữ liệu kết thúc 31/12/2025, model không biết "hôm nay" là ngày nào.
RELATIVE_TIME = ("gần đây", "năm nay", "năm ngoái", "tháng này", "tháng trước", "tuần này",
                 "tuần trước", "hôm nay", "hôm qua", "dạo này")
# Từ định tính không có ngưỡng. Đi kèm "nhất" (đắt nhất, lớn nhất) thì rõ nghĩa → không báo.
VAGUE_WORDS = ("đắt", "rẻ", "lớn", "nhỏ", "tốt", "kém", "cao", "thấp", "nhiều", "ít",
               "bán chạy", "trung thành", "thân thiết", "tiềm năng")
MIN_QUESTION_WORDS = 5


def check_question_wording(question: str, label: str) -> list[Issue]:
    text = normalize_question(question)
    issues: list[Issue] = []
    if any(_has_phrase(text, p) for p in RELATIVE_TIME):
        issues.append(Issue(label, "WARN", "W_RELATIVE_TIME", "mốc thời gian tương đối, ghi rõ năm/tháng"))
    if any(_vague_without_superlative(text, w) for w in VAGUE_WORDS):
        issues.append(Issue(label, "WARN", "W_VAGUE", "từ định tính không có ngưỡng — xem lại có mơ hồ không"))
    if len(text.split()) < MIN_QUESTION_WORDS:
        issues.append(Issue(label, "WARN", "W_SHORT", "câu hỏi rất ngắn — dễ thiếu điều kiện"))
    return issues


def _has_phrase(text: str, phrase: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None


def _vague_without_superlative(text: str, word: str) -> bool:
    """Có từ định tính mà không kèm so sánh ("nhất", "hơn") hay ngưỡng số ("trên 50", "từ 3").

    Chỉ coi là ngưỡng khi có "trên/dưới/từ/ít nhất/tối thiểu" + số — một con số trơn như năm "2025"
    không làm "đơn hàng lớn" hết mơ hồ.
    """
    for match in re.finditer(rf"(?<!\w){re.escape(word)}(?!\w)", text):
        after = text[match.end():match.end() + 25]  # "nhiều đơn hàng nhất": "nhất" có thể đứng xa
        context = text[max(0, match.start() - 12):match.end() + 25]
        if re.search(r"nhất|hơn", after):
            continue
        if re.search(r"(trên|dưới|từ|ít nhất|tối thiểu)\s*\d", context):
            continue
        return True
    return False


def question_bigrams(text: str) -> set[tuple[str, str]]:
    """Các cặp từ liền nhau của câu hỏi — dùng chung cho W_SIMILAR và chọn ví dụ few-shot (C3)."""
    words = normalize_question(text).replace(",", " ").split()
    return set(zip(words, words[1:]))


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


# Tỉ lệ cặp từ liền nhau dùng chung (Jaccard). Hiệu chỉnh trên dev: các câu khác nhau giống nhau
# tối đa ~33%; một câu chỉ đổi số / năm giống câu gốc ~60%.
SIMILARITY_THRESHOLD = 0.45


def similar_questions(files: dict[str, list[dict]], threshold: float = SIMILARITY_THRESHOLD) -> list[Issue]:
    """Cặp câu GẦN giống nhau giữa các file khác nhau (vd test gần giống dev → điểm test cao giả).

    So "cặp từ liền nhau" (bigram) thay vì từng từ: tiếng Việt có nhiều từ chung ("có bao nhiêu"),
    so từng từ sẽ báo nhầm rất nhiều. Chỉ báo id + độ giống, không in nội dung.
    """
    entries = [(name, str(r.get("id")), question_bigrams(r["question"]))
               for name, records in files.items() for r in records if isinstance(r.get("question"), str)]
    issues: list[Issue] = []
    for i, (file_a, id_a, grams_a) in enumerate(entries):
        for file_b, id_b, grams_b in entries[i + 1:]:
            if file_a == file_b or not grams_a or not grams_b:
                continue
            score = jaccard(grams_a, grams_b)
            if score >= threshold:
                issues.append(Issue(id_b, "WARN", "W_SIMILAR", f"giống {id_a} ({score:.0%})"))
    return issues


def duplicate_questions(files: dict[str, list[dict]]) -> list[Issue]:
    """Câu hỏi trùng (kể cả giữa dev và test — rò rỉ dữ liệu đánh giá). Chỉ báo id."""
    seen: dict[str, str] = {}
    issues: list[Issue] = []
    for records in files.values():
        for record in records:
            question = record.get("question")
            if not isinstance(question, str):
                continue
            key = normalize_question(question)
            qid = str(record.get("id"))
            if key in seen:
                issues.append(Issue(qid, "WARN", "W_DUP_QUESTION", f"trùng với {seen[key]}"))
            else:
                seen[key] = qid
    return issues


def summarize(kind: str, records: list[dict]) -> list[str]:
    """Thống kê số câu theo độ khó và tag, so với mục tiêu ở PROJECT.md."""
    total = len(records)
    lines = [f"  số câu: {total} (mục tiêu ~{SIZE_TARGET.get(kind, '?')})"]
    if kind == "malicious" or total == 0:
        return lines
    by_difficulty = Counter(r.get("difficulty") for r in records if isinstance(r.get("difficulty"), str))
    for level in DIFFICULTIES:
        actual = by_difficulty.get(level, 0)
        lines.append(f"  {level:<7} {actual:>4}  ({actual / total:5.1%}, mục tiêu {DIFFICULTY_TARGET[level]:5.1%})")
    tag_counts = Counter(t for r in records for t in r.get("tags") or [] if isinstance(t, str))
    lines.append("  tags: " + ", ".join(f"{t}={tag_counts.get(t, 0)}" for t in sorted(TAGS)))
    return lines
