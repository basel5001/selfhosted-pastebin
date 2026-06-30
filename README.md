# Selfhosted Pastebin

Encrypted paste service with zero-knowledge client-side encryption. Single Python container, SQLite storage, syntax highlighting, expiring pastes.

## Features

- **Zero-knowledge encryption** — AES-256-GCM encryption happens in-browser via the Web Crypto API. The server never sees plaintext content.
- **Password protection** — Optional access control with PBKDF2-hashed passwords
- **Burn after reading** — Self-destructing pastes deleted after first view
- **Expiring pastes** — 1 hour, 1 day, 1 week, 1 month, or never
- **Syntax highlighting** — highlight.js with 9 language presets
- **Rate limiting** — 10 pastes/minute per IP
- **Single container** — SQLite storage, no external dependencies

## How Encryption Works

```
Client                              Server
  |                                   |
  |-- Generate AES-256 key ---------> |
  |-- Encrypt content (AES-GCM) ---> |
  |-- POST /api/paste {encrypted} --> |-- Store ciphertext in SQLite
  |<-- { id: "abc123" } ------------- |
  |                                   |
  |-- Navigate to /abc123#<key> ----> |
  |-- GET /api/paste/abc123 --------> |-- Return ciphertext
  |<-- { content: "..." } ----------- |
  |-- Decrypt with key from # ------> |
  |-- Render plaintext                |
```

The encryption key lives in the URL fragment (`#key`), which is never sent to the server.

## Self-Hosting

### Docker Compose (recommended)

```bash
git clone https://github.com/basel5001/selfhosted-pastebin.git
cd selfhosted-pastebin
docker compose up -d
```

The service is available at `http://localhost:8000`.

### Local Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
make dev
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_PATH` | `data/pastebin.db` | SQLite database file path |
| `MAX_PASTE_SIZE` | `524288` | Max paste size in bytes (512KB) |
| `RATE_LIMIT_MAX` | `10` | Max pastes per rate limit window |
| `RATE_LIMIT_WINDOW` | `60` | Rate limit window in seconds |

## API

### Create Paste

```bash
curl -X POST http://localhost:8000/api/paste \
  -H "Content-Type: application/json" \
  -d '{
    "content": "<encrypted-base64>",
    "language": "python",
    "expires_in": "1d",
    "password": "optional",
    "burn_after_read": false
  }'
```

Response: `201 Created`
```json
{"id": "abc12345", "url": "/abc12345"}
```

### Get Paste

```bash
curl http://localhost:8000/api/paste/{id}
curl http://localhost:8000/api/paste/{id}?password=secret
```

### Delete Paste

```bash
curl -X DELETE http://localhost:8000/api/paste/{id}
```

### Health Check

```bash
curl http://localhost:8000/health
```

## Testing

```bash
make test    # Run pytest
make lint    # Run ruff
```

## License

MIT
