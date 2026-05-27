import os
import json
import sqlite3
import re
import resend
from datetime import datetime, timedelta
import gradio as gr
import requests

# =========================================================
# PROFESSIONAL CLEANING SERVICES AI BOOKING AGENT
# =========================================================

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")

EMAIL_ADDRESS = "mr.sandeepmcscet@gmail.com"

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_EMAIL = os.getenv("SMTP_EMAIL", EMAIL_ADDRESS)
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")

ADMIN_EMAIL = EMAIL_ADDRESS

# =========================================================
# DATABASE
# =========================================================

DB_NAME = "/tmp/cleaning_bookings.db"


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Fresh clean table without booking_time
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service TEXT,
            city TEXT,
            category TEXT,
            addons TEXT,
            booking_date TEXT,
            customer_name TEXT,
            customer_phone TEXT,
            customer_email TEXT,
            customer_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.commit()
    conn.close()


init_db()

# =========================================================
# DATA
# =========================================================

SERVICES = [
    "End of Lease Cleaning",
    "Window Cleaning",
    "Oven Cleaning",
    "Carpet Steam Cleaning",
    "Bond Cleaning",
    "Upholstery Cleaning",
    "Domestic Cleaning",
    "BBQ Cleaning",
    "Spring Cleaning",
    "Move In Cleaning",
    "Office Cleaning",
    "Pest Control Free Quote",
    "Construction Cleaning",
    "Airbnb / Short-Stay Cleaning",
]

AUSTRALIA_CITIES = [
    "Sydney",
    "Melbourne",
    "Brisbane",
    "Perth",
    "Adelaide",
    "Gold Coast",
    "Canberra",
]

PROPERTY_CATEGORIES = [
    "Studio",
    "1 Bedroom 1 Bathroom",
    "2 Bedroom 1 Bathroom",
    "2 Bedroom 2 Bathroom",
    "3 Bedroom 1 Bathroom",
    "3 Bedroom 2 Bathroom",
    "4 Bedroom 2 Bathroom",
    "Office / Commercial",
    "Airbnb Property",
]

ADDON_SERVICES = {
    "End of Lease Cleaning": [
        "Wall Spot Cleaning",
        "Balcony Wash",
        "Garage Cleaning",
        "Steam Carpet Cleaning",
    ],
    "Window Cleaning": [
        "Interior Windows",
        "Exterior Windows",
        "Tracks & Frames",
    ],
    "Office Cleaning": [
        "Desk Sanitisation",
        "Waste Removal",
        "Night Shift Cleaning",
    ],
}

DEFAULT_ADDONS = [
    "Eco Friendly Products",
    "Same Day Service",
    "Deep Sanitisation",
]

# =========================================================
# AI FUNCTIONS
# =========================================================


def search_cleaning_trends(service, city):

    if not SERPER_API_KEY:
        return "Serper API not configured."

    try:
        url = "https://google.serper.dev/search"

        payload = {
            "q": f"best {service} services in {city} Australia customer expectations"
        }

        headers = {
            "X-API-KEY": SERPER_API_KEY,
            "Content-Type": "application/json",
        }

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=20,
        )

        data = response.json()

        snippets = []

        for item in data.get("organic", [])[:5]:
            snippets.append(item.get("snippet", ""))

        return "\n".join(snippets)

    except Exception as e:
        return f"Search error: {str(e)}"


def generate_ai_summary(service, city, category, addons):
    """Generate intelligent booking summary using DeepSeek"""
    print("Generating AI summary...")
    addons_text = ", ".join(addons) if addons else "No add-ons selected"

    market_context = search_cleaning_trends(service, city)

    # Fallback if API key missing
    if not DEEPSEEK_API_KEY:
        return f"""
## 🤖 AI Booking Summary

### Service Details
- **Service:** {service}
- **City:** {city}
- **Property Type:** {category}
- **Add-ons:** {addons_text}

---

### Estimated Cleaning Information
- ⏱ Estimated Duration: 3–5 Hours
- 👥 Recommended Team Size: 2 Cleaners
- ⭐ Priority Level: High

---

### Preparation Tips
- Please ensure property access is available.
- Remove valuable or fragile items before service.
- Secure pets if required.

---

### Recommendation
Eco-friendly deep sanitisation is highly recommended for premium results.
"""

    try:
        url = "https://api.deepseek.com/chat/completions"

        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        }

        prompt = f"""
You are an AI cleaning consultant.

Customer Booking:
- Service: {service}
- City: {city}
- Property Type: {category}
- Addons: {addons_text}

Market Research:
{market_context}

Create:
1. Professional summary
2. Estimated cleaning duration
3. Recommended cleaning crew size
4. Cleaning checklist highlights
5. Customer preparation tips
6. Premium recommendation

Use beautiful markdown formatting.
"""

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a luxury cleaning service AI assistant.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "temperature": 0.7,
            "max_tokens": 700,
        }

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=60,
        )

        # Prevent Railway crash
        if response.status_code != 200:
            return f"""
## ⚠️ AI Service Temporarily Unavailable

Booking was still created successfully.

### Booking Details
- Service: {service}
- City: {city}
- Property Type: {category}
- Add-ons: {addons_text}

Please try again later for AI recommendations.
"""

        data = response.json()

        # Extra protection
        if "choices" not in data:
            return f"""
## ⚠️ AI Summary Currently Unavailable

Your booking has been received successfully.

### Service
- {service}
- {city}
- {category}
"""

        return data["choices"][0]["message"]["content"]

    except Exception as e:
        return f"""
## ⚠️ AI Generation Error

Your booking was successfully processed.

### Error
{str(e)}

### Booking Details
- Service: {service}
- City: {city}
- Property Type: {category}
- Add-ons: {addons_text}
"""
# =========================================================
# HELPERS
# =========================================================


def load_addons(service):

    addons = ADDON_SERVICES.get(service, DEFAULT_ADDONS)

    return gr.update(
        choices=addons,
        value=[],
    )


def validate_phone(phone):

    cleaned = re.sub(r"[^0-9+]", "", phone)

    patterns = [
        r"^\+61[0-9]{9}$",
        r"^0[0-9]{9}$",
        r"^\+[1-9][0-9]{7,14}$",
    ]

    for pattern in patterns:
        if re.match(pattern, cleaned):
            return True

    return False


def format_booking_date(date_value):

    try:

        if isinstance(date_value, (int, float)):
            dt = datetime.fromtimestamp(date_value)

        elif isinstance(date_value, str):

            try:
                dt = datetime.fromisoformat(date_value)

            except:
                dt = datetime.fromtimestamp(float(date_value))

        else:
            dt = date_value

        return dt.strftime("%A, %d %B %Y • %I:%M %p")

    except Exception:
        return str(date_value)


# =========================================================
# DATABASE SAVE
# =========================================================


def save_booking_to_db(
    service,
    city,
    category,
    addons,
    date,
    name,
    phone,
    email,
    notes,
):

    conn = sqlite3.connect(DB_NAME)

    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO bookings (
            service,
            city,
            category,
            addons,
            booking_date,
            customer_name,
            customer_phone,
            customer_email,
            customer_notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            service,
            city,
            category,
            json.dumps(addons),
            str(date),
            name,
            phone,
            email,
            notes,
        ),
    )

    booking_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return booking_id


# =========================================================
# EMAIL
# =========================================================


RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")

resend.api_key = RESEND_API_KEY


def send_booking_email(
    service,
    city,
    category,
    addons,
    date,
    name,
    phone,
    email,
    notes,
):

    try:

        addons_text = ", ".join(addons) if addons else "No add-ons selected"

        formatted_date = format_booking_date(date)

        customer_html = f"""
        <div style="font-family:Arial;padding:20px;">
            <h2>✨ Booking Confirmed</h2>

            <p>Hello <b>{name}</b>,</p>

            <p>Your cleaning booking has been received successfully.</p>

            <h3>Booking Details</h3>

            <ul>
                <li><b>Service:</b> {service}</li>
                <li><b>City:</b> {city}</li>
                <li><b>Category:</b> {category}</li>
                <li><b>Add-ons:</b> {addons_text}</li>
                <li><b>Date:</b> {formatted_date}</li>
            </ul>

            <p>Our team will contact you shortly.</p>

            <p>Thank you for choosing us.</p>
        </div>
        """

        admin_html = f"""
        <div style="font-family:Arial;padding:20px;">
            <h2>🧼 New Cleaning Booking</h2>

            <ul>
                <li><b>Name:</b> {name}</li>
                <li><b>Phone:</b> {phone}</li>
                <li><b>Email:</b> {email}</li>
                <li><b>Service:</b> {service}</li>
                <li><b>City:</b> {city}</li>
                <li><b>Category:</b> {category}</li>
                <li><b>Add-ons:</b> {addons_text}</li>
                <li><b>Date:</b> {formatted_date}</li>
                <li><b>Notes:</b> {notes}</li>
            </ul>
        </div>
        """

        # Customer Email
        resend.Emails.send({
            "from": "Cleaning Service <onboarding@resend.dev>",
            "to": [email],
            "subject": "✨ Your Booking is Confirmed",
            "html": customer_html,
        })

        # Admin Email
        resend.Emails.send({
            "from": "Cleaning Service <onboarding@resend.dev>",
            "to": ["mr.sandeepmcscet@gmail.com"],
            "subject": f"🧼 New Booking from {name}",
            "html": admin_html,
        })

        return "✅ Emails sent successfully"

    except Exception as e:
        return f"❌ Email error: {str(e)}"


# =========================================================
# BOOKING SUMMARY
# =========================================================


def create_booking_summary(
    service,
    city,
    category,
    addons,
    date,
    name,
    phone,
    email,
    notes,
):

    if not name.strip():
        return "❌ Please enter your name"

    if not email.strip() or "@" not in email:
        return "❌ Please enter valid email"

    if not validate_phone(phone):
        return "❌ Invalid phone number"

    formatted_date = format_booking_date(date)

    addons_text = ", ".join(addons) if addons else "No add-ons"
    print("Generating AI summary...")
    ai_response = generate_ai_summary(
        service,
        city,
        category,
        addons,
    )
    print("Saving booking...")
    booking_id = save_booking_to_db(
        service,
        city,
        category,
        addons,
        date,
        name,
        phone,
        email,
        notes,
    )
    print("Sending email...")
    email_status = send_booking_email(
        service,
        city,
        category,
        addons,
        date,
        name,
        phone,
        email,
        notes,
    )
    print("Email sent...")
    return f"""
# ✨ Booking Confirmed

## 🆔 Booking ID: #{booking_id}

| Details | Value |
|---|---|
| Service | {service} |
| City | {city} |
| Property | {category} |
| Add-ons | {addons_text} |
| Preferred Service Date | {formatted_date} |
| Customer | {name} |
| Phone | {phone} |
| Email | {email} |

---

{ai_response}

---

## 📧 Email Status

{email_status}
"""


# =========================================================
# CSS
# =========================================================

CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

*{
    font-family: 'Inter', sans-serif;
}



/* FIX DROPDOWN */

.gradio-container,
.gr-block,
.gr-box,
.gr-form,
.gr-group,
.gr-panel{
    overflow: visible !important;
}

.gr-dropdown{
    position: relative !important;
    z-index: 99999 !important;
}

.gr-dropdown ul{
    z-index: 999999 !important;
    background:#0f2f4d !important;
    border-radius:16px !important;
    border:1px solid rgba(255,255,255,0.1) !important;
    max-height:300px !important;
}

.gr-dropdown li{
    color:white !important;
    padding:12px !important;
}

.gr-dropdown li:hover{
    background:#00b4ff !important;
}

.gr-button-primary{
    background:linear-gradient(135deg,#00b4ff,#0077ff)!important;
}
h1,h2,h3,h4,h5,h6{
    color:black!important;
}
/* Hide Gradio Footer */

footer {
    display: none !important;
}

/* Hide "Built with Gradio" */

.gradio-container footer {
    display: none !important;
}

/* Hide bottom navigation */

footer.svelte-1ipelgc {
    display: none !important;
}
/* =========================================
   LOADING ANIMATION
========================================= */

.generate-loader {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;

    color: white;
    font-size: 18px;
    font-weight: 600;

    margin-top: 20px;
}

.loader-spinner {
    width: 22px;
    height: 22px;

    border: 3px solid rgba(255,255,255,0.2);
    border-top: 3px solid #00b4ff;

    border-radius: 50%;

    animation: spin 1s linear infinite;
}

@keyframes spin {
    100% {
        transform: rotate(360deg);
    }
}
"""

# =========================================================
# UI
# =========================================================

with gr.Blocks(
    analytics_enabled=False,
) as demo:

    demo.queue()
    VISITOR_FILE = "visitor_count.txt"
    
    def get_visitor_count():
        if not os.path.exists(VISITOR_FILE):
            with open(VISITOR_FILE, "w") as f:
                f.write("0")

        with open(VISITOR_FILE, "r") as f:
            count = int(f.read())

        return count


def increment_visitor_count():

    count = get_visitor_count() + 1

    with open(VISITOR_FILE, "w") as f:
        f.write(str(count))

    return count
    visitor_count = increment_visitor_count()
    gr.HTML(
    f"""
    <div class='main-card'>
        <div class='hero-title'>🧼 Professional Cleaning Services</div>

        <div class='hero-sub'>
        AI Powered Booking Agent • DeepSeek Intelligence • Smart Scheduling
        <br><br>
        👀 Total Visitors: <b>{visitor_count}</b>
        </div>
    """
)

    # STEP 1

    with gr.Group():

        service_dropdown = gr.Dropdown(
            label="1️⃣ Please Select Service",
            choices=SERVICES,
            value="End of Lease Cleaning",
            interactive=True,
        )

        city_dropdown = gr.Dropdown(
            label="2️⃣ Select Your City",
            choices=AUSTRALIA_CITIES,
            value="Sydney",
            interactive=True,
        )

        property_dropdown = gr.Dropdown(
            label="3️⃣ Select Property Category",
            choices=PROPERTY_CATEGORIES,
            value="2 Bedroom 1 Bathroom",
            interactive=True,
        )

    # STEP 2

    addon_checkbox = gr.CheckboxGroup(
        label="Additional Services",
        choices=ADDON_SERVICES["End of Lease Cleaning"],
        value=[],
        interactive=True,
    )

    # STEP 3

    booking_date = gr.DateTime(
        label="📅 Preferred Service Date",
        value=datetime.now() + timedelta(days=1),
    )

    # STEP 4

    customer_name = gr.Textbox(
        label="👤 Full Name",
        placeholder="Enter your full name",
    )

    customer_phone = gr.Textbox(
        label="📞 Phone Number",
        placeholder="+61412345678",
    )

    customer_email = gr.Textbox(
        label="📧 Email Address",
        placeholder="your@email.com",
    )

    customer_notes = gr.TextArea(
        label="📝 Additional Notes",
        placeholder="Parking info, pets, stains etc.",
        lines=4,
    )

    # BUTTONS

    with gr.Row():

        generate_btn = gr.Button(
            "✨ Generate AI Booking Summary",
            variant="primary",
        )

        clear_btn = gr.Button("🧹 Clear Form")
    loading_html = gr.HTML(visible=False)
    output = gr.Markdown()

    # EVENTS

    service_dropdown.change(
        fn=load_addons,
        inputs=service_dropdown,
        outputs=addon_checkbox,
    )

    def show_loader():
        return gr.update(
            value="""
            <div class="generate-loader">
                <div class="loader-spinner"></div>
                Generating AI Cleaning Summary...
            </div>
            """,
            visible=True,
        )


    def hide_loader():
        return gr.update(visible=False)


    generate_btn.click(
        fn=show_loader,
        outputs=loading_html,
    ).then(
        fn=create_booking_summary,
        inputs=[
            service_dropdown,
            city_dropdown,
            property_dropdown,
            addon_checkbox,
            booking_date,
            customer_name,
            customer_phone,
            customer_email,
            customer_notes,
        ],
        outputs=output,
    ).then(
        fn=hide_loader,
        outputs=loading_html,
    )

    clear_btn.click(
        lambda: (
            "End of Lease Cleaning",
            "Sydney",
            "2 Bedroom 1 Bathroom",
            [],
            datetime.now() + timedelta(days=1),
            "",
            "",
            "",
            "",
            "",
        ),
        outputs=[
            service_dropdown,
            city_dropdown,
            property_dropdown,
            addon_checkbox,
            booking_date,
            customer_name,
            customer_phone,
            customer_email,
            customer_notes,
            output,
        ],
    )

# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 7860))

demo.launch(
    favicon_path=None,
    server_name="0.0.0.0",
    server_port=int(os.environ.get("PORT", 7860)),
    share=False,
    show_error=True,
    theme=gr.themes.Glass(
        primary_hue="cyan",
        secondary_hue="blue",
        neutral_hue="slate",
        radius_size="lg"
    ),
    css=CUSTOM_CSS,
)