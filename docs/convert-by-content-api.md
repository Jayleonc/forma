# Convert-by-Content API Documentation

## Overview

The `/api/v1/convert-by-content` endpoint allows clients to submit Markdown content directly for processing, without requiring file upload or URL-based download. This is particularly useful for Git Sync and Editor documents that already have Markdown content stored in the database.

## Key Features

- **Direct Markdown submission**: No file download required
- **Async task model**: Returns immediately with `task_id`, processes in background
- **Callback-based**: Results delivered via HTTP callback
- **Size limits**: Configurable maximum content size (default 2MB)
- **Secure logging**: Content not logged in full, only metadata and preview
- **Compatible callbacks**: Uses same callback format as `/api/v1/convert`

## Endpoint Specification

### Request

**URL**: `POST /api/v1/convert-by-content`

**Headers**:

- `Content-Type: application/json`

**Request Body**:

```json
{
  "request_id": "string (required)",
  "markdown_content": "string (required)",
  "callback_url": "string (required, must be valid HTTP/HTTPS URL)",
  "content_type": "string (optional, default: text/markdown)",
  "strategy": "string (optional, default: auto, values: auto|fast|deep)"
}
```

**Field Descriptions**:

- `request_id`: Unique identifier for idempotency and correlation with your system
- `markdown_content`: The Markdown content to process (max size configurable via `FORMA_MAX_INLINE_MD_BYTES`)
- `callback_url`: URL where Forma will POST the results
- `content_type`: Content type hint (currently only `text/markdown` supported)
- `strategy`: Processing strategy (currently ignored for inline markdown, always uses basic normalization)

### Immediate Response

**Status Code**: `202 Accepted`

**Response Body**:

```json
{
  "task_id": "uuid-string",
  "status": "processing"
}
```

### Callback (Async Result)

Forma will POST to your `callback_url` when processing completes:

**Success Callback**:

```json
{
  "request_id": "your-request-id",
  "status": "completed",
  "markdown": "processed markdown content",
  "error": null
}
```

**Failure Callback**:

```json
{
  "request_id": "your-request-id",
  "status": "failed",
  "markdown": null,
  "error": "Error description with traceback"
}
```

**Note**: The callback format is compatible with Knowledge Hub's callback format. If the callback URL contains `callback/forma/convert` in the path or has a `token` query parameter, it will use Knowledge Hub's field names (`markdown` and `error` instead of `markdown_content` and `error_message`).

## Processing Behavior

The endpoint performs **basic normalization** on the submitted Markdown:

1. **Remove null characters** (`\x00`)
2. **Normalize line endings** to Unix style (`\n`)
3. **Strip trailing whitespace** from each line
4. **Ensure single trailing newline**

This is intentionally lightweight - no complex transformations are applied since the content is already in Markdown format.

## Error Handling

### HTTP 400 Bad Request

Returned immediately if:

- `markdown_content` exceeds `FORMA_MAX_INLINE_MD_BYTES` (default 2MB)
- Required fields are missing
- `callback_url` is not a valid HTTP/HTTPS URL

### HTTP 422 Unprocessable Entity

Returned if request body fails validation (e.g., invalid JSON, wrong field types)

### Callback with status="failed"

Sent if processing fails (e.g., normalization error, internal error)

## Configuration

Environment variables:

- `FORMA_MAX_INLINE_MD_BYTES`: Maximum size in bytes for `markdown_content` (default: 2097152 = 2MB)
- `CALLBACK_TOKEN`: Token sent in `X-Callback-Token` header for non-Knowledge-Hub callbacks
- `CONVERSION_TIMEOUT`: Timeout for processing (default: 600 seconds)

## Comparison with `/api/v1/convert`

| Feature         | `/api/v1/convert`                                         | `/api/v1/convert-by-content`       |
| --------------- | --------------------------------------------------------- | ---------------------------------- |
| Input           | `source_url` (file URL)                                   | `markdown_content` (inline string) |
| Download        | Yes, downloads from URL                                   | No download needed                 |
| Conversion      | Full document conversion (PDF/DOCX/PPTX/Image → Markdown) | Basic normalization only           |
| Use Case        | Uploaded files (PDF, DOCX, etc.)                          | Git Sync / Editor documents        |
| Processing      | Complex (OCR, VLM, format conversion)                     | Lightweight (normalization)        |
| Callback Format | Same                                                      | Same                               |

## Example Usage

### cURL Example

```bash
curl -X POST http://localhost:8000/api/v1/convert-by-content \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "doc-12345",
    "markdown_content": "# Hello World\n\nThis is my markdown content.\n",
    "callback_url": "https://your-app.com/api/callbacks/forma"
  }'
```

**Response**:

```json
{
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "processing"
}
```

### Python Example

```python
import requests

response = requests.post(
    "http://localhost:8000/api/v1/convert-by-content",
    json={
        "request_id": "doc-12345",
        "markdown_content": "# Hello World\n\nThis is my markdown content.\n",
        "callback_url": "https://your-app.com/api/callbacks/forma"
    }
)

task_id = response.json()["task_id"]
print(f"Task submitted: {task_id}")
```

### Callback Handler Example (FastAPI)

```python
from fastapi import FastAPI, Request

app = FastAPI()

@app.post("/api/callbacks/forma")
async def forma_callback(request: Request):
    payload = await request.json()

    if payload["status"] == "completed":
        markdown = payload["markdown"]
        # Store or process the markdown
        print(f"Received markdown: {len(markdown)} characters")
    else:
        error = payload["error"]
        # Handle error
        print(f"Processing failed: {error}")

    return {"received": True}
```

## Security Considerations

1. **Content Size Limits**: Always enforced to prevent memory exhaustion
2. **Callback URLs**: Must be valid HTTP/HTTPS URLs
3. **Logging**: Full markdown content is never logged, only size and preview (first 80 chars)
4. **Callback Authentication**:
   - Knowledge Hub callbacks: Token in query string
   - Other callbacks: `X-Callback-Token` header (if `CALLBACK_TOKEN` configured)

## Migration Guide

### For Knowledge Hub Integration

If you're migrating from the file-based flow to inline markdown:

**Before** (file-based):

```python
# KH uploads file, gets source_url
source_url = "http://kh-server/static/files/doc123.md"

requests.post("http://forma/api/v1/convert", json={
    "request_id": "doc-123",
    "source_url": source_url,
    "callback_url": "http://kh-server/callback/forma/convert?token=xxx"
})
```

**After** (inline markdown):

```python
# KH has markdown in database
markdown_content = doc.Content  # From database

requests.post("http://forma/api/v1/convert-by-content", json={
    "request_id": "doc-123",
    "markdown_content": markdown_content,
    "callback_url": "http://kh-server/callback/forma/convert?token=xxx"
})
```

The callback format remains identical, so no changes needed in your callback handler.

## Troubleshooting

### "Markdown content size exceeds maximum allowed size"

**Solution**: Reduce content size or increase `FORMA_MAX_INLINE_MD_BYTES` environment variable.

### Callback not received

**Possible causes**:

1. Callback URL not reachable from Forma server
2. Callback endpoint returning errors
3. Network/firewall issues

**Debug**: Check Forma logs for callback dispatch messages and HTTP errors.

### Processing takes too long

**Solution**: Check `CONVERSION_TIMEOUT` setting. For inline markdown, processing should be very fast (< 1 second typically).

## Limitations

1. **No complex transformations**: Unlike file conversion, this endpoint only does basic normalization
2. **Markdown only**: Currently only supports `text/markdown` content type
3. **Strategy ignored**: The `strategy` parameter is accepted but ignored (always uses basic normalization)
4. **No file output**: Results are only delivered via callback, not stored persistently

## Future Enhancements

Potential future improvements:

- Support for other text formats (HTML, reStructuredText, etc.)
- Optional advanced markdown cleaning/formatting
- Batch processing of multiple documents
- Persistent storage option
