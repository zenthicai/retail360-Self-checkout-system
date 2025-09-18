import os
import io
import uuid
import base64
import sqlite3
from datetime import datetime
from typing import Optional, Dict, List, Tuple

import streamlit as st
import pandas as pd
import numpy as np
from PIL import Image
import qrcode

# ---- Optional dependency for 1D/QR barcode decoding ----
PYZBAR_OK = True
try:
    from pyzbar.pyzbar import decode as zbar_decode
except Exception:
    PYZBAR_OK = False

# ---- New: Import FPDF for PDF generation ----
try:
    from fpdf import FPDF
    FPDF_OK = True
except Exception:
    FPDF_OK = False
    
# ==============================================================================
# CONFIG & STYLING
# ==============================================================================
st.set_page_config(
    page_title="Retail360 • AI Self‑Checkout", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 5px;
        padding: 1rem;
        margin: 1rem 0;
    }
    .cart-item {
        background: #f8f9fa;
        border-left: 4px solid #007bff;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 5px;
    }
    .stButton>button {
        width: 100%;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 5px;
        padding: 0.75rem;
    }
    .invoice-container {
        border: 1px solid #ddd;
        border-radius: 5px;
        padding: 10px;
        height: 600px;
    }
    .stDataFrame table thead th {
        background-color: #FF4B4B !important;
        color: white !important;
    }
</style>
""", unsafe_allow_html=True)

# Define file paths and constants
DB_PATH = "retail360.db"
BILLS_DIR = "bills"
QR_DIR = "exit_qr"
os.makedirs(BILLS_DIR, exist_ok=True)
os.makedirs(QR_DIR, exist_ok=True)

TAX_RATE = 0.18  # 18% GST for India

# ==============================================================================
# DATABASE LAYER (SQLite)
# ==============================================================================
DDL = {
    "products": """
        CREATE TABLE IF NOT EXISTS products (
            product_id INTEGER PRIMARY KEY,
            barcode TEXT UNIQUE NOT NULL,
            product_name TEXT NOT NULL,
            brand TEXT,
            category TEXT,
            price REAL NOT NULL,
            stock_quantity INTEGER DEFAULT 100,
            description TEXT,
            image_url TEXT,
            created_at TEXT,
            updated_at TEXT
        );
    """,
    "transactions": """
        CREATE TABLE IF NOT EXISTS transactions (
            trans_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            customer_name TEXT,
            subtotal REAL NOT NULL,
            tax_amount REAL NOT NULL,
            total REAL NOT NULL,
            utr TEXT,
            exit_code TEXT UNIQUE,
            status TEXT DEFAULT 'completed'
        );
    """,
    "transaction_items": """
        CREATE TABLE IF NOT EXISTS transaction_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trans_id TEXT NOT NULL,
            product_id INTEGER NOT NULL,
            qty INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            line_total REAL NOT NULL,
            FOREIGN KEY(trans_id) REFERENCES transactions(trans_id),
            FOREIGN KEY(product_id) REFERENCES products(product_id)
        );
    """
}

@st.cache_resource
def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn()
    cursor = conn.cursor()
    for table_name, ddl in DDL.items():
        cursor.execute(ddl)
    conn.commit()

def load_products_from_csv(df: pd.DataFrame) -> bool:
    try:
        df_clean = df.copy().fillna('')
        conn = get_conn()
        cursor = conn.cursor()
        success_count = 0
        for _, row in df_clean.iterrows():
            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO products 
                    (product_id, barcode, product_name, brand, category, price, 
                     stock_quantity, description, image_url, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    int(row['product_id']), str(row['barcode']), str(row['product_name']),
                    str(row['brand']), str(row['category']), float(row['price']),
                    int(row['stock_quantity']), str(row.get('description', '')),
                    str(row.get('image_url', '')), str(row.get('created_at', datetime.now().isoformat())),
                    str(row.get('updated_at', datetime.now().isoformat()))
                ))
                success_count += 1
            except Exception as e:
                st.warning(f"Skipped row {row.get('product_id', 'N/A')}: {str(e)}")
        conn.commit()
        return success_count
    except Exception as e:
        st.error(f"Error loading products: {str(e)}")
        return 0

def get_product_by_barcode(barcode: str) -> Optional[Dict]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT product_id, barcode, product_name, brand, category, price, stock_quantity
        FROM products WHERE barcode = ?
    """, (str(barcode).strip(),))
    row = cursor.fetchone()
    if row:
        return {
            'product_id': row[0], 'barcode': row[1], 'product_name': row[2],
            'brand': row[3], 'category': row[4], 'price': row[5], 'stock_quantity': row[6]
        }
    return None

def save_transaction(customer_name: str, cart_items: List[Dict], subtotal: float, 
                     tax_amount: float, total: float, utr: str) -> Tuple[str, str]:
    trans_id = f"TXN-{datetime.now().strftime('%Y%m%d%H%M%S')}-{str(uuid.uuid4())[:8]}"
    exit_code = f"EXIT-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    timestamp = datetime.now().isoformat()
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO transactions 
        (trans_id, timestamp, customer_name, subtotal, tax_amount, total, utr, exit_code)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (trans_id, timestamp, customer_name or "Anonymous", subtotal, tax_amount, total, utr, exit_code))
    for item in cart_items:
        cursor.execute("""
            INSERT INTO transaction_items 
            (trans_id, product_id, qty, unit_price, line_total)
            VALUES (?, ?, ?, ?, ?)
        """, (trans_id, item['product_id'], item['qty'], item['price'], item['line_total']))
    conn.commit()
    return trans_id, exit_code

def get_transaction_by_exit_code(exit_code: str) -> Optional[Tuple[Dict, pd.DataFrame]]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT trans_id, timestamp, customer_name, subtotal, tax_amount, total, utr
        FROM transactions WHERE exit_code = ?
    """, (exit_code.strip(),))
    transaction = cursor.fetchone()
    if not transaction:
        return None
    trans_data = {
        'trans_id': transaction[0], 'timestamp': transaction[1], 'customer_name': transaction[2],
        'subtotal': transaction[3], 'tax_amount': transaction[4], 'total': transaction[5], 'utr': transaction[6]
    }
    items_df = pd.read_sql_query("""
        SELECT ti.product_id, p.product_name, p.brand, ti.qty, ti.unit_price, ti.line_total
        FROM transaction_items ti JOIN products p ON p.product_id = ti.product_id
        WHERE ti.trans_id = ?
    """, conn, params=(transaction[0],))
    return trans_data, items_df

# ==============================================================================
# UTILITY FUNCTIONS
# ==============================================================================
def decode_barcodes_from_image(image: Image.Image) -> List[str]:
    if not PYZBAR_OK: return []
    try:
        img_array = np.array(image)
        decoded_objects = zbar_decode(img_array)
        barcodes = [obj.data.decode('utf-8') for obj in decoded_objects]
        return barcodes
    except Exception as e:
        st.error(f"Error decoding barcode: {str(e)}")
        return []

def generate_qr_code(data: str) -> bytes:
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    qr_image = qr.make_image(fill_color="black", back_color="white")
    img_buffer = io.BytesIO()
    qr_image.save(img_buffer, format='PNG')
    return img_buffer.getvalue()

def generate_pdf_invoice(trans_data: Dict, items_df: pd.DataFrame) -> bytes:
    if not FPDF_OK:
        st.error("❌ PDF generation library (fpdf) not found. Please run 'pip install fpdf'")
        return b''
    
    pdf = FPDF()
    pdf.add_page()
    
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "RETAIL360 INVOICE", 0, 1, 'C')
    pdf.ln(10)

    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 8, f"Transaction ID: {trans_data['trans_id']}", 0, 1)
    pdf.cell(0, 8, f"Date: {trans_data['timestamp'][:19]}", 0, 1)
    pdf.cell(0, 8, f"Customer: {trans_data['customer_name']}", 0, 1)
    pdf.cell(0, 8, f"UTR: {trans_data.get('utr', 'N/A')}", 0, 1)
    pdf.ln(10)

    pdf.set_font("Arial", "B", 10)
    pdf.cell(80, 8, "Product Name", 1)
    pdf.cell(30, 8, "Qty", 1)
    pdf.cell(40, 8, "Unit Price", 1)
    pdf.cell(40, 8, "Total", 1)
    pdf.ln()

    pdf.set_font("Arial", "", 10)
    for _, item in items_df.iterrows():
        pdf.cell(80, 8, f"{item['product_name']} ({item['brand']})", 1)
        pdf.cell(30, 8, str(item['qty']), 1)
        pdf.cell(40, 8, f"Rs. {item['unit_price']:.2f}", 1)
        pdf.cell(40, 8, f"Rs. {item['line_total']:.2f}", 1)
        pdf.ln()

    pdf.ln(10)
    
    pdf.set_font("Arial", "B", 12)
    pdf.cell(150, 8, "Subtotal:", 0, 0, 'R')
    pdf.cell(40, 8, f"Rs. {trans_data['subtotal']:.2f}", 0, 1, 'R')
    pdf.cell(150, 8, "Tax (18%):", 0, 0, 'R')
    pdf.cell(40, 8, f"Rs. {trans_data['tax_amount']:.2f}", 0, 1, 'R')
    pdf.cell(150, 8, "TOTAL:", 0, 0, 'R')
    pdf.cell(40, 8, f"Rs. {trans_data['total']:.2f}", 0, 1, 'R')
    pdf.ln(10)

    pdf.set_font("Arial", "I", 10)
    pdf.cell(0, 10, "Thank you for shopping with Retail360!", 0, 1, 'C')

    return pdf.output(dest='S').encode('latin1')

def generate_text_invoice(trans_data: Dict, items_df: pd.DataFrame) -> str:
    """Generates a plain text invoice from transaction data."""
    
    invoice_text = "==============================================\n"
    invoice_text += "              RETAIL360 INVOICE               \n"
    invoice_text += "==============================================\n"
    invoice_text += f"Transaction ID: {trans_data['trans_id']}\n"
    invoice_text += f"Date: {trans_data['timestamp'][:19]}\n"
    invoice_text += f"Customer: {trans_data['customer_name']}\n"
    invoice_text += f"UTR: {trans_data.get('utr', 'N/A')}\n"
    invoice_text += "----------------------------------------------\n"
    invoice_text += f"{'Product Name':<25} | {'Qty':>4} | {'Price':>8} | {'Total':>8}\n"
    invoice_text += "----------------------------------------------\n"
    
    for _, item in items_df.iterrows():
        product_name = (item['product_name'] + ' (' + item['brand'] + ')')[:24]
        invoice_text += f"{product_name:<25} | {str(item['qty']):>4} | {item['unit_price']:>8.2f} | {item['line_total']:>8.2f}\n"

    invoice_text += "----------------------------------------------\n"
    invoice_text += f"Subtotal: {'Rs. ' + f'{trans_data['subtotal']:.2f}':>33}\n"
    invoice_text += f"Tax (18%): {'Rs. ' + f'{trans_data['tax_amount']:.2f}':>32}\n"
    invoice_text += "----------------------------------------------\n"
    invoice_text += f"TOTAL: {'Rs. ' + f'{trans_data['total']:.2f}':>36}\n"
    invoice_text += "==============================================\n"
    invoice_text += "       Thank you for shopping with us!        \n"
    invoice_text += "==============================================\n"
    
    return invoice_text

def verify_exit_code(exit_code: str):
    result = get_transaction_by_exit_code(exit_code)
    if result:
        trans_data, items_df = result
        st.markdown("""
        <div class="success-box">
            <h3>✅ Exit Approved!</h3>
            <p>Customer can proceed to exit.</p>
        </div>
        """, unsafe_allow_html=True)
        st.subheader("📋 Transaction Details")
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Transaction ID:** {trans_data['trans_id']}")
            st.write(f"**Customer:** {trans_data['customer_name']}")
            st.write(f"**Date:** {trans_data['timestamp'][:19]}")
        with col2:
            st.write(f"**Total Amount:** ₹{trans_data['total']:.2f}")
            st.write(f"**UTR:** {trans_data['utr']}")
            st.write(f"**Status:** ✅ Verified")
        st.subheader("🛒 Purchased Items")
        st.dataframe(items_df, use_container_width=True, hide_index=True)
    else:
        st.error("❌ Invalid exit code. Please check and try again.")


# ==============================================================================
# MAIN APPLICATION INTERFACES
# ==============================================================================
def checkout_interface():
    st.header("🛍️ Customer Checkout")
    st.info("👋 **How it works:** Scan product barcodes with your camera or enter them manually to add items to your cart. When you're ready, complete the payment to generate your exit pass.")
    
    if 'cart' not in st.session_state:
        st.session_state.cart = {}

    st.subheader("📱 Scan Product")
    customer_name = st.text_input("👤 Customer Name (Optional)", placeholder="Enter your name")
    camera_image = st.camera_input("📸 Scan Product Barcode")
    manual_barcode = st.text_input("🔢 Or Enter Barcode Manually", placeholder="Enter barcode number")
    
    if st.button("➕ Add to Cart", key="add_manual"):
        if manual_barcode:
            add_item_to_cart(manual_barcode)
    
    if camera_image:
        process_camera_image(camera_image)
    
    st.markdown("---")
    st.subheader("🛒 Shopping Cart")
    display_cart()
    
    if st.session_state.cart:
        st.subheader("💳 Payment")
        process_payment(customer_name)

def add_item_to_cart(barcode: str):
    product = get_product_by_barcode(barcode)
    if product:
        if barcode in st.session_state.cart:
            st.session_state.cart[barcode]['qty'] += 1
        else:
            st.session_state.cart[barcode] = {**product, 'qty': 1, 'line_total': product['price']}
        st.success(f"✅ Added: {product['product_name']} (₹{product['price']:.2f})")
    else:
        st.error(f"❌ Product not found for barcode: {barcode}")

def process_camera_image(image):
    if PYZBAR_OK:
        try:
            pil_image = Image.open(image)
            barcodes = decode_barcodes_from_image(pil_image)
            if barcodes:
                for barcode in barcodes:
                    add_item_to_cart(barcode)
            else:
                st.info("📷 No barcode detected. Try taking a clearer photo.")
        except Exception as e:
            st.error(f"Error processing image: {str(e)}")
    else:
        st.warning("⚠️ Barcode scanning not available. Please install pyzbar library.")

def display_cart():
    if not st.session_state.cart:
        st.info("🛒 Your cart is empty. Scan products to add items!")
        return
    
    cart_data = []
    total = 0
    for barcode, item in st.session_state.cart.items():
        line_total = item['price'] * item['qty']
        cart_data.append({'Product': item['product_name'], 'Brand': item['brand'],
                         'Price': f"₹{item['price']:.2f}", 'Qty': item['qty'],
                         'Total': f"₹{line_total:.2f}"})
        total += line_total
    
    cart_df = pd.DataFrame(cart_data)
    st.dataframe(cart_df, use_container_width=True, hide_index=True)
    
    subtotal = total
    tax_amount = subtotal * TAX_RATE
    grand_total = subtotal + tax_amount
    
    st.markdown(f"""
    <div class="cart-item">
        <strong>💰 Cart Summary:</strong><br>
        Subtotal: ₹{subtotal:.2f}<br>
        Tax (18%): ₹{tax_amount:.2f}<br>
        <strong>Total: ₹{grand_total:.2f}</strong>
    </div>
    """, unsafe_allow_html=True)
    
    with st.form("cart_actions_form"):
        col1, col2 = st.columns(2)
        with col1:
            clear_button = st.form_submit_button("🗑️ Clear Cart", type="secondary")
        with col2:
            refresh_button = st.form_submit_button("🔄 Refresh Cart", type="secondary")
            
        if clear_button:
            st.session_state.cart = {}
            st.rerun()
            
        if refresh_button:
            st.rerun()

def process_payment(customer_name: str):
    if not st.session_state.cart:
        return
    
    subtotal = sum(item['price'] * item['qty'] for item in st.session_state.cart.values())
    tax_amount = subtotal * TAX_RATE
    grand_total = subtotal + tax_amount
    
    utr = st.text_input("💳 UPI Transaction Reference (UTR)", placeholder="Enter UTR after payment")
    
    if st.button("✅ Complete Payment", type="primary"):
        if not utr:
            st.warning("⚠️ Please enter UTR after completing UPI payment")
            return
        
        try:
            cart_items = [{
                'product_id': item['product_id'], 'qty': item['qty'], 'price': item['price'],
                'line_total': item['price'] * item['qty']
            } for item in st.session_state.cart.values()]
            
            trans_id, exit_code = save_transaction(customer_name, cart_items, subtotal, tax_amount, grand_total, utr)
            
            trans_data = {
                'trans_id': trans_id, 'timestamp': datetime.now().isoformat(),
                'customer_name': customer_name or "Anonymous", 'subtotal': subtotal,
                'tax_amount': tax_amount, 'total': grand_total, 'utr': utr
            }
            items_df = pd.DataFrame([
                {'product_name': item['product_name'], 'brand': item['brand'], 'qty': item['qty'],
                 'unit_price': item['price'], 'line_total': item['price'] * item['qty']}
                for item in st.session_state.cart.values()
            ])
            
            invoice_pdf_bytes = generate_pdf_invoice(trans_data, items_df)
            invoice_text = generate_text_invoice(trans_data, items_df)
            
            st.markdown("""
            <div class="success-box">
                <h3>🎉 Payment Successful!</h3>
                <p>Transaction completed. Please save your exit code and bill.</p>
            </div>
            """, unsafe_allow_html=True)
            
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("📄 Invoice")
                st.code(invoice_text, language='text')
                st.download_button("⬇️ Download Invoice (PDF)", data=invoice_pdf_bytes,
                                    file_name=f"invoice_{trans_id}.pdf", mime="application/pdf")
            
            with col2:
                st.subheader("🚪 Exit Pass")
                st.info(f"**Exit Code:** {exit_code}")
                qr_data = f"EXIT:{exit_code}|TOTAL:{grand_total:.2f}|TXN:{trans_id}"
                qr_bytes = generate_qr_code(qr_data)
                st.image(qr_bytes, caption="Show this QR at exit", width=250)
            
            st.session_state.cart = {}
            
        except Exception as e:
            st.error(f"❌ Payment processing failed: {str(e)}")

def exit_verification_interface():
    st.header("🚪 Exit Verification")
    st.info("👋 **How it works:** This section is for store staff. Use the camera to scan the customer's exit QR code, which they received after payment. The system will automatically verify their purchase and grant them an exit pass.")
    
    exit_camera = st.camera_input("📸 Scan Customer's Exit QR Code", key="exit_scanner")
    
    if exit_camera and PYZBAR_OK:
        try:
            pil_image = Image.open(exit_camera)
            codes = decode_barcodes_from_image(pil_image)
            if codes:
                for code in codes:
                    if code.startswith("EXIT:") or code.startswith("EXIT-"):
                        verify_exit_code(code)
            else:
                st.warning("📷 No QR code detected. Please ensure the QR code is clearly visible and try again.")
        except Exception as e:
            st.error(f"Error scanning QR: {str(e)}")
    elif exit_camera and not PYZBAR_OK:
        st.error("⚠️ QR code scanning not available. Please install pyzbar library.")
    
    st.markdown("""
    ---
    ### 👮 Staff Instructions:
    1. **Customer approaches exit** with their phone showing QR code
    2. **Point camera** at the QR code displayed on customer's phone
    3. **Wait for verification** - green checkmark means approved
    4. **Allow customer to exit** if verification is successful
    5. **Stop customer** if red error appears and call supervisor
    """)
    
    with st.expander("🚨 Emergency Override (Staff Only)", expanded=False):
        st.warning("⚠️ Use only in case of technical issues")
        emergency_code = st.text_input("Enter Exit Code Manually", placeholder="EXIT-YYYYMMDDHHMMSS")
        if st.button("🔓 Emergency Verify", type="secondary") and emergency_code:
            verify_exit_code(emergency_code)

def admin_interface():
    st.header("⚙️ Admin Panel")
    
    # Define a simple, fixed password
    ADMIN_PASSWORD = "admin123"

    # Initialize authentication state
    if "is_authenticated" not in st.session_state:
        st.session_state.is_authenticated = False
        
    # Check if user is authenticated
    if st.session_state.is_authenticated:
        st.info("💻 **How it works:** This is the staff-only control panel for managing the store. You can upload a new product catalog, view sales analytics, and browse the database tables directly.")
        tab1, tab2, tab3 = st.tabs(["📦 Product Management", "📊 Analytics", "🗄️ Database"])
        
        with tab1:
            st.subheader("📦 Product Catalog Management")
            uploaded_file = st.file_uploader(
                "Upload Products CSV", type=['csv'],
                help="Upload CSV with columns: product_id, barcode, product_name, brand, category, price, stock_quantity"
            )
            if uploaded_file:
                try:
                    df = pd.read_csv(uploaded_file)
                    st.subheader("📋 Data Preview")
                    st.dataframe(df.head(10), use_container_width=True)
                    required_cols = ['product_id', 'barcode', 'product_name', 'brand', 'category', 'price']
                    missing_cols = [col for col in required_cols if col not in df.columns]
                    if missing_cols:
                        st.error(f"❌ Missing required columns: {missing_cols}")
                    else:
                        if st.button("📥 Load Products to Database"):
                            with st.spinner("Loading products..."):
                                success_count = load_products_from_csv(df)
                                if success_count > 0:
                                    st.success(f"✅ Successfully loaded {success_count} products!")
                                else:
                                    st.error("❌ Failed to load products")
                except Exception as e:
                    st.error(f"Error reading CSV: {str(e)}")
        
        with tab2:
            st.subheader("📊 Business Analytics")
            conn = get_conn()
            col1, col2, col3 = st.columns(3)
            with col1:
                total_sales = pd.read_sql_query("SELECT SUM(total) as total FROM transactions", conn).iloc[0, 0] or 0
                st.metric("💰 Total Sales", f"₹{total_sales:.2f}")
            with col2:
                total_transactions = pd.read_sql_query("SELECT COUNT(*) as count FROM transactions", conn).iloc[0, 0]
                st.metric("🧾 Total Transactions", total_transactions)
            with col3:
                total_products = pd.read_sql_query("SELECT COUNT(*) as count FROM products", conn).iloc[0, 0]
                st.metric("📦 Total Products", total_products)
            
            st.subheader("📈 Recent Transactions")
            recent_transactions = pd.read_sql_query("""
                SELECT trans_id, timestamp, customer_name, total, utr
                FROM transactions ORDER BY timestamp DESC LIMIT 10
            """, conn)
            if not recent_transactions.empty:
                st.dataframe(recent_transactions, use_container_width=True, hide_index=True)
            else:
                st.info("No transactions found")
        
        with tab3:
            st.subheader("🗄️ Database Browser")
            conn = get_conn()
            st.write("**📦 Products**")
            products_df = pd.read_sql_query("SELECT * FROM products LIMIT 50", conn)
            if not products_df.empty:
                st.dataframe(products_df, use_container_width=True, hide_index=True)
            else:
                st.info("No products in database. Upload CSV to add products.")
            st.write("**🧾 Transactions**")
            transactions_df = pd.read_sql_query("""
                SELECT trans_id, timestamp, customer_name, total, utr, exit_code
                FROM transactions ORDER BY timestamp DESC LIMIT 20
            """, conn)
            if not transactions_df.empty:
                st.dataframe(transactions_df, use_container_width=True, hide_index=True)
            else:
                st.info("No transactions found")
    else:
        # Show password input if not authenticated
        st.info("🔒 This is an administration panel. Please enter the password to proceed.")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            if password == ADMIN_PASSWORD:
                st.session_state.is_authenticated = True
                st.rerun()
            else:
                st.error("❌ Incorrect password. Please try again.")

# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================
def main():
    init_db()
    
    st.markdown("""
    <div class="main-header">
        <h1>🛒 Retail360 - AI Self-Checkout System</h1>
        <p>Retail360 is an AI-powered self-checkout system that allows customers to quickly scan products and pay digitally.</p>
        <p>This system simplifies your shopping experience by eliminating long queues and providing instant digital invoices and exit passes.</p>
    </div>
    """, unsafe_allow_html=True)
    
    tab1, tab2, tab3 = st.tabs(["🛍️ Customer Checkout", "🚪 Exit Verification", "⚙️ Admin Panel"])
    
    with tab1:
        checkout_interface()
    
    with tab2:
        exit_verification_interface()

    with tab3:
        admin_interface()


if __name__ == "__main__":
    main()