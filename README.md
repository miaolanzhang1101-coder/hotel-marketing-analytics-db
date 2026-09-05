# Marlow House Analytics

Seed data and schema for a marketing dashboard backing Marlow House, a
modeled independent 74-room hotel on the California coast. Covers 730 days (2024-09-01 to 2026-08-31) so
year-over-year comparisons are possible across the full range.

Targets Postgres. Tested against a local instance; works unchanged with the
Supabase and Neon free tiers.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env        # set DATABASE_URL, optionally DB_SCHEMA

make generate               # regenerate the dataset (deterministic)
make seed                   # apply schema and load a database
make test                   # data quality + database integrity suites
```

The test suite has two layers. Data quality tests run against the committed
CSVs and need nothing installed beyond requirements.txt; they cover booking
invariants, foreign keys, occupancy bounds, aggregate reconciliation,
seasonality direction, campaign budget pacing, and full regeneration
determinism. Database integrity tests run only when DATABASE_URL is set and
verify the seeded instance: row counts, date coverage, orphan checks, and
that every dashboard view returns rows.

`src/seed.py` applies the schema (drop and recreate, safe to re-run), bulk
loads the CSVs with COPY, and finishes with reconciliation queries: row
counts, date coverage, aggregate-vs-bookings consistency, and orphaned
foreign key checks.

## Configuration

No values are hardcoded in the source. All parameters live in two places:

- `config.yaml` holds every business and environment parameter: the date
  window, property economics, seasonality coefficients, channel and market
  definitions, campaign flights and budgets, funnel rates, and the seed load
  order. `src/settings.py` loads it into typed, frozen dataclasses.
- `.env` holds secrets and deployment specifics: `DATABASE_URL` (required
  for seeding) and optional `DB_SCHEMA` for a non-default target schema,
  which is created if missing.

All paths resolve relative to the project root. Environment overrides:
`CONFIG_PATH` and `DATA_DIR`. Both entry points also accept CLI parameters:

```bash
python -m src.generate --seed 7 --start 2025-01-01 --end 2025-12-31 --out-dir /tmp/out
python -m src.seed --config other.yaml --data-dir /tmp/out --skip-schema
```

Changing `config.yaml` (a different property size, new campaigns, another
date range) regenerates a consistent dataset with no code changes.

## Data model

The row-level `bookings` table is the source of truth. All daily fact tables
are derived from it, so dashboard views built on different tables agree with
each other.

```
markets, channels, campaigns          dimensions
bookings                    18,690    row-level fact
daily_property_metrics         730    occupancy, ADR, RevPAR, revenue, pace
daily_channel_metrics        5,110    sessions, bookings, revenue, spend
daily_campaign_metrics         788    flighted spend, clicks, attribution
daily_market_metrics         8,760    feeder market sessions and bookings
```

`sql/schema.sql` also defines views used directly by the dashboard:
`v_monthly_summary`, `v_campaign_summary` (ROAS, cost per booking),
`v_market_summary` (booking share), `v_channel_monthly` (conversion rate).

## Modeling assumptions

Demand is modeled per arrival date, and booking dates are back-computed from
a lead-time distribution. This keeps the occupancy curve and the
booking-pace curve consistent.

- Annual seasonality peaking in July-August (89% occupancy, $328 ADR) with a
  January trough (38%, $160), holiday spikes, and Friday/Saturday arrival
  peaks typical of a leisure property.
- Year two grows roughly 8% in demand and 5% in ADR.
- OTA share drifts from 31% to 28% while direct and email grow.
- 14 flighted campaigns with budgets, daily spend, clicks, impressions, and
  probabilistic booking attribution. Performance varies by design: paid
  search geo campaigns reach 7-8x ROAS, awareness campaigns sit near 1x.
- Feeder markets weight toward Los Angeles (28% of bookings) with seasonal
  shifts: Phoenix over-indexes in summer, Seattle and Chicago in winter.
- Per-channel conversion rates (email 4.7%, paid search 3.1%, paid social
  0.8%) tie sessions to bookings. Lead times average 30 days for summer
  stays and 19 in winter; cancellation rate is 11%.

Headline KPIs land near published industry figures for an upper-upscale
leisure property: 65% occupancy, $176 RevPAR, 1.8% site conversion. The OTA
share is deliberately below the independent-hotel average, reflecting a
property with an established direct booking program.

## Layout

```
config.yaml         all business and environment parameters
.env.example        secrets template (DATABASE_URL, DB_SCHEMA)
src/settings.py     typed config loading, env overrides
src/model.py        seasonality, growth, channel mix, campaign lift
src/bookings.py     row-level booking generation
src/aggregates.py   daily fact tables derived from bookings
src/generate.py     entry point, writes data/*.csv
src/seed.py         schema + COPY loader + validations
sql/schema.sql      tables, constraints, indexes, views
tests/              data quality + database integrity suites
data/               generated CSVs, committed for reproducibility
```
