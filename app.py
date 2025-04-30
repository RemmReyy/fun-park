from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, send_file
from models import db, User, Ticket, Attraction, MaintenanceRecord, Transaction, TicketPrice
from datetime import datetime, timedelta
import qrcode
import os
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from io import BytesIO

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
        flash('Невірні дані для входу')
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
        flash('Несанкціонований доступ')
        return redirect(url_for('login'))

    if request.method == 'POST':
        try:
            ticket_type = request.form.get('ticket_type')
            if ticket_type not in ['single', 'daily', 'group']:
                flash('Невірний тип квитка')
                return redirect(url_for('ticket_purchase'))

            ticket_price = TicketPrice.query.filter_by(ticket_type=ticket_type).first()
            if not ticket_price:
                flash('Тип квитка не знайдено')
                return redirect(url_for('ticket_purchase'))
            price = ticket_price.price

            qr_code = f"qr_{int(datetime.now().timestamp())}_{hash(ticket_type)}"
            ticket = Ticket(type=ticket_type, price=price, qr_code=qr_code, status='active')
            db.session.add(ticket)
            db.session.commit()  # Commit to get ticket.id

            transaction = Transaction(
                ticket_id=ticket.id,  # Link transaction to ticket
                amount=price,
                payment_method='card',
                status='completed',
                transaction_type='purchase'
            )
            db.session.add(transaction)
            db.session.commit()

            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(ticket.qr_code)
            qr.make(fit=True)
            qr_img = qr.make_image(fill='black', back_color='white')
            qr_img.save(f'static/qr_codes/{qr_code}.png')

            flash('Квиток успішно придбано!')
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Помилка при купівлі квитка: {str(e)}')
            return redirect(url_for('ticket_purchase'))

    prices = TicketPrice.query.all()
    return render_template('ticket_purchase.html', prices=prices)

@app.route('/ticket/refund_exchange', methods=['GET', 'POST'])
def refund_exchange():
    if 'user_id' not in session or session.get('role') != 'cashier':
        flash('Несанкціонований доступ')
        return redirect(url_for('login'))

    ticket = None
    prices = TicketPrice.query.all()

    if request.method == 'POST':
        action = request.form.get('action')  # refund or exchange
        qr_code = request.form.get('qr_code')

        # Find ticket by QR code
        ticket = Ticket.query.filter_by(qr_code=qr_code).first()
        if not ticket:
            flash('Квиток не знайдено')
            return redirect(url_for('refund_exchange'))

        if ticket.status != 'active':
            flash('Квиток не може бути повернений або обміняний (вже використаний, повернений або обміняний)')
            return redirect(url_for('refund_exchange'))

        # Find the associated purchase transaction
        purchase_transaction = Transaction.query.filter_by(ticket_id=ticket.id, transaction_type='purchase', status='completed').first()
        if not purchase_transaction:
            flash('Транзакція покупки не знайдена')
            return redirect(url_for('refund_exchange'))

        try:
            if action == 'refund':
                # Mark ticket as refunded
                ticket.status = 'refunded'

                # Create a refund transaction
                refund_transaction = Transaction(
                    ticket_id=ticket.id,  # Link refund to ticket
                    amount=-purchase_transaction.amount,  # Negative amount for refund
                    payment_method=purchase_transaction.payment_method,
                    status='completed',
                    transaction_type='refund'
                )
                db.session.add(refund_transaction)
                db.session.commit()
                flash('Квиток успішно повернено!')

            elif action == 'exchange':
                new_ticket_type = request.form.get('new_ticket_type')
                if new_ticket_type not in ['single', 'daily', 'group']:
                    flash('Невірний тип квитка для обміну')
                    return redirect(url_for('refund_exchange'))

                new_price = TicketPrice.query.filter_by(ticket_type=new_ticket_type).first()
                if not new_price:
                    flash('Ціна для нового типу квитка не знайдена')
                    return redirect(url_for('refund_exchange'))
                new_price = new_price.price

                # Mark old ticket as exchanged
                ticket.status = 'exchanged'

                # Create a new ticket
                new_qr_code = f"qr_{int(datetime.now().timestamp())}_{hash(new_ticket_type)}"
                new_ticket = Ticket(type=new_ticket_type, price=new_price, qr_code=new_qr_code, status='active')
                db.session.add(new_ticket)
                db.session.commit()  # Commit to get new_ticket.id

                # Calculate price difference and create an exchange transaction
                price_difference = new_price - ticket.price
                exchange_transaction = Transaction(
                    ticket_id=new_ticket.id,  # Link exchange to new ticket
                    amount=price_difference,  # Positive if upgrade, negative if downgrade
                    payment_method=purchase_transaction.payment_method,
                    status='completed',
                    transaction_type='exchange'
                )
                db.session.add(exchange_transaction)

                # Generate new QR code
                qr = qrcode.QRCode(version=1, box_size=10, border=5)
                qr.add_data(new_qr_code)
                qr.make(fit=True)
                qr_img = qr.make_image(fill='black', back_color='white')
                qr_img.save(f'static/qr_codes/{new_qr_code}.png')

                db.session.commit()
                flash(f'Квиток успішно обміняно! Різниця в ціні: ${price_difference:.2f}')

        except Exception as e:
            db.session.rollback()
            flash(f'Помилка при обробці: {str(e)}')
            return redirect(url_for('refund_exchange'))

    return render_template('refund_exchange.html', ticket=ticket, prices=prices)

@app.route('/attraction/update/<int:id>', methods=['POST'])
def update_attraction(id):
    if session.get('role') not in ['technician', 'manager']:
        return jsonify({'error': 'Несанкціонований доступ'}), 403
    attraction = Attraction.query.get_or_404(id)
    status = request.form['status']
    attraction.status = status
    if status == 'maintenance':
        record = MaintenanceRecord(description=f'Обслуговування {attraction.name}', status='ongoing', technician_id=session['user_id'])
        db.session.add(record)
    db.session.commit()
    return jsonify({'message': 'Атракціон оновлено'})

@app.route('/attraction/add', methods=['GET', 'POST'])
def add_attraction():
    if 'user_id' not in session or session.get('role') != 'manager':
        flash('Несанкціонований доступ')
        return redirect(url_for('login'))

    if request.method == 'POST':
        try:
            name = request.form.get('name')
            capacity = request.form.get('capacity')
            status = request.form.get('status', 'active')

            if not name or not capacity:
                flash('Назва та місткість обов’язкові')
                return redirect(url_for('add_attraction'))

            try:
                capacity = int(capacity)
                if capacity <= 0:
                    flash('Місткість повинна бути додатною')
                    return redirect(url_for('add_attraction'))
            except ValueError:
                flash('Місткість повинна бути цілим числом')
                return redirect(url_for('add_attraction'))

            if status not in ['active', 'maintenance', 'inactive']:
                flash('Невірний статус')
                return redirect(url_for('add_attraction'))

            attraction = Attraction(name=name, capacity=capacity, status=status)
            db.session.add(attraction)
            db.session.commit()
            flash('Атракціон успішно додано!')
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Помилка при додаванні атракціону: {str(e)}')
            return redirect(url_for('add_attraction'))

    return render_template('add_attraction.html')

@app.route('/ticket/prices', methods=['GET', 'POST'])
def manage_ticket_prices():
    if session.get('role') != 'manager':
        flash('Несанкціонований доступ')
        return redirect(url_for('login'))

    if request.method == 'POST':
        ticket_type = request.form.get('ticket_type')
        price = request.form.get('price')
        try:
            price = float(price)
            if price <= 0:
                flash('Ціна повинна бути додатною')
                return redirect(url_for('manage_ticket_prices'))
        except ValueError:
            flash('Ціна повинна бути дійсним числом')
            return redirect(url_for('manage_ticket_prices'))

        ticket_price = TicketPrice.query.filter_by(ticket_type=ticket_type).first()
        if ticket_price:
            ticket_price.price = price
            ticket_price.updated_at = datetime.utcnow()
        else:
            ticket_price = TicketPrice(ticket_type=ticket_type, price=price)
            db.session.add(ticket_price)
        db.session.commit()
        flash('Ціну успішно оновлено!')
        return redirect(url_for('manage_ticket_prices'))

    prices = TicketPrice.query.all()
    return render_template('ticket_prices.html', prices=prices)

@app.route('/api/report', methods=['GET'])
def financial_report():
    if session.get('role') != 'manager':
        return jsonify({'error': 'Несанкціонований доступ'}), 403

    period = request.args.get('period', 'all')  # day, week, month, all
    transactions = Transaction.query

    if period == 'day':
        start_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        transactions = transactions.filter(Transaction.timestamp >= start_date)
    elif period == 'week':
        start_date = datetime.utcnow() - timedelta(days=datetime.utcnow().weekday())
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        transactions = transactions.all()
        transactions = [t for t in transactions if t.timestamp >= start_date]
    elif period == 'month':
        start_date = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        transactions = transactions.filter(Transaction.timestamp >= start_date)

    transactions = transactions.all()
    total_revenue = sum(t.amount for t in transactions if t.status == 'completed')
    ticket_types = {}
    refund_types = {}

    for t in transactions:
        if t.ticket_id:  # Ensure ticket_id exists
            ticket = Ticket.query.get(t.ticket_id)
            if ticket and t.status == 'completed':
                if t.transaction_type == 'purchase':
                    ticket_types[ticket.type] = ticket_types.get(ticket.type, 0) + 1
                elif t.transaction_type == 'refund':
                    refund_types[ticket.type] = refund_types.get(ticket.type, 0) + 1

    # Count total refunds
    refund_count = len([t for t in transactions if t.status == 'completed' and t.transaction_type == 'refund'])

    return jsonify({
        'total_revenue': total_revenue,
        'transaction_count': len([t for t in transactions if t.status == 'completed' and t.transaction_type == 'purchase']),
        'refund_count': refund_count,
        'refund_types': refund_types,
        'ticket_types': ticket_types
    })

@app.route('/api/report/pdf', methods=['GET'])
def financial_report_pdf():
    if session.get('role') != 'manager':
        return jsonify({'error': 'Несанкціонований доступ'}), 403

    period = request.args.get('period', 'all')  # day, week, month, all
    transactions = Transaction.query

    if period == 'day':
        start_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        transactions = transactions.filter(Transaction.timestamp >= start_date)
    elif period == 'week':
        start_date = datetime.utcnow() - timedelta(days=datetime.utcnow().weekday())
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        transactions = transactions.all()
        transactions = [t for t in transactions if t.timestamp >= start_date]
    elif period == 'month':
        start_date = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        transactions = transactions.filter(Transaction.timestamp >= start_date)

    transactions = transactions.all()
    total_revenue = sum(t.amount for t in transactions if t.status == 'completed')
    ticket_types = {}
    refund_types = {}

    for t in transactions:
        if t.ticket_id:  # Ensure ticket_id exists
            ticket = Ticket.query.get(t.ticket_id)
            if ticket and t.status == 'completed':
                if t.transaction_type == 'purchase':
                    ticket_types[ticket.type] = ticket_types.get(ticket.type, 0) + 1
                elif t.transaction_type == 'refund':
                    refund_types[ticket.type] = refund_types.get(ticket.type, 0) + 1

    # Count total refunds
    refund_count = len([t for t in transactions if t.status == 'completed' and t.transaction_type == 'refund'])

    # Generate PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []

    # Title
    period_name = {'all': 'All Time', 'day': 'Daily', 'week': 'Weekly', 'month': 'Monthly'}[period]
    elements.append(Paragraph(f"Financial Report: {period_name}", styles['Title']))
    elements.append(Spacer(1, 12))

    # Summary
    elements.append(Paragraph(f"Date Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
    elements.append(Paragraph(f"Total Revenue: ${total_revenue:.2f}", styles['Normal']))
    elements.append(Paragraph(f"Number of Transactions: {len([t for t in transactions if t.status == 'completed' and t.transaction_type == 'purchase'])}", styles['Normal']))
    elements.append(Paragraph(f"Number of Refunds: {refund_count}", styles['Normal']))

    # Refund Types
    if refund_types:
        elements.append(Paragraph("Refunds by Ticket Type:", styles['Heading2']))
        refund_data = [['Ticket Type', 'Count']]
        for ticket_type, count in refund_types.items():
            refund_data.append([ticket_type.capitalize(), str(count)])
        refund_table = Table(refund_data)
        refund_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(refund_table)
    else:
        elements.append(Paragraph("Refunds by Ticket Type: None", styles['Normal']))
    elements.append(Spacer(1, 12))

    # Ticket Types Table
    elements.append(Paragraph("Breakdown by Ticket Types:", styles['Heading2']))
    data = [['Ticket Type', 'Count']]
    for ticket_type, count in ticket_types.items():
        data.append([ticket_type.capitalize(), str(count)])
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(table)

    # Build PDF
    doc.build(elements)
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name=f"financial_report_{period}_{datetime.utcnow().strftime('%Y%m%d')}.pdf", mimetype='application/pdf')