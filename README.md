# dinpp-mel-dashboard

# 🌿 DINPP (Darwin Extra) — Live Smap MEL & Donor Dashboard

An interactive Monitoring, Evaluation, and Learning (MEL) web dashboard built with **Python** and **Streamlit**, connected directly to the **Smap Server REST API** (`https://sg.smap.com.au`).

It eliminates the need to manually download and merge Excel exports for routine monitoring across the five DINPP survey forms, providing real-time visibility for project teams, supervisors, and donors.

---

## ✨ Key Features

- **🏠 At a Glance (Donor Snapshot):**
  - Global filters by **Time Window** and **District**
  - Executive KPI cards (Total submissions, 7-day trend, Districts reached, Wards covered, Latest upload in `Asia/Kathmandu` time)
  - Copy-ready **Donor Update Brief**
  - **District-wise** and **Ward-level** breakdowns across all forms (stacked bar charts, District × Form matrix, and interactive District → Ward → Form Sunburst/Treemap)
  - Cumulative submission timeline & unified **OpenStreetMap GPS map**
  - One-click **CSV** and multi-sheet **Excel (`.xlsx`) Donor Pack** export
- **🔗 Cross-Form Linkage:** Compare any two forms using a shared ID or location column (e.g., Site ID, Farmer ID, Ward) to identify matched records and pending follow-ups.
- **🛡️ Data Quality (QA) & Field Team Monitoring:** Enumerator activity leaderboard, GPS capture rate, interview duration outlier detection, duplicate checks, and column missingness audit.
- **🔍 Single Form Deep-Dive:** Interactive frequency tables, numeric summaries, record filtering, and 2-variable cross-tabulation with downloadable outputs.

---

## 🔐 Security & Data Privacy

- **No survey data, credentials, or API keys are stored** in this repository.
- Users authenticate directly with their own **Smap username/password** or **Smap API Key** during each session.
- Data visibility strictly follows the user’s existing Smap project permissions (requires `Analyst` or `View Data` security role in Smap).

---

## 📁 Repository Structure

```text
├── app.py                 # Main Streamlit dashboard application
├── requirements.txt       # Python dependencies for Streamlit Cloud
├── .streamlit/
│   └── config.toml        # Custom MEL forest-teal UI theme
└── README.md              # Project documentation
```

---

## 💻 Running Locally

1. Install required packages:
   ```bash
   python -m pip install -r requirements.txt
   ```
2. Launch the dashboard:
   ```bash
   python -m streamlit run app.py
   ```
3. Open the local URL shown in the terminal (typically `http://localhost:8501`) and log in with your Smap credentials.
