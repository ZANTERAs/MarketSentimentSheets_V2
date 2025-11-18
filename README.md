# MarketSentimentSheets-V2

> **Short project description (EN)**  
> MarketSentimentSheets-V2 is a Python-based pipeline that builds a local news database for a set of stock tickers, enriches each article with sentiment analysis, and exports the result to an Excel workbook with per-ticker sheets and summary dashboards.

> **Descripción corta del proyecto (ES)**  
> MarketSentimentSheets-V2 es un pipeline en Python que construye una base de datos local de noticias para un conjunto de tickers, añade análisis de sentimiento a cada noticia y exporta todo a un archivo de Excel con hojas por ticker y resúmenes agregados.

---

## 🇬🇧 Overview (English)

### What this project does

- Fetches news articles related to a list of **stock tickers** using **NewsAPI**.
- Uses **yfinance** to automatically build a rich query of **company aliases**  
  (e.g. `NVDA OR NVIDIA OR "NVIDIA Corporation"`).
- Stores all fetched articles in a **local CSV database** (`news_db.csv`) with:
  - Stable identifiers (`NewsID`, `ArticleKey`) to avoid duplicates.
  - Article metadata: ticker, source, title, description, URL, date, snippet.
- Runs **sentiment analysis** (VADER) on each article and adds:
  - `sentiment_score` (compound score in [-1, 1])  
  - `sentiment_label` (`positive`, `neutral`, `negative`)
- Exports everything to an **Excel file** (`news_db.xlsx`) with:
  - A **Summary** sheet (per-ticker stats over total / last 1 / 7 / 30 days).
  - An **All_News** sheet with all articles.
  - One sheet per **ticker**.
  - Conditional formatting (green/red) based on `sentiment_score`.
- Can be triggered directly from Excel via **xlwings** buttons/macros.

---

### Project structure

```text
MarketSentimentSheets-V2/
├─ main.py                 # Entry point: fetch news + update CSV DB + sentiment
├─ aliases_from_yfinance.py# Build NewsAPI query aliases using yfinance
├─ news_sentiment.py       # Sentiment analysis helpers (VADER)
├─ news_to_excel.py        # Export CSV DB to a formatted Excel workbook
├─ news_db.csv             # Incremental local news database (generated)
├─ news_db.xlsx            # Excel report (generated)
├─ .env                    # Environment variables (NewsAPI key)
└─ README.md               # This file
```

---

### Requirements

- **Python** 3.10+ (tested on 3.13)
- A **NewsAPI** account and API key (free Developer plan is enough to start)
- Recommended libraries (see `pip install` below):

```bash
pip install pandas requests python-dotenv yfinance vaderSentiment xlsxwriter
# Optional, for Excel integration:
pip install xlwings
```

---

### Configuration

1. Create a `.env` file in the project root:

   ```env
   NEWSAPI_KEY=TU_API_KEY_DE_NEWSAPI_AQUI
   ```

2. Edit the tickers you care about in `main.py`:

   ```python
   TICKERS = ["NVDA", "MSFT", "AAPL", "MELI", "GOOGL", "YPF"]
   ```

---

### How it works (pipeline)

1. **Fetch & update DB (`main.py`)**

   ```bash
   python -m main
   ```

   - For each ticker in `TICKERS`:
     - Builds a query with aliases from Yahoo Finance (`aliases_from_yfinance.py`).
     - Fetches news for the **last 30 days** in time windows (respecting NewsAPI limits).
   - Normalizes results into a DataFrame with columns such as:
     - `Ticker`, `source`, `author`, `title`, `description`, `url`,
       `publishedAt`, `content_snippet`.
   - Computes:
     - `NewsID` = hash of (`Ticker`, `url`, `publishedAt`)
     - `ArticleKey` = hash of (`Ticker`, `title`, `publishedAt`)
   - Merges with the existing `news_db.csv` (if it exists):
     - Keeps only **new** rows based on `NewsID`.
     - Deduplicates by `NewsID` and then by `ArticleKey`.
   - Runs **sentiment analysis** via `news_sentiment.ensure_sentiment`:
     - Only for rows that don’t have `sentiment_score` yet.
   - Saves the updated database to `news_db.csv`.

2. **Export to Excel (`news_to_excel.py`)**

   ```bash
   python -m news_to_excel
   ```

   - Loads `news_db.csv` and parses `publishedAt` as timezone-naive datetimes.
   - Sorts by `Ticker` and `publishedAt` (newest first).
   - Creates an Excel file `news_db.xlsx` with:
     - **Summary** sheet, per ticker:
       - `article_count_1d`, `article_count_7d`, `article_count_30d`, `article_count_total`
       - `avg_sentiment_1d`, `avg_sentiment_7d`, `avg_sentiment_30d`, `avg_sentiment_total`
       - `positive_total`, `neutral_total`, `negative_total`
       - Windows (1d/7d/30d) are calculated relative to the **latest date** in the DB.
     - **All_News** sheet with all articles.
     - One sheet per **ticker**.
   - Applies formatting:
     - Column widths and wrapped text for long fields.
     - Conditional formatting on `sentiment_score`:
       - > 0.05 → green
       - < -0.05 → red

---

### NewsAPI free-plan limitations

This project is designed to play nicely with the free **Developer** plan:

- **History:** up to **30 days** of past news.
- **Results per query:** max **100** results.
- **Rate limit:** max **100 requests / 24h** (50 per 12h window).

The code therefore:

- Restricts fetching to `days=30`.
- Uses **1 page** per interval with `pageSize=100`.
- Splits the 30 days into windows (`step_days`) to spread requests.
- Handles `429 rateLimited` errors gracefully:
  - Stops fetching new tickers when rate limit is hit.
  - Still works with the existing `news_db.csv` (e.g. sentiment / Excel export).

---

### Excel integration (optional, via xlwings)

You can trigger the Python pipeline directly from Excel using **buttons** and **VBA macros** with xlwings.

Example macros:

```vba
Sub RunNewsUpdate()
    ' Calls main.main() via xlwings
    RunPython ""import main; main.main()""
End Sub

Sub ExportNewsToExcel()
    ' Calls news_to_excel.export_news_to_excel() via xlwings
    RunPython ""import news_to_excel; news_to_excel.export_news_to_excel()""
End Sub
```

Typical setup:

- Place your Excel workbook (e.g. `MarketSentimentSheets-V2.xlsm`) in the same folder as `main.py`.
- Install xlwings add-in:
  - `xlwings addin install`
- Create two buttons in Excel and assign the macros:
  - **Actualizar noticias** → `RunNewsUpdate`
  - **Generar Excel de noticias** → `ExportNewsToExcel`

---

### Technologies used

- **Python** (3.10+)
- **NewsAPI** – news provider
- **yfinance** – company metadata / aliases from Yahoo! Finance
- **pandas** – data manipulation and IO
- **requests** – HTTP calls to NewsAPI
- **python-dotenv** – `.env` management
- **vaderSentiment** – sentiment analysis
- **xlsxwriter** – Excel export and formatting
- **xlwings** (optional) – Excel ↔ Python integration

---

## 🇪🇸 Descripción general (Español)

### ¿Qué hace este proyecto?

- Descarga noticias relacionadas con una lista de **tickers bursátiles** usando **NewsAPI**.
- Usa **yfinance** para armar automáticamente una consulta con **alias de la empresa**  
  (por ejemplo: `NVDA OR NVIDIA OR "NVIDIA Corporation"`).
- Guarda todas las noticias en una **base de datos local CSV** (`news_db.csv`) con:
  - Identificadores estables (`NewsID`, `ArticleKey`) para evitar duplicados.
  - Metadatos de cada noticia: ticker, fuente, título, descripción, URL, fecha, snippet.
- Ejecuta **análisis de sentimiento** (VADER) sobre cada noticia y añade:
  - `sentiment_score` (score compuesto en [-1, 1])  
  - `sentiment_label` (`positive`, `neutral`, `negative`)
- Exporta todo a un archivo de **Excel** (`news_db.xlsx`) con:
  - Una hoja **Summary** (estadísticas por ticker en total / últimos 1 / 7 / 30 días).
  - Una hoja **All_News** con todas las noticias.
  - Una hoja por **ticker**.
  - Formato condicional (verde/rojo) según `sentiment_score`.
- Puede ejecutarse directamente desde Excel mediante botones y macros con **xlwings**.

---

### Flujo de trabajo

1. **Actualizar la base de noticias**

   ```bash
   python -m main
   ```

   - Descarga noticias de los últimos 30 días para cada ticker en `TICKERS`.
   - Usa `aliases_from_yfinance.py` para armar una buena consulta para NewsAPI.
   - Unifica los resultados, genera IDs únicos (`NewsID`, `ArticleKey`) y:
     - Agrega solo noticias nuevas a `news_db.csv`.
     - Elimina duplicados exactos y duplicados “casi iguales” (misma noticia en otros sitios).
   - Calcula el sentimiento de las noticias nuevas con `news_sentiment.py`.

2. **Generar el Excel de reportes**

   ```bash
   python -m news_to_excel
   ```

   - Lee `news_db.csv` y prepara un Excel `news_db.xlsx` con:
     - **Summary**: conteo y sentimiento medio por ticker (total, 1D, 7D, 30D).
     - **All_News**: todas las noticias.
     - Una hoja por ticker.
   - Aplica anchos de columna, texto envuelto, fechas, colores verde/rojo en `sentiment_score`.

---

### Limitaciones del plan gratuito de NewsAPI

Este proyecto está configurado para respetar el plan **Developer** gratuito:

- Hasta **30 días** de historia.
- Máximo **100 resultados por consulta**.
- Máximo **100 requests por 24 horas** (50 por ventana de 12 horas).

El código:

- Limita las consultas a `days=30`.
- Usa **1 página** por intervalo con `pageSize=100`.
- Divide el rango de 30 días en bloques (`step_days`) para controlar las llamadas.
- Maneja el error `429 rateLimited` sin romper la ejecución.

---

### Integración con Excel (xlwings, opcional)

Ejemplo de macros en VBA:

```vba
Sub RunNewsUpdate()
    ' Llama a main.main() desde Excel usando xlwings
    RunPython ""import main; main.main()""
End Sub

Sub ExportNewsToExcel()
    ' Llama a news_to_excel.export_news_to_excel()
    RunPython ""import news_to_excel; news_to_excel.export_news_to_excel()""
End Sub
```

Botones típicos en Excel:

- **Actualizar noticias** → descarga y actualiza `news_db.csv`.
- **Generar Excel de noticias** → genera/actualiza `news_db.xlsx`.

---
