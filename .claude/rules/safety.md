# Quy tắc an toàn SQL
- DB mở read-only (URI mode=ro).
- Chỉ chấp nhận đúng 1 câu lệnh, loại SELECT (cho phép WITH ... SELECT).
- Timeout 5 giây, tối đa 1000 dòng.
- Từ chối: INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/ATTACH/PRAGMA, nhiều câu lệnh nối bằng ";".