from flask import Flask, request, redirect, url_for, flash, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import io
import csv
from datetime import datetime, date
import os


app = Flask(__name__)
# Set a secret key for session management and flash messages
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-please-change')

# Add required app config for SQLAlchemy
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(basedir, 'banking.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)
from models import define_models
User, Source, Category, Transaction, RecurringPattern, Account = define_models(db)

@app.route('/transactions/import', methods=['GET', 'POST'])
def import_transactions():
    """Import transactions from CSV file"""
    if request.method == 'POST':
        try:
            # Check if file was uploaded
            if 'csv_file' not in request.files:
                flash('No file selected')
                return redirect(request.url)

            file = request.files['csv_file']
            if file.filename == '':
                flash('No file selected')
                return redirect(request.url)

            if file and file.filename.lower().endswith('.csv'):
                # Read CSV content
                import csv
                import io

                # Decode file content
                stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
                csv_input = csv.DictReader(stream)

                # Process CSV rows
                imported_count = 0
                errors = []

                # Get or create CSV import source ONCE before the loop (by name only, due to UNIQUE constraint)
                csv_source = Source.query.filter_by(name='CSV Import').first()
                if not csv_source:
                    csv_source = Source(
                        name='CSV Import',
                        type='csv_import',
                        is_active=True
                    )
                    db.session.add(csv_source)
                    db.session.flush()

                for row_num, row in enumerate(csv_input, start=2):  # Start at 2 for header
                    try:
                        # Map CSV columns (adjust these based on your CSV format)
                        transaction_date = row.get('Transaction Date', '').strip()
                        description = row.get('Transaction Description', '').strip()

                        # Parse date (adjust format as needed)
                        if transaction_date:
                            try:
                                # Try different date formats
                                for date_format in ['%d/%m/%Y', '%Y-%m-%d', '%m/%d/%Y']:
                                    try:
                                        parsed_date = datetime.strptime(transaction_date, date_format).date()
                                        break
                                    except ValueError:
                                        continue
                                else:
                                    errors.append(f"Row {row_num}: Invalid date format '{transaction_date}'")
                                    continue
                            except:
                                errors.append(f"Row {row_num}: Could not parse date '{transaction_date}'")
                                continue
                        else:
                            errors.append(f"Row {row_num}: Missing date")
                            continue

                        # Parse amount from Credit/Debit columns
                        credit_str = row.get('Credit Amount', '').replace('£', '').replace(',', '').strip()
                        debit_str = row.get('Debit Amount', '').replace('£', '').replace(',', '').strip()
                        amount = None
                        if credit_str:
                            try:
                                amount = float(credit_str)
                            except ValueError:
                                errors.append(f"Row {row_num}: Invalid credit amount '{credit_str}'")
                                continue
                        elif debit_str:
                            try:
                                amount = -float(debit_str)
                            except ValueError:
                                errors.append(f"Row {row_num}: Invalid debit amount '{debit_str}'")
                                continue
                        else:
                            errors.append(f"Row {row_num}: Missing amount")
                            continue

                        if not description:
                            description = 'Imported transaction'

                        # Create transaction
                        transaction = Transaction(
                            date=parsed_date,
                            description=description,
                            amount=amount,
                            source_id=csv_source.id,
                            source_type='csv_import',
                            created_at=datetime.utcnow()
                        )

                        db.session.add(transaction)
                        imported_count += 1

                    except Exception as e:
                        errors.append(f"Row {row_num}: {str(e)}")
                        continue

                # Commit all transactions
                db.session.commit()

                # Show results
                if imported_count > 0:
                    flash(f'Successfully imported {imported_count} transactions!')

                if errors:
                    if len(errors) <= 5:
                        for error in errors:
                            flash(f'Error: {error}', 'error')
                    else:
                        flash(f'{len(errors)} rows had errors. First few: {", ".join(errors[:3])}...', 'error')

                return redirect(url_for('transactions'))

            else:
                flash('Please upload a CSV file')

        except Exception as e:
            db.session.rollback()
            flash(f'Import failed: {str(e)}')

    return render_template('transactions/import.html')

@app.route('/transactions/add', methods=['GET', 'POST'])
def add_transaction():
    """Add single transaction manually"""
    if request.method == 'POST':
        try:
            date_str = request.form.get('date')
            description = request.form.get('description')
            amount = float(request.form.get('amount'))
            category_id = request.form.get('category_id') or None

            # Parse date
            transaction_date = datetime.strptime(date_str, '%Y-%m-%d').date()

            # Get or create manual entry source
            manual_source = Source.query.filter_by(type='manual').first()
            if not manual_source:
                manual_source = Source(
                    name='Manual Entry',
                    type='manual',
                    is_active=True
                )
                db.session.add(manual_source)
                db.session.flush()

            # Create transaction
            transaction = Transaction(
                date=transaction_date,
                description=description,
                amount=amount,
                category_id=category_id,
                source_id=manual_source.id,
                source_type='manual'
            )

            db.session.add(transaction)
            db.session.commit()

            flash(f'Transaction "{description}" added successfully!')
            return redirect(url_for('transactions'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error adding transaction: {str(e)}')

    # Get categories for dropdown
    categories = Category.query.order_by(Category.name).all()

    return render_template('transactions/add.html', categories=categories)

@app.route('/transactions/export')
def export_transactions():
    """Export transactions to CSV"""
    try:
        import csv
        from flask import make_response

        # Get all transactions
        transactions = Transaction.query.order_by(Transaction.date.desc()).all()

        # Create CSV response
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            'Date', 'Description', 'Amount', 'Category', 'Source', 'Reference'
        ])

        # Write transaction data
        for tx in transactions:
            writer.writerow([
                tx.date.strftime('%d/%m/%Y'),
                tx.description,
                float(tx.amount),
                tx.category.name if tx.category else '',
                tx.source.name if tx.source else '',
                tx.reference or ''
            ])

        # Create response
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=transactions_{date.today().strftime("%Y%m%d")}.csv'

        return response

    except Exception as e:
        flash(f'Export failed: {str(e)}')
        return redirect(url_for('transactions'))

@app.route("/")
def dashboard():
    accounts = Account.query.all()
    total_balance = sum([a.current_balance or 0 for a in accounts])
    return render_template("dashboard.html", accounts=accounts, total_balance=total_balance)

@app.route("/users")
def users():
    user_list = User.query.all()
    return render_template("users.html", users=user_list)

@app.route("/add-user", methods=["GET", "POST"])
def add_user():
    if request.method == "POST":
        # Add user creation logic here
        pass
    return render_template("add_user.html")

@app.route("/transactions")
def transactions():
    page = request.args.get('page', 1, type=int)
    transactions = Transaction.query.order_by(Transaction.date.desc()).paginate(page=page, per_page=20)
    return render_template("transactions/transactions.html", transactions=transactions)

@app.template_filter('currency')
def currency_filter(value):
    try:
        return f"£{float(value):,.2f}"
    except (ValueError, TypeError):
        return value

@app.template_filter('date_uk')
def date_uk_filter(value):
    try:
        return value.strftime('%d/%m/%Y')
    except Exception:
        return value

if __name__ == "__main__":
    app.run(debug=True)
