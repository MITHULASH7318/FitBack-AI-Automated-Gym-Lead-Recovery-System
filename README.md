# FitBack-AI-Automated-Gym-Lead-Recovery-System
Castro Gym: AI Member Recovery and Retention System

An automation project for a gym. It finds members who have stopped visiting, writes a short friendly message for each one with an AI model, sends it through a Telegram bot only to members who agreed to receive it, and records everything in a Google Sheet that feeds a live dashboard.

Live dashboard: [PASTE YOUR STREAMLIT LINK HERE]

All member data in this project is synthetic. The system was tested end to end with one real Telegram account. See Tested and not built yet.

How it works
Daily schedule (n8n)
  -> read members from Google Sheet
  -> check every rule (consent, opt-in, do-not-contact, verified chat, inactivity, cooldown)
  -> eligible: Groq writes a message (template fallback if the AI call fails)
       -> LIVE mode only: Telegram sends it -> row added to campaign_log -> last_campaign_date updated
  -> not eligible: skipped, with the exact reason

Telegram onboarding (n8n, always listening)
  member opens their personal link  ->  chat ID saved and marked as verified
  member replies YES                ->  opt-in saved
  member sends STOP                 ->  do-not-contact saved, no more messages

Streamlit dashboard  <-  reads the same Google Sheet (read-only)
Tech stack
Part	Tool
Automation	n8n (Cloud)
Member database and logs	Google Sheets
AI messages	Groq API
Messaging	Telegram Bot API
Dashboard	Python, Pandas, Plotly, Streamlit
Hosting (dashboard)	Streamlit Community Cloud
Source control	GitHub
Who gets a message

A member is contacted only if all of these are true:

Marketing consent is TRUE
Telegram opt-in is TRUE
do_not_contact is FALSE
The Telegram chat ID is valid and verified through the bot (a chat ID typed into the sheet is not enough)
At least 31 days since the last visit
Not contacted in the last 30 days (cooldown)

Boolean values are accepted as TRUE, true, yes, 1 and similar. If a member fails, the first failed rule is recorded as the reason.

Days inactive	Segment	Message tone
0 to 30	Active	No message
31 to 60	Friendly check-in	Light and casual
61 to 90	Motivational comeback	Encouraging
91 to 180	Personalised re-engagement	Warm and personal
181 or more	Gentle win-back	Very gentle, no pressure
Safety and privacy by design
Dry-run first. A MODE setting ('TEST' or 'LIVE') must be changed on purpose before anything is sent.
Consent and opt-out. Members must start the bot and reply YES. STOP blocks all future messages.
Verified chat IDs. Only a real Telegram message can mark a chat as verified, so fake or typed IDs are never contacted.
Cooldown and daily cap limit repeat messages and the effect of any mistake.
Minimal data to the AI. Only the member's first name and a tone hint go to Groq. No phone, email, plan or expiry.
Fallback templates are used if the AI call fails or returns an unusable message.
Dashboard privacy. Phone numbers, emails and Telegram IDs are hidden in tables and downloads.
No secrets in the repository. API keys and the Google key live in n8n credentials and Streamlit secrets.
Dashboard
Total, active, inactive and eligible members
Members contacted, messages sent, failed sends, replies, members rejoined, recovery conversion rate
Inactivity segment chart and membership expiry tracking
Campaign performance and full campaign history
Member search and filters
Skipped-member reasons
Message preview (last recorded message and the fallback template)
CSV downloads

"Sent" means Telegram accepted the message. It does not mean delivered, read, replied to or rejoined, and the dashboard keeps these counts separate.

Google Sheet layout

The dashboard and workflows expect one spreadsheet with three tabs:

Tab	Columns
Members	member_id, customer_name, phone_number, email, telegram_username, telegram_chat_id, last_visit_date, membership_expiry_date, membership_plan, total_visits, marketing_consent, telegram_opt_in, do_not_contact, last_campaign_date, chat_verified
campaign_log	campaign_id, member_id, customer_name, inactivity_days, recovery_segment, message_generated, message_text, message_source, message_sent, telegram_message_id, sent_at, send_status, failure_reason, customer_reply, opt_out, rejoined, rejoin_date
skipped_log	logged_at, member_id, customer_name, eligibility_reason, all_reasons, days_inactive, mode

Keep dates as yyyy-mm-dd and format the chat ID column as plain text.

Run the dashboard

Local, with CSV exports in a data/ folder (members.csv, campaign_log.csv, skipped_log.csv):

pip install -r requirements.txt
streamlit run app.py

Live from Google Sheets: create a read-only service account, share the spreadsheet with it as Viewer, and add this to .streamlit/secrets.toml (or the Streamlit Cloud Secrets box):

sheet_id = "YOUR_SHEET_ID"

[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "..."
client_email = "..."
client_id = "..."
token_uri = "https://oauth2.googleapis.com/token"

Never commit secrets.toml or the JSON key.

Tested and not built yet

Tested

Eligibility logic against a 100-member synthetic dataset with edge cases (missing dates, invalid chat IDs, text booleans, cooldown, opt-out).
Telegram onboarding (/start CODE, YES, STOP) with one real account.
AI message generation, including the fallback path.
A live send to that one account, logged in campaign_log, with the cooldown blocking a second message.
The dashboard against the live Google Sheet.

Not built yet

Reply tracking and "rejoined" tracking. These dashboard numbers stay at 0 until something writes those columns.
Delivery or read status. Telegram does not provide it for bots.
Re-subscribing after STOP through the bot (currently done by editing the sheet).
A second check at sign-up beyond the member code (for example the last digits of a phone number).
Repository
app.py            Streamlit dashboard
requirements.txt  Python packages
README.md         This file
Screenshots

Add dashboard and Telegram conversation screenshots here.
