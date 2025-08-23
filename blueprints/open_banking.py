# blueprints/open_banking.py - UK Open Banking Integration
from flask import (
    Blueprint,
    request,
    render_template,
    redirect,
    url_for,
    flash,
    jsonify,
    session,
)
from app import db
from models import Account, Transaction, Source, User, Category
from datetime import datetime, date, timedelta
import requests
import json
import uuid

open_banking_bp = Blueprint("open_banking", __name__)

# UK Open Banking Configuration
OPEN_BANKING_CONFIG = {
    "base_url": "https://api.openbanking.org.uk",  # Replace with actual provider
    "client_id": "your_client_id",  # Get from your Open Banking provider
    "client_secret": "your_client_secret",
    "redirect_uri": "http://localhost:5000/open-banking/callback",
    "scopes": ["accounts", "transactions"],
    "supported_banks": {
        "lloyds": {
            "name": "Lloyds Banking Group",
            "base_url": "https://api.lloydsbanking.com/open-banking",
            "logo": "/static/images/lloyds-logo.png",
        },
        "barclays": {
            "name": "Barclays",
            "base_url": "https://api.barclays.com/open-banking",
            "logo": "/static/images/barclays-logo.png",
        },
        "hsbc": {
            "name": "HSBC",
            "base_url": "https://api.hsbc.co.uk/open-banking",
            "logo": "/static/images/hsbc-logo.png",
        },
        "natwest": {
            "name": "NatWest Group",
            "base_url": "https://api.natwest.com/open-banking",
            "logo": "/static/images/natwest-logo.png",
        },
    },
}


class OpenBankingService:
    """Service class for UK Open Banking operations"""

    def __init__(self, provider="lloyds"):
        self.provider = provider
        self.config = OPEN_BANKING_CONFIG["supported_banks"].get(provider)
        if not self.config:
            raise ValueError(f"Unsupported banking provider: {provider}")

    def get_authorization_url(self, user_id, account_id=None):
        """Generate OAuth2 authorization URL for bank connection"""
        state = str(uuid.uuid4())
        session["oauth_state"] = state
        session["connecting_user_id"] = user_id
        if account_id:
            session["connecting_account_id"] = account_id

        params = {
            "response_type": "code",
            "client_id": OPEN_BANKING_CONFIG["client_id"],
            "redirect_uri": OPEN_BANKING_CONFIG["redirect_uri"],
            "scope": " ".join(OPEN_BANKING_CONFIG["scopes"]),
            "state": state,
        }

        auth_url = f"{self.config['base_url']}/auth?" + "&".join(
            [f"{k}={v}" for k, v in params.items()]
        )
        return auth_url

    def exchange_code_for_tokens(self, authorization_code):
        """Exchange authorization code for access tokens"""
        token_data = {
            "grant_type": "authorization_code",
            "code": authorization_code,
            "client_id": OPEN_BANKING_CONFIG["client_id"],
            "client_secret": OPEN_BANKING_CONFIG["client_secret"],
            "redirect_uri": OPEN_BANKING_CONFIG["redirect_uri"],
        }

        # In production, make actual API call
        # response = requests.post(f"{self.config['base_url']}/token", data=token_data)
        # return response.json()

        # Mock response for development
        return {
            "access_token": f"mock_access_token_{uuid.uuid4()}",
            "refresh_token": f"mock_refresh_token_{uuid.uuid4()}",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

    def get_account_information(self, access_token):
        """Fetch account information from bank"""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        # In production, make actual API call
        # response = requests.get(f"{self.config['base_url']}/accounts", headers=headers)
        # return response.json()

        # Mock response for development
        return {
            "accounts": [
                {
                    "account_id": f"acc_{uuid.uuid4()}",
                    "account_type": "Personal",
                    "account_sub_type": "CurrentAccount",
                    "currency": "GBP",
                    "nickname": "Main Current Account",
                    "account": {
                        "name": "Mr J Smith",
                        "identification": "12345678",
                        "scheme_name": "UK.OBIE.SortCodeAccountNumber",
                    },
                }
            ]
        }

    def get_transactions(self, access_token, account_id, from_date=None, to_date=None):
        """Fetch transactions from bank account"""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        params = {}
        if from_date:
            params["fromBookingDateTime"] = from_date.strftime("%Y-%m-%dT00:00:00Z")
        if to_date:
            params["toBookingDateTime"] = to_date.strftime("%Y-%m-%dT23:59:59Z")

        # In production, make actual API call
        # url = f"{self.config['base_url']}/accounts/{account_id}/transactions"
        # response = requests.get(url, headers=headers, params=params)
        # return response.json()

        # Mock response for development
        mock_transactions = []
        current_date = from_date or date.today() - timedelta(days=30)
        end_date = to_date or date.today()

        import random

        sample_merchants = [
            "TESCO STORES 3297",
            "AMAZON UK RETAIL",
            "SHELL PETROL STATION",
            "STARBUCKS COFFEE",
            "JOHN LEWIS PLC",
            "SAINSBURYS S/MKTS",
            "PAYPAL TRANSFER",
            "UBER TRIP",
            "SPOTIFY PREMIUM",
        ]

        while current_date <= end_date:
            if random.random() > 0.7:  # 30% chance of transaction per day
                amount = round(random.uniform(-150, 50), 2)
                mock_transactions.append(
                    {
                        "transaction_id": f"tx_{uuid.uuid4()}",
                        "amount": {"amount": str(amount), "currency": "GBP"},
                        "credit_debit_indicator": "Credit" if amount > 0 else "Debit",
                        "status": "Booked",
                        "booking_date_time": current_date.strftime(
                            "%Y-%m-%dT12:00:00Z"
                        ),
                        "value_date_time": current_date.strftime("%Y-%m-%dT12:00:00Z"),
                        "transaction_information": random.choice(sample_merchants),
                        "merchant_details": {
                            "merchant_name": random.choice(sample_merchants)
                        },
                    }
                )
            current_date += timedelta(days=1)

        return {"transactions": mock_transactions}


# Routes
@open_banking_bp.route("/")
def index():
    """Open Banking dashboard"""
    connected_accounts = Account.query.filter(
        Account.bank_connection_id.isnot(None)
    ).all()
    available_banks = OPEN_BANKING_CONFIG["supported_banks"]

    return render_template(
        "open_banking/index.html",
        connected_accounts=connected_accounts,
        available_banks=available_banks,
    )


@open_banking_bp.route("/connect")
def connect():
    """Start bank connection process"""
    users = User.query.filter_by(is_active=True).all()
    available_banks = OPEN_BANKING_CONFIG["supported_banks"]

    return render_template(
        "open_banking/connect.html", users=users, available_banks=available_banks
    )


@open_banking_bp.route("/authorize/<provider>")
def authorize(provider):
    """Redirect to bank authorization"""
    user_id = request.args.get("user_id")
    account_id = request.args.get("account_id")

    if not user_id:
        flash("Please select a user to connect the bank account to.")
        return redirect(url_for("open_banking.connect"))

    try:
        service = OpenBankingService(provider)
        auth_url = service.get_authorization_url(user_id, account_id)
        session["provider"] = provider
        return redirect(auth_url)

    except Exception as e:
        flash(f"Error initiating bank connection: {str(e)}")
        return redirect(url_for("open_banking.connect"))


@open_banking_bp.route("/callback")
def callback():
    """Handle OAuth callback from bank"""
    code = request.args.get("code")
    state = request.args.get("state")
    error = request.args.get("error")

    if error:
        flash(f"Bank authorization failed: {error}")
        return redirect(url_for("open_banking.connect"))

    if not code or state != session.get("oauth_state"):
        flash("Invalid authorization response from bank.")
        return redirect(url_for("open_banking.connect"))

    try:
        provider = session.get("provider", "lloyds")
        service = OpenBankingService(provider)

        # Exchange code for tokens
        tokens = service.exchange_code_for_tokens(code)

        # Get account information
        account_info = service.get_account_information(tokens["access_token"])

        # Create or update account connection
        user_id = session.get("connecting_user_id")
        user = User.query.get(user_id)

        if not user:
            flash("User not found.")
            return redirect(url_for("open_banking.connect"))

        # Create new account or update existing
        for bank_account in account_info["accounts"]:
            account = Account(
                user_id=user.id,
                account_name=f"{provider.title()} - {bank_account.get('nickname', 'Account')}",
                account_type="current",
                opening_balance=0.00,
                current_balance=0.00,
                bank_connection_id=tokens["access_token"][:50],  # Store connection ID
                external_account_id=bank_account["account_id"],
            )

            db.session.add(account)

        # Store tokens (in production, encrypt these!)
        from models import OpenBankToken

        token_record = OpenBankToken(
            provider=provider,
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token"),
            expires_at=datetime.utcnow()
            + timedelta(seconds=tokens.get("expires_in", 3600)),
        )
        db.session.add(token_record)

        db.session.commit()

        flash(f"Successfully connected {provider.title()} bank account!")
        return redirect(url_for("open_banking.sync_transactions", provider=provider))

    except Exception as e:
        db.session.rollback()
        flash(f"Error completing bank connection: {str(e)}")
        return redirect(url_for("open_banking.connect"))


@open_banking_bp.route("/sync/<provider>")
def sync_transactions(provider):
    """Sync transactions from connected bank"""
    try:
        service = OpenBankingService(provider)

        # Get the most recent token for this provider
        from models import OpenBankToken

        token_record = (
            OpenBankToken.query.filter_by(provider=provider)
            .order_by(OpenBankToken.created_at.desc())
            .first()
        )

        if not token_record or token_record.expires_at < datetime.utcnow():
            flash("Bank connection expired. Please reconnect.")
            return redirect(url_for("open_banking.connect"))

        # Get connected accounts for this provider
        connected_accounts = Account.query.filter(
            Account.bank_connection_id.isnot(None)
        ).all()

        total_imported = 0

        for account in connected_accounts:
            # Get transactions from the last 90 days
            from_date = date.today() - timedelta(days=90)
            transactions_data = service.get_transactions(
                token_record.access_token,
                account.external_account_id,
                from_date=from_date,
            )

            # Import transactions
            for tx_data in transactions_data["transactions"]:
                # Check if transaction already exists
                existing = Transaction.query.filter_by(
                    external_id=tx_data["transaction_id"]
                ).first()

                if existing:
                    continue

                # Parse transaction data
                amount = float(tx_data["amount"]["amount"])
                if tx_data["credit_debit_indicator"] == "Debit":
                    amount = -abs(amount)

                transaction_date = datetime.fromisoformat(
                    tx_data["booking_date_time"].replace("Z", "+00:00")
                ).date()

                # Create transaction
                transaction = Transaction(
                    external_id=tx_data["transaction_id"],
                    date=transaction_date,
                    description=tx_data.get("transaction_information", ""),
                    amount=amount,
                    account_id=account.id,
                    source_id=get_or_create_open_banking_source().id,
                    source_type="open_banking",
                    raw_data=json.dumps(tx_data),
                )

                db.session.add(transaction)
                total_imported += 1

            # Update account balance
            account.calculate_current_balance()

        db.session.commit()
        flash(
            f"Successfully imported {total_imported} new transactions from {provider.title()}!"
        )

    except Exception as e:
        db.session.rollback()
        flash(f"Error syncing transactions: {str(e)}")

    return redirect(url_for("open_banking.index"))


@open_banking_bp.route("/disconnect/<int:account_id>", methods=["POST"])
def disconnect_account(account_id):
    """Disconnect a bank account"""
    account = Account.query.get_or_404(account_id)

    if not account.bank_connection_id:
        flash("Account is not connected to Open Banking.")
        return redirect(url_for("open_banking.index"))

    try:
        account.bank_connection_id = None
        account.external_account_id = None
        db.session.commit()

        flash(f"Successfully disconnected {account.account_name}.")

    except Exception as e:
        db.session.rollback()
        flash(f"Error disconnecting account: {str(e)}")

    return redirect(url_for("open_banking.index"))


def get_or_create_open_banking_source():
    """Get or create Open Banking source"""
    source = Source.query.filter_by(type="open_banking").first()

    if not source:
        source = Source(name="Open Banking", type="open_banking", is_active=True)
        db.session.add(source)
        db.session.flush()

    return source


# Model for storing Open Banking tokens
class OpenBankToken(db.Model):
    __tablename__ = "openbank_tokens"

    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.Text, nullable=False)
    access_token = db.Column(db.Text)
    refresh_token = db.Column(db.Text)
    expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


# API endpoints
@open_banking_bp.route("/api/sync-all", methods=["POST"])
def api_sync_all():
    """API endpoint to sync all connected accounts"""
    try:
        total_imported = 0

        # Get all providers with active tokens
        from models import OpenBankToken

        active_tokens = OpenBankToken.query.filter(
            OpenBankToken.expires_at > datetime.utcnow()
        ).all()

        for token in active_tokens:
            service = OpenBankingService(token.provider)
            connected_accounts = Account.query.filter(
                Account.bank_connection_id.isnot(None)
            ).all()

            for account in connected_accounts:
                from_date = date.today() - timedelta(days=7)  # Last week only for API
                transactions_data = service.get_transactions(
                    token.access_token, account.external_account_id, from_date=from_date
                )

                for tx_data in transactions_data["transactions"]:
                    existing = Transaction.query.filter_by(
                        external_id=tx_data["transaction_id"]
                    ).first()

                    if not existing:
                        amount = float(tx_data["amount"]["amount"])
                        if tx_data["credit_debit_indicator"] == "Debit":
                            amount = -abs(amount)

                        transaction = Transaction(
                            external_id=tx_data["transaction_id"],
                            date=datetime.fromisoformat(
                                tx_data["booking_date_time"].replace("Z", "+00:00")
                            ).date(),
                            description=tx_data.get("transaction_information", ""),
                            amount=amount,
                            account_id=account.id,
                            source_id=get_or_create_open_banking_source().id,
                            source_type="open_banking",
                            raw_data=json.dumps(tx_data),
                        )

                        db.session.add(transaction)
                        total_imported += 1

        db.session.commit()

        return jsonify({"success": True, "transactions_imported": total_imported})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
