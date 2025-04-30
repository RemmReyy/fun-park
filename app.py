from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from models import db, User, Ticket, Attraction, MaintenanceRecord, Transaction, TicketPrice
from datetime import datetime
import qrcode
import os
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# Завантажуємо змінні оточення з .env
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default-secret-key-for-dev')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///funpark.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Create database
with app.app_context():
    db.create_all()

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['role'] = user.role
            return redirect(url_for('dashboard'))
        flash('Invalid credentials')
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    role = session['role']
    attractions = Attraction.query.all()
    if role == 'manager':
        tickets = Ticket.query.all()
        transactions = Transaction.query.all()
        return render_template('dashboard.html', role=role, attractions=attractions, tickets=tickets, transactions=transactions)
    elif role == 'cashier':
        return render_template('dashboard.html', role=role, attractions=attractions)
    elif role == 'technician':
        maintenance_records = MaintenanceRecord.query.all()
        return render_template('dashboard.html', role=role, attractions=attractions, maintenance_records=maintenance_records)
    return render_template('dashboard.html', role=role, attractions=attractions)

@app.route('/ticket/purchase', methods=['GET', 'POST'])
def ticket_purchase():
    if 'user_id' not in session or session.get('role') != 'cashier':
        flash('Unauthorized access')
        return redirect(url_for('login'))

    if request.method == 'POST':
        try:
            ticket_type = request.form.get('ticket_type')
            if ticket_type not in ['single', 'daily', 'group']:
                flash('Invalid ticket type')
                return redirect(url_for('ticket_purchase'))

            ticket_price = TicketPrice.query.filter_by(ticket_type=ticket_type).first()
            if not ticket_price:
                flash('Ticket type not found')
                return redirect(url_for('ticket_purchase'))
            price = ticket_price.price

            qr_code = f"qr_{int(datetime.now().timestamp())}_{hash(ticket_type)}"
            ticket = Ticket(type=ticket_type, price=price, qr_code=qr_code)
            db.session.add(ticket)

            transaction = Transaction(amount=price, payment_method='card', status='completed')
            db.session.add(transaction)
            db.session.commit()

            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(ticket.qr_code)
            qr.make(fit=True)
            qr_img = qr.make_image(fill='black', back_color='white')
            qr_img.save(f'static/qr_codes/{qr_code}.png')

            flash('Ticket purchased successfully!')
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error purchasing ticket: {str(e)}')
            return redirect(url_for('ticket_purchase'))

    prices = TicketPrice.query.all()
    return render_template('ticket_purchase.html', prices=prices)

@app.route('/attraction/update/<int:id>', methods=['POST'])
def update_attraction(id):
    if session.get('role') not in ['technician', 'manager']:
        return jsonify({'error': 'Unauthorized'}), 403
    attraction = Attraction.query.get_or_404(id)
    status = request.form['status']
    attraction.status = status
    if status == 'maintenance':
        record = MaintenanceRecord(description=f'Maintenance for {attraction.name}', status='ongoing', technician_id=session['user_id'])
        db.session.add(record)
    db.session.commit()
    return jsonify({'message': 'Attraction updated'})

@app.route('/attraction/add', methods=['GET', 'POST'])
def add_attraction():
    if 'user_id' not in session or session.get('role') != 'manager':
        flash('Unauthorized access')
        return redirect(url_for('login'))

    if request.method == 'POST':
        try:
            name = request.form.get('name')
            capacity = request.form.get('capacity')
            status = request.form.get('status', 'active')

            if not name or not capacity:
                flash('Name and capacity are required')
                return redirect(url_for('add_attraction'))

            try:
                capacity = int(capacity)
                if capacity <= 0:
                    flash('Capacity must be a positive integer')
                    return redirect(url_for('add_attraction'))
            except ValueError:
                flash('Capacity must be a valid integer')
                return redirect(url_for('add_attraction'))

            if status not in ['active', 'maintenance', 'inactive']:
                flash('Invalid status')
                return redirect(url_for('add_attraction'))

            attraction = Attraction(name=name, capacity=capacity, status=status)
            db.session.add(attraction)
            db.session.commit()
            flash('Attraction added successfully!')
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding attraction: {str(e)}')
            return redirect(url_for('add_attraction'))

    return render_template('add_attraction.html')

@app.route('/ticket/prices', methods=['GET', 'POST'])
def manage_ticket_prices():
    if session.get('role') != 'manager':
        flash('Unauthorized access')
        return redirect(url_for('login'))

    if request.method == 'POST':
        ticket_type = request.form.get('ticket_type')
        price = request.form.get('price')
        try:
            price = float(price)
            if price <= 0:
                flash('Price must be positive')
                return redirect(url_for('manage_ticket_prices'))
        except ValueError:
            flash('Price must be a valid number')
            return redirect(url_for('manage_ticket_prices'))

        ticket_price = TicketPrice.query.filter_by(ticket_type=ticket_type).first()
        if ticket_price:
            ticket_price.price = price
            ticket_price.updated_at = datetime.utcnow()
        else:
            ticket_price = TicketPrice(ticket_type=ticket_type, price=price)
            db.session.add(ticket_price)
        db.session.commit()
        flash('Price updated successfully!')
        return redirect(url_for('manage_ticket_prices'))

    prices = TicketPrice.query.all()
    return render_template('ticket_prices.html', prices=prices)

@app.route('/api/report', methods=['GET'])
def financial_report():
    if session.get('role') != 'manager':
        return jsonify({'error': 'Unauthorized'}), 403
    transactions = Transaction.query.all()
    total_revenue = sum(t.amount for t in transactions if t.status == 'completed')
    return jsonify({'total_revenue': total_revenue, 'transaction_count': len(transactions)})