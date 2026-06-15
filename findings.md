# Findings & Decisions

## Requirements
- Giữ nguyên kho tweet hiện có làm nguồn dữ liệu gốc.
- Biến dữ liệu thành tập huấn luyện cho mô hình mã nguồn mở cỡ khoảng 7–8B.
- Mục tiêu là sinh văn bản mang các đặc điểm hành văn tương tự, không chỉ học nội dung tweet.
- Cần một kế hoạch triển khai end-to-end, có thể chuyển thành backlog kỹ thuật.

## Research Findings
- Repository hiện là một pipeline ETL mẫu cho tài khoản `@elonmusk`, chưa phải Donald Trump.
- README mô tả luồng Twitter API → Python ETL → Airflow trên EC2 → S3, nhưng phần “Future Enhancements” cho biết upload S3 chưa hoàn thiện.
- Phạm vi lấy dữ liệu được mô tả là tối đa 200 tweet gần nhất qua Twitter API v1.1; quy mô này không đủ để huấn luyện phong cách ổn định và không đại diện cho toàn bộ các giai đoạn phát ngôn.
- Schema README hiện chỉ có `user`, `text`, `favorite_count`, `retweet_count`, `created_at`; còn thiếu `tweet_id`, quan hệ reply/quote/thread, URL/media, language, source, thời điểm ingest và provenance cần cho dedup/split/audit.
- Repo hiện chưa có dữ liệu tweet được commit, dependency lockfile, test, validation, training/evaluation code hoặc MLOps serving.
- `twitter_etl.py` chỉ gọi một trang `user_timeline(count=200)`, không pagination/checkpoint/incremental load; ghi `refined_tweets.csv` cục bộ và import `s3fs` nhưng không dùng.
- Thứ tự biến credential trong `OAuthHandler`/`set_access_token` có vẻ bị đảo so với tên biến; mọi secret để chuỗi rỗng trong mã nguồn thay vì được inject qua secret manager.
- ETL chỉ lọc retweet, chưa xử lý reply/quote/thread, URL/media, HTML entity, deleted post, duplicate hoặc ngôn ngữ.
- DAG dùng import Airflow cũ và lịch `timedelta(days=1)`; chưa có idempotency, data-quality gate hay task tách raw/normalized/curated.
- Git chỉ có commit khởi tạo; ba file kế hoạch là thay đổi chưa track duy nhất trong phiên làm việc này.
- Tài liệu X hiện hành nêu rõ việc dùng dữ liệu X để huấn luyện AI/ML là bị cấm (ngoại lệ được nêu là Grok); vì vậy nguồn và giấy phép của kho tweet là một **go/no-go gate**, không thể mặc định lấy lại bằng API hoặc scraping để fine-tune.
- Chính sách X cũng hạn chế phân phối nội dung hydrated, thường chỉ cho phép phân phối ID trong giới hạn; dataset text và model artifact không được public trước khi legal review xác nhận quyền sử dụng/phân phối.
- X API v2 có endpoint user posts và timeline được giới hạn đến các bài gần nhất tùy endpoint/tier; pipeline v1.1 trong repo không phải nền tảng thích hợp cho việc dựng một corpus lịch sử đầy đủ.
- Hugging Face TRL `SFTTrainer` hỗ trợ prompt-completion/conversational dataset, `assistant_only_loss` và tích hợp PEFT/QLoRA; đây là baseline triển khai phù hợp cho thí nghiệm 7–8B.
- `Qwen/Qwen2.5-7B-Instruct` có 7.61B tham số, model card nêu context 131,072 và giấy phép Apache-2.0; với tweet ngắn chỉ cần giới hạn sequence nhỏ để tiết kiệm compute.
- `meta-llama/Llama-3.1-8B-Instruct` dùng giấy phép cộng đồng riêng của Meta, do đó cần review nghĩa vụ license/attribution trước khi phân phối adapter hoặc dịch vụ.
- QLoRA huấn luyện adapter qua base model lượng tử hóa 4-bit, là cơ sở kỹ thuật để thử nghiệm model 7–8B trên một GPU 24 GB; vẫn phải benchmark OOM/throughput với sequence length và packing thực tế.
- Nghiên cứu về memorization cho thấy sao chép tăng khi mẫu bị lặp và khi prompt chứa nhiều context trùng train; dedup và kiểm thử prefix-completion phải là quality gate chứ không chỉ đo sau cùng.
- MAUVE có thể đo khoảng cách phân phối giữa văn bản sinh và văn bản thật, nhưng cần kết hợp stylometry, content adherence và đánh giá mù của con người; không dùng một metric đơn lẻ làm tiêu chí chọn model.
- Llama 3.1 8B có 128K context theo model card nhưng bị gated access và dùng Llama 3.1 Community License; context dài không đem lại lợi ích đáng kể cho mục tiêu tweet ngắn.

## Implementation Findings
- Runtime local là Python 3.11.9.
- Có sẵn `pandas`, `fastapi`, `pydantic` và `transformers`; chưa có `torch`, `datasets`, `trl`, `peft`, `bitsandbytes`, `mlflow` hoặc `pytest`.
- Core pipeline và tests cần chạy được bằng standard library; training/serving dependencies được tách thành optional extras và import lazily.
- `.gitignore` hiện chặn toàn bộ `*.json`, `*.csv`, `*.parquet`; cần thu hẹp để vẫn commit được config/fixture synthetic nhưng không commit corpus và model artifacts.
- Không có `AGENTS.md` bổ sung trong repository.
- Rights CLI đã cho phép manifest synthetic approved và từ chối manifest draft với exit code 2; gate hoạt động fail-closed như thiết kế.
- Fixture gồm nội dung hư cấu tự tạo, có exact duplicate, near duplicate, retweet, link-only và thread để kiểm thử các nhánh pipeline.
- Pipeline fixture đã build thành công: 16 source → 16 normalized → 13 curated, loại 1 retweet, 1 link-only và 1 exact duplicate.
- Grouped temporal split tạo 10 train, 1 validation, 2 test; hai record cùng thread nằm chung test, không có conversation/near-duplicate leakage.
- Manifest chứa input/config hash, rights version, dataset ID, split counts và SHA-256 của từng artifact; output directory phải chưa tồn tại để tránh ghi đè.
- Training preflight qua rights và synthetic quality approval rồi dừng đúng tại optional dependency gate vì local chưa có `torch/datasets/trl/peft/bitsandbytes`; không có GPU run ngoài ý muốn.
- Automatic evaluation trên held-out fixture đạt style distance 0, distinct-2/3 bằng 1 và không có train overlap; control case sao chép một train target bị phát hiện exact match và flagged.
- Quality approval phải khớp `dataset_id`, có reviewer/timestamp, label error rate ≤5% và sample size tối thiểu là số nhỏ hơn giữa toàn corpus và `max(500, 10% corpus)`.
- Guarded generator cho phép prompt an toàn với disclosure, chặn impersonation ở input, chặn identity claim ở output và chặn output exact/near-overlap với train corpus.
- FastAPI contract đã được kiểm tra: thiếu API key trả 401, request hợp lệ trả 200 kèm `synthetic=true`, prompt mạo danh trả 422; health/OpenAPI routes được tạo.
- Production backend gọi private OpenAI-compatible vLLM endpoint; deterministic stub chỉ bật khi được truyền trực tiếp hoặc `STYLE_ALLOW_STUB=1`.
- Test suite hiện có 16 tests và đã pass toàn bộ; `compileall` cũng pass cho `src`, `tests` và `dags`.
- Source audit tìm thấy 33 Python files, không có trailing whitespace; 4 dòng vượt 100 ký tự đã được format lại.
- Private S3 publisher đã được thêm: từ chối prefix không rỗng, yêu cầu AES256 server-side encryption và upload `manifest.json` cuối cùng; test dùng fake client nên không ghi dữ liệu ra AWS.
- Test suite tăng lên 19 tests và vẫn pass; source audit sau bổ sung S3 có 35 Python files, 0 trailing whitespace và 1 dòng dài đã được format lại.
- Dataset identity và training/S3 gates hiện bind cả rights manifest version lẫn SHA-256; thay đổi nội dung legal manifest mà tái dùng version cũ vẫn làm gate thất bại.
- Sau khi bổ sung rights hash và input logical name vào lineage, synthetic dataset ID mới là `6e7258ba4ada5d2d69ed`; 19 tests và compileall vẫn pass.
- Input coverage hiện bao gồm CSV, JSON wrapper và JSONL; test xác nhận `text_raw` giữ nguyên capitalization/punctuation trong khi `text_train` thay URL/mention theo config.
- Rights-lineage tamper test xác nhận thay đổi nội dung rights manifest sau dataset build làm training gate thất bại dù version string không đổi.
- Test suite hiện có 22 tests, tất cả pass; compileall tiếp tục pass.

## Remaining External Gates
- Chưa có corpus thật trong repository hoặc đường dẫn được cung cấp; chỉ fixture hư cấu được build.
- Rights manifest thật vẫn ở trạng thái chưa tồn tại/chưa duyệt; code sẽ từ chối dataset build và training cho tới khi có approval hợp lệ.
- Máy local chưa có `torch`, `datasets`, `trl`, `peft`, `bitsandbytes`, `mlflow` và không xác nhận CUDA; QLoRA entrypoint đã được kiểm tra đến dependency gate nhưng chưa chạy GPU.
- Chưa có AWS credential/bucket nên S3 được kiểm thử bằng fake client, không có external write.
- Human blind review và red-team trên generation thật chỉ thực hiện được sau khi có candidate model.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Giữ một lớp dữ liệu raw bất biến, tạo các lớp normalized/curated riêng | Bảo toàn khả năng truy vết và tái tạo dataset |
| Ưu tiên LoRA/QLoRA trước full fine-tuning | Phù hợp giai đoạn thử nghiệm, chi phí thấp hơn và dễ so sánh nhiều cấu hình |
| Chọn Qwen2.5-7B-Instruct làm baseline đầu tiên, Llama-3.1-8B-Instruct làm challenger tùy license access | Qwen có Apache-2.0 và hỗ trợ chat template chuẩn; hai model có kích thước tương đương để A/B công bằng |
| Train theo prompt → assistant completion, chỉ tính loss trên phần assistant | Tách điều kiện nội dung khỏi phong cách và tránh mô hình học lặp system/user prompt |
| Không ingest mới từ X API hoặc scraping cho mục đích ML nếu chưa có chấp thuận bằng văn bản | Chính sách X hiện hành liệt kê AI/ML training từ X data là restricted/prohibited |
| Dùng kiểm thử prefix-completion và nearest-neighbor similarity trước khi phát hành | Dedup chỉ giảm rủi ro đầu vào; cần đo khả năng adapter tái tạo nguyên văn ở đầu ra |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Chưa biết cấu trúc và chất lượng dữ liệu thực tế | Kiểm kê repository và lấy mẫu dữ liệu ở Phase 1 |
| README và console PowerShell hiển thị một số ký tự Unicode bị mojibake | Giữ file UTF-8 và dùng công cụ đọc/kiểm tra phù hợp khi xác minh nội dung |
| Git không đọc được global ignore ngoài workspace do quyền sandbox | Không ảnh hưởng phạm vi dự án; không cần escalation cho tác vụ lập kế hoạch |
| Chưa rõ provenance/quyền sử dụng của kho tweet người dùng nói tới | Đưa legal/data provenance thành Gate 0; chỉ huấn luyện khi có căn cứ sử dụng rõ ràng |
| Thiếu phần lớn dependency ML trong môi trường local | Không cài package khi chưa cần; dùng lazy imports và kiểm thử core bằng `unittest` |

## Resources
- Repository hiện tại: `D:\tailieuhoctap\data_engineer\elt_x_to_s3`
- X Developer Policy: https://docs.x.com/developer-terms/policy
- X Developer Guidelines (AI/ML restriction): https://docs.x.com/developer-guidelines
- X API Timelines: https://docs.x.com/x-api/posts/timelines/introduction
- Hugging Face TRL SFTTrainer: https://huggingface.co/docs/trl/en/sft_trainer
- Qwen2.5-7B-Instruct model card: https://huggingface.co/Qwen/Qwen2.5-7B-Instruct
- Meta Llama 3.1 8B Instruct model card/license: https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct
- QLoRA paper: https://arxiv.org/abs/2305.14314
- Quantifying Memorization Across Neural Language Models: https://arxiv.org/abs/2202.07646
- MAUVE paper: https://arxiv.org/abs/2102.01454

## Safety Notes
- Đầu ra phải được gắn nhãn rõ là văn bản tổng hợp/nhại phong cách, không phải phát ngôn thật.
- Không nên cho mô hình tự xưng là nhân vật thật hoặc tạo nội dung nhằm đánh lừa người đọc về nguồn phát ngôn.
- Cần kiểm tra memorization để tránh tái tạo nguyên văn tweet trong train set.

## Visual/Browser Findings
- Tài liệu chính thức X (đọc ngày 2026-09-04) liệt kê “Unauthorized AI Training” và bảng technical restrictions ghi AI/ML training bị cấm trừ Grok.
- Model card Qwen cho thấy có thể serve bằng vLLM/SGLang với API tương thích OpenAI; phù hợp cho phương án serving sau MVP.
- Các nguồn nghiên cứu nhấn mạnh QLoRA giúp giảm memory, duplicate làm tăng memorization và MAUVE tương quan với đánh giá chất lượng của con người; kế hoạch cần phản ánh cả ba điểm này.
