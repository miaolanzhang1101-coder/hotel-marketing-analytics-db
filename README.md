hotel-data-autumn

Seeded hotel marketing analytics data and database setup for the Autumn dashboard.



The dataset covers 730 days of realistic marketing, booking, channel, campaign, market, and property performance data for an independent hotel.

Project Structure

data/       Seeded CSV data
sql/        Database schema
src/        Data generation and seeding scripts
tests/      Data quality and database tests


Setup

1. Install dependencies

pip install -r requirements.txt


2. Set your database

Create a .env file:

DATABASE_URL="your-database-connection-string"


3. Create the database schema

psql "$DATABASE_URL" -f sql/schema.sql


4. Seed the data

python -m src.seed


5. Run tests

pytest


Data

The database includes:



Bookings

Campaigns

Marketing channels

Daily campaign metrics

Daily channel metrics

Daily market metrics

Daily property metrics

Feeder markets



The data is designed to support the Autumn hotel marketing dashboard and its performance and detail views.

Requirements

Python 3.10+

PostgreSQL

A hosted PostgreSQL database such as Supabase or NeonO
