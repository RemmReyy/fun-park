from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # manager, cashier, technician, operator

class Attraction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='active')  # active, maintenance, inactive

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(20), nullable=False)  # single, daily, group
    price = db.Column(db.Float, nullable=False)
    qr_code = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='active')  # active, used, refunded, exchanged
    attraction_id = db.Column(db.Integer, db.ForeignKey('attraction.id'), nullable=True)  # For single tickets
    valid_until = db.Column(db.DateTime, nullable=True)  # For daily tickets
    group_size = db.Column(db.Integer, nullable=True)  # For group tickets
    used_count = db.Column(db.Integer, nullable=True, default=0)  # For daily tickets, track usage

class MaintenanceRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), nullable=False)  # ongoing, completed
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    technician_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=True)  # Link to Ticket
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(20), nullable=False)  # card, cash
    status = db.Column(db.String(20), nullable=False)  # pending, completed, failed
    transaction_type = db.Column(db.String(20), nullable=False, default='purchase')  # purchase, refund, exchange
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

class TicketPrice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_type = db.Column(db.String(20), nullable=False, unique=True)  # single, daily, group
    price = db.Column(db.Float, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

class Queue(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    attraction_id = db.Column(db.Integer, db.ForeignKey('attraction.id'), nullable=False)
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)
    position = db.Column(db.Integer, nullable=False)  # Position in the queue (1, 2, 3...)
    added_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    ticket = db.relationship('Ticket', backref='queues', lazy='select')
    attraction = db.relationship('Attraction', backref='queues', lazy='select')