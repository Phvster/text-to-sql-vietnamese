# Schema CSDL bán hàng (`data/sales.db`)

SQLite, sinh bằng `python scripts/generate_db.py --seed 42`.
Tên bảng/cột tiếng Anh; câu hỏi người dùng tiếng Việt.

## Quy ước chung
- **Tiền**: VND, kiểu `INTEGER`. `unit_price` luôn là bội số của 1.000 → mọi phép tính tiền đều ra số nguyên, không sai số float.
- **Ngày giờ**: `TEXT` dạng ISO `YYYY-MM-DD HH:MM:SS` (dùng được `strftime`, `date()` của SQLite).
- **Khoảng thời gian đơn hàng**: 2023-01-01 → 2025-12-31.
- **Mã phân loại** (`status`, `segment`, `payment_method`, `gender`) lưu bằng mã tiếng Anh, không phải tiếng Việt.

## Bảng

### `categories` — danh mục sản phẩm (2 cấp)
| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| `category_id` | INTEGER PK | |
| `name` | TEXT NOT NULL | Tên danh mục tiếng Việt, ví dụ "Điện thoại", "Thời trang nữ" |
| `parent_id` | INTEGER NULL FK → `categories.category_id` | NULL = danh mục gốc |

### `customers` — khách hàng
| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| `customer_id` | INTEGER PK | |
| `full_name` | TEXT NOT NULL | Họ tên tiếng Việt |
| `email` | TEXT NOT NULL | |
| `phone` | TEXT NULL | ~5% NULL |
| `gender` | TEXT | `'M'` (nam) / `'F'` (nữ) |
| `birth_date` | TEXT NULL | `YYYY-MM-DD`, ~8% NULL |
| `city` | TEXT NOT NULL | Tỉnh/thành, tên chính thức (xem bảng ánh xạ) |
| `segment` | TEXT NOT NULL | `'retail'` / `'wholesale'` / `'vip'` |
| `created_at` | TEXT NOT NULL | Ngày đăng ký |

### `products` — sản phẩm
| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| `product_id` | INTEGER PK | |
| `name` | TEXT NOT NULL | |
| `category_id` | INTEGER NOT NULL FK → `categories` | Luôn là danh mục **con** |
| `brand` | TEXT NOT NULL | |
| `unit_price` | INTEGER NOT NULL | Giá niêm yết hiện tại |
| `cost_price` | INTEGER NOT NULL | Giá vốn (< `unit_price`) |
| `stock_quantity` | INTEGER NOT NULL | Tồn kho |
| `is_active` | INTEGER NOT NULL | 1 = đang bán, 0 = ngừng kinh doanh |
| `created_at` | TEXT NOT NULL | |

### `orders` — đơn hàng
| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| `order_id` | INTEGER PK | |
| `customer_id` | INTEGER NOT NULL FK → `customers` | |
| `order_date` | TEXT NOT NULL | |
| `status` | TEXT NOT NULL | `'pending'` / `'shipped'` / `'delivered'` / `'cancelled'` / `'returned'` |
| `payment_method` | TEXT NOT NULL | `'cod'` / `'bank_transfer'` / `'credit_card'` / `'e_wallet'` |
| `shipping_city` | TEXT NOT NULL | Nơi giao, thường trùng `customers.city` nhưng không luôn luôn |
| `total_amount` | INTEGER NOT NULL | Tổng tiền đơn (= tổng `line_total`, xem công thức) |

### `order_items` — chi tiết đơn
| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| `order_item_id` | INTEGER PK | |
| `order_id` | INTEGER NOT NULL FK → `orders` | |
| `product_id` | INTEGER NOT NULL FK → `products` | Một sản phẩm xuất hiện tối đa 1 lần mỗi đơn |
| `quantity` | INTEGER NOT NULL | ≥ 1 |
| `unit_price` | INTEGER NOT NULL | Giá **tại thời điểm mua** (có thể khác `products.unit_price`) |
| `discount_pct` | INTEGER NOT NULL | Phần trăm giảm giá ∈ {0, 5, 10, 15, 20} |

### `reviews` — đánh giá
| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| `review_id` | INTEGER PK | |
| `product_id` | INTEGER NOT NULL FK → `products` | |
| `customer_id` | INTEGER NOT NULL FK → `customers` | |
| `order_id` | INTEGER NOT NULL FK → `orders` | Chỉ đơn `'delivered'` mới có review |
| `rating` | INTEGER NOT NULL | 1–5 |
| `comment` | TEXT NULL | |
| `created_at` | TEXT NOT NULL | Sau `order_date` |

## Công thức
```
line_total          = quantity * unit_price * (100 - discount_pct) / 100   -- luôn nguyên
orders.total_amount = SUM(line_total) của các dòng order_items thuộc đơn đó
```
Không có cột `line_total`; doanh thu theo sản phẩm phải tự tính bằng công thức trên.
"Doanh thu" thông thường nên loại đơn `'cancelled'` (quy ước cụ thể ghi trong từng câu hỏi dataset).

## Ánh xạ cách nói → giá trị trong DB (giá trị lệch có chủ đích)
| Người dùng nói | Cột | Giá trị lưu |
|---|---|---|
| Sài Gòn, HCM, TP.HCM | `city`, `shipping_city` | `TP. Hồ Chí Minh` |
| Huế | `city`, `shipping_city` | `Thừa Thiên Huế` |
| Vũng Tàu | `city`, `shipping_city` | `Bà Rịa - Vũng Tàu` |
| chờ xử lý / đang giao / đã giao / bị hủy / trả hàng | `status` | `pending` / `shipped` / `delivered` / `cancelled` / `returned` |
| khách lẻ / khách sỉ / khách VIP | `segment` | `retail` / `wholesale` / `vip` |
| thanh toán khi nhận hàng / chuyển khoản / thẻ / ví điện tử | `payment_method` | `cod` / `bank_transfer` / `credit_card` / `e_wallet` |
| nam / nữ | `gender` | `M` / `F` |
