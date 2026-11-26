# Benchmark & Observability Report — Day 14

> Mọi con số dưới đây được lấy trực tiếp từ các file JSON trong `reports/`, CSV trong `benchmark-results/` và screenshot thực tế.

**Họ tên:** Nguyen Bao Trung (MSSV: 2A202604013)
**Ngày chạy:** 2026-11-26
**Môi trường:** macOS (Apple M1), Python 3.12.16, Docker 29.9.3 / Docker Compose v5.7.0

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | 95% người dùng nhận phản hồi dưới 0.5 giây — đủ mượt cho tương tác hỏi-đáp với mock LLM (~150–220 ms) và bắt được tình trạng tail latency hoặc quá tải hàng đợi. |
| Error rate `/ask` | < 2.0 % | Chấp nhận sai số lỗi upstream ngẫu nhiên (~1% theo `MOCK_ERROR_RATE=0.01`), tạo error budget 2% để phân biệt nhiễu tạm thời với sự cố thật (alert đặt cao hơn ở mức >5% trong 1 phút để tránh alert fatigue). |
| Accuracy trên golden dataset | ≥ 85 % (mục tiêu sau sửa KB: 100%, 0 regression) | Đảm bảo agent trả lời đúng đa số câu hỏi cốt lõi trước khi release và không được làm hỏng các câu trước đó đã trả lời đúng. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2, 300 requests/mức)

Nguồn dữ liệu: `reports/load_v2_c1.json`, `reports/load_v2_c10.json`, `reports/load_v2_c50.json`, `reports/load_v2_c100.json`.

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---:|---:|---:|---:|---:|---|
| 1 | 4.16 | 191.6 | 222.3 | 1704.4 | 0.33% | PASS |
| 10 | 39.16 | 190.2 | 217.6 | 1709.7 | 0.67% | PASS |
| 50 | 109.07 | 193.3 | 232.3 | 1687.1 | 3.67% | FAIL (error rate > 2%) |
| 100 | 64.67 | 384.1 | 3615.0 | 3813.2 | 1.00% | FAIL (p95 > 500ms) |

**Nhận xét:** RPS **không** tăng tuyến tính mãi theo concurrency. Từ concurrency 1 → 10 → 50, RPS tăng mạnh (4.16 → 39.16 → 109.07 req/s) vì agent xử lý bất đồng bộ (`async`/`await` chờ I/O mock LLM). Nhưng khi đẩy lên concurrency 100 trên 1 process uvicorn đơn lẻ, tranh chấp event loop/socket và xếp hàng request làm RPS **giảm ngược** xuống còn 64.67 req/s trong khi p50 tăng gần gấp đôi (384.1 ms) và p95 vọt lên 3615.0 ms (vi phạm SLO). Tại concurrency 50, p95 vẫn đạt (232.3 ms) nhưng tỉ lệ lỗi ngẫu nhiên 503 rơi vào 11/300 request (3.67% > 2.0%) nên FAIL SLO error rate.

### 2.2 Tail latency (`concurrency=20`, 300 requests/mức)

Nguồn dữ liệu: `reports/load_v2_slow_0.json`, `reports/load_v2_slow_0.03.json`, `reports/load_v2_slow_0.1.json`.

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---:|---:|---:|
| 0 | 191.3 | 221.0 | 235.0 |
| 0.03 (mặc định) | 210.8 | 220.0 | 1674.7 |
| 0.1 | 393.3 | 1700.2 | 1718.8 |

**Nhận xét:** **p99 và p95** nhạy nhất với các request chậm bất thường (tail latency):
- Khi `MOCK_SLOW_RATE` tăng từ `0` lên `0.03` (3% request chậm thêm ~1.5s), `avg` chỉ nhích nhẹ **+19.5 ms** (191.3 → 210.8 ms) và `p95` hầu như không đổi (220.0 ms), nhưng **p99 nhảy gấp 7 lần** lên `1674.7 ms`.
- Khi `MOCK_SLOW_RATE = 0.1` (10% request chậm, vượt ngưỡng 5%), cả **p95** (`1700.2 ms`) và **p99** (`1718.8 ms`) đều vọt lên ~1.7 giây và vi phạm SLO, trong khi **average vẫn chỉ là `393.3 ms`** (< 500 ms!).
- Vì vậy, **average che giấu trải nghiệm tệ của nhóm người dùng ở đuôi phân phối** — SLO latency bắt buộc phải đặt theo percentile (`p95`/`p99`).

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

Nguồn dữ liệu: `reports/eval_v1.json`, `reports/eval_v2.json`, `reports/eval_v2_fixed.json`.

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.35% (1/23) | 91.30% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 56.3 | 109.3 | 114.1 |
| Tổng cost (USD) | $0.000393 | $0.000764 | $0.000794 |
| Cost / câu đúng (USD) | $0.00039255 | $0.00003639 | $0.00003453 |
| Latency p50 / p95 (ms) | 152.7 / 188.9 | 196.4 / 221.6 | 184.3 / 219.9 |
| Quality gate | FAIL (ngưỡng ≥ 80%) | PASS (≥ 80%, 0 regression) | PASS (≥ 100%, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách sửa (trong `utils/mock_llm.py`, không sửa `golden_dataset.jsonl`):**

| ID | Keyword bị thiếu | Đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry vào `KNOWLEDGE_BASE` với từ khoá `["jwt"]` giải thích khác biệt giữa API key cố định và JWT (token có chữ ký số, chứa thông tin user và thời điểm hết hạn). |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry vào `KNOWLEDGE_BASE` với từ khoá `["hpa", "kubernetes", "autoscal"]` mô tả Kubernetes HPA tự động scale pod theo CPU, memory hoặc custom metrics (RPS, hàng đợi). |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**
- **Chất lượng tăng vượt trội:** v2 thêm bước retrieval (RAG) giúp accuracy nhảy từ **4.35% (1/23)** lên **91.30% (21/23)** và **100.0% (23/23)** sau khi bổ sung 2 tài liệu thiếu trong `KNOWLEDGE_BASE` (0 regression).
- **Chi phí & hiệu quả kinh tế:** v2 dùng trung bình gần **gấp đôi số token** mỗi câu (109.3–114.1 vs 56.3 token) do phải chèn tài liệu vào prompt, làm tổng cost tăng ~2× ($0.000794 vs $0.000393). Tuy nhiên xét theo **cost / câu trả lời đúng**, v2 sau sửa KB ($0.00003453) **rẻ hơn ~11.4 lần** so với v1 ($0.00039255) — đây là lý do nên so sánh theo "cost / câu đúng" thay vì "cost / câu".
- **Latency:** v2 chậm hơn một chút (~30–40 ms ở p50/p95) do thêm bước `search_knowledge_base` (~20 ms) và prompt dài hơn, nhưng sự đánh đổi này hoàn toàn xứng đáng so với mức tăng accuracy.

**Quality gate trong CI/CD (Exercise 7.3):**
`eval/run_eval.py` kết thúc bằng `raise SystemExit(0 if gate_ok else 1)`, trong đó `gate_ok = (accuracy >= --min-accuracy) and (len(regressions) == 0)`. Khi đặt trong GitHub Actions (chạy trên mỗi `pull_request` với `--min-accuracy 0.85 --baseline ...`), nếu accuracy tụt dưới ngưỡng hoặc xuất hiện bất kỳ câu regression nào, script trả **exit code 1** khiến step CI fail và GitHub branch protection tự động **chặn merge PR**:

```yaml
name: eval-quality-gate
on: [pull_request]
jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Run agent v2 & eval quality gate
        working-directory: 06-lab-complete/benchmark-observability/develop
        run: |
          pip install -r requirements.txt
          AGENT_VERSION=v2 MOCK_ERROR_RATE=0 python app.py &
          sleep 3
          python eval/run_eval.py --url http://localhost:8000 --min-accuracy 0.85
```

**Bổ sung Exercise 7.1 (Metrics):** Đã thêm `Histogram("agent_question_length_chars", ...)` vào `develop/app.py` (quan sát được `agent_question_length_chars_count 1.0` trên `/metrics`). Dùng `route.path` thay vì `request.url.path` làm label để tránh **cardinality explosion** (nếu bot quét hàng nghìn URL rác `/wp-admin`, `/.env`, `/a1b2c3`..., mỗi URL tạo 1 time series mới làm Prometheus cạn RAM).

---

## 4. Observability stack (production)

### 4.1 Screenshot & trả lời Exercise 7.4

- [x] Dashboard Grafana khi đang có tải ([screenshots/grafana-dashboard.png](screenshots/grafana-dashboard.png))
- [x] Một trace chậm trong Jaeger ([screenshots/jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png))
- [x] Một trace lỗi trong Jaeger ([screenshots/jaeger-error-trace.png](screenshots/jaeger-error-trace.png))
- [x] Trang Alerts của Prometheus với cả 4 alert đang **firing** ([screenshots/prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png))

**Trả lời câu hỏi Exercise 7.4 (quan sát khi chạy tải 30 users / ramp 5 trên Grafana & Prometheus):**
1. **p95 và avg:** Tại thời điểm chạy tải trên ảnh Grafana (`grafana-dashboard.png`): `Traffic = 9.1 req/s`, `Error rate = 1.60%`, `Latency p95 = 440.59 ms`, `Instances up = 2`, `LLM cost = $0.0527` (đo qua Prometheus API cửa sổ 5 phút dưới tải cao hơn: `p95 = 397.2 ms`, `avg = 246.4 ms`, `error rate = 0.97%`). Khoảng cách giữa `p95`/`p99` (~1.8s trên biểu đồ) và `avg`/`p50` (~200 ms) cho thấy phân phối latency bị **lệch phải (right-skewed)** do ~3% request chậm bất thường (`MOCK_SLOW_RATE=0.03`).
2. **Requests/s theo instance:** Nginx chia tải gần như cân bằng giữa các instance theo round-robin (đo qua Prometheus `rate(http_requests_total[2m])`: instance `172.18.0.6:8000` nhận **21.51 req/s**, instance `172.18.0.8:8000` nhận **20.74 req/s**).
3. **Vì sao input tokens/s lớn hơn output tokens/s?** Trên Prometheus, `input = 3,638.1 tok/s` gần gấp đôi `output = 1,904.2 tok/s` vì với agent v2 (RAG), mỗi prompt đầu vào bao gồm **system prompt + tài liệu retrieve được từ `KNOWLEDGE_BASE` + câu hỏi của user**, còn câu trả lời đầu ra ngắn gọn hơn.
4. **`curl -i http://localhost:8080/metrics` trả về gì và vì sao?** Trả về **`HTTP/1.1 404 Not Found`** từ Nginx (`nginx/1.28.3`). Nginx cố tình chặn `/metrics` từ bên ngoài để tránh lộ thông tin nội bộ hệ thống (cấu trúc route, số lượng instance, lỗi, chi phí) ra internet; chỉ Prometheus nằm trong mạng nội bộ Docker (`obs_net`) mới được scrape trực tiếp `agent:8000/metrics`.

### 4.2 Thí nghiệm "phá hệ thống" (Exercise 7.6)

Đã kiểm tra unit test alert rules bằng `promtool test rules /p/alert_rules_test.yml` (PASS), sau đó chạy thí nghiệm fault injection (`MOCK_ERROR_RATE=0.2`, `MOCK_SLOW_RATE=0.3`, `LLM_MODEL=mock-llm-large` kết hợp `docker pause k5-day14-observability-agent-2`) dưới tải Locust 30 users và đo thời gian chuyển trạng thái qua Prometheus `/api/v1/alerts`:

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (`for: 1m`, giá trị đo `18.67% > 5%`) | pending `+15.1s` → **firing `+75.3s`** | **Error rate** & **Requests/s theo status code** (503 tăng vọt) |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (`for: 2m`, giá trị đo `1.93s > 1s`) | pending `+15.1s` → **firing `+135.4s`** | **Latency p95** & **Latency /ask — p50 / p95 / p99** |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (`for: 2m`, giá trị > `$2/giờ`, đo từ `$2.74/giờ` tăng tiếp) | **firing** (vượt `$2/giờ` kéo dài > 2m) | **Cost burn rate (USD/giờ)** & **LLM latency p95 theo model** |
| D | `docker pause` 1 instance (`agent-2`) | `AgentInstanceDown` (`for: 30s`, `up == 0`) | pending `+5.1s` → **firing `+40.2s`** | **Instances up** (tụt từ 2 → 1) & **Requests/s theo instance** |
| E | `AGENT_VERSION=v1` | **Không alert nào firing** | Không kích hoạt | **Retrieval hit ratio (agent v2)** giảm về 0 & **Phiên bản đang chạy** (`agent_info` đổi sang `v1`) |

**Thí nghiệm E không làm alert nào firing — cách phát hiện trong production & phân tích lỗi 504 ở Nginx:**
- Khi chuyển sang `AGENT_VERSION=v1`, HTTP vẫn trả `200 OK`, latency còn nhanh hơn và cost rẻ hơn nên mọi alert hạ tầng/SLO truyền thống (error rate, p95, uptime, cost) đều im lặng dù chất lượng câu trả lời tụt từ 100% xuống 4.35%. Để bắt loại sự cố *silent quality degradation* này cần: (1) chạy **eval quality gate** trên golden dataset trong CI/CD trước khi deploy (chặn merge nếu tụt accuracy/regression), (2) theo dõi **online quality metrics** (retrieval hit ratio, user feedback thumbs up/down, LLM-as-judge sampling trên traffic thật) và đặt alert khi retrieval hit ratio tụt đột ngột.
- **Vì sao lỗi `504 Gateway Timeout` ở Nginx không hiện trên metric của agent?** Khi agent bị treo/quá tải không kịp trả lời trong `proxy_read_timeout`, chính Nginx đóng kết nối và trả `504` cho client trước khi middleware của agent hoàn tất response (`http_requests_total`), do đó chỉ thấy trên access log / metric của Nginx/load balancer (cần giám sát ở **cả tầng edge/proxy lẫn tầng app**).

### 4.3 Debug bằng trace (Exercise 7.5)

**Trace chậm nhất đã phân tích (`screenshots/jaeger-slow-trace.png`):**
- `trace_id`: `9059f5dddd0cc733cbb70fc4c33a2de8`
- Tổng thời gian: **1,716.4 ms** (hiển thị `1.7s` trên Jaeger, start `18.5 ms` cho middleware + `agent.retrieve_context`)
- Span chiếm nhiều thời gian nhất: **`chat mock-llm-small`** — **1,697.9 ms (~98.9%** tổng thời gian request), `input_tokens=95`, `output_tokens=55`
- Dòng log JSON tương ứng (grep từ `docker compose -p k5-day14-observability logs agent` theo đúng `trace_id`):

```json
{"ts": "2026-11-26T07:59:23.332118+00:00", "level": "INFO", "service": "observable-agent", "instance": "1b28b2d8de1e", "event": "llm_call", "trace_id": "9059f5dddd0cc733cbb70fc4c33a2de8", "span_id": "94500661185ff9bf", "request_id": "484ea29cfc95", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 95, "output_tokens": 55, "cost_usd": 4.7e-05, "llm_ms": 1697.9}
```

**Trace lỗi đã phân tích (`screenshots/jaeger-error-trace.png`):**
- `trace_id`: `900d90294f0c82bd691888727e47df97` (`HTTP 503`, tổng thời gian `155 ms`, span `chat mock-llm-small` `82.6 ms`, event `exception`: `utils.mock_llm.LLMError: Upstream LLM error: 503 Service Unavailable (mock)`).
- Dòng log JSON khớp `trace_id`:

```json
{"ts": "2026-11-26T07:57:56.225630+00:00", "level": "INFO", "service": "observable-agent", "instance": "1b28b2d8de1e", "event": "llm_error", "trace_id": "900d90294f0c82bd691888727e47df97", "span_id": "89171d7ad99f8d9f", "request_id": "a4f719b7579a", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Nguồn dữ liệu: `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv`.

**Theo endpoint `POST /ask`:**

| Số instance | Requests | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 6,910 | 58.14 | 200 | 770 | 1,700 | 68 (0.98%) |
| 3 | 7,196 | 60.11 | 200 | 270 | 1,700 | 71 (0.99%) |

**Tổng hợp (`Aggregated` — gồm `POST /ask` và `GET /health`):**

| Số instance | Requests | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 7,606 | 64.00 | 200 | 700 | 1,700 | 68 (0.89%) |
| 3 | 7,905 | 66.03 | 190 | 260 | 1,700 | 71 (0.90%) |

**Giải thích kết quả:**
- **Scale từ 1 → 3 instance cải thiện rõ rệt p95:** p95 của `POST /ask` giảm từ **770 ms xuống 270 ms (−64.9%)**, p95 tổng hợp giảm từ **700 ms xuống 260 ms**, và latency lớn nhất giảm từ 3,039 ms xuống 1,841 ms. Nguyên nhân: mỗi container agent bị giới hạn `0.5 CPU`; khi 100 users đồng thời đổ vào 1 instance, event loop và CPU bão hoà gây xếp hàng chờ; chia tải ra 3 instance qua Nginx giải phóng nút thắt CPU cục bộ.
- **Nút thắt còn lại nằm ở đâu?** `p99` giữ nguyên **1,700 ms** và tỉ lệ lỗi giữ nguyên **~1%** dù tăng gấp 3 instance, vì đây là độ trễ/lỗi cố hữu từ **upstream LLM** (`MOCK_SLOW_RATE=0.03`, `MOCK_ERROR_RATE=0.01`), scale ngang app server không làm giảm được. RPS chỉ tăng nhẹ (64.00 → 66.03 req/s) do 100 user ảo trong Locust có `wait_time` cố định giữa các lần gọi (tải đầu vào bị giới hạn bởi số user, không phải năng lực của cụm 3 instance).

---

## 6. Kết luận

- **3 điều học được về benchmark & observability:**
  1. **Không bao giờ đánh giá hiệu năng bằng latency trung bình hay chất lượng bằng cảm tính:** `avg` che giấu hoàn toàn tail latency (`MOCK_SLOW_RATE=0.1` cho avg `393.3 ms` nhưng p95/p99 lên `1.7s`), còn eval có baseline + quality gate giúp định lượng chính xác trade-off (v2 tốn gấp đôi token nhưng cost/câu đúng rẻ hơn ~11.4 lần so với v1) và chặn regression tự động.
  2. **Ba trụ cột Metrics – Traces – Logs phải nối với nhau qua `trace_id`:** Prometheus/Grafana cho biết *có sự cố gì* (p95 hay error rate tăng), Jaeger chỉ ra *chậm/lỗi ở span nào* (`chat mock-llm-small` chiếm 98.9% thời gian), và `trace_id` giúp grep ngay dòng log JSON chi tiết.
  3. **Alert hạ tầng không bắt được suy giảm chất lượng AI:** Khi đổi sang `AGENT_VERSION=v1`, mọi alert hạ tầng đều xanh trong khi accuracy sụp đổ — bắt buộc kết hợp eval tự động trong CI và giám sát chất lượng (retrieval hit ratio, feedback).
- **Nếu đưa agent này lên production thật, sẽ thêm các metric / alert:**
  1. **Metric chất lượng & RAG:** `agent_retrieval_hit_ratio` (alert nếu tụt dưới ngưỡng), phân bố điểm similarity của vector search, và tỉ lệ fallback/empty answer.
  2. **Metric ở tầng edge & dependency:** Tỉ lệ lỗi `4xx`/`502`/`504` từ Nginx/API Gateway, latency & tỉ lệ kết nối lỗi của **Redis** (`redis_errors_total`), và tỉ lệ request bị chặn bởi **rate limiter (429)** / **cost guard (402)** để phát hiện sớm hành vi lạm dụng hoặc hết ngân sách.
  3. **LLM-specific latency & routing:** Time-to-First-Token (**TTFT**) nếu bật streaming, và tích hợp **Alertmanager** định tuyến cảnh báo `critical` sang Slack/PagerDuty kèm runbook xử lý.
