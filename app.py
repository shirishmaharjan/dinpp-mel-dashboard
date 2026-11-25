import importlib.util
import io
import re
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

SMAP_SERVER = "https://sg.smap.com.au"
NEPAL_TZ = "Asia/Kathmandu"

# Professional MEL Color Palette (Forest Teal, Royal Blue, Amber, Emerald, Slate, Plum)
MEL_PALETTE = [
    "#0F766E",
    "#1D4ED8",
    "#D97706",
    "#059669",
    "#7C3AED",
    "#BE123C",
    "#0284C7",
    "#475569",
]

st.set_page_config(
    page_title="DINPP | Live MEL & Donor Dashboard",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==============================================================================
# PROFESSIONAL EXECUTIVE STYLING
# ==============================================================================
st.markdown(
    """
    <style>
        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 2rem;
        }
        div[data-testid="stMetric"] {
            background-color: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-left: 4px solid #0F766E;
            padding: 14px 16px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
        }
        div[data-testid="stMetric"] label {
            color: #475569 !important;
            font-weight: 600 !important;
            font-size: 0.85rem !important;
        }
        div[data-testid="stMetricValue"] {
            color: #0F172A !important;
            font-weight: 700 !important;
        }
        .section-header {
            font-size: 1.15rem;
            font-weight: 700;
            color: #0F172A;
            margin-top: 1rem;
            margin-bottom: 0.4rem;
            padding-bottom: 0.3rem;
            border-bottom: 2px solid #E2E8F0;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
        }
        .stTabs [data-baseweb="tab"] {
            padding: 8px 16px;
            font-weight: 600;
            border-radius: 6px 6px 0 0;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# Header Banner
st.markdown(
    """
    <div style="background: linear-gradient(90deg, #0F766E 0%, #115E59 60%, #1E293B 100%);
                padding: 18px 24px; border-radius: 10px; color: white; margin-bottom: 18px;">
        <h2 style="margin: 0; color: white; font-size: 1.65rem;">🌿 DINPP Live MEL & Donor Dashboard</h2>
        <p style="margin: 4px 0 0 0; color: #CCFBF1; font-size: 0.92rem;">
            Real-time multi-form overview, District & Ward coverage, cross-form linkage, and data quality monitoring (Smap Live API)
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ==============================================================================
# 1. AUTHENTICATION & SMAP API HELPERS
# ==============================================================================
with st.sidebar:
    st.header("🔐 Smap Login")
    auth_mode = st.radio("Login method", ["Username & Password", "API Key"])
    if auth_mode == "Username & Password":
        username = st.text_input("Smap Username")
        password = st.text_input("Smap Password", type="password")
        api_key = None
    else:
        api_key = st.text_input("Smap API Key", type="password")
        username = password = None

    refresh_btn = st.button("🔄 Refresh Live Data", use_container_width=True)

if not ((username and password) or api_key):
    st.info("Enter your Smap credentials in the sidebar to load your live MEL dashboard.")
    st.stop()


def smap_get(path):
    url = f"{SMAP_SERVER}{path}"
    if api_key:
        r = requests.get(url, headers={"x-api-key": api_key}, timeout=45)
    else:
        r = requests.get(url, auth=(username, password), timeout=45)
    r.raise_for_status()
    return r


@st.cache_data(ttl=300, show_spinner="Connecting to Smap & fetching form list...")
def get_forms(user_token_key):
    prefix = "/api/v2" if api_key else "/api/v1"
    return smap_get(f"{prefix}/data").json()


@st.cache_data(ttl=300, show_spinner="Loading survey records from Smap...")
def get_survey_data(id_string, subform=None, user_token_key=""):
    prefix = "/api/v2" if api_key else "/api/v1"
    params = ["meta=yes", f"tz={NEPAL_TZ}"]
    if subform:
        params.append(f"form={subform}")
    query = "?" + "&".join(params)

    try:
        r = smap_get(f"{prefix}/data.csv/{id_string}{query}")
        if not r.text.strip():
            return pd.DataFrame()
        return pd.read_csv(io.StringIO(r.text))
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code in (403, 404):
            r_json = smap_get(f"{prefix}/data/{id_string}{query}")
            data = r_json.json()
            return pd.json_normalize(data) if data else pd.DataFrame()
        raise


if refresh_btn:
    st.cache_data.clear()

auth_cache_key = api_key or f"{username}:{len(password)}"

try:
    forms = get_forms(auth_cache_key)
except requests.HTTPError as e:
    code = e.response.status_code if e.response is not None else "Error"
    st.error(f"Login or API failed ({code}). Please verify your Smap credentials.")
    st.stop()

if not forms:
    st.warning("No forms found for this Smap account.")
    st.stop()

with st.sidebar:
    st.divider()
    st.header("🗂️ Project Filter")
    filter_text = st.text_input("Filter forms by name", value="", placeholder="e.g. DINPP")
    filtered_forms = [f for f in forms if filter_text.lower() in f["title"].lower()]

    if not filtered_forms:
        st.warning("No forms match that filter.")
        st.stop()

    selected_titles = st.multiselect(
        "Active forms in dashboard",
        options=[f["title"] for f in filtered_forms],
        default=[f["title"] for f in filtered_forms],
    )
    active_forms = [f for f in filtered_forms if f["title"] in selected_titles]

if not active_forms:
    st.warning("Select at least one form in the sidebar.")
    st.stop()


# ==============================================================================
# 2. METADATA, GEOGRAPHY & CHART HELPERS
# ==============================================================================
def find_col(df, candidates, exact_only=False):
    lower_map = {c.lower().strip(): c for c in df.columns}
    for cand in candidates:
        if cand in lower_map:
            return lower_map[cand]
    if not exact_only:
        for cand in candidates:
            for lc, orig in lower_map.items():
                if cand in lc:
                    return orig
    return None


def parse_dt_series(series):
    dt = pd.to_datetime(series, errors="coerce")
    if hasattr(dt.dt, "tz") and dt.dt.tz is not None:
        dt = dt.dt.tz_convert(NEPAL_TZ).dt.tz_localize(None)
    return dt


def get_submission_time_series(df):
    col = find_col(df, ["_upload_time", "upload_time", "upload time", "_submission_time", "end", "_end", "start", "_start"])
    if not col or df.empty:
        return pd.Series(pd.NaT, index=df.index), None
    return parse_dt_series(df[col]), col


def get_enumerator_series(df):
    col = find_col(df, ["_user", "user", "username", "enumerator", "interviewer", "collected_by"])
    if not col or df.empty:
        return pd.Series("Unknown", index=df.index), None
    return df[col].fillna("Unknown").astype(str), col


def get_duration_minutes(df):
    start_col = find_col(df, ["_start", "start", "starttime", "start_time"])
    end_col = find_col(df, ["_end", "end", "endtime", "end_time"])
    if not start_col or not end_col or df.empty:
        return None
    s = parse_dt_series(df[start_col])
    e = parse_dt_series(df[end_col])
    return (e - s).dt.total_seconds() / 60.0


def clean_district_value(val):
    if pd.isna(val):
        return None
    s = str(val).strip()
    if not s or s.lower() in {"nan", "none", "null", "na", "n/a"}:
        return None
    s = s.replace("_", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s.title()


def clean_ward_value(val):
    if pd.isna(val):
        return None
    s = str(val).strip()
    if not s or s.lower() in {"nan", "none", "null", "na", "n/a"}:
        return None
    # Match numeric ward or "Ward 1" / "ward_02" / "1.0"
    m = re.match(r"^(?:ward\s*[-_#:]?\s*)?0*(\d+)(?:\.0+)?$", s, flags=re.IGNORECASE)
    if m:
        return f"Ward {int(m.group(1))}"
    return s.replace("_", " ").strip().title()


def ward_sort_key(ward_label):
    m = re.search(r"(\d+)", str(ward_label))
    return (0, int(m.group(1)), str(ward_label)) if m else (1, 9999, str(ward_label))


def extract_gps(df):
    if df.empty:
        return pd.DataFrame(columns=["lat", "lon"])

    lat_col = find_col(df, ["lat", "latitude", "_latitude", "gps_lat"])
    lon_col = find_col(df, ["lon", "lng", "long", "longitude", "_longitude", "gps_lon"])

    if lat_col and lon_col and lat_col != lon_col:
        lat = pd.to_numeric(df[lat_col], errors="coerce")
        lon = pd.to_numeric(df[lon_col], errors="coerce")
        valid = lat.between(-90, 90) & lon.between(-180, 180) & ~((lat == 0) & (lon == 0))
        out = pd.DataFrame({"lat": lat[valid], "lon": lon[valid]}, index=df.index[valid])
        if not out.empty:
            return out

    geopoint_re = re.compile(r"^\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)(?:\s+-?\d+(?:\.\d+)?){0,2}\s*$")
    wkt_re = re.compile(r"POINT\s*\(\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*\)", re.IGNORECASE)

    for col in df.select_dtypes(include="object").columns:
        sample = df[col].dropna().astype(str).head(20)
        if sample.empty:
            continue
        if sample.str.match(geopoint_re).any():
            extracted = df[col].astype(str).str.extract(geopoint_re)
            lat = pd.to_numeric(extracted[0], errors="coerce")
            lon = pd.to_numeric(extracted[1], errors="coerce")
            valid = lat.between(-90, 90) & lon.between(-180, 180) & ~((lat == 0) & (lon == 0))
            if valid.any():
                return pd.DataFrame({"lat": lat[valid], "lon": lon[valid]}, index=df.index[valid])
        if sample.str.contains(wkt_re).any():
            extracted = df[col].astype(str).str.extract(wkt_re)
            lon = pd.to_numeric(extracted[0], errors="coerce")
            lat = pd.to_numeric(extracted[1], errors="coerce")
            valid = lat.between(-90, 90) & lon.between(-180, 180) & ~((lat == 0) & (lon == 0))
            if valid.any():
                return pd.DataFrame({"lat": lat[valid], "lon": lon[valid]}, index=df.index[valid])

    return pd.DataFrame(columns=["lat", "lon"])


def style_fig(fig, height=400):
    fig.update_layout(
        template="plotly_white",
        height=height,
        font=dict(family="Segoe UI, Roboto, sans-serif", size=12, color="#1E293B"),
        title_font=dict(size=15, color="#0F172A"),
        margin=dict(l=12, r=12, t=48, b=16),
        hoverlabel=dict(bgcolor="white", font_size=12),
    )
    return fig


def plot_osm_map(geo_df, color_col, hover_cols, title):
    if hasattr(px, "scatter_map"):
        fig = px.scatter_map(
            geo_df,
            lat="lat",
            lon="lon",
            color=color_col,
            color_discrete_sequence=MEL_PALETTE,
            hover_data=hover_cols,
            zoom=6,
            title=title,
            map_style="open-street-map",
        )
    else:
        fig = px.scatter_mapbox(
            geo_df,
            lat="lat",
            lon="lon",
            color=color_col,
            color_discrete_sequence=MEL_PALETTE,
            hover_data=hover_cols,
            zoom=6,
            title=title,
            mapbox_style="open-street-map",
        )
    fig = style_fig(fig, height=430)
    fig.update_layout(margin=dict(l=0, r=0, t=42, b=0))
    return fig


# ==============================================================================
# 3. LOAD ALL ACTIVE FORMS ONCE & AUTO-DETECT DISTRICT / WARD COLUMNS
# ==============================================================================
datasets = {}
load_errors = {}

for f in active_forms:
    try:
        datasets[f["title"]] = get_survey_data(f["id_string"], user_token_key=auth_cache_key)
    except requests.HTTPError as ex:
        status = ex.response.status_code if ex.response is not None else "HTTP Error"
        load_errors[f["title"]] = f"Access denied ({status}) — check 'Analyst' or 'View Data' role in Smap."
    except Exception as ex:
        load_errors[f["title"]] = str(ex)

if load_errors:
    with st.expander(f"⚠️ Could not load {len(load_errors)} form(s)"):
        for fname, err in load_errors.items():
            st.write(f"**{fname}:** {err}")

if not datasets:
    st.error("None of the selected forms could be loaded.")
    st.stop()

# Sidebar: District & Ward Column Mapping (Auto-detected with manual override)
geo_col_map = {}
with st.sidebar:
    with st.expander("📍 District & Ward Columns", expanded=False):
        st.caption("Auto-detected per form. Adjust if a form uses a custom column name.")
        for title, df_tmp in datasets.items():
            if df_tmp.empty:
                geo_col_map[title] = {"district": None, "ward": None}
                continue

            cols = ["(None)"] + list(df_tmp.columns)
            auto_dist = find_col(df_tmp, ["district", "dist", "district_name", "jilla"])
            auto_ward = find_col(df_tmp, ["ward", "ward_no", "ward_number", "ward_num", "wada"])

            st.markdown(f"**{title}**")
            d_idx = cols.index(auto_dist) if auto_dist in cols else 0
            w_idx = cols.index(auto_ward) if auto_ward in cols else 0

            sel_d = st.selectbox("District column", cols, index=d_idx, key=f"dist_col_{title}")
            sel_w = st.selectbox("Ward column", cols, index=w_idx, key=f"ward_col_{title}")
            geo_col_map[title] = {
                "district": None if sel_d == "(None)" else sel_d,
                "ward": None if sel_w == "(None)" else sel_w,
            }


# ==============================================================================
# 4. DASHBOARD TABS
# ==============================================================================
tab_glance, tab_link, tab_qa, tab_deep = st.tabs([
    "🏠 At a Glance (Donor Snapshot)",
    "🔗 Cross-Form Linkage",
    "🛡️ Data Quality & Field Team",
    "🔍 Single Form Deep-Dive",
])


# ------------------------------------------------------------------------------
# TAB 1: AT A GLANCE (DONOR & MEL SNAPSHOT)
# ------------------------------------------------------------------------------
with tab_glance:
    now_npt = pd.Timestamp.now(tz=NEPAL_TZ).tz_localize(None)

    # Collect all available cleaned districts for the global district filter
    all_districts_found = set()
    for title, df_raw in datasets.items():
        d_col = geo_col_map[title]["district"]
        if d_col and not df_raw.empty:
            cleaned = df_raw[d_col].map(clean_district_value).dropna().unique()
            all_districts_found.update(cleaned)
    all_districts_sorted = sorted(all_districts_found)

    # Top Global Filter Bar
    gf1, gf2, gf3 = st.columns([1.3, 1.5, 1.5])
    with gf1:
        date_preset = st.selectbox(
            "📅 Time Window",
            ["All Time", "Last 7 Days", "Last 30 Days", "Last 90 Days", "Custom Range"],
        )
    custom_start, custom_end = None, None
    if date_preset == "Custom Range":
        with gf2:
            d_range = st.date_input(
                "Select date range",
                value=(now_npt.date() - pd.Timedelta(days=30), now_npt.date()),
            )
            if isinstance(d_range, tuple) and len(d_range) == 2:
                custom_start = pd.Timestamp(d_range[0])
                custom_end = pd.Timestamp(d_range[1]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        dist_filter_col = gf3
    else:
        dist_filter_col = gf2

    with dist_filter_col:
        selected_districts = st.multiselect(
            "📍 Filter by District (All by default)",
            options=all_districts_sorted,
            default=[],
            placeholder="All Districts",
        )

    cutoff_7d = now_npt - pd.Timedelta(days=7)
    cutoff_14d = now_npt - pd.Timedelta(days=14)
    cutoff_30d = now_npt - pd.Timedelta(days=30)

    timeline_frames = []
    gps_frames = []
    geo_records = []
    summary_rows = []
    all_active_users = set()
    filtered_districts_set = set()
    filtered_wards_set = set()
    latest_overall = None
    total_all_time = 0
    total_last_7d = 0
    total_prev_7d = 0

    for title, df_raw in datasets.items():
        if df_raw.empty:
            summary_rows.append({
                "Form Name": title,
                "Records (Filtered)": 0,
                "All-Time Total": 0,
                "Last 7 Days": 0,
                "Districts": 0,
                "Wards": 0,
                "Active Enumerators": 0,
                "With GPS (%)": "0%",
                "Latest Submission (NPT)": "No data",
            })
            continue

        dt_series, _ = get_submission_time_series(df_raw)
        user_series, _ = get_enumerator_series(df_raw)
        gps_df_raw = extract_gps(df_raw)

        d_col = geo_col_map[title]["district"]
        w_col = geo_col_map[title]["ward"]
        dist_series = df_raw[d_col].map(clean_district_value) if d_col else pd.Series(None, index=df_raw.index, dtype="object")
        ward_series = df_raw[w_col].map(clean_ward_value) if w_col else pd.Series(None, index=df_raw.index, dtype="object")

        # Apply Time + District Global Filter
        mask = pd.Series(True, index=df_raw.index)
        if date_preset == "Last 7 Days":
            mask &= dt_series >= cutoff_7d
        elif date_preset == "Last 30 Days":
            mask &= dt_series >= cutoff_30d
        elif date_preset == "Last 90 Days":
            mask &= dt_series >= (now_npt - pd.Timedelta(days=90))
        elif date_preset == "Custom Range" and custom_start is not None:
            mask &= (dt_series >= custom_start) & (dt_series <= custom_end)

        if selected_districts:
            mask &= dist_series.isin(selected_districts)

        df_filt = df_raw[mask].copy()
        dt_filt = dt_series[mask]
        user_filt = user_series[mask]
        dist_filt = dist_series[mask]
        ward_filt = ward_series[mask]

        # Counts
        valid_dt = dt_series.dropna()
        cnt_7d = int((valid_dt >= cutoff_7d).sum())
        cnt_prev_7d = int(((valid_dt >= cutoff_14d) & (valid_dt < cutoff_7d)).sum())

        total_all_time += len(df_raw)
        total_last_7d += cnt_7d
        total_prev_7d += cnt_prev_7d

        form_latest = dt_filt.dropna().max() if not dt_filt.dropna().empty else pd.NaT
        if pd.notna(form_latest):
            if latest_overall is None or form_latest > latest_overall:
                latest_overall = form_latest

        users_clean = set(user_filt[user_filt != "Unknown"].unique())
        all_active_users.update(users_clean)

        form_dists = set(dist_filt.dropna().unique())
        form_wards_pairs = set(
            zip(dist_filt.fillna("Unspecified"), ward_filt.dropna())
        )
        filtered_districts_set.update(form_dists)
        filtered_wards_set.update(form_wards_pairs)

        # Save District + Ward records for multi-form charts
        if not df_filt.empty:
            geo_records.append(
                pd.DataFrame({
                    "Form": title,
                    "District": dist_filt.fillna("Unspecified"),
                    "Ward": ward_filt.fillna("Unspecified"),
                })
            )

        gps_in_filt = gps_df_raw.loc[gps_df_raw.index.intersection(df_filt.index)].copy()
        gps_pct = (len(gps_in_filt) / len(df_filt) * 100) if len(df_filt) > 0 else 0.0

        if not gps_in_filt.empty:
            gps_in_filt["Form"] = title
            gps_in_filt["District"] = dist_filt.loc[gps_in_filt.index].fillna("N/A").values
            gps_in_filt["Ward"] = ward_filt.loc[gps_in_filt.index].fillna("N/A").values
            gps_in_filt["Enumerator"] = user_filt.loc[gps_in_filt.index].values
            gps_in_filt["Submitted"] = dt_filt.loc[gps_in_filt.index].dt.strftime("%Y-%m-%d %H:%M").fillna("N/A").values
            gps_frames.append(gps_in_filt)

        if not dt_filt.dropna().empty:
            timeline_frames.append(pd.DataFrame({"Date": dt_filt.dropna().dt.floor("D"), "Form": title}))

        summary_rows.append({
            "Form Name": title,
            "Records (Filtered)": len(df_filt),
            "All-Time Total": len(df_raw),
            "Last 7 Days": cnt_7d,
            "Districts": len(form_dists),
            "Wards": len(form_wards_pairs),
            "Active Enumerators": len(users_clean),
            "With GPS (%)": f"{gps_pct:.0f}%",
            "Latest Submission (NPT)": form_latest.strftime("%Y-%m-%d %H:%M") if pd.notna(form_latest) else "N/A",
        })

    summary_df = pd.DataFrame(summary_rows)
    filtered_total = int(summary_df["Records (Filtered)"].sum())

    # 5 Executive KPI Cards
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric(
        f"Submissions ({date_preset})",
        f"{filtered_total:,}",
        delta=f"{total_all_time:,} all-time" if (date_preset != "All Time" or selected_districts) else None,
    )
    delta_7d = total_last_7d - total_prev_7d
    k2.metric("Last 7 Days (All Forms)", f"{total_last_7d:,}", delta=f"{delta_7d:+d} vs prior 7d")
    k3.metric("Districts Reached", len(filtered_districts_set))
    k4.metric("Wards Covered", len(filtered_wards_set))
    k5.metric(
        "Latest Data Received",
        latest_overall.strftime("%d %b %Y") if latest_overall is not None else "N/A",
        delta=f"{len(all_active_users)} active enumerators",
        delta_color="off",
    )

    # Copy-Ready Donor Brief
    latest_str = latest_overall.strftime("%d %b %Y, %H:%M NPT") if latest_overall is not None else "N/A"
    top_form_row = summary_df.sort_values("Records (Filtered)", ascending=False).iloc[0]
    dist_phrase = (
        f"across {len(filtered_districts_set)} district(s) and {len(filtered_wards_set)} ward(s)"
        if filtered_districts_set
        else f"across {len(datasets)} active forms"
    )
    brief_text = (
        f"DINPP Live Survey Update ({now_npt.strftime('%d %b %Y')}): "
        f"A total of {filtered_total:,} submissions have been recorded {dist_phrase} "
        f"({total_last_7d:,} new records in the last 7 days) by {len(all_active_users)} active field enumerator(s). "
        f"Highest volume is in '{top_form_row['Form Name']}' ({int(top_form_row['Records (Filtered)']):,} records). "
        f"Most recent submission received: {latest_str}."
    )
    with st.expander("📝 Copy-Ready Donor Update Brief", expanded=True):
        st.text_area("Copy and paste into email / Slack / Teams:", value=brief_text, height=78, label_visibility="collapsed")

    # --------------------------------------------------------------------------
    # SECTION A: DISTRICT & WARD COVERAGE ACROSS ALL FORMS (SUPERVISOR REQUEST)
    # --------------------------------------------------------------------------
    st.markdown('<div class="section-header">📍 Geographic Coverage: District & Ward Breakdown (All Forms)</div>', unsafe_allow_html=True)

    geo_all_df = pd.concat(geo_records, ignore_index=True) if geo_records else pd.DataFrame()
    geo_valid_dist = geo_all_df[geo_all_df["District"] != "Unspecified"] if not geo_all_df.empty else pd.DataFrame()

    district_matrix = pd.DataFrame()
    ward_summary_df = pd.DataFrame()

    if geo_valid_dist.empty:
        st.info(
            "No District values detected yet. Open **📍 District & Ward Columns** in the sidebar to map "
            "each form's District and Ward column names."
        )
    else:
        # Row 1: District-Wise Stacked Bar + Interactive Hierarchy (Sunburst / Treemap)
        dr1, dr2 = st.columns([1.25, 1])

        with dr1:
            dist_form_counts = geo_valid_dist.groupby(["District", "Form"]).size().reset_index(name="Submissions")
            dist_totals = (
                dist_form_counts.groupby("District")["Submissions"]
                .sum()
                .sort_values(ascending=True)
            )
            fig_dist = px.bar(
                dist_form_counts,
                x="Submissions",
                y="District",
                color="Form",
                orientation="h",
                color_discrete_sequence=MEL_PALETTE,
                category_orders={"District": dist_totals.index.tolist()},
                title="District-Wise Submissions Across All Forms",
            )
            # Add total annotations at the end of stacked bars
            for dist_name, tot_val in dist_totals.items():
                fig_dist.add_annotation(
                    x=tot_val,
                    y=dist_name,
                    text=f" <b>{tot_val:,}</b>",
                    showarrow=False,
                    xanchor="left",
                    font=dict(size=11, color="#0F172A"),
                )
            fig_dist = style_fig(fig_dist, height=430)
            fig_dist.update_layout(
                legend=dict(orientation="h", y=-0.22, title=None),
                xaxis=dict(range=[0, dist_totals.max() * 1.14]),
            )
            st.plotly_chart(fig_dist, use_container_width=True)

        with dr2:
            hier_df = geo_valid_dist.copy()
            hier_df["Ward"] = hier_df["Ward"].replace("Unspecified", "Ward N/A")
            hier_counts = hier_df.groupby(["District", "Ward", "Form"]).size().reset_index(name="Submissions")

            hier_mode = st.radio(
                "Geographic Hierarchy View",
                ["Sunburst (Click to Drill Down)", "Treemap"],
                horizontal=True,
                label_visibility="collapsed",
            )
            if hier_mode.startswith("Sunburst"):
                fig_hier = px.sunburst(
                    hier_counts,
                    path=["District", "Ward", "Form"],
                    values="Submissions",
                    color="District",
                    color_discrete_sequence=MEL_PALETTE,
                    title="Interactive Drill-Down: District → Ward → Form",
                )
            else:
                fig_hier = px.treemap(
                    hier_counts,
                    path=["District", "Ward", "Form"],
                    values="Submissions",
                    color="District",
                    color_discrete_sequence=MEL_PALETTE,
                    title="Proportional Coverage: District → Ward → Form",
                )
            fig_hier = style_fig(fig_hier, height=390)
            st.plotly_chart(fig_hier, use_container_width=True)

        # Row 2: Ward-Level Bar Chart + District × Form Matrix Table
        wr1, wr2 = st.columns([1.25, 1])

        ward_valid = geo_valid_dist[geo_valid_dist["Ward"] != "Unspecified"].copy()
        with wr1:
            if ward_valid.empty:
                st.info("No Ward values detected. Map each form's Ward column in the sidebar (**📍 District & Ward Columns**).")
            else:
                ward_dist_opts = ["All Districts"] + sorted(ward_valid["District"].unique().tolist())
                focus_dist = st.selectbox("🏘️ Focus Ward Breakdown on District:", ward_dist_opts)

                w_plot_src = ward_valid if focus_dist == "All Districts" else ward_valid[ward_valid["District"] == focus_dist]
                if focus_dist == "All Districts":
                    w_plot_src = w_plot_src.copy()
                    w_plot_src["Ward_Label"] = w_plot_src["District"] + " — " + w_plot_src["Ward"]
                    ward_counts = w_plot_src.groupby(["District", "Ward", "Ward_Label", "Form"]).size().reset_index(name="Submissions")
                    # Sort cleanly by District then numeric Ward
                    ward_order = (
                        ward_counts[["District", "Ward", "Ward_Label"]]
                        .drop_duplicates()
                        .sort_values(by=["District", "Ward"], key=lambda s: s.map(ward_sort_key) if s.name == "Ward" else s)
                    )["Ward_Label"].tolist()
                    x_col = "Ward_Label"
                else:
                    ward_counts = w_plot_src.groupby(["Ward", "Form"]).size().reset_index(name="Submissions")
                    ward_order = sorted(ward_counts["Ward"].unique(), key=ward_sort_key)
                    x_col = "Ward"

                fig_ward = px.bar(
                    ward_counts,
                    x=x_col,
                    y="Submissions",
                    color="Form",
                    color_discrete_sequence=MEL_PALETTE,
                    category_orders={x_col: ward_order},
                    title=f"Ward-Level Submissions ({focus_dist})",
                )
                # Total labels above stacked ward bars
                w_tots = ward_counts.groupby(x_col)["Submissions"].sum()
                for w_lbl, w_tot in w_tots.items():
                    fig_ward.add_annotation(
                        x=w_lbl,
                        y=w_tot,
                        text=f"<b>{w_tot}</b>",
                        showarrow=False,
                        yanchor="bottom",
                        font=dict(size=10, color="#0F172A"),
                    )
                fig_ward = style_fig(fig_ward, height=400)
                fig_ward.update_layout(
                    legend=dict(orientation="h", y=-0.28, title=None),
                    xaxis_title=None,
                    xaxis_tickangle=-35 if len(ward_order) > 6 else 0,
                    yaxis=dict(range=[0, w_tots.max() * 1.15]),
                )
                st.plotly_chart(fig_ward, use_container_width=True)

                # Prepare clean Ward summary table for Excel export
                ward_summary_df = (
                    ward_valid.pivot_table(
                        index=["District", "Ward"],
                        columns="Form",
                        aggfunc="size",
                        fill_value=0,
                    )
                    .assign(Total=lambda d: d.sum(axis=1))
                    .reset_index()
                )

        with wr2:
            st.markdown("**District × Form Count Matrix**")
            district_matrix = pd.crosstab(
                geo_valid_dist["District"],
                geo_valid_dist["Form"],
                margins=True,
                margins_name="Total",
            )
            # Add Wards Covered column per district
            if not ward_valid.empty:
                wards_per_dist = ward_valid.groupby("District")["Ward"].nunique()
                district_matrix.insert(
                    0,
                    "Wards Covered",
                    [
                        int(wards_per_dist.get(idx, 0)) if idx != "Total" else int(len(filtered_wards_set))
                        for idx in district_matrix.index
                    ],
                )
            st.dataframe(district_matrix, use_container_width=True, height=390)

    # --------------------------------------------------------------------------
    # SECTION B: COLLECTION TIMELINE & MULTI-FORM MAP
    # --------------------------------------------------------------------------
    st.markdown('<div class="section-header">📈 Field Momentum & Geographic Map</div>', unsafe_allow_html=True)
    v1_left, v1_right = st.columns(2)

    with v1_left:
        if timeline_frames:
            all_tl = pd.concat(timeline_frames, ignore_index=True)
            daily = all_tl.groupby(["Date", "Form"]).size().reset_index(name="Daily Count").sort_values("Date")
            daily["Cumulative"] = daily.groupby("Form")["Daily Count"].cumsum()
            fig_cum = px.area(
                daily,
                x="Date",
                y="Cumulative",
                color="Form",
                color_discrete_sequence=MEL_PALETTE,
                title="Cumulative Submissions Over Time",
            )
            fig_cum = style_fig(fig_cum, height=430)
            fig_cum.update_layout(legend=dict(orientation="h", y=-0.24, title=None))
            st.plotly_chart(fig_cum, use_container_width=True)
        else:
            st.info("No timestamped records available in this filter.")

    with v1_right:
        if gps_frames:
            geo_all_pts = pd.concat(gps_frames, ignore_index=True)
            st.plotly_chart(
                plot_osm_map(
                    geo_all_pts,
                    color_col="Form",
                    hover_cols=["Form", "District", "Ward", "Enumerator", "Submitted"],
                    title=f"Unified GPS Map Across All Forms ({len(geo_all_pts):,} points)",
                ),
                use_container_width=True,
            )
        else:
            st.info("No GPS coordinates detected in the filtered records.")

    # --------------------------------------------------------------------------
    # SECTION C: FORM SUMMARY TABLE & ONE-CLICK DONOR PACK EXPORT
    # --------------------------------------------------------------------------
    st.markdown('<div class="section-header">📋 Form-by-Form Summary & Donor Export</div>', unsafe_allow_html=True)
    st.dataframe(summary_df, use_container_width=True)

    has_openpyxl = importlib.util.find_spec("openpyxl") is not None
    ex1, ex2 = st.columns(2)
    ex1.download_button(
        "⬇️ Download Form Summary CSV",
        summary_df.to_csv(index=False).encode("utf-8"),
        "dinpp_mel_summary.csv",
        "text/csv",
    )
    if has_openpyxl:
        xlsx_buf = io.BytesIO()
        with pd.ExcelWriter(xlsx_buf, engine="openpyxl") as writer:
            summary_df.to_excel(writer, sheet_name="Form Summary", index=False)
            if not district_matrix.empty:
                district_matrix.reset_index().to_excel(writer, sheet_name="District Breakdown", index=False)
            if not ward_summary_df.empty:
                ward_summary_df.to_excel(writer, sheet_name="Ward Breakdown", index=False)
            pd.DataFrame([{"Donor Brief": brief_text}]).to_excel(writer, sheet_name="Donor Brief", index=False)
        ex2.download_button(
            "⬇️ Download Full Donor Pack (.xlsx)",
            xlsx_buf.getvalue(),
            "dinpp_donor_pack.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        ex2.caption("Tip: Run `python -m pip install openpyxl` to enable multi-sheet `.xlsx` Donor Pack export.")


# ------------------------------------------------------------------------------
# TAB 2: CROSS-FORM LINKAGE (COVERAGE & FOLLOW-UP GAPS)
# ------------------------------------------------------------------------------
with tab_link:
    st.subheader("🔗 Cross-Form Coverage & Follow-Up Tracker")
    st.caption(
        "Compare any two forms using a shared ID or location column (e.g., Site ID, Farmer ID, Ward) "
        "to spot records present in Form A that haven't appeared in Form B yet."
    )

    non_empty_titles = [t for t, d in datasets.items() if not d.empty]
    if len(non_empty_titles) < 2:
        st.info("Need at least two forms with submitted records to compare across forms.")
    else:
        lc1, lc2 = st.columns(2)
        with lc1:
            form_a_name = st.selectbox("Reference Form (Form A)", non_empty_titles, index=0)
            df_a = datasets[form_a_name]
            key_a = st.selectbox("Matching ID / Location column in Form A", df_a.columns, key="key_a")
        with lc2:
            form_b_name = st.selectbox("Follow-Up Form (Form B)", non_empty_titles, index=1)
            df_b = datasets[form_b_name]
            key_b = st.selectbox("Matching ID / Location column in Form B", df_b.columns, key="key_b")

        vals_a = set(df_a[key_a].dropna().astype(str).str.strip()) - {"", "nan", "None"}
        vals_b = set(df_b[key_b].dropna().astype(str).str.strip()) - {"", "nan", "None"}

        matched = sorted(vals_a & vals_b)
        only_a = sorted(vals_a - vals_b)
        only_b = sorted(vals_b - vals_a)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Unique in Form A", len(vals_a))
        m2.metric("Unique in Form B", len(vals_b))
        m3.metric("Matched in Both", len(matched), delta=f"{(len(matched)/len(vals_a)*100):.0f}% of A" if vals_a else None)
        m4.metric("In A Only (Pending in B)", len(only_a))

        link_chart_df = pd.DataFrame({
            "Status": ["Matched in Both", "In Form A Only (Pending in B)", "In Form B Only"],
            "Unique IDs": [len(matched), len(only_a), len(only_b)],
        })
        fig_link = px.bar(
            link_chart_df,
            x="Status",
            y="Unique IDs",
            color="Status",
            color_discrete_sequence=MEL_PALETTE,
            text="Unique IDs",
            title=f"Overlap: {form_a_name} ({key_a}) vs {form_b_name} ({key_b})",
        )
        st.plotly_chart(style_fig(fig_link, height=360), use_container_width=True)

        g1, g2 = st.columns(2)
        with g1:
            st.write(f"**Pending Follow-Up (In `{form_a_name}` only):**")
            pending_df = pd.DataFrame({key_a: only_a})
            st.dataframe(pending_df, use_container_width=True)
            if only_a:
                st.download_button(
                    "⬇️ Download Pending List CSV",
                    pending_df.to_csv(index=False).encode("utf-8"),
                    "pending_followup_ids.csv",
                    "text/csv",
                )
        with g2:
            st.write(f"**Matched IDs ({len(matched)}):**")
            st.dataframe(pd.DataFrame({"Matched ID": matched}), use_container_width=True)


# ------------------------------------------------------------------------------
# TAB 3: DATA QUALITY (QA) & FIELD TEAM MONITORING
# ------------------------------------------------------------------------------
with tab_qa:
    st.subheader("🛡️ Field Team Activity & Data Quality Audit")

    enum_rows = []
    cutoff_7d_qa = pd.Timestamp.now(tz=NEPAL_TZ).tz_localize(None) - pd.Timedelta(days=7)

    for title, df_q in datasets.items():
        if df_q.empty:
            continue
        users, _ = get_enumerator_series(df_q)
        dts, _ = get_submission_time_series(df_q)
        dur = get_duration_minutes(df_q)
        gps = extract_gps(df_q)
        has_gps = df_q.index.isin(gps.index)

        enum_rows.append(
            pd.DataFrame({
                "Enumerator": users,
                "Form": title,
                "Submitted": dts,
                "HasGPS": has_gps,
                "DurationMin": dur if dur is not None else pd.Series(float("nan"), index=df_q.index),
            })
        )

    if enum_rows:
        all_enum = pd.concat(enum_rows, ignore_index=True)
        all_enum["IsLast7d"] = all_enum["Submitted"] >= cutoff_7d_qa

        board = (
            all_enum.groupby("Enumerator")
            .agg(
                Total_Submissions=("Form", "count"),
                Last_7_Days=("IsLast7d", "sum"),
                Forms_Covered=("Form", "nunique"),
                GPS_Rate_Pct=("HasGPS", lambda s: round(s.mean() * 100, 1)),
                Median_Duration_Min=("DurationMin", lambda s: round(s.dropna().median(), 1) if s.dropna().any() else None),
                Latest_Upload=("Submitted", "max"),
            )
            .reset_index()
            .sort_values("Total_Submissions", ascending=False)
        )
        board["Latest_Upload"] = board["Latest_Upload"].dt.strftime("%Y-%m-%d %H:%M").fillna("N/A")

        eb1, eb2 = st.columns([1.3, 1])
        with eb1:
            st.write("**Enumerator Productivity & Quality Leaderboard**")
            st.dataframe(board, use_container_width=True)
        with eb2:
            fig_enum = px.bar(
                board.sort_values("Total_Submissions", ascending=True),
                x="Total_Submissions",
                y="Enumerator",
                orientation="h",
                color="GPS_Rate_Pct",
                color_continuous_scale="Teal",
                title="Submissions by Enumerator (Colored by GPS %)",
            )
            st.plotly_chart(style_fig(fig_enum, height=380), use_container_width=True)

    st.divider()
    st.write("### 🔍 Single-Form QA Checks")
    qa_form_name = st.selectbox("Choose form to audit", list(datasets.keys()), key="qa_form")
    df_qa = datasets[qa_form_name]

    if df_qa.empty:
        st.info("No records to audit in this form.")
    else:
        qa1, qa2, qa3 = st.columns(3)
        with qa1:
            dup_col = st.selectbox("Check duplicates on column:", df_qa.columns, index=0, key="dup_col")
            s_dup = df_qa[dup_col].dropna().astype(str)
            dup_mask = s_dup.duplicated(keep=False)
            n_dups = int(dup_mask.sum())
            st.metric(f"Duplicate rows on '{dup_col}'", n_dups)

        dur_series = get_duration_minutes(df_qa)
        with qa2:
            min_ok = st.number_input("Flag interviews shorter than (min)", min_value=0.0, value=2.0, step=0.5)
        with qa3:
            max_ok = st.number_input("Flag interviews longer than (min)", min_value=5.0, value=120.0, step=5.0)

        if dur_series is not None and dur_series.dropna().any():
            valid_dur = dur_series.dropna()
            too_fast = df_qa[dur_series < min_ok]
            too_long = df_qa[dur_series > max_ok]
            dc1, dc2, dc3 = st.columns(3)
            dc1.metric("Median Duration (min)", f"{valid_dur.median():.1f}")
            dc2.metric(f"Too Fast (< {min_ok} min)", len(too_fast))
            dc3.metric(f"Unusually Long (> {max_ok} min)", len(too_long))

            fig_dur = px.histogram(
                x=valid_dur[valid_dur.between(0, max_ok * 1.5)],
                nbins=25,
                color_discrete_sequence=["#0F766E"],
                labels={"x": "Interview Duration (Minutes)"},
                title="Interview Duration Distribution",
            )
            st.plotly_chart(style_fig(fig_dur, height=340), use_container_width=True)
        else:
            st.info("Start/End timestamps not found in this form for interview duration checks.")

        if n_dups > 0:
            with st.expander(f"⚠️ View {n_dups} Duplicate Records on '{dup_col}'"):
                st.dataframe(df_qa.loc[s_dup[dup_mask].index], use_container_width=True)

        miss = (df_qa.isna().mean() * 100).round(1).reset_index()
        miss.columns = ["Column", "Missing (%)"]
        miss = miss[miss["Missing (%)"] > 0].sort_values("Missing (%)", ascending=False)
        if not miss.empty:
            fig_miss = px.bar(
                miss.head(20),
                x="Missing (%)",
                y="Column",
                orientation="h",
                color_discrete_sequence=["#D97706"],
                title="Top 20 Columns by Missing Data (%)",
            )
            st.plotly_chart(style_fig(fig_miss, height=400), use_container_width=True)
        else:
            st.success("Zero missing cells detected in this dataset!")


# ------------------------------------------------------------------------------
# TAB 4: SINGLE FORM DEEP-DIVE (FREQUENCIES, STATS, CROSS-TABS)
# ------------------------------------------------------------------------------
with tab_deep:
    chosen_title = st.selectbox("Select a Form", [f["title"] for f in active_forms], key="deep_form")
    chosen_form = next(f for f in active_forms if f["title"] == chosen_title)

    subforms = chosen_form.get("subforms", {})
    chosen_subform = None
    if subforms:
        sub_choice = st.selectbox("Dataset / Repeat Table", ["Main Form"] + list(subforms.keys()))
        if sub_choice != "Main Form":
            chosen_subform = sub_choice

    try:
        df = (
            datasets[chosen_title]
            if chosen_subform is None
            else get_survey_data(chosen_form["id_string"], subform=chosen_subform, user_token_key=auth_cache_key)
        )
    except requests.HTTPError as ex:
        status = ex.response.status_code if ex.response is not None else ""
        st.error(f"Smap returned {status} for {chosen_title}.")
        st.stop()

    if df.empty:
        st.info("This form/subform currently has 0 submissions.")
        st.stop()

    with st.expander("🔎 Filter records before analyzing (optional)"):
        filter_col = st.selectbox("Filter by column", ["(None)"] + list(df.columns))
        if filter_col != "(None)":
            opts = sorted(df[filter_col].dropna().astype(str).unique().tolist())
            picked = st.multiselect(f"Keep values in '{filter_col}'", opts, default=opts)
            df = df[df[filter_col].astype(str).isin(picked)]

    c1, c2, c3 = st.columns(3)
    c1.metric("Filtered Submissions", len(df))
    c2.metric("Total Variables", len(df.columns))
    c3.metric("Overall Missing Cells", f"{df.isna().mean().mean() * 100:.1f}%" if not df.empty else "0.0%")

    if df.empty:
        st.warning("No rows match your filter.")
        st.stop()

    num_cols = df.select_dtypes(include="number").columns.tolist()
    cat_cols = [c for c in df.columns if c not in num_cols]

    st.markdown("### 1. Descriptive Statistics & Frequencies")
    col_left, col_right = st.columns(2)

    with col_left:
        st.write("**Categorical / Select Variable Frequency**")
        if cat_cols:
            cat_var = st.selectbox("Choose categorical column", cat_cols, key="deep_cat")
            chart_type = st.radio("Chart type", ["Bar", "Pie"], horizontal=True)
            freq = df[cat_var].fillna("(Missing)").value_counts().reset_index()
            freq.columns = [cat_var, "Count"]
            freq["Percent (%)"] = (freq["Count"] / len(df) * 100).round(1)
            st.dataframe(freq, use_container_width=True)
            if chart_type == "Bar":
                fig_cat = px.bar(
                    freq.head(20),
                    x=cat_var,
                    y="Count",
                    text="Percent (%)",
                    color_discrete_sequence=["#0F766E"],
                    title=f"Top values: {cat_var}",
                )
            else:
                fig_cat = px.pie(
                    freq.head(12),
                    names=cat_var,
                    values="Count",
                    color_discrete_sequence=MEL_PALETTE,
                    title=f"Share: {cat_var}",
                )
            st.plotly_chart(style_fig(fig_cat, height=380), use_container_width=True)

    with col_right:
        st.write("**Numeric Variable Summary**")
        if num_cols:
            num_var = st.selectbox("Choose numeric column", num_cols, key="deep_num")
            stats = df[num_var].describe().round(2).to_frame(name="Value")
            st.dataframe(stats, use_container_width=True)
            fig_hist = px.histogram(
                df,
                x=num_var,
                nbins=20,
                marginal="box",
                color_discrete_sequence=["#1D4ED8"],
                title=f"Distribution: {num_var}",
            )
            st.plotly_chart(style_fig(fig_hist, height=380), use_container_width=True)
        else:
            st.info("No numeric columns detected in this form.")

    st.markdown("### 2. Cross-Tabulation (2 Variables)")
    if len(df.columns) >= 2:
        x1, x2, x3 = st.columns(3)
        row_var = x1.selectbox("Row Variable", df.columns, index=0)
        col_var = x2.selectbox("Column Variable", df.columns, index=1)
        norm_opt = x3.selectbox("Show values as", ["Counts", "Row %", "Column %", "Total %"])

        if row_var == col_var:
            st.warning("Choose two different variables for Row and Column.")
        else:
            norm_map = {"Counts": False, "Row %": "index", "Column %": "columns", "Total %": "all"}
            ct = pd.crosstab(
                df[row_var].fillna("(Missing)"),
                df[col_var].fillna("(Missing)"),
                normalize=norm_map[norm_opt],
                margins=True,
            )
            if norm_opt != "Counts":
                ct = (ct * 100).round(1)

            st.dataframe(ct, use_container_width=True)
            st.download_button(
                "⬇️ Download Cross-Tab CSV",
                ct.to_csv().encode("utf-8"),
                f"crosstab_{row_var}_vs_{col_var}.csv",
                "text/csv",
            )

            ct_plot = pd.crosstab(df[row_var].fillna("(Missing)"), df[col_var].fillna("(Missing)"))
            fig_ct = px.bar(
                ct_plot,
                barmode="group",
                color_discrete_sequence=MEL_PALETTE,
                title=f"{row_var} by {col_var}",
            )
            st.plotly_chart(style_fig(fig_ct, height=400), use_container_width=True)

    with st.expander("View Raw Dataset"):
        st.dataframe(df.head(300), use_container_width=True)
        st.download_button(
            "⬇️ Download Filtered Dataset CSV",
            df.to_csv(index=False).encode("utf-8"),
            f"{chosen_form['id_string']}_filtered.csv",
            "text/csv",
        )