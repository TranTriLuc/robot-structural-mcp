# robot-structural-mcp

MCP server cho **Autodesk Robot Structural Analysis Professional**. Cho phép trợ lý AI
đọc mô hình và kết quả phân tích trực tiếp từ phiên Robot đang mở.

Khác với Revit, Robot **không cần add-in**: `Robot.Application` là COM server ngoài
process, nên chỉ cần cài Python là chạy. Không phải build DLL, không cần quyền admin.

## Yêu cầu

- Windows + Autodesk Robot Structural Analysis Professional (kiểm thử trên bản 2027)
- Python 3.11+ và [uv](https://docs.astral.sh/uv/)
- Robot **đang chạy** và **đã mở một mô hình** — server gắn vào instance đang chạy
  qua `GetActiveObject`, nó không tự khởi động Robot

## Cài đặt

```powershell
git clone https://github.com/<user>/robot-structural-mcp.git
cd robot-structural-mcp
.\install.ps1
```

`install.ps1` tạo virtualenv, cài phụ thuộc và ghi cấu hình MCP vào `~/.claude.json`.
Khởi động lại Claude sau khi cài.

Cấu hình thủ công nếu muốn:

```json
{
  "mcpServers": {
    "robot": {
      "type": "stdio",
      "command": "<repo>\\.venv\\Scripts\\python.exe",
      "args": ["-m", "robot_mcp"],
      "env": { "ROBOT_MCP_MAX_ITEMS": "200" }
    }
  }
}
```

## An toàn: mặc định chỉ-đọc

Server **không sửa mô hình** trừ khi bạn cho phép rõ ràng. Các tool ghi
(`robot_save`, `robot_open_model`) sẽ từ chối cho tới khi đặt:

```
ROBOT_MCP_ALLOW_WRITE=1
```

`robot_run_calculation` không nằm dưới cờ này vì nó không sửa mô hình, nhưng nó ghi đè
kết quả và chạy lâu, nên bắt buộc truyền `confirm=true`.

## Đơn vị — đọc kỹ phần này

RobotOM **luôn trả về đơn vị SI** (m, N, N·m, Pa, rad) bất kể giao diện Robot đang hiển
thị gì. Lấy thẳng số đó rồi coi như đơn vị trên màn hình là cách sai hệ số 1000 mà nhìn
vẫn hợp lý — nguy hiểm nhất trong tính toán kết cấu.

Vì vậy mọi kết quả trả về đều kèm khối `units` tường minh, và được quy đổi qua
`robot_mcp/units.py`. Mặc định: **kN, kNm, m, mm (chuyển vị), MPa**.

Đổi bằng tool `robot_units` hoặc biến môi trường `ROBOT_MCP_UNIT_FORCE`,
`ROBOT_MCP_UNIT_MOMENT`, `ROBOT_MCP_UNIT_LENGTH`, `ROBOT_MCP_UNIT_DISPLACEMENT`,
`ROBOT_MCP_UNIT_STRESS`.

## Tools

### Kết nối & dự án
| Tool | Việc |
|---|---|
| `robot_status` | Kiểm tra kết nối, tên/đường dẫn mô hình, số lượng đối tượng, kết quả đã có chưa |
| `robot_units` | Xem/đổi đơn vị đầu ra |
| `robot_save` | Lưu mô hình — **WRITE** |
| `robot_open_model` | Mở file .rtd khác — **WRITE** |

### Mô hình
| Tool | Việc |
|---|---|
| `robot_model_summary` | Tổng quan: số lượng, bounding box, danh sách tiết diện/vật liệu/gối |
| `robot_list_nodes` / `robot_get_node` | Nút và toạ độ |
| `robot_list_bars` / `robot_get_bar` | Thanh: nút đầu/cuối, chiều dài, tiết diện, vật liệu, release |
| `robot_list_panels` | Tấm |
| `robot_list_sections` / `robot_list_materials` | Nhãn tiết diện / vật liệu |
| `robot_list_supports` / `robot_list_releases` | Nhãn gối, release và đối tượng mang nhãn |

### Tải trọng
| Tool | Việc |
|---|---|
| `robot_list_load_cases` | Toàn bộ trường hợp tải và tổ hợp |
| `robot_list_combinations` | Chỉ tổ hợp, kèm case thành phần và hệ số |
| `robot_get_load_records` | Các bản ghi tải trong một case |

### Phân tích
| Tool | Việc |
|---|---|
| `robot_calculation_status` | Kết quả đã sẵn sàng chưa, trạng thái lần tính cuối |
| `robot_run_calculation` | Chạy phân tích (cần `confirm=true`) |

### Kết quả
| Tool | Việc |
|---|---|
| `robot_get_bar_forces` | Nội lực dọc thanh (FX/FY/FZ, MX/MY/MZ) theo vị trí tương đối 0–1 |
| `robot_get_bar_extreme_forces` | Bao nội lực min/max từng thành phần, kèm vị trí xảy ra |
| `robot_get_node_displacements` | Chuyển vị và góc xoay |
| `robot_get_node_reactions` | Phản lực gối — đầu vào cho thiết kế móng |

### Phát triển
| Tool | Việc |
|---|---|
| `robot_inspect` | Duyệt chỉ-đọc cây đối tượng RobotOM để tìm API chưa được bọc |

## Chọn đối tượng

Các tool nhận `selection` theo **cú pháp gốc của Robot**: `"1 3 5to9"`, `"all"`,
`"1to100by2"`. Bỏ trống thì lấy tất cả. Nhờ vậy truy vấn bám sát thói quen dùng Robot
thay vì phải liệt kê số hiệu.

## Phân trang

Mô hình vài chục nghìn phần tử sẽ làm vỡ context nếu đọc hết một lần. Mọi tool liệt kê
đều có `limit`/`offset` và bị chặn trên bởi `ROBOT_MCP_MAX_ITEMS` (mặc định 200).
Kết quả trả về luôn có cờ `truncated`.

## Ghi chú thiết kế

- **Một thread STA duy nhất.** Robot chỉ trả lời trên thread đã khởi tạo COM apartment,
  còn MCP runtime gọi tool trên thread bất kỳ. Toàn bộ lời gọi được dồn qua `_Worker`
  trong `com.py`.
- **Hằng số lấy từ type library**, không viết theo trí nhớ. `I_OT_BAR=1`,
  `I_LT_BAR_SECTION=3`… được đọc trực tiếp từ `robotom.tlb` bằng `makepy`. Sai một hằng
  số ở đây là số liệu sai âm thầm.
- **Kết quả kiểm tra trước khi đọc.** Mọi tool kết quả kiểm `Results.Available` trước,
  nếu chưa tính thì báo lỗi rõ ràng thay vì trả số cũ.
- **Tắt cửa sổ tiến trình** trước khi `Calculate()` — hộp thoại modal của Robot sẽ chặn
  toàn bộ COM nếu để bật.

## Lộ trình

Giai đoạn 2 (cầu nối thiết kế): `export_bar_forces_table`, `get_design_envelope`,
`export_reactions_table`, `get_required_reinforcement`, `get_steel_design_results`.

Giai đoạn 3 (dựng mô hình): tạo/sửa nút, thanh, tấm, gối, tải, tổ hợp.

## Giấy phép

MIT
