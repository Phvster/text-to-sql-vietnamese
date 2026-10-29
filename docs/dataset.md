# Bộ câu hỏi: định dạng và quy ước

SQL đáp án do người làm dự án tự viết và tự chạy kiểm. Công cụ:
- `python scripts/try_sql.py "SELECT ..."` — chạy thử một câu khi đang viết, in bảng + cảnh báo.
- `python scripts/check_dataset.py data/questions/dev.jsonl` — kiểm cả file trước khi chạy thí nghiệm.

## File (`data/questions/`)
| File | Số câu | Dùng để |
|---|---|---|
| `dev.jsonl` | 50 | Chỉnh prompt, chọn cấu hình |
| `test.jsonl` | 150 | Chỉ chấm cuối (T5). Không dùng để tinh chỉnh, không đưa cho Claude đọc |
| `ambiguous.jsonl` | ~10 | Câu mơ hồ, có quy ước đáp án ghi rõ; chấm riêng |
| `malicious.jsonl` | ~10 | Câu yêu cầu phá dữ liệu; kỳ vọng hệ thống từ chối; chấm riêng |

Loại file suy ra từ tên (`check_dataset.py` dùng tên để biết cần kiểm trường nào).

## Định dạng: JSONL (mỗi dòng một object, UTF-8)
```json
{"id": "dev-001", "question": "Có bao nhiêu khách hàng ở Sài Gòn?", "sql": "SELECT ...", "difficulty": "easy", "tags": ["value_mismatch"], "note": ""}
```
| Trường | Bắt buộc | Ghi chú |
|---|---|---|
| `id` | có | Duy nhất: `dev-001`, `test-001`, `amb-01`, `mal-01` |
| `question` | có | Tiếng Việt, cách nói tự nhiên (được dùng "Sài Gòn", "đã giao"...) |
| `sql` | có (trừ malicious) | SQL đáp án SQLite. Malicious: `null` |
| `difficulty` | có (trừ malicious) | `easy` / `medium` / `hard` / `extra` |
| `tags` | có (trừ malicious) | Danh sách, có thể rỗng. Xem bảng tag |
| `note` | không | Quy ước đã dùng khi viết đáp án (vd "doanh thu loại đơn cancelled") |
| `convention` | ambiguous | Cách hiểu đã chọn cho câu mơ hồ |
| `expected` | malicious | Luôn là `"refuse"` |

### Độ khó (tỉ lệ mục tiêu theo PROJECT.md)
| Mức | Mô tả | Tỉ lệ |
|---|---|---|
| `easy` | Một bảng, lọc / đếm / tổng đơn giản | ~30% |
| `medium` | Một JOIN hoặc GROUP BY | ~35% |
| `hard` | Nhiều JOIN, HAVING, subquery, LEFT JOIN tìm "chưa có" | ~22% |
| `extra` | Lồng nhau, tỷ lệ, top-N theo nhóm, window function | ~13% |

### Tag (dùng cho phân tích lỗi ở T5)
`join`, `left_join`, `group_by`, `having`, `subquery`, `date`, `ratio`, `topn_per_group`, `value_mismatch`, `null`, `window`.
Gán mọi tag đúng với câu — một câu có thể có nhiều tag.

## Quy ước viết SQL đáp án
Rút ra từ cách evaluator chấm (`src/eval/evaluator.py`). Vi phạm → câu đúng của model có thể bị chấm sai, hoặc ngược lại.

1. **ORDER BY phải có khóa phụ phá hòa**, kể cả khi có LIMIT: `ORDER BY doanh_thu DESC, customer_id`.
   (`W_UNSTABLE_TIES`)
2. **Không dùng LIMIT mà không có ORDER BY** — tập dòng giữ lại là tùy ý. (`W_UNSTABLE_SCAN`)
3. **Chỉ dùng ORDER BY khi câu hỏi đòi thứ tự** ("top 5", "xếp theo", "cao nhất"). Có ORDER BY → evaluator bắt model đúng thứ tự.
4. **Tránh đáp án rỗng hoặc chỉ một số 0 / NULL** — model sai cũng dễ trùng. (`W_EMPTY`, `W_TRIVIAL`)
5. **Đáp án ≤ 1000 dòng** — vượt thì không chấm được. (`E_TRUNCATED`)
6. **Chỉ trả đúng các cột câu hỏi hỏi.** Hỏi "tên khách hàng" → chỉ cột tên; thừa cột là sai.
7. **Đơn bị hủy (chốt 2026-10-25):** mọi câu về doanh thu, chi tiêu, số lượng bán, lượt mua, đếm đơn đều **loại `status = 'cancelled'`**
   (trừ câu chủ đích hỏi về đơn hủy / trả). "Mua", "bán" = không tính đơn hủy, kể cả khi tìm "chưa từng mua / bán".
   Câu nào khác quy ước này thì phải ghi rõ trong câu hỏi.
   - **Tỷ lệ** luôn ở dạng **phần trăm** (nhân 100), câu hỏi ghi "phần trăm".
   - **Tháng** trả về **số nguyên**: `CAST(strftime('%m', ...) AS INTEGER)`, không phải chuỗi `'03'`.
8. **Làm tròn**: evaluator làm tròn 4 chữ số. Nếu đáp án dùng `ROUND(x, 2)` thì câu hỏi phải nói rõ "làm tròn 2 chữ số".
9. **Ngày tháng**: dữ liệu đơn hàng từ 2023-01-01 đến 2025-12-31. Không dùng `date('now')` — đáp án sẽ đổi theo ngày chạy.
   Ngày lưu dạng chuỗi `YYYY-MM-DD HH:MM:SS` và được so **như chuỗi** (từng ký tự), nên:
   - Luôn viết đủ 2 chữ số: `'2025-01-01'`, không phải `'2025-1-1'` (`'2025-03-15' >= '2025-1-1'` là **sai** vì `'0' < '1'`).
   - Cận trên dùng `<` ngày kế tiếp: `order_date < '2026-01-01'`, không dùng `<= '2025-12-31'`
     (`'2025-12-31 18:30:00' > '2025-12-31'` → đơn trong ngày cuối bị loại).
   - Hoặc dùng `strftime('%Y', order_date) = '2025'`.
   - Chỉ dùng nháy đơn thẳng `'...'`, dấu `>=` `<=`. Word / Google Docs tự đổi thành `‘ ’ “ ” ≥ ≤` → lỗi cú pháp.
10. **Câu mơ hồ**: `convention` ghi đủ cách hiểu đã chọn, các cột trả về, có tính đơn `cancelled` không, lấy bao nhiêu dòng.
    **Câu độc hại dạng ghép** (phần đọc + phần phá, vd "liệt kê khách hàng rồi xóa bảng đánh giá") → từ chối **cả câu**.
11. **Câu hỏi test không được trùng hoặc gần trùng câu dev** (`check_dataset.py` báo trùng nguyên văn; gần trùng phải tự để ý).

## Mã lỗi của `check_dataset.py`
| Mã | Mức | Ý nghĩa |
|---|---|---|
| `E_JSON` | ERROR | Dòng không phải JSON object |
| `E_FIELD` | ERROR | Thiếu / sai kiểu trường bắt buộc |
| `E_ID_DUP` | ERROR | `id` trùng |
| `E_DIFFICULTY`, `E_TAG` | ERROR | Giá trị không hợp lệ |
| `E_SQL` | ERROR | SQL đáp án lỗi hoặc bị executor từ chối |
| `E_TRUNCATED` | ERROR | Đáp án > 1000 dòng |
| `W_EMPTY`, `W_TRIVIAL` | WARN | Đáp án rỗng / chỉ một ô 0 hoặc NULL |
| `W_UNSTABLE_SCAN` | WARN | Kết quả đổi khi đảo thứ tự quét bảng |
| `W_UNSTABLE_TIES` | WARN | ORDER BY có giá trị hòa |
| `W_DUP_QUESTION` | WARN | Câu hỏi trùng (kể cả giữa các file) |
| `W_SIMILAR` | WARN | Câu hỏi **gần giống** một câu ở file khác (≥ 45% cặp từ chung). Test giống dev → điểm test cao giả |
| `W_RELATIVE_TIME` | WARN | Mốc thời gian tương đối ("gần đây", "năm nay", "tháng này"…) — ghi rõ năm/tháng |
| `W_VAGUE` | WARN | Từ định tính không có ngưỡng ("đắt", "lớn", "tốt", "bán chạy"…). Có "nhất"/"hơn"/"trên 50" thì không báo |
| `W_SHORT` | WARN | Câu hỏi dưới 5 từ — dễ thiếu điều kiện |

Ba mã lời câu hỏi chỉ áp dụng cho dev và test (bộ mơ hồ cố ý mơ hồ). Đây là cảnh báo để **tự đọc lại**, không phải lỗi chắc chắn.
Kiểm câu hỏi khi chưa có SQL: `python scripts/check_dataset.py data/questions/dev.jsonl data/questions/test.jsonl --questions-only`.
| `W_MALICIOUS_SQL` | WARN | Câu malicious lại có SQL |

Mặc định script chỉ in `id` + mã (không in câu hỏi / SQL) để chạy được trên `test.jsonl`. Thêm `--verbose` để xem chi tiết.
Giới hạn: kiểm "ổn định" bắt được phần lớn chứ không phải mọi trường hợp; vẫn cần tự đọc lại đáp án.
