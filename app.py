# BlueBank Customer Support — compact website redesign
# Main application logic lives here. All custom CSS is in styles.css.
# Educational demo only: no real accounts or banking transactions are connected.

import os
import re
import asyncio
from pathlib import Path
from functools import partial

import streamlit as st
from dotenv import load_dotenv
from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient


# ============================================================
# 1. App setup and secure API key loading
# ============================================================
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

st.set_page_config(
    page_title="BlueBank | Customer Care",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# 2. Session state
# ============================================================
for key, default in {
    "theme": "Light Blue",
    "page": "Home",
    "messages": [],
    "pending_question": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ============================================================
# 3. Single visual theme — midnight navy with electric blue accents
# ============================================================
C = {
    "bg": "#071426", "panel": "#101F35", "panel2": "#192F4C",
    "text": "#EDF5FF", "muted": "#A7BCD4", "accent": "#55B7FF",
    "accent2": "#245C9A", "border": "#284563", "control_bg": "#10233B",
    "control_text": "#EDF5FF", "button_bg": "#1769AA",
    "button_text": "#FFFFFF", "hero_text": "#FFFFFF",
}

# ============================================================
# 4. Load styles.css and apply the current theme
# IMPORTANT: st.html injects the CSS so it is not shown as page text.
# ============================================================
css_path = Path(__file__).resolve().parent / "styles.css"
if not css_path.exists():
    st.error("styles.css is missing. Place it beside app.py.")
    st.stop()

css = css_path.read_text(encoding="utf-8")
for name, value in C.items():
    css = css.replace(f"var(--bb-{name})", value)
st.html(f"<style>{css}</style>")

# ============================================================
# 5. Sidebar branding and single navigation menu
# Branding stays above navigation, away from Streamlit's top toolbar.
# ============================================================
# ============================================================
# 6. One navigation menu only — in the sidebar
# ============================================================
PAGES = ["Home", "AI Support", "Help Centre", "Contact Us", "Security & Privacy"]
with st.sidebar:
    st.markdown(
        """<div class="bb-sidebar-brand">
          <div class="bb-logo" aria-label="BlueBank logo"><span>BB</span></div>
          <div class="bb-wordmark">
            <div class="bb-name">BlueBank</div>
            <div class="bb-tagline">TRUST • CLARITY • CUSTOMER CARE</div>
          </div>
        </div>""",
        unsafe_allow_html=True,
    )
    st.markdown("### Navigation")
    st.session_state.page = st.radio(
        "Choose a page",
        PAGES,
        index=PAGES.index(st.session_state.page),
        format_func=lambda p: {
            "Home": "⌂  Home",
            "AI Support": "◉  AI Support",
            "Help Centre": "▤  Help Centre",
            "Contact Us": "☎  Contact Us",
            "Security & Privacy": "◇  Security & Privacy",
        }[p],
        label_visibility="collapsed",
        key="page_navigation",
    )
    st.markdown("---")
    st.caption("🔒 Never share your password, PIN or OTP.")
    st.caption("Demo only — no real banking services are connected.")
    if st.button("Clear chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()


def open_support(question=None):
    """Widget callback: runs before Streamlit rebuilds the navigation widget."""
    st.session_state.page_navigation = "AI Support"
    st.session_state.page = "AI Support"
    if question:
        st.session_state.pending_question = question


# ============================================================
# 7. Main keyword router
# It selects one department before an AutoGen agent is called.
# ============================================================
def route_question(question: str) -> str:
    text = question.lower().strip()

    # Suspected fraud or unauthorized activity must be escalated first.
    fraud_keywords = [
        "fraud", "scam", "stolen", "unauthorized", "unauthorised",
        "money missing", "someone stole", "hacked", "suspicious transaction",
        "unknown transaction", "didn't make this transaction",
        "don't recognize this transaction", "do not recognise this transaction",
    ]
    if any(word in text for word in fraud_keywords):
        return "HUMAN_SUPPORT"

    # Never perform an actual payment or money transfer.
    action_patterns = [
        r"\b(?:make|execute|initiate)\s+(?:the\s+)?(?:transfer|payment)\b",
        r"\b(?:pay|transfer|send)\s+(?:it\s+)?(?:for me|on my behalf)\b",
        r"\b(?:transfer|send)\s+(?:€|\$|£|₹)?\s*\d+(?:[.,]\d+)?\s+"
        r"(?:euros?|dollars?|pounds?|rupees?)?\s*(?:to|into)\b",
        r"\btransfer money now\b", r"\bsend money now\b",
        r"\bpay this bill for me\b", r"\bmake this payment\b",
    ]
    if any(re.search(pattern, text) for pattern in action_patterns):
        return "HUMAN_SUPPORT"

    # Loan Information includes personal, home, student, business and car loans.
    if any(word in text for word in [
        "loan", "mortgage", "emi", "repayment", "interest rate",
        "loan eligibility", "loan documents", "loan application",
    ]):
        return "LOAN"

    if any(word in text for word in [
        "card", "pin", "debit", "credit card", "atm", "declined card",
    ]):
        return "CARD"

    if any(word in text for word in [
        "transfer", "transaction", "pending payment", "payment status",
        "international payment", "exchange rate", "remittance", "send money",
        "money transfer", "payment delay", "wire transfer",
    ]):
        return "TRANSACTION"

    if any(word in text for word in [
        "account", "kyc", "savings", "current account",
        "account opening", "account fees", "bank charges",
    ]):
        return "ACCOUNT"

    return "UNCLASSIFIED"


# ============================================================
# 8. Four specialist AutoGen agents
# ============================================================
def create_specialists(client):
    return {
        "ACCOUNT": AssistantAgent(
            name="account_services_agent",
            model_client=client,
            system_message="""Answer general questions about account opening, KYC,
savings/current accounts and fees. Never invent bank-specific policies.
You cannot access or change accounts. Never request passwords, PINs or OTPs."""
        ),
        "CARD": AssistantAgent(
            name="card_support_agent",
            model_client=client,
            system_message="""Answer general debit/credit card questions, declined
payments and safe card guidance. You cannot block or replace cards or change PINs.
For lost cards, direct users to their bank's official app or published phone number.
Never request passwords, PINs or OTPs."""
        ),
        "TRANSACTION": AssistantAgent(
            name="transaction_enquiry_agent",
            model_client=client,
            system_message="""Explain general transfers, international payments, fees
and pending payment processes. You cannot access transaction records, send/cancel/
reverse money, or verify real transaction status. Do not invent current fees, rates
or processing times. Never request passwords, PINs or OTPs."""
        ),
        "LOAN": AssistantAgent(
            name="loan_information_agent",
            model_client=client,
            system_message="""Answer general questions about personal, home, student,
business and car loans, common documents, eligibility factors and repayments.
Do not guarantee approval or invent current rates. You cannot approve or submit loans.
Never request banking credentials or OTPs."""
        ),
    }


# ============================================================
# 9. Route and process the question
# ============================================================
def quick_conversation_reply(question: str):
    """Return friendly greeting/thanks responses without needing an API call."""
    text = re.sub(r"[^a-z\s']", " ", question.lower()).strip()
    text = re.sub(r"\s+", " ", text)

    greetings = {
        "hello", "hi", "hey", "hello there", "hi there", "good morning",
        "good afternoon", "good evening", "howdy",
    }
    thanks = {
        "thanks", "thank you", "thank you so much", "many thanks",
        "thanks a lot", "thx", "ty",
    }

    if text in greetings or any(text.startswith(g + " ") for g in greetings):
        return (
            "Hello and welcome to BlueBank Customer Care! 👋\n\n"
            "I'm here to help with general questions about **accounts, cards, "
            "transactions and loans**. Choose a quick question below or type "
            "what you'd like help with.\n\n"
            "For your safety, please don't share passwords, PINs, OTPs or full card numbers."
        ), "CUSTOMER CARE"
    if text in thanks or text.startswith("thank you "):
        return (
            "You're very welcome! 😊 I'm glad I could help. If you have another "
            "question about accounts, cards, transactions or loans, feel free to ask. "
            "Have a great day!"
        ), "CUSTOMER CARE"
    return None


async def process_question(question: str):
    friendly_reply = quick_conversation_reply(question)
    if friendly_reply:
        return friendly_reply

    department = route_question(question)

    # Escalation is handled without calling an LLM or performing any action.
    if department == "HUMAN_SUPPORT":
        return (
            "### Human support recommended\n\n"
            "This may involve suspected fraud, a sensitive issue, or a banking action. "
            "Contact your bank using its official app or published phone number. "
            "Report suspected fraud immediately. This demo cannot move money, investigate "
            "fraud, or change accounts. Never share your password, PIN or OTP."
        ), department

    if department == "UNCLASSIFIED":
        return (
            "I couldn't identify the right department. Please ask about an account, "
            "card, transaction or loan. You can also contact your bank through an official channel."
        ), department

    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing from your .env file.")

    # Each request gets its own client; close it before the event loop ends.
    client = OpenAIChatCompletionClient(model="gpt-4o-mini",api_key=OPENAI_API_KEY)
    try:
        agents = create_specialists(client)
        result = await agents[department].run(task=question)
        if not getattr(result, "messages", None):
            raise RuntimeError("The AI agent returned an empty response.")
        content = result.messages[-1].content
        if isinstance(content, list):
            # Some model responses return a list of text/content blocks.
            parts = []
            for item in content:
                value = getattr(item, "text", None)
                parts.append(str(value if value is not None else item))
            content = "\n".join(parts)
        return str(content), department
    finally:
        await client.close()


# ============================================================
# 10. HOME PAGE — compact cards, no repeated navigation
# ============================================================
if st.session_state.page == "Home":
    st.markdown(
        """
        <section class="bb-hero">
          <div class="bb-eyebrow">BLUEBANK DIGITAL CARE</div>
          <h1>How can we help you today?</h1>
          <p>Friendly guidance for everyday banking — all in one place.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    # One clear support call-to-action instead of multiple repeated menus.
    left, right = st.columns([1.6, 1], gap="medium")
    with left:
        st.markdown(
            """
            <section class="bb-support-panel">
              <div class="bb-support-icon">✦</div>
              <div>
                <h3>Ask BlueBank Support</h3>
                <p>Get help with accounts, cards, transactions or loans.</p>
              </div>
            </section>
            """,
            unsafe_allow_html=True,
        )
        st.button("Start a conversation  →", type="primary",
                  use_container_width=True, on_click=open_support)

    with right:
        st.markdown(
            """
            <section class="bb-safety-panel">
              <div class="bb-safety-title">🔒 Your security matters</div>
              <p>Never share your PIN, password, OTP or full card number.</p>
              <span>BlueBank is a demo project.</span>
            </section>
            """,
            unsafe_allow_html=True,
        )

    st.markdown('<div class="bb-section-title">Explore our services</div>',
                unsafe_allow_html=True)

    services = [
        ("♧", "Accounts", "Opening, KYC and account fees.",
         "What documents do I need to open an account?"),
        ("▣", "Cards", "Card issues and declined payments.",
         "My debit card payment was declined."),
        ("⇄", "Transactions", "Transfer processes and payment guidance.",
         "How do international transfers work?"),
        ("◇", "Loan Information", "Personal, home and other loan guidance.",
         "I would like information about a loan."),
    ]
    # Two compact rows of service links instead of oversized cards.
    for row_start in (0, 2):
        cols = st.columns(2, gap="small")
        for col, service in zip(cols, services[row_start:row_start + 2]):
            icon, title, description, prompt = service
            with col:
                st.markdown(
                    f'<div class="bb-service"><span class="bb-service-icon">{icon}</span>'
                    f'<div><b>{title}</b><p>{description}</p></div>'
                    f'<span class="bb-service-arrow">↗</span></div>',
                    unsafe_allow_html=True,
                )
                st.button(f"Ask about {title}", key=f"service_{title}",
                          use_container_width=True,
                          on_click=partial(open_support, prompt))


# ============================================================
# 11. AI SUPPORT PAGE
# ============================================================
elif st.session_state.page == "AI Support":
    st.markdown('<div class="bb-page-title">AI Customer Support</div>',
                unsafe_allow_html=True)
    st.markdown(
        '<p class="bb-page-subtitle">A keyword-based Main Router sends each question '
        'to one relevant department agent.</p>',
        unsafe_allow_html=True,
    )
    st.info("Demo only. Never enter passwords, PINs, OTPs or full card numbers.")

    st.markdown("**Quick questions**")
    quick_questions = [
        ("Account", "What documents are needed to open an account?"),
        ("Card", "My debit card payment was declined."),
        ("Transaction", "How do international transfers work?"),
        ("Loan", "I would like information about a loan."),
    ]
    quick_cols = st.columns(4, gap="small")
    for col, (label, prompt) in zip(quick_cols, quick_questions):
        with col:
            if st.button(label, key=f"quick_{label}", use_container_width=True):
                st.session_state.pending_question = prompt
                st.rerun()

    # Render previous conversation messages.
    for message in st.session_state.messages:
        avatar = "🧑" if message["role"] == "user" else "🏦"
        with st.chat_message(message["role"], avatar=avatar):
            st.markdown(message["content"])
            if message.get("department"):
                st.caption(f"Department: {message['department']}")

    typed = st.chat_input("Type your banking question...")
    question = st.session_state.pending_question
    st.session_state.pending_question = None
    if typed:
        question = typed

    if question:
        st.session_state.messages.append(
            {"role": "user", "content": question, "department": None}
        )
        with st.chat_message("user", avatar="🧑"):
            st.markdown(question)

        friendly_reply = quick_conversation_reply(question)
        department = "CUSTOMER CARE" if friendly_reply else route_question(question)
        with st.chat_message("assistant", avatar="🏦"):
            st.caption(f"Main Router → {department}")
            try:
                with st.spinner("Preparing your answer..."):
                    answer, department = asyncio.run(process_question(question))
                st.markdown(answer)
                st.caption(f"Answered by: {department}")
                st.session_state.messages.append({
                    "role": "assistant", "content": answer, "department": department,
                })
            except Exception as exc:
                import traceback
                traceback.print_exc()
                st.error(
                    f"The support request failed ({type(exc).__name__}): {exc}"
                )
                st.caption("Check that OPENAI_API_KEY is set in .env and that the API account has access to the configured model.")
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": "Sorry, I couldn't process that request. Please try again later.",
                    "department": "ERROR",
                })

    if st.session_state.messages and st.button("Clear conversation"):
        st.session_state.messages = []
        st.rerun()


# ============================================================
# 12. HELP CENTRE
# ============================================================
elif st.session_state.page == "Help Centre":
    st.markdown('<div class="bb-page-title">Help Centre</div>',
                unsafe_allow_html=True)
    st.markdown('<p class="bb-page-subtitle">Quick answers to common banking questions.</p>',
                unsafe_allow_html=True)
    faqs = [
        ("Account opening and KYC",
         "Banks commonly request identity documents and may ask for proof of address or tax details. "
         "Check your bank's official website for exact requirements."),
        ("Card declined or lost",
         "Check the card status and payment details. For a lost card, contact your bank immediately "
         "through its official app or published phone number."),
        ("International transactions",
         "Fees, exchange rates, recipient details and timing vary by provider. Verify details with "
         "your official bank or transfer provider."),
        ("Loan information",
         "Lenders may review identity, income, credit history and other details. Exact requirements, "
         "rates and approval depend on the lender."),
        ("Suspected fraud",
         "Contact your bank immediately through its official app or published phone number. Never "
         "share your password, PIN or OTP."),
    ]
    for question, answer in faqs:
        with st.expander(question):
            st.write(answer)
    st.button("Ask the AI assistant", type="primary", on_click=open_support)


# ============================================================
# 13. CONTACT US
# Replace the placeholders with verified details for any real deployment.
# ============================================================
elif st.session_state.page == "Contact Us":
    st.markdown('<div class="bb-page-title">Contact BlueBank</div>',
                unsafe_allow_html=True)
    st.markdown('<p class="bb-page-subtitle">Contact details below are placeholders for this demo.</p>',
                unsafe_allow_html=True)

    col1, col2 = st.columns(2, gap="small")
    with col1:
        st.markdown(
            '<div class="bb-contact"><b>☎ Customer Care</b>'
            '<p>Phone: [Add official phone number]</p>'
            '<p>Hours: [Add verified support hours]</p></div>',
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            '<div class="bb-contact"><b>✉ Email Support</b>'
            '<p>Email: [Add official support email]</p>'
            '<p>Never send passwords, PINs or OTPs.</p></div>',
            unsafe_allow_html=True,
        )

    st.markdown("**Send a demo enquiry**")
    st.caption("This form does not send an email or create a support ticket.")
    with st.form("contact_demo"):
        st.text_input("Name (optional)")
        st.text_input("Email (optional)")
        topic = st.selectbox(
            "Topic",
            ["Account Services", "Card Support", "Transaction Enquiry",
             "Loan Information", "Website Feedback"],
        )
        message = st.text_area("Message", placeholder="Do not include sensitive financial details.")
        submitted = st.form_submit_button("Submit demo enquiry")
    if submitted:
        if not message.strip():
            st.warning("Please enter a message.")
        else:
            st.success(f"Demo enquiry received on screen for {topic}; nothing was sent.")


# ============================================================
# 14. SECURITY & PRIVACY
# ============================================================
elif st.session_state.page == "Security & Privacy":
    st.markdown('<div class="bb-page-title">Security & Privacy</div>',
                unsafe_allow_html=True)
    st.markdown(
        '<div class="bb-safety-panel"><b>BlueBank is a fictional demonstration app.</b>'
        '<p>It is not connected to a real bank and cannot view or change accounts.</p></div>',
        unsafe_allow_html=True,
    )
    st.markdown("### What the chatbot can do")
    st.markdown(
        "- Answer general account, card, transaction and loan questions.\n"
        "- Route a question to one specialist agent.\n"
        "- Recommend official human support for suspected fraud or sensitive requests."
    )
    st.markdown("### What the chatbot cannot do")
    st.markdown(
        "- Send, receive, cancel or reverse money.\n"
        "- Read balances or transaction histories.\n"
        "- Block cards, change PINs, or approve loans."
    )
    st.markdown("### Protect your information")
    st.markdown(
        "- Never enter passwords, PINs, OTPs, full card numbers or account secrets.\n"
        "- Use official bank apps, websites and phone numbers.\n"
        "- Report suspected fraud to your bank immediately."
    )
    st.markdown("### Demo privacy")
    st.write(
        "Messages remain in Streamlit session state while the session is active. "
        "Questions sent to the configured model provider are processed by that provider. "
        "Do not enter personal or financial secrets, and review the provider's current "
        "privacy and data-retention terms before using the app."
    )


# ============================================================
# 15. Compact shared footer
# ============================================================
st.markdown(
    """
    <footer class="bb-footer">
      <b>BB&nbsp; BlueBank</b><span>Customer Care Demo</span>
      <small>Educational project only · Not a real financial institution · No real transactions</small>
    </footer>
    """,
    unsafe_allow_html=True,
)
