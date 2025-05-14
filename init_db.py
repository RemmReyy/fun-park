from app import app, db
from models import User, TicketPrice, Notification
from werkzeug.security import generate_password_hash
import os

# Create the database and populate it with initial data
with app.app_context():
    # Drop all tables and recreate them
    db.drop_all()
    db.create_all()

    # Create initial users
    manager = User(username='manager', password=generate_password_hash('password'), role='manager')
    cashier = User(username='cashier', password=generate_password_hash('password'), role='cashier')
    technician = User(username='technician', password=generate_password_hash('password'), role='technician')
    operator = User(username='operator', password=generate_password_hash('password'), role='operator')
    db.session.add_all([manager, cashier, technician, operator])

    # Create initial ticket prices
    single_price = TicketPrice(ticket_type='single', price=10.0)
    daily_price = TicketPrice(ticket_type='daily', price=30.0)
    group_price = TicketPrice(ticket_type='group', price=50.0)
    db.session.add_all([single_price, daily_price, group_price])

    db.session.commit()
    print("Database initialized with initial data.")