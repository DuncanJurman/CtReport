import streamlit as st
import requests
import pandas as pd
import random
import datetime
from mailchimp_marketing import Client
from urllib.parse import urlparse
from bs4 import BeautifulSoup

# File paths
TEMPLATE_FILE = "Nick Email Machine Template.html"
OUTPUT_FILE = "Updated_Email_Template.html"

# URLs
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1CIY8uZJcfrLduMHcjxBqYpFs0ygIJPSdGHZ_RVlR48g/gviz/tq?tqx=out:csv"
GOOGLE_SHEET_EDIT_URL = "https://docs.google.com/spreadsheets/d/1CIY8uZJcfrLduMHcjxBqYpFs0ygIJPSdGHZ_RVlR48g/edit"
HEADLINES_URL = "https://www.ctcapitolreport.com/email_template.php"

# ---------- STEP 1: Scrape Headlines ----------
def scrape_headlines(url):
    response = requests.get(url)
    if response.status_code != 200:
        st.error("❌ Failed to retrieve the page")
        return None
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    sections = {
        'Top Headlines': [],
        'Left Column': [],
        'Middle Column': [],
        'Right Column': []
    }
    
    current_section = None
    
    for tag in soup.find_all(['h2', 'a']):
        if tag.name == 'h2':
            section_title = tag.text.strip()
            if section_title in sections:
                current_section = section_title
        elif tag.name == 'a' and current_section and 'href' in tag.attrs:
            link_url = tag['href'].strip()
            link_text = tag.previous_sibling
            if not link_text or not isinstance(link_text, str):
                parent = tag.find_parent()
                if parent:
                    link_text = parent.get_text(strip=True).replace(link_url, '').strip()
            else:
                link_text = link_text.strip()
            
            if not link_text:
                link_text = "Title Not Found"
            
            sections[current_section].append(f"{link_text} <a href=\"{link_url}\" target=\"_blank\">(link)</a><br><br>")

    # Trim the last "<br><br>" from each section
    for section in sections:
        if sections[section]:  
            sections[section][-1] = sections[section][-1].replace("<br><br>", "")  

    return sections

# ---------- STEP 2: Get Ads from Public Google Sheet ----------
def get_ads_from_public_google_sheet(sheet_csv_url):
    try:
        df = pd.read_csv(sheet_csv_url)
    except Exception as e:
        st.error(f"❌ Error fetching Google Sheet: {e}")
        return []

    df.columns = ["Ad Text", "Ad Link"]

    ads = [
        f"{row['Ad Text']} <a href=\"{row['Ad Link']}\" target=\"_blank\">(link)</a>"
        for _, row in df.iterrows()
    ]

    return ads

# ---------- STEP 3: Format Ads ----------
def format_ads(ads):
    formatted_ads = []
    
    for ad in ads:
        ad_parts = ad.split('<a href="')
        ad_text = ad_parts[0].replace("IMPORTANT SPONSORED MESSAGE: ", "").strip()
        ad_url = ad_parts[1].split('" target="_blank">')[0]
        website = urlparse(ad_url).netloc  
        formatted_ad = f'<br><br><strong>IMPORTANT SPONSORED MESSAGE:</strong> {ad_text} <a href="{ad_url}" target="_blank">{website}</a>'
        formatted_ads.append(formatted_ad)
    
    return formatted_ads

# ---------- STEP 4: Insert Data into Template ----------
def insert_data_into_template(template_path, output_path, headlines, ads):
    try:
        with open(template_path, 'r', encoding='utf-8') as file:
            template = file.read()
    except Exception as e:
        st.error(f"❌ Error reading template file: {e}")
        return None

    ads = format_ads(ads)

    def format_section(section):
        return "".join(section)

    random.shuffle(ads)
    ad_slots = ['Top Headlines', 'Left Column', 'Middle Column', 'Right Column']

    for i in range(min(len(ads), len(ad_slots))):
        headlines[ad_slots[i]].append(ads[i])  

    template = template.replace("{{TOP_HEADLINES}}", format_section(headlines['Top Headlines']))
    template = template.replace("{{LEFT_HEADLINES}}", format_section(headlines['Left Column']))
    template = template.replace("{{MIDDLE_HEADLINES}}", format_section(headlines['Middle Column']))
    template = template.replace("{{RIGHT_HEADLINES}}", format_section(headlines['Right Column']))

    current_date = datetime.datetime.now().strftime("%-m/%-d/%Y")
    template = template.replace("{{CURRENT_DATE}}", current_date)

    with open(output_path, 'w', encoding='utf-8') as file:
        file.write(template)

    return output_path

# ---------- STEP 5: Mailchimp Campaign Creation ----------

# Hardcoded Mailchimp Credentials
MAILCHIMP_API_KEY = st.secrets["mailchimp"]["MAILCHIMP_API_KEY"]
MAILCHIMP_SERVER_PREFIX = "us20"
MAILCHIMP_AUDIENCE_ID = "7f9e915456"


# Read HTML Template
def read_html_template(file_path):
    try:
        with open(file_path, "r") as file:
            return file.read()
    except Exception as e:
        st.error(f"❌ Error reading HTML template: {e}")
        return None

# Create Mailchimp Campaign
def create_campaign(subject_line):
    client = Client()
    client.set_config({
        "api_key": MAILCHIMP_API_KEY,
        "server": MAILCHIMP_SERVER_PREFIX
    })

    today = datetime.datetime.now()
    campaign_name = f"{today.month} {today.day} {today.year} blast"

    campaign_data = {
        "type": "regular",
        "recipients": {
            "list_id": MAILCHIMP_AUDIENCE_ID
        },
        "settings": {
            "subject_line": subject_line,
            "title": campaign_name,
            "from_name": "Ct. Capitol Report",
            "reply_to": "news@ctcapitolreport.com"
        }
    }

    try:
        campaign = client.campaigns.create(campaign_data)
        return campaign["id"]
    except Exception as e:
        st.error(f"❌ Error creating campaign: {e}")
        return None

# Set Campaign Content
def set_campaign_content(campaign_id, html_content):
    client = Client()
    client.set_config({
        "api_key": MAILCHIMP_API_KEY,
        "server": MAILCHIMP_SERVER_PREFIX
    })
    try:
        client.campaigns.set_content(campaign_id, {"html": html_content})
        return True
    except Exception as e:
        st.error(f"❌ Error setting campaign content: {e}")
        return False

# Send Mailchimp Campaign
def send_campaign(campaign_id):
    client = Client()
    client.set_config({
        "api_key": MAILCHIMP_API_KEY,
        "server": MAILCHIMP_SERVER_PREFIX
    })
    try:
        client.campaigns.send(campaign_id)
        return True
    except Exception as e:
        st.error(f"❌ Error sending campaign: {e}")
        return False

# ---------- STREAMLIT UI ----------
# App Title
st.title("Automated Newsletter App")

# -------------------- STEP 1: Fetch & Edit Google Ads --------------------
st.header("Step 1: Fetch and Edit Google Ads")

col1, col2 = st.columns(2)
with col1:
    if st.button("Load Google Sheet Ads"):
        ads_df = get_ads_from_public_google_sheet(GOOGLE_SHEET_CSV_URL)
        if ads_df:
            st.success("Ads Loaded Successfully!")
            st.dataframe(pd.DataFrame({
                "Ad Text": [a.split('<a')[0] for a in ads_df], 
                "Ad Link": [a.split('href="')[1].split('"')[0] for a in ads_df]
            }))

with col2:
    st.markdown(f'<a href="{GOOGLE_SHEET_EDIT_URL}" target="_blank"><button style="width:100%;">Edit Ads</button></a>', unsafe_allow_html=True)

st.divider()

# -------------------- STEP 2: Scrape & Generate Email --------------------
st.header("Step 2: Scrape & Generate Email")

if st.button("Scrape & Generate Email"):
    st.info("Scraping headlines and fetching ads...")

    headlines = scrape_headlines(HEADLINES_URL)
    ads = get_ads_from_public_google_sheet(GOOGLE_SHEET_CSV_URL)

    if not headlines:
        st.error("❌ No headlines found! Please check the source website.")
    elif not ads:
        st.warning("⚠️ No ads found, proceeding without ads.")

    if headlines:
        output_path = insert_data_into_template(TEMPLATE_FILE, OUTPUT_FILE, headlines, ads)
        if output_path:
            st.session_state["email_generated"] = True
            st.success("✅ Email template generated successfully!")
            with open(output_path, "r") as file:
                st.download_button("Download Email HTML", file.read(), file_name="Updated_Email_Template.html", mime="text/html")

st.divider()

# -------------------- STEP 3: Create Mailchimp Campaign --------------------
st.header("Step 3: Mailchimp Campaign")

# Initialize session state
if "campaign_id" not in st.session_state:
    st.session_state["campaign_id"] = None
if "subject_line" not in st.session_state:
    st.session_state["subject_line"] = ""

# User Input for Subject Line
subject_line = st.text_input("Enter Email Subject Line")

if st.button("Create Mailchimp Campaign"):
    if not subject_line:
        st.warning("⚠️ Please enter a subject line before proceeding.")
    elif "email_generated" not in st.session_state or not st.session_state["email_generated"]:
        st.error("❌ No email template found! Please generate the email first.")
    else:
        html_content = read_html_template(OUTPUT_FILE)
        if not html_content:
            st.error("❌ Email template file is empty or missing.")
        else:
            campaign_id = create_campaign(subject_line)
            if campaign_id:
                success = set_campaign_content(campaign_id, html_content)
                if success:
                    st.session_state["campaign_id"] = campaign_id
                    st.session_state["subject_line"] = subject_line
                    st.success(f"✅ Campaign '{subject_line}' created successfully! ID: {campaign_id}")

st.divider()

# -------------------- STEP 4: Preview & Send Campaign --------------------
if st.session_state["campaign_id"]:
    st.header("Step 4: Preview & Send Campaign")
    st.write(f"**Campaign Subject Line:** {st.session_state['subject_line']}")

    if st.button("Send Now"):
        confirm_send = st.checkbox("I confirm that I want to send this campaign now.")
        if confirm_send:
            success = send_campaign(st.session_state["campaign_id"])
            if success:
                st.success("✅ Campaign sent successfully!")