# Text-to-SQL tiếng Việt: thông tin đề tài

## 1. Tóm tắt

Hệ thống nhận câu hỏi bằng tiếng Việt, sinh câu lệnh SQL, chạy trên cơ sở dữ liệu thật và trả về bảng kết quả.

Đóng góp chính của project không phải là mô hình mới mà là **so sánh có đo lường** các kỹ thuật cải thiện độ chính xác so với baseline, kèm phân tích lỗi theo loại truy vấn. Project dùng làm sản phẩm trên CV cho vị trí AI/ML/NLP engineer.

## 2. Bài toán

- **Đầu vào:** câu hỏi tiếng Việt, ví dụ "Top 5 khách hàng chi tiêu nhiều nhất năm 2025 là ai?"
- **Đầu ra:** câu SQL (SQLite) và bảng kết quả khi chạy câu SQL đó.
- **Điểm khó cần đo:**
  - Ánh xạ từ ngữ sang schema (schema linking): "doanh thu" tương ứng cột `total_amount`.
  - Lệch giá trị: người dùng nói "Sài Gòn", DB lưu "TP. Hồ Chí Minh".
  - Truy vấn phức tạp: nhiều JOIN, subquery, tỷ lệ, top-N theo nhóm, xử lý ngày tháng.
  - Câu hỏi mơ hồ và câu hỏi độc hại ("xóa bảng khách hàng").
  - SQL chạy được nhưng trả kết quả sai logic mà không báo lỗi.

## 3. Phạm vi

**Trong phạm vi**
- Một cơ sở dữ liệu bán hàng tự sinh, SQLite.
- Bộ câu hỏi 200 câu tiếng Việt có SQL đáp án đã kiểm chứng.
- 5 cấu hình so sánh (C0–C4), hai cỡ model LLM.
- Đánh giá bằng execution accuracy, kiểm định thống kê, phân tích lỗi.
- Demo Gradio, README, dòng mô tả cho CV.

**Ngoài phạm vi (cắt để kịp 3 tuần)**
- Fine-tune LoRA (chỉ làm nếu còn dư thời gian, là bonus).
- Nhiều hệ quản trị CSDL khác nhau (chỉ SQLite).
- Hội thoại nhiều lượt, câu hỏi tiếp nối.

## 4. Cơ sở dữ liệu

- Tự sinh bằng script (Faker), **không dùng Chinook/Northwind** vì LLM có thể đã thấy các bộ này nhiều lần (data contamination).
- 6 bảng: `customers`, `products`, `categories`, `orders`, `order_items`, `reviews`.
- Quy mô tham khảo: khoảng 2.000 khách hàng, 200 sản phẩm, 20.000 đơn, 60.000 dòng chi tiết đơn.
- Cố tình có giá trị lệch với cách người dùng nói (địa danh, trạng thái đơn, loại khách) để đo lỗi lệch giá trị.
- Schema đặt tên tiếng Anh, câu hỏi tiếng Việt (giống tình huống thực tế).

## 5. Bộ câu hỏi (dataset)

| Thành phần | Số lượng | Ghi chú |
|---|---|---|
| Dev | 50 | Dùng để chỉnh prompt và cấu hình |
| Test | 150 | Chỉ chấm cuối, không được dùng để tinh chỉnh |
| Bộ mơ hồ | khoảng 10 | Ghi rõ quy ước đáp án; chấm riêng |
| Bộ độc hại | khoảng 10 | Kỳ vọng hệ thống từ chối; chấm riêng |

Độ khó (tham khảo, trên 200 câu): dễ ~60 (một bảng), trung bình ~70 (JOIN hoặc GROUP BY), khó ~45 (nhiều JOIN, HAVING, subquery), rất khó ~25 (lồng nhau, tỷ lệ, top-N theo nhóm).

**Nguyên tắc:** SQL đáp án do người làm tự chạy và kiểm tra kết quả từng câu. LLM có thể soạn nháp câu hỏi nhưng không được vừa sinh đáp án vừa làm đối tượng đánh giá.

## 6. Các cấu hình so sánh

| Cấu hình | Nội dung |
|---|---|
| C0 | Baseline: toàn bộ schema + câu hỏi, zero-shot |
| C1 | C0 + dòng dữ liệu mẫu và giá trị phân biệt của các cột |
| C2 | C1 + schema linking (chỉ đưa bảng/cột liên quan) |
| C3 | C2 + few-shot chọn theo độ tương tự câu hỏi (retrieval) |
| C4 | C3 + vòng sửa lỗi bằng phản hồi thực thi (tối đa 2 lần) |

Chạy với hai cỡ model (Haiku 5.5 và Sonnet 5.5, cùng thế hệ; thinking tắt) để có thêm trục chi phí và độ chính xác.
Tiết kiệm chi phí (chốt 2026-10-30): **Haiku là model chính** — dùng cho mọi lượt dev, C3/C4, chạy lặp, và test
đủ C0–C4. **Sonnet chỉ chạy một lần ở T5 trên test, 2 cấu hình** (C0 và cấu hình tốt nhất của Haiku) để trả lời
"kỹ thuật còn cần không khi model mạnh hơn". Sonnet trên dev chỉ có lượt 2026-10-30 (prompt cũ) làm tham khảo.
Cập nhật 2026-10-29: từ API version 2026-10-21, `temperature`/`top_p`/`top_k` bị từ chối và Claude API không có `seed`,
nên không cố định được đầu ra. Đo độ dao động bằng cách chạy lặp (`--repeats`); số lần lặp cho test chốt ở T5.

## 7. Đánh giá

- **Metric chính:** execution accuracy, so tập kết quả không phụ thuộc thứ tự dòng (trừ khi đáp án có ORDER BY) và không phụ thuộc tên cột.
- **Metric phụ:** tỷ lệ SQL chạy được, độ trễ, chi phí mỗi câu, tỷ lệ từ chối đúng ở bộ độc hại.
- **Thống kê:** khoảng tin cậy bootstrap; McNemar cho cặp cấu hình trên cùng tập câu hỏi. Không kết luận "tốt hơn" khi khoảng tin cậy chồng nhau.
- **Phân tích lỗi** theo loại: schema linking, JOIN sai, GROUP BY sai, lệch giá trị, xử lý ngày tháng, mơ hồ, cú pháp.
- **Lưu ý:** execution accuracy có thể chấm nhầm khi hai câu SQL khác nhau trùng kết quả. Cần DB đủ lớn, đa dạng giá trị và kiểm tra thủ công một số trường hợp.

## 8. An toàn

- DB mở ở chế độ chỉ đọc.
- Chỉ chấp nhận đúng một câu `SELECT`; chặn mọi lệnh ghi, xóa, thay đổi schema.
- Timeout 5 giây, giới hạn 1.000 dòng.
- Mọi SQL do model sinh bắt buộc đi qua một module thực thi duy nhất (`src/db/executor.py`).
- Có test cho các trường hợp tấn công điển hình.

## 9. Kiến thức cần có

- **Vững:** SQL (JOIN, GROUP BY/HAVING, subquery, CTE, window function, ngày tháng trong SQLite); Python để viết một package nhỏ và test; thiết kế thí nghiệm và thống kê cơ bản.
- **Mức dùng được:** prompt cho LLM, embedding và retrieval, thiết kế schema, Git, gọi API LLM, Gradio.
- **Không cần:** kiến trúc Transformer bên trong, fine-tune, NLP cổ điển.

## 10. Kế hoạch 3 tuần (6 target)

| Tuần | Target | Kết quả cần có |
|---|---|---|
| 1 | T1: Hạ tầng | Repo, CLAUDE.md, DB tự sinh, executor an toàn, evaluator có unit test (đã qua review) |
| 1 | T2: Bộ dữ liệu | 200 câu (50 dev / 150 test) có SQL đã kiểm chứng, gán độ khó; bộ mơ hồ và độc hại |
| 2 | T3: Baseline và nhánh đơn giản | Pipeline chạy C0, C1, C2 trên dev; chốt cấu hình để chạy test |
| 2 | T4: Nhánh nâng cao | C3, C4; chạy hai cỡ model |
| 3 | T5: Đánh giá | Bảng ablation, khoảng tin cậy, phân tích lỗi, chi phí và độ trễ |
| 3 | T6: Đóng gói | Demo Gradio, README có bảng kết quả và hạn chế, dòng mô tả CV |

T2 là target dễ trượt nhất (viết và kiểm chứng SQL thủ công). Phương án dự phòng: giảm test xuống 120 câu, quyết định trước khi bắt đầu.

## 11. Làm việc với Claude Code

- Cấu trúc: `CLAUDE.md` ngắn (guardrail ở đầu), `.claude/rules/` (eval, safety), `.claude/agents/` (researcher, reviewer), nhật ký ở `docs/PROGRESS.md`.
- Mỗi target: mở session mới và cho Claude đọc CLAUDE.md cùng PROGRESS.md; dùng Plan Mode trước khi sửa code; `/compact` khi context khoảng 70%; cập nhật PROGRESS.md trước khi đóng.
- Dùng `reviewer` đặc biệt cho evaluator và executor.
- Giao cho Claude Code phần boilerplate; tự đọc và hiểu evaluator, thiết kế cấu hình, phân tích lỗi để bảo vệ được khi phỏng vấn.

## 12. Rủi ro chính

| Rủi ro | Cách xử lý |
|---|---|
| Baseline LLM đã quá mạnh, cải tiến nhỏ | Báo cáo trung thực; tập trung phân tích ở câu khó và lệch giá trị |
| Đáp án SQL sai | Tự chạy và kiểm từng câu; reviewer kiểm evaluator |
| Chỉnh prompt theo test (rò rỉ đánh giá) | Tách dev/test cứng, ghi trong guardrail |
| Phình phạm vi | Cắt fine-tune, một DB, một dialect |
| Chênh lệch giữa cấu hình chỉ là nhiễu | Bootstrap và McNemar |
| Không bảo vệ được code khi phỏng vấn | Tự đọc và hiểu evaluator và pipeline |

## 13. Sản phẩm bàn giao

- Repo gọn, tái lập được (seed, config, hướng dẫn chạy).
- Bộ dữ liệu và DB (có thể công bố trên HuggingFace).
- Bảng ablation, phân tích lỗi, hạn chế nêu rõ trong README.
- Demo: nhập câu hỏi, xem SQL sinh ra và bảng kết quả.
- Dòng mô tả cho CV, điền số liệu thật sau khi có kết quả. Mẫu:
  "Xây dựng hệ thống Text-to-SQL tiếng Việt, đánh giá 5 cấu hình trên 150 câu test; cải thiện execution accuracy từ __% lên __% (khoảng tin cậy 95%: __), phân tích lỗi theo loại truy vấn."

## 14. Thông tin còn thiếu

- Số giờ có thể dành mỗi tuần.
- Có API key sẵn hay chỉ chạy được model local.
- Mức SQL hiện tại (có thể cần thêm vài ngày luyện trước T2).