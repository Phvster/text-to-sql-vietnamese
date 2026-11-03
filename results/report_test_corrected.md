# Báo cáo split `test` — đáp án đã sửa

Chấm lại theo đáp án đã sửa (sai lệch trong docs/analysis_plan.md; test.jsonl sha d206f2df1e99). Loại 4 câu đổi đề so với b491734: test-080, test-096, test-128, test-150.

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
| haiku | C0 | 146 | 3 | 76.5 | 69.9–82.6 | 100.0 | 0 | 0.00009 | 1.36 |
| haiku | C1 | 146 | 3 | 84.0 | 78.5–89.0 | 99.8 | 0 | 0.00011 | 1.37 |
| haiku | C2 | 146 | 3 | 88.4 | 83.3–92.9 | 100.0 | 0 | 0.00013 | 2.57 |
| haiku | C3 | 146 | 3 | 89.5 | 84.5–93.8 | 98.6 | 0 | 0.00016 | 2.45 |
| haiku | C4 | 146 | 3 | 90.0 | 85.2–94.3 | 98.6 | 0 | 0.00016 | 2.37 |
| sonnet | C0 | 146 | 1 | 82.9 | 76.7–89.0 | 100.0 | 0 | 0.00167 | 1.78 |
| sonnet | C3 | 146 | 1 | 94.5 | 90.4–97.9 | 100.0 | 0 | 0.00381 | 6.70 |

## So sánh định trước

McNemar trên đúng theo đa số lần lặp; Holm cho 4 so sánh liên tiếp của Haiku (m = 4 cố định); 3 so sánh phụ dùng p không hiệu chỉnh. Kết luận chỉ khi p < 0.05, CI không chứa 0 và hai phép thử cùng chiều.

| So sánh | Chênh lệch (điểm %) | CI 95% | b (A sai, B đúng) | c (A đúng, B sai) | p | p Holm | Kết luận |
|---|---|---|---|---|---|---|---|
| haiku C0 → haiku C1 | +7.5 | +1.4…+13.9 | 19 | 11 | 0.200 | 0.601 | chưa đủ bằng chứng |
| haiku C1 → haiku C2 | +4.3 | +1.1…+8.0 | 12 | 3 | 0.035 | 0.141 | chưa đủ bằng chứng |
| haiku C2 → haiku C3 | +1.1 | -3.9…+6.2 | 10 | 7 | 0.629 | 1.000 | chưa đủ bằng chứng |
| haiku C3 → haiku C4 | +0.5 | -0.9…+1.8 | 0 | 1 | 1.000 | 1.000 | chưa đủ bằng chứng |
| haiku C0 → haiku C3 | +13.0 | +6.4…+19.9 | 26 | 6 | 0.001 | không hiệu chỉnh | B tốt hơn |
| haiku C0 → sonnet C0 | +6.4 | +2.7…+10.3 | 10 | 1 | 0.012 | không hiệu chỉnh | B tốt hơn |
| haiku C3 → sonnet C3 | +5.0 | +0.5…+9.8 | 9 | 3 | 0.146 | không hiệu chỉnh | chưa đủ bằng chứng |

## Theo độ khó

| Nhóm | Câu | haiku C0 | haiku C1 | haiku C2 | haiku C3 | haiku C4 | sonnet C0 | sonnet C3 |
|---|---|---|---|---|---|---|---|---|
| easy | 45 | 83.0 | 98.5 | 100.0 | 94.8 | 94.8 | 84.4 | 100.0 |
| medium | 53 | 76.7 | 86.2 | 88.1 | 94.3 | 95.0 | 81.1 | 94.3 |
| hard | 34 | 77.5 | 79.4 | 93.1 | 85.3 | 87.3 | 85.3 | 94.1 |
| extra | 14 | 52.4 | 40.5 | 40.5 | 64.3 | 61.9 | 78.6 | 78.6 |

## Theo tag

| Nhóm | Câu | haiku C0 | haiku C1 | haiku C2 | haiku C3 | haiku C4 | sonnet C0 | sonnet C3 |
|---|---|---|---|---|---|---|---|---|
| date | 30 | 75.6 | 67.8 | 72.2 | 82.2 | 81.1 | 86.7 | 86.7 |
| group_by | 71 | 73.7 | 80.3 | 86.9 | 89.2 | 89.7 | 83.1 | 94.4 |
| having | 19 | 82.5 | 100.0 | 100.0 | 89.5 | 91.2 | 89.5 | 100.0 |
| join | 62 | 79.0 | 81.7 | 88.7 | 89.8 | 91.4 | 87.1 | 96.8 |
| left_join | 4 | 75.0 | 75.0 | 75.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| null | 4 | 75.0 | 100.0 | 100.0 | 100.0 | 100.0 | 75.0 | 100.0 |
| ratio | 8 | 45.8 | 33.3 | 41.7 | 75.0 | 75.0 | 75.0 | 75.0 |
| subquery | 12 | 72.2 | 69.4 | 86.1 | 83.3 | 83.3 | 83.3 | 83.3 |
| topn_per_group | 2 | 83.3 | 16.7 | 33.3 | 66.7 | 66.7 | 100.0 | 100.0 |
| value_mismatch | 7 | 14.3 | 100.0 | 100.0 | 100.0 | 100.0 | 14.3 | 100.0 |
| window | 5 | 46.7 | 20.0 | 13.3 | 26.7 | 33.3 | 60.0 | 60.0 |

## Lý do (số bản ghi)

| Lý do | haiku C0 | haiku C1 | haiku C2 | haiku C3 | haiku C4 | sonnet C0 | sonnet C3 |
|---|---|---|---|---|---|---|---|
| column_count | 15 | 30 | 22 | 6 | 5 | 1 | 1 |
| match | 335 | 368 | 387 | 392 | 394 | 121 | 138 |
| mismatch | 46 | 29 | 23 | 24 | 25 | 12 | 5 |
| pred_error | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| pred_truncated | 5 | 3 | 3 | 3 | 3 | 1 | 1 |
| refused | 0 | 0 | 0 | 6 | 6 | 0 | 0 |
| row_count | 37 | 7 | 3 | 7 | 5 | 11 | 1 |

## C4 — vòng sửa (đếm theo bản ghi: 3 lần lặp → mỗi câu tính 3 lần)

| Model | Bản ghi kích hoạt | Lần gọi sửa | Sửa được | Làm hỏng |
|---|---|---|---|---|
| haiku | 6 | 6 | 2 | 0 |
