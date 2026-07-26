# Self-hosted, E2B-compatible sandboxes — the whole thing

Companion code for *"Self-hosting an E2B-compatible sandbox stack, from an empty
server"*. Four scripts take a blank VM to a deployment the **unmodified** `e2b`
Python SDK talks to.

Verified end to end on CentOS Stream 10 against `e2b` 2.35.0 and
`e2b-code-interpreter` 2.9.0: **50 checks, 48 passing** (the 2 failures are unimplemented calls, see below).

## What you need

- A server with a public IP and ports 80/443 free
- A domain whose nameservers are at a provider [lego](https://go-acme.github.io/lego/dns/)
  supports (~150 of them), plus API credentials for it
- Nothing else — Docker gets installed by step 1

## Run it

```bash
export SANDRPOD_DOMAIN=example.com
export ACME_EMAIL=you@example.com

./01-install-docker.sh

# two A records: api.<domain> and *.<domain>, both pointing at this server.
# The wildcard is the part that matters — E2B addresses services inside a
# sandbox as <port>-<sandboxID>.<domain>, and the ID does not exist until the
# sandbox does.
cat > dns.env <<'ENV'
TENCENTCLOUD_SECRET_ID=...
TENCENTCLOUD_SECRET_KEY=...
ENV
chmod 600 dns.env
set -a; source dns.env; set +a
./tcdns.py upsert "$SANDRPOD_DOMAIN" api "$(curl -s ifconfig.me)"
./tcdns.py upsert "$SANDRPOD_DOMAIN" '*' "$(curl -s ifconfig.me)"

./02-issue-cert.sh      # wildcard cert via DNS-01
./03-deploy.sh          # four containers + an e2b_-shaped API key
```

Then, from anywhere:

```bash
pip install e2b e2b-code-interpreter     # official packages, untouched
export E2B_DOMAIN=example.com
export E2B_API_KEY=e2b_...               # printed by 03-deploy.sh

python e2b_sweep.py                      # 30 checks: lifecycle, fs, commands, PTY, ports
python e2b_sweep_code.py                 # 14 checks: run_code, contexts, charts
```

Certificate renewal:

```bash
cp lego-renew.{service,timer} /etc/systemd/system/
systemctl enable --now lego-renew.timer   # daily; no-ops until <30 days left
```

## Files

| | |
|---|---|
| `01-install-docker.sh` | Docker CE on CentOS Stream 10 |
| `tcdns.py` | ~90-line stdlib-only DNSPod client (TC3-signed) for the two A records |
| `02-issue-cert.sh` | lego DNS-01, `<domain>` + `*.<domain>` |
| `03-deploy.sh` | secrets, `compose up`, issues the API key |
| `docker-compose.yml` | Postgres + control plane + worker + Caddy |
| `Caddyfile` | one `:443` block, wildcard cert, Host preserved |
| `lego-renew.*` | daily renewal timer, reloads Caddy on success |
| `e2b_sweep.py` | core SDK surface |
| `e2b_sweep_code.py` | code interpreter, contexts, matplotlib charts |

## Three things that will bite you

**The wildcard record.** Everything else is ordinary; this is the one piece
without which nothing works. Test a name that does not exist yet:
`getent ahostsv4 8000-abc.$SANDRPOD_DOMAIN`.

**The `Host` header.** The backend routes control-plane vs. which-sandbox
entirely on `Host`. Caddy forwards it by default. If you swap in nginx you must
write `proxy_set_header Host $host;` or every sandbox URL silently stops
resolving to a sandbox.

**The Docker network name.** `SANDRPOD_NETWORK` goes straight to the Docker API,
and Compose prefixes network names with the project name unless you pin them —
which is why `docker-compose.yml` sets `name: sandrpod`. Get this wrong and the
failure is quiet: sandboxes get created, land on the wrong network, and every
exec hangs until it times out.

## Not implemented

`create_snapshot()`, `list_snapshots()` and `fork()` return `405`. `envVars` on
create is accepted but has not been exercised against the real SDK.

## Where this came from

The walkthrough this accompanies is
[docs/PRODUCTION_DEPLOYMENT.md](https://github.com/sandrpod/sandrpod/blob/main/docs/PRODUCTION_DEPLOYMENT.md)
in the SandrPod repo, which covers the same ground as reference documentation
rather than as a narrative.

`docker-compose.yml` and `Caddyfile` here are copies of
`docker/docker-compose.prod.yml` and `docker/Caddyfile` upstream — that is where
they are maintained, so check there if something has moved on.

---

SandrPod: <https://github.com/sandrpod/sandrpod> · Apache-2.0
