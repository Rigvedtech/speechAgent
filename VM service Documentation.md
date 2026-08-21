# VM service documentation

This file explains **which services run on the Azure VM** and how they start.

**VM:** `azureuser@20.244.7.67` (hostname `Aibot`)  
**App repo on the VM:** `/home/azureuser/speechAgent`

This version covers **frontend**, **backend**, and **Postgres**.

| Piece | systemd service | Status in this doc |
| --- | --- | --- |
| Frontend | `nginx` | **This document** |
| Backend | `speechagent-api` | **This document** |
| Database | `postgresql@16-main` | **This document** |

---

## See all services on the VM

SSH in, then list what is running:

```bash
systemctl list-units --type=service --state=running
```

You will see about 24 services. Most are Ubuntu / Azure (`ssh`, `cron`, `walinuxagent`, and so on). **Ignore those.**

Our app lines are:

```text
nginx.service              loaded active running    A high performance web server and a reverse proxy server
speechagent-api.service    loaded active running    SpeechAgent API (FastAPI + WebSocket)
postgresql@16-main.service loaded active running    PostgreSQL Cluster 16-main
```

There is **no** service named `speechagent-frontend`. There is **no** `npm` service.

Do they start when the VM boots?

```bash
systemctl is-enabled nginx speechagent-api postgresql@16-main
```

`enabled` means yes — systemd starts that unit on reboot.

---

# 1. Frontend service (nginx)

## 1.1 Simple idea

On a **laptop**, you run the UI with:

```bash
cd frontend
npm run dev
```

That starts a Node / Vite process. It must stay open. **We do not do this on Azure.**

On the **Azure VM**, the website is already **built** into HTML, JS, and CSS files. A program called **nginx** only **sends those files** to the browser. The browser then runs React.

So:

| Place | How the UI runs |
| --- | --- |
| Laptop | `npm run dev` (live Node server) |
| Azure VM | `nginx` serves files from `/var/www/speechagent` |

`npm run dev` is **not** in the nginx config. That is correct.

---

## 1.2 Files you must know

| What | Path on the VM |
| --- | --- |
| nginx **service** (start/stop on boot) | Ubuntu unit `nginx` — view with `systemctl cat nginx` |
| nginx **site config** (our app) | `/etc/nginx/sites-enabled/speechagent` |
| Files nginx **serves** (the live website) | `/var/www/speechagent` |
| React **source** (`.tsx` pages you edit) | `/home/azureuser/speechAgent/frontend` |
| Deploy script that **builds** the UI | `/home/azureuser/speechAgent/scripts/deploy-vm.sh` |
| GitHub Actions trigger | `.github/workflows/deploy-vm.yml` (in git) |

Open the site config:

```bash
sudo cat /etc/nginx/sites-enabled/speechagent
```

The line that points to the live website is:

```text
root /var/www/speechagent;
index index.html;
```

List what nginx actually serves:

```bash
ls /var/www/speechagent
```

Typical output:

```text
assets  auth-hero.png  favicon-dark.svg  favicon-light.svg  favicon.svg  icons.svg  index.html  platforms  proctor
```

You will **not** see `LoginPage.tsx` here. Those source files live only under `frontend/src/`. After `npm run build`, they become one HTML file plus JS/CSS under `assets/`.

---

## 1.3 How nginx “runs” the frontend (a bit deeper)

nginx does **not** execute React. It is a file server (and a proxy for `/api`).

**Step 1 — browser asks for the site**

Someone opens `https://prabhat.rigvedtech.com`.

- Port **80** (HTTP) redirects to **HTTPS** (port 443).
- nginx sends `/var/www/speechagent/index.html`.

**Step 2 — `index.html` is only a shell**

The page has an empty box:

```html
<div id="root"></div>
```

In **source** (`frontend/index.html`) the script is `/src/main.tsx`. The browser cannot run `.tsx` in production.

**Step 3 — build rewrites the script**

`npm run build` changes that tag to something like:

```html
<script type="module" src="/assets/index-Ab12cd.js"></script>
```

See it on the VM:

```bash
cat /var/www/speechagent/index.html
ls /var/www/speechagent/assets
```

The files in `assets/` **are** the whole React app (login, dashboard, routes), bundled for the browser.

**Step 4 — browser runs React**

1. Browser downloads `/assets/...js` from nginx.
2. JavaScript finds `#root`.
3. React paints the UI **in the user’s browser**, not on the VM.

**Step 5 — routes like `/login`**

There is no file named `login`. nginx has:

```text
location / {
    try_files $uri $uri/ /index.html;
}
```

Meaning: if the file does not exist, still send `index.html`. Then the JS looks at the URL and shows the login page.

**Step 6 — `/api` is not the frontend**

```text
location /api/ {
    proxy_pass http://127.0.0.1:8000;
}
```

The JS in the browser calls `/api/...`. nginx **forwards** that to the Python backend. Same for `/health`, `/docs`, `/ws/`. `/recall-ws` goes to port **5213**.

Picture:

```text
Browser
  ├─ GET /            → nginx → index.html              (file)
  ├─ GET /assets/*.js → nginx → bundled React            (file)
  ├─ GET /login       → nginx → index.html again         (SPA)
  └─ GET /api/...     → nginx → Python on port 8000      (proxy)
```

---

## 1.4 What happens on **VM start / reboot**

GitHub Actions does **not** run. `deploy-vm.sh` does **not** run. There is **no** `npm run build`.

Flow:

```text
VM power on
  → systemd sees nginx is enabled
  → starts nginx.service
  → nginx reads /etc/nginx/sites-enabled/speechagent
  → serves whatever files are already in /var/www/speechagent
```

Those files are from the **last successful deploy**. If nobody deployed after a code change, the old website stays.

Check after reboot:

```bash
sudo systemctl status nginx --no-pager
ls /var/www/speechagent
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1/
```

`200` (or a redirect to HTTPS) means nginx is serving the site.

Useful commands:

```bash
sudo systemctl status nginx
sudo systemctl restart nginx
sudo systemctl reload nginx
sudo nginx -t
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

React `console.log` does **not** appear here. UI errors are in the **browser** (F12). nginx logs are HTTP hits and server errors.

---

## 1.5 What happens when **GitHub Actions** runs

**When:** push or merge to **`main`**, or a manual “Deploy to Azure VM” in Actions.

**What the YAML does:** it does **not** start nginx and it does **not** run `npm` on GitHub’s machines. It only SSH into the VM and runs a script **on the VM**.

File: `.github/workflows/deploy-vm.yml`

```text
GitHub Actions (cloud)
  → SSH to 20.244.7.67
  → git pull main
  → bash /home/azureuser/speechAgent/scripts/deploy-vm.sh
```

The YAML is short on purpose. Long shell in that action breaks. All real steps are in `deploy-vm.sh`.

**Frontend part of `deploy-vm.sh` (this is the build):**

```text
cd /home/azureuser/speechAgent/frontend
npm ci              # install packages
npm run build       # compile React → frontend/dist/
sudo cp -r dist/. /var/www/speechagent/    # publish for nginx
```

Then it checks the site:

```text
curl http://127.0.0.1/
```

nginx is **already running**. The script **does not** restart nginx. New files replace old ones; the next browser request gets the new UI.

Full frontend deploy picture:

```text
Push to main
  → GitHub Actions SSHs to VM
  → deploy-vm.sh
       1. (also stops/starts backend — see section 2)
       2. npm ci
       3. npm run build
          source:  /home/azureuser/speechAgent/frontend/src/*.tsx
          output:  /home/azureuser/speechAgent/frontend/dist/
       4. copy dist/ → /var/www/speechagent
       5. Node exits (build finished)
  → nginx keeps serving /var/www/speechagent
  → users see the new site
```

Same deploy by hand (this **is** a production deploy — do not run it just to read the file):

```bash
cd /home/azureuser/speechAgent
bash scripts/deploy-vm.sh
```

**Only read** the script:

```bash
less /home/azureuser/speechAgent/scripts/deploy-vm.sh
```

Press `q` to quit. Search for `npm`:

```bash
grep -n "npm" /home/azureuser/speechAgent/scripts/deploy-vm.sh
```

---

## 1.6 Two folders — do not mix them

```text
You edit this (source):
  /home/azureuser/speechAgent/frontend/src/

Build output (temporary, created on deploy):
  /home/azureuser/speechAgent/frontend/dist/

nginx serves this (live site):
  /var/www/speechagent/
```

If you change a `.tsx` file and **only** reboot the VM, the website **does not** update. You must deploy (`main` push or `deploy-vm.sh`) so `npm run build` runs again.

---

## 1.7 Frontend checklist (handover)

| Question | Answer |
| --- | --- |
| Which service is the frontend? | `nginx` |
| Where is the site config? | `/etc/nginx/sites-enabled/speechagent` |
| Where are the live files? | `/var/www/speechagent` |
| Is `npm run dev` on the VM? | **No** (laptop only) |
| When does `npm run build` run? | Only during `deploy-vm.sh` (GitHub Actions or by hand) |
| On VM reboot, does the UI rebuild? | **No**. nginx starts and serves existing files |
| On GitHub Actions, does nginx restart? | **No**. New files are copied in; nginx stays up |
| Where do UI errors show? | Browser F12. nginx logs are HTTP only |

---

# 2. Backend service (`speechagent-api`)

## 2.1 Simple idea

The backend is a **Python program** that stays running: `api_server.py` (FastAPI). It answers `/api`, `/health`, websockets, and talks to Postgres.

On a **laptop** you often start it yourself:

```bash
cd backend
source venv/bin/activate    # Windows: venv\Scripts\activate
python api_server.py
```

On **Azure**, you do **not** keep a terminal open. systemd runs the same command as a service named **`speechagent-api`**.

nginx does **not** run Python. The browser hits nginx; nginx **forwards** `/api` to this service on port **8000**.

| Place | How the API runs |
| --- | --- |
| Laptop | `python api_server.py` (you start it) |
| Azure VM | systemd `speechagent-api` (always on) |

---

## 2.2 Files you must know

| What | Path on the VM |
| --- | --- |
| systemd **service file** | `/etc/systemd/system/speechagent-api.service` |
| Python **code** | `/home/azureuser/speechAgent/backend/` |
| Virtualenv (packages) | `/home/azureuser/speechAgent/backend/venv/` |
| Secrets / DB URL | `/home/azureuser/speechAgent/backend/.env` |
| Saved **log files** | `/home/azureuser/speechAgent/backend/logs/` |
| Interview transcripts | `/home/azureuser/speechAgent/backend/transcripts/` |
| Deploy script | `/home/azureuser/speechAgent/scripts/deploy-vm.sh` |

Open the service file:

```bash
systemctl cat speechagent-api
```

What it actually runs:

```text
WorkingDirectory=/home/azureuser/speechAgent/backend
ExecStart=/home/azureuser/speechAgent/backend/venv/bin/python api_server.py
```

That is the same as: `cd backend` then `venv/bin/python api_server.py`.

Other lines in that file (plain meaning):

| Line | Meaning |
| --- | --- |
| `After=network.target postgresql.service` | Start after network and Postgres |
| `Wants=postgresql.service` | Prefer Postgres to be up |
| `User=azureuser` | Not root |
| `Restart=always` | If Python crashes, start it again after 5 seconds |
| `WantedBy=multi-user.target` | Can start on VM boot (if **enabled**) |

Is it enabled and running?

```bash
sudo systemctl status speechagent-api
systemctl is-enabled speechagent-api
```

Healthy API:

```bash
curl -sS http://127.0.0.1:8000/health
```

You should see `"status":"healthy"`.

---

## 2.3 How the backend works with nginx (a bit deeper)

```text
Browser  →  https://prabhat.rigvedtech.com/api/...
         →  nginx  (location /api/)
         →  http://127.0.0.1:8000   ← speechagent-api (Python)
         →  Postgres on 127.0.0.1:5432
```

- Port **8000** = HTTP API (FastAPI). Only listening on the VM. The public site uses **443**; nginx proxies.
- Port **5213** = Recall audio websocket. nginx `/recall-ws` forwards here.
- `/health`, `/docs`, `/ws/` also proxy to **8000**.

Python reads `backend/.env` (database, Groq, Sarvam, Recall, JWT, public URLs). After you change `.env`, restart the service or the old values stay in memory:

```bash
sudo systemctl restart speechagent-api
```

---

## 2.4 Where to see logs

**A. systemd journal** (live console of the service):

```bash
sudo journalctl -u speechagent-api -n 200 --no-pager
sudo journalctl -u speechagent-api -f
```

`Ctrl+C` stops `-f`. You will see lines like `GET /api/job-postings 200 OK`.

**B. Files on disk** (saved when the process starts):

```bash
ls -lt /home/azureuser/speechAgent/backend/logs/
```

Names look like `api_server_20260820_093133.log` (date/time of **that** start). Each restart of `speechagent-api` creates a **new** file.

Follow the newest file:

```bash
tail -f $(ls -t /home/azureuser/speechAgent/backend/logs/api_server_*.log | head -1)
```

This is written by `backend/file_logging.py` (`FILE_LOGGING_ENABLED`, default on).

Not the same:

| Place | What |
| --- | --- |
| `backend/logs/` | Full API log files |
| `backend/transcripts/` | Interview text |
| `/var/log/nginx/` | Frontend HTTP, not Python |

---

## 2.5 What happens on **VM start / reboot**

GitHub Actions does **not** run. `deploy-vm.sh` does **not** run. There is **no** `pip install` and **no** new git pull.

Flow:

```text
VM power on
  → systemd starts postgresql@16-main  (database)
  → systemd sees speechagent-api is enabled
  → starts speechagent-api.service
  → runs: venv/bin/python api_server.py
  → API listens on port 8000 (and WS 5213)
```

The code on disk is whatever was last deployed. Reboot **does not** update git. It only starts Python again.

Check after reboot:

```bash
sudo systemctl status speechagent-api --no-pager
curl -sS http://127.0.0.1:8000/health
```

Useful commands:

```bash
sudo systemctl status speechagent-api
sudo systemctl restart speechagent-api
sudo systemctl stop speechagent-api
sudo systemctl start speechagent-api
sudo journalctl -u speechagent-api -f
```

Do **not** run `python api_server.py` by hand while the service is already `active`. You would get two processes fighting for the same ports.

---

## 2.6 What happens when **GitHub Actions** runs

**When:** push or merge to **`main`**, or a manual “Deploy to Azure VM” in Actions.

Same as frontend: YAML only SSHs in and runs `deploy-vm.sh` on the VM.

**Backend part of `deploy-vm.sh`:**

```text
sudo systemctl stop speechagent-api     # stop old Python
git reset to origin/main                # new code
cd backend
pip install -r requirements.txt         # packages
python database/migrate.py ...          # DB if needed (see Postgres later)
sudo systemctl start speechagent-api    # start new Python
curl http://127.0.0.1:8000/health       # fail deploy if API is down
```

If the script dies **before** the API is healthy, a trap tries `systemctl start speechagent-api` so the site is not left with no backend.

Picture:

```text
Push to main
  → GitHub Actions SSHs to VM
  → deploy-vm.sh
       1. stop speechagent-api
       2. git pull / reset to main
       3. pip install
       4. migrations (if pending)
       5. start speechagent-api   ← new api_server.py is now running
       6. then frontend npm build (section 1)
  → users hit nginx → new Python on :8000
```

Unlike nginx, the backend **is** stopped and started on deploy. That is how new Python code goes live. There is no “copy dist/” for the API — it runs the files in `/home/azureuser/speechAgent/backend/` directly.

If you change only Python and **only** reboot the VM, you still get the **old git** on disk. New backend code needs a deploy (`main` push or `bash scripts/deploy-vm.sh`).

After deploy, confirm:

```bash
sudo systemctl status speechagent-api --no-pager
curl -sS http://127.0.0.1:8000/health
```

---

## 2.7 Backend checklist (handover)

| Question | Answer |
| --- | --- |
| Which service is the backend? | `speechagent-api` |
| Where is the unit file? | `/etc/systemd/system/speechagent-api.service` |
| What command does it run? | `venv/bin/python api_server.py` in `backend/` |
| Port | **8000** (API). Recall audio **5213** |
| How does the browser reach it? | nginx `/api/` → `127.0.0.1:8000` |
| On VM reboot, does git pull? | **No**. systemd starts the existing `api_server.py` |
| On GitHub Actions, what happens? | Stop API → pull code → pip → migrate → **start API** |
| After `.env` change? | `sudo systemctl restart speechagent-api` |
| Where are saved logs? | `/home/azureuser/speechAgent/backend/logs/api_server_*.log` |
| Live logs? | `sudo journalctl -u speechagent-api -f` |

---

# 3. Postgres service (`postgresql@16-main`)

## 3.1 Simple idea

Postgres is the **database**. It stores users, jobs, interviews, and so on. It does **not** serve the website.

```text
Browser → nginx → speechagent-api (:8000) → PostgreSQL (:5432) → database prabhat_DB
```

nginx never talks to Postgres. Only Python does, using `DATABASE_URL` in `/home/azureuser/speechAgent/backend/.env`.

On this VM the cluster is **PostgreSQL 16**, name **main**, so the unit is:

```text
postgresql@16-main
```

| Place | How the DB runs |
| --- | --- |
| Laptop | Local Postgres (host `localhost` in `.env`) |
| Azure VM | systemd `postgresql@16-main` (host `127.0.0.1` in `.env`) |

Do **not** mix laptop and VM databases.

### VM database login (production)

Source of truth on the box: `/home/azureuser/speechAgent/backend/.env` (`DATABASE_URL`). Current handover values (same as `KNOWLEDGE_TRANSFER.md`):

| Item | Azure VM |
| --- | --- |
| Username | `postgres` |
| Password | `1234` |
| Database | `prabhat_DB` |
| Host | `127.0.0.1` (loopback on the VM — **not** public IP `20.244.7.67`) |
| Port | `5432` |
| Full URL | `postgresql://postgres:1234@127.0.0.1:5432/prabhat_DB` |

Laptop **dev** uses the same user / password / database, but host **`localhost`**:

```text
postgresql://postgres:1234@localhost:5432/prabhat_DB
```

Confirm on the VM (do not commit a changed password to git if you rotate it):

```bash
grep '^DATABASE_URL=' /home/azureuser/speechAgent/backend/.env
```

Connect as the OS user `postgres` (no password prompt for local peer/trust):

```bash
sudo -u postgres psql -d prabhat_DB
```

Or with the app password over TCP:

```bash
psql "postgresql://postgres:1234@127.0.0.1:5432/prabhat_DB"
```

`\q` to leave. Do not expose port **5432** on the public internet; the API connects on loopback only.

---

## 3.2 Two kinds of files (same idea as nginx)

For nginx we had:

- **Service file** = start the program  
- **Site config** = what the website does  

Postgres is the same:

| Kind | Path / command | Job |
| --- | --- | --- |
| **Service (template)** | `/usr/lib/systemd/system/postgresql@.service` | Start/stop the cluster |
| **Parent service** | `systemctl cat postgresql` | Wrapper; `speechagent-api` waits on this (`Wants=postgresql.service`) |
| **Postgres config** | `/etc/postgresql/16/main/postgresql.conf` | How Postgres listens, memory, etc. |
| **Who may connect** | `/etc/postgresql/16/main/pg_hba.conf` | Auth rules |
| **Data on disk** | `/var/lib/postgresql/16/main` | Tables, our database `prabhat_DB` |
| **How our app connects** | `/home/azureuser/speechAgent/backend/.env` | `DATABASE_URL=...127.0.0.1:5432/prabhat_DB` |

`prabhat_DB` is **inside** Postgres. It is **not** written in the systemd file.

---

## 3.3 The service file (template) — Ubuntu provides it

**This is the Postgres service file.** When you run `systemctl cat postgresql@16-main --no-pager`, the first line is:

```text
# /usr/lib/systemd/system/postgresql@.service
```

That **is** the unit. There is usually **no** extra file named `postgresql@16-main.service` in `/etc/systemd/system/`. `@` means **template**; systemd fills in `%i` = `16-main`.

**Who wrote it?** The **Ubuntu PostgreSQL package**, not this git repo and not a file we created. Same idea as nginx. Our backend is the exception (`speechagent-api.service` we wrote).

| Service | Service file | Who put it on the VM |
| --- | --- | --- |
| Frontend | `/usr/lib/systemd/system/nginx.service` | Ubuntu nginx package |
| Database | `/usr/lib/systemd/system/postgresql@.service` | Ubuntu Postgres package |
| Backend | `/etc/systemd/system/speechagent-api.service` | **Us** (this project) |

That systemd file only **starts/stops** the engine. It does **not** contain `prabhat_DB`, passwords, or `DATABASE_URL`.

Open it:

```bash
systemctl cat postgresql@16-main --no-pager
```

The `@` means template. `%i` becomes `16-main`. `%I` becomes `16/main`.

After filling in, start is:

```text
/usr/bin/pg_ctlcluster --skip-systemctl-redirect 16-main start
```

That helper then reads **Postgres’s own** config (also from the Ubuntu package, not git):

```bash
ls /etc/postgresql/16/main/
sudo cat /etc/postgresql/16/main/postgresql.conf
```

| File | What it is |
| --- | --- |
| `postgresql.conf` | Port 5432, listen address, memory |
| `pg_hba.conf` | Who may connect |

How **our app** connects is only:

```text
/home/azureuser/speechAgent/backend/.env  →  DATABASE_URL
```

Useful lines in the systemd file:

| In the file | Meaning |
| --- | --- |
| `AssertPathExists=/etc/postgresql/%I/postgresql.conf` | Needs `/etc/postgresql/16/main/postgresql.conf` |
| `PartOf=postgresql.service` | This cluster belongs to parent `postgresql` |
| `ExecStart=... pg_ctlcluster %i start` | Start cluster `16-main` |
| `ExecStop=... stop` | Stop it |
| `#Restart=on-failure` (commented out) | systemd will **not** auto-restart like `speechagent-api`. Postgres restarts itself internally |
| `[Install]` `WantedBy=multi-user.target` | **Can** start on VM boot if enabled |

Always use `--no-pager` so `[Install]` is not cut off.

Parent unit:

```bash
systemctl cat postgresql --no-pager
```

---

## 3.4 Status you should see

```bash
sudo systemctl status postgresql@16-main
systemctl is-enabled postgresql@16-main
systemctl is-enabled postgresql
```

Healthy looks like:

- `Active: active (running)`
- Main process: `/usr/lib/postgresql/16/bin/postgres -D /var/lib/postgresql/16/main ...`
- Extra workers (`checkpointer`, `walwriter`, …) are **internal**. Ignore them.

These lines mean **our API is connected**:

```text
postgres: 16/main: postgres prabhat_DB 127.0.0.1(...) idle
```

- database `prabhat_DB`
- client `127.0.0.1` (Python on the same VM, not the public internet)
- `idle` = waiting for the next query (normal)

`is-enabled` may say **`enabled-runtime`** instead of `enabled`. That is Ubuntu’s cluster style. The parent `postgresql.service` still brings the cluster up on boot. Check both `postgresql` and `postgresql@16-main`.

Boot links:

```bash
ls -l /etc/systemd/system/multi-user.target.wants/ | grep postgres
```

Confirm the app URL (do not paste secrets into chat/git):

```bash
grep '^DATABASE_URL=' /home/azureuser/speechAgent/backend/.env
sudo -u postgres psql -d prabhat_DB -c '\conninfo'
```

`\q` leaves `psql`.

---

## 3.5 What happens on **VM start / reboot**

GitHub Actions does **not** run. `deploy-vm.sh` does **not** run. Data on disk stays.

```text
VM power on
  → systemd starts postgresql / postgresql@16-main
  → Postgres listens on 127.0.0.1:5432
  → speechagent-api starts (After=postgresql.service)
  → nginx starts
```

Reboot does **not** change schema. It only starts the database engine again.

Check after reboot:

```bash
sudo systemctl status postgresql@16-main --no-pager
sudo -u postgres psql -d prabhat_DB -c 'SELECT 1;'
curl -sS http://127.0.0.1:8000/health
```

Useful commands:

```bash
sudo systemctl status postgresql@16-main
sudo journalctl -u postgresql@16-main -n 100 --no-pager
sudo systemctl restart postgresql@16-main
```

**Do not restart Postgres unless it is broken.** API connections drop until it is back.

---

## 3.6 What happens when **GitHub Actions** runs

There is **no** Postgres service that “starts because Actions ran.” The YAML and `deploy-vm.sh` do **not** `systemctl start postgresql`. The DB is expected to **already be running**.

What deploy **can** do to the database:

1. Count pending SQL files (`python database/migrate.py pending-count`)
2. If pending **> 0**: dump to `/home/azureuser/speechAgent/backups/db/` (keep last 3), then `migrate.py apply`
3. If pending **= 0**: skip dump, leave the DB as-is
4. Then start `speechagent-api` so Python uses the (maybe new) tables

**Never** run `database/init.sql` with `DROP SCHEMA` on production. That wipes data. Only new numbered files like `034_....sql`.

Picture:

```text
Push to main
  → GitHub Actions SSHs to VM
  → deploy-vm.sh
       Postgres: stays running (no systemctl restart)
       If new SQL: dump + apply
       Then: restart Python (section 2)
       Then: npm build (section 1)
```

Manual migrate (only if you know why):

```bash
cd /home/azureuser/speechAgent
source backend/venv/bin/activate
python database/migrate.py status
python database/migrate.py pending-count
```

---

## 3.7 Postgres checklist (handover)

| Question | Answer |
| --- | --- |
| Which service is the database? | `postgresql@16-main` (parent: `postgresql`) |
| Where is the unit file? | `/usr/lib/systemd/system/postgresql@.service` (Ubuntu package, **not** git). `%i` = `16-main` |
| Did we write this service? | **No.** Compare: we **did** write `speechagent-api.service` |
| Where is Postgres config? | `/etc/postgresql/16/main/postgresql.conf` |
| Where is data? | `/var/lib/postgresql/16/main` |
| Database name | `prabhat_DB` |
| Username / password | `postgres` / `1234` (live value: `DATABASE_URL` in `backend/.env`) |
| How does the API connect? | `DATABASE_URL=postgresql://postgres:1234@127.0.0.1:5432/prabhat_DB` |
| On VM reboot? | systemd starts Postgres, then the API. No git, no migrate |
| On GitHub Actions? | Postgres **stays up**. Maybe migrate. **No** `systemctl restart postgresql` |
| Auto-start on boot? | `[Install] WantedBy=multi-user.target` plus enable (`enabled` or `enabled-runtime`) |
| Safe to restart often? | **No** — only if the DB is down |

---

## 4. All three together (short)

```text
VM boot
  → postgresql@16-main     (data)
  → speechagent-api        (Python :8000)
  → nginx                  (files + proxy)

GitHub Actions (push to main)
  → SSH → deploy-vm.sh
  → stop API → git pull → pip
  → migrate only if new SQL (Postgres stays running)
  → start API
  → npm ci / npm run build → copy to /var/www/speechagent
  → nginx stays up
```

Laptop `npm run dev` / `python api_server.py` are **not** used on Azure.
