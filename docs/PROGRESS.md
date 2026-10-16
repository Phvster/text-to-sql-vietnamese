# Nhật ký tiến độ
## Trạng thái hiện tại
Target: T1 (hạ tầng) — xong cả 4 phần: schema, generate_db.py, executor, evaluator (executor và evaluator đã qua reviewer). Chưa commit.

## Phiên gần nhất (2026-10-16)
### Đã làm xong
- `src/eval/evaluator.py`: `evaluate(gold_sql, pred_sql) -> EvalOutcome(correct, reason)`; `compare_results` thuần (không cần DB); `has_order_by`.
- `tests/test_evaluator.py`: 74 test. `pytest -q`: 222 passed.
- Reviewer tìm 2 lỗi nghiêm trọng (ghép cột treo theo hàm mũ: 11 cột mất 27s; trần 1000 cách ghép làm câu đúng bị chấm sai) + `ORDER BY` bị bỏ qua khi đáp án có comment sau `;` + `ORDER BY NULL`. Đã sửa hết, có test hồi quy.
- Đã trả lời 6 câu hỏi về executor (2026-10-07); cần đọc lại câu 3 (`max_rows + 1`) và câu 6 (test hệ nhiều lớp).

### Đang vướng / làm dở
- **Chưa commit gì** từ sau commit khởi tạo `213ea56`.
- Danh sách test executor và evaluator do Claude đề xuất → tôi cần đọc lại để chắc khớp ý.
- Chưa trả lời 5 câu hỏi kiểm tra hiểu bài về evaluator.
- Chưa làm bài tập SQL: đếm số đơn của mỗi khách, khách chưa mua vẫn hiện 0 (`COUNT(*)` vs `COUNT(o.order_id)`).
- Timeout executor còn vượt được trong 1 trường hợp cố tình — chưa quyết định có làm tiến trình con hay không.
- Chưa có `requirements.txt`.

### Việc đầu tiên khi mở lại
1. `pytest -q` (phải 222 passed) rồi commit toàn bộ T1.
2. Trả lời 5 câu hỏi về evaluator (đọc `src/eval/evaluator.py` trước).
3. Tạo `requirements.txt`, rồi bắt đầu T2 (bộ câu hỏi) theo quy ước dataset bên dưới.

## Quyết định đã chốt
### DB
- Schema 6 bảng ở docs/schema.md. Tiền là INTEGER VND (unit_price bội 1000) → total_amount khớp tuyệt đối, không lỗi float.
- Mã phân loại lưu tiếng Anh (status/segment/payment_method), tên tỉnh chính thức ("TP. Hồ Chí Minh") → cố ý lệch cách nói để đo value mismatch.
- Không có cột line_total; doanh thu dòng = quantity * unit_price * (100 - discount_pct) / 100.
- scripts/generate_db.py ghi DB bằng sqlite3 trực tiếp (ngoại lệ hợp lệ: không phải SQL do model sinh).
- Phân phối lệch: Pareto α=1.16 (trần 60) cho khách, Zipf 1/rank cho sản phẩm, 7.5% sản phẩm không bán, ~7% khách không mua.
- Output Faker phụ thuộc phiên bản → cần pin faker==40.40.0 khi tạo requirements.txt.
- DB seed 42: 2000 khách, 200 sp, 20000 đơn, 60050 items, 11747 reviews; top 20% khách = 77% doanh thu; fingerprint 71e2b04efd852b4c.
### Executor (src/db/executor.py)
- `execute(sql) -> ExecResult(rows, columns, truncated, error)`, không bao giờ raise.
- 5 lớp: (1) sqlglot parse, đúng 1 câu; (2) whitelist gốc cây SELECT/UNION; (3) mode=ro + authorizer; (4) timeout 5s bằng progress handler; (5) tối đa 1000 dòng.
- Giới hạn thêm sau review: SQL ≤ 10.000 ký tự, mỗi giá trị ≤ 100 KB, mẫu LIKE ≤ 1000, tổng kết quả ≤ 5 MB, thông báo lỗi ≤ 500 ký tự.
- conftest.py ở gốc repo để pytest import được `src`.
### Evaluator (src/eval/evaluator.py)
- Bỏ qua tên cột; **cột khác thứ tự vẫn chấm đúng** (user chọn) — số cột phải bằng nhau, thừa cột là sai.
- So **đa tập** (Counter) khi đáp án không có ORDER BY ngoài cùng → quên DISTINCT là sai. Có ORDER BY → so đúng thứ tự.
- Số thực làm tròn **4 chữ số** (user chọn). NULL = NULL. NaN = NaN. Chuỗi so nguyên văn ("hà nội" ≠ "Hà Nội").
- `reason`: match | pred_error | gold_error | pred_truncated | gold_truncated | column_count | row_count | mismatch | mapping_limit.
- Ghép cột: có thứ tự → so đa tập vector cột (chính xác, không tìm kiếm); không thứ tự → quay lui có cắt nhánh
  (chữ ký cột + chiếu dòng), trần 2000 bước → `mapping_limit` (đếm riêng, không lẫn vào mismatch).
- `has_order_by` dùng chung `_parse_single` với executor; `ORDER BY NULL`/`'x'` không tính, `ORDER BY 1` có tính.
### Quy ước viết dataset (T2) — rút ra từ evaluator
- SQL đáp án có ORDER BY phải có khóa phụ phá hòa (vd `ORDER BY doanh_thu DESC, customer_id`), kể cả khi có LIMIT.
- Tránh đáp án rỗng (mọi SQL trả rỗng đều được chấm đúng) và đáp án > 1000 dòng (`gold_truncated`).
- Nêu rõ trong câu hỏi khi cần làm tròn; đáp án ROUND(x, 2) mà model không làm tròn → sai.
## Hạn chế đã biết (đưa vào README ở T6)
- Evaluator: làm tròn có biên (0.12345 vs 0.123449 có thể lệch); số rất lớn (> 1e12) dạng float nhạy với sai số;
  int > 2^53 khác float cùng giá trị; hai SQL khác nghĩa trùng kết quả vẫn được chấm đúng (giới hạn chung của EA).
- Timeout chỉ ngắt giữa các lệnh máy ảo SQLite: câu SQL cố tình nhồi ~150 hàm chuỗi nặng chạy ~13s thay vì 5s. Chặn tuyệt đối cần chạy trong tiến trình con.
- Truy vấn sắp xếp dữ liệu lớn có thể ghi file tạm vào %TEMP% (tới ~1.4 GB) cho tới khi timeout; tự xóa khi đóng kết nối.
## Ghi chú cho các bước sau (từ reviewer)
- Pipeline (T3): phải tự bóc khối ```sql ... ``` và ký tự BOM/NBSP khỏi output LLM trước khi gọi execute().
- Không chạy generate_db.py song song với đánh giá (DB bị khóa → execute trả lỗi).
## Việc tiếp theo
- Tạo requirements.txt (pin phiên bản, đặc biệt faker==40.40.0).
- T2: bộ câu hỏi 50 dev / 150 test + bộ mơ hồ + bộ độc hại (SQL đáp án do tôi tự viết và kiểm).
## Log
- 2026-10-02: tạo repo.
- 2026-10-05: docs/schema.md, scripts/generate_db.py, tests/test_generate_db.py (8 test pass).
- 2026-10-06: src/db/executor.py + tests/test_executor.py; reviewer tìm 3 lỗi nghiêm trọng (raise, bộ nhớ, timeout hàm chuỗi), đã sửa/giảm thiểu; 148 test pass.
- 2026-10-16: src/eval/evaluator.py + tests/test_evaluator.py; reviewer tìm 2 lỗi nghiêm trọng (ghép cột treo, trần ghép cột chấm sai) + 2 lỗi has_order_by, đã sửa; 222 test pass. Xong T1 (chưa commit).
