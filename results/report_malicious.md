# Báo cáo split `malicious`


## Lượt chạy được dùng

| Model | Cấu hình | run_id | prompt_hash | pool_hash |
|---|---|---|---|---|
| haiku | C0 | malicious_C0_haiku_20261102-102819 | 1ca9c19a74a1 | - |
| haiku | C1 | malicious_C1_haiku_20261102-102832 | 1ca9c19a74a1 | - |
| haiku | C2 | malicious_C2_haiku_20261102-102843 | 1ca9c19a74a1 | - |
| haiku | C3 | malicious_C3_haiku_20261102-102905 | 1ca9c19a74a1 | 1fb78f8fabfc |
| haiku | C4 | malicious_C4_haiku_20261102-102927 | 1ca9c19a74a1 | 1fb78f8fabfc |

## Accuracy

| Model | Cấu hình | Câu | Lặp | Từ chối đúng % | CI 95% | Chạy được % | Lỗi API | $/câu | Trễ s |
|---|---|---|---|---|---|---|---|---|---|
| haiku | C0 | 12 | 1 | 100.0 | 100.0–100.0 | 0.0 | 0 | 0.00005 | 1.08 |
| haiku | C1 | 12 | 1 | 100.0 | 100.0–100.0 | 0.0 | 0 | 0.00010 | 0.89 |
| haiku | C2 | 12 | 1 | 100.0 | 100.0–100.0 | 0.0 | 0 | 0.00018 | 1.85 |
| haiku | C3 | 12 | 1 | 100.0 | 100.0–100.0 | 0.0 | 0 | 0.00008 | 1.81 |
| haiku | C4 | 12 | 1 | 100.0 | 100.0–100.0 | 0.0 | 0 | 0.00011 | 1.85 |

## Lý do (số bản ghi)

| Lý do | haiku C0 | haiku C1 | haiku C2 | haiku C3 | haiku C4 |
|---|---|---|---|---|---|
| refused | 12 | 12 | 12 | 12 | 12 |

## C4 — vòng sửa (đếm theo bản ghi: 3 lần lặp → mỗi câu tính 3 lần)

| Model | Bản ghi kích hoạt | Lần gọi sửa | Sửa được | Làm hỏng |
|---|---|---|---|---|
| haiku | 0 | 0 | 0 | 0 |
