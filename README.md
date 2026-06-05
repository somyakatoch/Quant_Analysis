# IB Futures Event Study Dashboard

This Streamlit dashboard analyzes Australian IB futures around major fixed-income events:

- SVB Collapse
- Yen Carry Unwind
- Liberation Day

## Features

- Upload Excel workbook
- Choose event window
- Plot outright futures prices
- Convert prices into implied rates
- Analyze volume
- Analyze curve spreads
- Calculate rolling z-scores
- Summarize event impact in basis points and equivalent 25 bp moves

## Required Excel Format

The workbook should contain sheets named:

- `YIBc1` or `YIBc1.`
- `YIBc2` or `YIBc2.`
- `YIBc3` or `YIBc3.`
- `YIBc4` or `YIBc4.`

Each sheet should contain:

- DateTime column: `DateTime (AET)` or `AUS_Local_DateTime`
- `Last`
- `Volume`

## Run Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Cloud

1. Push this folder to GitHub.
2. Go to Streamlit Cloud.
3. Click **New app**.
4. Select your GitHub repository.
5. Set main file path as:

```text
app.py
```

6. Deploy.

## Suggested Files

Use:
- 2023 workbook for SVB
- 2024–2026 workbook for Yen Carry and Liberation Day
