from __future__ import annotations

from pathlib import Path

import pandas as pd

# ---- CONFIG --------------------------------------------------------------------

INPUT_CSV = Path("news_db.csv")
OUTPUT_XLSX = Path("news_db.xlsx")

PREFERRED_COLUMNS = [
    "publishedAt",
    "Ticker",
    "source",
    "author",
    "title",
    "description",
    "sentiment_score",
    "sentiment_label",
    "url",
]

COLUMN_WIDTHS = {
    "publishedAt": 14,
    "Ticker": 8,
    "source": 25,
    "author": 20,
    "title": 50,
    "description": 70,
    "sentiment_score": 16,
    "sentiment_label": 16,
    "url": 50,
    # Summary columns:
    "article_count_total": 18,
    "article_count_1d": 16,
    "article_count_7d": 16,
    "article_count_30d": 18,
    "avg_sentiment_total": 18,
    "avg_sentiment_1d": 16,
    "avg_sentiment_7d": 16,
    "avg_sentiment_30d": 18,
    "positive_total": 16,
    "neutral_total": 16,
    "negative_total": 16,
}


# ---- HELPERS -------------------------------------------------------------------


def load_news_db(path: Path = INPUT_CSV) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Input CSV not found: {path}")

    df = pd.read_csv(path)

    # Parse datetime if present and drop timezone (Excel requires tz-naive)
    if "publishedAt" in df.columns:
        dt = pd.to_datetime(df["publishedAt"], errors="coerce", utc=True)
        df["publishedAt"] = dt.dt.tz_convert(None)

    return df


def _ordered_columns(df: pd.DataFrame) -> list[str]:
    """Return the list of columns in the order we prefer, but only those that exist."""
    cols = [c for c in PREFERRED_COLUMNS if c in df.columns]
    extras = [c for c in df.columns if c not in cols]
    return cols + extras


# ---- MAIN EXPORT ---------------------------------------------------------------


def export_news_to_excel(
    input_csv: Path = INPUT_CSV,
    output_xlsx: Path = OUTPUT_XLSX,
    include_all_sheet: bool = True,
) -> None:
    """
    Read news_db.csv and export to an Excel file with:
      - A 'Summary' sheet (totals + last 1d/7d/30d)
      - One sheet per ticker
      - (Optional) an 'All_News' sheet with all rows
    """
    df = load_news_db(input_csv)

    if df.empty:
        print("⚠️ news_db.csv is empty. Nothing to export.")
        return

    # Sort by ticker then date (newest first)
    sort_cols = []
    ascending = []
    if "Ticker" in df.columns:
        sort_cols.append("Ticker")
        ascending.append(True)
    if "publishedAt" in df.columns:
        sort_cols.append("publishedAt")
        ascending.append(False)
    if sort_cols:
        df = df.sort_values(sort_cols, ascending=ascending)

    # Select and order columns
    cols = _ordered_columns(df)
    df = df[cols]

    with pd.ExcelWriter(
        output_xlsx,
        engine="xlsxwriter",
        datetime_format="yyyy-mm-dd hh:mm",
        date_format="yyyy-mm-dd",
    ) as writer:
        workbook = writer.book

        # Formats
        header_fmt = workbook.add_format(
            {"bold": True, "bg_color": "#D9D9D9", "border": 1}
        )
        text_fmt = workbook.add_format({"text_wrap": True, "valign": "top", "border": 1})
        date_fmt = workbook.add_format(
            {"num_format": "yyyy-mm-dd", "valign": "top", "border": 1}
        )
        normal_fmt = workbook.add_format({"valign": "top", "border": 1})
        pos_fmt = workbook.add_format(
            {"valign": "top", "border": 1, "font_color": "green"}
        )
        neg_fmt = workbook.add_format(
            {"valign": "top", "border": 1, "font_color": "red"}
        )

        def format_worksheet(ws, data: pd.DataFrame):
            """Apply header, column widths, conditional formats, freeze panes."""
            n_rows = len(data)

            for col_idx, col_name in enumerate(data.columns):
                # header
                ws.write(0, col_idx, col_name, header_fmt)
                # width + base format
                width = COLUMN_WIDTHS.get(col_name, 20)
                if col_name in ("title", "description"):
                    ws.set_column(col_idx, col_idx, width, text_fmt)
                elif col_name == "publishedAt":
                    ws.set_column(col_idx, col_idx, width, date_fmt)
                else:
                    ws.set_column(col_idx, col_idx, width, normal_fmt)

            # sentiment_score conditional formatting
            if "sentiment_score" in data.columns and n_rows > 0:
                score_col_idx = data.columns.get_loc("sentiment_score")
                first_data_row = 1
                last_data_row = n_rows

                # Positive: > 0.05
                ws.conditional_format(
                    first_data_row,
                    score_col_idx,
                    last_data_row,
                    score_col_idx,
                    {
                        "type": "cell",
                        "criteria": ">",
                        "value": 0.05,
                        "format": pos_fmt,
                    },
                )
                # Negative: < -0.05
                ws.conditional_format(
                    first_data_row,
                    score_col_idx,
                    last_data_row,
                    score_col_idx,
                    {
                        "type": "cell",
                        "criteria": "<",
                        "value": -0.05,
                        "format": neg_fmt,
                    },
                )

            ws.freeze_panes(1, 0)

        # ---- Summary sheet: totals + 1d/7d/30d ------------------------------
        if (
            "Ticker" in df.columns
            and "sentiment_score" in df.columns
            and "publishedAt" in df.columns
        ):
            base = (
                df.groupby("Ticker")
                .agg(
                    article_count_total=("Ticker", "size"),
                    avg_sentiment_total=("sentiment_score", "mean"),
                    positive_total=("sentiment_label", lambda s: (s == "positive").sum()),
                    neutral_total=("sentiment_label", lambda s: (s == "neutral").sum()),
                    negative_total=("sentiment_label", lambda s: (s == "negative").sum()),
                )
            )

            ref_date = df["publishedAt"].max()

            if pd.isna(ref_date):
                summary = base.reset_index()
            else:
                ref_date = pd.to_datetime(ref_date)

                def window_stats(days: int, prefix: str) -> pd.DataFrame:
                    start = ref_date - pd.Timedelta(days=days)
                    mask = df["publishedAt"] >= start
                    if not mask.any():
                        # no rows in this window
                        return (
                            pd.DataFrame(
                                columns=[
                                    "Ticker",
                                    f"article_count_{prefix}",
                                    f"avg_sentiment_{prefix}",
                                ]
                            )
                            .set_index("Ticker")
                        )
                    g = (
                        df.loc[mask]
                        .groupby("Ticker")
                        .agg(
                            **{
                                f"article_count_{prefix}": ("Ticker", "size"),
                                f"avg_sentiment_{prefix}": ("sentiment_score", "mean"),
                            }
                        )
                    )
                    return g

                w1d = window_stats(1, "1d")
                w7d = window_stats(7, "7d")
                w30d = window_stats(30, "30d")

                summary = (
                    base.join(w1d, how="left")
                    .join(w7d, how="left")
                    .join(w30d, how="left")
                    .reset_index()
                )

            # Round all avg_* columns
            for col in summary.columns:
                if col.startswith("avg_sentiment_"):
                    summary[col] = summary[col].round(3)

            # Column order: counts first, then averages, then totals breakdown
            desired_order = [
                "Ticker",
                "article_count_1d",
                "article_count_7d",
                "article_count_30d",
                "article_count_total",
                "avg_sentiment_1d",
                "avg_sentiment_7d",
                "avg_sentiment_30d",
                "avg_sentiment_total",
                "positive_total",
                "neutral_total",
                "negative_total",
            ]
            cols_in_summary = list(summary.columns)
            ordered = [c for c in desired_order if c in cols_in_summary]
            extras = [c for c in cols_in_summary if c not in ordered]
            summary = summary[ordered + extras]

            sheet_name = "Summary"
            summary.to_excel(writer, sheet_name=sheet_name, index=False)
            ws_sum = writer.sheets[sheet_name]
            format_worksheet(ws_sum, summary)

        # ---- All_News sheet --------------------------------------------------
        if include_all_sheet:
            sheet_name = "All_News"
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            ws_all = writer.sheets[sheet_name]
            format_worksheet(ws_all, df)

        # ---- One sheet per ticker -------------------------------------------
        if "Ticker" in df.columns:
            for ticker, df_ticker in df.groupby("Ticker"):
                sheet_name = str(ticker)[:31]
                df_ticker.to_excel(writer, sheet_name=sheet_name, index=False)
                ws = writer.sheets[sheet_name]
                format_worksheet(ws, df_ticker)

    print(f"✅ Exported news to Excel: {output_xlsx}")


if __name__ == "__main__":
    export_news_to_excel()
