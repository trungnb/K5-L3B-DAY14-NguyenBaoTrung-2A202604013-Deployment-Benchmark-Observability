# Day 14 Lab — Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns phát hiện trong `01-localhost-vs-production/develop/app.py`

1. **Hardcode secrets trong mã nguồn (dòng 17–18):** `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`. Nếu push lên GitHub public, bot quét tự động sẽ thu thập key trong vài giây.
2. **In secret ra log (dòng 34):** `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` làm lộ API key trên stdout và mọi hệ thống thu thập log.
3. **Hardcode cấu hình / không tách config theo môi trường (dòng 21–22):** `DEBUG = True`, `MAX_TOKENS = 500` viết cứng trong code; muốn đổi giữa dev/staging/prod phải sửa code và deploy lại.
4. **Dùng `print()` thay cho structured logging (dòng 33–34, 38, 48):** Không có timestamp, log level chuẩn hay định dạng JSON → khó tìm kiếm, lọc và phân tích trên hệ thống giám sát (Loki, Datadog, Cloud Logging).
5. **Không có endpoint health check & readiness (toàn bộ file):** Thiếu `GET /health` và `GET /ready`, khiến nền tảng cloud / load balancer không biết container còn sống hay đã sẵn sàng nhận traffic để tự restart hoặc ngắt route.
6. **Bind cứng `host="localhost"` và `port=8000` (dòng 51–52):** Trong container hoặc trên Railway/Render, app phải bind `0.0.0.0` và đọc port từ biến môi trường `PORT`; bind `localhost` khiến bên ngoài container không kết nối được.
7. **Bật cứng `reload=True` (dòng 53):** Chế độ auto-reload chỉ dành cho phát triển cục bộ; dùng trên production tốn tài nguyên theo dõi file và dễ gây restart bất ngờ.
8. **Không xử lý graceful shutdown (`SIGTERM` / `lifespan`):** Khi nền tảng tắt hoặc rolling deploy container, các request đang xử lý bị cắt ngang đột ngột.

### Exercise 1.2: Kết quả chạy bản develop

Chạy `01-localhost-vs-production/develop/app.py` và gọi theo quy ước query param của K5 (`curl -sS -i -X POST "http://localhost:8000/ask?question=Hello"`):

```http
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 07:08:31 GMT
server: uvicorn
content-length: 103
content-type: application/json

{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

### Exercise 1.3: So sánh `develop` vs `production`

Kết quả chạy `01-localhost-vs-production/production/app.py`:
- `GET /health` → `200 OK`: `{"status":"ok","uptime_seconds":2.8,"version":"1.0.0","environment":"development","timestamp":"2026-11-26T07:08:36.065492+00:00"}`
- `GET /ready` → `200 OK`: `{"ready":true}`
- `POST /ask` (`{"question":"Hello"}`) → `200 OK`: `{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","model":"gpt-4o-mini"}`
- Khi gửi `SIGTERM`, server log `Shutting down` → `Waiting for application shutdown.` → `Application shutdown complete.`

| Feature | Develop (`develop/app.py`) | Production (`production/app.py` + `config.py`) | Tại sao quan trọng? |
|---|---|---|---|
| **Config & Secrets** | Hardcode `OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG=True`, `PORT=8000` (dòng 17–22, 51–52) | Tách vào `Settings` trong `config.py`, đọc từ `os.getenv(...)` và `validate()` fail-fast khi thiếu `AGENT_API_KEY` ở production (dòng 15–50) | Tránh rò rỉ secret lên git; cùng một artifact chạy được ở dev/staging/prod chỉ bằng cách đổi biến môi trường (12-Factor III). |
| **Network binding** | `host="localhost"`, `port=8000`, `reload=True` (dòng 51–53) | `host="0.0.0.0"`, `port=settings.port` (từ `PORT`), `reload=settings.debug` (dòng 194–199) | Container và nền tảng PaaS (Railway/Render) cấp port động qua `PORT` và cần bind `0.0.0.0` để proxy/host kết nối vào. |
| **Health & Readiness** | Không có | `GET /health` (liveness, dòng 135–149) và `GET /ready` (readiness, trả 503 nếu `not is_ready`, dòng 152–161) | Platform tự động restart container treo (liveness) và load balancer chỉ đẩy traffic khi app đã khởi tạo xong (readiness). |
| **Logging** | `print("[DEBUG] ...")`, còn in cả `OPENAI_API_KEY` (dòng 33–38) | `logging` định dạng JSON + `json.dumps(...)`, chỉ log metadata (`question_length`, `client_ip`), không log secret (dòng 28–32, 111–122) | Log có cấu trúc dễ truy vấn, tổng hợp, tạo cảnh báo trong production mà không làm lộ thông tin nhạy cảm. |
| **Shutdown** | Tắt đột ngột | `lifespan` chuyển `is_ready = False` khi tắt và đợi request hoàn tất; đăng ký handler `SIGTERM` (dòng 39–68, 180–189) | Không cắt ngang request đang xử lý và không làm mất dữ liệu trong lúc deploy hoặc scale down. |
| **Input & CORS** | Nhận query param thô, không cấu hình CORS | Validate body JSON (thiếu `question` → 422, dòng 102–108), cấu hình `CORSMiddleware` theo `ALLOWED_ORIGINS` (dòng 77–82) | Trả lỗi rõ ràng cho client và kiểm soát domain được phép gọi API từ trình duyệt. |

---

## Part 2: Docker

### Exercise 2.1: Phân tích `02-docker/develop/Dockerfile`

1. **Base image:** `python:3.11` (bản đầy đủ Debian + Python 3.11 runtime + build tools, dung lượng lớn ~1 GB).
2. **Working directory:** `/app` (`WORKDIR /app`), là thư mục làm việc mặc định cho các lệnh `COPY`, `RUN`, `CMD` phía sau.
3. **Tại sao `COPY 02-docker/develop/requirements.txt .` đứng trước `COPY 02-docker/develop/app.py .`?** Để tận dụng **Docker layer cache**. `requirements.txt` ít thay đổi hơn mã nguồn `app.py`; khi chỉ sửa `app.py`, Docker tái sử dụng cache của layer `RUN pip install --no-cache-dir -r requirements.txt` mà không phải tải và cài lại toàn bộ thư viện.
4. **`CMD` vs `ENTRYPOINT` khác nhau thế nào?**
   - `CMD` cung cấp lệnh/tham số mặc định và **dễ bị ghi đè** khi truyền tham số sau tên image ở `docker run <image> <cmd mới>`.
   - `ENTRYPOINT` cố định chương trình chính của container (khó ghi đè, phải dùng `--entrypoint`), còn `CMD` khi đi kèm `ENTRYPOINT` đóng vai trò làm tham số mặc định truyền vào `ENTRYPOINT`.

### Exercise 2.2: Build và chạy `my-agent:develop`

Build từ thư mục gốc repo: `docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .` và chạy `docker run -d -p 8000:8000 my-agent:develop`.

Gọi thử (`curl -sS -i -X POST "http://localhost:8000/ask?question=What%20is%20Docker%3F"`):

```http
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 07:10:46 GMT
server: uvicorn
content-length: 103
content-type: application/json

{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

### Exercise 2.3: Multi-stage build và so sánh kích thước image

- **Stage 1 (`builder`, `python:3.11-slim`):** Cài `gcc`, `libpq-dev` và chạy `pip install --no-cache-dir --user -r requirements.txt` để biên dịch và cài toàn bộ dependencies vào `/root/.local`.
- **Stage 2 (`runtime`, `python:3.11-slim`):** Tạo user non-root `appuser`, chỉ `COPY --from=builder /root/.local /home/appuser/.local`, copy `main.py` và `utils/mock_llm.py`, đặt `USER appuser`, cấu hình `HEALTHCHECK` và chạy `uvicorn` với 2 workers.
- **Tại sao image nhỏ hơn?** Stage cuối dùng base `python:3.11-slim` (thay vì `python:3.11` đầy đủ) và **loại bỏ hoàn toàn** compiler (`gcc`), thư viện build (`libpq-dev`) và cache của stage builder.

Số liệu đo thực tế trên máy bằng `docker images my-agent` và `docker image inspect` (arm64v8):

| Image | Disk Usage (`docker images`) | Exact Size (`docker image inspect`) |
|---|---:|---:|
| `my-agent:develop` | 1.67 GB | 1,672.2 MB (1,594.7 MiB) |
| `my-agent:advanced` | 265 MB | 265.5 MB (253.2 MiB) |
| **Chênh lệch (giảm)** | **−1.40 GB** | **−84.1%** |

### Exercise 2.4: Docker Compose stack (`02-docker/production/docker-compose.yml`)

Tạo `.env.local` rỗng và chạy `docker compose -p k5-day14-docker -f 02-docker/production/docker-compose.yml up -d --build`.

**Sơ đồ kiến trúc (4 service trên bridge network `internal`):**

```text
Client (localhost:80)
   │
   ▼
[ nginx:alpine ]  (Reverse proxy, security headers, rate limit 10 req/s)
   │  proxy_pass http://agent:8000
   ▼
[ agent ]         (FastAPI + uvicorn --workers 2, không expose port ra host)
   ├──▶ [ redis:7-alpine ]        (port 6379, volume redis_data — cache & rate limit)
   └──▶ [ qdrant/qdrant:v1.9.0 ]  (port 6333, volume qdrant_data — vector DB)
```

Các service giao tiếp qua DNS nội bộ của Docker network `internal` (`agent:8000`, `redis:6379`, `qdrant:6333`), chỉ `nginx` mở port 80/443 ra ngoài host. `agent` dùng `depends_on` với `condition: service_healthy` cho cả `redis` và `qdrant`.

**Kết quả test qua Nginx:**

```http
$ curl -sS -i http://localhost/health
HTTP/1.1 200 OK
Server: nginx
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"status":"ok","uptime_seconds":2.6,"version":"2.0.0","timestamp":"2026-11-26T07:13:48.806321"}

$ curl -sS -i -X POST http://localhost/ask -H "Content-Type: application/json" -d '{"question": "Explain microservices"}'
HTTP/1.1 200 OK
Server: nginx
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

---

## Part 4: API Security

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop/`)

- API key được kiểm tra trong dependency `verify_api_key` (`app.py`, dòng 39–54) đọc header `X-API-Key` qua `APIKeyHeader(name="X-API-Key", auto_error=False)` và inject vào `/ask` bằng `Depends(verify_api_key)`.
- Nếu thiếu key → trả `401 Unauthorized`; nếu sai key → trả `403 Forbidden`.
- **Cách rotate key:** Đọc key từ biến môi trường (`AGENT_API_KEY`) hoặc hỗ trợ danh sách key cũ + key mới song song trong thời gian chuyển tiếp (dual-key window), cập nhật client sang key mới rồi thu hồi key cũ.

Chạy với `AGENT_API_KEY=secret-key-123 python app.py`:

```http
# Không có key → 401
HTTP/1.1 401 Unauthorized
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

# Có key hợp lệ → 200
HTTP/1.1 200 OK
content-type: application/json

{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

### Exercise 4.2 & 4.3: JWT Authentication & Rate Limiting (`04-api-gateway/production/`)

- **JWT flow (`auth.py`):** Client gửi `username`/`password` tới `POST /auth/token` → server xác thực và ký JWT (`HS256`, chứa `sub`, `role`, `iat`, `exp` 60 phút) bằng `JWT_SECRET`. Các request tới `/ask` gửi `Authorization: Bearer <token>`, server giải mã và kiểm chữ ký mà không cần tra database mỗi request.
- **Rate limiting (`rate_limiter.py`):** Dùng thuật toán **Sliding Window** (lưu `deque` timestamps trong 60 giây, loại bỏ các timestamp cũ hơn `now - 60`). Giới hạn theo role: `user` (`student`) = **10 requests/phút**, `admin` (`teacher`) = **100 requests/phút** (`app.py` dòng 141 chọn `rate_limiter_admin` nếu `role == "admin"`).

Kết quả chạy thực tế với tài khoản `student` / `demo123` tại `POST /auth/token` (token đã che: `eyJhbGciOiJI...z2XLlk`):

```http
# Không có token → 401
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer
x-content-type-options: nosniff
x-frame-options: DENY

{"detail":"Authentication required. Include: Authorization: Bearer <token>"}

# Có token hợp lệ (request #1) → 200
HTTP/1.1 200 OK
x-content-type-options: nosniff
x-frame-options: DENY

{"question":"Explain JWT","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","usage":{"requests_remaining":9,"budget_remaining_usd":1.6e-05}}

# Vòng lặp gửi liên tiếp (request 2..10 → 200 OK, request 11 → 429)
Request 2..10: HTTP/1.1 200 OK
Request 11:
HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795677335
retry-after: 59

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

### Exercise 4.4: Cost Guard

- `04-api-gateway/production/cost_guard.py` theo dõi `input_tokens`, `output_tokens` theo ngày và tính chi phí dựa trên đơn giá token (`PRICE_PER_1K_INPUT_TOKENS`, `PRICE_PER_1K_OUTPUT_TOKENS`), chặn khi vượt ngân sách user (`402 Payment Required`) hoặc ngân sách toàn hệ thống (`503`), cảnh báo ở mốc 80%.
- **Vì sao cần cả Rate Limit và Cost Guard?** Rate limit chỉ giới hạn **tốc độ** (số request/phút), không kiểm soát **độ dài prompt/output** hay chi phí tích luỹ cả ngày/tháng. Một user gửi request dưới ngưỡng rate limit nhưng prompt cực dài (hoặc dùng model đắt) vẫn có thể đốt hết ngân sách LLM.
- **Triển khai production bằng Redis:** Thay dict in-memory bằng key theo chu kỳ trong Redis (vd `budget:{user_id}:{YYYY-MM}` hoặc `cost:{YYYY-MM-DD}`), dùng `GET` để kiểm tra trước khi gọi LLM (vượt ngưỡng → trả `402`), sau khi gọi LLM cộng dồn nguyên tử bằng `INCRBYFLOAT` và đặt `EXPIRE` (vd 32 ngày cho budget tháng / 2 ngày cho budget ngày) để mọi worker/instance dùng chung và tự reset sang chu kỳ mới.

---

## Part 5: Scaling & Reliability

### Exercise 5.1 & 5.2: Health Checks & Graceful Shutdown (`05-scaling-reliability/develop/`)

- **Liveness (`GET /health`) vs Readiness (`GET /ready`):**
  - `/health` kiểm tra process còn sống không (nếu fail → platform **restart** container).
  - `/ready` kiểm tra instance đã sẵn sàng nhận traffic chưa (đã load xong model, chưa shutdown, kết nối DB/Redis bình thường; nếu trả `503` → load balancer **ngừng route traffic** vào instance này nhưng không restart nó).
- **Graceful shutdown:** Khi nhận `SIGTERM`, uvicorn ngừng nhận kết nối mới, hoàn thành các request đang chạy (in-flight), rồi mới chạy `lifespan` shutdown để dọn tài nguyên và thoát.

**Kết quả chạy thực tế (`develop/app.py`):**

```http
# GET /health → 200 OK
{"status":"ok","uptime_seconds":2.7,"version":"1.0.0","environment":"development","timestamp":"2026-11-26T07:15:32.899323+00:00","checks":{"memory":{"status":"ok","used_percent":83.1}}}

# GET /ready → 200 OK
{"ready":true,"in_flight_requests":1}

# Gửi POST /ask?question=Long%20task đồng thời gửi kill -TERM <PID>:
HTTP/1.1 200 OK
{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

Log tắt an toàn của server:
```text
INFO:     Shutting down
INFO:     127.0.0.1:51557 - "POST /ask?question=Long%20task HTTP/1.1" 200 OK
INFO:     Waiting for application shutdown.
2026-11-26 14:15:36,060 INFO 🔄 Graceful shutdown initiated...
2026-11-26 14:15:36,060 INFO ✅ Shutdown complete
INFO:     Application shutdown complete.
INFO:     Finished server process [12084]
```

### Exercise 5.3, 5.4 & 5.5: Stateless Design, Load Balancing & `test_stateless.py`

- **Tại sao không lưu state trong RAM khi scale ngang?** Mỗi instance có vùng nhớ RAM độc lập. Khi Nginx chia tải (round-robin) sang 3 instance, request 1 vào `instance A` còn request 2 vào `instance B` sẽ không thấy lịch sử hội thoại; ngoài ra khi restart hoặc deploy mới, toàn bộ state trong RAM sẽ mất.
- **Giải pháp (`05-scaling-reliability/production/app.py`):** Đưa toàn bộ session/history ra **Redis** (`session:{session_id}` với TTL 3600s), để bất kỳ instance nào nhận request cũng đọc/ghi cùng một trạng thái.

**Kết quả chạy `docker compose -p k5-day14-scaling up -d --build --scale agent=3` và `python test_stateless.py` (cổng `8080`, endpoint `POST /chat`):**

```text
Session ID: f434928a-71c7-4ca4-a03e-9e27d6bee5c2

Request 1: [instance-8f5498]  Q: What is Docker?
Request 2: [instance-750741]  Q: Why do we need containers?
Request 3: [instance-8f5498]  Q: What is Kubernetes?
Request 4: [instance-57a748]  Q: How does load balancing work?
Request 5: [instance-750741]  Q: What is Redis used for?

Total requests: 5
Instances used: {'instance-57a748', 'instance-8f5498', 'instance-750741'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
✅ Session history preserved across all instances via Redis!
```

**Giải thích:** 5 câu hỏi trong cùng một session được Nginx điều phối sang đủ 3 instance khác nhau (`instance-8f5498`, `instance-750741`, `instance-57a748`), nhưng khi gọi `GET /chat/{session_id}/history` vẫn còn nguyên đủ 10 message (5 câu hỏi user + 5 câu trả lời assistant) vì toàn bộ lịch sử được lưu tập trung trong Redis.

---

## Part 3: Cloud Deployment (CP6 — Deploy Agent Part 6)

### Exercise 3.1 / 3.2: Deploy trên nền tảng chính
- **Public URL:** *(UNVERIFIED — chờ deploy thư mục `06-lab-complete/` lên Railway hoặc Render kèm Redis)*
- **Screenshots:** `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png` *(chờ chụp sau khi deploy)*

### So sánh `railway.toml` vs `render.yaml`

| Tiêu chí | `railway.toml` (Railway) | `render.yaml` (Render Blueprint) | Vì sao khác nhau? |
|---|---|---|---|
| **Định dạng & phạm vi** | TOML, cấu hình **một service** (`[build]`, `[deploy]`). | YAML, định nghĩa **nhiều tài nguyên** cùng lúc dưới `services:` (web service + Redis add-on trong cùng file). | Render theo hướng Blueprint (IaC toàn bộ stack từ Git); Railway quản lý project/service linh hoạt qua CLI và Dashboard. |
| **Cách build & runtime** | `[build]` chọn `builder = "DOCKERFILE"` (hoặc `"NIXPACKS"` tự nhận diện ngôn ngữ). | Khai báo rõ `type: web`, `runtime: docker` (hoặc `python` kèm `buildCommand`/`startCommand`), `region`, `plan`. | Render yêu cầu khai báo tường minh hạ tầng (`region`, `plan`, `runtime`) ngay trong Blueprint. |
| **Health check & restart** | `healthcheckPath = "/health"`, `healthcheckTimeout = 30`, `restartPolicyType = "ON_FAILURE"`, `restartPolicyMaxRetries = 3`. | `healthCheckPath: /health`, `autoDeploy: true`. | Railway cho tinh chỉnh trực tiếp chính sách retry khi crash ngay trong `railway.toml`. |
| **Quản lý biến môi trường & secrets** | Không ghi trong `railway.toml`; đặt qua `railway variables set` hoặc Dashboard (kèm reference biến Redis nội bộ). | Khai báo danh sách `envVars:` trong file; secret dùng `generateValue: true` (tự sinh) hoặc `sync: false` (nhập tay trên Dashboard) để không lộ giá trị thật trong git. | Render khai báo schema env vars trong IaC; Railway tách hoàn toàn cấu hình biến khỏi file config. |

### Exercise 3.3: GCP Cloud Run CI/CD Pipeline (`03-cloud-deployment/production-cloud-run/`)

Đọc `cloudbuild.yaml` và `service.yaml`, pipeline CI/CD tự động khi push lên nhánh `main` đi qua 4 bước tuần tự (`waitFor`):
1. **`test` (`python:3.11-slim`):** Cài `requirements.txt` + `pytest` và chạy `pytest tests/ -v`; nếu test fail thì dừng pipeline ngay.
2. **`build` (`gcr.io/cloud-builders/docker`):** Build Docker image gắn 2 tag (`:$COMMIT_SHA` và `:latest`), tái sử dụng layer cache từ `:latest` (`--cache-from`).
3. **`push`:** Đẩy toàn bộ tag lên Google Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **`deploy` (`gcr.io/cloud-builders/gcloud`):** Deploy bản `$COMMIT_SHA` lên Cloud Run (`asia-southeast1`, `min-instances=1` tránh cold start, `max-instances=10`, `512Mi` RAM, `1` CPU, `timeout=60s`), nạp secrets (`OPENAI_API_KEY`, `AGENT_API_KEY`) từ Secret Manager và gắn `livenessProbe` (`/health`) + `startupProbe` (`/ready`) như định nghĩa IaC trong `service.yaml`.

---

## Part 6: Final Project (`06-lab-complete/`)

Kết quả chạy `python check_production_ready.py` (chế độ đầy đủ, có Docker — image `321 MB`, `docker stop` exit code `0` trong `0.6s`):

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```
