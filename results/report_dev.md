# Báo cáo split `dev`


## Lượt chạy được dùng

| Model | Cấu hình | run_id | prompt_hash | pool_hash |
|---|---|---|---|---|
| haiku | C0 | dev_C0_haiku_20261030-220242 | ac7c11feaec7 | - |
| haiku | C1 | dev_C1_haiku_20261030-220400 | ac7c11feaec7 | - |
| haiku | C2 | dev_C2_haiku_20261030-220519 | ac7c11feaec7 | - |
| haiku | C3 | dev_C3_haiku_20261030-231556 | 1ca9c19a74a1 | 1fb78f8fabfc |
| haiku | C4 | dev_C4_haiku_20261030-231800 | 1ca9c19a74a1 | 1fb78f8fabfc |
| sonnet | C0 | dev_C0_sonnet_20261030-125113 | 4dd66cbd6ccc | - |
| sonnet | C1 | dev_C1_sonnet_20261030-125248 | 4dd66cbd6ccc | - |
| sonnet | C2 | dev_C2_sonnet_20261030-125423 | 4dd66cbd6ccc | - |

⚠️ Các lượt chạy dùng 3 prompt khác nhau — so sánh giữa chúng không công bằng.

## Accuracy

| Model | Cấu hình | Câu | Lặp | Accuracy % | CI 95% | Chạy được % | Lỗi API | $/câu | Trễ s |
|---|---|---|---|---|---|---|---|---|---|
| haiku | C0 | 50 | 1 | 78.0 | 66.0–88.0 | 100.0 | 0 | 0.00010 | 1.47 |
| haiku | C1 | 50 | 1 | 88.0 | 78.0–96.0 | 100.0 | 0 | 0.00012 | 1.52 |
| haiku | C2 | 50 | 1 | 88.0 | 78.0–96.0 | 100.0 | 0 | 0.00020 | 2.50 |
| haiku | C3 | 50 | 1 | 92.0 | 84.0–98.0 | 100.0 | 0 | 0.00024 | 2.41 |
| haiku | C4 | 50 | 1 | 90.0 | 80.0–98.0 | 98.0 | 0 | 0.00014 | 2.46 |
| sonnet | C0 | 50 | 1 | 78.0 | 66.0–88.0 | 100.0 | 0 | 0.00183 | 1.81 |
| sonnet | C1 | 50 | 1 | 78.0 | 66.0–88.0 | 100.0 | 0 | 0.00238 | 1.83 |
| sonnet | C2 | 50 | 1 | 78.0 | 66.0–88.0 | 100.0 | 0 | 0.00374 | 3.21 |

## So sánh định trước

McNemar trên đúng theo đa số lần lặp; Holm cho 4 so sánh liên tiếp của Haiku (m = 4 cố định); 3 so sánh phụ dùng p không hiệu chỉnh. Kết luận chỉ khi p < 0.05, CI không chứa 0 và hai phép thử cùng chiều.

| So sánh | Chênh lệch (điểm %) | CI 95% | b (A sai, B đúng) | c (A đúng, B sai) | p | p Holm | Kết luận |
|---|---|---|---|---|---|---|---|
| haiku C0 → haiku C1 | +10.0 | -2.0…+22.0 | 7 | 2 | 0.180 | 0.719 | chưa đủ bằng chứng |
| haiku C1 → haiku C2 | +0.0 | -8.0…+8.0 | 2 | 2 | 1.000 | 1.000 | chưa đủ bằng chứng |
| haiku C2 → haiku C3 | +4.0 | -4.0…+12.0 | 3 | 1 | 0.625 | 1.000 | chưa đủ bằng chứng |
| haiku C3 → haiku C4 | -2.0 | -10.0…+4.0 | 1 | 2 | 1.000 | 1.000 | chưa đủ bằng chứng |
| haiku C0 → haiku C3 | +14.0 | +2.0…+26.0 | 9 | 2 | 0.065 | không hiệu chỉnh | chưa đủ bằng chứng |
| haiku C0 → sonnet C0 | +0.0 | -14.0…+14.0 | 7 | 7 | 1.000 | không hiệu chỉnh | chưa đủ bằng chứng |

## Theo độ khó

| Nhóm | Câu | haiku C0 | haiku C1 | haiku C2 | haiku C3 | haiku C4 | sonnet C0 | sonnet C1 | sonnet C2 |
|---|---|---|---|---|---|---|---|---|---|
| easy | 15 | 66.7 | 100.0 | 100.0 | 100.0 | 100.0 | 93.3 | 100.0 | 100.0 |
| medium | 20 | 75.0 | 85.0 | 90.0 | 95.0 | 90.0 | 70.0 | 75.0 | 70.0 |
| hard | 9 | 100.0 | 100.0 | 88.9 | 88.9 | 77.8 | 88.9 | 77.8 | 77.8 |
| extra | 6 | 83.3 | 50.0 | 50.0 | 66.7 | 83.3 | 50.0 | 33.3 | 50.0 |

## Theo tag

| Nhóm | Câu | haiku C0 | haiku C1 | haiku C2 | haiku C3 | haiku C4 | sonnet C0 | sonnet C1 | sonnet C2 |
|---|---|---|---|---|---|---|---|---|---|
| date | 13 | 53.8 | 76.9 | 76.9 | 84.6 | 76.9 | 69.2 | 76.9 | 69.2 |
| group_by | 26 | 92.3 | 84.6 | 84.6 | 92.3 | 88.5 | 76.9 | 69.2 | 69.2 |
| having | 5 | 100.0 | 100.0 | 80.0 | 100.0 | 100.0 | 60.0 | 40.0 | 40.0 |
| join | 21 | 85.7 | 95.2 | 85.7 | 90.5 | 90.5 | 61.9 | 61.9 | 61.9 |
| left_join | 3 | 100.0 | 100.0 | 100.0 | 100.0 | 66.7 | 100.0 | 100.0 | 100.0 |
| null | 2 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| ratio | 2 | 100.0 | 0.0 | 50.0 | 50.0 | 100.0 | 100.0 | 50.0 | 100.0 |
| subquery | 5 | 100.0 | 80.0 | 100.0 | 80.0 | 100.0 | 100.0 | 60.0 | 80.0 |
| topn_per_group | 3 | 100.0 | 100.0 | 66.7 | 100.0 | 100.0 | 0.0 | 0.0 | 0.0 |
| value_mismatch | 11 | 36.4 | 90.9 | 90.9 | 100.0 | 100.0 | 72.7 | 90.9 | 90.9 |
| window | 5 | 80.0 | 60.0 | 60.0 | 60.0 | 80.0 | 40.0 | 20.0 | 40.0 |

## Lý do (số bản ghi)

| Lý do | haiku C0 | haiku C1 | haiku C2 | haiku C3 | haiku C4 | sonnet C0 | sonnet C1 | sonnet C2 |
|---|---|---|---|---|---|---|---|---|
| column_count | 3 | 3 | 4 | 1 | 1 | 4 | 5 | 6 |
| match | 39 | 44 | 44 | 46 | 45 | 39 | 39 | 39 |
| mismatch | 5 | 2 | 1 | 1 | 1 | 4 | 4 | 3 |
| refused | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| row_count | 3 | 1 | 1 | 2 | 2 | 3 | 2 | 2 |

## C4 — vòng sửa (đếm theo bản ghi: 3 lần lặp → mỗi câu tính 3 lần)

| Model | Bản ghi kích hoạt | Lần gọi sửa | Sửa được | Làm hỏng |
|---|---|---|---|---|
| haiku | 0 | 0 | 0 | 0 |
