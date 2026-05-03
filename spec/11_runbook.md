# spec/11_runbook.md

## 1. Objective

Provide operational procedures for running, monitoring, and recovering the system in production.

This runbook enables:

* Safe deployment
* Incident response
* System recovery
* Operational consistency

---

## 2. System Overview (Operational View)

Components:

* FastAPI backend (Uvicorn)
* PostgreSQL database
* Nginx (reverse proxy + HTTPS)
* (Future) Redis queue for async jobs

---

## 3. Deployment Procedure

### 3.1 Server Setup (Hetzner VM)

```bash
sudo apt update
sudo apt install python3-pip python3-venv postgresql nginx
```

---

### 3.2 Application Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

### 3.3 Environment Variables

Set:

```bash
export DATABASE_URL=postgresql://user:password@localhost/db
export GHL_API_KEY=your_api_key
```

---

### 3.4 Run Application

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

---

### 3.5 Nginx Configuration

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
    }
}
```

---

### 3.6 Enable HTTPS

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx
```

---

### 3.7 Verification

* Visit: `https://yourdomain.com/health`
* Expect:

```json id="health_check"
{
  "status": "ok"
}
```

---

## 4. Startup Procedure

1. Start PostgreSQL
2. Start FastAPI (Uvicorn)
3. Start Nginx
4. Verify `/health` endpoint

---

## 5. Shutdown Procedure

1. Stop FastAPI
2. Stop Nginx
3. Stop PostgreSQL (if needed)

---

## 6. Health Monitoring

### 6.1 Health Endpoint

**GET /health**

Expected:

* HTTP 200
* `{ "status": "ok" }`

---

### 6.2 Manual Checks

* API responding < 500ms
* DB connection active
* Logs updating

---

## 7. Common Operations

### 7.1 Check HOT Leads

```sql
SELECT lead_id FROM leads WHERE lead_signal = 'HOT';
```

---

### 7.2 Check Event Count for Lead

```sql
SELECT COUNT(*) FROM progress_events WHERE lead_id = 'user@example.com';
```

---

### 7.3 Inspect Latest Activity

```sql
SELECT MAX(occurred_at) FROM progress_events WHERE lead_id = 'user@example.com';
```

---

## 8. Incident Response

---

### 8.1 High API Latency

**Symptoms**

* Response time > 800ms

**Actions**

1. Check logs
2. Verify DB performance:

   ```sql
   EXPLAIN ANALYZE SELECT ...
   ```
3. Check indexes exist
4. Restart FastAPI if needed

---

### 8.2 Duplicate Events Detected

**Symptoms**

* Multiple rows for same `event_id`

**Actions**

1. Verify PRIMARY KEY constraint
2. Check DB schema integrity
3. Investigate insertion logic

---

### 8.3 GHL Duplicate Sync

**Symptoms**

* Same lead sent multiple times

**Actions**

1. Check `ghl_synced` flag
2. Verify update logic
3. Audit logs for duplicate triggers

---

### 8.4 DB Connection Failure

**Symptoms**

* API errors (500)
* Connection refused

**Actions**

1. Restart PostgreSQL
2. Verify connection string
3. Check connection pool limits

---

### 8.5 External API Failure (GHL)

**Symptoms**

* GHL sync not occurring

**Actions**

1. Check logs for API errors
2. Verify API key
3. Retry manually (if needed)

---

## 9. Recovery Procedures

### 9.1 Restart Application

```bash
pkill -f uvicorn
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

---

### 9.2 Restart Database

```bash
sudo systemctl restart postgresql
```

---

### 9.3 Restore Data (If Needed)

* Re-import from backup
* Validate event integrity

---

## 10. Backup Strategy

### 10.1 MVP

ASSUMPTION: Manual backups

```bash
pg_dump dbname > backup.sql
```

---

### 10.2 Future

* Automated daily backups
* Offsite storage

---

## 11. Logging Access

### 11.1 View Logs

```bash
tail -f app.log
```

OR

```bash
journalctl -u your-service
```

---

### 11.2 What to Look For

* Errors
* Failed API calls
* Missing events

---

## 12. Rate Limiting Issues

### Symptoms

* Frequent HTTP 429 responses

### Actions

* Verify rate limiting config
* Adjust thresholds if needed

---

## 13. Security Incidents

### Examples

* Unauthorized access
* Suspicious traffic

### Actions

1. Check logs
2. Block IP via firewall
3. Rotate credentials

---

## 14. Scaling Operations (Future)

* Add more API instances
* Use load balancer
* Add Redis queue

---

## 15. Constraints

### Must

* Follow startup/shutdown order
* Monitor health endpoint
* Log all incidents

---

### Must Not

* Modify DB directly (outside controlled ops)
* Delete events
* Ignore error logs

---

### Preferences

* Automate deployment (future)
* Use process manager (systemd/docker)

---

## 16. Escalation Triggers

Immediate escalation if:

* API down
* DB unreachable
* Data inconsistency detected
* Duplicate events found
* GHL duplication occurs

---

## 17. Definition of Done

* [ ] Deployment reproducible
* [ ] Health endpoint verified
* [ ] Logs accessible
* [ ] Recovery steps tested
* [ ] Backup process defined
* [ ] Incident procedures documented

---

## 18. Summary

This runbook ensures:

* Reliable operations
* Fast recovery
* Controlled deployment

It is the operational backbone of the system and MUST be followed strictly.
