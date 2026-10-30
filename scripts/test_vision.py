"""Vision + upload-helper tests (no fastapi, no model key needed)."""
import os
import sys
import tempfile

sys.path.insert(0, ".")
from app.chat.uploads import (resolve_image, save_upload, safe_filename,
                              validate_upload)
from app.chat.vision import describe_image

FAILURES = []


def check(name, ok, detail=""):
    if ok:
        print(f"  ok: {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL {name} :: {detail}")


# --- vision: describe only what is visible, fail soft ---
check("stub description passes through",
      describe_image(b"\x89PNG...", "image/png",
                     llm_fn=lambda d, m: "A red logo on white.")
      == "A red logo on white.")
check("no llm_fn -> None, never a crash",
      describe_image(b"\x89PNG...", "image/png") is None)
check("non-image mime is stored, never described",
      describe_image(b"%PDF...", "application/pdf",
                     llm_fn=lambda d, m: "should not run") is None)
check("llm failure -> None",
      describe_image(b"\x89PNG...", "image/png",
                     llm_fn=lambda d, m: (_ for _ in ()).throw(
                         RuntimeError("no key"))) is None)
check("empty data -> None",
      describe_image(b"", "image/png",
                     llm_fn=lambda d, m: "x") is None)
check("blank description -> None",
      describe_image(b"\x89PNG...", "image/png",
                     llm_fn=lambda d, m: "   ") is None)

# --- uploads: validation + storage ---
check("png accepted", validate_upload("logo.png", 1000) is None)
check("ai accepted", validate_upload("art.ai", 1000) is None)
check("exe refused", validate_upload("run.exe", 1000) is not None)
check("no extension refused", validate_upload("logo", 1000) is not None)
check("over 10MB refused",
      validate_upload("big.png", 11 * 1024 * 1024) is not None)
check("traversal stripped",
      "/" not in safe_filename("../../etc/passwd")
      and ".." not in safe_filename("../../etc/passwd"))
with tempfile.TemporaryDirectory() as td:
    stored = save_upload(td, "sess-1", "logo.png", b"PNGDATA")
    check("file written under session folder",
          os.path.isfile(os.path.join(td, "sess-1", stored)))
    with open(os.path.join(td, "sess-1", stored), "rb") as fh:
        check("bytes round-trip", fh.read() == b"PNGDATA")
    check("stored image resolves",
          resolve_image(td, "sess-1", stored) is not None)
    check("traversal name never resolves",
          resolve_image(td, "sess-1", "../sess-1/" + stored) is None
          and resolve_image(td, "sess-1", "../../etc/passwd") is None)
    check("missing file never resolves",
          resolve_image(td, "sess-1", "deadbeef-nope.png") is None)
    pdf_stored = save_upload(td, "sess-1", "art.pdf", b"PDFDATA")
    check("non-image never resolves",
          resolve_image(td, "sess-1", pdf_stored) is None)
    check("other session never resolves",
          resolve_image(td, "sess-2", stored) is None)

print(f"VISION: {len(FAILURES)} failed")
if FAILURES:
    sys.exit(1)
print("All vision/upload cases passed.")
