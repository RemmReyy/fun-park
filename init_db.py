from app import app, db, User, Attraction, TicketPrice
from werkzeug.security import generate_password_hash

with app.app_context():
    db.create_all()
    manager = User(username='manager', password=generate_password_hash('password'), role='manager')
    cashier = User(username='cashier', password=generate_password_hash('password'), role='cashier')
    technician = User(username='technician', password=generate_password_hash('password'), role='technician')
    attraction1 = Attraction(name='Американські гірки', capacity=50, status='active')
    attraction2 = Attraction(name='Колесо огляду', capacity=30, status='active')
    ticket_price1 = TicketPrice(ticket_type='single', price=10)
    ticket_price2 = TicketPrice(ticket_type='daily', price=30)
    ticket_price3 = TicketPrice(ticket_type='group', price=50)
    db.session.add_all([manager, cashier, technician, attraction1, attraction2, ticket_price1, ticket_price2, ticket_price3])
    db.session.commit()
    print("База даних ініціалізована!")