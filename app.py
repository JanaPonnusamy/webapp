from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import pymssql
import os
from dotenv import load_dotenv

# Load environment variables from webapp.env
load_dotenv('webapp.env')

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'fallback_secret_key')

# Database connection details from .env
db_server = os.environ.get('DB_SERVER')
db_user = os.environ.get('DB_USER')
db_password = os.environ.get('DB_PASSWORD')
db_name = os.environ.get('DB_NAME')

def get_db_connection():
    return pymssql.connect(server=db_server, user=db_user, password=db_password, database=db_name)

# Check credentials in Users table
def check_login(username, password):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM Users WHERE Username=%s AND Password=%s", (username, password))
        row = cursor.fetchone()
        conn.close()
        return row is not None
    except Exception as e:
        print("Database error:", e)
        return False

@app.before_request
def require_login():
    allowed = ['login', 'static', 'search_store', 'search_supplier', 'get_orders', 'get_suppliercode', 'update_orders']
    if 'user' not in session and request.endpoint not in allowed and not request.path.startswith('/logout'):
        return redirect(url_for('login'))

@app.route('/', methods=['GET', 'POST'])
def login():
    error = ''
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if check_login(username, password):
            session['user'] = username
            return redirect(url_for('dashboard'))
        else:
            error = 'Invalid credentials. Try again.'
    return render_template('login.html', error=error)

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html', user=session['user'])

@app.route('/search_store')
def search_store():
    query = request.args.get('q', '')
    matches = []
    if query:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT TOP 10 StoreName FROM Stores WHERE StoreName LIKE %s AND isactive=1", ('%' + query + '%',))
            matches = [row[0] for row in cursor.fetchall()]
            conn.close()
        except Exception as e:
            print("DB error:", e)
    return jsonify(matches)

@app.route('/search_supplier')
def search_supplier():
    query = request.args.get('q', '')
    store = request.args.get('store', '')
    matches = []
    if query and store:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT TOP 10 SupplierName 
                FROM OrderSuppliers 
                WHERE SupplierName LIKE %s AND StoreName = %s
            """, ('%' + query + '%', store))
            matches = [row[0] for row in cursor.fetchall()]
            conn.close()
        except Exception as e:
            print("DB error (supplier):", e)
    return jsonify(matches)

@app.route('/get_orders')
def get_orders():
    suppliercode = request.args.get('suppliercode', '')
    storename = request.args.get('storename', '')
    results = []
    if not suppliercode or not storename:
        return jsonify([])
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        query = """
            SELECT productcode, productname, OrderQty, saleunit, mrp, orsupplier, remarks, OrderId, StoreCode
            FROM ordermanagement
            WHERE status = 1
              AND orsuppliercode IN (SELECT Value FROM dbo.SplitString(%s, ','))
              AND storename = %s
              AND orderqty > 0
            ORDER BY productname
        """
        cursor.execute(query, (suppliercode, storename))
        rows = cursor.fetchall()
        for idx, row in enumerate(rows, start=1):
            results.append({
                'SerialNo': idx,
                'ProductCode': row[0],
                'ProductName': row[1],
                'OrderQty': row[2],
                'SaleUnit': row[3],
                'MRP': row[4],
                'ORSUPPLIER': row[5],
                'Remarks': row[6] if row[6] else '',
                'OrderId': row[7],
                'StoreCode': row[8]
            })
        conn.close()
    except Exception as e:
        print("Error fetching orders:", e)
    return jsonify(results)

@app.route('/get_suppliercode')
def get_suppliercode():
    suppliername = request.args.get('suppliername', '')
    storename = request.args.get('storename', '')
    code = ''
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT TOP 1 SupplierCode FROM OrderSuppliers WHERE SupplierName=%s AND StoreName=%s", (suppliername, storename))
        row = cursor.fetchone()
        if row:
            code = row[0]
        conn.close()
    except Exception as e:
        print("Error fetching supplier code:", e)
    return jsonify({'suppliercode': code})

@app.route('/update_orders', methods=['POST'])
def update_orders():
    data = request.json
    print(f"Received data from frontend: {data}")
    updated_items = data.get('updatedData', [])
    if not updated_items:
        return jsonify({'success': False, 'message': 'No data to update.'})
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        for item in updated_items:
            product_code = item.get('ProductCode')
            product_name = item.get('ProductName')
            edit_qty = item.get('EditQty')
            or_qty = item.get('OrQty')
            diff_qty = item.get('Diffqty')
            sale_unit = item.get('SaleUnit')
            wanted_type = item.get('WantedType', 'NA')
            status_text = item.get('Status')
            web_remarks = item.get('webRemarks')
            order_id = item.get('OrderId')
            item_store_name = item.get('StoreName')
            item_store_code = item.get('StoreCode')
            cursor.execute("""
                SELECT COUNT(*) FROM weborderstatus
                WHERE OrderId = %s AND ProductCode = %s
            """, (order_id, product_code))
            exists = cursor.fetchone()[0] > 0
            if exists:
                update_query = """
                    UPDATE weborderstatus
                    SET
                        EditQty = %s,
                        Diffqty = %s,
                        Status = %s,
                        webRemarks = %s,
                        OrQty = %s,
                        ProductName = %s,
                        SaleUnit = %s,
                        WantedType = %s,
                        StoreName = %s,
                        StoreCode = %s
                    WHERE OrderId = %s AND ProductCode = %s
                """
                params = (edit_qty, diff_qty, status_text, web_remarks, or_qty,
                          product_name, sale_unit, wanted_type, item_store_name, item_store_code,
                          order_id, product_code)
                cursor.execute(update_query, params)
            else:
                insert_query = """
                    INSERT INTO weborderstatus (
                        ProductCode, ProductName, Diffqty, SaleUnit, WantedType,
                        Status, EditQty, OrQty, webRemarks, OrderId, StoreName, StoreCode
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                params = (product_code, product_name, diff_qty, sale_unit, wanted_type,
                          status_text, edit_qty, or_qty, web_remarks, order_id, item_store_name, item_store_code)
                cursor.execute(insert_query, params)
        conn.commit()
        return jsonify({'success': True, 'message': 'Orders updated successfully.'})
    except Exception as e:
        print("Error updating weborderstatus:", e)
        if conn:
            conn.rollback()
        return jsonify({'success': False, 'message': f'Database error: {str(e)}'})
    finally:
        if conn:
            conn.close()

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
