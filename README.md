# 🛒 Retail360 - AI Self-Checkout System

**Retail360** is an **AI-powered self-checkout system** that revolutionizes the retail experience by enabling customers to scan their own products, pay digitally, and receive an instant digital exit pass. This application simplifies the shopping journey, reduces wait times, and provides a secure, efficient process for both customers and staff.

## ✨ Features

### Customer Checkout Interface
- **Barcode Scanning:** Add products to the cart by scanning their barcodes with a camera
- **Manual Entry:** Manually input barcodes if a camera isn't available
- **Real-time Cart Management:** View and manage items in the shopping cart with live updates on subtotal, tax, and total price
- **Digital Payment & Invoice:** After payment, receive a unique UPI Transaction Reference (UTR), a downloadable PDF invoice, and a scannable QR code for exiting the store

### Exit Verification Interface
- **QR Code Scanner:** A dedicated interface for store staff to scan customer-generated QR codes
- **Instant Verification:** The system instantly verifies the transaction details linked to the QR code to approve the customer's exit
- **Emergency Override:** A manual entry option for staff to verify a customer's exit code in case of technical issues

### Admin Panel
- **Secure Access:** The admin panel is protected by a password to ensure only authorized staff can access it
- **Product Management:** Easily upload an entire product catalog from a CSV file
- **Business Analytics:** View key metrics like total sales, transaction count, and product count
- **Database Browser:** Directly view and browse the contents of the products and transactions database tables

## 🚀 Getting Started

### Prerequisites

To run this application, you need to have **Python** installed on your system. It's recommended to use a **virtual environment**.

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/zenthicai/retail360-Self-checkout-system.git
   cd retail360-Self-checkout-system
   ```

2. **Create a virtual environment (optional but recommended):**
   ```bash
   python -m venv venv
   ```

3. **Activate the virtual environment:**
   - **On Windows:**
     ```bash
     venv\Scripts\activate
     ```
   - **On macOS and Linux:**
     ```bash
     source venv/bin/activate
     ```

4. **Install the required dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

### Running the Application

1. **Ensure you have the required files:** The application automatically creates an `retail360.db` file and `bills` and `exit_qr` directories.

2. **Run the Streamlit app from your terminal:**
   ```bash
   streamlit run app.py
   ```

3. The application will open in your web browser.

## 🛠️ Configuration

The application uses a local **SQLite database** (`retail360.db`) for all product and transaction data.

- **Database:** The database schema is defined in the Python code (DDL dictionary) and is automatically initialized on the first run
- **Admin Password:** The default admin password is `admin123`. For a production environment, you should replace this with a more secure authentication method
- **Tax Rate:** The `TAX_RATE` constant is set to `0.18` (18% GST for India) and can be easily modified at the top of the script

## 📂 Project Structure

```
Retail360/
├── app.py                  # Main Streamlit application script
├── retail360.db            # Local SQLite database (auto-generated)
├── bills/                  # Directory for storing PDF invoices (auto-generated)
├── exit_qr/                # Directory for storing exit QR codes (auto-generated)
├── README.md               # This file
└── requirements.txt        # List of Python dependencies
```

## 📝 Dependencies Notes

- The `pyzbar` library is optional for barcode scanning via the camera. If you don't install it, manual barcode entry will still work
- The `fpdf` library is optional for PDF invoice generation. If it's not installed, the application will still generate and display a plain text invoice

## 🔧 Technical Requirements

- Python 3.7+
- Streamlit
- SQLite3 (included with Python)
- Additional dependencies as listed in `requirements.txt`

## 📞 Support

If you encounter any issues or have questions, please open an issue in the repository.
