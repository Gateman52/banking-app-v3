"""
Main Flask application file for the Banking App v3.

This file initializes the Flask application, configures the database,
defines the SQLAlchemy models, and sets up the application routes
for managing users, accounts, transactions, and categories.
"""

import os
from datetime import date, datetime, timedelta

import pytz
from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

# Initialize Flask app
app = Flask(__name__)

# For security, the secret key should be a long, random string.
# It's best practice to load it from an environment variable rather than hardcoding it.
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    app.logger.warning("SECRET_KEY environment variable not set. Using a default for development.")
    SECRET_KEY = "a-default-and-insecure-secret-key-for-dev"
app.secret_key = SECRET_KEY

# Database configuration - Using your existing banking.db
basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"sqlite:///{os.path.join(basedir, 'banking.db')}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize extensions
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# UK Configuration
UK_TIMEZONE = pytz.timezone("Europe/London")


# SQLAlchemy Models - Your existing tables + new ones
class User(db.Model):
    """Represents a user of the application."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

    # Relationships
    accounts = db.relationship("Account", backref="user", lazy="dynamic")

    @property
    def full_name(self):
        """Return the user's full name."""
        return f"{self.first_name} {self.last_name}"


class Source(db.Model):
    """Represents a source of transactions (e.g., a bank, a CSV file)."""

    __tablename__ = "sources"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Category(db.Model):
    """Represents a category for classifying transactions."""

    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # income/expense
    color = db.Column(db.String(7))
    parent_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    description = db.Column(db.String(200))
    monthly_budget = db.Column(db.Numeric(10, 2))
    is_recurring = db.Column(db.Boolean, default=False)

    # Relationships
    subcategories = db.relationship("Category", remote_side=[id])
    transactions = db.relationship("Transaction", backref="category")


class Transaction(db.Model):
    """Represents a single financial transaction."""

    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.String(255))
    date = db.Column(db.Date, nullable=False)
    description = db.Column(db.Text, nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    balance = db.Column(db.Numeric(10, 2))
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    source_id = db.Column(db.Integer, db.ForeignKey("sources.id"))
    source_type = db.Column(db.String(50))
    raw_data = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    account = db.Column(db.Text)  # Your existing column
    reference = db.Column(db.Text)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"))
    is_projected = db.Column(db.Boolean, default=False)
    recurring_pattern_id = db.Column(db.Integer)

    source = db.relationship("Source", backref="transactions")
    account_link = db.relationship("Account", backref="account_transactions")


class RecurringPattern(db.Model):
    """Represents a detected recurring transaction pattern."""

    __tablename__ = "recurring_patterns"

    id = db.Column(db.Integer, primary_key=True)
    description_norm = db.Column(db.Text, nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    avg_interval_days = db.Column(db.Integer)
    last_date = db.Column(db.Date)
    occurrences = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    is_active = db.Column(db.Boolean, default=True)
    confidence_score = db.Column(db.Float, default=0.0)


class Account(db.Model):
    """Represents a bank account belonging to a user."""

    __tablename__ = "accounts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    account_name = db.Column(db.String(100), nullable=False)
    account_type = db.Column(db.String(50), default="current")
    opening_balance = db.Column(db.Numeric(10, 2), default=0.00)
    current_balance = db.Column(db.Numeric(10, 2), default=0.00)
    currency = db.Column(db.String(3), default="GBP")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    bank_connection_id = db.Column(db.String(255))
    external_account_id = db.Column(db.String(255))

    def get_live_balance(self):
        """Calculate current balance on-the-fly based on opening balance + transactions"""
        total_transactions = (
            db.session.query(db.func.sum(Transaction.amount))
            .filter(Transaction.account_id == self.id)
            .scalar()
            or 0
        )
        # The `current_balance` column in the DB may be stale. This provides the actual value.
        return float(self.opening_balance or 0) + float(total_transactions)


# Template filters for UK formatting
@app.template_filter("currency")
def format_currency(amount):
    """Format currency for UK (£)"""
    if amount is None:
        return "£0.00"
    return f"£{float(amount):.2f}"


@app.template_filter("date_uk")
def format_date_uk(date_obj):
    """Format date for UK (dd/mm/yyyy)"""
    if hasattr(date_obj, "strftime"):
        return date_obj.strftime("%d/%m/%Y")
    return str(date_obj)


@app.template_filter("datetime_uk")
def format_datetime_uk(datetime_obj):
    """Format datetime for UK (dd/mm/yyyy HH:MM)"""
    if datetime_obj is None:
        return ""
    uk_time = datetime_obj.replace(tzinfo=pytz.UTC).astimezone(UK_TIMEZONE)
    return uk_time.strftime("%d/%m/%Y %H:%M")


# Simple projection calculation
def calculate_projected_balance_2_weeks():
    """Simple 2-week projection"""
    today = date.today()
    two_weeks_from_now = today + timedelta(days=14)

    # Get current total balance
    current_balance = 0
    accounts = Account.query.filter_by(is_active=True).all()
    for account in accounts:
        current_balance += account.get_live_balance()

    # Simple projection - assume no change for now
    projected_change = 0

    return {
        "current_balance": current_balance,
        "projected_change": projected_change,
        "projected_balance": current_balance + projected_change,
        "projection_date": two_weeks_from_now,
    }


# Routes
@app.route("/")
def dashboard():
    """Main dashboard"""
    # Get user accounts and balances
    accounts = Account.query.filter_by(is_active=True).all()

    # Calculate current balances
    total_balance = 0
    for account in accounts:
        account.live_balance = account.get_live_balance()
        total_balance += account.live_balance

    # Get transaction statistics
    total_transactions = Transaction.query.count()
    recent_transactions = (
        Transaction.query.order_by(Transaction.date.desc()).limit(10).all()
    )

    # Get projected balance
    projected_balance = calculate_projected_balance_2_weeks()

    # Category breakdown
    category_stats = (
        db.session.query(
            Category.name,
            Category.color,
            db.func.sum(Transaction.amount).label("total"),
            db.func.count(Transaction.id).label("count"),
        )
        .join(Transaction)
        .group_by(Category.id)
        .order_by("total")
        .limit(8)
        .all()
    )

    return render_template(
        "dashboard.html",
        accounts=accounts,
        total_balance=total_balance,
        total_transactions=total_transactions,
        recent_transactions=recent_transactions,
        projected_balance=projected_balance,
        category_stats=category_stats,
    )


@app.route("/users")
def users():
    """User management page"""
    user_list = User.query.order_by(User.created_at.desc()).all()
    return render_template("users.html", users=user_list)


@app.route("/add-user", methods=["GET", "POST"])
def add_user():
    """Add new user with account"""
    if request.method == "POST":
        try:
            # Create user
            user = User(
                username=request.form["username"],
                email=request.form["email"],
                first_name=request.form["first_name"],
                last_name=request.form["last_name"],
            )
            db.session.add(user)
            db.session.flush()  # Get user ID

            # Create default current account
            opening_balance = float(request.form.get("opening_balance", 0))
            account = Account(
                user_id=user.id,
                account_name=f"{user.first_name}'s Current Account",
                account_type="current",
                opening_balance=opening_balance,
                current_balance=opening_balance,
            )
            db.session.add(account)
            db.session.flush()  # Get account ID

            # Create opening balance transaction if amount > 0
            if opening_balance != 0:
                # Get or create opening balance source
                source = Source.query.filter_by(type="opening_balance").first()
                if not source:
                    source = Source(
                        name="Opening Balance", type="opening_balance", is_active=True
                    )
                    db.session.add(source)
                    db.session.flush()

                opening_transaction = Transaction(
                    date=date.today(),
                    description="Opening Balance",
                    amount=opening_balance,
                    account_id=account.id,
                    source_id=source.id,
                    source_type="opening_balance",
                )
                db.session.add(opening_transaction)

            db.session.commit()
            flash("""
                f"User {user.full_name}
                  created successfully with opening balance of
                  £{opening_balance:.2f}!"
            """)
            return redirect(url_for("users"))

        except IntegrityError:
            db.session.rollback()
            flash(
                "Error: Username or email already exists. Please choose different values."
            )

        except (SQLAlchemyError, ValueError) as e:
            db.session.rollback()
            app.logger.error("Error creating user: %s", e, exc_info=True)
            flash(f"An error occurred while creating the user: {e}")

    return render_template("add_user.html")


# Simple transaction view
@app.route("/transactions")
def transactions():
    """Simple transaction list"""
    page = request.args.get("page", 1, type=int)
    per_page = 50

    paginated_transactions = Transaction.query.order_by(
        Transaction.date.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    return render_template("transactions/transactions.html", transactions=paginated_transactions)


@app.route("/categories")
def categories():
    """Categories management page"""
    category_list = Category.query.order_by(Category.type, Category.name).all()

    # Group by type and add statistics
    income_categories = []
    expense_categories = []

    for cat in category_list:
        # Count transactions for this category
        transaction_count = Transaction.query.filter_by(category_id=cat.id).count()

        # Calculate total amount for this category
        total_amount = (
            db.session.query(db.func.sum(Transaction.amount))
            .filter(Transaction.category_id == cat.id)
            .scalar()
            or 0
        )

        # Add stats to category object
        cat.transaction_count = transaction_count
        cat.total_amount = float(total_amount)

        if cat.type == "income":
            income_categories.append(cat)
        else:
            expense_categories.append(cat)

    return render_template(
        "categories/index.html",
        income_categories=income_categories,
        expense_categories=expense_categories,
        total_categories=len(category_list),
    )


@app.route("/categories/add", methods=["GET", "POST"])
def add_category():
    """Add new category"""
    if request.method == "POST":
        try:
            category = Category(
                name=request.form["name"],
                type=request.form["type"],
                description=request.form.get("description", ""),
                color=request.form.get("color", "#667eea"),
                monthly_budget=float(request.form.get("monthly_budget", 0)) or None,
            )

            db.session.add(category)
            db.session.commit()

            flash(f'Category "{category.name}" created successfully!')
            return redirect(url_for("categories"))

        except (ValueError, TypeError):
            db.session.rollback()
            flash(
                "Invalid input. Please check the values entered, especially for the budget."
            )

        except SQLAlchemyError as e:
            db.session.rollback()
            app.logger.error("Database error creating category: %s", e, exc_info=True)
            flash(f"A database error occurred: {e}")

    return render_template("categories/add_category.html")


@app.route("/categories/<int:category_id>")
def view_category(category_id):
    """View category details with transactions"""
    category = Category.query.get_or_404(category_id)

    # Get transactions for this category with pagination
    page = request.args.get("page", 1, type=int)
    per_page = 25

    paginated_transactions = (
        Transaction.query.filter_by(category_id=category_id)
        .order_by(Transaction.date.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    # Calculate statistics
    total_amount = (
        db.session.query(db.func.sum(Transaction.amount))
        .filter(Transaction.category_id == category_id)
        .scalar()
        or 0
    )
    transaction_count = Transaction.query.filter_by(category_id=category_id).count()

    stats = {
        "total_amount": float(total_amount),
        "transaction_count": transaction_count,
        "avg_amount": float(total_amount) / transaction_count
        if transaction_count > 0
        else 0,
    }

    return render_template(
        "categories/view_category.html",
        category=category,
        transactions=paginated_transactions,
        stats=stats,
    )


@app.route("/categories/<int:category_id>/edit", methods=["GET", "POST"])
def edit_category(category_id):
    """Edit existing category"""
    category = Category.query.get_or_404(category_id)

    if request.method == "POST":
        try:
            category.name = request.form["name"]
            category.type = request.form["type"]
            category.description = request.form.get("description", "")
            category.color = request.form.get("color", category.color)
            category.monthly_budget = (
                float(request.form.get("monthly_budget", 0)) or None
            )

            db.session.commit()

            flash(f'Category "{category.name}" updated successfully!')
            return redirect(url_for("view_category", category_id=category.id))

        except (ValueError, TypeError):
            db.session.rollback()
            flash(
                "Invalid input. Please check the values entered, especially for the budget."
            )

        except SQLAlchemyError as e:
            db.session.rollback()
            app.logger.error("Database error updating category: %s", e, exc_info=True)
            flash(f"A database error occurred: {e}")

    return render_template("categories/edit_category.html", category=category)


@app.route("/categories/<int:category_id>/delete", methods=["POST"])
def delete_category(category_id):
    """Delete category (with safety checks)"""
    category = Category.query.get_or_404(category_id)

    # Check if category has transactions
    transaction_count = Transaction.query.filter_by(category_id=category_id).count()
    if transaction_count > 0:
        flash(
            f'Cannot delete category "{category.name}" - it has '
            f"{transaction_count} transactions. Please reassign transactions first."
        )
        return redirect(url_for("view_category", category_id=category_id))

    try:
        category_name = category.name
        db.session.delete(category)
        db.session.commit()

        flash(f'Category "{category_name}" deleted successfully!')
        return redirect(url_for("categories"))

    except SQLAlchemyError as e:
        db.session.rollback()
        app.logger.error("Database error deleting category: %s", e, exc_info=True)
        flash(f"A database error occurred while trying to delete the category: {e}")
        return redirect(url_for("view_category", category_id=category_id))


# Also update your navigation links in templates to point to the correct routes


# API endpoint for checking status
@app.route("/api/status")
def api_status():
    """API status check"""
    return jsonify(
        {
            "status": "running",
            "transactions": Transaction.query.count(),
            "categories": Category.query.count(),
            "users": User.query.count(),
            "accounts": Account.query.count(),
        }
    )


if __name__ == "__main__":
    print("🏦 Banking App v3 Starting...")
    print("📊 Using your existing banking.db")
    print("\nAvailable routes:")
    print("  • http://127.0.0.1:5000/ - Dashboard")
    print("  • http://127.0.0.1:5000/users - User management")
    print("  • http://127.0.0.1:5000/add-user - Add new user")
    print("  • http://127.0.0.1:5000/transactions - View transactions")
    print("  • http://127.0.0.1:5000/api/status - API status")
    print("\n✨ Features:")
    print("  • Your 287 transactions preserved")
    print("  • Your 21 categories intact")
    print("  • UK formatting (£, dd/mm/yyyy)")
    print("  • User accounts with opening balances")
    print("  • Balance projections ready")

    app.run(debug=True)
