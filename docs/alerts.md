# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert mẫu để tham khảo

Ví dụ dưới đây minh họa mức độ cụ thể cần có. Học viên không cần copy nguyên, nhưng ba alert trong bài nộp nên rõ ràng tương tự: điều kiện là gì, kéo dài bao lâu, ảnh hưởng tới user ra sao và người trực cần kiểm tra gì trước.

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: latency P95 của `response_sent.latency_ms`
- Điều kiện và thời gian duy trì: `p95(latency_ms) > 3000ms` trong 5 phút
- Ảnh hưởng tới người dùng: người dùng phải chờ lâu hơn trước khi nhận câu trả lời
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard latency để xác nhận P95/P99 và khoảng thời gian tăng.
  2. Lọc `data/logs.jsonl` trong khoảng đó, lấy một `correlation_id` có `latency_ms` cao.
  3. Mở trace cùng `correlation_id` trên Langfuse, so sánh các span chính để xác định bước nào bất thường.
- Mitigation tạm thời: dựa trên evidence thực tế để rollback prompt, khôi phục cấu hình liên quan, tắt practice scenario hoặc giảm tải khi demo.
- Owner: `student-<MSSV>`

## Alert 1

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: SLO `fast_successful_requests` (99.5% request `response_sent` có `latency_ms <= 3000` trong 28 ngày); panel Latency.
- Điều kiện và thời gian duy trì: `p95(response_sent.latency_ms) > 3000ms` liên tục 5 phút.
- Ảnh hưởng tới người dùng: người dùng chờ lâu trước khi nhận câu trả lời; mỗi request chậm hơn 3000ms đốt error budget 0.5%.
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard panel Latency, xác nhận P95/P99 vượt đường threshold 3000ms từ lúc nào và TTFT P95 có tăng theo không (TTFT tăng → generation chậm; TTFT bình thường mà latency tăng → bước trước LLM chậm).
  2. Lọc `data/logs.jsonl` trong khoảng đó: `event == "response_sent"` và `latency_ms > 3000`, lấy một `correlation_id`.
  3. Mở trace Langfuse có cùng `correlation_id`, so sánh thời lượng span `retrieval` và `llm-generation` dưới `lab-agent-run`.
- Mitigation tạm thời: nếu span `retrieval` chậm, khôi phục/tắt cấu hình retrieval gây chậm hoặc giảm tải; nếu `llm-generation` chậm sau khi đổi prompt, rollback label `production` về version trước; báo trạng thái trong `#k4-l3b-alerts`.
- Owner: `student-2A202602858`

## Alert 2

- Tên: `HighErrorRateOrRetrievalFailure`
- Severity: `critical`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: SLO `fast_successful_requests` (request lỗi không có `response_sent` nên tính là bad event); guardrail `error_rate_pct_max: 2` và `retrieval_success_rate_pct_min: 90`; panel Errors.
- Điều kiện và thời gian duy trì: `count(request_failed) / count(request_received) * 100 > 2%` hoặc tỷ lệ `tool_success == true` của `tool_name == "retrieval"` `< 90%`, liên tục 5 phút.
- Ảnh hưởng tới người dùng: người dùng nhận HTTP 500 hoặc câu trả lời không dựa trên tài liệu; error budget bị đốt rất nhanh.
- Ba bước kiểm tra đầu tiên:
  1. Mở panel Errors, xem error rate, breakdown theo `error_type` và retrieval success rate bắt đầu xấu từ lúc nào.
  2. Lọc `data/logs.jsonl`: `event == "request_failed"` trong khoảng đó, đọc `error_type`, `tool_name`, `tool_success` và lấy `correlation_id`.
  3. Mở trace cùng `correlation_id`, tìm observation có level `ERROR` (thường là `retrieval`) và đọc status message.
- Mitigation tạm thời: khôi phục dependency/cấu hình retrieval bị lỗi, tắt thay đổi gần nhất hoặc chuyển sang fallback answer; nếu lỗi xuất hiện sau khi đổi prompt thì rollback `production`.
- Owner: `student-2A202602858`

## Alert 3

- Tên: `CostPerRequestSpike`
- Severity: `warning`
- Duration: `15m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: guardrail `daily_cost_usd_max: 2.5` (≈ 0.104 USD/giờ); panel Cost và Tokens. Baseline cost ~0.002 USD/request.
- Điều kiện và thời gian duy trì: `avg(response_sent.cost_usd) > 0.004` (gấp 2 baseline) hoặc `sum(cost_usd)` trong 1 giờ `> 0.104 USD`, liên tục 15 phút.
- Ảnh hưởng tới người dùng: câu trả lời dài bất thường và chậm hơn; hệ thống có nguy cơ vượt ngân sách ngày.
- Ba bước kiểm tra đầu tiên:
  1. Mở panel Cost và Tokens, xác định cost tăng do `tokens_in` (prompt dài hơn) hay `tokens_out` (output dài hơn) và từ lúc nào.
  2. Lọc `data/logs.jsonl`: `event == "response_sent"` có `cost_usd` hoặc `tokens_out` cao nhất, lấy `correlation_id`.
  3. Mở trace cùng `correlation_id`, xem `usage_details`/`cost_details` và `prompt_version` của observation `llm-generation`, so với trace baseline.
- Mitigation tạm thời: rollback label `production` nếu prompt version mới làm token tăng; giới hạn độ dài output hoặc tắt thay đổi cấu hình gây tăng token; theo dõi lại panel Cost sau 15 phút.
- Owner: `student-2A202602858`
