import os
import sqlite3

from flask import Flask, flash, redirect, render_template, request, session
# from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

app.secret_key = os.getenv('SECRET_KEY', 'your_default_secret_key')

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
# Session(app)


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    conn = sqlite3.connect("finance.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Fetch stocks with sum of shares and total value
    stocks = cursor.execute('SELECT stock_symbol, SUM(shares) AS shares, SUM(total) AS total FROM trans WHERE user_id = ? GROUP BY stock_symbol HAVING SUM(shares) > 0', (session["user_id"], )).fetchall()
    
    # Fetch user's cash balance
    cash_row = cursor.execute('SELECT cash FROM users WHERE id = ?', (session["user_id"], )).fetchone()
    cash = cash_row["cash"] if cash_row is not None else 0
    
    # Calculate total value of all transactions (including buys and sells)
    total_row = cursor.execute('SELECT SUM(total) FROM trans WHERE user_id = ?', (session["user_id"], )).fetchone()
    total = total_row[0] if total_row[0] is not None else 0
    
    conn.close()
    
    return render_template("index.html", stocks=stocks, cash=cash, total=cash + total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("stock_symbol")
        shares = request.form.get("shares")
        
        if not shares.isdecimal() or int(shares) <= 0:
            return apology("Invalid number of shares", 403)
        
        shares = int(shares)
        stock_data = lookup(symbol)
        
        if stock_data is None:
            return apology("Invalid symbol", 403)
    
        cost = stock_data.get("price") * shares 
        
        conn = sqlite3.connect("finance.db")
        cursor = conn.cursor()
        
        # Get the user's cash
        cursor.execute("SELECT cash FROM users WHERE id = ?", (session['user_id'],))
        result = cursor.fetchone()
        
        if result is None:
            conn.close()
            return apology("User not found", 403)
        
        cash = result[0]
        
        if cash < cost:
            conn.close()
            return apology("Insufficient balance", 403)
        else:
            # Update user's cash
            cursor.execute("UPDATE users SET cash = ? WHERE id = ?", (round(cash - cost, 2), session['user_id']))
            
            # Insert new transaction
            cursor.execute("INSERT INTO trans (user_id, stock_symbol, shares, price, total, trans_type) VALUES (?, ?, ?, ?, ?, 'buy')", (session["user_id"], symbol, shares, stock_data["price"], cost))

            # Commit the transaction
            conn.commit()
            conn.close()
            
            return redirect("/")
    else:
        return render_template("buy.html")



@app.route("/history")
@login_required
def history():
    conn = sqlite3.connect("finance.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    stocks = cursor.execute('SELECT * FROM trans WHERE user_id=?', (session["user_id"], ))
    return render_template("history.html", stocks=stocks)
    

@app.route("/add_cash", methods=["GET", "POST"])
@login_required
def add_cash():
    if request.method == "POST":
        cash = request.form.get("cash")

        # Validate the input
        if not cash.isdecimal() or float(cash) <= 0:
            return apology("Invalid cash amount", 403)
        
        cash = float(cash)
        
        conn = sqlite3.connect("finance.db")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get existing cash
        cash_exist = cursor.execute('SELECT cash FROM users WHERE id = ?', (session["user_id"],)).fetchone()
        
        if cash_exist is None:
            conn.close()
            return apology("User not found", 403)

        # Update the cash
        new_cash = cash_exist["cash"] + cash
        cursor.execute('UPDATE users SET cash = ? WHERE id = ?', (new_cash, session["user_id"]))
        
        conn.commit()
        conn.close()
        
        return redirect("/")
    else:
        return render_template("addcash.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    session.clear()
    
    conn = sqlite3.connect("finance.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        if not username:
            conn.close()
            return apology("must provide username", 403)
        
        if not password:
            conn.close()
            return apology("must provide password", 403)
        
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        
        if row is None or not check_password_hash(row["hash"], password):
            conn.close()
            return apology("invalid username and/or password", 403)
        
        session["user_id"] = row["id"]
        
        conn.close()
        return redirect("/")
    else:
        conn.close()
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""
    session.clear()
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote"""
    if request.method == "POST":
        stock_symbol = request.form.get("stock_symbol")
        stock_data = lookup(stock_symbol)
        
        if stock_data is None:
            return apology("Stock Symbol does not exist", 403)
        
        return render_template("stockQuote.html", price=round(stock_data["price"], 2), symbol=stock_data["symbol"])
    else:
        return render_template("getQuote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    conn = sqlite3.connect("finance.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirm_password = request.form.get("confirmation")
        
        if not username:
            conn.close()
            return apology("must provide username", 400)
        
        if not password:
            conn.close()
            return apology("must provide password", 400)
        
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        row = cursor.fetchone()
        
        if row:
            conn.close()
            return apology("username already exists", 400)
        
        if password != confirm_password:
            conn.close()
            return apology("Passwords do not match", 400)
        
        hash_pass = generate_password_hash(password)
        cursor.execute("INSERT INTO users (username, hash) VALUES (?, ?)", (username, hash_pass))
        
        conn.commit()
        
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        session["user_id"] = user["id"]
        
        conn.close()
        return redirect("/")
    
    else:
        conn.close()
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        conn = sqlite3.connect("finance.db")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        shares = request.form.get("shares")
        symbol = request.form.get("symbol")
        
        stock_data = lookup(symbol)
        if stock_data is None:
            return apology("Stock not found", 403)
        
        if not shares.isdecimal() or int(shares) <= 0:
            return apology("Invalid Shares", 403)

        shares = int(shares)
        shares_exist = cursor.execute('SELECT SUM(shares) as total_shares FROM trans WHERE user_id = ? AND stock_symbol = ?', (session["user_id"], symbol)).fetchone()["total_shares"]

        if shares_exist is None or shares > shares_exist:
            conn.close()
            return apology("You don't own that many shares", 403)
        
        sold_price = stock_data["price"] * shares  # CURRENT PRICE OF STOCK * NO. OF SHARES
        
        # UPDATE DATABASE
        cash = cursor.execute('SELECT cash FROM users WHERE id = ?', (session["user_id"],)).fetchone()["cash"]
        
        cursor.execute('UPDATE users SET cash = ? WHERE id = ?', (cash + sold_price, session["user_id"]))
        
        # Insert new transaction for the sale
        cursor.execute("INSERT INTO trans (user_id, stock_symbol, shares, price, total, trans_type) VALUES (?, ?, ?, ?, ?, 'sell')", (session["user_id"], symbol, -shares, stock_data["price"], -sold_price))

        conn.commit()
        conn.close()
        
        return redirect("/")
    
    else:
        conn = sqlite3.connect("finance.db")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        stocks = cursor.execute('SELECT stock_symbol, SUM(shares) as total_shares FROM trans WHERE user_id = ? GROUP BY stock_symbol HAVING total_shares > 0', (session["user_id"], )).fetchall()
        conn.close()
        
        return render_template("sell.html", stocks=stocks)


