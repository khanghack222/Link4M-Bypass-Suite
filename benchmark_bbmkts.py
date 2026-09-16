import sys
import os
import time
import json
import traceback

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CORE_DIR = os.path.join(ROOT_DIR, "src", "core")
if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)

import bbmkts_runner

def run_benchmark(num_runs: int = 3, target_link: str = "https://bbmkts.com/go/3p82s"):
    print("=" * 70)
    print(f"🔥 BẮT ĐẦU BENCHMARK ĐO TỈ LỆ THẤT BẠI BBMKTS ({num_runs} LƯỢT CHẠY)")
    print(f"🎯 Target URL: {target_link}")
    print("=" * 70)

    results = []

    for i in range(1, num_runs + 1):
        print(f"\n[{i}/{num_runs}] 🚀 Đang khởi chạy bbmkts_runner (Headless: True)...")
        t0 = time.time()
        actual_dest = None
        err_msg = None
        try:
            actual_dest = bbmkts_runner.run(target_link, headless=True)
        except Exception as e:
            err_msg = str(e)
            traceback.print_exc()

        dur = round(time.time() - t0, 1)
        is_success = bool(actual_dest and "bbmkts.com" not in actual_dest and actual_dest.startswith("http"))
        
        if is_success:
            print(f"[{i}/{num_runs}] ✅ THÀNH CÔNG trong {dur}s! Link đích: {actual_dest}")
        else:
            print(f"[{i}/{num_runs}] ❌ THẤT BẠI sau {dur}s! Kết quả: {actual_dest} | Lỗi: {err_msg}")

        results.append({
            "run": i,
            "target": target_link,
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
    print("📊 BÁO CÁO KẾT QUẢ BENCHMARK TỈ LỆ THẤT BẠI BBMKTS")
    print("=" * 70)
    print(f"🔹 Tổng số lượt chạy:     {total}")
    print(f"✅ Thành công:            {success_count} ({succ_rate:.1f}%)")
    print(f"❌ Thất bại:              {fail_count} ({fail_rate:.1f}%)")
    print(f"⏱ Thời gian TB/lượt:     {avg_dur}s")
    print("-" * 70)
    print("Chi tiết từng lượt:")
    for r in results:
        status_icon = "✅" if r["success"] else "❌"
        print(f"  {status_icon} Lượt #{r['run']}: {r['duration']}s | Đích: {r['actual']} | Lỗi: {r['error']}")
    print("=" * 70)

    report_path = os.path.join(ROOT_DIR, "benchmark_bbmkts_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "total": total,
            "success_count": success_count,
            "fail_count": fail_count,
            "success_rate": succ_rate,
            "fail_rate": fail_rate,
            "avg_duration": avg_dur,
            "runs": results
        }, f, indent=2, ensure_ascii=False)
    print(f"📄 Báo cáo chi tiết đã lưu tại: {report_path}")

if __name__ == "__main__":
    runs = 3
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        runs = int(sys.argv[1])
    target = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2].startswith("http") else "https://bbmkts.com/go/3p82s"
    run_benchmark(runs, target)
