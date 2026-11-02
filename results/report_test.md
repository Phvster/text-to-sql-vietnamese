# Báo cáo split `test`


## Lượt chạy được dùng

| Model | Cấu hình | run_id | prompt_hash | pool_hash |
|---|---|---|---|---|
| haiku | C0 | test_C0_haiku_20261031-013612 | 1ca9c19a74a1 | - |
| haiku | C1 | test_C1_haiku_20261031-014639 | 1ca9c19a74a1 | - |
| haiku | C2 | test_C2_haiku_20261031-015714 | 1ca9c19a74a1 | - |
| haiku | C3 | test_C3_haiku_20261031-021644 | 1ca9c19a74a1 | 1fb78f8fabfc |
| haiku | C4 | test_C4_haiku_20261031-023517 | 1ca9c19a74a1 | 1fb78f8fabfc |
| sonnet | C0 | test_C0_sonnet_20261031-025320 | 1ca9c19a74a1 | - |
| sonnet | C3 | test_C3_sonnet_20261031-025753 | 1ca9c19a74a1 | 1fb78f8fabfc |

## Accuracy

| Model | Cấu hình | Câu | Lặp | Accuracy % | CI 95% | Chạy được % | Lỗi API | $/câu | Trễ s |
|---|---|---|---|---|---|---|---|---|---|
| haiku | C0 | 150 | 3 | 65.6 | 58.0–72.9 | 100.0 | 0 | 0.00009 | 1.37 |
| haiku | C1 | 150 | 3 | 73.8 | 67.1–80.2 | 99.8 | 0 | 0.00011 | 1.38 |
| haiku | C2 | 150 | 3 | 75.8 | 68.9–82.2 | 100.0 | 0 | 0.00013 | 2.57 |
| haiku | C3 | 150 | 3 | 76.0 | 69.3–82.4 | 98.7 | 0 | 0.00016 | 2.45 |
| haiku | C4 | 150 | 3 | 76.2 | 69.6–82.7 | 98.7 | 0 | 0.00016 | 2.37 |
| sonnet | C0 | 150 | 1 | 70.0 | 62.7–77.3 | 100.0 | 0 | 0.00168 | 1.79 |
| sonnet | C3 | 150 | 1 | 80.7 | 74.0–86.7 | 100.0 | 0 | 0.00380 | 6.65 |

## So sánh định trước

McNemar trên đúng theo đa số lần lặp; Holm cho 4 so sánh liên tiếp của Haiku (m = 4 cố định); 3 so sánh phụ dùng p không hiệu chỉnh. Kết luận chỉ khi p < 0.05, CI không chứa 0 và hai phép thử cùng chiều.

| So sánh | Chênh lệch (điểm %) | CI 95% | b (A sai, B đúng) | c (A đúng, B sai) | p | p Holm | Kết luận |
|---|---|---|---|---|---|---|---|
| haiku C0 → haiku C1 | +8.2 | +2.2…+14.4 | 19 | 10 | 0.136 | 0.544 | chưa đủ bằng chứng |
| haiku C1 → haiku C2 | +2.0 | -1.3…+5.3 | 10 | 4 | 0.180 | 0.544 | chưa đủ bằng chứng |
| haiku C2 → haiku C3 | +0.2 | -4.4…+4.7 | 8 | 7 | 1.000 | 1.000 | chưa đủ bằng chứng |
| haiku C3 → haiku C4 | +0.2 | -1.1…+1.6 | 0 | 1 | 1.000 | 1.000 | chưa đủ bằng chứng |
| haiku C0 → haiku C3 | +10.4 | +4.0…+17.1 | 23 | 7 | 0.005 | không hiệu chỉnh | B tốt hơn |
| haiku C0 → sonnet C0 | +4.4 | +1.3…+7.8 | 7 | 1 | 0.070 | không hiệu chỉnh | chưa đủ bằng chứng |
| haiku C3 → sonnet C3 | +4.7 | +0.7…+8.9 | 8 | 2 | 0.109 | không hiệu chỉnh | chưa đủ bằng chứng |

## Theo độ khó

| Nhóm | Câu | haiku C0 | haiku C1 | haiku C2 | haiku C3 | haiku C4 | sonnet C0 | sonnet C3 |
|---|---|---|---|---|---|---|---|---|
| easy | 45 | 83.0 | 98.5 | 100.0 | 94.8 | 94.8 | 84.4 | 100.0 |
| medium | 55 | 60.6 | 70.3 | 71.5 | 74.5 | 75.2 | 63.6 | 76.4 |
| hard | 35 | 56.2 | 61.9 | 66.7 | 62.9 | 63.8 | 60.0 | 68.6 |
| extra | 15 | 53.3 | 40.0 | 40.0 | 55.6 | 53.3 | 73.3 | 66.7 |

## Theo tag

| Nhóm | Câu | haiku C0 | haiku C1 | haiku C2 | haiku C3 | haiku C4 | sonnet C0 | sonnet C3 |
|---|---|---|---|---|---|---|---|---|
| date | 32 | 61.5 | 54.2 | 57.3 | 59.4 | 58.3 | 68.8 | 65.6 |
| group_by | 73 | 56.6 | 63.9 | 67.6 | 67.6 | 67.6 | 63.0 | 74.0 |
| having | 19 | 50.9 | 63.2 | 63.2 | 57.9 | 57.9 | 52.6 | 63.2 |
| join | 65 | 60.5 | 63.6 | 67.7 | 70.3 | 71.3 | 66.2 | 75.4 |
| left_join | 5 | 60.0 | 46.7 | 60.0 | 66.7 | 66.7 | 80.0 | 60.0 |
| null | 4 | 75.0 | 100.0 | 100.0 | 100.0 | 100.0 | 75.0 | 100.0 |
| ratio | 9 | 48.1 | 33.3 | 40.7 | 59.3 | 59.3 | 66.7 | 55.6 |
| subquery | 14 | 31.0 | 26.2 | 31.0 | 38.1 | 35.7 | 28.6 | 21.4 |
| topn_per_group | 2 | 83.3 | 16.7 | 33.3 | 66.7 | 66.7 | 100.0 | 100.0 |
| value_mismatch | 7 | 14.3 | 100.0 | 100.0 | 100.0 | 100.0 | 14.3 | 100.0 |
| window | 5 | 46.7 | 20.0 | 13.3 | 26.7 | 33.3 | 60.0 | 60.0 |

## Lý do (số bản ghi)

| Lý do | haiku C0 | haiku C1 | haiku C2 | haiku C3 | haiku C4 | sonnet C0 | sonnet C3 |
|---|---|---|---|---|---|---|---|
| column_count | 20 | 33 | 25 | 15 | 14 | 2 | 2 |
| match | 295 | 332 | 341 | 342 | 343 | 105 | 121 |
| mismatch | 80 | 65 | 63 | 62 | 64 | 26 | 20 |
| pred_error | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| pred_truncated | 5 | 3 | 3 | 3 | 3 | 1 | 1 |
| refused | 0 | 0 | 0 | 6 | 6 | 0 | 0 |
| row_count | 50 | 16 | 18 | 22 | 20 | 16 | 6 |

## C4 — vòng sửa (đếm theo bản ghi: 3 lần lặp → mỗi câu tính 3 lần)

| Model | Bản ghi kích hoạt | Lần gọi sửa | Sửa được | Làm hỏng |
|---|---|---|---|---|
| haiku | 6 | 6 | 2 | 0 |
