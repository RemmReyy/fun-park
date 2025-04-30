from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # manager, cashier, technician, visitor

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(20), nullable=False)  # single, daily, group
    price = db.Column(db.Float, nullable=False)
    qr_code = db.Column(db.String(100), nullable=False)
    valid_from = db.Column(db.DateTime, default=datetime.utcnow)
    valid_to = db.Column(db.DateTime)

class Attraction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='active')  # active, maintenance, inactive
    capacity = db.Column(db.Integer, nullable=False)

class MaintenanceRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False)  # ongoing, completed
    technician_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    date = db.Column(db.DateTime, default=datetime.utcnow)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False)  # completed, pending, failed
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class TicketPrice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_type = db.Column(db.String(20), unique=True, nullable=False)
    price = db.Column(db.Float, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)