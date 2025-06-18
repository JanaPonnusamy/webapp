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
        # Print what the user submitted
        print("Login form submitted: username={}, password={}".format(username, password))
        if check_login(username, password):
            session['user'] = username
            return redirect(url_for('dashboard'))
        else:
            error = 'Invalid credentials. Try again.'
    return render_template('login.html', error=error)

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
