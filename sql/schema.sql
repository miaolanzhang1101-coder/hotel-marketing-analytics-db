-- =============================================================================
-- Hotel marketing analytics schema (Postgres)
-- Dimensions (markets, channels, campaigns), one row-level fact (bookings),
-- four daily aggregate facts derived from bookings, and dashboard views.
-- Idempotent: safe to re-run.
-- =============================================================================

drop view if exists v_monthly_summary, v_campaign_summary, v_market_summary,
                    v_channel_monthly cascade;
drop table if exists daily_campaign_metrics, daily_market_metrics,
                     daily_channel_metrics, daily_property_metrics,
                     bookings, campaigns, channels, markets cascade;

-- ------------------------------------------------------------ dimensions
create table markets (
    id          smallint primary key,
    name        text not null unique,
    region      text not null,          -- state/province code
    country     char(2) not null,
    summer_idx  numeric(4,2) not null,  -- seasonal demand index vs baseline
    winter_idx  numeric(4,2) not null
);

create table channels (
    id                 smallint primary key,
    name               text not null unique,
    is_paid            boolean not null,
    is_website_channel boolean not null  -- traffic lands on our own site
);

create table campaigns (
    id           smallint primary key,
    name         text not null unique,
    channel_id   smallint not null references channels(id),
    objective    text not null check (objective in ('bookings','awareness')),
    start_date   date not null,
    end_date     date not null check (end_date >= start_date),
    total_budget numeric(10,2) not null
);

-- ------------------------------------------------------------ row-level fact
create table bookings (
    id             integer primary key,
    booking_date   date not null,
    checkin_date   date not null,
    checkout_date  date not null,
    nights         smallint not null check (nights between 1 and 30),
    rooms          smallint not null default 1,
    guests         smallint not null,
    market_id      smallint not null references markets(id),
    channel_id     smallint not null references channels(id),
    campaign_id    smallint references campaigns(id),   -- null = unattributed
    room_revenue   numeric(10,2) not null,
    adr            numeric(8,2) not null,
    lead_time_days smallint not null check (lead_time_days >= 0),
    status         text not null check (status in ('confirmed','cancelled')),
    check (checkout_date = checkin_date + nights)
);
create index idx_bookings_booking_date on bookings (booking_date);
create index idx_bookings_checkin      on bookings (checkin_date);
create index idx_bookings_channel      on bookings (channel_id, booking_date);
create index idx_bookings_market       on bookings (market_id, booking_date);
create index idx_bookings_campaign     on bookings (campaign_id) where campaign_id is not null;

-- ------------------------------------------------------------ daily aggregates
create table daily_property_metrics (
    date            date primary key,
    rooms_available smallint not null,
    rooms_occupied  smallint not null,
    occupancy_rate  numeric(6,4) not null,
    adr             numeric(8,2) not null,
    revpar          numeric(8,2) not null,
    room_revenue    numeric(12,2) not null,
    bookings_made   smallint not null,
    cancellations   smallint not null
);

create table daily_channel_metrics (
    date        date not null,
    channel_id  smallint not null references channels(id),
    sessions    integer not null,
    users       integer not null,
    bookings    smallint not null,
    revenue     numeric(12,2) not null,
    spend       numeric(10,2) not null,
    impressions integer not null,
    clicks      integer not null,
    primary key (date, channel_id)
);

create table daily_campaign_metrics (
    date        date not null,
    campaign_id smallint not null references campaigns(id),
    spend       numeric(10,2) not null,
    impressions integer not null,
    clicks      integer not null,
    sessions    integer not null,
    bookings    smallint not null,
    revenue     numeric(12,2) not null,
    primary key (date, campaign_id)
);

create table daily_market_metrics (
    date       date not null,
    market_id  smallint not null references markets(id),
    sessions   integer not null,
    bookings   smallint not null,
    revenue    numeric(12,2) not null,
    primary key (date, market_id)
);

-- ------------------------------------------------------------ dashboard views
create view v_monthly_summary as
select date_trunc('month', date)::date as month,
       round(avg(occupancy_rate), 4)   as occupancy,
       round(avg(adr), 2)              as adr,
       round(avg(revpar), 2)           as revpar,
       sum(room_revenue)               as revenue,
       sum(bookings_made)              as bookings,
       sum(cancellations)              as cancellations
from daily_property_metrics
group by 1 order by 1;

create view v_campaign_summary as
select c.id, c.name, ch.name as channel, c.objective,
       c.start_date, c.end_date, c.total_budget,
       coalesce(sum(m.spend), 0)    as spend,
       coalesce(sum(m.clicks), 0)   as clicks,
       coalesce(sum(m.sessions), 0) as sessions,
       coalesce(sum(m.bookings), 0) as bookings,
       coalesce(sum(m.revenue), 0)  as revenue,
       case when sum(m.spend) > 0
            then round(sum(m.revenue) / sum(m.spend), 2) end as roas,
       case when sum(m.bookings) > 0 and sum(m.spend) > 0
            then round(sum(m.spend) / sum(m.bookings), 2) end as cost_per_booking
from campaigns c
join channels ch on ch.id = c.channel_id
left join daily_campaign_metrics m on m.campaign_id = c.id
group by c.id, c.name, ch.name, c.objective, c.start_date, c.end_date,
         c.total_budget
order by c.start_date;

create view v_market_summary as
select mk.name, mk.region, mk.country,
       sum(m.sessions) as sessions,
       sum(m.bookings) as bookings,
       sum(m.revenue)  as revenue,
       round(100.0 * sum(m.bookings) / sum(sum(m.bookings)) over (), 1)
           as booking_share_pct
from daily_market_metrics m
join markets mk on mk.id = m.market_id
group by mk.id, mk.name, mk.region, mk.country
order by revenue desc;

create view v_channel_monthly as
select date_trunc('month', m.date)::date as month, ch.name as channel,
       sum(m.sessions) as sessions, sum(m.bookings) as bookings,
       sum(m.revenue) as revenue, sum(m.spend) as spend,
       case when sum(m.sessions) > 0
            then round(100.0 * sum(m.bookings) / sum(m.sessions), 2)
       end as conversion_pct
from daily_channel_metrics m
join channels ch on ch.id = m.channel_id
group by 1, ch.id, ch.name
order by 1, revenue desc;
