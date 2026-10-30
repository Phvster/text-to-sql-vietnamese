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
(chưa có)
