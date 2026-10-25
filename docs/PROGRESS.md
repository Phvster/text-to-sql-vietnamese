# Nhật ký tiến độ
## Trạng thái hiện tại
Target: T2 (bộ câu hỏi). T1 xong, đã commit và push (`origin/main`, repo private). Hạ tầng T2 xong, chưa commit.
Việc còn lại của T2 là việc của tôi: viết câu hỏi + SQL đáp án.

## Phiên gần nhất (2026-10-16)
### Đã làm xong
- T1: evaluator + reviewer; commit thành 5 commit, xóa `Kế hoạch.docx` khỏi lịch sử, `*.docx` vào `.gitignore`; push lên GitHub (private).
- `requirements.txt` (pin phiên bản, Faker==40.40.0).
- `docs/dataset.md`: định dạng JSONL, độ khó, tag, 10 quy ước viết đáp án, bảng mã lỗi.
- `src/eval/dataset.py` + `scripts/check_dataset.py`: kiểm định dạng, chạy đáp án qua executor, cảnh báo đáp án rỗng / không ổn định.
- `scripts/try_sql.py`: chạy thử SQL khi viết đáp án.
- Executor thêm cờ `reverse_unordered` (chỉ cho kiểm dataset). Reviewer: không làm yếu lớp an toàn nào; các lỗi ở phần kiểm đáp án đã sửa.
- `data/questions/dev_drafts.md`: 60 câu nháp dev + 12 mơ hồ + 12 độc hại, KHÔNG có SQL.
- `pytest -q`: 275 passed.

### Cập nhật 2026-10-17
- Đã sửa lời câu hỏi dev trong `dev_drafts.md` (Claude sửa thêm lỗi chính tả, làm rõ M10).
- Chốt: câu độc hại dạng ghép → từ chối cả câu. `malicious.jsonl` xong (12 câu, check_dataset: 0 ERROR, 0 WARN).
- Viết nháp SQL cho 12 câu mơ hồ: 9/12 lỗi khi chạy. Lỗi chính: tên bảng sai (`customer`, `product`, `order`),
  ký tự Word (`‘ ” ≥ ≤`), ngày `'2025-1-1'` và cận `<= '2025-12-31'`, thiếu khóa phụ, `convention` chưa ghi.
  → Đã thêm quy ước ngày tháng vào `docs/dataset.md` (mục 9, 10).
- Claude không viết/sửa SQL đáp án (guardrail CLAUDE.md), chỉ chỉ ra lỗi.

### Cập nhật 2026-10-18
- `ambiguous.jsonl`: Claude sửa phần không phải SQL (id → amb-01..12, thêm difficulty/tags, chính tả). Còn 8 ERROR, đều ở SQL.
  Lỗi chạy được nhưng sai: amb-06 viết 'Bà Rịa-Vũng Tàu' (DB: 'Bà Rịa - Vũng Tàu') → đếm thiếu cả tỉnh;
  amb-08 ngưỡng 1,5 triệu → 79% đơn là "lớn"; amb-12 convention loại đơn hủy nhưng SQL không lọc.
- `dev.jsonl`: Claude tạo khung 60 câu từ dev_drafts.md (`sql` trống, difficulty/tags dự kiến). Tôi bỏ bớt ~10 câu, điền SQL.

### Cập nhật 2026-10-24
- Lỡ xóa dev-031..060 (file chưa commit) → Claude tạo lại từ dev_drafts.md (sql trống). **Nhớ commit thường xuyên.**
- Tôi đã viết SQL dev-001..030: 0 ERROR. Lỗi logic còn lại: dev-001 ('Sài Gòn'), dev-010 ('VIP'), dev-023 ('Huế')
  dùng cách nói thay vì giá trị trong DB; dev-018, dev-023 chưa loại đơn hủy; nhiều câu thừa cột hoặc thừa ORDER BY.
- dev-024: đổi lời câu hỏi "trên 10" → "trên 5 sản phẩm" (thương hiệu nhiều nhất chỉ có 9 sản phẩm). SQL cần sửa theo.

### Cập nhật 2026-10-25
- Tôi viết xong SQL 60 câu dev: 0 ERROR, 3 WARN. Claude kiểm logic: 5 câu sai kết quả (001, 018, 031, 056, 059),
  3 câu yếu nên bỏ (039, 048 rỗng; 042 đáp án = số sản phẩm đã bán), 3 quy ước chưa nhất quán
  (có loại đơn hủy khi tính bán/chi tiêu; tỷ lệ dạng 0–1 hay %; tháng dạng số hay chuỗi).
- Claude sửa không đụng SQL: tag dev-038, lời câu hỏi dev-040.

### Đang vướng / làm dở
- `dev.jsonl`: sửa 5 câu sai, chốt 3 quy ước, bỏ 10 câu còn 50. **Chưa commit lần nào.** `test.jsonl` chưa có.
- Sửa 12 câu SQL mơ hồ theo nhận xét, ghi `convention` đầy đủ, chạy `try_sql.py` từng câu.
- Câu hỏi kiểm tra hiểu bài: đã chấm 5 câu về hạ tầng dataset (2026-10-17); còn 5 câu về evaluator.
- Chưa làm bài tập SQL `COUNT(*)` vs `COUNT(o.order_id)`.
- Timeout executor còn vượt được trong 1 trường hợp cố tình — chưa quyết định có làm tiến trình con hay không.
- Danh sách test do Claude đề xuất → tôi cần đọc lại để chắc khớp ý.

### Việc đầu tiên khi mở lại
1. Đọc lại `docs/dataset.md` mục 9–10, sửa 12 câu SQL mơ hồ bằng `try_sql.py`, ghi vào `ambiguous.jsonl`.
2. Viết SQL cho 50 câu dev → `dev.jsonl`, chạy `check_dataset.py` tới khi 0 ERROR.
3. Quyết định trước khi viết test: giữ 150 câu hay giảm còn 120 (phương án dự phòng trong PROJECT.md).

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
### Dataset (T2)
- Định dạng và quy ước đầy đủ: `docs/dataset.md`. Claude soạn nháp câu hỏi dev (không SQL); câu hỏi test tôi tự nghĩ.
- `check_dataset.py` mặc định chỉ in id + mã lỗi (chạy được trên test.jsonl). Claude không chạy nó trên test.jsonl.
- Kiểm "ổn định" của đáp án: (1) chạy lại với `PRAGMA reverse_unordered_selects` qua cờ `reverse_unordered` của executor;
  (2) thêm khóa phụ tăng/giảm vào ORDER BY ngoài cùng và ORDER BY + LIMIT trong subquery. Không bắt được GROUP_CONCAT trong nhóm.
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
- T2: viết 50 dev / 150 test + ~10 mơ hồ + ~10 độc hại (SQL đáp án do tôi tự viết và kiểm).
- T3: pipeline C0, C1, C2 trên dev (nhớ bóc khối ```sql``` khỏi output LLM).
## Log
- 2026-10-02: tạo repo.
- 2026-10-05: docs/schema.md, scripts/generate_db.py, tests/test_generate_db.py (8 test pass).
- 2026-10-06: src/db/executor.py + tests/test_executor.py; reviewer tìm 3 lỗi nghiêm trọng (raise, bộ nhớ, timeout hàm chuỗi), đã sửa/giảm thiểu; 148 test pass.
- 2026-10-16: src/eval/evaluator.py + tests/test_evaluator.py; reviewer tìm 2 lỗi nghiêm trọng (ghép cột treo, trần ghép cột chấm sai) + 2 lỗi has_order_by, đã sửa; 222 test pass. Xong T1, commit + push (private).
- 2026-10-16: hạ tầng T2 (dataset.md, check_dataset.py, try_sql.py, cờ reverse_unordered, dev_drafts.md); reviewer không thấy lỗi an toàn, sửa 2 lỗi bỏ sót đáp án không ổn định; 275 test pass.
- 2026-10-17: malicious.jsonl (12 câu); chốt quy ước câu ghép; nhận xét nháp SQL câu mơ hồ; thêm quy ước ngày tháng vào dataset.md.
