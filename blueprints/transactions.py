from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    current_app,
)
from markupsafe import Markup

transactions_bp = Blueprint("transactions", __name__, url_prefix="/transactions")


@transactions_bp.route("/")
def list_transactions():
    page = request.args.get("page", 1, type=int)
    per_page = 50
    category_filter = request.args.get("category")
    search_query = request.args.get("search", "")

    try:
        from models import Transaction, Category

        db = current_app.db

        query = Transaction.query.join(
            Category, Transaction.category_id == Category.id, isouter=True
        )
        if category_filter:
            query = query.filter(Transaction.category_id == category_filter)
        if search_query:
            search_param = f"%{search_query}%"
            query = query.filter(
                db.or_(
                    Transaction.description.like(search_param),
                    getattr(Transaction, "reference", "").like(search_param),
                )
            )
        query = query.order_by(Transaction.date.desc(), Transaction.id.desc())
        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        categories_list = Category.query.order_by(Category.name).all()
        return render_template(
            "transactions.html",
            transactions=paginated.items,
            categories=categories_list,
            current_page=page,
            total_pages=paginated.pages,
            total_transactions=paginated.total,
            category_filter=category_filter,
            search_query=search_query,
        )
    except Exception as e:
        flash(f"Error loading transactions: {e}", "error")
        return render_template("transactions.html")


@transactions_bp.route("/import", methods=["GET", "POST"])
def import_transactions():
    if request.method == "POST":
        if "file" not in request.files:
            flash("No file selected", "error")
            return redirect(request.url)
        file = request.files["file"]
        if file.filename == "":
            flash("No file selected", "error")
            return redirect(request.url)
        if file and file.filename.lower().endswith(".csv"):
            try:
                import csv
                import io

                stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
                csv_input = csv.DictReader(stream)
                imported_count = current_app.transaction_helper.import_from_csv(
                    csv_input
                )
                flash(f"Successfully imported {imported_count} transactions", "success")
                return redirect(url_for("transactions.list_transactions"))
            except Exception as e:
                flash(f"Error importing file: {e}", "error")
        else:
            flash("Please select a CSV file", "error")
    return render_template("import.html")


@transactions_bp.route("/categorize")
def categorize():
    try:
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 20, type=int)

        raw = current_app.transaction_helper.get_uncategorized_transactions(
            page=page, per_page=per_page
        )

        # Normalize raw -> (items, pagination_info)
        items = []
        total_uncategorized = 0
        total_pages = 1
        current_page = page

        # Common shapes:
        # - (paginated_obj, total)
        # - dict with keys: items/rows, total, pages, page
        # - list of items
        if isinstance(raw, tuple) and len(raw) == 2:
            paginated_part, total_uncategorized = raw
            if hasattr(paginated_part, "items"):
                items = list(paginated_part.items)
                total_pages = getattr(paginated_part, "pages", total_pages)
                current_page = getattr(paginated_part, "page", page)
            elif isinstance(paginated_part, dict):
                items = paginated_part.get("items") or paginated_part.get("rows") or []
                total_pages = paginated_part.get("pages", total_pages)
                current_page = paginated_part.get("page", page)
            else:
                # fallback: treat as iterable
                try:
                    items = list(paginated_part)
                except Exception:
                    items = []
        elif isinstance(raw, dict):
            items = raw.get("items") or raw.get("rows") or []
            total_uncategorized = raw.get("total") or raw.get("count") or 0
            total_pages = raw.get("pages", total_pages)
            current_page = raw.get("page", page)
        elif hasattr(raw, "items"):
            # maybe a pagination object returned directly
            items = list(raw.items)
            total_pages = getattr(raw, "pages", total_pages)
            current_page = getattr(raw, "page", page)
            total_uncategorized = getattr(raw, "total", len(items))
        else:
            try:
                items = list(raw)
                total_uncategorized = len(items)
            except Exception:
                items = []
                total_uncategorized = 0

        grouped = current_app.transaction_helper.group_transactions_by_description(
            items
        )
        from models import Category

        categories_list = Category.query.order_by(Category.name).all()
        return render_template(
            "categorize.html",
            grouped_transactions=grouped,
            categories=categories_list,
            total_uncategorized=total_uncategorized,
            current_page=current_page,
            total_pages=total_pages,
            per_page=per_page,
        )
    except Exception as e:
        flash(f"Error loading categorization page: {e}", "error")
        return redirect(url_for("main.dashboard"))


@transactions_bp.route("/categorize/<int:transaction_id>", methods=["POST"])
def update_category(transaction_id):
    category_id = request.form.get("category_id")
    try:
        transaction = current_app.transaction_helper.update_transaction_category(
            transaction_id, category_id
        )
        if transaction and category_id:
            from models import Transaction

            similar_count = Transaction.query.filter(
                current_app.db.func.lower(Transaction.description)
                == transaction.description.lower(),
                Transaction.category_id.is_(None),
                Transaction.id != transaction_id,
            ).count()
            if similar_count > 0:
                button_html = Markup(
                    "Transaction categorized successfully."
                    "<div class='mt-2'>"
                    f"<button class='btn btn-sm btn-outline-primary apply-same-btn' "
                    f"data-transaction-id='{transaction_id}' "
                    f"data-category-id='{category_id}'>"
                    "Apply to matching uncategorized transactions</button>"
                    "</div>"
                )
                flash(button_html, "success")
            else:
                flash("Transaction categorized successfully", "success")
        else:
            flash("Transaction updated", "success")
    except Exception as e:
        flash(f"Error updating category: {e}", "error")
    return redirect(url_for("transactions.categorize"))


@transactions_bp.route("/categorize/apply_same", methods=["POST"])
def apply_same():
    try:
        data = request.get_json() or {}
        transaction_id = data.get("transaction_id")
        transaction_ids = data.get("transaction_ids")
        category_id = data.get("category_id")
        if not category_id or (not transaction_id and not transaction_ids):
            return jsonify({"error": "Missing parameters"}), 400
        from models import Transaction

        src_ids = []
        if transaction_ids:
            src_ids = [int(i) for i in transaction_ids if i]
        elif transaction_id:
            src_ids = [int(transaction_id)]
        source_transactions = Transaction.query.filter(
            Transaction.id.in_(src_ids)
        ).all()
        total_updated = 0
        for trans in source_transactions:
            if trans.description:
                count = current_app.transaction_helper.apply_category_to_similar(
                    trans.description, category_id, exclude_ids=src_ids
                )
                total_updated += count
        return jsonify({"updated": total_updated})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@transactions_bp.route("/categorize/bulk", methods=["POST"])
def bulk_update_category():
    ids = request.form.getlist("transaction_ids") or request.form.get(
        "transaction_ids", ""
    )
    category_id = request.form.get("category_id")
    transaction_ids = []
    if isinstance(ids, str):
        ids = [s.strip() for s in ids.split(",") if s.strip()]
    for tid in ids:
        try:
            transaction_ids.append(int(tid))
        except (ValueError, TypeError):
            continue
    if not transaction_ids:
        flash("No transactions selected", "error")
        return redirect(url_for("transactions.categorize"))
    try:
        count = current_app.transaction_helper.bulk_update_categories(
            transaction_ids, category_id
        )
        if category_id:
            ids_csv = ",".join(str(i) for i in transaction_ids)
            button_html = Markup(
                f"Assigned category to {count} transactions. "
                "<div class='mt-2'>"
                "<button class='btn btn-sm btn-outline-primary apply-same-btn' "
                f"data-transaction-ids='{ids_csv}' "
                f"data-category-id='{category_id}'>"
                "Apply to matching uncategorized transactions</button></div>"
            )
            flash(button_html, "success")
        else:
            flash(f"Updated {count} transactions", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("transactions.categorize"))
