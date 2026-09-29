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

## 2. Host on Cloudflare Pages

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

## 3. Point the domain

1. In Cloudflare, **Add a site**, enter `northvanvotes.ca`
2. Copy the two nameservers it gives you
3. At your registrar, replace the existing nameservers with those two
4. Back in **Pages → your project → Custom domains**, add `northvanvotes.ca`
   and `www.northvanvotes.ca`

DNS propagation is usually minutes, occasionally a few hours. SSL is automatic.

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
