# blueprints/categories.py - Full CRUD operations for categories
from flask import Blueprint, request, render_template, redirect, url_for, flash, jsonify
from app import db
from models import Category, Transaction
from datetime import datetime

categories_bp = Blueprint("categories", __name__)


@categories_bp.route("/")
def index():
    """List all categories with full management"""
    categories = Category.query.order_by(Category.type, Category.name).all()

    # Group by type and add transaction counts
    income_categories = []
    expense_categories = []

    for cat in categories:
        cat.transaction_count = len(cat.transactions)
        cat.total_amount = sum(float(tx.amount) for tx in cat.transactions)

        if cat.type == "income":
            income_categories.append(cat)
        else:
            expense_categories.append(cat)

    return render_template(
        "categories/index.html",
        income_categories=income_categories,
        expense_categories=expense_categories,
    )


@categories_bp.route("/add", methods=["GET", "POST"])
def add():
    """Add new category"""
    if request.method == "POST":
        try:
            category = Category(
                name=request.form["name"],
                type=request.form["type"],
                description=request.form.get("description", ""),
                color=request.form.get("color", "#3498db"),
                parent_id=request.form.get("parent_id") or None,
                monthly_budget=float(request.form.get("monthly_budget", 0)) or None,
                is_recurring=bool(request.form.get("is_recurring")),
            )

            db.session.add(category)
            db.session.commit()

            flash(f'Category "{category.name}" created successfully!')
            return redirect(url_for("categories.index"))

        except Exception as e:
            db.session.rollback()
            flash(f"Error creating category: {str(e)}")

    # Get parent categories for dropdown
    parent_categories = Category.query.filter_by(parent_id=None).all()

    return render_template("categories/add.html", parent_categories=parent_categories)


@categories_bp.route("/<int:id>")
def view(id):
    """View category details with transactions"""
    category = Category.query.get_or_404(id)

    # Get pagination parameters
    page = request.args.get("page", 1, type=int)
    per_page = 25

    # Get transactions for this category
    transactions = (
        Transaction.query.filter_by(category_id=id)
        .order_by(Transaction.date.desc())
        .paginate(page=page, per_page=per_page)
    )

    # Calculate category statistics
    total_amount = sum(float(tx.amount) for tx in category.transactions)
    transaction_count = len(category.transactions)
    avg_amount = total_amount / transaction_count if transaction_count > 0 else 0

    # Monthly breakdown
    monthly_stats = (
        db.session.query(
            db.func.strftime("%Y-%m", Transaction.date).label("month"),
            db.func.sum(Transaction.amount).label("total"),
            db.func.count(Transaction.id).label("count"),
        )
        .filter(Transaction.category_id == id)
        .group_by("month")
        .order_by("month")
        .all()
    )

    stats = {
        "total_amount": total_amount,
        "transaction_count": transaction_count,
        "avg_amount": avg_amount,
        "monthly_stats": monthly_stats,
    }

    return render_template(
        "categories/view.html",
        category=category,
        transactions=transactions,
        stats=stats,
    )


@categories_bp.route("/<int:id>/edit", methods=["GET", "POST"])
def edit(id):
    """Edit existing category"""
    category = Category.query.get_or_404(id)

    if request.method == "POST":
        try:
            category.name = request.form["name"]
            category.type = request.form["type"]
            category.description = request.form.get("description", "")
            category.color = request.form.get("color", category.color)
            category.parent_id = request.form.get("parent_id") or None
            category.monthly_budget = (
                float(request.form.get("monthly_budget", 0)) or None
            )
            category.is_recurring = bool(request.form.get("is_recurring"))

            db.session.commit()

            flash(f'Category "{category.name}" updated successfully!')
            return redirect(url_for("categories.view", id=category.id))

        except Exception as e:
            db.session.rollback()
            flash(f"Error updating category: {str(e)}")

    # Get parent categories (excluding self and descendants)
    parent_categories = Category.query.filter(
        Category.parent_id.is_(None), Category.id != id
    ).all()

    return render_template(
        "categories/edit.html", category=category, parent_categories=parent_categories
    )


@categories_bp.route("/<int:id>/delete", methods=["POST"])
def delete(id):
    """Delete category (with safety checks)"""
    category = Category.query.get_or_404(id)

    # Check if category has transactions
    if category.transactions:
        flash(
            f'Cannot delete category "{category.name}" - it has {len(category.transactions)} transactions. Please reassign transactions first.'
        )
        return redirect(url_for("categories.view", id=id))

    # Check if category has subcategories
    if category.subcategories:
        flash(
            f'Cannot delete category "{category.name}" - it has subcategories. Please reassign or delete subcategories first.'
        )
        return redirect(url_for("categories.view", id=id))

    try:
        category_name = category.name
        db.session.delete(category)
        db.session.commit()

        flash(f'Category "{category_name}" deleted successfully!')
        return redirect(url_for("categories.index"))

    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting category: {str(e)}")
        return redirect(url_for("categories.view", id=id))


@categories_bp.route("/bulk-categorize", methods=["POST"])
def bulk_categorize():
    """Bulk categorize uncategorized transactions"""
    try:
        # Get uncategorized transactions
        uncategorized = Transaction.query.filter_by(category_id=None).all()

        categorized_count = 0

        # Simple auto-categorization rules
        categorization_rules = {
            "salary": {
                "keywords": ["salary", "payroll", "wages"],
                "category_name": "Salary",
            },
            "groceries": {
                "keywords": ["tesco", "asda", "sainsbury", "morrisons", "aldi", "lidl"],
                "category_name": "Groceries",
            },
            "fuel": {
                "keywords": ["bp", "shell", "esso", "texaco", "petrol", "fuel"],
                "category_name": "Transport",
            },
            "utilities": {
                "keywords": ["electric", "gas", "water", "council tax"],
                "category_name": "Utilities",
            },
            "internet": {
                "keywords": ["bt", "sky", "virgin", "broadband", "internet"],
                "category_name": "Utilities",
            },
        }

        for transaction in uncategorized:
            description_lower = transaction.description.lower()

            for rule_key, rule_data in categorization_rules.items():
                if any(
                    keyword in description_lower for keyword in rule_data["keywords"]
                ):
                    # Find or create category
                    category = Category.query.filter_by(
                        name=rule_data["category_name"]
                    ).first()
                    if category:
                        transaction.category_id = category.id
                        categorized_count += 1
                        break

        db.session.commit()
        flash(f"Successfully categorized {categorized_count} transactions!")

    except Exception as e:
        db.session.rollback()
        flash(f"Error during bulk categorization: {str(e)}")

    return redirect(url_for("categories.index"))


@categories_bp.route("/stats")
def stats():
    """Category statistics and analytics"""
    # Monthly category breakdown
    monthly_breakdown = (
        db.session.query(
            Category.name,
            Category.color,
            db.func.strftime("%Y-%m", Transaction.date).label("month"),
            db.func.sum(Transaction.amount).label("total"),
        )
        .join(Transaction)
        .group_by(Category.id, "month")
        .order_by("month", Category.name)
        .all()
    )

    # Top spending categories
    top_categories = (
        db.session.query(
            Category.name,
            Category.color,
            db.func.sum(Transaction.amount).label("total"),
            db.func.count(Transaction.id).label("count"),
        )
        .join(Transaction)
        .group_by(Category.id)
        .order_by(db.func.sum(Transaction.amount))
        .limit(10)
        .all()
    )

    # Budget vs actual spending
    budget_comparison = []
    categories_with_budgets = Category.query.filter(
        Category.monthly_budget.isnot(None)
    ).all()

    from datetime import date

    current_month = date.today().strftime("%Y-%m")

    for category in categories_with_budgets:
        actual_spending = (
            db.session.query(db.func.sum(Transaction.amount))
            .filter(Transaction.category_id == category.id)
            .filter(db.func.strftime("%Y-%m", Transaction.date) == current_month)
            .scalar()
            or 0
        )

        budget_comparison.append(
            {
                "category": category,
                "budget": float(category.monthly_budget),
                "actual": float(actual_spending),
                "variance": float(actual_spending) - float(category.monthly_budget),
                "percentage": (
                    float(actual_spending) / float(category.monthly_budget) * 100
                )
                if category.monthly_budget != 0
                else 0,
            }
        )

    return render_template(
        "categories/stats.html",
        monthly_breakdown=monthly_breakdown,
        top_categories=top_categories,
        budget_comparison=budget_comparison,
        current_month=current_month,
    )


# API endpoints for AJAX operations
@categories_bp.route("/api/list")
def api_list():
    """API endpoint for category list"""
    categories = Category.query.order_by(Category.name).all()

    return jsonify(
        [
            {
                "id": cat.id,
                "name": cat.name,
                "type": cat.type,
                "color": cat.color,
                "description": cat.description,
                "transaction_count": len(cat.transactions),
                "monthly_budget": float(cat.monthly_budget)
                if cat.monthly_budget
                else None,
            }
            for cat in categories
        ]
    )


@categories_bp.route("/api/<int:id>/transactions")
def api_category_transactions(id):
    """API endpoint for category transactions"""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    transactions = (
        Transaction.query.filter_by(category_id=id)
        .order_by(Transaction.date.desc())
        .paginate(page=page, per_page=per_page)
    )

    return jsonify(
        {
            "transactions": [
                {
                    "id": tx.id,
                    "date": tx.date.strftime("%Y-%m-%d"),
                    "description": tx.description,
                    "amount": float(tx.amount),
                    "source": tx.source.name if tx.source else None,
                }
                for tx in transactions.items
            ],
            "pagination": {
                "page": page,
                "pages": transactions.pages,
                "total": transactions.total,
                "per_page": per_page,
            },
        }
    )
