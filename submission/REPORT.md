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

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** tự chạy `load_test.py --concurrency 5` (2 lượt) và các request prompt demo bằng key của project cá nhân; kiểm tra qua Langfuse API: 23 trace có đủ root + retrieval + generation, mỗi trace mang `correlation_id` trùng với `data/logs.jsonl`.
- **Cấu trúc root/retrieval/generation observations:** `lab-agent-run` (agent, root, metadata prompt/doc_count/query preview đã scrub) → `retrieval` (retriever, input `query_preview` đã scrub, output `doc_count`) và `llm-generation` (generation, model `claude-sonnet-4-5`, link tới prompt Langfuse, `usage_details` input/output, `cost_details` input/output/total, `completion_start_time` = TTFT). Không capture raw input/output; chỉ preview qua `summarize_text` (đã scrub PII).
- **Cách nối trace với log:** middleware sinh/nhận `x-request-id` → `correlation_id` được bind vào log và truyền vào `propagate_attributes(metadata=...)` của trace, cộng thêm trong metadata của `retrieval`/`llm-generation`; tìm trace bằng metadata `correlation_id` hoặc từ log line.
- **Prompt name:** `day13-chat` (text prompt, giữ đủ `{{feature}}`, `{{docs}}`, `{{message}}`).
- **Version/label baseline:** version 1, labels `baseline` + `production` ban đầu (template starter).
- **Version/label candidate:** version 2, label `candidate`; thêm dòng `Instruction=Answer in at most 3 short sentences, only from Docs.` → `tokens_in` cùng input tăng từ 45 lên 61.
- **Trace ID của mỗi version:** cùng input "Explain how metrics, logs and traces work together for monitoring":
  - `baseline` → v1: trace `504074fc4dbdbe565933a2c5aa56ab0a` (`req-b1000004`)
  - `candidate` → v2: trace `c52beebf7f5858185ae390cc3125038d` (`req-c2000002`)
  - `production` sau khi promote → v2: trace `d58dd521306421d8cf146a1f4e80d1ac` (`req-a2000003`)
  - `production` sau khi rollback → v1: trace `e72cc7c25c3d541c5440b428018c8759` (`req-a1000005`, `tokens_in` về lại 45)
- **Cách promote và rollback `production`:** app chỉ đọc `LANGFUSE_PROMPT_NAME`/`LANGFUSE_PROMPT_LABEL`, không sửa code. Promote: gắn label `production` cho version 2 (Langfuse tự gỡ label khỏi version 1). Rollback: gắn lại `production` cho version 1. Prompt cache TTL 60s nên chờ ≥60s hoặc restart API rồi chạy lại request để xác nhận `prompt_version` trong trace.

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** `python scripts/build_dashboard.py [--watch]` đọc `data/logs.jsonl` và `config/dashboard.yaml`, ghi `data/dashboard.html` (time range 60 phút, refresh 30s, đơn vị và đường threshold từ contract, trạng thái Đạt/Vượt ngưỡng từng panel). Sáu panel: Latency (P50/P95/P99 + TTFT P95), Traffic (count, request/phút), Errors (error rate %, breakdown `error_type`, retrieval success %), Cost (USD/phút, tổng), Tokens (tokens_in/tokens_out), Quality (mean). `validate_dashboard.py`: 6/6. Baseline lúc 10:43: P50 154ms, P95 1564ms, P99 6204ms (request đầu khi mạng tới Langfuse chậm), TTFT P95 50ms, error 0%, retrieval success 100%, tổng cost 0.129 USD, 10,579 tokens, quality 0.865.
- **SLO và lý do chọn:** `fast_successful_requests`: 99.5% request có `response_sent` với `latency_ms <= 3000` trong 28 ngày. Giữ ngưỡng 3000ms vì P95 thực tế ~1.5s (có tracing Cloud), còn khoảng đệm ~2x nhưng vẫn bắt được retrieval chậm thêm ~2.5s/request.
- **Cách tính error budget:** 100% − 99.5% = 0.5%. Với 10,000 request/28 ngày → tối đa 50 request lỗi hoặc > 3000ms. Request lỗi (không có `response_sent`) cũng tính là bad event.
- **Ba alert và runbook tương ứng:** (Slack `#k4-l3b-alerts`, owner `student-2A202602858`, chi tiết trong `docs/alerts.md`)
  1. `HighLatencyP95` (warning, 5m): P95 latency > 3000ms → runbook `docs/alerts.md#alert-1`.
  2. `HighErrorRateOrRetrievalFailure` (critical, 5m): error rate > 2% hoặc retrieval success < 90% → `#alert-2`.
  3. `CostPerRequestSpike` (warning, 15m): cost trung bình > 0.004 USD/request (2x baseline) hoặc > 0.104 USD/giờ (guardrail 2.5 USD/ngày) → `#alert-3`.

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
