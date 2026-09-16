import sys
import os
import time
import json
import urllib.request
import traceback

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CORE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "core")
if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)

import layma_runner

API_TOKEN = "050dc0233de6e4566264724bf5c94687"

def create_shortlink(target_url: str) -> str:
    api_url = f"https://api.layma.net/api/admin/shortlink/quicklink?tokenUser={API_TOKEN}&format=json&url={urllib.parse.quote(target_url)}&link_du_phong={urllib.parse.quote(target_url)}"
    req = urllib.request.Request(api_url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    })
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        if data.get("success") and data.get("html"):
            return data["html"]
        raise RuntimeError(f"Tạo link thất bại: {data}")

def run_benchmark(num_runs: int = 3):
    import urllib.parse
    print("=" * 70)
    print(f"🔥 BẮT ĐẦU BENCHMARK ĐO TỈ LỆ THẤT BẠI LAYMA.NET ({num_runs} LƯỢT CHẠY)")
    print("=" * 70)

    results = []

    for i in range(1, num_runs + 1):
        test_id = f"test_{int(time.time())}_{i}"
        target_dest = f"https://httpbin.org/get?benchmark_id={test_id}"
        
        print(f"\n[{i}/{num_runs}] 🔹 Đang tạo shortlink cho mục tiêu: {target_dest}")
        try:
            shortlink = create_shortlink(target_dest)
            print(f"   Link LayMa tạo ra: {shortlink}")
        except Exception as e:
            print(f"   ❌ Lỗi khi gọi API tạo link: {e}")
            results.append({
                "run": i,
                "shortlink": "N/A",
                "target": target_dest,
                "actual": None,
                "duration": 0,
                "success": False,
                "error": f"API create error: {e}"
            })
            continue

        print(f"[{i}/{num_runs}] 🚀 Đang kích hoạt layma_runner (Headless: True)...")
        t0 = time.time()
        actual_dest = None
        err_msg = None
        try:
            actual_dest = layma_runner.run(shortlink, headless=True)
        except Exception as e:
            err_msg = str(e)
            traceback.print_exc()

        dur = round(time.time() - t0, 1)
        is_success = bool(actual_dest and "httpbin.org" in actual_dest and "layma.net" not in actual_dest)
        
        if is_success:
            print(f"[{i}/{num_runs}] ✅ THÀNH CÔNG trong {dur}s! Link đích: {actual_dest}")
        else:
            print(f"[{i}/{num_runs}] ❌ THẤT BẠI sau {dur}s! Kết quả: {actual_dest} | Lỗi: {err_msg}")

        results.append({
            "run": i,
            "shortlink": shortlink,
            "target": target_dest,
            "actual": actual_dest,
            "duration": dur,
            "success": is_success,
            "error": err_msg
        })

        if i < num_runs:
            print("⏳ Chờ 3s trước lượt kế tiếp...")
            time.sleep(3)

    # Summary calculation
    total = len(results)
    success_count = sum(1 for r in results if r["success"])
    fail_count = total - success_count
    fail_rate = (fail_count / total * 100) if total > 0 else 0
    succ_rate = (success_count / total * 100) if total > 0 else 0
    avg_dur = round(sum(r["duration"] for r in results) / total, 1) if total > 0 else 0

    print("\n" + "=" * 70)
    print("📊 BÁO CÁO KẾT QUẢ BENCHMARK TỈ LỆ THẤT BẠI LAYMA.NET")
    print("=" * 70)
    print(f"  ✦ Tổng số lượt thử nghiệm:   {total}")
    print(f"  ✦ Số lượt thành công:         {success_count} ({succ_rate:.1f}%)")
    print(f"  ✦ Số lượt thất bại:           {fail_count} ({fail_rate:.1f}%)")
    print(f"  ✦ Thời gian trung bình/lượt:  {avg_dur}s")
    print("-" * 70)
    print(f"{'Lượt':<6}{'Shortlink':<28}{'Thời gian':<12}{'Trạng thái':<14}{'Ghi chú'}")
    print("-" * 70)
    for r in results:
        status_str = "✔ PASS" if r["success"] else "✖ FAIL"
        note = r["actual"] if r["success"] else (r["error"] or "Không lấy được đích")
        print(f"{r['run']:<6}{r['shortlink']:<28}{str(r['duration']) + 's':<12}{status_str:<14}{note}")
    print("=" * 70 + "\n")

    # Save summary to json
    with open("benchmark_layma_report.json", "w", encoding="utf-8") as f_rep:
        json.dump({
            "total": total,
            "success": success_count,
            "fail": fail_count,
            "fail_rate_pct": fail_rate,
            "success_rate_pct": succ_rate,
            "avg_duration_sec": avg_dur,
            "details": results
        }, f_rep, indent=2, ensure_ascii=False)
    print("[*] Đã lưu báo cáo chi tiết vào benchmark_layma_report.json")

if __name__ == "__main__":
    runs = 3
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        runs = int(sys.argv[1])
    run_benchmark(runs)
