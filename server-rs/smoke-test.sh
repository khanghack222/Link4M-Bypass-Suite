#!/usr/bin/env bash
# Smoke test cho bypass-server: 23 check, không cần Chrome.
#
#   BASE=http://127.0.0.1:8080 ./smoke-test.sh
#   BASE=http://127.0.0.1:8080 API_KEY=secret ./smoke-test.sh
#
# Chỉ dùng curl + python3 (không cần jq). Mỗi check in PASS/FAIL và script
# thoát 1 nếu có bất kỳ check nào trượt.
set -u

BASE="${BASE:-http://127.0.0.1:8080}"
API_KEY="${API_KEY:-}"
PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null || { echo "cần python3 trong PATH"; exit 2; }

pass=0
fail=0
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

auth=()
if [ -n "$API_KEY" ]; then
    auth=(-H "x-api-key: $API_KEY")
fi

# check <tên> <giá trị mong đợi> <giá trị thực>
check() {
    local name="$1" want="$2" got="$3"
    if [ "$want" = "$got" ]; then
        pass=$((pass + 1))
        printf 'PASS  %s\n' "$name"
    else
        fail=$((fail + 1))
        printf 'FAIL  %s (muốn %s, được %s)\n' "$name" "$want" "$got"
    fi
}

# jget <file> <biểu thức python trên `d`>
jget() {
    "$PY" - "$1" "$2" <<'PY'
import json, sys
path, expr = sys.argv[1], sys.argv[2]
try:
    with open(path, encoding='utf-8') as fh:
        d = json.load(fh)
except Exception:
    print('__parse_error__')
    raise SystemExit(0)
try:
    print(eval(expr, {'d': d, 'len': len, 'sorted': sorted}))
except Exception:
    print('__missing__')
PY
}

# status <method> <path> [body] [--] [curl args...]
status() {
    local method="$1" path="$2" body="${3:-}"
    shift 3 2>/dev/null || shift $#
    if [ -n "$body" ]; then
        curl -s -o "$tmp/body.json" -w '%{http_code}' -X "$method" \
            "$BASE$path" -H 'content-type: application/json' \
            "${auth[@]}" "$@" --data-binary "$body"
    else
        curl -s -o "$tmp/body.json" -w '%{http_code}' -X "$method" \
            "$BASE$path" "${auth[@]}" "$@"
    fi
}

# status_file <method> <path> <file> [curl args...]
status_file() {
    local method="$1" path="$2" file="$3"
    shift 3
    curl -s -o "$tmp/body.json" -w '%{http_code}' -X "$method" "$BASE$path" \
        -H 'content-type: application/json' "${auth[@]}" \
        --data-binary "@$file" "$@"
}

echo "== bypass-server smoke @ $BASE"

check "GET /health -> 200" 200 "$(status GET /health "" )"
check "health.status = ok" "ok" "$(jget "$tmp/body.json" "d['status']")"
check "health.workers = 1" "1" "$(jget "$tmp/body.json" "d['workers']")"

check "GET /api/v1/supported -> 200" 200 "$(status GET /api/v1/supported "")"
check "supported = 6 provider" "6" "$(jget "$tmp/body.json" "len(d['supported'])")"
check "DECODE không lộ ra ngoài" "False" \
    "$(jget "$tmp/body.json" "'DECODE' in d['supported']")"

check "GET / -> 200" 200 "$(status GET / "")"
check "root.status = online" "online" "$(jget "$tmp/body.json" "d['status']")"

fast='{"url":"https://bbmkts.com/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS9zbW9rZQ==","wait":true}'
check "POST /api/v1/bypass fast decode -> 200" 200 \
    "$(status POST /api/v1/bypass "$fast")"
check "decode.status = success" "success" \
    "$(jget "$tmp/body.json" "d['status']")"
check "decode.destination_url" "https://example.com/smoke" \
    "$(jget "$tmp/body.json" "d['destination_url']")"
check "decode.provider = decode" "decode" \
    "$(jget "$tmp/body.json" "d['provider']")"

check "GET /api/v1/bypass?url=... -> 200" 200 \
    "$(status GET "/api/v1/bypass?url=https://bbmkts.com/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS9n&wait=1" "")"
check "GET decode.destination_url" "https://example.com/g" \
    "$(jget "$tmp/body.json" "d['destination_url']")"

check "provider lạ -> 400" 400 \
    "$(status POST /api/v1/bypass '{"url":"https://unknownlink.com/x","wait":true}')"
check "url rỗng -> 400" 400 \
    "$(status POST /api/v1/bypass '{"url":"","wait":true}')"
check "thiếu field url -> 422" 422 \
    "$(status POST /api/v1/bypass '{"wait":true}')"
check "JSON hỏng -> 400" 400 \
    "$(status POST /api/v1/bypass '{oops')"
check "job không tồn tại -> 404" 404 \
    "$(status GET /api/v1/jobs/khong-co-that "")"

batch='{"urls":["https://bbmkts.com/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS9h","https://bbmkts.com/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS9i"],"wait":true}'
check "POST /api/v1/batch 2 link -> 200" 200 \
    "$(status POST /api/v1/batch "$batch")"
check "batch.count = 2" "2" "$(jget "$tmp/body.json" "d['count']")"

# 51 URL: dựng bằng python để khỏi lặp tay
"$PY" - > "$tmp/big.json" <<'PY'
import json
print(json.dumps({"urls": ["https://bbmkts.com/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS94"] * 51}))
PY
check "batch 51 URL -> 400" 400 \
    "$(status_file POST /api/v1/batch "$tmp/big.json")"

# body > 1 MB
"$PY" - > "$tmp/huge.json" <<'PY'
import json
print(json.dumps({"url": "https://bbmkts.com/go/file/" + "A" * 1_100_000}))
PY
check "body > 1MB -> 413" 413 \
    "$(status_file POST /api/v1/bypass "$tmp/huge.json")"

echo "== $pass PASS / $fail FAIL"
[ "$fail" -eq 0 ] || exit 1
