import os
import streamlit as st
import pandas as pd
import hashlib

try:
    import gspread
    from google.oauth2.service_account import Credentials
except Exception:
    gspread = None
    Credentials = None

# ==================== CONFIG ====================
TUT_COLS = ["Tut 1", "Tut 2", "Tut 3", "Tut 4", "Tut 5"]
REQUIRED_COLS = ["Student_Number", "Surname", "Name"] + TUT_COLS + ["Overall", "question", "response", "Password"]
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
LOCAL_CSV = os.path.join(os.path.dirname(__file__), "TutorialGroup.csv")
SHEET_ID = "15MGolGLXmdQzAr8MCv4SgYTUVPpjnZSXZ6Nbu6XG8tk"
SHEET_EXPORT_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=0"


def hash_password(raw_password: str) -> str:
    """One-way hash so plaintext passwords are never stored anywhere."""
    return hashlib.sha256(raw_password.encode("utf-8")).hexdigest()


@st.cache_resource(show_spinner=False)
def get_worksheet():
    """Connect to Google Sheets using Streamlit secrets when available."""
    try:
        if gspread is None or Credentials is None:
            raise RuntimeError("Google Sheets libraries are not available")

        if not hasattr(st, "secrets") or "gcp_service_account" not in st.secrets:
            raise KeyError("Missing Google Sheets service-account secrets")

        service_account = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(service_account, scopes=SCOPES)
        client = gspread.authorize(creds)
        sheet_id = st.secrets.get("sheet_id", SHEET_ID)
        return client.open_by_key(sheet_id).sheet1
    except Exception:
        return None


def load_data() -> pd.DataFrame:
    """Pull the latest roster from Google Sheets via secrets, then fall back to the CSV export or local CSV file."""
    sheet = get_worksheet()

    if sheet is None:
        try:
            df = pd.read_csv(SHEET_EXPORT_URL)
        except Exception:
            df = pd.read_csv(LOCAL_CSV)
    else:
        df = pd.DataFrame(sheet.get_all_records())

    if df.empty:
        st.error("The roster appears to be empty. Make sure row 1 has your column headers and the student rows are filled in below it.")
        st.stop()

    df.columns = df.columns.str.strip()
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].astype(str).str.strip()

    df["Student_Number"] = df["Student_Number"].astype(str).str.strip()

    for col in REQUIRED_COLS:
        if col not in df.columns:
            df[col] = ""

    for col in TUT_COLS + ["Overall"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df


def save_data():
    """Push the in-memory roster back to Google Sheets via secrets, or save locally when unavailable."""
    sheet = get_worksheet()
    df = st.session_state.db.fillna("")

    if sheet is None:
        df.to_csv(LOCAL_CSV, index=False)
        return

    values = [df.columns.tolist()] + df.astype(str).values.tolist()
    sheet.clear()
    sheet.update(values=values)


# ==================== STYLING ====================
st.markdown(
    """
    <style>
    .stApp {
        background-color: #c1121f;
        background-image:
            radial-gradient(circle, #111111 9px, transparent 10px),
            radial-gradient(circle, #111111 9px, transparent 10px);
        background-size: 60px 60px;
        background-position: 0 0, 30px 30px;
    }

    .stApp, .stApp p, .stApp label, .stApp span, .stApp h1,
    .stApp h2, .stApp h3, .stApp .stMarkdown {
        color: #ffffff;
    }

    div[data-testid="stForm"], div[data-testid="stVerticalBlock"] > div:has(> div[data-testid="stMetric"]),
    div[data-testid="stDataFrame"] {
        background-color: rgba(0, 0, 0, 0.55);
        border-radius: 10px;
        padding: 12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ==================== LOAD DATA ====================
if "db" not in st.session_state:
    st.session_state.db = load_data()

with st.sidebar:
    if st.button("🔄 Refresh Data"):
        st.session_state.db = load_data()
        st.success("Data refreshed from Google Sheet.")
        st.rerun()

role = st.sidebar.radio("Select Role:", ["Student Portal", "Tutor Dashboard"])

if role == "Student Portal":
    st.header("👤 Student Authentication")

    if "auth_index" not in st.session_state:
        st.session_state.auth_index = None
    if "password_ok" not in st.session_state:
        st.session_state.password_ok = False

    with st.form("auth_form"):
        input_fn = st.text_input("First Name (Matches 'Name' column)")
        input_sn = st.text_input("Surname")
        input_id = st.text_input("Student Number")
        submit_auth = st.form_submit_button("Identify Myself")

    if submit_auth:
        df = st.session_state.db
        input_fn = input_fn.strip()
        input_sn = input_sn.strip()
        input_id = input_id.strip()

        match = df[
            (df['Student_Number'].str.strip().str.lower() == input_id.lower()) &
            (df['Name'].str.strip().str.lower() == input_fn.lower()) &
            (df['Surname'].str.strip().str.lower() == input_sn.lower())
        ]

        if not match.empty:
            st.session_state.auth_index = int(match.index[0])
            st.session_state.password_ok = False
            st.success(f"Identity confirmed, {input_fn}! Now enter your password below.")
        else:
            st.session_state.auth_index = None
            st.session_state.password_ok = False
            st.error("Authentication failed. Please verify the exact spelling from your spreadsheet.")

    if st.session_state.auth_index is not None and not st.session_state.password_ok:
        idx = st.session_state.auth_index
        df = st.session_state.db
        stored_hash = str(df.at[idx, 'Password'])

        if stored_hash == "" or stored_hash == "nan":
            st.subheader("🔑 Create Your Password")
            st.caption("This is your first time logging in — set a password to protect your marks.")
            with st.form("set_password_form"):
                new_pw = st.text_input("Choose a Password", type="password")
                confirm_pw = st.text_input("Confirm Password", type="password")
                submit_pw = st.form_submit_button("Set Password")

            if submit_pw:
                if len(new_pw) < 4:
                    st.error("Password must be at least 4 characters long.")
                elif new_pw != confirm_pw:
                    st.error("Passwords do not match. Please try again.")
                else:
                    st.session_state.db.at[idx, 'Password'] = hash_password(new_pw)
                    save_data()
                    st.session_state.password_ok = True
                    st.success("Password set! Loading your dashboard...")
                    st.rerun()
        else:
            st.subheader("🔒 Enter Your Password")
            with st.form("login_password_form"):
                login_pw = st.text_input("Password", type="password")
                submit_login_pw = st.form_submit_button("Log In")

            if submit_login_pw:
                if hash_password(login_pw) == stored_hash:
                    st.session_state.password_ok = True
                    st.rerun()
                else:
                    st.error("Incorrect password. Please try again.")

    if st.session_state.auth_index is not None and st.session_state.password_ok:
        idx = st.session_state.auth_index
        df = st.session_state.db
        student_data = df.iloc[idx]

        if st.button("🚪 Log Out"):
            st.session_state.auth_index = None
            st.session_state.password_ok = False
            st.rerun()

        st.subheader("📊 Your Performance Breakdown")

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Tut 1", f"{student_data.get('Tut 1', 0)}")
        col2.metric("Tut 2", f"{student_data.get('Tut 2', 0)}")
        col3.metric("Tut 3", f"{student_data.get('Tut 3', 0)}")
        col4.metric("Tut 4", f"{student_data.get('Tut 4', 0)}")
        col5.metric("Tut 5", f"{student_data.get('Tut 5', 0)}")

        st.metric(label="🏆 Overall Mark Progress", value=f"{student_data.get('Overall', 0)}")

        st.subheader("💬 Query a Mark")
        user_q = st.text_input("Ask your tutor a question about your marks:", value=str(student_data['question']))

        if st.button("Submit Question"):
            st.session_state.db.at[idx, 'question'] = user_q
            save_data()
            st.success("Question sent to your tutor!")
            st.rerun()

        if student_data['response']:
            st.info(f"**Tutor Response:** {student_data['response']}")

elif role == "Tutor Dashboard":
    st.header("👨‍🏫 Tutor Administration Dashboard")
    password = st.text_input("Enter Tutor Password", type="password")

    if password == "tutor123":
        st.subheader("Student Roster & Queries")
        df = st.session_state.db

        visible_cols = ["Student_Number", "Surname", "Name", "Overall", "question", "response"]
        st.dataframe(df[[c for c in visible_cols if c in df.columns]])

        students_with_questions = df[df['question'] != ""]

        if not students_with_questions.empty:
            st.subheader("Pending Student Queries")
            selected_student_id = st.selectbox("Select Student to Reply to:", students_with_questions['Student_Number'])

            s_match = df[df['Student_Number'] == selected_student_id].iloc[0]
            s_idx = df[df['Student_Number'] == selected_student_id].index[0]

            st.write(f"**{s_match['Name']} {s_match['Surname']} asked:** {s_match['question']}")
            tutor_reply = st.text_area("Your Response:", value=str(s_match['response']))

            if st.button("Send Response"):
                st.session_state.db.at[s_idx, 'response'] = tutor_reply
                save_data()
                st.success("Response updated!")
                st.rerun()
        else:
            st.write("No pending student questions.")

        st.subheader("🔑 Reset a Student's Password")
        st.caption("Use this if a student forgets their password. It clears their password so they can set a new one next time they log in.")
        reset_student_id = st.selectbox("Select Student:", df['Student_Number'], key="reset_pw_select")
        if st.button("Reset Password"):
            r_idx = df[df['Student_Number'] == reset_student_id].index[0]
            st.session_state.db.at[r_idx, 'Password'] = ""
            save_data()
            st.success(f"Password reset for {reset_student_id}. They can set a new one on their next login.")
    elif password:
        st.error("Incorrect tutor password.")
