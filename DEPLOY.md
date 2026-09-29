# Deploying North Van Votes

Static site, no server, no database. Build it and upload a folder.

**Build output is 2.3 MB.** The whole thing — 76 pages, 46 photos, all of it.

---

## 1. Buy the domain

`northvanvotes.ca` was free as of 2026-09-29. Take the `.ca`: it needs Canadian
presence, which you have, and it reads as local and civic.

**Cloudflare Registrar does not sell `.ca`**, so buy it at a CIRA-accredited
registrar and point the nameservers at Cloudflare afterwards:

- [Porkbun](https://porkbun.com) — cheapest, no upsell noise
- [Namecheap](https://namecheap.com)
- [Rebel](https://rebel.ca) — Canadian

Consider grabbing `northvanvotes.com` too (~$15) so nobody else points it
somewhere odd mid-campaign. Park it and redirect.

## Current state (set up 2026-09-29)

The VPS is **already configured and serving**. Caddy v2.11.4 is installed and
running, ports 80/443 are open in `ufw`, the site is at
`/var/www/northvanvotes`, and `xray` (the VPN, port 27372) and
`market-research-agent-swarm` (port 5000) were left untouched.

**Only DNS remains.** See "Pointing the domain" below.

To redeploy after any change: `bash deploy/deploy.sh`

## 2a. Hosting on your own VPS

`deploy/` has everything: a `Caddyfile`, a one-time `setup-vps.sh`, and
`deploy.sh` which builds on the Mac and rsyncs `dist/` up. The VPS only serves
files — no Node, no build step, nothing competing with the Etsy pipeline for
memory.

```bash
scp -r deploy 209.250.232.171:~/northvan-votes/    # or git clone on the box
ssh 209.250.232.171 'bash ~/northvan-votes/deploy/setup-vps.sh'
bash deploy/deploy.sh
```

Caddy issues and renews TLS by itself — no certbot, no renewal cron.

**Two things measured on 2026-09-29 that matter for this choice:**

- **The VPS is in Frankfurt** (Vultr, AS20473). Every request from a North
  Vancouver phone crosses the Atlantic and a continent. For reference, from this
  machine `cnv.org` connects in ~28 ms and a Cloudflare edge in ~24 ms.
- **Ports 80 and 443 time out** from outside, so the firewall will need opening
  (Vultr's cloud firewall as well as `ufw`).

Neither is a blocker, but put Cloudflare's free proxy in front of it — see below.

## 2b. Host on Cloudflare Pages

Free, unlimited bandwidth, global CDN, free SSL. Bandwidth matters here: traffic
will spike on **October 7** and **October 17**, which is exactly when a metered
free tier would cut out. Vercel's free tier restricts commercial use and Netlify
caps at 100 GB/month.

1. Create a Cloudflare account, go to **Workers & Pages → Create → Pages**
2. **Connect to Git**, pick this repository
3. Build settings:

   | Setting | Value |
   |---|---|
   | Framework preset | Astro |
   | Build command | `npm run build` |
   | Build output directory | `dist` |
   | Root directory | `site` |

4. Environment variables: `NODE_VERSION` = `20`
5. Deploy. First build takes about a minute; later ones ~20 seconds.

Every push to `main` redeploys automatically.

## 3. Pointing the domain (VPS + Cloudflare proxy)

The order matters. Caddy proves it controls the domain over plain HTTP, so give
it a clear path to do that **before** turning the proxy on.

1. Cloudflare → **Add a site** → `northvanvotes.ca`. Copy the two nameservers.
2. At the registrar (Porkbun), replace the nameservers with those two.
3. In Cloudflare **DNS**, add:

   | Type | Name | Content | Proxy |
   |---|---|---|---|
   | A | `northvanvotes.ca` | `209.250.232.171` | **DNS only** (grey) |
   | CNAME | `www` | `northvanvotes.ca` | **DNS only** (grey) |

4. Wait for it to resolve, then load `https://northvanvotes.ca`. Caddy fetches a
   Let's Encrypt certificate on that first request — about 30 seconds.
5. **Only once that works**, flip both records to **Proxied** (orange) and set
   **SSL/TLS → Full (strict)**.

Going straight to proxied can leave Caddy unable to complete the ACME challenge
and stuck retrying. Grey first is foolproof and costs one extra minute.

Once proxied: Cloudflare's Vancouver edge serves North Vancouver readers,
Frankfurt is hit only on a cache miss, and the origin IP — the same box running
your VPN and the Etsy pipeline — stops being public.

## 4. Before it goes public

- [ ] Re-check advance voting dates and locations against
      [cnv.org](https://www.cnv.org/City-Hall/General-Local-Election/2026-General-Local-Election)
      and [dnv.org](https://www.dnv.org/government-administration/voting-dates-and-locations),
      then update `VERIFIED` in `site/src/lib/voting.ts`. **A stale polling
      place is the one error that actually costs someone their vote.**
- [ ] Set up `corrections@northvanvotes.ca` — Cloudflare Email Routing forwards
      it to your inbox for free. The address is already printed on `/methodology`.
- [ ] Confirm the Buy Me a Coffee link resolves.

## Updating after launch

```bash
.venv/bin/python -m pipeline.build_dataset   # re-scrape, re-assert
git add -A && git commit -m "..." && git push # Cloudflare rebuilds on push
```

The build refuses to publish if the candidate count changed, a category is
unknown, or any quote no longer matches the source it cites. That is deliberate:
a silent scrape failure would be worse than a failed deploy.

## What is not configured

- **No analytics.** Deliberate — `/methodology` tells readers the site tracks
  nobody, and that should stay true. If you ever want counts, Cloudflare's Web
  Analytics is server-side and sets no cookies.
- **`script-src` keeps `'unsafe-inline'`** in `public/_headers`, because the
  countdown, shuffle and ballot list are inline scripts. Everything else in the
  CSP is locked down, and the site takes no user input.
