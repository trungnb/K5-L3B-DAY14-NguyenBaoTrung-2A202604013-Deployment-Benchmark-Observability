# Deployment Information — Day 14 (K5)

## Public URL

https://k5-day14-agent-e1jt.onrender.com

## Platform

**Render** (Region: `Singapore (Southeast Asia)`, Plan: `Free`)
- **Web Service (`k5-day14-agent`):** Docker runtime, Root Directory `06-lab-complete`, Health Check Path `/health`
- **Key Value / Redis (`k5-day14-redis`):** Managed Valkey 8.1.10 (`allkeys-lru`), kết nối nội bộ cùng region qua `REDIS_URL`

> **Lưu ý gói Free:** Render Free Web Service tự động sleep sau ~15 phút không có traffic; request đầu tiên sau khi ngủ có thể mất ~30–50 giây để cold start.

## Test Commands (4 lệnh tự kiểm CP6)

Đặt `BASE` và `AGENT_API_KEY` (đã cấu hình trên Render Dashboard, không lưu trong repo):

```bash
BASE="https://k5-day14-agent-e1jt.onrender.com"

# 1. Liveness check → 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"
# Kết quả thực tế: 200  ({"status":"ok","environment":"production"})

# 2. Readiness check (kiểm kết nối Redis trên cloud) → 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"
# Kết quả thực tế: 200  ({"status":"ready"})

# 3. Gọi /ask không có API key → 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Hello"}'
# Kết quả thực tế: 401

# 4. Gọi /ask với API key hợp lệ → 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'
# Kết quả thực tế: 200
```

## Environment Variables Set (trên Render Dashboard — không commit giá trị thật)

- `PORT` *(Render tự inject)*
- `ENVIRONMENT` (`production`)
- `REDIS_URL` *(Internal Key Value URL của `k5-day14-redis`)*
- `AGENT_API_KEY` *(secret random, đặt trên Dashboard)*
- `RATE_LIMIT_PER_MINUTE` (`10`)
- `DAILY_BUDGET_USD` (`1.0`)

## Screenshots

- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
