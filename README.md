# OwnerRez MCP connector (hosted)

A remote MCP server that gives Claude tools to read and act on your
OwnerRez account: bookings, properties, guests, financials (quotes,
payments, refunds, fees), and guest messaging.

It's built on top of the open-source [`ownerrez-mcp`](https://github.com/buildwithmanag/ownerrez-mcp)
project (MIT licensed) — this repo adds a Streamable HTTP transport and a
bearer-token gate around it so it can run as a public web service and be
added to Claude as a **custom connector**, instead of only running locally.

## Read this first: what it can and can't do

OwnerRez's account-level API ("API for Apps," the kind you get a personal
token for) is **read-plus-messaging**, not a full read/write booking API:

| Can do | Can't do |
|---|---|
| List/read bookings, properties, guests, owners | Create or update a booking |
| See who's currently checked in | Block or unblock calendar dates |
| Read quotes, payments, refunds, fees | Create expenses |
| Send/read guest messages on existing threads | Create a new message thread |
| Create/list/delete webhook subscriptions | |

Creating bookings and blocking dates only exists on OwnerRez's separate
**Channel API**, which is reserved for approved OTA/channel-partner
integrations (Airbnb, Vrbo, etc.) — not something available through your
own account's API token. So "block these dates" or "create this booking"
isn't something this connector — or any tool using your personal OwnerRez
credentials — can do today. If you need to block dates programmatically,
the practical options are OwnerRez's own calendar UI, or (since you already
have PriceLabs connected) PriceLabs' date-override tools, which sync back
to OwnerRez.

Everything in the left column is real and working in this server.

## 1. Get an OwnerRez Personal Access Token

In OwnerRez: **Settings → API → Personal Access Tokens** (see OwnerRez's own
[Authentication docs](https://www.ownerrez.com/support/articles/api-auth) if
that's not exactly where you find it — OwnerRez has reorganized this menu
before). Generate a token; you'll get a **username** and a **token** value.
Keep both — you'll paste them into your hosting platform's environment
variables, never into a browser or chat.

## 2. Generate a connector access token

This is a separate secret — not from OwnerRez — that Claude will send back
on every request so random visitors can't hit your server and pull your
booking data. Generate one:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Save it; you'll need it in step 3 and step 4.

## 3. Deploy

### Option A — Render (recommended, no server ops)

1. This repo is already on GitHub at `gcwharton-a11y/ownerrez-mcp`.
2. In the [Render dashboard](https://dashboard.render.com/), choose
   **New + → Blueprint**, connect your GitHub account if prompted, and pick
   this repo — `render.yaml` here configures the service automatically.
3. When prompted for environment variables, set:
   - `MCP_ACCESS_TOKEN` — the secret from step 2
   - `OWNERREZ_USERNAME` / `OWNERREZ_TOKEN` — from step 1
   - `OWNERREZ_READ_ONLY` — leave as `1` to start read-only, or clear it to
     allow guest-message sending and webhook management (see the table
     above — this never enables booking/date writes, because OwnerRez's API
     doesn't offer them)
4. Deploy. Render gives you a URL like `https://ownerrez-mcp.onrender.com`.
   Your connector URL is that plus `/mcp/` — e.g.
   `https://ownerrez-mcp.onrender.com/mcp/`.

### Option B — Any Docker host (Railway, Fly.io, your own VM)

The included `Dockerfile` runs anywhere that accepts a container and a
`PORT` env var:

```bash
docker build -t ownerrez-mcp .
docker run -p 8080:8080 \
  -e MCP_ACCESS_TOKEN=... \
  -e OWNERREZ_USERNAME=... \
  -e OWNERREZ_TOKEN=... \
  -e OWNERREZ_READ_ONLY=1 \
  ownerrez-mcp
```

### Local test (no deploy)

```bash
git clone https://github.com/gcwharton-a11y/ownerrez-mcp.git
cd ownerrez-mcp
pip install -r requirements.txt
MCP_ACCESS_TOKEN=devtoken OWNERREZ_USERNAME=... OWNERREZ_TOKEN=... \
  uvicorn http_app:app --host 0.0.0.0 --port 8080
curl http://localhost:8080/health   # -> ok
```

## 4. Add it to Claude as a custom connector

1. In Claude, go to **Settings → Connectors → Add custom connector** (an
   org admin needs to do this step).
2. Server URL: `https://<your-deployed-host>/mcp/` (trailing slash).
3. Authentication type: choose **request headers** (static header / API
   key auth). Enter:
   - Header name: `Authorization`
   - Header value: `Bearer <the MCP_ACCESS_TOKEN from step 2>`
4. Save. Claude will send that header on every call to your server, and
   `http_app.py`'s middleware checks it before anything touches OwnerRez.

If your Claude plan doesn't yet expose header-based auth for custom
connectors (it's in beta), the fallback is to keep the server unlisted
(don't share the URL) — anyone without the token still gets a `401` on
every request, so it's not open even without connector-level auth wired up.

## Security notes

- The bearer token gates the **whole account's** OwnerRez data — treat it
  like a password. Rotate it (regenerate + redeploy with a new
  `MCP_ACCESS_TOKEN`) if you ever suspect it leaked.
- `OWNERREZ_READ_ONLY=1` is the safer default; only clear it if you want
  Claude to be able to send guest messages or manage webhook subscriptions
  on your behalf.
- Nothing here can create, modify, or cancel a booking, or touch pricing —
  that's outside what OwnerRez's account API exposes, not just a
  restriction of this server.

## Credit

Tool definitions, the OwnerRez API client, retry/backoff, and read-only
guard logic are from [buildwithmanag/ownerrez-mcp](https://github.com/buildwithmanag/ownerrez-mcp)
(MIT license, included as `LICENSE.upstream`). `http_app.py` and the
deployment files in this repo are the additions that make it run as a
hosted, authenticated remote server instead of a local stdio process.
