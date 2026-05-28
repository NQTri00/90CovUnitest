import urllib.request
import urllib.parse
import json
import time
import sys

def make_request(url, method="GET", data=None):
    req = urllib.request.Request(url, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
        json_data = json.dumps(data).encode("utf-8")
        req.data = json_data
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} - {e.read().decode('utf-8')}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

def main():
    base_url = "http://localhost:8000"
    print("Step 1: Start Agent Run on 'demo_project'")
    run_res = make_request(f"{base_url}/api/run", "POST", {"repo_path": "demo_project"})
    run_id = run_res["run_id"]
    print(f"Run ID: {run_id}")

    print("\nStep 2: Polling status until 'awaiting_user_approval'")
    while True:
        status_res = make_request(f"{base_url}/api/status/{run_id}")
        status = status_res.get("status")
        progress = status_res.get("progress")
        prog_percent = progress.get("percentage") if progress else 0
        prog_msg = progress.get("message") if progress else "N/A"
        print(f"Status: {status} | Progress: {prog_percent}% - {prog_msg}")

        if status == "awaiting_user_approval":
            print("\nSuccessfully reached human-in-the-loop checkpoint!")
            test_plan = status_res.get("test_plan")
            test_cases = test_plan.get("test_cases", [])
            print(f"Found {len(test_cases)} planned test cases:")
            for tc in test_cases:
                print(f" - {tc['test_id']} ({tc['service']} -> {tc['method']})")
            
            selected_ids = [tc["test_id"] for tc in test_cases]
            break
        elif status == "failed":
            print(f"Run failed early: {status_res.get('error')}")
            sys.exit(1)
        elif status == "completed":
            print("Run completed directly without pausing?")
            sys.exit(1)
        time.sleep(1)

    print("\nStep 3: Resume Run with selected test cases")
    resume_res = make_request(f"{base_url}/api/resume/{run_id}", "POST", {"selected_test_ids": selected_ids})
    print(f"Resume response: {resume_res}")

    print("\nStep 4: Polling status until 'completed'")
    while True:
        status_res = make_request(f"{base_url}/api/status/{run_id}")
        status = status_res.get("status")
        progress = status_res.get("progress")
        prog_percent = progress.get("percentage") if progress else 0
        prog_msg = progress.get("message") if progress else "N/A"
        print(f"Status: {status} | Progress: {prog_percent}% - {prog_msg}")

        if status == "completed":
            print("\nPipeline run completed successfully!")
            coverage_report = status_res.get("coverage_report")
            print(f"Final Total Coverage: {coverage_report.get('total_coverage')}%")
            print("History of execution steps:")
            for item in status_res.get("history", []):
                print(f" - {item}")
            break
        elif status == "failed":
            print(f"Pipeline failed: {status_res.get('error')}")
            sys.exit(1)
        time.sleep(1)

if __name__ == "__main__":
    main()
