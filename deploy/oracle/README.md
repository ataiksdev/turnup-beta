# Deploying the backend to Oracle Cloud (free)

What runs where:

| Piece | Where | Cost |
|---|---|---|
| API, background jobs, Postgres, uploaded images, nightly backups, HTTPS | One Oracle Cloud "Always Free" VM, using this repo's `docker-compose.yml` | $0 |
| Website (Next.js) | Vercel | $0 (Hobby) |
| Android app | Built on your PC, talks to the API over HTTPS | – |

After setup, every push to the default branch that passes CI deploys itself
(`.github/workflows/deploy.yml`). Your PC is only needed for Android builds.

Time needed: about an hour, most of it waiting for Oracle and DNS.

---

## 1. Oracle account

1. Sign up at **cloud.oracle.com** ("Start for free"). A card is required for identity checks;
   Always Free resources aren't charged. Pick a **home region** close to your users (it can't be
   changed later). Free VM capacity varies by region; if one is always full, a newer account
   in another region is the fix.
2. Recommended: **upgrade the account to "Pay As You Go"** (Billing → Upgrade). Always Free
   resources stay free, but Oracle stops reclaiming free VMs it considers idle (a quiet beta
   app can look idle). Then set a **budget alert** (Billing → Budgets) at, say, $1 so you hear
   about any charge immediately.

## 2. Create the VM

On your PC, make an SSH key if you don't have one: `ssh-keygen -t ed25519` (press Enter to
accept the defaults; the public key is `~/.ssh/id_ed25519.pub`).

In the Oracle console: **Compute → Instances → Create instance**

- **Image:** Canonical **Ubuntu 24.04** (or 22.04)
- **Shape:** Change shape → **Ampere** → `VM.Standard.A1.Flex`, **2 OCPUs, 12 GB memory**
  (marked "Always Free eligible")
- **Networking:** keep "Assign a public IPv4 address"
- **SSH keys:** paste the contents of your `id_ed25519.pub`
- Create. If it says **"Out of capacity"**, try another availability domain or try again later.

Then make the IP permanent so DNS doesn't break if the VM restarts: instance → **Attached VNICs →
IPv4 addresses → Edit → Reserved public IP** (free).

## 3. Open ports 80 and 443 in Oracle's firewall

Instance page → the **subnet** link → **Security Lists** → *Default Security List* →
**Add Ingress Rules**:

| Source CIDR | Protocol | Destination port |
|---|---|---|
| `0.0.0.0/0` | TCP | `80` |
| `0.0.0.0/0` | TCP | `443` |
| `0.0.0.0/0` | UDP | `443` (optional, HTTP/3) |

(The VM also has its own firewall; `setup.sh` opens the same ports there.)

## 4. A name for the API

HTTPS needs a domain name pointing at the server's IP:

- **Your own domain:** add an **A record** `api` → the server's IP (so the API is
  `api.yourdomain.com`).
- **No domain yet (free):** sign in at **duckdns.org**, create a subdomain (e.g.
  `turnup-api.duckdns.org`) and set its IP to the server's IP.

Wait until `ping <that name>` shows the server's IP before the next step.

## 5. Set up the server

From your PC, in this repository:

```bash
scp deploy/oracle/setup.sh ubuntu@<server-ip>:
```
```bash
ssh ubuntu@<server-ip>
```

Then, on the server:

```bash
bash setup.sh
```

The script installs Docker and security updates, opens the firewall and adds swap. It asks you to:

1. **Add a read-only deploy key on GitHub** (it prints the key and waits): repository →
   Settings → Deploy keys → Add deploy key, leave "Allow write access" unchecked.
2. Enter the **API name** from step 4 and the **website address** (your Vercel URL, step 7;
   use your best guess like `https://turnup.vercel.app`; it can be changed later).

It generates the secrets, starts everything, and gets an HTTPS certificate automatically. At the
end it prints **four values for GitHub** (next step).

Check it's up: open `https://<api name>/api/health`, which should show `{"status":"ok",...}`.

## 6. Turn on automatic deploys

GitHub repository → **Settings → Secrets and variables → Actions**:

- **Secrets** (New repository secret), using the values `setup.sh` printed:
  `ORACLE_HOST`, `ORACLE_USER`, `ORACLE_KNOWN_HOSTS`, `ORACLE_SSH_KEY`
- **Variables** tab (optional): `API_URL` = `https://<api name>` so each deploy also checks the
  API from outside.

Test it: **Actions → Deploy → Run workflow**. From now on, every push to the default branch
that passes CI deploys automatically.

The Actions key can only run `deploy/oracle/deploy.sh` on the server (SSH enforces it), so it
can't be used to log in or run anything else.

## 7. Website on Vercel

1. **vercel.com → Add New → Project →** import this repository.
2. **Root Directory:** `frontend`.
3. **Environment Variables:**
   - `NEXT_PUBLIC_API_URL` = `https://<api name>`
   - `API_PROXY_ORIGIN` = `https://<api name>`
   - `NEXT_PUBLIC_SITE_URL` = the site's address (e.g. `https://turnup.vercel.app`)
4. Deploy.

If the website ended up at a different address than you gave `setup.sh`, update it on the
server (`FRONTEND_URL` and `ALLOWED_ORIGINS` in `/opt/turnup/.env`), then run
`/opt/turnup/deploy/oracle/deploy.sh`.

## 8. Android app

In `frontend/.env.local` on your PC:

```
NEXT_PUBLIC_API_URL=https://<api name>
NEXT_PUBLIC_SITE_URL=<website address>
```

Remove `CAPACITOR_DEV_SERVER_URL` (or the release build refuses to run; see
`frontend/android/app/release-guard.gradle`), then:

```bash
npm run build:capacitor
```
```bash
npx cap sync android
```

and build in Android Studio. The app's origin (`http://localhost`) is already allowed by the
server's `ALLOWED_ORIGINS`.

## 9. Payments and email

Edit `/opt/turnup/.env` on the server, then run `/opt/turnup/deploy/oracle/deploy.sh`:

- **Paystack:** `PAYSTACK_SECRET_KEY`, `PAYSTACK_PUBLIC_KEY`. In the Paystack dashboard, set the
  webhook URL to `https://<api name>/api/events/webhooks/paystack`.
- **Email:** `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, and `EMAIL_CONSOLE=false`.
  Until then, emails (verification, password reset, tickets) are printed to the logs.

---

## Day to day (on the server, in `/opt/turnup`)

| Task | Command |
|---|---|
| Status | `docker compose ps` |
| Logs | `docker compose logs -f backend` (or `worker`, `proxy`, `backup`) |
| Deploy now / apply `.env` changes | `./deploy/oracle/deploy.sh` |
| Load demo data (empty database only) | `docker compose run --rm migrate python -m app.cli seed` |
| Restart one service | `docker compose restart backend` |
| List backups | `docker compose exec backup ls -lh /backups` |
| Copy a backup to your PC | on your PC: `ssh ubuntu@<server-ip> 'cd /opt/turnup && docker compose exec -T backup cat /backups/turnup-YYYY-MM-DD.sql.gz' > turnup-backup.sql.gz` |

**Backups** are made at start-up and every 24 hours after, and kept for 14 days
(`BACKUP_KEEP_DAYS`). They live on the same VM, so copy one to your PC now and then.

**Venue verification files** (CAC certificates, IDs, agent visit photos) live in the separate
`kyc` volume, not in the database backups. They're personal data: if you back them up, keep the
copy encrypted and private. They're deleted automatically 12 months after a venue closes.

### Restore a backup

This replaces the current database with the backup.

```bash
cd /opt/turnup && docker compose stop backend worker
docker compose exec -T db psql -U turnup -d postgres -c 'DROP DATABASE turnup;' -c 'CREATE DATABASE turnup;'
docker compose exec -T backup sh -c 'gunzip -c /backups/turnup-YYYY-MM-DD.sql.gz | psql -q'
./deploy/oracle/deploy.sh
```

## Troubleshooting

- **`https://<api name>` doesn't load / no certificate:** check the name resolves to the server
  (`ping`), ports 80/443 are open (step 3), and `docker compose logs proxy` for certificate errors.
- **Website or app says it can't reach the server / CORS error in the browser console:** the
  page's address must be in `ALLOWED_ORIGINS` (the website's URL, plus `http://localhost` for
  the app), with no trailing slash.
- **A deploy failed in GitHub Actions:** the job log shows the backend logs. Fix and push again,
  or run `./deploy/oracle/deploy.sh` on the server to see it live.
- **Oracle "Out of capacity" when creating the VM:** a common free-tier problem. Retry later or
  use another availability domain.
