import hashlib
from pathlib import Path

import os
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from dotenv import load_dotenv
from news_sentiment import ensure_sentiment
from aliases_from_yfinance import get_aliases_from_yfinance

# 1) CONFIGURATION ----------------------------------------------------------------

load_dotenv()
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")
BASE_URL = "https://newsapi.org/v2/everything"

# List of tickers you care about
TICKERS = ["NVDA", "MSFT", "AAPL", "MELI","GOOGL", "YPF"]  # <- change this

def build_query_for_ticker(ticker: str) -> str:
    """
    Create a NewsAPI query using aliases from yfinance.
    Example:
      aliases = ["NVDA", "NVIDIA", "NVIDIA Corporation"]
      -> 'NVDA OR NVIDIA OR "NVIDIA Corporation"'
    """
    aliases = get_aliases_from_yfinance(ticker)

    parts = []
    for alias in aliases:
        alias = alias.strip()
        if not alias:
            continue

        # Add quotes if there are spaces (exact phrase search)
        if " " in alias:
            parts.append(f'"{alias}"')
        else:
            parts.append(alias)

    # Safety fallback
    if not parts:
        parts = [ticker.upper()]

    query = " OR ".join(parts)
    print(f"Built query for {ticker}: {query}")
    return query

# -------------------------------- ID --------------------------------

def make_news_id(ticker: str, url: str, published_at: str | None = None) -> str:
    """
    Build a stable ID for a news article.

    Using Ticker + URL (+ publishedAt if you want).
    If the same article appears again, it will generate the same hash.
    """
    ticker = (ticker or "").upper()
    url = (url or "").strip()
    published_at = (published_at or "").strip()

    key = f"{ticker}|{url}|{published_at}"
    # SHA-256 hash to make it fixed-length and safe as an ID
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def ensure_news_id(df: pd.DataFrame) -> pd.DataFrame:
    """
    Make sure the DataFrame has a 'NewsID' column.
    If missing, compute it from Ticker + url + publishedAt.
    """
    if df.empty:
        return df

    if "NewsID" not in df.columns or df["NewsID"].isna().any():
        df["NewsID"] = df.apply(
            lambda r: make_news_id(
                r.get("Ticker", ""),
                r.get("url", ""),
                r.get("publishedAt", ""),
            ),
            axis=1,
        )

    return df

# -------------------------------- Article ID --------------------------------

#Assures that it cannot find two identical articles, from two different regions.

def make_article_key(ticker: str,
                     title: str | None,
                     published_at: str | None) -> str:
    ticker = (ticker or "").upper().strip()
    title = (title or "").strip().lower()
    published_at = (published_at or "").strip()
    key = f"{ticker}|{title}|{published_at}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def ensure_article_key(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    if "ArticleKey" not in df.columns or df["ArticleKey"].isna().any():
        df["ArticleKey"] = df.apply(
            lambda r: make_article_key(
                r.get("Ticker", ""),
                r.get("title", ""),
                r.get("publishedAt", ""),
            ),
            axis=1,
        )
    return df


# 2) LOW-LEVEL FETCH FUNCTIONS ----------------------------------------------------


def fetch_page(query: str, from_str: str, to_str: str, page: int = 1, page_size: int = 100) -> dict:
    if not NEWSAPI_KEY:
        raise RuntimeError("NEWSAPI_KEY is not set. Please add it to your .env file.")

    params = {
        "q": query,
        "from": from_str,
        "to": to_str,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": page_size,
        "page": page,
        "apiKey": NEWSAPI_KEY,
    }

    response = requests.get(BASE_URL, params=params, timeout=10)

    if response.status_code != 200:
        # Try to show the real NewsAPI error payload
        try:
            err = response.json()
            code = err.get("code")
            msg = err.get("message")
            raise RuntimeError(
                f"NewsAPI error {response.status_code} (code={code}): {msg}"
            )
        except ValueError:
            # If response is not JSON, fall back to generic HTTP error
            response.raise_for_status()

    return response.json()


def fetch_interval(query: str,
                   start: datetime,
                   end: datetime,
                   max_pages: int = 5) -> list:
    """
    Fetch news between start and end (datetimes),
    paging through results up to max_pages.
    Reduce max_pages if you hit rate limits.
    """
    from_str = start.strftime("%Y-%m-%d")
    to_str = end.strftime("%Y-%m-%d")

    print(f"\n⏳ Interval {from_str} -> {to_str} | query={query!r}")
    articles = []
    page = 1

    while page <= max_pages:
        print(f"  - Page {page}")
        data = fetch_page(query, from_str, to_str, page=page)
        batch = data.get("articles", [])

        if not batch:
            break

        articles.extend(batch)

        # If fewer than page_size, there are no more pages
        if len(batch) < 100:
            break

        page += 1
        time.sleep(1)  # small pause for rate limits

    return articles


def fetch_last_n_days_for_query(query: str,
                                days: int = 30,
                                step_days: int = 5,
                                max_pages_per_interval: int = 1) -> list:
    """
    Fetch news for the last `days` days for a given query (string),
    in windows of `step_days` days.

    ⚠ On the free Developer plan, NewsAPI only allows up to 30 days
      of history. Asking for more will trigger HTTP 426.
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    print(f"\n=== Fetching for query: {query!r}")
    print(f"Time range (clamped): {start.date()} -> {end.date()} (last {days} days)")

    all_articles = []
    current = start

    while current < end:
        interval_end = min(current + timedelta(days=step_days), end)
        interval_articles = fetch_interval(
            query, current, interval_end, max_pages=max_pages_per_interval
        )
        all_articles.extend(interval_articles)
        current = interval_end

    return all_articles


# 3) HIGH-LEVEL: PER TICKER ------------------------------------------------------


def fetch_news_for_ticker(ticker: str,
                          years: int = 5,
                          step_days: int = 30,
                          max_pages_per_interval: int = 1) -> pd.DataFrame:
    """
    Fetch last `years` of news for a single ticker and return a DataFrame
    tagged with the ticker symbol.
    """
    query = build_query_for_ticker(ticker)
    articles = fetch_last_n_days_for_query(
        query,
        days=30,              # Developer plan limit
        step_days=step_days,          # e.g. 5-day chunks
        max_pages_per_interval=max_pages_per_interval,
    )



    rows = []
    for a in articles:
        rows.append({
            "Ticker": ticker.upper(),
            "source": (a.get("source") or {}).get("name"),
            "author": a.get("author"),
            "title": a.get("title"),
            "description": a.get("description"),
            "url": a.get("url"),
            "publishedAt": a.get("publishedAt"),
            # Usually truncated content; good as a preview
            "content_snippet": a.get("content"),
        })

    df = pd.DataFrame(rows)

    # You might want to deduplicate by URL for that ticker:
    if not df.empty:
        df = df.drop_duplicates(subset=["url"])
        df = ensure_news_id(df) # ensure NewsID column

    return df


def main():
    # ---------------- CONFIG ----------------
    step_days = 5
    # Developer plan limit: max 100 results per query.
    # With page_size=100 in fetch_page, keep this at 1.
    max_pages_per_interval = 1

    db_path = Path("news_db.csv")

    # ------------- FETCH PER TICKER -------------
    all_dfs = []
    hit_rate_limit = False

    for ticker in TICKERS:
        print("\n############################")
        print(f"###   TICKER: {ticker}")
        print("############################")

        if hit_rate_limit:
            print("  Skipping this ticker due to earlier rate limit.")
            continue

        try:
            df_ticker = fetch_news_for_ticker(
                ticker,
                years=5,               # kept for compatibility
                step_days=step_days,
                max_pages_per_interval=max_pages_per_interval,
            )
        except RuntimeError as e:
            if "NewsAPI error 429" in str(e) or "rateLimited" in str(e):
                print(f"  ⚠️ Rate limit reached while fetching {ticker}: {e}")
                hit_rate_limit = True
                # stop fetching new tickers, but continue the script
                continue
            else:
                # other errors should still stop the script
                raise

        print(f"  -> Retrieved {len(df_ticker)} articles for {ticker}")
        all_dfs.append(df_ticker)

    # ------------- BUILD OR LOAD DATAFRAME -------------
    if not all_dfs:
        # No new data fetched this run
        if not db_path.exists():
            print("\n⚠️ No articles fetched and no existing DB found. Nothing to do.")
            return

        print("\n⚠️ No new articles fetched (likely rate limit). Using existing DB only.")
        final_df = pd.read_csv(db_path)
        final_df = ensure_news_id(final_df)
        final_df = ensure_article_key(final_df)

    else:
        # We have new data to merge
        new_df = pd.concat(all_dfs, ignore_index=True)
        new_df = ensure_news_id(new_df)
        new_df = ensure_article_key(new_df)

        if db_path.exists():
            # Load existing DB
            existing_df = pd.read_csv(db_path)
            existing_df = ensure_news_id(existing_df)
            existing_df = ensure_article_key(existing_df)

            existing_ids = set(existing_df["NewsID"])

            before = len(new_df)
            new_only_df = new_df[~new_df["NewsID"].isin(existing_ids)]
            after = len(new_only_df)

            print(f"\nFound existing DB with {len(existing_df)} rows.")
            print(f"Fetched {before} rows this run.")
            print(f"New unique articles to add: {after}")

            if after == 0:
                final_df = existing_df
            else:
                final_df = pd.concat([existing_df, new_only_df], ignore_index=True)
        else:
            print("\nNo existing DB found. Creating news_db.csv from scratch.")
            final_df = new_df

    # ------------- DEDUP & SENTIMENT -------------
    final_df = ensure_article_key(final_df)
    final_df = final_df.drop_duplicates(subset=["NewsID"])
    final_df = final_df.drop_duplicates(subset=["ArticleKey"])
    print(f"\nFinal DB size after merge and deduplication: {len(final_df)} rows.")

    final_df = ensure_sentiment(final_df)

    # ------------- SAVE -------------
    final_df.to_csv(db_path, index=False, encoding="utf-8")
    print(f"\n✅ Saved {len(final_df)} total rows to {db_path.name}")


if __name__ == "__main__":
    main()
