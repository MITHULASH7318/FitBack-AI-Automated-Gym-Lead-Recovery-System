"""Castro Gym - AI Member Recovery Dashboard (Streamlit).

Reads three tabs: Members, campaign_log, skipped_log.
Mode 1 (local): CSV files in the 'data' folder next to this file.
Mode 2 (cloud): Google Sheet through a service account saved in Streamlit secrets.
"""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Castro Gym - Member Recovery", page_icon="🏋️", layout="wide")

MIN_DAYS = 31
COOLDOWN_DAYS = 30
DATA_DIR = Path(__file__).parent / "data"
SEGMENTS = ["Active", "Friendly check-in", "Motivational comeback",
            "Personalised re-engagement", "Gentle win-back", "Unknown"]
MEMBER_COLS = ["member_id", "customer_name", "phone_number", "email", "telegram_username",
               "telegram_chat_id", "last_visit_date", "membership_expiry_date", "membership_plan",
               "total_visits", "marketing_consent", "telegram_opt_in", "do_not_contact",
               "last_campaign_date"]
LOG_COLS = ["campaign_id", "member_id", "customer_name", "inactivity_days", "recovery_segment",
            "message_generated", "message_text", "message_source", "message_sent",
            "telegram_message_id", "sent_at", "send_status", "failure_reason",
            "customer_reply", "opt_out", "rejoined", "rejoin_date"]
SKIP_COLS = ["logged_at", "member_id", "customer_name", "eligibility_reason",
             "all_reasons", "days_inactive", "mode"]
TEMPLATES = {
    "Friendly check-in": "Hi {n}! Just checking in from Castro Gym. We'd love to see you back whenever you're ready. 😊",
    "Motivational comeback": "Hi {n}! Your fitness journey is always worth continuing. We'd love to welcome you back to Castro Gym whenever you're ready.",
    "Personalised re-engagement": "Hi {n}! We hope you're doing well. It's been a little while since your last visit to Castro Gym, and we'd love to welcome you back whenever you're ready.",
    "Gentle win-back": "Hi {n}! No pressure at all. Our doors at Castro Gym are always open for you whenever you feel like coming back.",
}


def to_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin(["true", "yes", "y", "1"])


def parse_dates(series: pd.Series) -> pd.Series:
    """Accepts 2026-08-01 (ISO) or 01/08/2026 (day first, Indian format). Time part is ignored."""
    s = series.astype(str).str.strip().str.slice(0, 10)
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    iso = s.str.match(r"^\d{4}-\d{2}-\d{2}$")
    out[iso] = pd.to_datetime(s[iso], format="%Y-%m-%d", errors="coerce")
    other = ~iso & s.ne("")
    out[other] = pd.to_datetime(s[other], format="%d/%m/%Y", errors="coerce")
    return out


def ensure_cols(df: pd.DataFrame, cols: list) -> pd.DataFrame:
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df.fillna("")


@st.cache_data(ttl=300, show_spinner="Loading data...")
def load_data():
    source = "Local CSV files"
    secrets_error = ""
    try:
        use_sheet = "gcp_service_account" in st.secrets and "sheet_id" in st.secrets
        if not use_sheet:
            if len(st.secrets) > 0:
                secrets_error = "Secrets file found, but it has no [gcp_service_account] section or no sheet_id."
            elif (Path.cwd() / ".streamlit" / "secrets.toml").exists():
                secrets_error = ("secrets.toml exists but is empty or could not be read. Save the file, "
                                 "keep every value in double quotes and the private key on one line.")
    except Exception as e:
        use_sheet = False
        if type(e).__name__ != "StreamlitSecretNotFoundError":
            secrets_error = f"Secrets file could not be read ({type(e).__name__}). Check quotes and line breaks."
        elif (Path.cwd() / ".streamlit" / "secrets.toml").exists():
            secrets_error = ("secrets.toml exists but could not be read. Save the file, keep every value "
                             "in double quotes and the private key on one line.")

    if use_sheet:
        import gspread
        from google.oauth2.service_account import Credentials
        creds = Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]),
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
        sh = gspread.authorize(creds).open_by_key(st.secrets["sheet_id"])

        def read(tab):
            try:
                rows = sh.worksheet(tab).get_all_values()
            except gspread.WorksheetNotFound:
                return pd.DataFrame()
            if not rows:
                return pd.DataFrame()
            return pd.DataFrame(rows[1:], columns=rows[0])

        source = "Google Sheet (live)"
        members, log, skipped = read("Members"), read("campaign_log"), read("skipped_log")
    else:
        def read(name):
            path = DATA_DIR / name
            return pd.read_csv(path, dtype=str) if path.exists() else pd.DataFrame()

        members, log, skipped = read("members.csv"), read("campaign_log.csv"), read("skipped_log.csv")

    return (ensure_cols(members, MEMBER_COLS), ensure_cols(log, LOG_COLS),
            ensure_cols(skipped, SKIP_COLS), source, secrets_error)


def segment_of(d):
    if pd.isna(d):
        return "Unknown"
    if d <= 30:
        return "Active"
    if d <= 60:
        return "Friendly check-in"
    if d <= 90:
        return "Motivational comeback"
    if d <= 180:
        return "Personalised re-engagement"
    return "Gentle win-back"


def prepare_members(m: pd.DataFrame, today: pd.Timestamp) -> pd.DataFrame:
    m = m.copy()
    m["days_inactive"] = (today - parse_dates(m["last_visit_date"])).dt.days
    m["days_to_expiry"] = (parse_dates(m["membership_expiry_date"]) - today).dt.days
    m["days_since_campaign"] = (today - parse_dates(m["last_campaign_date"])).dt.days
    m["recovery_segment"] = m["days_inactive"].apply(segment_of)
    m["membership_status"] = np.where(m["days_to_expiry"].isna(), "Unknown",
                                      np.where(m["days_to_expiry"] < 0, "Expired", "Active"))

    chat = m["telegram_chat_id"].astype(str).str.strip()
    conditions = [
        to_bool(m["do_not_contact"]),
        ~to_bool(m["marketing_consent"]),
        ~to_bool(m["telegram_opt_in"]),
        chat == "",
        ~chat.str.fullmatch(r"-?\d{5,}"),
        m["days_inactive"].isna(),
        m["days_inactive"] < MIN_DAYS,
        m["days_since_campaign"] < COOLDOWN_DAYS,
    ]
    reasons = ["Do not contact is TRUE", "No marketing consent", "No Telegram opt-in",
               "Telegram chat ID is empty", "Telegram chat ID is invalid",
               "Last visit date missing or invalid", "Member is active (under 31 days)",
               "Cooldown (contacted in last 30 days)"]
    m["eligibility_reason"] = np.select(conditions, reasons, default="Eligible")
    m["eligible"] = m["eligibility_reason"] == "Eligible"
    return m


# ------------------------------------------------------------------ sidebar
st.sidebar.title("🏋️ Castro Gym")
ist_today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
ref_date = st.sidebar.date_input("Reference date", ist_today,
                                 help="Days inactive are counted up to this date.")
if st.sidebar.button("🔄 Refresh data"):
    st.cache_data.clear()
    st.rerun()

members_raw, log, skipped, source, secrets_error = load_data()
st.sidebar.caption(f"Data source: {source}")
if secrets_error:
    st.sidebar.warning(secrets_error)

if members_raw["member_id"].astype(str).str.strip().eq("").all():
    st.title("Castro Gym - AI Member Recovery Dashboard")
    st.error("No member data found. Put members.csv in the 'data' folder, or add Google Sheet secrets.")
    st.stop()

members = prepare_members(members_raw, pd.Timestamp(ref_date))
log = log.copy()
status = log["send_status"].astype(str).str.upper()
sent = log[status == "SENT"].copy()
failed = log[status == "FAILED"]

# ------------------------------------------------------------------ KPIs
total = len(members)
active = int((members["days_inactive"] <= 30).sum())
inactive = int((members["days_inactive"] >= MIN_DAYS).sum())
eligible = int(members["eligible"].sum())
contacted = sent["member_id"].nunique()
messages_sent = len(sent)
replies = int(log["customer_reply"].astype(str).str.strip().ne("").sum())
rejoined = log.loc[to_bool(log["rejoined"]), "member_id"].nunique()
conversion = f"{rejoined / contacted * 100:.1f}%" if contacted else "–"

st.title("Castro Gym - AI Member Recovery Dashboard")
st.caption("“Sent” means Telegram accepted the message. It does not mean delivered, read or rejoined.")

r1 = st.columns(5)
r1[0].metric("Total members", total)
r1[1].metric("Active (visited in last 30 days)", active)
r1[2].metric("Inactive (31+ days)", inactive)
r1[3].metric("Eligible to contact", eligible)
r1[4].metric("Members contacted", contacted)
r2 = st.columns(5)
r2[0].metric("Messages sent", messages_sent)
r2[1].metric("Failed sends", len(failed))
r2[2].metric("Replies received", replies)
r2[3].metric("Members rejoined", rejoined)
r2[4].metric("Recovery conversion", conversion, help="Rejoined members ÷ members contacted")
if members["days_inactive"].isna().any():
    st.warning(f"{int(members['days_inactive'].isna().sum())} members have a missing or invalid last visit date.")

tab_over, tab_mem, tab_camp, tab_skip, tab_prev, tab_dl = st.tabs(
    ["Overview", "Members", "Campaigns", "Skipped members", "Message preview", "Downloads"])

SAFE_COLS = ["member_id", "customer_name", "membership_plan", "total_visits", "last_visit_date",
             "days_inactive", "recovery_segment", "membership_expiry_date", "membership_status",
             "days_to_expiry", "eligible", "eligibility_reason", "last_campaign_date"]

# ------------------------------------------------------------------ overview
with tab_over:
    c1, c2 = st.columns(2)
    seg = (members["recovery_segment"].value_counts()
           .reindex(SEGMENTS, fill_value=0).reset_index())
    seg.columns = ["Segment", "Members"]
    seg = seg[seg["Members"] > 0]
    c1.subheader("Inactivity segments")
    c1.plotly_chart(px.bar(seg, x="Segment", y="Members", text="Members", color="Segment"),
                    width="stretch")

    bucket = pd.cut(members["days_to_expiry"], bins=[-np.inf, -1, 30, 60, 90, np.inf],
                    labels=["Expired", "Expires in 0-30 days", "31-60 days", "61-90 days", "90+ days"])
    exp = bucket.value_counts(sort=False).reset_index()
    exp.columns = ["Membership expiry", "Members"]
    c2.subheader("Membership expiry tracking")
    c2.plotly_chart(px.bar(exp, x="Membership expiry", y="Members", text="Members"),
                    width="stretch")

# ------------------------------------------------------------------ members
with tab_mem:
    f1, f2, f3, f4 = st.columns(4)
    q = f1.text_input("Search name or member ID")
    seg_sel = f2.multiselect("Segment", SEGMENTS)
    elig_sel = f3.selectbox("Eligibility", ["All", "Eligible only", "Not eligible only"])
    plan_sel = f4.multiselect("Plan", sorted(members["membership_plan"].astype(str).unique()))
    view = members.copy()
    if q:
        mask = (view["customer_name"].astype(str).str.contains(q, case=False, na=False)
                | view["member_id"].astype(str).str.contains(q, case=False, na=False))
        view = view[mask]
    if seg_sel:
        view = view[view["recovery_segment"].isin(seg_sel)]
    if plan_sel:
        view = view[view["membership_plan"].isin(plan_sel)]
    if elig_sel == "Eligible only":
        view = view[view["eligible"]]
    elif elig_sel == "Not eligible only":
        view = view[~view["eligible"]]
    st.write(f"{len(view)} members shown")
    st.dataframe(view[SAFE_COLS], width="stretch", hide_index=True)
    st.caption("Phone, email and Telegram IDs are hidden on purpose.")

# ------------------------------------------------------------------ campaigns
with tab_camp:
    if log["member_id"].astype(str).str.strip().eq("").all():
        st.info("No campaign rows yet. Run the n8n workflow in LIVE mode to create them.")
    else:
        c1, c2 = st.columns(2)
        stat = log["send_status"].replace("", "UNKNOWN").value_counts().reset_index()
        stat.columns = ["Status", "Messages"]
        c1.subheader("Campaign performance by status")
        c1.plotly_chart(px.bar(stat, x="Status", y="Messages", text="Messages", color="Status"),
                        width="stretch")
        if len(sent):
            sent["day"] = parse_dates(sent["sent_at"]).dt.date
            per_day = sent.groupby("day").size().reset_index(name="Messages sent")
            c2.subheader("Messages sent per day")
            c2.plotly_chart(px.bar(per_day, x="day", y="Messages sent", text="Messages sent"),
                            width="stretch")
            by_seg = sent["recovery_segment"].value_counts().reset_index()
            by_seg.columns = ["Segment", "Messages sent"]
            st.subheader("Messages sent by segment")
            st.plotly_chart(px.bar(by_seg, x="Segment", y="Messages sent", text="Messages sent"),
                            width="stretch")
        st.subheader("Campaign history")
        st.dataframe(log.assign(_d=parse_dates(log["sent_at"])).sort_values(["_d", "sent_at"], ascending=False).drop(columns="_d"),
                     width="stretch", hide_index=True)

# ------------------------------------------------------------------ skipped
with tab_skip:
    skipped_now = members[~members["eligible"]]
    st.subheader("Why members are not eligible right now")
    st.caption("Calculated from the current Members sheet with the same rules as the n8n workflow. "
               "The first failed rule is shown.")
    reasons = skipped_now["eligibility_reason"].value_counts().reset_index()
    reasons.columns = ["Reason", "Members"]
    st.plotly_chart(px.bar(reasons, x="Members", y="Reason", orientation="h", text="Members"),
                    width="stretch")
    st.dataframe(skipped_now[SAFE_COLS], width="stretch", hide_index=True)
    if not skipped["member_id"].astype(str).str.strip().eq("").all():
        st.subheader("Skipped log written by n8n")
        st.dataframe(skipped.sort_values("logged_at", ascending=False),
                     width="stretch", hide_index=True)

# ------------------------------------------------------------------ preview
with tab_prev:
    st.subheader("Message preview")
    options = (members["member_id"].astype(str) + " - " + members["customer_name"].astype(str)).tolist()
    pick = st.selectbox("Choose a member", options)
    mid = pick.split(" - ")[0]
    row = members[members["member_id"].astype(str) == mid].iloc[0]
    st.write(f"Segment: **{row['recovery_segment']}**  |  Inactive days: **{row['days_inactive']}**  |  "
             f"Eligible now: **{'Yes' if row['eligible'] else 'No - ' + row['eligibility_reason']}**")
    past = log[log["member_id"].astype(str) == mid]
    past = past.assign(_d=parse_dates(past["sent_at"])).sort_values(["_d", "sent_at"], ascending=False)
    if len(past):
        st.success(f"Last message recorded ({past.iloc[0]['message_source']}, "
                   f"{past.iloc[0]['send_status']}):")
        st.info(past.iloc[0]["message_text"])
    else:
        st.caption("No message recorded for this member yet.")
    tpl = TEMPLATES.get(row["recovery_segment"])
    if tpl:
        first = str(row["customer_name"]).split(" ")[0] or "there"
        st.markdown("**Fallback template preview** (no AI call is made from the dashboard):")
        st.info(tpl.format(n=first))
    else:
        st.caption("Active or unknown members do not get a recovery message.")

# ------------------------------------------------------------------ downloads
with tab_dl:
    st.subheader("Download reports (CSV)")
    st.download_button("Members report (no phone/email/chat ID)",
                       members[SAFE_COLS].to_csv(index=False).encode("utf-8"),
                       "members_report.csv", "text/csv")
    st.download_button("Eligible members",
                       members[members["eligible"]][SAFE_COLS].to_csv(index=False).encode("utf-8"),
                       "eligible_members.csv", "text/csv")
    st.download_button("Skipped members with reasons",
                       members[~members["eligible"]][SAFE_COLS].to_csv(index=False).encode("utf-8"),
                       "skipped_members.csv", "text/csv")
    st.download_button("Campaign history", log.to_csv(index=False).encode("utf-8"),
                       "campaign_history.csv", "text/csv")