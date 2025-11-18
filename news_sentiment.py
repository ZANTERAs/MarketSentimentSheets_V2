# news_sentiment.py

from __future__ import annotations

import numpy as np
import pandas as pd
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# Global analyzer (created once)
_SIA = SentimentIntensityAnalyzer()


def _sentiment_for_text(text: str | None) -> tuple[float | None, str | None]:
    """
    Compute VADER sentiment for a piece of text.

    Returns:
        (compound_score, label) where label in {"positive","negative","neutral"}.
        If text is empty/None, returns (None, None).
    """
    if not text or not str(text).strip():
        return None, None

    scores = _SIA.polarity_scores(str(text))
    compound = scores.get("compound", 0.0)

    if compound >= 0.05:
        label = "positive"
    elif compound <= -0.05:
        label = "negative"
    else:
        label = "neutral"

    return compound, label


def ensure_sentiment(
    df: pd.DataFrame,
    text_columns: tuple[str, ...] = ("title", "description", "content_snippet"),
    score_col: str = "sentiment_score",
    label_col: str = "sentiment_label",
) -> pd.DataFrame:
    """
    Ensure the DataFrame has sentiment columns.

    - Creates `score_col` and `label_col` if missing.
    - Computes sentiment ONLY for rows where `score_col` is NaN.
    - Text is built by concatenating `text_columns`.

    Parameters
    ----------
    df : pd.DataFrame
        News database with at least the text columns.
    text_columns : tuple[str, ...]
        Columns to concatenate for sentiment input.
    score_col : str
        Name of the numeric sentiment column.
    label_col : str
        Name of the label column.

    Returns
    -------
    pd.DataFrame
        Same df, modified in-place and returned for convenience.
    """
    if df.empty:
        return df

    # Create columns if they don't exist
    if score_col not in df.columns:
        df[score_col] = np.nan
    if label_col not in df.columns:
        df[label_col] = pd.NA

    # Which rows still need sentiment?
    mask = df[score_col].isna()

    if not mask.any():
        return df  # nothing to do

    # Slice only rows that need sentiment
    subset = df.loc[mask, list(text_columns)]

    scores: list[float | None] = []
    labels: list[str | None] = []

    for _, row in subset.iterrows():
        parts = []
        for col in text_columns:
            val = row.get(col)
            if isinstance(val, str) and val.strip():
                parts.append(val.strip())
        text = " ".join(parts)
        score, label = _sentiment_for_text(text)
        scores.append(score)
        labels.append(label)

    df.loc[mask, score_col] = scores
    df.loc[mask, label_col] = labels

    return df
