# PaddleOCR sidecar — fallback OCR for InDataFlow

Lightweight FastAPI service that runs PaddleOCR on document images/PDFs.
Called by `cargo-api-worker-mt` when Google Cloud Vision fails (billing disabled, quota exceeded, etc.).

## Quick start

```bash
cp .env.example .env  # edit PADDLE_OCR_API_SECRET
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8791
```

## Docker

```bash
docker build -t paddle-ocr-service .
docker run -d -p 8791:8791 \
  -e PADDLE_OCR_API_SECRET=your-secret \
  paddle-ocr-service
```

## API

### `POST /v1/ocr`

Accepts multipart form with field `file` (PDF, JPEG, PNG, WebP).
Returns JSON with extracted text.

```bash
curl -X POST http://localhost:8791/v1/ocr \
  -H "Authorization: Bearer your-secret" \
  -F "file=@invoice.jpg"
```

Response:
```json
{
  "text": "EXPORTER: ... INVOICE NO: ...",
  "chars": 1247,
  "pages": 1,
  "engine": "paddleocr"
}
```

## Env vars

| Var | Default | Description |
|-----|---------|-------------|
| `PADDLE_OCR_API_SECRET` | — | Required. Must match Worker's `PADDLE_OCR_API_SECRET`. |
| `PADDLE_OCR_MAX_MB` | 15 | Max upload file size in MB. |
