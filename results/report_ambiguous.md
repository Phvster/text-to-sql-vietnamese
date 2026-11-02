# Báo cáo split `ambiguous`


## Lượt chạy được dùng

| Model | Cấu hình | run_id | prompt_hash | pool_hash |
|---|---|---|---|---|
| haiku | C0 | ambiguous_C0_haiku_20261102-102144 | 1ca9c19a74a1 | - |
| haiku | C1 | ambiguous_C1_haiku_20261102-102203 | 1ca9c19a74a1 | - |
| haiku | C2 | ambiguous_C2_haiku_20261102-102217 | 1ca9c19a74a1 | - |
| haiku | C3 | ambiguous_C3_haiku_20261102-102242 | 1ca9c19a74a1 | 1fb78f8fabfc |
| haiku | C4 | ambiguous_C4_haiku_20261102-102304 | 1ca9c19a74a1 | 1fb78f8fabfc |

## Accuracy

| Model | Cấu hình | Câu | Lặp | Accuracy % | CI 95% | Chạy được % | Lỗi API | $/câu | Trễ s |
|---|---|---|---|---|---|---|---|---|---|
| haiku | C0 | 12 | 1 | 16.7 | 0.0–41.7 | 100.0 | 0 | 0.00011 | 1.54 |
| haiku | C1 | 12 | 1 | 16.7 | 0.0–41.7 | 100.0 | 0 | 0.00015 | 1.12 |
| haiku | C2 | 12 | 1 | 25.0 | 0.0–50.0 | 91.7 | 0 | 0.00025 | 2.05 |
| haiku | C3 | 12 | 1 | 16.7 | 0.0–41.7 | 50.0 | 0 | 0.00011 | 1.87 |
| haiku | C4 | 12 | 1 | 25.0 | 0.0–50.0 | 66.7 | 0 | 0.00011 | 2.06 |

## So sánh định trước

McNemar trên đúng theo đa số lần lặp; Holm cho 4 so sánh liên tiếp của Haiku (m = 4 cố định); 3 so sánh phụ dùng p không hiệu chỉnh. Kết luận chỉ khi p < 0.05, CI không chứa 0 và hai phép thử cùng chiều.

| So sánh | Chênh lệch (điểm %) | CI 95% | b (A sai, B đúng) | c (A đúng, B sai) | p | p Holm | Kết luận |
|---|---|---|---|---|---|---|---|
| haiku C0 → haiku C1 | +0.0 | +0.0…+0.0 | 0 | 0 | 1.000 | 1.000 | chưa đủ bằng chứng |
| haiku C1 → haiku C2 | +8.3 | +0.0…+25.0 | 1 | 0 | 1.000 | 1.000 | chưa đủ bằng chứng |
| haiku C2 → haiku C3 | -8.3 | -25.0…+0.0 | 0 | 1 | 1.000 | 1.000 | chưa đủ bằng chứng |
| haiku C3 → haiku C4 | +8.3 | +0.0…+25.0 | 1 | 0 | 1.000 | 1.000 | chưa đủ bằng chứng |
| haiku C0 → haiku C3 | +0.0 | +0.0…+0.0 | 0 | 0 | 1.000 | không hiệu chỉnh | chưa đủ bằng chứng |

## Theo độ khó

| Nhóm | Câu | haiku C0 | haiku C1 | haiku C2 | haiku C3 | haiku C4 |
|---|---|---|---|---|---|---|
| easy | 5 | 40.0 | 40.0 | 60.0 | 40.0 | 60.0 |
| medium | 3 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| hard | 4 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## Theo tag

| Nhóm | Câu | haiku C0 | haiku C1 | haiku C2 | haiku C3 | haiku C4 |
|---|---|---|---|---|---|---|
| date | 4 | 25.0 | 25.0 | 25.0 | 25.0 | 25.0 |
| group_by | 6 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| having | 2 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| join | 5 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| subquery | 2 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| value_mismatch | 1 | 0.0 | 0.0 | 100.0 | 0.0 | 100.0 |

## Lý do (số bản ghi)

| Lý do | haiku C0 | haiku C1 | haiku C2 | haiku C3 | haiku C4 |
|---|---|---|---|---|---|
| column_count | 6 | 6 | 6 | 3 | 4 |
| match | 2 | 2 | 3 | 2 | 3 |
| mismatch | 4 | 4 | 2 | 1 | 1 |
| refused | 0 | 0 | 1 | 6 | 4 |

## C4 — vòng sửa (đếm theo bản ghi: 3 lần lặp → mỗi câu tính 3 lần)

| Model | Bản ghi kích hoạt | Lần gọi sửa | Sửa được | Làm hỏng |
|---|---|---|---|---|
| haiku | 0 | 0 | 0 | 0 |
