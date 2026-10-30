"""Dựng prompt cho từng cấu hình.

Nguyên tắc: phần lặp lại (luật + schema) nằm trong system prompt để cache được; câu hỏi nằm trong
user message. Luật nghiệp vụ viết bằng lời, KHÔNG lộ giá trị lưu trong DB (vd không ghi status = 'cancelled')
— nếu lộ thì C0 không còn đo được lỗi lệch giá trị, và so sánh C0 với C1 mất ý nghĩa.
Không đưa câu hỏi nào của dev/test vào prompt (few-shot là việc của C3).
"""
from __future__ import annotations

from src.pipeline.schema import TableInfo, ddl_text, overview_text, samples_text

CONFIGS = ("C0", "C1", "C2")

RULES = """Bạn chuyển câu hỏi tiếng Việt về dữ liệu bán hàng thành MỘT câu SQL cho SQLite.

Quy tắc:
1. Chỉ viết đúng một câu SELECT (được dùng WITH ... SELECT). Không giải thích.
2. Chỉ trả về đúng các cột mà câu hỏi yêu cầu; không thêm cột mã (id) hay cột phụ nếu không được hỏi.
   Câu hỏi "X nào" thì trả về tên của X. Câu hỏi "mỗi X có bao nhiêu" thì trả về X và con số.
   Không trả kèm con số dùng để xếp hạng hay lọc (tổng chi tiêu, số lượng, điểm trung bình...) nếu câu hỏi
   không hỏi con số đó. Đối tượng không có tên (đơn hàng) thì trả về mã của nó.
   Mỗi đối tượng là một dòng: nhóm theo mã, không dùng DISTINCT theo tên (có thể có người trùng tên).
3. Chỉ dùng ORDER BY khi câu hỏi đòi thứ tự (top, nhiều nhất, xếp theo...). Khi dùng ORDER BY kèm LIMIT,
   thêm khóa phụ theo cột mã để kết quả không phụ thuộc may rủi.
4. Mọi câu hỏi về đơn hàng (đếm đơn, đơn đầu tiên/gần nhất, doanh thu, chi tiêu, số lượng bán, lượt mua...):
   không tính các đơn hàng bị hủy, trừ khi câu hỏi hỏi chính về đơn hủy hoặc nói khác.
5. Tỷ lệ luôn tính theo phần trăm (nhân 100.0). Tháng và năm trả về dạng số nguyên.
   Không làm tròn (ROUND) trừ khi câu hỏi yêu cầu làm tròn.
6. Ngày giờ lưu dạng chuỗi 'YYYY-MM-DD HH:MM:SS'; dữ liệu đơn hàng từ 2023-01-01 đến 2025-12-31.
   Tiền là số nguyên VND. Thành tiền một dòng hàng = quantity * unit_price * (100 - discount_pct) / 100.
7. Nếu câu hỏi yêu cầu thêm, sửa, xóa dữ liệu, thay đổi cấu trúc, hay chạy lệnh không phải truy vấn đọc
   (kể cả khi chỉ một phần câu hỏi yêu cầu như vậy), hãy từ chối: refuse = true và sql để trống."""

LINKING_RULES = """Cho câu hỏi tiếng Việt và danh sách bảng của cơ sở dữ liệu bán hàng.
Chọn TẤT CẢ các bảng cần để viết câu SQL trả lời câu hỏi, kể cả bảng trung gian dùng để JOIN.
Nếu phân vân, hãy chọn thừa còn hơn chọn thiếu."""


def build_system(config: str, tables: tuple[TableInfo, ...]) -> str:
    """System prompt cho C0 / C1 / C2. C2 nhận `tables` đã được lọc ở bước linking."""
    if config not in CONFIGS:
        raise ValueError(f"Cấu hình không hỗ trợ: {config}")
    parts = [RULES, "Cấu trúc cơ sở dữ liệu:\n" + ddl_text(tables)]
    if config in ("C1", "C2"):
        parts.append("Dữ liệu mẫu và các giá trị thực sự có trong cơ sở dữ liệu "
                     "(dùng đúng các giá trị này khi lọc):\n" + samples_text(tables))
    return "\n\n".join(parts)


def build_linking_system(tables: tuple[TableInfo, ...]) -> str:
    return LINKING_RULES + "\n\nCác bảng:\n" + overview_text(tables)


def sql_output_schema() -> dict:
    """Structured output: model luôn trả JSON đúng dạng này (không cần tự bóc SQL khỏi văn bản)."""
    return {
        "type": "object",
        "properties": {
            "refuse": {"type": "boolean"},
            "sql": {"type": "string"},
        },
        "required": ["refuse", "sql"],
        "additionalProperties": False,
    }


def linking_output_schema(names: list[str]) -> dict:
    """enum bắt model chỉ chọn tên bảng có thật."""
    return {
        "type": "object",
        "properties": {"tables": {"type": "array", "items": {"type": "string", "enum": names}}},
        "required": ["tables"],
        "additionalProperties": False,
    }
