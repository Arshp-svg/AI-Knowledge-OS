import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import json
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:8000"

def test_security_headers():
    print("\n--- 1. Testing Production Security Headers ---")
    req = urllib.request.Request(f"{BASE_URL}/")
    with urllib.request.urlopen(req) as resp:
        headers = dict(resp.headers)
        print("Response Headers:")
        for k in ["x-content-type-options", "x-frame-options", "x-xss-protection", "referrer-policy"]:
            val = headers.get(k)
            print(f"  {k}: {val}")
            assert val is not None, f"Missing header: {k}"
    print(" Security headers verified successfully!")

def test_file_upload_validation():
    print("\n--- 2. Testing File Upload Validation & Security Gates ---")
    # Test 2a: Fake PDF (invalid magic bytes)
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    fake_body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="fake_document.pdf"\r\n'
        f"Content-Type: application/pdf\r\n\r\n"
        f"This is plain text pretending to be a PDF!\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{BASE_URL}/documents/upload",
        data=fake_body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST"
    )

    try:
        urllib.request.urlopen(req)
        print("❌ FAILED: Fake PDF was accepted without rejection!")
        sys.exit(1)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f" Status {e.code}: {body}")
        assert e.code == 400, f"Expected 400, got {e.code}"
        assert "not an authentic PDF" in body, "Expected authentic PDF error message"
        print(" Fake PDF without %PDF- magic bytes was correctly rejected (HTTP 400)!")

def test_rate_limiting():
    print("\n--- 3. Testing Sliding-Window Rate Limiting (SlowAPI) ---")
    # The limit on /ask/ is 20/minute. Firing 25 rapid requests should trigger HTTP 429.
    payload = json.dumps({"question": "What is an attention mechanism?", "top_k": 1}).encode("utf-8")
    
    rate_limited = False
    rate_limit_response = None
    successful_requests = 0

    print("Firing rapid sequential requests to /ask/...")
    for i in range(1, 26):
        req = urllib.request.Request(
            f"{BASE_URL}/ask/",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req) as resp:
                successful_requests += 1
                if i % 5 == 0:
                    print(f"  Request {i}: HTTP {resp.status} (allowed)")
        except urllib.error.HTTPError as e:
            if e.code == 429:
                rate_limited = True
                rate_limit_response = e.read().decode("utf-8")
                print(f"  Request {i}: Throttled! HTTP 429 Too Many Requests")
                print(f"  Throttling Response: {rate_limit_response}")
                break
            else:
                print(f"  Unexpected HTTP error {e.code}: {e.read().decode('utf-8')}")
                break

    assert rate_limited, "Expected rate limit (HTTP 429) to be triggered within 25 requests!"
    print(f" Rate limiter cleanly throttled excessive requests (Allowed: {successful_requests}, then 429)!")

if __name__ == "__main__":
    try:
        test_security_headers()
        test_file_upload_validation()
        test_rate_limiting()
        print("\n ALL DAY 6 SECURITY & RATE LIMITING TESTS PASSED!")
    except Exception as exc:
        print(f"\n❌ Test failed with error: {exc}")
        sys.exit(1)
