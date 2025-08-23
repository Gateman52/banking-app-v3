# blueprints/accounts.py - Account Management Blueprint
from flask import Blueprint, request, render_template, redirect, url_for, flash, jsonify
from app import db
from models import Account, User, Transaction, Source
from datetime import datetime, date
from decimal import Decimal

accounts_bp = Blueprint("accounts", __name__)


@accounts_bp.route("/")
def index():
    """List all accounts"""
    accounts = (
        Account.query.filter_by(is_active=True)
        .order_by(Account.created_at.desc())
        .all()
    )

    # Calculate current balances and add statistics
    total_balance = 0
    for account in accounts:
        account.calculate_current_balance()
        total_balance += float(account.current_balance or 0)

        # Add transaction count for last 30 days
        recent_transactions = Transaction.query.filter(
            Transaction.account_id == account.id,
            Transaction.date >= date.today().replace(day=1),  # This month
        ).count()
        account.recent_transaction_count = recent_transactions

    return render_template(
        "accounts/index.html", accounts=accounts, total_balance=total_balance
    )


@accounts_bp.route("/add", methods=["GET", "POST"])
def add():
    """Add new account to existing user"""
    if request.method == "POST":
        try:
            user_id = request.form["user_id"]
            account_name = request.form["account_name"]
            account_type = request.form["account_type"]
            opening_balance = Decimal(request.form.get("opening_balance", "0.00"))

            # Validate user exists
            user = User.query.get(user_id)
            if not user:
                flash("Selected user does not exist.")
                return redirect(url_for("accounts.add"))

            # Create new account
            account = Account(
                user_id=user_id,
                account_name=account_name,
                account_type=account_type,
                opening_balance=opening_balance,
                current_balance=opening_balance,
            )

            db.session.add(account)
            db.session.flush()  # Get account ID

            # Create opening balance transaction if amount != 0
            if opening_balance != 0:
                # Get or create a source for opening balances
                source = Source.query.filter_by(type="opening_balance").first()
                if not source:
                    source = Source(
                        name="Opening Balance", type="opening_balance", is_active=True
                    )
                    db.session.add(source)
                    db.session.flush()

                opening_transaction = Transaction(
                    date=date.today(),
                    description=f"Opening balance for {account_name}",
                    amount=opening_balance,
                    account_id=account.id,
                    source_id=source.id,
                    source_type="opening_balance",
                )
                db.session.add(opening_transaction)

            db.session.commit()

            flash(
                f'Account "{account_name}" created successfully for {user.full_name} with opening balance of £{opening_balance:.2f}!'
            )
            return redirect(url_for("accounts.view", id=account.id))

        except Exception as e:
            db.session.rollback()
            flash(f"Error creating account: {str(e)}")

    # Get users for dropdown
    users = (
        User.query.filter_by(is_active=True)
        .order_by(User.first_name, User.last_name)
        .all()
    )

    # Account types
    account_types = [
        ("current", "Current Account"),
        ("savings", "Savings Account"),
        ("credit", "Credit Card"),
        ("loan", "Loan Account"),
        ("investment", "Investment Account"),
    ]

    return render_template(
        "accounts/add.html", users=users, account_types=account_types
    )


@accounts_bp.route("/<int:id>")
def view(id):
    """View account details and transactions"""
    account = Account.query.get_or_404(id)
    account.calculate_current_balance()

    # Get pagination parameters
    page = request.args.get("page", 1, type=int)
    per_page = 25

    # Get transactions for this account
    transactions = (
        Transaction.query.filter_by(account_id=id)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    # Calculate account statistics
    total_transactions = Transaction.query.filter_by(account_id=id).count()

    # Monthly breakdown
    monthly_summary = (
        db.session.query(
            db.func.strftime("%Y-%m", Transaction.date).label("month"),
            db.func.sum(Transaction.amount).label("total_amount"),
            db.func.count(Transaction.id).label("transaction_count"),
        )
        .filter(Transaction.account_id == id)
        .group_by("month")
        .order_by("month")
        .all()
    )

    # Recent activity (last 7 days)
    recent_activity = (
        Transaction.query.filter(
            Transaction.account_id == id,
            Transaction.date >= date.today() - timedelta(days=7),
        )
        .order_by(Transaction.date.desc())
        .all()
    )

    stats = {
        "total_transactions": total_transactions,
        "monthly_summary": monthly_summary,
        "recent_activity": recent_activity,
        "balance_change": float(account.current_balance)
        - float(account.opening_balance),
    }

    return render_template(
        "accounts/view.html", account=account, transactions=transactions, stats=stats
    )


@accounts_bp.route("/<int:id>/edit", methods=["GET", "POST"])
def edit(id):
    """Edit account details"""
    account = Account.query.get_or_404(id)

    if request.method == "POST":
        try:
            account.account_name = request.form["account_name"]
            account.account_type = request.form["account_type"]

            # Handle opening balance change (be careful!)
            new_opening_balance = Decimal(request.form.get("opening_balance", "0.00"))
            if new_opening_balance != account.opening_balance:
                # Calculate the difference
                difference = new_opening_balance - account.opening_balance

                # Update opening balance
                account.opening_balance = new_opening_balance

                # Create adjustment transaction
                if difference != 0:
                    source = Source.query.filter_by(type="adjustment").first()
                    if not source:
                        source = Source(
                            name="Balance Adjustment", type="adjustment", is_active=True
                        )
                        db.session.add(source)
                        db.session.flush()

                    adjustment_transaction = Transaction(
                        date=date.today(),
                        description=f"Opening balance adjustment: £{difference:.2f}",
                        amount=difference,
                        account_id=account.id,
                        source_id=source.id,
                        source_type="adjustment",
                    )
                    db.session.add(adjustment_transaction)

            # Recalculate current balance
            account.calculate_current_balance()

            db.session.commit()

            flash(f'Account "{account.account_name}" updated successfully!')
            return redirect(url_for("accounts.view", id=account.id))

        except Exception as e:
            db.session.rollback()
            flash(f"Error updating account: {str(e)}")

    # Account types for dropdown
    account_types = [
        ("current", "Current Account"),
        ("savings", "Savings Account"),
        ("credit", "Credit Card"),
        ("loan", "Loan Account"),
        ("investment", "Investment Account"),
    ]

    return render_template(
        "accounts/edit.html", account=account, account_types=account_types
    )


@accounts_bp.route("/<int:id>/deactivate", methods=["POST"])
def deactivate(id):
    """Deactivate account (soft delete)"""
    account = Account.query.get_or_404(id)

    # Check if account has recent transactions (last 30 days)
    recent_transactions = Transaction.query.filter(
        Transaction.account_id == id,
        Transaction.date >= date.today() - timedelta(days=30),
    ).count()

    if recent_transactions > 0:
        flash(
            f"Cannot deactivate account - it has {recent_transactions} transactions in the last 30 days."
        )
        return redirect(url_for("accounts.view", id=id))

    try:
        account.is_active = False
        db.session.commit()

        flash(f'Account "{account.account_name}" has been deactivated.')
        return redirect(url_for("accounts.index"))

    except Exception as e:
        db.session.rollback()
        flash(f"Error deactivating account: {str(e)}")
        return redirect(url_for("accounts.view", id=id))


@accounts_bp.route("/<int:id>/reactivate", methods=["POST"])
def reactivate(id):
    """Reactivate a deactivated account"""
    account = Account.query.get_or_404(id)

    try:
        account.is_active = True
        db.session.commit()

        flash(f'Account "{account.account_name}" has been reactivated.')
        return redirect(url_for("accounts.view", id=id))

    except Exception as e:
        db.session.rollback()
        flash(f"Error reactivating account: {str(e)}")
        return redirect(url_for("accounts.view", id=id))


@accounts_bp.route("/<int:id>/transfer", methods=["GET", "POST"])
def transfer(id):
    """Transfer money between accounts"""
    from_account = Account.query.get_or_404(id)

    if request.method == "POST":
        try:
            to_account_id = request.form["to_account_id"]
            amount = Decimal(request.form["amount"])
            description = request.form.get("description", "Internal transfer")

            to_account = Account.query.get(to_account_id)
            if not to_account:
                flash("Destination account not found.")
                return redirect(url_for("accounts.transfer", id=id))

            if amount <= 0:
                flash("Transfer amount must be positive.")
                return redirect(url_for("accounts.transfer", id=id))

            # Check sufficient balance (allow small overdraft for current accounts)
            from_account.calculate_current_balance()
            overdraft_limit = 100 if from_account.account_type == "current" else 0

            if float(from_account.current_balance) + overdraft_limit < float(amount):
                flash(
                    f"Insufficient funds. Available: £{float(from_account.current_balance) + overdraft_limit:.2f}"
                )
                return redirect(url_for("accounts.transfer", id=id))

            # Create transfer source if needed
            source = Source.query.filter_by(type="transfer").first()
            if not source:
                source = Source(
                    name="Internal Transfer", type="transfer", is_active=True
                )
                db.session.add(source)
                db.session.flush()

            # Create debit transaction (from account)
            debit_transaction = Transaction(
                date=date.today(),
                description=f"Transfer to {to_account.account_name}: {description}",
                amount=-amount,  # Negative for debit
                account_id=from_account.id,
                source_id=source.id,
                source_type="transfer",
            )

            # Create credit transaction (to account)
            credit_transaction = Transaction(
                date=date.today(),
                description=f"Transfer from {from_account.account_name}: {description}",
                amount=amount,  # Positive for credit
                account_id=to_account.id,
                source_id=source.id,
                source_type="transfer",
            )

            db.session.add(debit_transaction)
            db.session.add(credit_transaction)

            # Update balances
            from_account.calculate_current_balance()
            to_account.calculate_current_balance()

            db.session.commit()

            flash(
                f"Successfully transferred £{amount:.2f} from {from_account.account_name} to {to_account.account_name}"
            )
            return redirect(url_for("accounts.view", id=id))

        except Exception as e:
            db.session.rollback()
            flash(f"Error processing transfer: {str(e)}")

    # Get available accounts for transfer (exclude current account and inactive accounts)
    available_accounts = (
        Account.query.filter(Account.id != id, Account.is_active == True)
        .order_by(Account.account_name)
        .all()
    )

    return render_template(
        "accounts/transfer.html",
        from_account=from_account,
        available_accounts=available_accounts,
    )


# API endpoints
@accounts_bp.route("/api/list")
def api_list():
    """API endpoint for account list"""
    accounts = Account.query.filter_by(is_active=True).all()

    account_list = []
    for account in accounts:
        account.calculate_current_balance()
        account_list.append(
            {
                "id": account.id,
                "user_id": account.user_id,
                "user_name": account.user.full_name if account.user else "Unknown",
                "account_name": account.account_name,
                "account_type": account.account_type,
                "current_balance": float(account.current_balance),
                "opening_balance": float(account.opening_balance),
                "currency": account.currency,
                "is_connected": bool(account.bank_connection_id),
                "created_at": account.created_at.strftime("%Y-%m-%d"),
            }
        )

    return jsonify(account_list)


@accounts_bp.route("/api/<int:id>/balance")
def api_balance(id):
    """API endpoint for account balance"""
    account = Account.query.get_or_404(id)
    account.calculate_current_balance()

    return jsonify(
        {
            "account_id": account.id,
            "current_balance": float(account.current_balance),
            "opening_balance": float(account.opening_balance),
            "balance_change": float(account.current_balance)
            - float(account.opening_balance),
            "currency": account.currency,
            "last_updated": datetime.utcnow().isoformat(),
        }
    )


@accounts_bp.route("/api/<int:id>/summary")
def api_summary(id):
    """API endpoint for account summary"""
    account = Account.query.get_or_404(id)
    account.calculate_current_balance()

    # Get transaction counts and totals
    total_transactions = Transaction.query.filter_by(account_id=id).count()

    # This month's activity
    current_month_start = date.today().replace(day=1)
    monthly_transactions = Transaction.query.filter(
        Transaction.account_id == id, Transaction.date >= current_month_start
    ).all()

    monthly_total = sum(float(tx.amount) for tx in monthly_transactions)
    monthly_count = len(monthly_transactions)

    return jsonify(
        {
            "account": {
                "id": account.id,
                "name": account.account_name,
                "type": account.account_type,
                "current_balance": float(account.current_balance),
                "opening_balance": float(account.opening_balance),
            },
            "statistics": {
                "total_transactions": total_transactions,
                "monthly_transactions": monthly_count,
                "monthly_total": monthly_total,
                "balance_change": float(account.current_balance)
                - float(account.opening_balance),
            },
        }
    )


# Helper function to create account-related templates
def create_account_templates():
    """Template creation guide for account management"""
    templates_info = {
        "accounts/index.html": "List all accounts with balances and quick actions",
        "accounts/add.html": "Form to add new account to existing user",
        "accounts/view.html": "Account details with transaction history",
        "accounts/edit.html": "Edit account details and opening balance",
        "accounts/transfer.html": "Transfer money between accounts",
    }

    return templates_info
