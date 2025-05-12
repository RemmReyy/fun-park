from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, send_file
from models import db, User, Ticket, Attraction, MaintenanceRecord, Transaction, TicketPrice, Queue
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
@app.route('/index')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

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
        flash('Невірні дані для входу', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Ви успішно вийшли з системи!', 'success')
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    role = user.role
    if role == 'manager':
        attractions = Attraction.query.all()
    elif role == 'technician':
        attractions = Attraction.query.filter_by(status='maintenance').all()
    elif role == 'cashier':
        attractions = Attraction.query.filter_by(status='active').all()
    elif role == 'operator':
        attractions = Attraction.query.filter_by(status='active').all()
    else:
        attractions = []
    queues = {attraction.id: Queue.query.filter_by(attraction_id=attraction.id).order_by(Queue.position).all() for attraction in attractions}

    maintenance_records = MaintenanceRecord.query.all()
    maintenance_data = [
        {
            'id': record.id,
            'description': record.description,
            'status': record.status,
            'date': record.date,
            'technician_name': User.query.get(record.technician_id).username if record.technician_id else 'Невідомий',
            'attraction_name': Attraction.query.get(record.attraction_id).name if record.attraction_id else 'Невідомий'
        }
        for record in maintenance_records
    ]

    return render_template('dashboard.html', role=role, attractions=attractions, queues=queues, maintenance_records=maintenance_data)

@app.route('/ticket/purchase', methods=['GET', 'POST'])
def ticket_purchase():
    if 'user_id' not in session or session.get('role') != 'cashier':
        flash('Несанкціонований доступ')
        return redirect(url_for('login'))

    if request.method == 'POST':
        print(f"Received form data: {request.form}")  # Debug print

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

            if ticket_type == 'single':
                attraction_id = request.form.get('attraction_id')
                if not attraction_id or attraction_id == '':
                    flash('Оберіть атракціон для одиничного квитка')
                    return redirect(url_for('ticket_purchase'))
                attraction = Attraction.query.get(int(attraction_id))
                if not attraction:
                    flash('Атракціон не знайдено')
                    return redirect(url_for('ticket_purchase'))
                if attraction.status != 'active':
                    flash('Обраний атракціон неактивний або на обслуговуванні')
                    return redirect(url_for('ticket_purchase'))
                ticket.attraction_id = int(attraction_id)
            elif ticket_type == 'daily':
                ticket.valid_until = datetime.utcnow() + timedelta(days=1)  # Valid for 24 hours
            elif ticket_type == 'group':
                group_size = request.form.get('group_size')
                try:
                    group_size = int(group_size) if group_size else 0
                    if group_size < 2 or group_size > 10:
                        flash('Розмір групи має бути від 2 до 10 осіб')
                        return redirect(url_for('ticket_purchase'))
                    ticket.group_size = group_size
                except ValueError:
                    flash('Розмір групи має бути цілим числом')
                    return redirect(url_for('ticket_purchase'))

            db.session.add(ticket)
            db.session.commit()  # Commit to get ticket.id

            transaction = Transaction(
                ticket_id=ticket.id,
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
    attractions = Attraction.query.all()
    return render_template('ticket_purchase.html', prices=prices, attractions=attractions)

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

        ticket = Ticket.query.filter_by(qr_code=qr_code).first()
        if not ticket:
            flash('Квиток не знайдено')
            return redirect(url_for('refund_exchange'))

        if ticket.status != 'active':
            flash('Квиток не може бути повернений або обміняний')
            return redirect(url_for('refund_exchange'))

        purchase_transaction = Transaction.query.filter_by(ticket_id=ticket.id, transaction_type='purchase', status='completed').first()
        if not purchase_transaction:
            flash('Транзакція покупки не знайдена')
            return redirect(url_for('refund_exchange'))

        try:
            if action == 'refund':
                ticket.status = 'refunded'
                refund_transaction = Transaction(
                    ticket_id=ticket.id,
                    amount=-purchase_transaction.amount,
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

                new_price = TicketPrice.query.filter_by(ticket_type=new_ticket_type).first().price
                ticket.status = 'exchanged'
                new_qr_code = f"qr_{int(datetime.now().timestamp())}_{hash(new_ticket_type)}"
                new_ticket = Ticket(type=new_ticket_type, price=new_price, qr_code=new_qr_code, status='active')

                if new_ticket_type == 'single':
                    new_ticket.attraction_id = ticket.attraction_id
                elif new_ticket_type == 'daily':
                    new_ticket.valid_until = datetime.utcnow() + timedelta(days=1)
                elif new_ticket_type == 'group':
                    new_ticket.group_size = ticket.group_size

                db.session.add(new_ticket)
                db.session.commit()

                price_difference = new_price - ticket.price
                exchange_transaction = Transaction(
                    ticket_id=new_ticket.id,
                    amount=price_difference,
                    payment_method=purchase_transaction.payment_method,
                    status='completed',
                    transaction_type='exchange'
                )
                db.session.add(exchange_transaction)

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
    if 'technician' in request.form.get('role', ''):
        attraction = Attraction.query.get_or_404(id)
        new_status = request.form.get('status')
        if new_status in ['active', 'maintenance', 'inactive']:
            attraction.status = new_status
            db.session.commit()
            flash('Статус атракціону оновлено!', 'success')
        else:
            flash('Недопустимий статус.', 'error')
        return redirect(url_for('dashboard'))
    flash('Доступ заборонено.', 'error')
    return redirect(url_for('dashboard'))

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

    period = request.args.get('period', 'all')
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
        if t.ticket_id:
            ticket = Ticket.query.get(t.ticket_id)
            if ticket and t.status == 'completed':
                if t.transaction_type == 'purchase':
                    ticket_types[ticket.type] = ticket_types.get(ticket.type, 0) + 1
                elif t.transaction_type == 'refund':
                    refund_types[ticket.type] = refund_types.get(ticket.type, 0) + 1

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

    period = request.args.get('period', 'all')
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
        if t.ticket_id:
            ticket = Ticket.query.get(t.ticket_id)
            if ticket and t.status == 'completed':
                if t.transaction_type == 'purchase':
                    ticket_types[ticket.type] = ticket_types.get(ticket.type, 0) + 1
                elif t.transaction_type == 'refund':
                    refund_types[ticket.type] = refund_types.get(ticket.type, 0) + 1

    refund_count = len([t for t in transactions if t.status == 'completed' and t.transaction_type == 'refund'])

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []

    period_name = {'all': 'All Time', 'day': 'Daily', 'week': 'Weekly', 'month': 'Monthly'}[period]
    elements.append(Paragraph(f"Financial Report: {period_name}", styles['Title']))
    elements.append(Spacer(1, 12))

    elements.append(Paragraph(f"Date Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
    elements.append(Paragraph(f"Total Revenue: ${total_revenue:.2f}", styles['Normal']))
    elements.append(Paragraph(f"Number of Transactions: {len([t for t in transactions if t.status == 'completed' and t.transaction_type == 'purchase'])}", styles['Normal']))
    elements.append(Paragraph(f"Number of Refunds: {refund_count}", styles['Normal']))

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

    doc.build(elements)
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name=f"financial_report_{period}_{datetime.utcnow().strftime('%Y%m%d')}.pdf", mimetype='application/pdf')

@app.route('/queue/add', methods=['POST'])
def add_to_queue():
    if 'user_id' not in session or session.get('role') != 'operator':
        flash('Несанкціонований доступ')
        return redirect(url_for('login'))

    qr_code = request.form.get('qr_code')
    attraction_id = request.form.get('attraction_id')

    attraction = Attraction.query.get(attraction_id)
    if not attraction:
        flash('Атракціон не знайдено')
        return redirect(url_for('dashboard'))

    if attraction.status != 'active':
        flash('Атракціон неактивний або на обслуговуванні')
        return redirect(url_for('dashboard'))

    ticket = Ticket.query.filter_by(qr_code=qr_code).first()
    if not ticket:
        flash('Квиток не знайдено')
        return redirect(url_for('dashboard'))

    # Check ticket validity based on type
    if ticket.status != 'active':
        flash('Квиток не може бути використаний')
        return redirect(url_for('dashboard'))

    if ticket.type == 'daily' and ticket.valid_until and datetime.utcnow() > ticket.valid_until:
        flash('Термін дії щоденного квитка закінчився')
        return redirect(url_for('dashboard'))

    if ticket.type == 'single' and ticket.attraction_id and ticket.attraction_id != int(attraction_id):
        flash('Цей одиничний квиток дійсний лише для іншого атракціону')
        return redirect(url_for('dashboard'))

    existing_queue = Queue.query.filter_by(ticket_id=ticket.id).first()
    if existing_queue:
        flash('Квиток уже в черзі')
        return redirect(url_for('dashboard'))

    current_queue_size = Queue.query.filter_by(attraction_id=attraction_id).count()
    if current_queue_size >= attraction.capacity:
        flash('Черга на атракціон повна')
        return redirect(url_for('dashboard'))

    try:
        last_position = Queue.query.filter_by(attraction_id=attraction_id).order_by(Queue.position.desc()).first()
        next_position = last_position.position + 1 if last_position else 1

        queue_entry = Queue(attraction_id=attraction_id, ticket_id=ticket.id, position=next_position)
        db.session.add(queue_entry)
        db.session.commit()
        flash('Квиток успішно додано в чергу!')
    except Exception as e:
        db.session.rollback()
        flash(f'Помилка при додаванні в чергу: {str(e)}')

    return redirect(url_for('dashboard'))

@app.route('/queue/process/<int:queue_id>', methods=['POST'])
def process_queue(queue_id):
    if 'user_id' not in session or session.get('role') != 'operator':
        return jsonify({'error': 'Несанкціонований доступ'}), 403

    queue_entry = Queue.query.get(queue_id)
    if not queue_entry:
        return jsonify({'error': 'Запис у черзі не знайдено'}), 404

    ticket = Ticket.query.get(queue_entry.ticket_id)
    if not ticket:
        return jsonify({'error': 'Квиток не знайдено'}), 404

    try:
        if ticket.type == 'daily':
            ticket.used_count = (ticket.used_count or 0) + 1
            if ticket.used_count >= 5:  # Limit to 5 uses per day
                ticket.status = 'used'
        elif ticket.type in ['single', 'group']:
            ticket.status = 'used'

        db.session.delete(queue_entry)

        remaining_entries = Queue.query.filter_by(attraction_id=queue_entry.attraction_id).order_by(Queue.position).all()
        for index, entry in enumerate(remaining_entries, start=1):
            entry.position = index

        db.session.commit()
        return jsonify({'message': 'Відвідувача пропущено на атракціон!'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Помилка при обробці черги: {str(e)}'}), 500

@app.route('/attraction/delete/<int:id>', methods=['POST'])
def delete_attraction(id):
    attraction = Attraction.query.get_or_404(id)
    if attraction:
        # Видаляємо пов’язані записи черги
        Queue.query.filter_by(attraction_id=id).delete()
        # Видаляємо пов’язані одиничні квитки
        Ticket.query.filter_by(attraction_id=id, type='single').delete()
        # Видаляємо сам атракціон
        db.session.delete(attraction)
        db.session.commit()
        flash('Атракціон успішно видалено!', 'success')
    else:
        flash('Атракціон не знайдено.', 'error')
    return redirect(url_for('dashboard'))

@app.route('/maintenance/add', methods=['GET', 'POST'])
def add_maintenance():
    if request.method == 'POST' and 'technician' in request.form.get('role', ''):
        description = request.form.get('description')
        attraction_id = request.form.get('attraction_id')
        status = request.form.get('status', 'ongoing')

        if not description or not attraction_id:
            flash('Опис і атракціон є обов’язковими!', 'error')
            return redirect(url_for('dashboard'))

        attraction = Attraction.query.get(attraction_id)
        if not attraction:
            flash('Атракціон не знайдено.', 'error')
            return redirect(url_for('dashboard'))

        record = MaintenanceRecord(
            description=description,
            status=status,
            technician_id=request.form.get('user_id'),
            attraction_id=attraction_id,
            date=datetime.utcnow()
        )
        db.session.add(record)
        db.session.commit()
        flash('Запис про обслуговування додано!', 'success')
        return redirect(url_for('dashboard'))
    return render_template('add_maintenance.html', attractions=Attraction.query.all())

@app.route('/maintenance/edit/<int:id>', methods=['POST'])
def edit_maintenance(id):
    if 'technician' in request.form.get('role', ''):
        record = MaintenanceRecord.query.get_or_404(id)
        record.description = request.form.get('description')
        record.status = request.form.get('status')
        db.session.commit()
        flash('Запис про обслуговування оновлено!', 'success')
    else:
        flash('Доступ заборонено.', 'error')
    return redirect(url_for('dashboard'))

@app.route('/maintenance/delete/<int:id>', methods=['POST'])
def delete_maintenance(id):
    if 'technician' in request.form.get('role', ''):
        record = MaintenanceRecord.query.get_or_404(id)
        db.session.delete(record)
        db.session.commit()
        flash('Запис про обслуговування видалено!', 'success')
    else:
        flash('Доступ заборонено.', 'error')
    return redirect(url_for('dashboard'))