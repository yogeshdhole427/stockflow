import os
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from flask import Flask, jsonify, request, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, and_
from sqlalchemy.exc import IntegrityError

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///stockflow.db")

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# ---- Models ----
class Company(db.Model):
    __tablename__ = "companies"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, unique=True, nullable=False)

class Warehouse(db.Model):
    __tablename__ = "warehouses"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    name = db.Column(db.String, nullable=False)
    address = db.Column(db.String)
    __table_args__ = (db.UniqueConstraint("company_id", "name", name="uq_wh_company_name"),)

class Product(db.Model):
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String, unique=True, nullable=False)
    name = db.Column(db.String, nullable=False)
    price = db.Column(db.Numeric(12,2), nullable=False, default=0.00)
    product_type = db.Column(db.String, nullable=False, default="standard")
    active = db.Column(db.Boolean, nullable=False, default=True)

class Supplier(db.Model):
    __tablename__ = "suppliers"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    contact_email = db.Column(db.String)
    phone = db.Column(db.String)

class SupplierProduct(db.Model):
    __tablename__ = "supplier_products"
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id", ondelete="CASCADE"), primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    company_id = db.Column(db.Integer)
    lead_time_days = db.Column(db.Integer, default=7)

class Inventory(db.Model):
    __tablename__ = "inventories"
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id", ondelete="CASCADE"), primary_key=True)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    safety_stock = db.Column(db.Integer, default=0)

class InventoryChange(db.Model):
    __tablename__ = "inventory_changes"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False)
    quantity_delta = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String)
    ref_type = db.Column(db.String)
    ref_id = db.Column(db.Integer)
    changed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

class ProductBundle(db.Model):
    __tablename__ = "product_bundles"
    bundle_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    component_product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    quantity = db.Column(db.Integer, nullable=False)

class SalesOrder(db.Model):
    __tablename__ = "sales_orders"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    ordered_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

class SalesOrderItem(db.Model):
    __tablename__ = "sales_order_items"
    order_id = db.Column(db.Integer, db.ForeignKey("sales_orders.id", ondelete="CASCADE"), primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="RESTRICT"), primary_key=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id", ondelete="RESTRICT"), primary_key=True)
    quantity = db.Column(db.Integer, nullable=False)

class ProductThreshold(db.Model):
    __tablename__ = "product_thresholds"
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    threshold = db.Column(db.Integer, nullable=False, default=0)

class ProductThresholdOverride(db.Model):
    __tablename__ = "product_threshold_overrides"
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id", ondelete="CASCADE"), primary_key=True)
    threshold = db.Column(db.Integer, nullable=False)

# ---- Health ----
@app.route("/health")
def health():
    return {"status": "ok"}

# ---- Helper ----
def decimal_from(value):
    try:
        d = Decimal(str(value))
        if d < 0:
            raise InvalidOperation()
        return d
    except Exception:
        return None

# ---- Endpoint: Create Product ----
@app.route("/api/products", methods=["POST"])
def create_product():
    if not request.is_json:
        return jsonify(error="Content-Type must be application/json"), 415
    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()
    sku = (data.get("sku") or "").strip()
    price_raw = data.get("price")
    warehouse_id = data.get("warehouse_id")
    initial_qty = data.get("initial_quantity", 0)

    if not name or not sku or price_raw is None or warehouse_id is None:
        return jsonify(error="Missing required fields: name, sku, price, warehouse_id"), 400

    price = decimal_from(price_raw)
    if price is None:
        return jsonify(error="Invalid price (must be non-negative decimal)"), 400

    try:
        initial_qty = int(initial_qty)
        if initial_qty < 0:
            return jsonify(error="initial_quantity must be >= 0"), 400
    except Exception:
        return jsonify(error="initial_quantity must be an integer"), 400

    wh = Warehouse.query.get(warehouse_id)
    if not wh:
        return jsonify(error="warehouse_id not found"), 404

    try:
        product = Product(name=name, sku=sku, price=price)
        db.session.add(product)
        db.session.flush()  # product.id available

        inv = Inventory.query.filter_by(product_id=product.id, warehouse_id=warehouse_id).with_for_update().first()
        if inv:
            inv.quantity += initial_qty
        else:
            inv = Inventory(product_id=product.id, warehouse_id=warehouse_id, quantity=initial_qty)
            db.session.add(inv)

        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="SKU already exists"), 409
    except Exception as e:
        db.session.rollback()
        return jsonify(error="Internal server error"), 500

    location = url_for("get_product", product_id=product.id, _external=True)
    return jsonify(
        message="Product created",
        product={"id": product.id, "name": product.name, "sku": product.sku, "price": str(product.price)},
        inventory={"warehouse_id": warehouse_id, "quantity": inv.quantity},
        links={"self": location}
    ), 201

# ---- Helper: Get Product ----
@app.route("/api/products/<int:product_id>", methods=["GET"])
def get_product(product_id):
    p = Product.query.get_or_404(product_id)
    return jsonify(id=p.id, sku=p.sku, name=p.name, price=str(p.price), active=p.active)

# ---- Endpoint: Low Stock Alerts ----
@app.route("/api/companies/<int:company_id>/alerts/low-stock", methods=["GET"])
def low_stock_alerts(company_id):
    company = Company.query.get(company_id)
    if not company:
        return jsonify(error="company not found"), 404

    try:
        days = int(request.args.get("days", 30))
        if days <= 0:
            days = 30
    except Exception:
        days = 30
    since = datetime.utcnow() - timedelta(days=days)

    recent_sales = (
        db.session.query(
            SalesOrderItem.product_id.label("pid"),
            SalesOrderItem.warehouse_id.label("wid"),
            func.sum(SalesOrderItem.quantity).label("qty_30d")
        )
        .join(SalesOrder, SalesOrder.id == SalesOrderItem.order_id)
        .filter(SalesOrder.company_id == company_id)
        .filter(SalesOrder.ordered_at >= since)
        .group_by(SalesOrderItem.product_id, SalesOrderItem.warehouse_id)
        .subquery()
    )

    wh_ids = db.session.query(Warehouse.id).filter(Warehouse.company_id == company_id).subquery()

    inv = (
        db.session.query(
            Inventory.product_id,
            Inventory.warehouse_id,
            Inventory.quantity,
        )
        .filter(Inventory.warehouse_id.in_(wh_ids))
        .subquery()
    )

    threshold = (
        db.session.query(
            Product.id.label("pid"),
            inv.c.warehouse_id.label("wid"),
            func.coalesce(ProductThresholdOverride.threshold, ProductThreshold.threshold, 0).label("thresh")
        )
        .join(inv, inv.c.product_id == Product.id)
        .outerjoin(ProductThreshold, ProductThreshold.product_id == Product.id)
        .outerjoin(ProductThresholdOverride, and_(
            ProductThresholdOverride.product_id == Product.id,
            ProductThresholdOverride.warehouse_id == inv.c.warehouse_id
        ))
        .subquery()
    )

    supplier_sub = (
        db.session.query(
            SupplierProduct.product_id.label("pid"),
            Supplier.id.label("sid"),
            Supplier.name.label("sname"),
            Supplier.contact_email.label("semail"),
            func.min(SupplierProduct.lead_time_days).label("lead")
        )
        .join(Supplier, Supplier.id == SupplierProduct.supplier_id)
        .group_by(SupplierProduct.product_id, Supplier.id, Supplier.name, Supplier.contact_email)
        .subquery()
    )

    q = (
        db.session.query(
            Product.id.label("product_id"),
            Product.name.label("product_name"),
            Product.sku.label("sku"),
            Warehouse.id.label("warehouse_id"),
            Warehouse.name.label("warehouse_name"),
            inv.c.quantity.label("current_stock"),
            threshold.c.thresh.label("threshold"),
            func.coalesce(recent_sales.c.qty_30d, 0).label("qty_30d"),
            supplier_sub.c.sid.label("supplier_id"),
            supplier_sub.c.sname.label("supplier_name"),
            supplier_sub.c.semail.label("supplier_email")
        )
        .join(inv, inv.c.product_id == Product.id)
        .join(Warehouse, Warehouse.id == inv.c.warehouse_id)
        .join(threshold, and_(threshold.c.pid == Product.id, threshold.c.wid == Warehouse.id))
        .outerjoin(recent_sales, and_(recent_sales.c.pid == Product.id, recent_sales.c.wid == Warehouse.id))
        .outerjoin(supplier_sub, supplier_sub.c.pid == Product.id)
        .filter(recent_sales.c.qty_30d.isnot(None))
        .filter(inv.c.quantity < threshold.c.thresh)
    )

    alerts = []
    for row in q.all():
        avg_daily = row.qty_30d / days if row.qty_30d and days > 0 else None
        days_until = int(row.current_stock / avg_daily) if avg_daily and avg_daily > 0 else None
        alerts.append({
            "product_id": row.product_id,
            "product_name": row.product_name,
            "sku": row.sku,
            "warehouse_id": row.warehouse_id,
            "warehouse_name": row.warehouse_name,
            "current_stock": int(row.current_stock),
            "threshold": int(row.threshold),
            "days_until_stockout": days_until,
            "supplier": {
                "id": row.supplier_id,
                "name": row.supplier_name,
                "contact_email": row.supplier_email
            }
        })
    return jsonify({"alerts": alerts, "total_alerts": len(alerts)}), 200

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)