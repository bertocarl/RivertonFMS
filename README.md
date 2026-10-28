# FMS for TotalEnergies Bonje

A Django rewrite of the station's FMS, GLPY and SALES programs as one system. It covers shifts and pump meters, sales entry, credit customers and invoices, fuel deliveries and tanks, a double-entry ledger, and the daily DSSR report with page-range printing.

> **Read this first.** The code was written and statically checked in an environment with no Django installed and no internet, so it has **not been run**. The test suite in `tests/` is written to exercise every flow, but run it before you trust the system (step 3 below). Migrations are not pre-generated for the same reason; the setup steps create them.

## Quick start (SQLite, no Redis)

```bash
sh scripts/setup.sh --demo        # venv, install, migrations, seed, demo users
. .venv/bin/activate
python manage.py test             # run this once; everything should pass
python manage.py runserver
```

Open http://127.0.0.1:8000. Demo users (`manager`, `supervisor`, `attendant`, `accountant`) all use the password `ChangeMe123!`. Change them, or skip `--demo` and run `python manage.py createsuperuser` instead.

After `makemigrations` runs, commit the new `*/migrations/` files so every install uses the same schema.

## Docker (PostgreSQL, Redis, Celery worker)

```bash
docker compose up --build
```

The web container generates migrations into your project folder, migrates, seeds the station and starts Gunicorn on port 8000. Create your first user with `docker compose exec web python manage.py createsuperuser`.

## What is inside

| App | What it does |
| --- | --- |
| `accounts` | Users with four roles: attendant, supervisor, accountant, manager. |
| `forecourt` | Station, products and price history, tanks, pumps with `ifsf_node_id`, nozzles, stock movements, dashboard, IFSF gateway API. |
| `shifts` | Open a shift, enter closing meters and dips, verify, back up, close. |
| `sales` | Sale entries (cash, M-Pesa, card, credit), automatic invoices, credit limits, customer payments. |
| `purchases` | Suppliers, deliveries into tanks (with capacity checks), supplier payments. |
| `ledger` | Chart of accounts, balanced journals, expenses, trial balance. Sales, purchases, payments and shift closes post here automatically. |
| `reports` | DSSR, trial balance and debtors. Built by a Celery task, shown page by page, printed to PDF by page range. |

## How the notice's workflows map to this system

- **One program.** FMS, GLPY and SALES are now one login and one menu.
- **Login.** Type the password, press Tab, press OK.
- **Consecutive entries.** Save a sale, press **Next** on the confirmation screen, or just press **F3** on any page that offers a new entry.
- **Shift closing.** Verify the shift (the date is entered there once), back up the data, close the shift. Nothing is asked again at close. A shortage must be accepted at verification.
- **Entering the date.** On the verify screen click a meter in the Electric cash column and press Tab. The date box turns green. A small "Unlock" link is there for mouse-only use.
- **Printing a page range.** Open a report, use **Start Page** and **End Page** under the report. For pages 4 to 10 enter 4 and 10 and press Print pages. A PDF of exactly those pages opens.

Shift states are Open, then Verified, then Closed. Sales and meter changes are only allowed while a shift is Open. A supervisor can reopen a Verified shift for corrections.

## Money and stock rules

- Fuel sales entries record **how** pump sales were paid. Fuel stock comes off the tanks from pump meter litres when the shift closes.
- Shop, lubricant and gas sales reduce stock immediately.
- At close, metered fuel value is compared with recorded fuel sales. The difference is booked to Cash over/short.
- Credit sales create an invoice. Customer payments settle the oldest open invoices first.
- Every posting is a balanced journal. The ledger refuses unbalanced entries.

## IFSF pump gateway

Each pump has an `ifsf_node_id` (Setup, Pumps and IFSF nodes). Your forecourt controller or a small bridge posts each dispense:

```bash
curl -X POST http://SERVER:8000/api/ifsf/transaction/ \
  -H "X-IFSF-Token: $IFSF_API_TOKEN" -H "Content-Type: application/json" \
  -d '{"node_id":"IFSF-BONJE-01","nozzle":1,"volume":"20.50","amount":"3895.00",
       "totalizer_volume":"10020.50","totalizer_amount":"1903900.00",
       "transaction_id":"T-0001","timestamp":"2026-10-28T09:15:00+03:00"}'
```

- `GET /api/ifsf/nodes/` lists the active nodes and nozzles for configuring the bridge.
- Repeating a `transaction_id` is safe: it returns `duplicate` and changes nothing.
- Totalizers update the nozzle. On the closing-meter screen, **Fill from pump totalizers** copies them in.
- This is an HTTP bridge, not a full IFSF protocol stack. Writing the bridge for your controller's make is separate work.

## Celery and Redis

Reports run through Celery. With `USE_CELERY=0` (the default) they run inside the request, so you do not need Redis. Set `USE_CELERY=1`, point `CELERY_BROKER_URL` at Redis and start a worker: `celery -A config worker -l info`. The report page polls until the report is ready.

## Before real use

1. **Prices are placeholders.** Set today's pump and cost prices under Products and prices.
2. Set a real `DJANGO_SECRET_KEY`, `IFSF_API_TOKEN`, `DJANGO_DEBUG=0` and `DJANGO_ALLOWED_HOSTS`. Serve over HTTPS and set `SECURE_COOKIES=1`.
3. Enter real opening tank levels and opening pump meters. Set each nozzle's totalizers to the current pump readings before the first shift.
4. Shift backups are saved in `backups/` and also downloaded. Copy that folder off the machine regularly, and back up the database too.
5. The page loads Tailwind CSS and HTMX from public CDNs. For a station with unreliable internet, download those files into `static/` and point `templates/base.html` at them.

## Not included

- KRA eTIMS or fiscal device integration, and VAT handling. Prices are treated as final.
- M-Pesa or card terminal integration. Operators type the M-Pesa code or slip number.
- Payroll, multi-station consolidation (the models carry a station, but screens assume one), and bank reconciliation.
- Edits to posted journals. Corrections are made with new entries.

## Layout

```
config/       settings, URLs, Celery
common/       shared forms, list/form views, role checks, formatting
accounts/ forecourt/ shifts/ sales/ purchases/ ledger/ reports/
templates/    all screens
tests/        end-to-end tests of shifts, sales, purchases, IFSF API, reports, pages
scripts/      setup and Docker entrypoint
```
