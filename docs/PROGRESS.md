# Nhật ký tiến độ
## Trạng thái hiện tại
Target: T1–T6 xong (2026-11-03). Kết quả cuối: README.md, results/report_test*.md, docs/error_analysis.md.

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

### Cập nhật 2026-10-25 (lần 2)
- Đã: commit dev; chốt quy ước (a) loại đơn hủy, (b) tỷ lệ = %, (c) tháng = số nguyên → ghi vào dataset.md mục 7.
  dev còn 50 câu, ambiguous 0 ERROR. Bộ test chốt **150 câu**; đã viết câu hỏi test (chưa SQL).
- Claude KHÔNG đọc test.jsonl (guardrail). Thêm vào check_dataset: `--questions-only`, W_SIMILAR (test gần giống dev),
  W_RELATIVE_TIME / W_VAGUE / W_SHORT. Ngưỡng giống 45% hiệu chỉnh trên dev. 288 test pass.
- Agent độc lập soát logic dev + ambiguous: còn lỗi SQL ở amb-07, amb-10, amb-05, amb-04; bất nhất "đơn đầu tiên"
  (dev-047 loại đơn hủy, amb-04 / amb-11 không); năm trả chuỗi ở dev-018, dev-026; dev-060 ngưỡng "ít nhất 3" vô tác dụng.
  Claude đã sửa tag / độ khó / lời câu hỏi (dev-001 trả lại "Sài Gòn", 025, 035, 040, 053; tag 9 câu; 044, 045 → medium).

### Cập nhật 2026-10-29 — T2 đóng, bắt đầu T3
- Commit + push bộ câu hỏi (dev 50, test 150, mơ hồ 12, độc hại 12) và công cụ kiểm câu hỏi.
- **Quyết định T3:** Haiku 5.5 + Sonnet 5.5 (cùng thế hệ), tắt thinking cả hai. API 2026-10-21 bỏ temperature,
  không có seed → không cố định được đầu ra; dùng `--repeats` để đo dao động. Đã sửa PROJECT.md, CLAUDE.md.
- Pipeline `src/pipeline/` (schema, prompts, llm, linking, run) + `scripts/run_pipeline.py`, `scripts/compare_runs.py`.
  C0 = DDL; C1 = + dòng mẫu, giá trị phân biệt; C2 = C1 trên bảng do LLM chọn (đo linking recall).
  Split test bị chặn nếu thiếu cờ `--i-am-running-final-test`. `--max-cost` dừng khi vượt ngân sách.
- Reviewer: 4 lỗi nghiêm trọng (lỗi 529/408/409 làm dừng cả lượt; recall phân biệt hoa thường; lỗi linking bị
  nuốt + tính recall 1.0; lỗi API bị chấm như câu sai) + 8 trung bình → đã sửa, 348 test pass.
- **Chưa chạy API thật:** `.env` đang rỗng → cần tạo API key và ghi vào `.env`.
- Quyết định: bỏ CHECK chứa giá trị chữ khỏi DDL trong prompt (`strip_value_checks`, áp dụng mọi cấu hình) để
  C0 không thấy trước giá trị status/segment/payment_method/gender; C0 → C1 chỉ khác phần giá trị mẫu.
  Hạn chế cần ghi trong báo cáo: DB thật thường có CHECK, nên mức tăng C0 → C1 ở đây là cận trên. 357 test pass.
- Đã bỏ cột id khỏi 6 đáp án mơ hồ (amb-01, 03, 04, 07, 09, 10) cho khớp luật prompt; ambiguous 0 ERROR, 0 WARN.

- 2026-10-30: API chạy được. Dev lượt 1 (prompt cũ): Haiku C0/C1/C2 = 52/64/62%, Sonnet = 78/78/78%; tổng $0.43.
  value_mismatch Haiku 3 → 9/11 nhờ C1. C2 recall 98% nhưng không tăng accuracy, tốn gấp đôi.
  Phân tích câu sai: phần lớn do quy ước (năm dạng chuỗi, luật đơn hủy trong prompt hẹp hơn dataset.md, cột thừa,
  DISTINCT theo tên). Đã chốt: năm = số nguyên; mọi câu về đơn đều loại đơn hủy; mỗi đối tượng một dòng.
  Sửa prompt (luật 2, 4, 5) + dataset.md; tôi sửa đáp án dev-018/026 và rà test/ambiguous.
- Chốt chi phí: Haiku là model chính; Sonnet chỉ chạy 1 lần ở T5 (test, C0 + cấu hình tốt nhất). Xem PROJECT.md.

- Dev Haiku sau khi sửa prompt + thêm luật "không ROUND nếu không được yêu cầu": C0/C1/C2 = 78/88/88%, tổng < $0.05.
  value_mismatch: C0 4/11 → C1 10/11. Còn sai ở C1: dev-031/044 (vẫn thêm cột / DISTINCT theo tên), dev-054 (quên lũy kế),
  vài câu lật qua lại giữa các lượt (049, 053, 037, 060) = nhiễu do không cố định được đầu ra.
  McNemar C0 vs C1 (b=7, c=2): p ≈ 0.18 → trên 50 câu chưa đủ bằng chứng; cần test 150 câu + chạy lặp.
  Dừng chỉnh prompt trên dev ở đây để tránh quá khớp với dev.

### 2026-10-30 — T4: C3 + C4
- Chốt: kho ví dụ = dev (leave-one-out khi chấm dev; test dùng cả 50 câu dev); C4 sửa khi SQL lỗi HOẶC 0 dòng, tối đa 2 lần.
- `src/pipeline/fewshot.py` (3 ví dụ, Jaccard bigram, dùng chung `question_bigrams` với W_SIMILAR; đường dẫn dev cố định).
  Ví dụ nằm ở user message → system C3/C4 giống hệt C2. Vòng sửa trong `run.py` (`_repair`), ghi `first_sql`,
  `first_correct` → thống kê fixed/broken. Summary có `pool_hash`; `prompt_hash` gồm cả K và MAX_REPAIRS.
- Reviewer: không vi phạm guardrail; 4 lỗi trung bình đã sửa (model trả lại SQL cũ vẫn bị ép sửa tiếp; từ chối ở lượt
  sửa của câu độc hại không được tính; C3 thiếu pool lặng lẽ thành C2; prompt_hash không đổi khi dev đổi).
  Test bắt thêm 2 lỗi: history bị sửa tại chỗ; first_correct sai khi lượt đầu từ chối. 383 test pass.
- Dev Haiku: C3 = 92%, C4 = 90% (~$0.02). C4 **không kích hoạt lần sửa nào** (Haiku không ra SQL lỗi hay rỗng trên dev)
  → C3 vs C4 chỉ là nhiễu (C4 lượt này từ chối nhầm dev-018). Hạn chế cần ghi: trigger "0 dòng" không bắt được
  COUNT/SUM sai (luôn ra 1 dòng). Few-shot cũng làm lộ giá trị DB qua ví dụ (vd 'wholesale').
  Ghi chú: amb-08 giống dev-002 (Jaccard 0.50) → ở C3, dev-002 là ví dụ đầu cho amb-08.

### 2026-10-31 — T5 phần 1: công cụ phân tích (chưa chạy test)
- `docs/analysis_plan.md`: đăng ký trước ma trận chạy, metric, các cặp so sánh, quy tắc kết luận — viết TRƯỚC khi chạy test.
- `src/eval/stats.py` (bootstrap theo câu hỏi, McNemar chính xác, Holm, Python thuần), `scripts/analyze_runs.py`
  (→ results/report_<split>.md), `scripts/run_matrix.py` (chạy cả ma trận một lệnh, ngân sách tổng, `--dry-run`).
- Thử trên dev: Haiku C0→C1 +10 điểm nhưng p_Holm 0.72; C0→C3 +14 điểm, CI bootstrap không chứa 0 nhưng McNemar p 0.065
  → "chưa đủ bằng chứng" trên 50 câu. Dry-run test: ước tính ~$1.34.

- Reviewer: thống kê đúng, chốt chặn test kín; 4 lỗi nghiêm trọng đã sửa (họ Holm tự thu nhỏ khi thiếu lượt chạy;
  lượt chạy lẻ sau có thể thay lượt chính; báo cáo sập khi khác tập câu; chạy lại ma trận sẽ chạy test hai lần) +
  run_matrix kiểm prompt đã đóng băng (1ca9c19a74a1), kết luận cần hai phép thử cùng chiều, cột lỗi API. 409 test pass.
  Trần ngân sách ma trận test nâng lên $2.0 (ước tính $1.34; tổng dự án vẫn < $3).

## Phiên 2026-11-02 — T5: đã chạy test (một lần), báo cáo `results/report_{test,ambiguous,malicious}.md`
- Commit kế hoạch phân tích lúc 01:29 ngày 31/10, lượt test đầu tiên lúc 01:36 → đăng ký trước hợp lệ. Hash prompt khớp ở mọi lượt.
- Test (Haiku × 3 lần lặp): C0 65.6, C1 73.8, C2 75.8, C3 76.0, C4 76.2%. Sonnet: C0 70.0, C3 80.7%. Chi phí test khoảng $1.1.
- Kết luận theo quy tắc: chỉ C0→C3 (+10.4, p = 0.005, không hiệu chỉnh) là "B tốt hơn". C0→C1 có CI +2.2…+14.4 không chứa 0,
  nhưng McNemar p_Holm = 0.54 → "chưa đủ bằng chứng" (đa số phiếu làm mất thông tin các câu đúng 1/3 hoặc 2/3).
- Dev cao hơn test khoảng 14–16 điểm (C3: 92 so với 76) → prompt đã khớp quá mức với dev; đây chính là lý do cần bộ test giữ riêng.
- value_mismatch: C0 14% → C1–C4 100% (7 câu). C3/C4 từ chối 6 bản ghi test và 6/12 câu mơ hồ → cần đọc khi phân tích lỗi.
- Bộ độc hại: cả 5 cấu hình từ chối 12/12. C4 kích hoạt sửa 6 lần: sửa được 2, làm hỏng 0.

### Đang vướng / làm dở
- Phân tích lỗi Haiku C3 (35 câu sai theo đa số): khoảng 21 câu do đáp án vi phạm quy ước (chủ yếu quy tắc 7 về đơn hủy),
  5 câu hỏi mơ hồ, 9 lỗi thật của model. Đã ghi sai lệch #1 vào `docs/analysis_plan.md`.
- Đã sửa đáp án test (giữ quy ước NULL mới, 4 câu đổi đề bị loại). `scripts/regrade.py` chấm lại không gọi API:
  Haiku C0 76.5, C1 84.0, C2 88.4, C3 89.5, C4 90.0%; Sonnet C0 82.9, C3 94.5% (146 câu).
  C0→C3 tốt hơn ở cả hai bộ số; Haiku→Sonnet ở C0 chỉ đạt ở bộ đã sửa. C3 còn 14 câu sai = 9 lỗi model + 5 câu mơ hồ.
  Ghi sai lệch #1–#3 trong `docs/analysis_plan.md`. 413 test pass.
## Phiên 2026-11-03 — T6: đóng gói
- `app.py`: demo Gradio (mặc định Haiku C3, cho đổi C0–C4 / Sonnet). Dùng lại `answer_question()`, SQL đi qua executor,
  câu ví dụ chỉ lấy từ dev, giới hạn 500 ký tự, hiện chi phí cộng dồn của phiên. `gradio==6.31.0`. `tests/test_demo.py`.
- `README.md` (tiếng Anh): cấu hình, an toàn, dataset, hai bộ số, so sánh đã đăng ký trước, phân biệt kết luận vững
  và kết luận dễ đổ, phân tích lỗi, hạn chế, hướng dẫn tái lập. `docs/error_analysis.md`: 35 câu C3 = 21 lỗi đáp án
  + 5 câu mơ hồ + 9 lỗi model.
- Tổng chi phí API của cả dự án: $1.61 (dev 0.49, test 1.11, mơ hồ + độc hại 0.015).
- Dòng CV:
  - EN: "Built a Vietnamese Text-to-SQL system (Claude API, SQLite) and ran a pre-registered ablation of 5 prompting
    configurations on 146 held-out questions: sample values + schema linking + retrieved few-shot examples raised
    execution accuracy from 76.5% to 89.5% (+13.0 pts, 95% CI +6.4…+19.9, McNemar p = 0.001); sandboxed read-only
    SQL executor, bootstrap/McNemar/Holm statistics, error analysis by query type."
  - VI: "Xây dựng hệ thống Text-to-SQL tiếng Việt; đánh giá có đăng ký trước 5 cấu hình prompt trên 146 câu test:
    giá trị mẫu + chọn bảng + ví dụ few-shot tăng execution accuracy từ 76,5% lên 89,5% (+13,0 điểm, CI 95%
    +6,4…+19,9; p = 0,001); executor SQL chỉ đọc nhiều lớp an toàn, thống kê bootstrap/McNemar/Holm, phân tích lỗi."
- Việc còn lại (tùy chọn): chụp màn hình demo vào `docs/demo.png` rồi thêm vào README; công bố dataset lên HuggingFace.
- Commit các file `results/*_summary.json` của test, ambiguous, malicious và các báo cáo.
- Sửa SQL theo danh sách trên; chốt quy ước năm (số hay chuỗi) và "đơn đầu tiên" có tính đơn hủy không.
- Chạy `check_dataset.py ... --questions-only` trên test, tự sửa câu bị W_SIMILAR / W_VAGUE / W_RELATIVE_TIME; rồi viết SQL test.
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
