# Text-to-SQL tiếng Việt

## GUARDRAILS (bắt buộc)
- KHÔNG BAO GIỜ đọc, in, hay dùng data/questions/test.jsonl để chỉnh prompt/cấu hình. Chỉ dùng dev.jsonl. Test chỉ chạy ở T5 khi tôi yêu cầu rõ.
- Mọi SQL do model sinh PHẢI đi qua src/db/executor.py. Không gọi sqlite3 trực tiếp ở chỗ khác.
- Không tự sinh SQL đáp án cho dataset. Đáp án do tôi viết và kiểm.
- Không sửa evaluator/executor mà không chạy lại toàn bộ tests.
- Không đọc file .env.

## Dự án
Câu hỏi tiếng Việt → SQL (SQLite) → kết quả. So sánh 5 cấu hình C0–C4 trên Haiku 5.5 và Sonnet 5.5 (thinking tắt).
Chi tiết: docs/PROJECT.md. Tiến độ: docs/PROGRESS.md.

## Lệnh
- Test: `pytest -q`
- Sinh DB: `python scripts/generate_db.py --seed 42`
- Chạy pipeline (tốn tiền, chỉ dev): `python scripts/run_pipeline.py --config C1 --model haiku --split dev --limit 5`

## Style
Python 3.11, type hints, hàm nhỏ. Tôi đang học: giải thích ngắn lý do thiết kế khi viết code mới.