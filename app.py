from flask import Flask, request, jsonify, session, redirect, url_for, render_template
from flask_mysqldb import MySQL
from flask_bcrypt import Bcrypt
from flask_cors import CORS

app = Flask(__name__, template_folder=".")  # Look for HTML files in the same directory
CORS(app)
bcrypt = Bcrypt(app)
app.secret_key = 'your_secret_key'  # Keep this secure!

# MySQL Database Configuration
app.config["MYSQL_HOST"] = "sql7.freesqldatabase.com"
app.config["MYSQL_USER"] = "sql7763333"
app.config["MYSQL_PASSWORD"] = "BtCcUDutUB"
app.config["MYSQL_DB"] = "sql7763333"
app.config["MYSQL_PORT"] = 3306

mysql = MySQL(app)

# Redirect to login page
@app.route('/')
def home():
    return redirect(url_for('login'))

# Serve Login Page
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')  # Ensure 'login.html' exists
    
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400

    cur = mysql.connection.cursor()

    # Check if user is a company
    cur.execute("SELECT companyId, password FROM companies WHERE username = %s", (username,))
    company = cur.fetchone()

    if company:
        db_password = company[1]
        if db_password == password:  # Compare directly (NO HASHING)
            session['user'] = {'companyId': company[0], 'role': 'company'}  
            return jsonify({'redirect': '/company_dashboard'})

    # Check if user is a client
    cur.execute("SELECT clientId, password FROM clients WHERE username = %s", (username,))
    client = cur.fetchone()

    if client:
        db_password = client[1]
        if db_password == password:  # Compare directly (NO HASHING)
            session['user'] = {'clientId': client[0], 'role': 'client'} 
            return jsonify({'redirect': '/client_dashboard'})

    return jsonify({'error': 'Invalid username or password'}), 401

# Serve Client Dashboard
@app.route('/client_dashboard', methods=['GET'])
def client_dashboard():
    if 'user' not in session or session['user']['role'] != 'client':
        return redirect(url_for('login'))

    client_id = session['user']['clientId']
    cur = mysql.connection.cursor()

    # ✅ Fetch purchases from the correct table
    table_name = f"purchases{client_id}"
    cur.execute(f"SELECT date, price FROM {table_name} WHERE clientId = %s", (client_id,))
    purchases = cur.fetchall()

    # ✅ Fetch RFID cards
    cur.execute("SELECT uid, balance FROM users WHERE clientId = %s", (client_id,))
    rfid_cards = [{'uid': row[0], 'balance': row[1]} for row in cur.fetchall()]
    
    cur.close()

    # ✅ Pass the data to the template instead of returning JSON
    return render_template('client_dashboard.html', purchases=purchases, rfid_cards=rfid_cards)

# Serve Company Dashboard
@app.route('/company_dashboard', methods=['GET', 'POST'])
def company_dashboard():
    if 'user' not in session or session['user']['role'] != 'company':
        return redirect(url_for('login'))

    company_id = session['user']['companyId']  # Get the company ID

    # Fetch company name and the number of vending machines
    cur = mysql.connection.cursor()
    cur.execute("SELECT companyName, vendingMachineNum FROM companies WHERE companyId = %s", (company_id,))
    company_data = cur.fetchone()
    company_name = company_data[0]
    vending_machine_num = company_data[1]  # The number of vending machines

    # Ensure machine_id is received correctly (default: first vending machine)
    machine_id = request.form.get('machine', '1')

    try:
        machine_id = int(machine_id)  # Convert to integer to avoid errors
    except ValueError:
        machine_id = 1  # Default to first vending machine

    # Generate the list of vending machine IDs (e.g., [1, 2, 3] if vendingMachineNum = 3)
    machines = [{"id": i, "name": f"Vending Machine {i}"} for i in range(1, vending_machine_num + 1)]

    # Tables for sales and products
    sales_table = f"selles{company_id}"
    products_table = f"products{company_id}"

    # Fetch sales data
    sales_query = f"SELECT productCode, productName, salePrice, saleTime FROM {sales_table} WHERE vendingMachineId = %s"
    cur.execute(sales_query, (machine_id,))
    sales = cur.fetchall()

    # Fetch product prices
    products_query = f"SELECT productCode, productName, productPrice FROM {products_table} WHERE vendingMachineId = %s"
    cur.execute(products_query, (machine_id,))
    products = cur.fetchall()

    cur.close()

    return render_template('company_dashboard.html', company_name=company_name, sales=sales, products=products, selected_machine=machine_id, machines=machines)

# Update Prices
@app.route('/update_prices', methods=['POST'])
def update_prices():
    if 'user' not in session or session['user']['role'] != 'company':
        return redirect(url_for('login'))

    company_id = session['user']['companyId']
    machine_id = request.form.get('machine', '1')  # Get selected machine

    table_name = f"products{company_id}"  # Correct table for products

    cur = mysql.connection.cursor()
    for key, value in request.form.items():
        if key.startswith("price_"):  # Filter only price fields
            product_code = key.split("_")[1]
            new_price = value

            query = f"UPDATE {table_name} SET productPrice = %s WHERE productCode = %s AND vendingMachineId = %s"
            cur.execute(query, (new_price, product_code, machine_id))

    mysql.connection.commit()
    cur.close()

    return redirect(url_for('company_dashboard'))  # Refresh page

if __name__ == '__main__':
    app.run(debug=True)
