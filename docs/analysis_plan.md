# Kế hoạch phân tích T5 (đăng ký trước — viết ngày 2026-10-31, TRƯỚC khi chạy test)

File này chốt cách chạy và cách phân tích bộ test **trước khi thấy kết quả**, để không thể (vô tình) chọn phép thống kê,
cặp so sánh hay cấu hình "đẹp số" sau khi đã nhìn số liệu. Mọi thay đổi sau khi chạy test phải ghi rõ ở cuối file.

## Cấu hình đã đóng băng
- Prompt: `prompt_hash = 1ca9c19a74a1` (lượt dev C3/C4 ngày 2026-10-30; `run_matrix.py` từ chối chạy nếu khác).
  Kho ví dụ C3/C4: `dev.jsonl` (`pool_hash = 1fb78f8fabfc`). Lượt dev Haiku C0–C2 mang hash cũ `ac7c11feaec7` chỉ vì
  cách tính hash được mở rộng sau đó (thêm mẫu few-shot/sửa lỗi); nội dung prompt C0–C2 không đổi.
- Model: Haiku 5.5 (chính), Sonnet 5.5 (phụ); thinking tắt. Không đặt được temperature (API) → chạy lặp.
- Cấu hình tốt nhất trên dev: **C3** (Haiku dev: C0 78, C1 88, C2 88, C3 92, C4 90%).

## Ma trận chạy (`scripts/run_matrix.py`)
| Split | Model | Cấu hình | Số lần lặp |
|---|---|---|---|
| test (150) | Haiku | C0, C1, C2, C3, C4 | 3 |
| test (150) | Sonnet | C0, C3 | 1 |
| ambiguous (12) | Haiku | C0–C4 | 1 |
| malicious (12) | Haiku | C0–C4 | 1 |

Ngân sách tổng: $2.0 (dừng nếu vượt; ước tính ~$1.35). Bị ngắt giữa chừng → chạy lại lệnh: ô đã xong được bỏ qua.
Báo cáo test chỉ dùng lượt đúng hash + đúng số lần lặp ở bảng trên.

## Metric và thống kê (`scripts/analyze_runs.py`, `src/eval/stats.py`)
- **Metric chính:** execution accuracy, trung bình qua các lần lặp.
- **Khoảng tin cậy 95%:** bootstrap theo câu hỏi (10.000 lần, seed 0); mỗi câu = tỉ lệ đúng qua các lần lặp.
- **So sánh định trước (Haiku, test):** C0→C1, C1→C2, C2→C3, C3→C4 (họ 4 so sánh, hiệu chỉnh Holm),
  cộng C0→C3 (tổng tác dụng, báo riêng). **Sonnet vs Haiku** ở C0 và C3 (báo riêng).
- Mỗi cặp: McNemar chính xác trên "đúng theo đa số lần lặp" + CI bootstrap ghép cặp của chênh lệch accuracy.
- **Quy tắc kết luận:** chỉ nói "B tốt hơn A" khi p < 0.05 VÀ CI chênh lệch không chứa 0 VÀ hai phép thử cùng chiều
  (b > c ⇔ chênh lệch > 0). Họ 4 so sánh dùng p đã Holm với m = 4 cố định (cặp thiếu lượt chạy tính p = 1);
  3 so sánh phụ dùng p không hiệu chỉnh và ghi rõ "không hiệu chỉnh".
  Ngược lại: "không đủ bằng chứng có khác biệt" (KHÔNG nói "không có tác dụng").
- Lỗi API: vẫn tính là sai trong accuracy chính; báo số lỗi API của từng lượt bên cạnh.

## Phân tích phụ
- Accuracy theo tag và độ khó (mọi cấu hình × model); phân bố `reason`.
- C4: số câu kích hoạt sửa, fixed (sai → đúng), broken (đúng → sai).
- Đọc tay khoảng 20 câu sai của Haiku C3 → xếp loại lỗi (schema linking, JOIN, GROUP BY, lệch giá trị, ngày tháng,
  mơ hồ, cú pháp, chấm nhầm).
- ambiguous: accuracy theo quy ước đáp án; malicious: tỉ lệ từ chối đúng, và mọi lệnh ghi đều bị executor chặn.
- Chi phí và độ trễ trung bình mỗi câu.

## Sau khi chạy test
- Không chỉnh prompt, cấu hình, đáp án dựa trên kết quả test.
- Nếu phát hiện lỗi hạ tầng (executor, evaluator, pipeline) hoặc đáp án sai: ghi vào mục "Sai lệch so với kế hoạch"
  dưới đây, báo cả số trước và sau khi sửa.

## Sai lệch so với kế hoạch
1. **2026-11-02 — đáp án test vi phạm quy ước của chính `docs/dataset.md`** (phát hiện khi phân tích lỗi Haiku C3).
   Trong 35 câu C3 sai theo đa số, khoảng 21 câu là model làm đúng quy ước nhưng đáp án thì không: thiếu loại đơn
   `cancelled` (quy tắc 7), trả tháng/năm dạng chuỗi, tỷ lệ không ở dạng phần trăm, dùng `'now'` (quy tắc 9).
   - Để không thiên vị cấu hình nào, đã quét **máy móc cả 150 đáp án** (không nhìn kết quả model): 44 câu bị gắn cờ.
   - Tiêu chí sửa: chỉ sửa khi đáp án vi phạm một quy tắc **đã ghi** trong `docs/dataset.md` trước ngày chạy test.
     Câu hỏi mơ hồ thì giữ nguyên và báo là mơ hồ. Người làm dự án tự sửa đáp án.
   - Chấm lại các SQL đã sinh (không gọi lại API). Báo cáo **cả hai** bộ số: theo đáp án gốc và theo đáp án đã sửa.
   - Công cụ: `scripts/regrade.py`, rồi `analyze_runs.py --corrected` → `results/report_test_corrected.md`.
     Ngoài các cờ ở trên, còn sửa thêm khóa phụ phá hòa (quy tắc 1) và tỷ lệ đơn hủy/trả tính theo đơn (109, 130).
2. **2026-11-02 — quy ước NULL mới:** thêm `brand IS NOT NULL` / `city IS NOT NULL` ở 13 câu
   (028, 047, 049, 055, 058, 064, 075, 084, 094, 105, 110, 123, 130). Quy ước này **chưa có** trước ngày chạy test;
   người làm dự án quyết định giữ. Từ nay đã ghi vào `docs/dataset.md`.
3. **2026-11-02 — 4 câu bị đổi đề** (080, 096, 128, 150) khi sửa đáp án → loại khỏi bộ số đã sửa ở mọi cấu hình
   (model đã trả lời đề cũ). Bộ số đã sửa có 146 câu.

**Kết quả hai bộ số** (Haiku × 3, Sonnet × 1):

| | Haiku C0 | C1 | C2 | C3 | C4 | Sonnet C0 | Sonnet C3 |
|---|---|---|---|---|---|---|---|
| Đáp án gốc (150 câu) | 65.6 | 73.8 | 75.8 | 76.0 | 76.2 | 70.0 | 80.7 |
| Đáp án đã sửa (146 câu) | 76.5 | 84.0 | 88.4 | 89.5 | 90.0 | 82.9 | 94.5 |

Kết luận **vững ở cả hai bộ số**: Haiku C0→C3 tốt hơn (+10.4 / +13.0 điểm; p = 0.005 / 0.001).
Chỉ đạt ở bộ đã sửa (**dễ đổ**, phải nói rõ): Haiku C0 → Sonnet C0 (p = 0.012, không hiệu chỉnh).
Họ 4 bước liên tiếp: ở cả hai bộ số không bước nào đạt sau Holm.
