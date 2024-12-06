from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import pyodbc
import os
import logging

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

app.secret_key = os.getenv('FLASK_SECRET_KEY', '4b0eae123e2f86a8493d45f8d9f3c7f42c9d2a5b9f2e96b3f1e25c6b5734a8cb')

# Azure SQL Database connection settings
server = 'airline-flask-web.database.windows.net;'
database = 'airline;'
username = 'airlineticketsadmin;'
password = 'Rsk@2912;'
driver = '{ODBC Driver 17 for SQL Server}'

# Function to get a database connection
def get_db_connection():
    try:
        connection = pyodbc.connect(
            f'DRIVER={driver};SERVER={server};PORT=1433;DATABASE={database};UID={username};PWD={password}'
        )
        return connection
    except Exception as e:
        logging.error(f"Database connection error: {e}")
        raise

# Function to fetch tickets from Azure SQL Database
def fetch_tickets_from_sql():
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM Tickets")
    tickets = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
    connection.close()
    return tickets

@app.route('/')
def login():
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Save user to Azure SQL Database
        try:
            connection = get_db_connection()
            cursor = connection.cursor()
            cursor.execute(
                "INSERT INTO User_table (username, password) VALUES (?, ?)", 
                (username, password)
            )
            connection.commit()
            connection.close()
            return redirect(url_for('login'))
        except Exception as e:
            logging.error(f"Error saving user: {e}")
            return str(e)
    return render_template('register.html')

@app.route('/home', methods=['GET', 'POST'])
def home():
    # Fetch the data from Azure SQL Database (tickets)
    tickets = fetch_tickets_from_sql()

    # Get the logged-in user's username from the session
    username = session.get('username')

    # Apply filters from the form
    if request.method == 'POST':
        status_filter = request.form.get('statusFilter', 'all')
        price_filter = request.form.get('priceFilter', 'default')

        # Filter tickets based on the selected status
        if status_filter != 'all':
            tickets = [ticket for ticket in tickets if ticket['statuses'] == status_filter]

        # Sort tickets based on price filter
        if price_filter == 'high-low':
            tickets.sort(key=lambda x: x['price'], reverse=True)
        elif price_filter == 'low-high':
            tickets.sort(key=lambda x: x['price'])

    return render_template('home.html', tickets=tickets, username=username)



@app.route('/book/<ticket_id>', methods=['POST'])
def book_ticket(ticket_id):
    if 'username' not in session:
        return jsonify({'error': 'User not logged in.'}), 401

    username = session['username']

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Check if the ticket exists and is not already booked
        cursor.execute("SELECT * FROM Tickets WHERE ticket_id = ?", (ticket_id,))
        ticket = cursor.fetchone()
        if not ticket:
            return jsonify({'error': 'Ticket not found.'}), 404

        ticket_status = ticket[2]  # Assuming 'status' is the third column
        if ticket_status == 'booked':
            return jsonify({'error': 'Ticket already booked.'}), 400

        # Update the ticket status to "booked" and assign the username
        cursor.execute(
            "UPDATE Tickets SET statuses = ?, users = ? WHERE ticket_id = ?", 
            ('booked', username, ticket_id)
        )
        connection.commit()
        connection.close()

        return redirect(url_for('home'))
    except Exception as e:
        logging.error(f"Error booking ticket: {e}")
        return str(e)

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/login', methods=['POST'])
def login_user():
    username = request.form['username']
    password = request.form['password']

    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM User_table WHERE username = ?", (username,))
        user = cursor.fetchone()
        connection.close()

        if user and user[1] == password:  # Assuming 'password' is the second column
            session['username'] = username
            return redirect(url_for('home'))
        else:
            return "Invalid credentials, please try again."
    except Exception as e:
        logging.error(f"Error logging in: {e}")
        return str(e)
    
@app.route('/add_ticket', methods=['GET', 'POST'])
def add_ticket():
    if 'username' not in session:
        return jsonify({'error': 'User not logged in.'}), 401
    
    if request.method == 'POST':
        # Retrieve form data
        destination = request.form['destination']
        price = request.form['price']
        status = request.form['statuses']
        username = session['username']  # Get the username of the logged-in user

        # Generate the next ticket_id by checking the last one
        try:
            connection = get_db_connection()
            cursor = connection.cursor()

            # Retrieve the last ticket_id (assuming ticket_id is of format 'T001', 'T002', 'T119', etc.)
            cursor.execute("SELECT TOP 1 ticket_id FROM Tickets ORDER BY ticket_id DESC")
            last_ticket = cursor.fetchone()

            if last_ticket:
                # Extract the number from the ticket ID and increment it
                last_ticket_id = last_ticket[0]  # 'T119' for example
                ticket_number = int(last_ticket_id[1:])  # Get the number part, e.g., 119 from 'T119'
                new_ticket_number = ticket_number + 1
                # Generate new ticket_id in format 'T120'
                ticket_id = f"T{new_ticket_number:03d}"
            else:
                # If no tickets exist, start with 'T001'
                ticket_id = "T001"

            # Insert the new ticket into the database along with the username of the logged-in user
            cursor.execute(
                "INSERT INTO Tickets (ticket_id, source, destination, price, statuses, users) VALUES (?, ?, ?, ?, ?, ?)", 
                (ticket_id, request.form['source'], destination, price, status, username)
            )
            connection.commit()
            connection.close()

            # Redirect to home after successful insertion
            return redirect(url_for('home'))
        except Exception as e:
            logging.error(f"Error adding ticket: {e}")
            return str(e)

    # Render the add ticket form
    return render_template('addticket.html')


@app.route('/update_ticket/<ticket_id>', methods=['GET', 'POST'])
def update_ticket(ticket_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']

    if request.method == 'POST':
        destination = request.form['destination']
        price = request.form['price']
        status = request.form['statuses']

        try:
            connection = get_db_connection()
            cursor = connection.cursor()

            # Check if the ticket belongs to the logged-in user
            cursor.execute("SELECT * FROM Tickets WHERE ticket_id = ? AND users = ?", (ticket_id, username))
            ticket = cursor.fetchone()

            if not ticket:
                return jsonify({'error': 'You can only update your own tickets.'}), 403  # Unauthorized update attempt

            # Proceed with updating the ticket
            cursor.execute(
                "UPDATE Tickets SET destination = ?, price = ?, statuses = ? WHERE ticket_id = ?", 
                (destination, price, status, ticket_id)
            )
            connection.commit()
            connection.close()

            # Redirect to home after successful update
            return redirect(url_for('home'))
        except Exception as e:
            logging.error(f"Error updating ticket: {e}")
            return str(e)

    # Fetch ticket details for pre-filling the form
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM Tickets WHERE ticket_id = ?", (ticket_id,))
        ticket = cursor.fetchone()
        connection.close()
        
        if ticket and ticket[5] == username:  # Ensure the ticket belongs to the logged-in user
            ticket_data = dict(zip([column[0] for column in cursor.description], ticket))
            return render_template('update_ticket.html', ticket=ticket_data)
        else:
            return "Ticket not found or not authorized to update.", 403  # Unauthorized attempt
    except Exception as e:
        logging.error(f"Error fetching ticket: {e}")
    return "Ticket not found."


@app.route('/delete_ticket/<ticket_id>', methods=['POST'])
def delete_ticket(ticket_id):
    if 'username' not in session:
        return jsonify({'error': 'User not logged in.'}), 401
    
    try:
        # Connect to the database
        connection = get_db_connection()
        cursor = connection.cursor()

        # Check if the ticket exists and if the logged-in user is the one who booked it
        cursor.execute("SELECT * FROM Tickets WHERE ticket_id = ?", (ticket_id,))
        ticket = cursor.fetchone()
        
        if not ticket:
            return jsonify({'error': 'Ticket not found.'}), 404

        # Fetch column names dynamically
        column_names = [column[0] for column in cursor.description]

        # Check if the current user is the one who booked the ticket
        if 'users' not in column_names:
            return jsonify({'error': 'Column "users" does not exist in the Tickets table.'}), 500

        user_index = column_names.index('users')  # Dynamically find index of 'users' column
        if ticket[user_index] != session['username']:  # Use dynamic index
            return jsonify({'error': 'You can only delete your own tickets.'}), 403

        # Delete the ticket with the specified ticket_id
        cursor.execute("DELETE FROM Tickets WHERE ticket_id = ?", (ticket_id,))
        connection.commit()
        connection.close()

        # Redirect to home after successful deletion
        return redirect(url_for('home'))
    except Exception as e:
        logging.error(f"Error deleting ticket: {e}")
        return str(e)


if __name__ == '__main__':
    app.run(debug=True)
