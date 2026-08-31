# NEONDROP — Security Architecture & Hardening Guide

This document details the security architecture, threat model, cryptographic provably-fair engine, financial ledger integrity, and production hardening procedures for the **NEONDROP** Django gaming platform.

---

## 🛡️ 1. Threat Model & Security Principles

```
  ┌─────────────────────────────────────────────────────────────┐
  │                    UNTRUSTED CLIENT BROWSER                 │
  │  (Zero Trust: Never trust balance, prices, or win rolls)     │
  └──────────────────────────────┬──────────────────────────────┘
                                 │ HTTPS + CSRF Token + Rate Limit
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                    DJANGO APPLICATION LAYER                 │
  │  • Session Fixation Defense  • Rate Limiting & Idempotency   │
  │  • Generic Auth Errors       • Authoritative DB Validation  │
  └──────────────────────────────┬──────────────────────────────┘
                                 │ Atomic Transactions (select_for_update)
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                 FINANCIAL LEDGER & DATABASE                 │
  │  • Immutable Transaction Log • Row-Level Balance Locks      │
  │  • Cryptographic Provably Fair (HMAC-SHA256) Audit Trail    │
  └─────────────────────────────────────────────────────────────┘
```

### Core Security Tenet
**The Django backend is the absolute single source of truth.**
The client interface is completely untrusted. Any client payload attempting to submit `balance`, `price`, `item_value`, `won_item`, or `user_id` is discarded. The server derives all identity from `request.user` and all prices and values directly from locked database records.

---

## 🔐 2. Authentication & Session Security

1. **Password Storage**: Uses Django's PBKDF2 with SHA-256 password hashing. Passwords are never stored in plaintext and never logged.
2. **Brute-Force & Rate Limiting**:
   - `/users/login/`: Rate-limited to 5 attempts per 60 seconds per IP.
   - `/users/register/`: Rate-limited to 5 registrations per hour per IP.
3. **Session Fixation Defense**:
   - `request.session.cycle_key()` is called immediately upon successful user login to invalidate pre-auth session identifiers.
4. **Anti-Enumeration**:
   - Authentication failures return generic error messages (*"Неверное имя пользователя/email или пароль"*), preventing attackers from enumerating valid usernames.
5. **Session Cookies**:
   - `SESSION_COOKIE_HTTPONLY = True` (inaccessible to JavaScript).
   - `SESSION_COOKIE_SAMESITE = 'Lax'` (CSRF mitigation).
   - `SESSION_COOKIE_SECURE = True` in production.

---

## 💰 3. Financial Ledger & Balance Protection

To guarantee financial integrity and eliminate double-spending, all balance mutations are processed through the centralized `modify_user_balance` service in [`payments/services.py`](file:///C:/Users/User/.gemini/antigravity/scratch/neondrop/payments/services.py).

### Authoritative Balance Mutation Flow
```python
@transaction.atomic
def modify_user_balance(user, amount_delta, transaction_type, ...):
    # 1. Lock user profile row in database (prevents race conditions)
    profile = Profile.objects.select_for_update().get(user=user)
    
    # 2. Strict non-negative check
    if profile.balance + amount_delta < Decimal('0.00'):
        raise InsufficientBalanceError(...)
        
    # 3. Apply mutation
    profile.balance += amount_delta
    profile.save(update_fields=['balance'])
    
    # 4. Create immutable Transaction record
    tx = Transaction.objects.create(
        user=user,
        amount=amount_delta,
        balance_before=balance_before,
        balance_after=profile.balance,
        transaction_type=transaction_type,
        ...
    )
    return tx
```

### Protection Against Double-Spending & Replay Attacks
- **Row-Level Database Locking**: `Profile.objects.select_for_update()` locks the user's balance row for the duration of the transaction. Parallel simultaneous requests execute sequentially without race conditions.
- **Idempotency Keys**: API endpoints accept an `idempotency_key` parameter. Cache-backed atomic locks reject duplicate submissions (`HTTP 409 Conflict`).

---

## 🎲 4. Provably Fair Cryptographic Algorithm

Outcomes are never generated using JavaScript `Math.random()`. Instead, a server-side Provably Fair algorithm guarantees mathematical fairness and non-tampering.

### Cryptographic Parameters
- **`server_seed`**: 64-character hexadecimal string generated using CSPRNG (`secrets.token_hex(32)`).
- **`server_seed_hash`**: `SHA-256(server_seed)` published to the user before or alongside the opening.
- **`client_seed`**: User-provided or browser entropy string.
- **`nonce`**: User's opening counter (`profile.total_opened + 1`).

### Mathematical Roll Derivation
$$\text{HMAC} = \text{HMAC-SHA256}(\text{key}=\text{server\_seed}, \text{msg}=\text{client\_seed}:\text{nonce})$$
$$\text{Roll} = \frac{\text{int}(\text{HMAC}[0:8], 16)}{2^{32}} \in [0.0, 1.0)$$

### Verification
Users can independently verify any opening at `/fairness/` by verifying that $\text{SHA-256}(\text{server\_seed}) = \text{server\_seed\_hash}$ and recalculating the HMAC roll.

---

## 💳 5. Payment & Deposit Security

1. **No Automatic Client Credits**: The frontend has **zero** ability to credit balances.
2. **Telegram Deposit Lifecycle**:
   - User creates deposit request at `/deposit/` &rarr; `Transaction` created with `status='pending'`.
   - User contacts manager via pre-filled Telegram link.
   - Administrator verifies the payment in external banking/crypto wallet.
   - Administrator approves the transaction in Django Admin (`/admin/payments/transaction/`).
   - Server runs `@transaction.atomic` balance crediting and records the ledger log.
3. **Admin Audit**:
   - All admin actions record the performing admin user ID and IP address in the ledger log.

---

## 📋 6. Production Hardening Checklist

Before deploying to production, ensure the following environment variables and settings are configured:

### 1. Environment Configuration (`.env`)
```ini
DJANGO_SECRET_KEY=YOUR_LONG_RANDOM_50+_CHARACTER_SECRET_KEY
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=neondrop.gg,www.neondrop.gg
DATABASE_URL=postgresql://neondrop_user:secure_password@localhost:5432/neondrop_db
REDIS_URL=redis://127.0.0.1:6379/1
TELEGRAM_BOT_USERNAME=neondrop_admin
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```

### 2. Security Headers
When `DJANGO_DEBUG=False`, NEONDROP automatically enforces:
- `SECURE_BROWSER_XSS_FILTER = True`
- `SECURE_CONTENT_TYPE_NOSNIFF = True`
- `X_FRAME_OPTIONS = 'DENY'`
- `SECURE_HSTS_SECONDS = 31536000` (1 Year)
- `SECURE_HSTS_INCLUDE_SUBDOMAINS = True`
- `SECURE_HSTS_PRELOAD = True`

### 3. Nginx Reverse Proxy Configuration
```nginx
server {
    listen 443 ssl http2;
    server_name neondrop.gg www.neondrop.gg;

    ssl_certificate /etc/letsencrypt/live/neondrop.gg/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/neondrop.gg/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location /static/ {
        alias /var/www/neondrop/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }

    location /media/ {
        alias /var/www/neondrop/media/;
        expires 7d;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 💾 7. Backup & Disaster Recovery

### Automated PostgreSQL Database Backup Script
Save as `/usr/local/bin/neondrop_backup.sh`:
```bash
#!/bin/bash
BACKUP_DIR="/var/backups/neondrop"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
mkdir -p "$BACKUP_DIR"

# 1. Dump PostgreSQL database
pg_dump -U neondrop_user -h localhost neondrop_db | gzip > "$BACKUP_DIR/db_$TIMESTAMP.sql.gz"

# 2. Archive user media
tar -czf "$BACKUP_DIR/media_$TIMESTAMP.tar.gz" -C /var/www/neondrop media

# 3. Retain only backups from last 14 days
find "$BACKUP_DIR" -type f -mtime +14 -delete

echo "[$(date)] Backup completed: db_$TIMESTAMP.sql.gz"
```

### Crontab Schedule (Daily at 03:00 UTC)
```bash
0 3 * * * /usr/local/bin/neondrop_backup.sh >> /var/log/neondrop_backup.log 2>&1
```

### Database Restoration Procedure
```bash
# Restore PostgreSQL database from compressed backup
gunzip -c /var/backups/neondrop/db_YYYYMMDD_HHMMSS.sql.gz | psql -U neondrop_user -h localhost -d neondrop_db
```
