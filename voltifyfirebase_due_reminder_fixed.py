# MainCode_firebase.py
import datetime
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from twilio.rest import Client
import socket
import random
import firebase_admin
from firebase_admin import credentials, firestore

# =========================
# CONFIG - service account
# =========================
SERVICE_ACCOUNT_FILE = "voltify-bb595-firebase-adminsdk-fbsvc-d0987e12f8.json"

# ================================================================
# ✉ NOTIFICATION FUNCTION (unchanged)
# ================================================================
def notify_user(user_identifier, ip_address, contact=None, mode="email"):
    """
    Sends alert or OTP via email or SMS.
    Note: Update sender credentials and Twilio credentials to real ones.
    """
    try:
        if mode == "email":
            sender_email = "yourvoltifyalerts@gmail.com"  # <-- change this
            sender_pass = "your-app-password"            # <-- change this
            receiver_email = contact

            msg = MIMEMultipart("alternative")
            msg["Subject"] = "Voltify Security Notification"
            msg["From"] = sender_email
            msg["To"] = receiver_email
            msg.attach(MIMEText(ip_address, "plain"))

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(sender_email, sender_pass)
                server.sendmail(sender_email, receiver_email, msg.as_string())

            print(f"📧 Email sent to {receiver_email}")

        elif mode == "sms":
            account_sid = "AC151308604fc43d8e178e62a2649667d9"
            auth_token = "3752485569962ba1002585c7360c850a"
            twilio_number = "+15803083553"
            
            # Format phone number (must be in E.164 format)
            if not contact:
                print("❌ Error: No phone number provided for SMS")
                return
            
            phone_number = contact.strip()
            original_number = phone_number
            
            # Ensure phone number starts with +
            if not phone_number.startswith('+'):
                if len(phone_number) == 10:
                    phone_number = "+91" + phone_number  # India country code
                    print(f"📱 Formatting phone number: {original_number} → {phone_number}")
                elif len(phone_number) > 10:
                    phone_number = "+" + phone_number
                else:
                    phone_number = "+1" + phone_number  # Default to US
            
            try:
                print(f"📤 Sending SMS to {phone_number}...")
                client = Client(account_sid, auth_token)
                message = client.messages.create(
                    body=ip_address,
                    from_=twilio_number,
                    to=phone_number
                )
                print(f"✅ SMS sent successfully! (SID: {message.sid})")
            except Exception as e:
                error_msg = str(e)
                print(f"❌ SMS Failed: {error_msg}")
                if "not verified" in error_msg.lower() or "unverified" in error_msg.lower():
                    print("   → Phone number not verified in Twilio trial account")
                    print("   → Verify numbers at: https://console.twilio.com/us1/develop/phone-numbers/manage/verified")

        else:
            print("\n⚠ MESSAGE ⚠")
            print(ip_address)

    except Exception as e:
        print(f"Error sending alert: {e}")

# ================================================================
# 🔒 SECURITY HELPERS (unchanged)
# ================================================================
def get_current_ip():
    try:
        return socket.gethostbyname(socket.gethostname())
    except:
        return "Unknown-IP"

def generate_otp():
    """Generate 6-digit OTP"""
    return str(random.randint(100000, 999999))

# ================================================================
# Firestore helpers (wrap common operations)
# ================================================================
def get_provider_rate(db, provider):
    """
    Returns float rate or None.
    provider: string
    """
    doc_ref = db.collection("provider_rates").document(provider)
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict()
        try:
            return float(data.get("cost_per_unit", 0))
        except Exception:
            return None
    return None

def provider_exists(db, provider):
    return db.collection("provider_rates").document(provider).get().exists

# ================================================================
# --- SUPER ADMIN FUNCTIONS (converted to Firestore)
# ================================================================
def add_customer_unscoped(db):
    print("\n--- (Super Admin) Add New Customer ---")
    try:
        acc_no = str(int(input("Enter Account Number: ")))  # store as string key
        name = input("Enter Name: ")
        address = input("Enter Address: ")
        district = input("Enter District: ")
        provider = input("Enter Electricity Provider: ")
        mobile = input("Enter Mobile Number: ")

        if not provider_exists(db, provider):
            print(f"--- WARNING --- Provider '{provider}' not found in provider_rates ---")

        customer_data = {
            "account_number": acc_no,
            "name": name,
            "address": address,
            "district": district,
            "electricity_provider": provider,
            "mobile_number": mobile,
            "age": None  # optional field left None if not provided
        }

        # Use account_number as document id
        db.collection("electricity_customers").document(acc_no).set(customer_data)
        print(f"Customer '{name}' added successfully.")
    except Exception as e:
        print(f"Error adding customer: {e}")

def generate_bill_unscoped(db):
    print("\n--- Generate Bill (Super Admin) ---")
    key = input("Enter Account No or Mobile No: ")
    try:
        # Try to find by account_number first, then mobile_number
        cust_ref = db.collection("electricity_customers").document(str(key))
        cust_doc = cust_ref.get()
        cust = None
        if cust_doc.exists:
            cust = cust_doc.to_dict()
        else:
            # search by mobile_number
            q = db.collection("electricity_customers").where("mobile_number", "==", key).limit(1).get()
            if q:
                cust = q[0].to_dict()

        if not cust:
            print("Customer not found.")
            return

        acc_no = cust.get("account_number", "")
        if not acc_no:
            print("Error: Customer account number is missing in database.")
            return
        name = cust.get("name", "")
        provider = cust.get("electricity_provider", "")

        units = float(input("Enter Units Consumed (kWh): "))
        rate = get_provider_rate(db, provider)

        if rate is None:
            print(f"--- ERROR --- No rate found for provider '{provider}'. Please add one in the Super Admin menu.")
            return

        total = round(units * rate, 2)
        today = datetime.datetime.utcnow()

        bill_data = {
            "account_number": acc_no,
            "no_of_units": units,
            "cost_per_unit": rate,
            "total_bill": total,
            "arrear": 0.0,
            "bill_date": today,
            "due_date": today + datetime.timedelta(days=15),
            "status": "due"
        }
        # Add bill (auto-generated ID)
        doc_ref = db.collection("electricity_bills").add(bill_data)
        print(f"Bill generated successfully. Bill ID: {doc_ref[1].id}")
    except Exception as e:
        print(f"Error generating bill: {e}")

def manage_provider_rates(db):
    print("\n--- Manage Provider Rates ---")
    docs = db.collection("provider_rates").get()
    for d in docs:
        data = d.to_dict()
        print(f"  {d.id}: ₹{data.get('cost_per_unit')}")
    ch = input("\n1.Add 2.Update 3.Back: ")
    if ch == "1":
        p = input("Provider: ")
        r = float(input("Rate: "))
        db.collection("provider_rates").document(p).set({"electricity_provider": p, "cost_per_unit": r})
        print("Rate added.")
    elif ch == "2":
        p = input("Provider: ")
        r = float(input("New Rate: "))
        doc_ref = db.collection("provider_rates").document(p)
        if doc_ref.get().exists:
            doc_ref.update({"cost_per_unit": r})
            print("Rate updated.")
        else:
            print("Provider not found.")
    else:
        return

def create_provider_admin(db):
    print("\n--- Create Provider Admin ---")
    try:
        provider = input("Enter Provider Name: ")
        admin = input("Enter Admin Name: ")
        password = provider + "@123"
        doc_ref = db.collection("electricity_provider_details").document(provider)
        if doc_ref.get().exists:
            print("Admin already exists.")
            return
        doc_ref.set({
            "electricity_provider": provider,
            "admin_name": admin,
            "password": password,
            "time": None
        })
        print(f"Admin created for {provider}. Password: {password}")
    except Exception as e:
        print(f"Error: {e}")

# ================================================================
# --- PROVIDER ADMIN LOGIN (with OTP) ---
# ================================================================
def provider_login(db):
    print("\n--- Provider Admin Login ---")
    try:
        provider = input("Provider Name: ")
        admin = input("Admin Name: ")
        password = input("Password: ")
        ip = get_current_ip()

        doc_ref = db.collection("electricity_provider_details").document(provider)
        doc = doc_ref.get()
        if not doc.exists:
            print("Invalid provider or admin name.")
            return None
        data = doc.to_dict()
        stored_pass = data.get("password")
        stored_admin = data.get("admin_name")
        if admin != stored_admin:
            print("Invalid provider or admin name.")
            return None

        if password == stored_pass:
            otp = generate_otp()
            notify_user(admin, f"Your Voltify Admin OTP is: {otp}", contact="provider_email@gmail.com", mode="email")
            entered = input("Enter OTP: ").strip()
            if entered == otp:
                print(f"✅ Login successful. Welcome {admin}.")
                doc_ref.update({"time": datetime.datetime.utcnow()})
                return provider
            else:
                print("❌ Invalid OTP.")
                return None
        else:
            print("⚠ Invalid password.")
            notify_user(admin, f"Suspicious login from IP {ip}", contact="provider_email@gmail.com", mode="email")
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None

# ================================================================
# --- PROVIDER PORTAL FUNCTIONS ---
# ================================================================
def add_customer_scoped(db, provider):
    print(f"\n--- Add Customer for {provider} ---")
    try:
        acc = str(int(input("Account No: ")))
        name = input("Name: ")
        addr = input("Address: ")
        dist = input("District: ")
        mob = input("Mobile: ")
        customer_data = {
            "account_number": acc,
            "name": name,
            "address": addr,
            "district": dist,
            "electricity_provider": provider,
            "mobile_number": mob,
            "age": None
        }
        db.collection("electricity_customers").document(acc).set(customer_data)
        print("Customer added.")
    except Exception as e:
        print(e)

def generate_bill_scoped(db, provider):
    print(f"\n--- Generate Bill for {provider} ---")
    try:
        key = input("Enter Account or Mobile: ")
        # find specific customer for this provider
        cust_doc = None
        doc = db.collection("electricity_customers").document(str(key)).get()
        if doc.exists:
            doc_data = doc.to_dict()
            if doc_data and doc_data.get("electricity_provider") == provider:
                cust_doc = doc_data
        else:
            q = db.collection("electricity_customers")\
                  .where("mobile_number", "==", key)\
                  .where("electricity_provider", "==", provider).limit(1).get()
            if q:
                cust_doc = q[0].to_dict()

        if not cust_doc:
            print("Customer not found.")
            return

        acc = cust_doc.get("account_number", "")
        if not acc:
            print("Error: Customer account number is missing in database.")
            return
        name = cust_doc.get("name", "")
        rate = get_provider_rate(db, provider)
        if rate is None:
            print(f"--- ERROR --- No rate found for provider '{provider}'. Please add one in the Super Admin menu.")
            return

        units = float(input("Units: "))
        total = round(units * rate, 2)
        bill_data = {
            "account_number": acc,
            "no_of_units": units,
            "cost_per_unit": rate,
            "total_bill": total,
            "arrear": 0.0,
            "bill_date": datetime.datetime.utcnow(),
            "due_date": datetime.datetime.utcnow() + datetime.timedelta(days=15),
            "status": "due"
        }
        ref = db.collection("electricity_bills").add(bill_data)
        print(f"Bill generated. Bill ID: {ref[1].id}")
    except Exception as e:
        print(f"Fatal Error: {e}")

# ================================================================
# --- CUSTOMER LOGIN (with OTP) ---
# ================================================================
def customer_login(db):
    print("\n--- Customer Login ---")
    try:
        acc = input("Account Number: ")
        mob = input("Mobile (Password): ")
        ip = get_current_ip()

        doc = db.collection("electricity_customers").document(str(acc)).get()
        if not doc.exists:
            print("Login failed.")
            notify_user(acc, f"Suspicious login from IP {ip}", contact=mob, mode="sms")
            return None
        
        row = doc.to_dict()
        stored_mobile = row.get("mobile_number", "")
        if stored_mobile != mob:
            print("Login failed.")
            notify_user(acc, f"Suspicious login from IP {ip}", contact=mob, mode="sms")
            return None
        otp = generate_otp()
        # Use stored mobile number from database, not user input
        notify_user(row.get('name','user'), f"Your Voltify OTP is: {otp}", contact=stored_mobile, mode="sms")
        entered = input("Enter OTP: ").strip()
        if entered == otp:
            print(f"✅ Welcome {row.get('name','user')}!")
            return str(row.get("account_number", ""))  # Ensure string return for consistency
        else:
            print("❌ Incorrect OTP.")
            return None
    except Exception as e:
        print(e)
        return None

# ================================================================
# --- BILL VIEW & PAYMENT (Firestore) ---
# ================================================================
def view_my_bills(db, acc):
    try:
        bills = db.collection("electricity_bills")\
                  .where("account_number", "==", str(acc))\
                  .order_by("bill_date", direction=firestore.Query.DESCENDING).get()
    except Exception as e:
        # If ordering fails (no composite index), fetch without ordering and sort manually
        print("Note: Bills fetched without date ordering (index may be required).")
        bills = db.collection("electricity_bills")\
                  .where("account_number", "==", str(acc)).get()
        # Sort manually by date
        bills_list = list(bills)
        bills_list.sort(key=lambda x: x.to_dict().get("bill_date", datetime.datetime.min), reverse=True)
        bills = bills_list
    if not bills:
        print("\n--- You have no bills on record. ---")
        return
    print("\n--- Your Bills ---")
    for b in bills:
        d = b.to_dict()
        bill_id = b.id
        date = d.get("bill_date")
        if isinstance(date, datetime.datetime):
            date_str = date.strftime("%Y-%m-%d")
        else:
            date_str = str(date)
        print(f"Bill #{bill_id} | Date: {date_str} | Units: {d.get('no_of_units')} | Amount: ₹{d.get('total_bill')} | Status: {d.get('status')}")

def pay_bill(db, acc):
    print("\n--- Pay a Bill ---")
    bills = db.collection("electricity_bills")\
              .where("account_number", "==", str(acc))\
              .where("status", "==", "due").get()
    if not bills:
        print("No due bills.")
        return

    print("Available bills to pay:")
    for b in bills:
        d = b.to_dict()
        print(f"Bill #{b.id} - Amount: ₹{d.get('total_bill')}")

    b_id = input("Enter Bill ID to pay: ").strip()
    if not b_id:
        print("Invalid Bill ID.")
        return

    bill_ref = db.collection("electricity_bills").document(b_id)
    bill_doc = bill_ref.get()
    if not bill_doc.exists:
        print(f"Bill ID {b_id} is not found.")
        return
    bill_data = bill_doc.to_dict()
    if bill_data.get("status") != "due":
        print("This bill is not due or already paid.")
        return

    total = float(bill_data.get("total_bill", 0.0))
    amount_usd = round(total / 80.0, 2)  # assuming INR->USD conversion for demonstration

    print("\n========================================================")
    print("PAYMENT REQUIRED")
    print(f"Bill ID: {b_id}")
    print(f"Amount: ₹{total} (approx ${amount_usd} USD)")
    print("\nPlease open the following URL in your browser to complete the payment:")
    print(f"\nhttp://localhost:3000/pay.html?bill_id={b_id}&amount={amount_usd}&acc_no={acc}")
    print("\nAfter paying, mark the bill as paid by confirming here.")
    confirm = input("Mark as paid now? (y/n): ").lower()
    if confirm == "y":
        bill_ref.update({"status": "paid", "paid_on": datetime.datetime.utcnow()})
        print("Payment recorded. Bill marked as paid.")
    else:
        print("Payment not recorded here. Complete payment on the payment page.")
    print("========================================================\n")

# ================================================================
# --- PORTALS (run loops) ---
# ================================================================
def run_customer_portal(db):
    acc = customer_login(db)
    if not acc: return
    while True:
        print("\n--- Customer Portal ---")
        print("1.View Bills 2.Pay Bill 3.Logout")
        ch = input("Choice: ")
        if ch == "1": view_my_bills(db, acc)
        elif ch == "2": pay_bill(db, acc)
        elif ch == "3": break

def run_provider_portal(db):
    prov = provider_login(db)
    if not prov: return
    while True:
        print("\n--- Provider Portal ---")
        print("1.Add Customer 2.Generate Bill 3.Logout")
        ch = input("Choice: ")
        if ch == "1": add_customer_scoped(db, prov)
        elif ch == "2": generate_bill_scoped(db, prov)
        elif ch == "3": break

def run_super_admin_portal(db):
    while True:
        print("--- Super Admin Portal ---")
        print("1.Add Customer 2.Generate Bill 3.Manage Rates 4.Send Due Reminders 5.Create Admin 6.Logout")
        ch = input("Choice: ")
        if ch == "1":
            add_customer_unscoped(db)
        elif ch == "2":
            generate_bill_unscoped(db)
        elif ch == "3":
            manage_provider_rates(db)
        elif ch == "4":
            send_due_bill_notifications(db)
        elif ch == "5":
            create_provider_admin(db)
        elif ch == "6":
            break
        else:
            print("Invalid choice. Try again.")


# ================================================================
# --- BILL DUE REMINDER NOTIFICATION FEATURE ---
# ================================================================
def send_due_bill_notifications(db):
    """
    Checks all bills and sends reminders via SMS and email for upcoming or overdue bills.
    """
    today = datetime.datetime.utcnow()
    bills_ref = db.collection("electricity_bills").where("status", "==", "due").get()
    print("\n--- Checking for due bill reminders ---")

    for b in bills_ref:
        data = b.to_dict()
        due_date = data.get("due_date")
        if not due_date:
            continue

        # Convert Firestore timestamp to datetime if needed
        if hasattr(due_date, 'to_datetime'):
            due_date = due_date.to_datetime()

        acc_no = data.get("account_number")
        total = data.get("total_bill", 0.0)
        days_left = (due_date - today).days

        if days_left <= 2 and days_left >= 0:
            message = f"💡 Reminder: Your electricity bill of ₹{total} is due on {due_date.strftime('%Y-%m-%d')}."
        elif days_left < 0:
            message = f"⚠️ Your electricity bill of ₹{total} was due on {due_date.strftime('%Y-%m-%d')}. Please pay immediately."
        else:
            continue

        # Get customer contact info
        cust_doc = db.collection("electricity_customers").document(str(acc_no)).get()
        if not cust_doc.exists:
            continue
        cust = cust_doc.to_dict()
        name = cust.get("name", "Customer")
        mobile = cust.get("mobile_number")
        email = cust.get("email", None)

        # Send SMS reminder
        if mobile:
            notify_user(name, message, contact=mobile, mode="sms")
        # Send Email reminder
        if email:
            notify_user(name, message, contact=email, mode="email")

        print(f"📤 Reminder sent to {name} (SMS: {mobile}, Email: {email})")

# ================================================================
# --- MAIN (initialize Firebase instead of MySQL) ---
# ================================================================
def main():
    try:
        print("Initializing Firebase Firestore...")
        cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
        # Check if Firebase is already initialized to avoid error on re-runs
        try:
            firebase_admin.get_app()
            db = firestore.client()
            print("Using existing Firebase connection.")
        except ValueError:
            firebase_admin.initialize_app(cred)
            db = firestore.client()
        print("Connected to Firestore.")

        while True:
            print("\n===== VOLTIFY MAIN PORTAL =====")
            print("1.Customer Login\n2.Provider Admin Login\n3.Super Admin Login\n4.Send Bill Reminders\n5.Exit")
            ch = input("Choice: ")
            if ch == "1": run_customer_portal(db)
            elif ch == "2": run_provider_portal(db)
            elif ch == "3": run_super_admin_portal(db)
            elif ch == "4":
                send_due_bill_notifications(db)
            elif ch == "5":
                print("Exiting.")
                sys.exit(0)
            else:
                print("Invalid choice.")
    except Exception as e:
        print(f"Fatal Error: {e}")

if __name__ == "__main__":
    main()
