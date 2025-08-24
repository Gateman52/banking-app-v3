import csv
from datetime import datetime
from flask import current_app

class TransactionHelper:
    def import_from_csv(self, csv_input):
        from app import db, Transaction
        imported_count = 0
        for row in csv_input:
            try:
                # Map CSV fields
                date_str = row.get("Transaction Date")
                description = row.get("Transaction Description")
                debit = row.get("Debit Amount") or "0"
                credit = row.get("Credit Amount") or "0"
                # Calculate amount: credit - debit
                try:
                    amount = float(credit.replace(",", "")) - float(debit.replace(",", ""))
                except Exception:
                    amount = 0
                # Parse date (try common formats)
                date = None
                for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                    try:
                        date = datetime.strptime(date_str, fmt).date()
                        break
                    except Exception:
                        continue
                # Create transaction
                transaction = Transaction(
                    date=date,
                    description=description,
                    amount=amount,
                    category_id=None
                )
                db.session.add(transaction)
                imported_count += 1
            except Exception as e:
                current_app.logger.error(f"Error importing row: {row} - {e}")
        db.session.commit()
        return imported_count
