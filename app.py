from flask import Flask, session, request, redirect, url_for, render_template
import pyodbc
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'replace-this-with-a-secret-key')

# Replace with your actual SQL Server connection string or use an environment variable
DB_CONNECTION_STRING = os.environ.get(
    'DB_CONNECTION_STRING',
    'DRIVER={ODBC Driver 17 for SQL Server};SERVER=your-server;DATABASE=your-db;UID=your-user;PWD=your-password'
)

def get_db_connection():
    return pyodbc.connect(DB_CONNECTION_STRING)

def check_login(username, password):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Users WHERE username=? AND password=?", (username, password))
    row = cursor.fetchone()
    print("Checking login for:", username, password)
    print("Query result row:", row)
    cursor.close()
    conn.close()
    return row is not None

@app.before_request
def require_login():
    allowed = [
        'login', 'static', 'search_store', 'search_supplier',
        'get_orders', 'get_suppliercode', 'update_orders'
    ]
    if 'user' not in session and request.endpoint not in allowed and not request.path.startswith('/logout'):
        return redirect(url_for('login'))

@app.route('/', methods=['GET', 'POST'])
def login():
    error = ''
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        print("Login form submitted: username={}, password={}".format(username, password))
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

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

# Add your other routes (search_store, search_supplier, etc.) here

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8000)
