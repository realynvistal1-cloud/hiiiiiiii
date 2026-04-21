import os
import uuid
from decimal import Decimal

from flask import Flask, jsonify, request
from flask_cors import CORS
from sqlalchemy import Column, DateTime, Integer, Numeric, String, create_engine, func
from sqlalchemy.orm import declarative_base, scoped_session, sessionmaker

app = Flask(__name__)

# Allow your frontend domain
CORS(app, resources={r"/api/*": {"origins": "*"}})

Base = declarative_base()


def build_database_url():
    # First priority: full DATABASE_URL from hosting
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return db_url

    # Fallback: build from separate variables
    db_user = os.getenv("DB_USER", "root")
    db_password = os.getenv("DB_PASSWORD", "")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "3306")
    db_name = os.getenv("DB_NAME", "bagsstore_db")

    return f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"


DATABASE_URL = build_database_url()

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=280
)

SessionLocal = scoped_session(
    sessionmaker(bind=engine, autoflush=False, autocommit=False)
)


class Product(Base):
    __tablename__ = "products"

    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    stock = Column(Integer, nullable=False)
    image = Column(String(255), nullable=False)


class Order(Base):
    __tablename__ = "orders"

    order_id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(String(50), nullable=False)
    quantity = Column(Integer, nullable=False)
    total_amount = Column(Numeric(10, 2), nullable=False)
    status = Column(String(50), nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class Payment(Base):
    __tablename__ = "payments"

    payment_id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String(50), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    status = Column(String(50), nullable=False)
    created_at = Column(DateTime, server_default=func.now())


def seed_products():
    db = SessionLocal()
    try:
        if db.query(Product).count() == 0:
            db.add_all([
                Product(
                    id="school_backpack",
                    name="School Backpack",
                    price=35.00,
                    stock=13,
                    image="images/school_backpack.jpg"
                ),
                Product(
                    id="leather_handbag",
                    name="Leather Handbag",
                    price=50.00,
                    stock=8,
                    image="images/leather_handbag.jpg"
                ),
                Product(
                    id="travel_bag",
                    name="Travel Bag",
                    price=65.00,
                    stock=10,
                    image="images/travel_bag.jpg"
                ),
                Product(
                    id="sling_bag",
                    name="Sling Bag",
                    price=25.00,
                    stock=20,
                    image="images/sling_bag.jpg"
                )
            ])
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


Base.metadata.create_all(bind=engine)
seed_products()


@app.teardown_appcontext
def shutdown_session(exception=None):
    SessionLocal.remove()


@app.route("/")
def home():
    return "Bagstore backend is running"


@app.route("/api/get_inventory", methods=["GET"])
def get_inventory():
    db = SessionLocal()
    try:
        products = db.query(Product).all()
        inventory = {}

        for product in products:
            inventory[product.id] = {
                "name": product.name,
                "price": float(product.price),
                "stock": product.stock,
                "image": product.image
            }

        return jsonify(inventory), 200
    finally:
        db.close()


@app.route("/api/create_order", methods=["POST"])
def create_order():
    data = request.get_json(silent=True) or {}
    item_id = data.get("item_id")
    quantity = data.get("quantity", 1)

    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        return jsonify({
            "status": "failed",
            "message": "Invalid quantity"
        }), 400

    if not item_id or quantity < 1:
        return jsonify({
            "status": "failed",
            "message": "Invalid request"
        }), 400

    db = SessionLocal()

    try:
        product = db.query(Product).filter_by(id=item_id).first()

        if not product:
            return jsonify({
                "status": "failed",
                "message": "Bag does not exist"
            }), 404

        if product.stock < quantity:
            return jsonify({
                "status": "failed",
                "message": "Bag out of stock"
            }), 400

        total_amount = Decimal(product.price) * quantity

        # Reduce stock
        product.stock -= quantity

        # Save payment
        txn_id = f"BAG-TXN-{uuid.uuid4().hex[:8].upper()}"
        payment = Payment(
            transaction_id=txn_id,
            amount=total_amount,
            status="Success"
        )
        db.add(payment)

        # Save order
        order = Order(
            item_id=item_id,
            quantity=quantity,
            total_amount=total_amount,
            status="Success"
        )
        db.add(order)

        db.commit()

        return jsonify({
            "status": "success",
            "message": "Order placed successfully!",
            "item_id": item_id,
            "quantity": quantity,
            "total_amount": float(total_amount),
            "transaction_id": txn_id
        }), 200

    except Exception as e:
        db.rollback()
        return jsonify({
            "status": "failed",
            "message": f"Server error: {str(e)}"
        }), 500
    finally:
        db.close()


@app.route("/api/orders", methods=["GET"])
def get_orders():
    db = SessionLocal()
    try:
        orders = db.query(Order).order_by(Order.order_id.desc()).all()
        return jsonify([
            {
                "order_id": order.order_id,
                "item_id": order.item_id,
                "quantity": order.quantity,
                "total_amount": float(order.total_amount),
                "status": order.status,
                "created_at": order.created_at.isoformat() if order.created_at else None
            }
            for order in orders
        ]), 200
    finally:
        db.close()


@app.route("/api/payments", methods=["GET"])
def get_payments():
    db = SessionLocal()
    try:
        payments = db.query(Payment).order_by(Payment.payment_id.desc()).all()
        return jsonify([
            {
                "payment_id": payment.payment_id,
                "transaction_id": payment.transaction_id,
                "amount": float(payment.amount),
                "status": payment.status,
                "created_at": payment.created_at.isoformat() if payment.created_at else None
            }
            for payment in payments
        ]), 200
    finally:
        db.close()


@app.route("/api/admin_update", methods=["POST"])
def admin_update():
    data = request.get_json(silent=True) or {}
    action = data.get("action_type")

    db = SessionLocal()

    try:
        if action == "add":
            item_name = data.get("name")
            if not item_name:
                return jsonify({
                    "status": "error",
                    "message": "Name is required"
                }), 400

            item_id = item_name.lower().replace(" ", "_")

            existing = db.query(Product).filter_by(id=item_id).first()
            if existing:
                return jsonify({
                    "status": "error",
                    "message": "Item already exists"
                }), 400

            product = Product(
                id=item_id,
                name=item_name,
                price=float(data.get("price", 0)),
                stock=int(data.get("stock", 0)),
                image=data.get("image", "images/default.jpg")
            )

            db.add(product)
            db.commit()

            return jsonify({
                "status": "success",
                "message": f"Added {item_name}!"
            }), 200

        elif action == "edit":
            item_id = data.get("item_id")
            product = db.query(Product).filter_by(id=item_id).first()

            if not product:
                return jsonify({
                    "status": "error",
                    "message": "Item not found"
                }), 404

            if data.get("new_price") is not None:
                product.price = float(data.get("new_price"))

            if data.get("add_stock") is not None:
                product.stock += int(data.get("add_stock"))

            if data.get("new_image"):
                product.image = data.get("new_image")

            db.commit()

            return jsonify({
                "status": "success",
                "message": f"Updated {product.name}!"
            }), 200

        return jsonify({
            "status": "error",
            "message": "Invalid request"
        }), 400

    except Exception as e:
        db.rollback()
        return jsonify({
            "status": "error",
            "message": f"Server error: {str(e)}"
        }), 500
    finally:
        db.close()


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)