# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x     | Yes       |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT** open a public GitHub issue
2. Email the maintainer or use GitHub's private vulnerability reporting
3. Include steps to reproduce and potential impact
4. Allow reasonable time for a fix before public disclosure

## Security Model

- **Encryption**: AES-256-GCM via the Web Crypto API, performed entirely client-side
- **Zero-knowledge**: The server stores only ciphertext; decryption keys exist only in URL fragments
- **Passwords**: PBKDF2-HMAC-SHA256 with 600,000 iterations and random 16-byte salts
- **Rate limiting**: In-memory per-IP throttling to prevent abuse

## Known Limitations

- Rate limiting is per-process and resets on restart
- No CSRF protection (API is stateless JSON)
- URL fragment keys can be captured by browser extensions or shared bookmarks
