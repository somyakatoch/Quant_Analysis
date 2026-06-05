# IB Futures Event Study Dashboard

A professional Streamlit dashboard for analyzing Australian 30-Day Interbank Cash Rate Futures around major fixed-income events.

## Events Included

- SVB Collapse
- Yen Carry Unwind
- Liberation Day

## Dashboard Sections

1. Outright futures prices  
2. Market-implied future rates  
3. Volume and participation  
4. Curve spreads  
5. Rolling z-scores  
6. Summary tables  
7. Interpretation guide  

## Core Formula

IB futures price:

```text
Price = 100 - implied expected cash rate
```

So:

```text
Delta r = -Delta Price
```

## Expected Excel Format

The workbook should include sheets named:

```text
YIBc1 or YIBc1.
YIBc2 or YIBc2.
YIBc3 or YIBc3.
YIBc4 or YIBc4.
```

Required columns:

```text
DateTime (AET) or AUS_Local_DateTime
Last
Volume
```

## Run Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Cloud

1. Create a GitHub repository.
2. Upload these files:
   - app.py
   - requirements.txt
   - README.md
   - .gitignore
3. Open Streamlit Cloud.
4. Click **New app**.
5. Select the GitHub repository.
6. Set main file path:

```text
app.py
```

7. Click Deploy.

## Recommended Workflow

- Use the 2023 workbook for SVB.
- Use the 2024–2026 workbook for Yen Carry and Liberation Day.
- Compare:
  - price changes
  - implied-rate changes
  - equivalent 25 bp moves priced
  - volume
  - spread compression
  - rolling z-scores
