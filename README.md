# Hotel Data — Autumn

Seeded hotel marketing analytics data and database infrastructure for the Autumn dashboard.

The dataset contains 730 days of realistic hotel marketing data, including bookings, campaigns, channels, markets, and property performance.

## Project Structure

- `data/` — Seeded CSV datasets
- `sql/` — PostgreSQL schema
- `src/` — Data generation and seeding scripts
- `tests/` — Data quality and database integrity tests
- `config.yaml` — Project configuration
- `requirements.txt` — Python dependencies
- `Makefile` — Common development commands

## Setup

### 1. Clone the repository

    git clone https://github.com/miaolanzhang1101-coder/hotel-marketing-analytics-db.git
    cd hotel-marketing-analytics-db

### 2. Install dependencies

    pip install -r requirements.txt

### 3. Configure the database

Create a `.env` file in the project root and add your PostgreSQL connection string:

    DATABASE_URL="your-database-connection-string"

Use a hosted PostgreSQL database such as Supabase or Neon.

Do not commit `.env` to GitHub.

### 4. Create the database schema

    psql "$DATABASE_URL" -f sql/schema.sql

### 5. Seed the database

    python -m src.seed

This loads the 730-day hotel marketing dataset into the database.

### 6. Run tests

    pytest

The test suite checks data quality and database integrity.

## Dataset

| Dataset | Description |
| --- | --- |
| Bookings | Booking and revenue records |
| Campaigns | Marketing campaign definitions |
| Channels | Marketing channel information |
| Daily Campaign Metrics | Daily campaign performance |
| Daily Channel Metrics | Daily channel performance |
| Daily Market Metrics | Feeder-market performance |
| Daily Property Metrics | Hotel-level daily performance |
| Markets | Geographic market definitions |

## Requirements

- Python 3.10+
- PostgreSQL
- PostgreSQL `psql` command-line tools
- Hosted PostgreSQL database

## Security

Never commit database credentials or connection strings. Use `.env` for local configuration and `.env.example` as the template.
