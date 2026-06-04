"""Lightweight PaddleOCR sidecar — returns extracted text from images/PDFs."""

import io
import os
import tempfile
import traceback
from typing import Optional

import fitz  # PyMuPDF
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from paddleocr import PaddleOCR

app = FastAPI(title="PaddleOCR Sidecar", version="1.0.0")

_ocr: Optional[PaddleOCR] = None


def _get_ocr() -> PaddleOCR:
    global _ocr
    if _ocr is None:
        use_angle = os.environ.get("PADDLE_OCR_USE_ANGLE_CLS", "true").lower() in ("1", "true", "yes")
        lang = os.environ.get("PADDLE_OCR_LANG", "en").strip()
        _ocr = PaddleOCR(use_angle_cls=use_angle, lang=lang, show_log=False)
    return _ocr


def _require_secret(request: Request) -> None:
    secret = os.environ.get("PADDLE_OCR_API_SECRET", "").strip()
    if not secret:
        raise HTTPException(500, "PADDLE_OCR_API_SECRET is not configured on server")
    auth = request.headers.get("authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth else ""
    if token != secret:
        raise HTTPException(401, "invalid_or_missing_bearer_token")


def _max_bytes() -> int:
    raw = os.environ.get("PADDLE_OCR_MAX_MB", "15").strip()
    try:
        return max(1, min(50, int(raw))) * 1024 * 1024
    except ValueError:
        return 15 * 1024 * 1024


def _infer_mime(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith((".png",)):
        return "image/png"
    if lower.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith((".tiff", ".tif")):
        return "image/tiff"
    if lower.endswith(".bmp"):
        return "image/bmp"
    return "application/octet-stream"


def _run_paddle_on_bytes(data: bytes, mime: str) -> str:
    ocr = _get_ocr()

    if mime == "application/pdf" or (
        mime == "application/octet-stream" and data[:4] == b"%PDF"
    ):
        doc = fitz.open(stream=data, filetype="pdf")
        chunks: list[str] = []
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            pix = page.get_pixmap(dpi=300)
            img_bytes = pix.tobytes("png")
            with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as tmp:
                tmp.write(img_bytes)
                tmp.flush()
                result = ocr.ocr(tmp.name, cls=True)
            page_text = _flatten_ocr(result)
            if page_text.strip():
                chunks.append(page_text.strip())
        doc.close()
        return "\n\n".join(chunks)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        result = ocr.ocr(tmp.name, cls=True)
    return _flatten_ocr(result)


def _flatten_ocr(result) -> str:
    if not result:
        return ""
    lines: list[str] = []
    for page_result in result:
        if not page_result:
            continue
        for line in page_result:
            text = line[1][0] if len(line) > 1 and isinstance(line[1], (list, tuple)) else ""
            if text and isinstance(text, str):
                lines.append(text.strip())
    return "\n".join(lines)


@app.post("/v1/ocr")
async def ocr_endpoint(request: Request) -> JSONResponse:
    _require_secret(request)

    max_bytes = _max_bytes()
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > max_bytes:
        raise HTTPException(413, f"file too large (max {max_bytes // (1024*1024)} MB)")

    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        file_field = form.get("file")
        if not file_field or not hasattr(file_field, "read"):
            raise HTTPException(400, "missing file field")
        data = await file_field.read()
        filename = getattr(file_field, "filename", "upload") or "upload"
    else:
        data = await request.body()
        filename = request.headers.get("x-filename", "upload")

    if len(data) > max_bytes:
        raise HTTPException(413, f"file too large (max {max_bytes // (1024*1024)} MB)")
    if not data:
        raise HTTPException(400, "empty body")

    mime = _infer_mime(filename)

    try:
        text = _run_paddle_on_bytes(data, mime)
    except Exception:
        tb = traceback.format_exc()[-2000:]
        raise HTTPException(500, f"paddleocr_failed:{tb}")

    return JSONResponse({
        "text": text,
        "chars": len(text),
        "pages": text.count("\n\n") + 1 if text.strip() else 0,
        "engine": "paddleocr",
    })


@app.get("/v1/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "paddle-ocr"})


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8791"))
    uvicorn.run("server:app", host=host, port=port, reload=False)
