# File này (dù rỗng) khiến pytest thêm thư mục gốc repo vào sys.path,
# nhờ đó test import được `src.db.executor` khi chạy `pytest -q`.
