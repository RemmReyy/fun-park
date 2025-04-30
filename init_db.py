from app import app, db, User, Attraction
from werkzeug.security import generate_password_hash

with app.app_context():
    db.create_all()
    # Додавання користувачів
    manager = User(username='manager', password=generate_password_hash('password'), role='manager')
    cashier = User(username='cashier', password=generate_password_hash('password'), role='cashier')
    technician = User(username='technician', password=generate_password_hash('password'), role='technician')
    # Додавання атракціонів
    attraction1 = Attraction(name='Американські гірки', capacity=50, status='active')
    attraction2 = Attraction(name='Колесо огляду', capacity=30, status='active')
    db.session.add_all([manager, cashier, technician, attraction1, attraction2])
    db.session.commit()
    print("База даних ініціалізована!")