# CIC Compass: Hosting Costs

Budget (NFR-5): **$20/month** recurring, plus $250 one-time. Prices read from vendor pages on **2026-11-14**; re-check before handing over (see "Human verification").

## Monthly total

Two setups: what runs **now** (hackathon demo, everything free) and what CIC should run **in production** (always on).

| Item | Now (demo) | Production for CIC | Status |
|---|---|---|---|
| Render web service (FastAPI + SPA, one Docker image) | Free instance (0.1 CPU, 512 MB): **$0**, sleeps after 15 min idle | Starter instance (0.5 CPU, 512 MB): **≈ $7** | ⚠️ Starter price **unverified**: the pricing page did not render for our fetcher; confirm on render.com/pricing |
| Render workspace | Hobby: $0 | Hobby: $0 | verified |
| Neon Postgres | Free: $0 | Free: $0 | verified |
| Resend email | Free: $0 (dry-run, unused) | Free: $0 | verified |
| **Total** | **$0 / month** | **≈ $7 / month** | both within the $20 budget |

Switching to production is one line: `plan: free` → `plan: starter` in `render.yaml` (or change the instance type in the Render dashboard).

One-time: $0 so far. A sending domain for live email (if CIC does not already own one) is ~$10–15/year at any registrar and would come from the $250 one-time budget.

## Vendor terms and sources

**Render** ([compute plans](https://render.com/docs/compute-plans), [workspace plans](https://render.com/docs/platform-features-by-plan), [bandwidth](https://render.com/docs/outbound-bandwidth), [free tier](https://render.com/docs/free), [deploys](https://render.com/docs/deploys#pre-deploy-command), [shell](https://render.com/docs/ssh))
- "Starter" is the legacy name for plan `0.5c-512mb`: 0.5 CPU, 512 MB. Docs refer pricing to [render.com/pricing](https://render.com/pricing).
- Hobby workspace: "does not have a monthly fee, so you only pay for usage"; 1 team member, up to 25 services.
- Included outbound bandwidth on Hobby: 5 GB/month; overage $0.15/GB. A board-sized app stays far below this.
- Paid web services get dashboard Shell/SSH and a pre-deploy command. The free instance has neither and "spins down" after 15 minutes idle (about one minute to wake); free instances share 750 instance hours per workspace per month, enough for one service running all month.
- Free is fine for the demo because migrations run on container start (no pre-deploy needed) and `cli setup` runs from a laptop against Neon (no Shell needed). Open the URL a minute before recording so it is awake. For CIC's daily use, Starter avoids the one-minute wake-up.

**Neon** ([pricing](https://neon.com/pricing), page dated 2026-11-04)
- Free: $0/month, permanent, no card. 100 projects; 1 GB storage per project; 100 CU-hours per project per month; scales to zero after 5 minutes idle (cannot be turned off on Free); history window 6 hours; 5 GB public egress per project per month. Going over CU-hours or egress suspends compute until the next billing period.
- Fit: a few hundred donors and a few thousand gifts are well under 1 GB. Scale-to-zero adds a short cold start on the first request after idle.
- Risk: no instant restore on Free; the 6-hour history is the only safety net. The runbook (Phase 6) will add a `pg_dump` backup step.

**Resend** ([pricing](https://resend.com/pricing))
- Free: $0/month, 3,000 emails/month, 100 emails/day, 3 domains.
- Next tier: Pro $20/month for 50,000 emails (would exceed the budget if added on top of Render; not needed for a board digest and personal thank-yous).

## Human verification

1. Open [render.com/pricing](https://render.com/pricing) and confirm the Starter instance price; replace "≈ $7" above.
2. Open [neon.com/pricing](https://neon.com/pricing) and [resend.com/pricing](https://resend.com/pricing) and confirm the Free plan numbers.
3. Before handover, the accounts move to CIC (see `docs/HANDOFF_TO_CIC.md`, Phase 6).
