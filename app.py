from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from models import db, User, Ticket, Attraction, MaintenanceRecord, Transaction
from datetime import datetime
import qrcode
import os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
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
    if request.method == 'POST':
        ticket_type = request.form['ticket_type']
        price = {'single': 10, 'daily': 30, 'group': 50}[ticket_type]
        ticket = Ticket(type=ticket_type, price=price, qr_code='qr_' + str(datetime.now().timestamp()))
        db.session.add(ticket)

        transaction = Transaction(amount=price, payment_method='card', status='completed')
        db.session.add(transaction)
        db.session.commit()

        # Generate QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(ticket.qr_code)
        qr.make(fit=True)
        qr_img = qr.make_image(fill='black', back_color='white')
        qr_img.save(f'static/qr_codes/{ticket.qr_code}.png')

        flash('Ticket purchased successfully!')
        return redirect(url_for('dashboard'))
    return render_template('ticket_purchase.html')

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

@app.route('/api/report', methods=['GET'])
def financial_report():
    if session.get('role') != 'manager':
        return jsonify({'error': 'Unauthorized'}), 403
    transactions = Transaction.query.all()
    total_revenue = sum(t.amount for t in transactions if t.status == 'completed')
    return jsonify({'total_revenue': total_revenue, 'transaction_count': len(transactions)})