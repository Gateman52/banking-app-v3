# migrate_database.py - Add missing tables to existing banking.db
import sqlite3
import os
from datetime import datetime


def migrate_database():
    """Add missing tables to existing banking.db while preserving all data"""

    print("🔧 Banking Database Migration")
    print("=" * 50)

    # Check if database exists
    if not os.path.exists("banking.db"):
        print("❌ banking.db not found!")
        print("Please make sure banking.db is in the current directory.")
        return False

    # Create backup first
    backup_name = f"banking_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    print(f"📁 Creating backup: {backup_name}")

    import shutil

    shutil.copy2("banking.db", backup_name)
    print(f"✅ Backup created successfully!")

    # Connect to database
    conn = sqlite3.connect("banking.db")
    cursor = conn.cursor()

    try:
        print("\n🔍 Checking existing tables...")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = [table[0] for table in cursor.fetchall()]
        print(f"Found tables: {', '.join(existing_tables)}")

        # Add missing tables
        tables_to_add = []

        # 1. Users table
        if "users" not in existing_tables:
            print("\n➕ Adding users table...")
            cursor.execute("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    username VARCHAR(80) UNIQUE NOT NULL,
                    email VARCHAR(120) UNIQUE NOT NULL,
                    first_name VARCHAR(100) NOT NULL,
                    last_name VARCHAR(100) NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1
                )
            """)
            tables_to_add.append("users")

        # 2. Accounts table
        if "accounts" not in existing_tables:
            print("➕ Adding accounts table...")
            cursor.execute("""
                CREATE TABLE accounts (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    account_name VARCHAR(100) NOT NULL,
                    account_type VARCHAR(50) DEFAULT 'current',
                    opening_balance NUMERIC(10, 2) DEFAULT 0.00,
                    current_balance NUMERIC(10, 2) DEFAULT 0.00,
                    currency VARCHAR(3) DEFAULT 'GBP',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    bank_connection_id VARCHAR(255),
                    external_account_id VARCHAR(255),
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
            tables_to_add.append("accounts")

        # 3. Add columns to existing transactions table if needed
        print("\n🔧 Checking transactions table structure...")
        cursor.execute("PRAGMA table_info(transactions)")
        transaction_columns = [col[1] for col in cursor.fetchall()]

        # Add account_id column if missing
        if "account_id" not in transaction_columns:
            print("➕ Adding account_id column to transactions...")
            cursor.execute("ALTER TABLE transactions ADD COLUMN account_id INTEGER")

        # Add is_projected column if missing
        if "is_projected" not in transaction_columns:
            print("➕ Adding is_projected column to transactions...")
            cursor.execute(
                "ALTER TABLE transactions ADD COLUMN is_projected BOOLEAN DEFAULT 0"
            )

        # Add recurring_pattern_id column if missing
        if "recurring_pattern_id" not in transaction_columns:
            print("➕ Adding recurring_pattern_id column to transactions...")
            cursor.execute(
                "ALTER TABLE transactions ADD COLUMN recurring_pattern_id INTEGER"
            )

        # 4. Update categories table with new columns
        print("\n🔧 Updating categories table...")
        cursor.execute("PRAGMA table_info(categories)")
        category_columns = [col[1] for col in cursor.fetchall()]

        # Add monthly_budget column if missing
        if "monthly_budget" not in category_columns:
            print("➕ Adding monthly_budget column to categories...")
            cursor.execute(
                "ALTER TABLE categories ADD COLUMN monthly_budget NUMERIC(10, 2)"
            )

        # Add is_recurring column if missing
        if "is_recurring" not in category_columns:
            print("➕ Adding is_recurring column to categories...")
            cursor.execute(
                "ALTER TABLE categories ADD COLUMN is_recurring BOOLEAN DEFAULT 0"
            )

        # 5. Update recurring_patterns table
        cursor.execute("PRAGMA table_info(recurring_patterns)")
        pattern_columns = [col[1] for col in cursor.fetchall()]

        if "category_id" not in pattern_columns:
            print("➕ Adding category_id column to recurring_patterns...")
            cursor.execute(
                "ALTER TABLE recurring_patterns ADD COLUMN category_id INTEGER"
            )

        if "is_active" not in pattern_columns:
            print("➕ Adding is_active column to recurring_patterns...")
            cursor.execute(
                "ALTER TABLE recurring_patterns ADD COLUMN is_active BOOLEAN DEFAULT 1"
            )

        if "confidence_score" not in pattern_columns:
            print("➕ Adding confidence_score column to recurring_patterns...")
            cursor.execute(
                "ALTER TABLE recurring_patterns ADD COLUMN confidence_score REAL DEFAULT 0.0"
            )

        # 6. Create default user and account for existing transactions
        print("\n👤 Creating default user and account...")

        # Create default user
        cursor.execute(
            """
            INSERT INTO users (username, email, first_name, last_name, created_at)
            VALUES ('default.user', 'user@example.com', 'Default', 'User', ?)
        """,
            (datetime.now(),),
        )

        default_user_id = cursor.lastrowid
        print(f"✅ Created default user with ID: {default_user_id}")

        # Create default account
        cursor.execute(
            """
            INSERT INTO accounts (user_id, account_name, account_type, opening_balance, current_balance, created_at)
            VALUES (?, 'Main Account', 'current', 0.00, 0.00, ?)
        """,
            (default_user_id, datetime.now()),
        )

        default_account_id = cursor.lastrowid
        print(f"✅ Created default account with ID: {default_account_id}")

        # Link all existing transactions to default account
        print("🔗 Linking existing transactions to default account...")
        cursor.execute(
            """
            UPDATE transactions
            SET account_id = ?
            WHERE account_id IS NULL
        """,
            (default_account_id,),
        )

        transactions_updated = cursor.rowcount
        print(f"✅ Linked {transactions_updated} transactions to default account")

        # Calculate and update account balance based on transactions
        cursor.execute(
            "SELECT SUM(amount) FROM transactions WHERE account_id = ?",
            (default_account_id,),
        )
        total_balance = cursor.fetchone()[0] or 0

        cursor.execute(
            """
            UPDATE accounts
            SET current_balance = ?, opening_balance = 0.00
            WHERE id = ?
        """,
            (total_balance, default_account_id),
        )

        print(f"✅ Updated account balance to £{total_balance:.2f}")

        # Commit all changes
        conn.commit()

        print("\n🎉 Migration completed successfully!")
        print("=" * 50)
        print("📊 Summary:")
        print(
            f"  • Tables added: {', '.join(tables_to_add) if tables_to_add else 'None (already existed)'}"
        )
        print(f"  • Default user created: default.user")
        print(f"  • Default account created: Main Account")
        print(f"  • Transactions linked: {transactions_updated}")
        print(f"  • Account balance: £{total_balance:.2f}")
        print(f"  • Backup saved as: {backup_name}")

        # Verify data integrity
        cursor.execute("SELECT COUNT(*) FROM transactions")
        transaction_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM categories")
        category_count = cursor.fetchone()[0]

        print(f"  • Transactions preserved: {transaction_count}")
        print(f"  • Categories preserved: {category_count}")

        print("\n✅ Your banking app is now ready to run!")
        print("Run: python app.py")

        return True

    except Exception as e:
        print(f"\n❌ Migration failed: {str(e)}")
        conn.rollback()

        # Restore backup
        print(f"🔄 Restoring backup from {backup_name}...")
        shutil.copy2(backup_name, "banking.db")
        print("✅ Database restored from backup")

        return False

    finally:
        conn.close()


if __name__ == "__main__":
    print("This script will add missing tables to your existing banking.db")
    print("Your transaction and category data will be preserved.")
    print("")

    response = input("Continue with migration? (y/N): ")
    if response.lower() == "y":
        success = migrate_database()

        if success:
            print("\n🚀 Next steps:")
            print("1. Run: python app.py")
            print("2. Visit: http://127.0.0.1:5000")
            print("3. Check your dashboard with preserved data")
            print("4. Add additional users if needed")
        else:
            print("\n❌ Migration failed. Check the error above.")
    else:
        print("Migration cancelled.")
