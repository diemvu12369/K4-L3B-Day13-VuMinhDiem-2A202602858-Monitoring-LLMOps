# Báo cáo cá nhân — K4-L3B Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:**
- **MSSV:**
- **Lớp:** K4-L3B
- **Repository URL:**
- **Commit SHA cuối:**
- **Challenge ID:**
- **Tên project Langfuse cá nhân:** `day13-k4-l3b-<MSSV>`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/cp0-cp1-results.txt` |
| Log validator | `evidence/cp0-cp1-results.txt` |
| Dashboard validator | `evidence/cp0-cp1-results.txt` |
| Structured log | `evidence/04-structured-log.png` (log: `evidence/cp1-structured-logs.jsonl`) |
| PII redaction | `evidence/05-pii-redaction.png` |
| Trace list | `evidence/06-trace-list.png` |
| Trace waterfall | `evidence/07-trace-waterfall.png` |
| Trace metadata | `evidence/08-trace-metadata.png` |
| Prompt versions | `evidence/09-prompt-versions.png` |
| Prompt rollback | `evidence/10-prompt-rollback.png` |
| Dashboard runtime | `evidence/11-dashboard-overview.png` |
| Incident metric | `evidence/12-incident-metric.png` |
| Incident log | `evidence/13-incident-log.png` |
| Incident trace | `evidence/14-incident-trace.png` |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100, 21 records; 20 thiếu field bắt buộc và enrichment, 0 correlation ID | 100/100, 25 records; 12 correlation ID, 0 thiếu field/enrichment, 0 PII leak | Baseline trước CP1 được giữ tại `evidence/cp0-pre-cp1-logs.jsonl`; lượt cuối dùng log sạch sau sửa |
| `validate_dashboard.py` | HỢP LỆ: 6/6 panel | HỢP LỆ: 6/6 panel | Contract validator |
| `pytest` | Chưa chạy được ở Python mặc định do thiếu `structlog` và `langfuse` | 27 passed trong `.venv` | Dependencies đã cài theo `requirements.txt` |
| Số traces hợp lệ | 0 (chưa cấu hình Langfuse) | 11 traces `lab-agent-run` trên Langfuse Cloud, mỗi trace có `correlation_id` khớp log (vd. `req-0b0868de`) | `/health` báo `tracing_enabled: true`; child span retrieval/generation thuộc CP2 |
| Số PII leak | 0 | 0 | Được kiểm tra bởi log validator |
| Latency P95 / TTFT P95 | Chưa đo | Chưa đo | Ngoài phạm vi CP0/CP1 |
| Retrieval success rate | Chưa đo | Chưa đo | Ngoài phạm vi CP0/CP1 |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** nhận `x-request-id` nếu khớp `req-<8-hex>`, nếu không tạo ID mới; bind trong structlog contextvars và trả lại qua response header/body.
- **Các metadata được ghi vào structured log:** `user_id_hash`, `session_id`, `feature`, `model`, `env` và `correlation_id`.
- **Cách bảo đảm PII được scrub trước khi ghi:** `scrub_event` đệ quy qua các chuỗi ở mọi field trước `JsonlFileProcessor` và JSON renderer.
- **Cách kiểm chứng kết quả:** PII tests cho email, điện thoại VN, CCCD, thẻ; test event lồng nhau và middleware; log validator cuối đạt 100/100 với 0 PII leak.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:**
- **Cấu trúc root/retrieval/generation observations:**
- **Cách nối trace với log:**
- **Prompt name:**
- **Version/label baseline:**
- **Version/label candidate:**
- **Trace ID của mỗi version:**
- **Cách promote và rollback `production`:**

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:**
- **SLO và lý do chọn:**
- **Cách tính error budget:**
- **Ba alert và runbook tương ứng:**

> Ví dụ cách viết error budget: "SLO 99.5% trong 28 ngày nghĩa là error budget 0.5%. Nếu workload có 10,000 request thì tối đa 50 request được phép lỗi hoặc chậm hơn ngưỡng SLO."

## 7. Điều tra challenge

- **Challenge ID:**
- **Khoảng thời gian điều tra:**
- **Triệu chứng từ metrics:**
- **Log line và correlation ID liên quan:**
- **Trace ID và span gây ảnh hưởng:**
- **Root cause:**
- **Fix action:**
- **Preventive measure:**

> Gợi ý cách viết ngắn, không thay cho evidence thực tế: "Metric cho thấy `[latency/error/cost/quality]` bất thường trong `[khoảng thời gian]`. Log line `[event]` có `correlation_id=[...]` đại diện cho request bị ảnh hưởng. Trace cùng `correlation_id` cho thấy span `[retrieval/generation/prompt/tool]` có dấu hiệu `[chậm/lỗi/token tăng]`. Root cause là `[nguyên nhân suy ra từ evidence]`. Fix action là `[hành động khôi phục]`; preventive measure là `[alert/runbook/test/guardrail để ngăn tái diễn]`."

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:**
- **Một lỗi/blocker đã gặp:** Python mặc định thiếu dependencies; key Langfuse bị điền ngược (public/secret) và mạng timeout khi export span.
- **Cách tìm nguyên nhân và xử lý:** cài `requirements.txt` trong `.venv`; kiểm tra prefix `pk-lf-`/`sk-lf-` và `auth_check()`, đổi mạng rồi chạy lại load test, xác nhận trace qua Langfuse API.
- **Cách hiểu luồng Metrics → Logs → Traces:**
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:**
- **Điều quan trọng nhất đã học:**
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:**
	CP0/CP1 đã hoàn thành. Prompt `day13-chat` chưa tạo trên Langfuse nên app dùng fallback prompt (sẽ làm ở CP2).

## 9. Checklist trước khi nộp

- [ ] Kết quả và evidence thuộc commit SHA cuối.
- [ ] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [ ] Incident evidence nối đúng metric → log → trace.
- [ ] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [ ] Repository chạy lại được theo README.
- [ ] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
