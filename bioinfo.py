import streamlit as st
import requests
import json
import bcrypt
import google.generativeai as genai
from streamlit_option_menu import option_menu
import streamlit_authenticator as stauth
import time

# ==============================
# CONFIGURATION
# ==============================
st.set_page_config(page_title="🧬 BioAI Explorer", page_icon="🧬", layout="wide")

genai_key = None
try:
    # safe access (st.secrets raises if no valid TOML found)
    if "api" in st.secrets and "gemini_key" in st.secrets["api"]:
        genai_key = st.secrets["api"]["gemini_key"]
        st.info(f"Gemini key found — length={len(genai_key)}; masked={genai_key[:4]}...{genai_key[-4:]}")
        try:
            genai.configure(api_key=genai_key)
            st.success("genai.configure succeeded (key loaded).")
        except Exception as e:
            st.error("Failed to configure Gemini client: " + str(e))
            genai_key = None
    else:
        st.warning("Gemini API key not present in st.secrets.")
except Exception as e:
    st.warning("Could not read secrets.toml: " + str(e))
    genai_key = None

# ==============================
# LOAD OR INITIALIZE USER DATA
# ==============================
def load_users():
    try:
        with open("users.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_users(users):
    with open("users.json", "w") as f:
        json.dump(users, f)

users = load_users()

# ==============================
# SIGNUP FUNCTION
# ==============================
def signup(email, password):
    if email in users:
        return False, "User already exists!"
    hashed_pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    users[email] = hashed_pw
    save_users(users)
    return True, "Account created successfully!"

# ==============================
# LOGIN FUNCTION
# ==============================
def login(email, password):
    if email not in users:
        return False, "No account found!"
    stored_hash = users[email].encode()
    if bcrypt.checkpw(password.encode(), stored_hash):
        return True, "Login successful!"
    return False, "Invalid password!"

# ==============================
# AUTH SECTION
# ==============================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user = None

if not st.session_state.logged_in:
    st.title("🧬 BioAI Explorer Login Portal")

    tab1, tab2 = st.tabs(["🔑 Login", "🧾 Sign Up"])

    with tab1:
        email = st.text_input("📧 Email", key="login_email")
        password = st.text_input("🔒 Password", type="password", key="login_pw")
        if st.button("Login"):
            success, msg = login(email, password)
            if success:
                st.session_state.logged_in = True
                st.session_state.user = email
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    with tab2:
        new_email = st.text_input("📨 Create Email", key="signup_email")
        new_password = st.text_input("🔐 Create Password", type="password", key="signup_pw")
        if st.button("Sign Up"):
            success, msg = signup(new_email, new_password)
            if success:
                st.success(msg)
            else:
                st.error(msg)

else:
    # ==============================
    # MAIN DASHBOARD
    # ==============================
    with st.sidebar:
        st.image("https://upload.wikimedia.org/wikipedia/commons/1/1e/Protein_structure.png", use_container_width=True)
        st.title(f"Welcome, {st.session_state.user.split('@')[0].capitalize()} 👋")
        choice = option_menu(
            "Navigation",
            ["Home", "Protein Explorer", "AI Assistant", "Logout"],
            icons=["house", "dna", "robot", "box-arrow-right"],
            menu_icon="cast",
            default_index=0,
        )

    if choice == "Home":
        st.title("🧬 BioAI Explorer")
        st.markdown("""
        Welcome to **BioAI Explorer** — your smart AI companion for bioinformatics exploration.

        🔹 **Search Proteins** from UniProt  
        🔹 **Ask AI** about biological terms or drug/herbal insights  
        🔹 **Visualize** sequences, IDs, and functions  

        ---
        """)

    elif choice == "Protein Explorer":
        st.header("🔍 Explore Protein Data from UniProt")
        protein_id = st.text_input("Enter a UniProt ID (e.g., P69905 for Hemoglobin alpha):", key="protein_id")
        if st.button("Fetch Data", key="fetch_uniprot"):
            if not protein_id:
                st.warning("Please enter a UniProt ID.")
            else:
                def fetch_uniprot_json(protein_id, retries=3, timeout=15):
                    session = requests.Session()
                    url = f"https://rest.uniprot.org/uniprotkb/{protein_id}.json"
                    backoff = 1
                    for attempt in range(1, retries + 1):
                        try:
                            resp = session.get(url, timeout=timeout)
                            resp.raise_for_status()
                            return resp.json()
                        except requests.exceptions.Timeout:
                            if attempt == retries:
                                raise
                            time.sleep(backoff)
                            backoff *= 2
                        except requests.exceptions.HTTPError as e:
                            # return None for 404 (not found) so caller can show a friendly message
                            if resp.status_code == 404:
                                return None
                            raise
                        except requests.exceptions.RequestException:
                            if attempt == retries:
                                raise
                            time.sleep(backoff)
                            backoff *= 2

                try:
                    data = fetch_uniprot_json(protein_id, retries=3, timeout=15)
                except requests.exceptions.Timeout:
                    st.error("UniProt request timed out after multiple attempts. Try again or increase timeout.")
                except Exception as e:
                    st.error(f"Request failed: {e}")
                else:
                    if not data:
                        st.error("Protein not found (404). Check the UniProt ID.")
                    else:
                        # safe nested extraction
                        protein_name = (data.get("proteinDescription", {}) \
                                           .get("recommendedName", {}) \
                                           .get("fullName", {}) \
                                           .get("value")) or "Name not available"
                        organism = (data.get("organism", {}) \
                                        .get("scientificName")) or "Organism not available"
                        seq = (data.get("sequence", {}) \
                                  .get("value"))
                        length = (data.get("sequence", {}) \
                                    .get("length")) or (len(seq) if seq else "N/A")
                        preview = (seq[:300] + "...") if seq and len(seq) > 300 else (seq or "Sequence not available")
                        st.subheader("Protein Information:")
                        st.json({
                            "Protein Name": protein_name,
                            "Organism": organism,
                            "Length": length,
                            "Sequence (preview)": preview,
                            "Raw JSON (partial)": {k: data.get(k) for k in ("accession", "dbReferences", "comments") if k in data}
                        })

    elif choice == "AI Assistant":
        st.header("🤖 BioAI Chat Assistant")
        query = st.text_area("Ask anything about bioinformatics, herbs, or proteins:", key="ai_query")
        if st.button("Ask AI", key="ask_ai"):
            if not query or not query.strip():
                st.warning("Please enter a question.")
            elif not genai_key:
                st.error("Gemini API key not configured.")
            else:
                def call_genai_model(prompt, model="models/text-bison-001"):
                    """Try several common call patterns for the google.generativeai package."""
                    errors = []
                    # pattern A: genai.generate_text(...)
                    if hasattr(genai, "generate_text"):
                        try:
                            return genai.generate_text(model=model, prompt=prompt)
                        except Exception as e:
                            errors.append(f"generate_text: {e}")
                    # pattern B: genai.generate(...)
                    if hasattr(genai, "generate"):
                        try:
                            return genai.generate(model=model, prompt=prompt)
                        except Exception as e:
                            errors.append(f"generate: {e}")
                    # pattern C: genai.models.generate(...)
                    models_ns = getattr(genai, "models", None)
                    if models_ns and hasattr(models_ns, "generate"):
                        try:
                            return models_ns.generate(model=model, input=prompt)
                        except Exception as e:
                            errors.append(f"models.generate: {e}")
                    # pattern D: client class instance (Client or GenerativeAIClient)
                    for cls_name in ("Client", "GenerativeAIClient"):
                        cls = getattr(genai, cls_name, None)
                        if cls:
                            try:
                                instance = cls(api_key=genai_key) if callable(cls) else cls()
                                if hasattr(instance, "generate_text"):
                                    return instance.generate_text(model=model, prompt=prompt)
                                if hasattr(instance, "generate"):
                                    return instance.generate(model=model, prompt=prompt)
                            except Exception as e:
                                errors.append(f"{cls_name}: {e}")
                    raise Exception("No supported generate method found. Tried: " + " | ".join(errors))

                def extract_text_from_response(resp):
                    """Normalize common response shapes to a text string."""
                    if resp is None:
                        return None
                    # object with attribute 'text' or 'output'
                    if hasattr(resp, "text"):
                        return getattr(resp, "text")
                    if hasattr(resp, "output"):
                        return getattr(resp, "output")
                    # dict-like shapes
                    if isinstance(resp, dict):
                        if "output" in resp and isinstance(resp["output"], str):
                            return resp["output"]
                        if "text" in resp and isinstance(resp["text"], str):
                            return resp["text"]
                        # candidates list (common in some SDKs)
                        candidates = resp.get("candidates") or resp.get("outputs")
                        if isinstance(candidates, list) and candidates:
                            first = candidates[0]
                            if isinstance(first, dict):
                                return first.get("content") or first.get("text") or first.get("output")
                            if isinstance(first, str):
                                return first
                    # some SDKs return a nested dict under 'response' or 'result'
                    for key in ("response", "result"):
                        if isinstance(resp, dict) and key in resp and isinstance(resp[key], dict):
                            return extract_text_from_response(resp[key])
                    return None

                try:
                    resp = call_genai_model(query, model="models/text-bison-001")
                    text = extract_text_from_response(resp)
                    if text:
                        st.write(text)
                    else:
                        st.warning("No text returned from model. Raw response:")
                        st.write(resp)
                except Exception as e:
                    msg = str(e)
                    # detect model-not-found vs no-generate-method
                    if "model not found" in msg.lower() or "not found" in msg.lower():
                        st.error("AI call failed: model not available for this API/version. Try a supported model ID.")
                    elif "no supported generate method" in msg.lower():
                        st.error("AI SDK mismatch: the installed google.generativeai package does not expose a known generate method.")
                        st.info("Update the package or consult its docs. For now, you can try installing a compatible client version.")
                    else:
                        st.error(f"AI call failed: {e}")
                    st.exception(e)

    elif choice == "Logout":
        st.session_state.logged_in = False
        st.session_state.user = None
        st.success("You have been logged out successfully!")
        st.rerun()
