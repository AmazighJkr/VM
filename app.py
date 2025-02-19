import pymysql
pymysql.install_as_MySQLdb()

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sock import Sock
import json
import os
from flask import Flask, request, jsonify, session, redirect, url_for, render_template
from flask_mysqldb import MySQL
from flask_bcrypt import Bcrypt

app = Flask(__name__, template_folder=".")  # Look for HTML files in the same directory
CORS(app)
bcrypt = Bcrypt(app)
sock = Sock(app)  # WebSocket setup
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

# Helper function to validate table names
def validate_table_name(table_name):
    allowed_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
    if all(char in allowed_chars for char in table_name):
        return table_name
    raise ValueError("Invalid table name")

# Route to fetch vending machines
@app.route("/vendingmachines", methods=["GET"])
def get_vending_machines():
    cursor = None
    try:
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT vendingMachineCode AS code, vendingMachineName AS name FROM vendingmachines")
        vending_machines = cursor.fetchall()
        return jsonify([{ "code": row[0], "name": row[1] } for row in vending_machines])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()

# WebSocket route
@sock.route('/ws')
def websocket_connection(ws):
    while True:
        try:
            message = ws.receive()
            if not message:
                break

            data = json.loads(message)
            event = data.get("event")
            payload = data.get("data")

            if event == "sell_product":
                handle_sell_product(ws, payload)
            elif event == "update_price":
                handle_update_price(ws, payload)
            elif event == "custom_command":
                handle_custom_command(ws, payload)
            else:
                ws.send(json.dumps({"error": "Invalid event type"}))

        except Exception as e:
            ws.send(json.dumps({"error": str(e)}))
            break

# Sell product functionality
def handle_sell_product(ws, data):
    vending_machine_code = data.get("vendingMachineCode")
    uid = data.get("uid")
    password = data.get("password")
    product_code = data.get("productCode")
    
    cursor = None
    try:
        cursor = mysql.connection.cursor()

        # Verify vending machine
        cursor.execute("SELECT vendingMachineId, companyId FROM vendingmachines WHERE vendingMachineCode = %s", (vending_machine_code,))
        vending_machine = cursor.fetchone()
        if not vending_machine:
            ws.send(json.dumps({"sell_response": "Invalid vending machine code"}))
            return
        vending_machine_id, company_id = vending_machine
        
        # Determine correct products table
        products_table = f"products{company_id}"
        
        # Fetch product price from the correct products table
        cursor.execute(f"SELECT productPrice, productName FROM {products_table} WHERE vendingMachineId = %s AND productCode = %s", (vending_machine_id, product_code))
        product = cursor.fetchone()
        if not product:
            ws.send(json.dumps({"sell_response": "Product not found in vending machine"}))
            return
        product_price = product[0]
        product_name = product[1]
        
        # Verify user
        cursor.execute("SELECT userId, balance FROM users WHERE uid = %s AND password = %s", (uid, password))
        user = cursor.fetchone()
        if not user:
            ws.send(json.dumps({"sell_response": "Invalid user credentials"}))
            return
        user_id, balance = user

        # Check balance
        if balance < product_price:
            ws.send(json.dumps({"sell_response": f"Insufficient balance, {balance}"}))
            return

        # Update user's balance
        new_balance = balance - product_price
        cursor.execute("UPDATE users SET balance = %s WHERE userId = %s", (new_balance, user_id))

        # Record the sale
        sale_table = validate_table_name(f"selles{vending_machine_id}")
        cursor.execute(
            f"INSERT INTO {sale_table} (vendingMachineId,productCode, productName, SalePrice, saleTime) VALUES (%s, %s, %s, NOW())",
            (vending_machine_id, product_code, product_name, product_price)
        )

        # Record the purchase
        purchase_table = validate_table_name(f"purchases{user_id}")
        cursor.execute(
            f"INSERT INTO {purchase_table} (clientId, price, date) VALUES (%s, %s, NOW())",
            (user_id, product_price)
        )

        mysql.connection.commit()
        ws.send(json.dumps({"sell_response": f"Sale successful, {new_balance}"}))

    except Exception as e:
        ws.send(json.dumps({"sell_response": str(e)}))

    finally:
        if cursor:
            cursor.close()

# Update price functionality
def handle_update_price(ws, data):
    vending_machine_code = data.get("vendingMachineCode")
    product_code = data.get("productCode")
    new_price = data.get("newPrice")

    cursor = None
    try:
        cursor = mysql.connection.cursor()

        # Verify vending machine
        cursor.execute("SELECT vendingMachineId FROM vendingmachines WHERE vendingMachineCode = %s", (vending_machine_code,))
        vending_machine = cursor.fetchone()
        if not vending_machine:
            ws.send(json.dumps({"update_response": "Invalid vending machine code"}))
            return
        vending_machine_id = vending_machine[0]

        # Update product price
        query = """
            UPDATE products 
            SET productPrice = %s 
            WHERE vendingMachineId = %s AND productCode = %s
        """
        cursor.execute(query, (new_price, vending_machine_id, product_code))
        mysql.connection.commit()
        ws.send(json.dumps({"update_response": "Product price updated successfully"}))

    except Exception as e:
        ws.send(json.dumps({"update_response": str(e)}))

    finally:
        if cursor:
            cursor.close()

# Custom command functionality
def handle_custom_command(ws, data):
    vending_machine_code = data.get("vendingMachineCode")
    command = data.get("command")
    try:
        ws.send(json.dumps({"custom_command_response": f"Command '{command}' sent to vending machine '{vending_machine_code}'"}))
    except Exception as e:
        ws.send(json.dumps({"error": str(e)}))
        

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


# Run the Flask app
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=os.getenv('PORT', 3000), debug=True)
