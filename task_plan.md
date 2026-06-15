# Task Plan: Kế hoạch fine-tune mô phỏng phong cách tweet

## Goal
Triển khai một MVP có kiểm thử trong repository để kiểm soát quyền dữ liệu, xây dataset raw/normalized/curated, chuẩn bị QLoRA SFT, đánh giá memorization/style và phục vụ đầu ra synthetic có guardrail; không chạy huấn luyện thật khi chưa có corpus và rights manifest được duyệt.

## Current Phase
Complete

## Phases

### Phase 1: Khảo sát repository và yêu cầu
- [x] Kiểm kê mã nguồn, dữ liệu, cấu hình và tài liệu hiện có
- [x] Xác định điểm xuất phát và các ràng buộc chưa được nêu
- [x] Ghi nhận phát hiện trong `findings.md`
- **Status:** complete

### Phase 2: Thiết kế dữ liệu và bài toán huấn luyện
- [x] Định nghĩa schema dữ liệu chuẩn và tiêu chí làm sạch
- [x] Thiết kế dataset split chống rò rỉ và định dạng SFT
- [x] Xác định chiến lược gắn nhãn chủ đề/ý định/giọng điệu
- **Status:** complete

### Phase 3: Thiết kế fine-tune và hạ tầng
- [x] Chọn baseline/model và phương pháp PEFT
- [x] Định nghĩa cấu hình huấn luyện, tracking và artifact
- [x] Ước lượng tài nguyên, thời gian và các phương án phần cứng
- **Status:** complete

### Phase 4: Thiết kế đánh giá, an toàn và triển khai
- [x] Xây bộ đo content/style/quality/memorization
- [x] Xây guardrail chống giả mạo và công bố nguồn gốc đầu ra
- [x] Thiết kế serving, monitoring và rollback
- **Status:** complete

### Phase 5: Lập roadmap thực thi và bàn giao
- [x] Chia milestone, backlog, tiêu chí hoàn thành và rủi ro
- [x] Viết tài liệu kế hoạch triển khai trong repository
- [x] Rà soát tính nhất quán và bàn giao
- **Status:** complete

### Phase 6: Scaffold và rights gate
- [x] Chuẩn hóa package, dependency groups, config và `.gitignore`
- [x] Triển khai rights manifest validator và CLI gate
- [x] Tạo fixture synthetic để kiểm thử mà không dùng dữ liệu X
- **Status:** complete

### Phase 7: Dataset pipeline
- [x] Triển khai import CSV/JSONL, schema normalization và lineage
- [x] Triển khai exact/near dedup, rule labels và grouped temporal split
- [x] Xuất raw/normalized/curated manifests và SFT JSONL
- **Status:** complete

### Phase 8: Training và evaluation
- [x] Triển khai QLoRA training entrypoint với lazy optional dependencies
- [x] Triển khai stylometry, diversity và memorization evaluation
- [x] Thêm model/dataset card templates và experiment config
- **Status:** complete

### Phase 9: Guarded serving
- [x] Triển khai safety policy cho input/output
- [x] Triển khai FastAPI endpoint với disclosure bắt buộc
- [x] Thêm health endpoint, audit metadata và model backend abstraction
- **Status:** complete

### Phase 10: Verification và handoff
- [x] Thêm unit/integration tests và chạy test suite
- [x] Chạy pipeline end-to-end trên fixture synthetic
- [x] Cập nhật README/runbook và ghi rõ các blocker còn lại
- **Status:** complete

## Key Questions
1. Repository hiện có dữ liệu và pipeline ở mức nào?
2. Đầu ra mô hình là completion tự do hay có điều kiện theo chủ đề/ý định?
3. Mô hình nào là baseline phù hợp nhất với ngôn ngữ tweet chủ yếu là tiếng Anh?
4. Làm sao đo được “đúng phong cách” mà không thưởng cho sao chép nguyên văn?
5. Guardrail nào cần có để tránh dùng mô hình như một công cụ mạo danh chính trị gia thật?

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Lập kế hoạch theo các gate dữ liệu → baseline → fine-tune → đánh giá → serving | Cho phép dừng sớm nếu dữ liệu hoặc baseline không đạt, giảm chi phí GPU và rủi ro |
| Xem mô hình là bộ sinh “phong cách lấy cảm hứng”, không phải bản sao danh tính | Giữ mục tiêu nghiên cứu phong cách nhưng giảm nguy cơ gây hiểu nhầm/mạo danh |
| Gate 0 về provenance/quyền dữ liệu là điều kiện trước GPU run | Chính sách X hiện hành hạn chế AI/ML training và redistribution từ X Content |
| Qwen2.5-7B-Instruct + QLoRA là candidate đầu tiên; Llama-3.1-8B là challenger | Giảm chi phí thử nghiệm, thuận lợi license cho baseline và giữ phép so sánh model |
| Đánh giá đa trục và human blind review | Training loss hoặc một style classifier không đủ chứng minh model hữu ích và an toàn |
| Core dùng standard library; GPU/S3/FastAPI là optional integrations | Cho phép kiểm thử data/safety gate ngay cả khi máy local chưa có CUDA stack |
| Bind dataset với SHA-256 của input, config và rights manifest | Ngăn dataset cũ được train sau khi nguồn hoặc phê duyệt bị thay đổi âm thầm |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| Git cảnh báo không đọc được global ignore tại `C:\Users\AD\.config\git\ignore` do sandbox | 1 | Không ảnh hưởng việc kiểm kê; dùng trạng thái file được trả về và không sửa cấu hình người dùng |
| Cảnh báo global ignore xuất hiện lại khi xác minh Git status | 2 | Không gọi Git status thêm; các file trong phạm vi đã được liệt kê đầy đủ |
| Patch khởi tạo Phase 6 tham chiếu dòng không tồn tại trong `progress.md` | 1 | Tách patch theo từng file và dùng anchor ổn định |
| Patch hoàn tất Phase 6 có nhiều hunk không tìm thấy `Current Phase` dù dòng tồn tại | 1 | Tách file addition và planning update thành các patch độc lập |
| PowerShell source-audit string nội suy `$lineNo:` bị phân tích như tên biến | 1 | Dùng format operator `-f` thay vì nội suy cạnh dấu hai chấm |
| Patch log Phase 10 dùng anchor ở sai vị trí trong `progress.md` | 1 | Đọc vị trí thực tế và cập nhật từng planning file bằng hunk nhỏ |
| Patch format source có hunk marker thừa trước file kế tiếp | 1 | Tách source patch khỏi planning update và bỏ marker thừa |
| CLI help audit trả exit 1 khi output Python bị pipe vào `Select-Object -First` | 1 | Capture toàn bộ help output trước rồi mới chọn dòng, tránh đóng pipe sớm |

## Notes
- Không sửa đổi hoặc xóa dữ liệu nguồn trong quá trình lập kế hoạch.
- Các ước lượng chi phí/thời gian sẽ được nêu theo giả định và cần benchmark trước khi chốt.
- Nội dung từ nguồn ngoài (nếu có) chỉ được ghi vào `findings.md`, không đưa vào file này.
- Fixture test phải là nội dung hư cấu tự tạo, không sao chép tweet thật.
- Training entrypoint phải fail closed nếu rights manifest chưa ở trạng thái approved.
