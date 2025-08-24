
from datetime import datetime

def define_models(db):
    class User(db.Model):
        __tablename__ = "users"
        id = db.Column(db.Integer, primary_key=True)
        username = db.Column(db.String(80), unique=True, nullable=False)
        email = db.Column(db.String(120), unique=True, nullable=False)
        first_name = db.Column(db.String(100), nullable=False)
        last_name = db.Column(db.String(100), nullable=False)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)
        is_active = db.Column(db.Boolean, default=True)
        accounts = db.relationship(
            "Account",
            back_populates="user",
            cascade="all, delete-orphan",
        )
        @property
        def full_name(self):
            return f"{self.first_name} {self.last_name}"

    class Source(db.Model):
        __tablename__ = "sources"
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(100), nullable=False)
        type = db.Column(db.String(50), nullable=False)
        is_active = db.Column(db.Boolean, default=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class Category(db.Model):
        __tablename__ = "categories"
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(100), nullable=False)
        type = db.Column(db.String(20), nullable=False)
        color = db.Column(db.String(7))
        parent_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
        created_at = db.Column(db.DateTime, default=datetime.utcnow)
        description = db.Column(db.String(200))
        monthly_budget = db.Column(db.Numeric(10, 2))
        is_recurring = db.Column(db.Boolean, default=False)
        subcategories = db.relationship("Category", remote_side=[id])
        transactions = db.relationship("Transaction", backref="category")

    class Transaction(db.Model):
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
        account = db.Column(db.Text)
        reference = db.Column(db.Text)
        account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"))
        is_projected = db.Column(db.Boolean, default=False)
        recurring_pattern_id = db.Column(db.Integer)
        source = db.relationship("Source", backref="transactions")
        account_link = db.relationship("Account", backref="account_transactions")

    class RecurringPattern(db.Model):
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

    class Account(db.Model):
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
        user = db.relationship("User", back_populates="accounts")
        def get_live_balance(self):
            total_transactions = (
                db.session.query(db.func.sum(Transaction.amount))
                .filter(Transaction.account_id == self.id)
                .scalar()
                or 0
            )
            return float(self.opening_balance or 0) + float(total_transactions)

    return User, Source, Category, Transaction, RecurringPattern, Account

