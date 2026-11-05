"""Verification script for file upload fix.
Tests:
1. upload one file of each allowed type under 10MB (PNG, JPG, JPEG, WEBP, PDF, AI, EPS, ZIP)
2. an 11MB file gets the size error WITH its actual size ("This file is 11MB, the limit is 10MB")
3. an unsupported type (.exe) gets the type error naming the detected type ("This file is EXE, allowed types are PNG, JPG, PDF, AI, EPS, ZIP")
4. same file twice in a row dedupes (shows once)
5. filenames with spaces and dashes parse correctly
"""
import io
import json
import os
import sys
import urllib.request
import urllib.parse

sys.path.insert(0, ".")
from app.chat.uploads import validate_upload, format_file_size, ALLOWED_EXTS, IMAGE_EXTS

FAILURES = []

def check(name, ok, detail=""):
    if ok:
        print(f"  PASS: {name}")
    else:
        FAILURES.append(name)
        print(f"  FAIL: {name} :: {detail}")

print("=== 1. Unit tests: validate_upload & format_file_size ===")
# Formatted size
check("11MB exact", format_file_size(11 * 1024 * 1024) == "11MB", format_file_size(11 * 1024 * 1024))
check("11.5MB", format_file_size(int(11.5 * 1024 * 1024)) == "11.5MB", format_file_size(int(11.5 * 1024 * 1024)))
check("12MB", format_file_size(12 * 1024 * 1024) == "12MB", format_file_size(12 * 1024 * 1024))

# Valid files for each allowed extension
for ext in ["png", "jpg", "jpeg", "webp", "pdf", "ai", "eps", "zip"]:
    fn = f"sample_design.{ext}"
    res = validate_upload(fn, 500 * 1024)
    check(f"allowed type under 10MB: {ext}", res is None, f"got {res}")

# Filename with spaces and dashes
fn_screenshot = "Screenshot From 2026-11-06 01-01-24.png"
check("filename with spaces and dashes accepted", validate_upload(fn_screenshot, 2 * 1024 * 1024) is None)

# 11MB file gets specific size error with actual size
err_11mb = validate_upload("big_image.png", 11 * 1024 * 1024)
expected_11mb = "This file is 11MB, the limit is 10MB"
check("11MB file gets specific size error with actual size", err_11mb == expected_11mb, f"got: {err_11mb}")

# Unsupported types get specific type error naming detected type
err_exe = validate_upload("installer.exe", 1024)
expected_exe = "This file is EXE, allowed types are PNG, JPG, PDF, AI, EPS, ZIP"
check("unsupported .exe gets type error naming EXE", err_exe == expected_exe, f"got: {err_exe}")

err_no_ext = validate_upload("unknown_file", 1024)
expected_no_ext = "This file is unknown, allowed types are PNG, JPG, PDF, AI, EPS, ZIP"
check("unsupported no ext gets unknown", err_no_ext == expected_no_ext, f"got: {err_no_ext}")


print("\n=== 2. HTTP API tests against running server (http://localhost:8001) ===")

def post_multipart(url, fields, files):
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    body = io.BytesIO()
    for k, v in fields.items():
        body.write(f"--{boundary}\r\n".encode())
        body.write(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode())
        body.write(f"{v}\r\n".encode())
    for k, (filename, content, content_type) in files.items():
        body.write(f"--{boundary}\r\n".encode())
        body.write(f'Content-Disposition: form-data; name="{k}"; filename="{filename}"\r\n'.encode())
        body.write(f"Content-Type: {content_type}\r\n\r\n".encode())
        body.write(content)
        body.write(b"\r\n")
    body.write(f"--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        url,
        data=body.getvalue(),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())

api_url = "http://localhost:8001/api/chat/upload"

# Test all 8 allowed types through the actual HTTP API
dummy_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
for ext in ["png", "jpg", "jpeg", "webp", "pdf", "ai", "eps", "zip"]:
    fn = f"test_upload.{ext}"
    mime = "image/png" if ext == "png" else ("application/pdf" if ext == "pdf" else "application/octet-stream")
    status, data = post_multipart(api_url, {"session_id": "test-verify-all"}, {"file": (fn, dummy_content, mime)})
    check(f"HTTP upload {ext} succeeds", status == 200 and data.get("ok") is True, f"status={status}, data={data}")

# Test reproducing user issue: valid screenshot with spaces & dashes
fn_user_screenshot = "Screenshot From 2026-11-06 01-01-24.png"
status, data = post_multipart(api_url, {"session_id": "test-verify-screenshot"}, {"file": (fn_user_screenshot, dummy_content, "image/png")})
check("HTTP upload 'Screenshot From 2026-11-06 01-01-24.png' succeeds", status == 200 and data.get("ok") is True, f"status={status}, data={data}")
check("HTTP upload stored image is retrievable", bool(data.get("stored")), f"stored={data.get('stored')}")
if data.get("stored"):
    file_url = f"http://localhost:8001/api/chat/file?session_id=test-verify-screenshot&name={data['stored']}"
    with urllib.request.urlopen(file_url) as file_resp:
        check("HTTP /api/chat/file returns image 200 OK", file_resp.status == 200)

# Test 11MB file upload gets size error WITH actual size
large_data = b"X" * (11 * 1024 * 1024)
status, data = post_multipart(api_url, {"session_id": "test-verify-size"}, {"file": ("oversized.png", large_data, "image/png")})
check("HTTP upload 11MB file rejected", data.get("ok") is False, f"data={data}")
check("HTTP upload 11MB error has actual size & 10MB limit", data.get("detail") == expected_11mb, f"got: {data.get('detail')}")

# Test unsupported type (.exe) gets type error naming detected type
status, data = post_multipart(api_url, {"session_id": "test-verify-exe"}, {"file": ("virus.exe", b"MZ...", "application/x-msdownload")})
check("HTTP upload .exe rejected", data.get("ok") is False, f"data={data}")
check("HTTP upload .exe error names EXE and allowed types", data.get("detail") == expected_exe, f"got: {data.get('detail')}")

# Test dedupe: uploading the same file twice in a row in the same session
dedupe_sess = "test-verify-dedupe"
status1, data1 = post_multipart(api_url, {"session_id": dedupe_sess}, {"file": ("logo_dedupe.png", dummy_content, "image/png")})
status2, data2 = post_multipart(api_url, {"session_id": dedupe_sess}, {"file": ("logo_dedupe.png", dummy_content, "image/png")})
check("HTTP upload 1st succeeds", data1.get("ok") is True)
check("HTTP upload 2nd succeeds", data2.get("ok") is True)
# Since the same file was attached twice in a row, the attached set note is not spammed
check("HTTP dedupe: quote does not list duplicate files", "logo_dedupe.png, logo_dedupe.png" not in data2.get("reply", ""))

print(f"\nUpload verification complete: {len(FAILURES)} failures.")
if FAILURES:
    sys.exit(1)
