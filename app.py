# -*- coding: utf-8 -*-
"""
تطبيق إدارة قسم الخدمات الاجتماعية للموظفين - نسخة متقدمة
مع تسديد الأقساط + شهادات + بحث في القوائم
"""

from flask import Flask, render_template, request, redirect, url_for, flash, g
import sqlite3
import os
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "social_services_secret_key_2026")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.environ.get("DB_DIR", BASE_DIR)
try:
    test_path = os.path.join(DB_DIR, ".write_test")
    with open(test_path, "w") as f:
        f.write("ok")
    os.remove(test_path)
except Exception:
    DB_DIR = "/tmp"

DATABASE = os.path.join(DB_DIR, "social_services.db")


def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE, check_same_thread=False)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DATABASE, check_same_thread=False)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS Employee (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            Name TEXT NOT NULL,
            Sex TEXT CHECK(Sex IN ('ذكر', 'أنثى')),
            RIP TEXT,
            Name_AR TEXT,
            Department TEXT,
            Phone TEXT,
            Created_At TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS AIDE_TYPE (
            Type_AIDE TEXT PRIMARY KEY,
            Value REAL DEFAULT 0,
            Description TEXT
        );

        CREATE TABLE IF NOT EXISTS Credit (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            Employee_ID INTEGER NOT NULL,
            Type_Credit TEXT NOT NULL,
            Montant REAL NOT NULL,
            N_check TEXT,
            D_check TEXT,
            Months INTEGER DEFAULT 10,
            Monthly_Amount REAL,
            Start_Date TEXT,
            End_Date TEXT,
            Status TEXT DEFAULT 'نشط',
            Is_Paused INTEGER DEFAULT 0,
            Pause_Reason TEXT,
            Pause_Date TEXT,
            Notes TEXT,
            Created_At TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (Employee_ID) REFERENCES Employee(ID) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS Payment (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            Credit_ID INTEGER NOT NULL,
            Amount REAL NOT NULL,
            Payment_Date TEXT NOT NULL,
            Month_Number INTEGER,
            Is_Auto INTEGER DEFAULT 0,
            Notes TEXT,
            Created_At TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (Credit_ID) REFERENCES Credit(ID) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS AIDE (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            Employee_ID INTEGER NOT NULL,
            Type_AIDE TEXT NOT NULL,
            Type_Doc TEXT,
            N_Doc TEXT,
            Date_Doc TEXT,
            Montant REAL,
            Status TEXT DEFAULT 'مقبول',
            Notes TEXT,
            Created_At TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (Employee_ID) REFERENCES Employee(ID) ON DELETE CASCADE,
            FOREIGN KEY (Type_AIDE) REFERENCES AIDE_TYPE(Type_AIDE)
        );

        CREATE TABLE IF NOT EXISTS Settings (
            Key TEXT PRIMARY KEY,
            Value TEXT
        );
    """)

    # ترقية الجداول القديمة إن وُجدت
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(Credit)").fetchall()]
        if "Monthly_Amount" not in cols:
            conn.execute("ALTER TABLE Credit ADD COLUMN Monthly_Amount REAL")
        if "Start_Date" not in cols:
            conn.execute("ALTER TABLE Credit ADD COLUMN Start_Date TEXT")
        if "End_Date" not in cols:
            conn.execute("ALTER TABLE Credit ADD COLUMN End_Date TEXT")
        if "Is_Paused" not in cols:
            conn.execute("ALTER TABLE Credit ADD COLUMN Is_Paused INTEGER DEFAULT 0")
        if "Pause_Reason" not in cols:
            conn.execute("ALTER TABLE Credit ADD COLUMN Pause_Reason TEXT")
        if "Pause_Date" not in cols:
            conn.execute("ALTER TABLE Credit ADD COLUMN Pause_Date TEXT")
    except Exception:
        pass

    types = [
        ("ولادة طفل", 15000, "منحة ولادة"),
        ("ختان طفل", 8000, "منحة ختان"),
        ("زواج الموظف", 25000, "منحة زواج"),
        ("وفاة والد أو والدة", 20000, "منحة وفاة والد/والدة"),
        ("وفاة أحد الأبناء", 20000, "منحة وفاة ابن/ابنة"),
        ("عمرة", 50000, "منحة عمرة"),
        ("حج", 100000, "منحة حج"),
    ]
    for t, v, d in types:
        conn.execute(
            "INSERT OR IGNORE INTO AIDE_TYPE (Type_AIDE, Value, Description) VALUES (?, ?, ?)",
            (t, v, d)
        )

    conn.execute("INSERT OR IGNORE INTO Settings (Key, Value) VALUES ('budget_total', '5000000')")
    conn.execute("INSERT OR IGNORE INTO Settings (Key, Value) VALUES ('budget_year', ?)", (str(datetime.now().year),))
    conn.execute("INSERT OR IGNORE INTO Settings (Key, Value) VALUES ('office_name', 'مكتب الخدمات الاجتماعية')")
    conn.commit()
    conn.close()


try:
    init_db()
except Exception as e:
    print(f"Warning init_db: {e}")


def get_setting(key, default=""):
    db = get_db()
    row = db.execute("SELECT Value FROM Settings WHERE Key=?", (key,)).fetchone()
    return row["Value"] if row else default


def set_setting(key, value):
    db = get_db()
    db.execute("INSERT OR REPLACE INTO Settings (Key, Value) VALUES (?, ?)", (key, str(value)))
    db.commit()


def get_budget_stats():
    db = get_db()
    total_budget = float(get_setting("budget_total", "5000000"))
    spent_aides = db.execute("SELECT COALESCE(SUM(Montant),0) FROM AIDE WHERE Status='مقبول'").fetchone()[0]
    spent_credits = db.execute("SELECT COALESCE(SUM(Montant),0) FROM Credit WHERE Status='نشط'").fetchone()[0]
    total_spent = spent_aides + spent_credits
    remaining = total_budget - total_spent
    return {
        "total": total_budget,
        "spent_aides": spent_aides,
        "spent_credits": spent_credits,
        "total_spent": total_spent,
        "remaining": remaining,
        "percent_used": round((total_spent / total_budget * 100) if total_budget else 0, 1)
    }


def get_credit_remaining(credit_id):
    db = get_db()
    credit = db.execute("SELECT Montant FROM Credit WHERE ID=?", (credit_id,)).fetchone()
    if not credit:
        return 0
    paid = db.execute("SELECT COALESCE(SUM(Amount),0) FROM Payment WHERE Credit_ID=?", (credit_id,)).fetchone()[0]
    return max(0, credit["Montant"] - paid)


def get_credit_paid(credit_id):
    db = get_db()
    return db.execute("SELECT COALESCE(SUM(Amount),0) FROM Payment WHERE Credit_ID=?", (credit_id,)).fetchone()[0]


def generate_auto_payments(credit_id):
    """إنشاء أقساط تلقائية للقرض إذا لم تكن موجودة"""
    db = get_db()
    credit = db.execute("SELECT * FROM Credit WHERE ID=?", (credit_id,)).fetchone()
    if not credit or not credit["Start_Date"] or not credit["Months"]:
        return 0
    existing = db.execute("SELECT COUNT(*) FROM Payment WHERE Credit_ID=?", (credit_id,)).fetchone()[0]
    if existing > 0:
        return 0  # لا تعيد الإنشاء

    monthly = credit["Monthly_Amount"] or (credit["Montant"] / credit["Months"])
    start = datetime.strptime(credit["Start_Date"][:10], "%Y-%m-%d")
    created = 0
    for i in range(1, credit["Months"] + 1):
        pay_date = start + relativedelta(months=i)
        # لا نسجل كمدفوع تلقائياً، فقط كجدول أقساط مستحقة (Amount=0 يعني مستحق غير مدفوع)
        # الأفضل: نسجل الأقساط كمدفوعات فقط عند التسديد الفعلي
        # هنا ننشئ سجلات "مجدولة" بمبلغ القسط
        db.execute("""
            INSERT INTO Payment (Credit_ID, Amount, Payment_Date, Month_Number, Is_Auto, Notes)
            VALUES (?, ?, ?, ?, 1, ?)
        """, (credit_id, 0, pay_date.strftime("%Y-%m-%d"), i, f"قسط رقم {i} - مجدول"))
        created += 1
    db.commit()
    return created


def pay_installment(credit_id, amount, payment_date=None, notes="", month_number=None):
    db = get_db()
    if not payment_date:
        payment_date = datetime.now().strftime("%Y-%m-%d")
    db.execute("""
        INSERT INTO Payment (Credit_ID, Amount, Payment_Date, Month_Number, Is_Auto, Notes)
        VALUES (?, ?, ?, ?, 0, ?)
    """, (credit_id, float(amount), payment_date, month_number, notes))
    # تحديث حالة القرض إذا اكتمل
    remaining = get_credit_remaining(credit_id)
    if remaining <= 0:
        db.execute("UPDATE Credit SET Status='مسدد' WHERE ID=?", (credit_id,))
    db.commit()


# ==================== الرئيسية ====================
@app.route("/")
def index():
    db = get_db()
    try:
        stats = {
            "employees": db.execute("SELECT COUNT(*) FROM Employee").fetchone()[0],
            "credits_active": db.execute("SELECT COUNT(*) FROM Credit WHERE Status='نشط'").fetchone()[0],
            "credits_paused": db.execute("SELECT COUNT(*) FROM Credit WHERE Is_Paused=1").fetchone()[0],
            "aides_accepted": db.execute("SELECT COUNT(*) FROM AIDE WHERE Status='مقبول'").fetchone()[0],
            "total_credit": db.execute("SELECT COALESCE(SUM(Montant),0) FROM Credit WHERE Status='نشط'").fetchone()[0],
            "total_aide": db.execute("SELECT COALESCE(SUM(Montant),0) FROM AIDE WHERE Status='مقبول'").fetchone()[0],
            "total_paid": db.execute("SELECT COALESCE(SUM(Amount),0) FROM Payment WHERE Amount > 0").fetchone()[0],
        }
        aide_by_type = db.execute("""
            SELECT Type_AIDE, COUNT(*) as cnt, COALESCE(SUM(Montant),0) as total
            FROM AIDE WHERE Status='مقبول' GROUP BY Type_AIDE ORDER BY total DESC
        """).fetchall()
    except Exception:
        init_db()
        stats = {k: 0 for k in ["employees","credits_active","credits_paused","aides_accepted","total_credit","total_aide","total_paid"]}
        aide_by_type = []

    budget = get_budget_stats()
    return render_template("index.html", stats=stats, budget=budget, aide_by_type=aide_by_type,
                           office_name=get_setting("office_name"))


# ==================== البحث ====================
@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    results = {"employees": [], "credits": [], "aides": []}
    if q:
        db = get_db()
        like = f"%{q}%"
        results["employees"] = db.execute("""
            SELECT * FROM Employee
            WHERE Name LIKE ? OR Name_AR LIKE ? OR RIP LIKE ? OR Phone LIKE ? OR Department LIKE ? OR CAST(ID AS TEXT) LIKE ?
            ORDER BY ID DESC LIMIT 50
        """, (like, like, like, like, like, like)).fetchall()
        results["credits"] = db.execute("""
            SELECT c.*, e.Name, e.Name_AR FROM Credit c
            JOIN Employee e ON c.Employee_ID = e.ID
            WHERE e.Name LIKE ? OR e.Name_AR LIKE ? OR c.Type_Credit LIKE ? OR c.N_check LIKE ?
               OR CAST(c.ID AS TEXT) LIKE ? OR CAST(e.ID AS TEXT) LIKE ?
            ORDER BY c.ID DESC LIMIT 50
        """, (like, like, like, like, like, like)).fetchall()
        results["aides"] = db.execute("""
            SELECT a.*, e.Name, e.Name_AR FROM AIDE a
            JOIN Employee e ON a.Employee_ID = e.ID
            WHERE e.Name LIKE ? OR e.Name_AR LIKE ? OR a.Type_AIDE LIKE ? OR a.N_Doc LIKE ?
               OR CAST(a.ID AS TEXT) LIKE ? OR CAST(e.ID AS TEXT) LIKE ?
            ORDER BY a.ID DESC LIMIT 50
        """, (like, like, like, like, like, like)).fetchall()
    return render_template("search.html", q=q, results=results)


# ==================== الإعدادات ====================
@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        set_setting("budget_total", request.form.get("budget_total", "0"))
        set_setting("budget_year", request.form.get("budget_year", str(datetime.now().year)))
        set_setting("office_name", request.form.get("office_name", "مكتب الخدمات الاجتماعية"))
        flash("تم حفظ الإعدادات", "success")
        return redirect(url_for("settings"))
    return render_template("settings.html",
                           budget_total=get_setting("budget_total"),
                           budget_year=get_setting("budget_year"),
                           office_name=get_setting("office_name"),
                           budget=get_budget_stats())


# ==================== التقارير ====================
@app.route("/reports")
def reports():
    return render_template("reports.html")


@app.route("/reports/summary")
def report_summary():
    db = get_db()
    budget = get_budget_stats()
    employees_count = db.execute("SELECT COUNT(*) FROM Employee").fetchone()[0]
    credits = db.execute("SELECT Status, COUNT(*) as cnt, COALESCE(SUM(Montant),0) as total FROM Credit GROUP BY Status").fetchall()
    aides = db.execute("SELECT Status, COUNT(*) as cnt, COALESCE(SUM(Montant),0) as total FROM AIDE GROUP BY Status").fetchall()
    aides_by_type = db.execute("""
        SELECT Type_AIDE, COUNT(*) as cnt, COALESCE(SUM(Montant),0) as total
        FROM AIDE WHERE Status='مقبول' GROUP BY Type_AIDE ORDER BY total DESC
    """).fetchall()
    credits_by_type = db.execute("""
        SELECT Type_Credit, COUNT(*) as cnt, COALESCE(SUM(Montant),0) as total FROM Credit GROUP BY Type_Credit
    """).fetchall()
    return render_template("report_summary.html", budget=budget, employees_count=employees_count,
                           credits=credits, aides=aides, aides_by_type=aides_by_type,
                           credits_by_type=credits_by_type, office_name=get_setting("office_name"),
                           now=datetime.now().strftime("%Y-%m-%d %H:%M"))


@app.route("/reports/aides")
def report_aides():
    db = get_db()
    status = request.args.get("status", "")
    type_aide = request.args.get("type", "")
    from_date = request.args.get("from_date", "")
    to_date = request.args.get("to_date", "")
    query = "SELECT a.*, e.Name, e.Name_AR, e.RIP, e.Department FROM AIDE a JOIN Employee e ON a.Employee_ID=e.ID WHERE 1=1"
    params = []
    if status:
        query += " AND a.Status=?"; params.append(status)
    if type_aide:
        query += " AND a.Type_AIDE=?"; params.append(type_aide)
    if from_date:
        query += " AND date(a.Created_At)>=?"; params.append(from_date)
    if to_date:
        query += " AND date(a.Created_At)<=?"; params.append(to_date)
    query += " ORDER BY a.ID DESC"
    rows = db.execute(query, params).fetchall()
    total = sum(r["Montant"] or 0 for r in rows)
    types = db.execute("SELECT Type_AIDE FROM AIDE_TYPE ORDER BY Type_AIDE").fetchall()
    return render_template("report_aides.html", rows=rows, total=total, types=types,
                           status=status, type_aide=type_aide, from_date=from_date, to_date=to_date,
                           office_name=get_setting("office_name"), now=datetime.now().strftime("%Y-%m-%d %H:%M"))


@app.route("/reports/credits")
def report_credits():
    db = get_db()
    status = request.args.get("status", "")
    type_credit = request.args.get("type", "")
    query = "SELECT c.*, e.Name, e.Name_AR, e.RIP, e.Department FROM Credit c JOIN Employee e ON c.Employee_ID=e.ID WHERE 1=1"
    params = []
    if status:
        query += " AND c.Status=?"; params.append(status)
    if type_credit:
        query += " AND c.Type_Credit=?"; params.append(type_credit)
    query += " ORDER BY c.ID DESC"
    rows = db.execute(query, params).fetchall()
    # إضافة المتبقي لكل قرض
    enriched = []
    for r in rows:
        d = dict(r)
        d["paid"] = get_credit_paid(r["ID"])
        d["remaining"] = max(0, (r["Montant"] or 0) - d["paid"])
        enriched.append(d)
    total = sum(r["Montant"] or 0 for r in rows)
    return render_template("report_credits.html", rows=enriched, total=total,
                           status=status, type_credit=type_credit,
                           office_name=get_setting("office_name"), now=datetime.now().strftime("%Y-%m-%d %H:%M"))


@app.route("/reports/employee/<int:id>")
def report_employee(id):
    db = get_db()
    emp = db.execute("SELECT * FROM Employee WHERE ID=?", (id,)).fetchone()
    if not emp:
        flash("الموظف غير موجود", "danger")
        return redirect(url_for("employees"))
    credits = db.execute("SELECT * FROM Credit WHERE Employee_ID=? ORDER BY ID DESC", (id,)).fetchall()
    aides = db.execute("SELECT * FROM AIDE WHERE Employee_ID=? ORDER BY ID DESC", (id,)).fetchall()
    total_credits = sum(c["Montant"] or 0 for c in credits)
    total_aides = sum(a["Montant"] or 0 for a in aides if a["Status"] == "مقبول")
    return render_template("report_employee.html", emp=emp, credits=credits, aides=aides,
                           total_credits=total_credits, total_aides=total_aides,
                           office_name=get_setting("office_name"), now=datetime.now().strftime("%Y-%m-%d %H:%M"))


# ==================== شهادات ====================
@app.route("/credits/<int:id>/certificate")
def credit_certificate(id):
    db = get_db()
    credit = db.execute("""
        SELECT c.*, e.Name, e.Name_AR, e.RIP, e.Sex, e.Department, e.Phone
        FROM Credit c JOIN Employee e ON c.Employee_ID = e.ID WHERE c.ID=?
    """, (id,)).fetchone()
    if not credit:
        flash("القرض غير موجود", "danger")
        return redirect(url_for("credits"))
    paid = get_credit_paid(id)
    remaining = max(0, credit["Montant"] - paid)
    return render_template("certificate_credit.html", c=credit, paid=paid, remaining=remaining,
                           office_name=get_setting("office_name"), now=datetime.now().strftime("%Y-%m-%d"))


@app.route("/aides/<int:id>/certificate")
def aide_certificate(id):
    db = get_db()
    aide = db.execute("""
        SELECT a.*, e.Name, e.Name_AR, e.RIP, e.Sex, e.Department, e.Phone
        FROM AIDE a JOIN Employee e ON a.Employee_ID = e.ID WHERE a.ID=?
    """, (id,)).fetchone()
    if not aide:
        flash("المنحة غير موجودة", "danger")
        return redirect(url_for("aides"))
    return render_template("certificate_aide.html", a=aide,
                           office_name=get_setting("office_name"), now=datetime.now().strftime("%Y-%m-%d"))


# ==================== الموظفين ====================
@app.route("/employees")
def employees():
    db = get_db()
    q = request.args.get("q", "").strip()
    if q:
        like = f"%{q}%"
        rows = db.execute("""
            SELECT * FROM Employee
            WHERE Name LIKE ? OR Name_AR LIKE ? OR RIP LIKE ? OR Phone LIKE ?
               OR Department LIKE ? OR CAST(ID AS TEXT) LIKE ?
            ORDER BY ID DESC
        """, (like, like, like, like, like, like)).fetchall()
    else:
        rows = db.execute("SELECT * FROM Employee ORDER BY ID DESC").fetchall()
    return render_template("employees.html", employees=rows, q=q)


@app.route("/employees/add", methods=["GET", "POST"])
def add_employee():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("الاسم مطلوب", "danger")
            return redirect(url_for("add_employee"))
        db = get_db()
        db.execute("""
            INSERT INTO Employee (Name, Sex, RIP, Name_AR, Department, Phone)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, request.form.get("sex"), request.form.get("rip", "").strip(),
              request.form.get("name_ar", "").strip(), request.form.get("department", "").strip(),
              request.form.get("phone", "").strip()))
        db.commit()
        flash("تم إضافة الموظف", "success")
        return redirect(url_for("employees"))
    return render_template("employee_form.html", employee=None)


@app.route("/employees/edit/<int:id>", methods=["GET", "POST"])
def edit_employee(id):
    db = get_db()
    employee = db.execute("SELECT * FROM Employee WHERE ID=?", (id,)).fetchone()
    if not employee:
        flash("الموظف غير موجود", "danger")
        return redirect(url_for("employees"))
    if request.method == "POST":
        db.execute("""
            UPDATE Employee SET Name=?, Sex=?, RIP=?, Name_AR=?, Department=?, Phone=? WHERE ID=?
        """, (request.form.get("name", "").strip(), request.form.get("sex"),
              request.form.get("rip", "").strip(), request.form.get("name_ar", "").strip(),
              request.form.get("department", "").strip(), request.form.get("phone", "").strip(), id))
        db.commit()
        flash("تم التعديل", "success")
        return redirect(url_for("employees"))
    return render_template("employee_form.html", employee=employee)


@app.route("/employees/delete/<int:id>")
def delete_employee(id):
    db = get_db()
    db.execute("DELETE FROM Employee WHERE ID=?", (id,))
    db.commit()
    flash("تم الحذف", "success")
    return redirect(url_for("employees"))


@app.route("/employees/view/<int:id>")
def view_employee(id):
    db = get_db()
    emp = db.execute("SELECT * FROM Employee WHERE ID=?", (id,)).fetchone()
    if not emp:
        flash("الموظف غير موجود", "danger")
        return redirect(url_for("employees"))
    credits = db.execute("SELECT * FROM Credit WHERE Employee_ID=? ORDER BY ID DESC", (id,)).fetchall()
    aides = db.execute("SELECT * FROM AIDE WHERE Employee_ID=? ORDER BY ID DESC", (id,)).fetchall()
    # إضافة المتبقي للقروض
    credits_data = []
    for c in credits:
        d = dict(c)
        d["paid"] = get_credit_paid(c["ID"])
        d["remaining"] = max(0, (c["Montant"] or 0) - d["paid"])
        credits_data.append(d)
    return render_template("employee_view.html", emp=emp, credits=credits_data, aides=aides)


# ==================== القروض + التسديد ====================
@app.route("/credits")
def credits():
    db = get_db()
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    query = """
        SELECT c.*, e.Name, e.Name_AR FROM Credit c
        JOIN Employee e ON c.Employee_ID = e.ID WHERE 1=1
    """
    params = []
    if q:
        like = f"%{q}%"
        query += " AND (e.Name LIKE ? OR e.Name_AR LIKE ? OR c.Type_Credit LIKE ? OR CAST(c.ID AS TEXT) LIKE ? OR CAST(e.ID AS TEXT) LIKE ?)"
        params.extend([like, like, like, like, like])
    if status:
        query += " AND c.Status=?"; params.append(status)
    query += " ORDER BY c.ID DESC"
    rows = db.execute(query, params).fetchall()
    enriched = []
    total_remaining = 0
    for r in rows:
        d = dict(r)
        d["paid"] = get_credit_paid(r["ID"])
        d["remaining"] = max(0, (r["Montant"] or 0) - d["paid"])
        if r["Status"] == "نشط":
            total_remaining += d["remaining"]
        enriched.append(d)
    return render_template("credits.html", credits=enriched, q=q, status=status, total_remaining=total_remaining)


@app.route("/credits/add", methods=["GET", "POST"])
def add_credit():
    db = get_db()
    employees = db.execute("SELECT ID, Name, Name_AR, RIP FROM Employee ORDER BY ID").fetchall()
    if request.method == "POST":
        emp_id = request.form.get("employee_id")
        type_credit = request.form.get("type_credit")
        montant = float(request.form.get("montant") or 0)
        months = int(request.form.get("months") or 10)
        start_date = request.form.get("start_date") or datetime.now().strftime("%Y-%m-%d")
        if not emp_id or not type_credit or not montant:
            flash("يرجى ملء الحقول المطلوبة", "danger")
            return redirect(url_for("add_credit"))
        monthly = round(montant / months, 2) if months else montant
        try:
            end_date = (datetime.strptime(start_date, "%Y-%m-%d") + relativedelta(months=months)).strftime("%Y-%m-%d")
        except Exception:
            end_date = start_date
        cur = db.execute("""
            INSERT INTO Credit (Employee_ID, Type_Credit, Montant, N_check, D_check, Months,
                                Monthly_Amount, Start_Date, End_Date, Notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (emp_id, type_credit, montant, request.form.get("n_check", "").strip(),
              request.form.get("d_check", "").strip(), months, monthly, start_date, end_date,
              request.form.get("notes", "").strip()))
        credit_id = cur.lastrowid
        db.commit()
        # إنشاء جدول الأقساط المجدولة
        generate_auto_payments(credit_id)
        flash(f"تم تسجيل القرض رقم {credit_id} وإنشاء جدول الأقساط", "success")
        return redirect(url_for("credit_detail", id=credit_id))
    return render_template("credit_form.html", employees=employees, credit=None)


@app.route("/credits/edit/<int:id>", methods=["GET", "POST"])
def edit_credit(id):
    db = get_db()
    credit = db.execute("SELECT * FROM Credit WHERE ID=?", (id,)).fetchone()
    if not credit:
        flash("القرض غير موجود", "danger")
        return redirect(url_for("credits"))
    employees = db.execute("SELECT ID, Name, Name_AR, RIP FROM Employee ORDER BY ID").fetchall()
    if request.method == "POST":
        months = int(request.form.get("months") or 10)
        montant = float(request.form.get("montant") or 0)
        monthly = round(montant / months, 2) if months else montant
        start_date = request.form.get("start_date") or credit["Start_Date"]
        try:
            end_date = (datetime.strptime(start_date[:10], "%Y-%m-%d") + relativedelta(months=months)).strftime("%Y-%m-%d")
        except Exception:
            end_date = credit["End_Date"]
        db.execute("""
            UPDATE Credit SET Employee_ID=?, Type_Credit=?, Montant=?, N_check=?, D_check=?,
                Months=?, Monthly_Amount=?, Start_Date=?, End_Date=?, Status=?, Notes=?
            WHERE ID=?
        """, (request.form.get("employee_id"), request.form.get("type_credit"), montant,
              request.form.get("n_check", "").strip(), request.form.get("d_check", "").strip(),
              months, monthly, start_date, end_date, request.form.get("status"),
              request.form.get("notes", "").strip(), id))
        db.commit()
        flash("تم التعديل", "success")
        return redirect(url_for("credit_detail", id=id))
    return render_template("credit_form.html", employees=employees, credit=credit)


@app.route("/credits/<int:id>")
def credit_detail(id):
    db = get_db()
    credit = db.execute("""
        SELECT c.*, e.Name, e.Name_AR, e.RIP FROM Credit c
        JOIN Employee e ON c.Employee_ID = e.ID WHERE c.ID=?
    """, (id,)).fetchone()
    if not credit:
        flash("القرض غير موجود", "danger")
        return redirect(url_for("credits"))
    payments = db.execute("""
        SELECT * FROM Payment WHERE Credit_ID=? ORDER BY Month_Number, Payment_Date
    """, (id,)).fetchall()
    paid = get_credit_paid(id)
    remaining = max(0, credit["Montant"] - paid)
    return render_template("credit_detail.html", c=credit, payments=payments,
                           paid=paid, remaining=remaining)


@app.route("/credits/<int:id>/pay", methods=["POST"])
def credit_pay(id):
    amount = request.form.get("amount")
    payment_date = request.form.get("payment_date") or datetime.now().strftime("%Y-%m-%d")
    notes = request.form.get("notes", "").strip()
    month_number = request.form.get("month_number") or None
    if not amount:
        flash("أدخل المبلغ", "danger")
        return redirect(url_for("credit_detail", id=id))
    pay_installment(id, amount, payment_date, notes, int(month_number) if month_number else None)
    flash("تم تسجيل الدفعة", "success")
    return redirect(url_for("credit_detail", id=id))


@app.route("/credits/<int:id>/pay-auto")
def credit_pay_auto(id):
    """تسديد القسط المستحق التالي تلقائياً"""
    db = get_db()
    credit = db.execute("SELECT * FROM Credit WHERE ID=?", (id,)).fetchone()
    if not credit:
        flash("القرض غير موجود", "danger")
        return redirect(url_for("credits"))
    if credit["Is_Paused"]:
        flash("القرض موقوف مؤقتاً — لا يمكن التسديد التلقائي", "warning")
        return redirect(url_for("credit_detail", id=id))
    # ابحث عن أول قسط مجدول غير مدفوع (Amount=0)
    scheduled = db.execute("""
        SELECT * FROM Payment WHERE Credit_ID=? AND Amount=0 AND Is_Auto=1
        ORDER BY Month_Number LIMIT 1
    """, (id,)).fetchone()
    monthly = credit["Monthly_Amount"] or (credit["Montant"] / max(credit["Months"], 1))
    if scheduled:
        db.execute("""
            UPDATE Payment SET Amount=?, Payment_Date=?, Notes=?, Is_Auto=1
            WHERE ID=?
        """, (monthly, datetime.now().strftime("%Y-%m-%d"),
              f"تسديد تلقائي - قسط {scheduled['Month_Number']}", scheduled["ID"]))
    else:
        pay_installment(id, monthly, notes="تسديد تلقائي", month_number=None)
    remaining = get_credit_remaining(id)
    if remaining <= 0:
        db.execute("UPDATE Credit SET Status='مسدد' WHERE ID=?", (id,))
    db.commit()
    flash("تم تسديد قسط تلقائياً", "success")
    return redirect(url_for("credit_detail", id=id))


@app.route("/credits/<int:id>/pause", methods=["GET", "POST"])
def credit_pause(id):
    db = get_db()
    credit = db.execute("SELECT * FROM Credit WHERE ID=?", (id,)).fetchone()
    if not credit:
        flash("القرض غير موجود", "danger")
        return redirect(url_for("credits"))
    if request.method == "POST":
        reason = request.form.get("pause_reason", "").strip()
        if not reason:
            flash("يجب كتابة سبب الإيقاف", "danger")
            return redirect(url_for("credit_pause", id=id))
        db.execute("""
            UPDATE Credit SET Is_Paused=1, Pause_Reason=?, Pause_Date=? WHERE ID=?
        """, (reason, datetime.now().strftime("%Y-%m-%d"), id))
        db.commit()
        flash("تم إيقاف التسديد مؤقتاً", "success")
        return redirect(url_for("credit_detail", id=id))
    return render_template("credit_pause.html", c=credit)


@app.route("/credits/<int:id>/resume")
def credit_resume(id):
    db = get_db()
    db.execute("UPDATE Credit SET Is_Paused=0, Pause_Reason=NULL, Pause_Date=NULL WHERE ID=?", (id,))
    db.commit()
    flash("تم استئناف التسديد", "success")
    return redirect(url_for("credit_detail", id=id))


@app.route("/credits/delete/<int:id>")
def delete_credit(id):
    db = get_db()
    db.execute("DELETE FROM Credit WHERE ID=?", (id,))
    db.commit()
    flash("تم الحذف", "success")
    return redirect(url_for("credits"))


@app.route("/payments/<int:id>/delete")
def delete_payment(id):
    db = get_db()
    pay = db.execute("SELECT Credit_ID FROM Payment WHERE ID=?", (id,)).fetchone()
    if pay:
        credit_id = pay["Credit_ID"]
        db.execute("DELETE FROM Payment WHERE ID=?", (id,))
        # إعادة فتح القرض إن كان مسدداً
        remaining = get_credit_remaining(credit_id)
        if remaining > 0:
            db.execute("UPDATE Credit SET Status='نشط' WHERE ID=?", (credit_id,))
        db.commit()
        flash("تم حذف الدفعة", "success")
        return redirect(url_for("credit_detail", id=credit_id))
    return redirect(url_for("credits"))


# ==================== المنح ====================
@app.route("/aides")
def aides():
    db = get_db()
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    type_aide = request.args.get("type", "")
    query = "SELECT a.*, e.Name, e.Name_AR FROM AIDE a JOIN Employee e ON a.Employee_ID=e.ID WHERE 1=1"
    params = []
    if q:
        like = f"%{q}%"
        query += " AND (e.Name LIKE ? OR e.Name_AR LIKE ? OR a.Type_AIDE LIKE ? OR CAST(a.ID AS TEXT) LIKE ? OR CAST(e.ID AS TEXT) LIKE ?)"
        params.extend([like, like, like, like, like])
    if status:
        query += " AND a.Status=?"; params.append(status)
    if type_aide:
        query += " AND a.Type_AIDE=?"; params.append(type_aide)
    query += " ORDER BY a.ID DESC"
    rows = db.execute(query, params).fetchall()
    total = sum(r["Montant"] or 0 for r in rows if r["Status"] == "مقبول")
    types = db.execute("SELECT Type_AIDE FROM AIDE_TYPE ORDER BY Type_AIDE").fetchall()
    return render_template("aides.html", aides=rows, q=q, status=status, type_aide=type_aide, total=total, types=types)


@app.route("/aides/add", methods=["GET", "POST"])
def add_aide():
    db = get_db()
    employees = db.execute("SELECT ID, Name, Name_AR, RIP FROM Employee ORDER BY ID").fetchall()
    aide_types = db.execute("SELECT * FROM AIDE_TYPE ORDER BY Type_AIDE").fetchall()
    if request.method == "POST":
        emp_id = request.form.get("employee_id")
        type_aide = request.form.get("type_aide")
        if not emp_id or not type_aide:
            flash("يرجى ملء الحقول المطلوبة", "danger")
            return redirect(url_for("add_aide"))
        montant = request.form.get("montant")
        if not montant:
            t = db.execute("SELECT Value FROM AIDE_TYPE WHERE Type_AIDE=?", (type_aide,)).fetchone()
            montant = t["Value"] if t else 0
        cur = db.execute("""
            INSERT INTO AIDE (Employee_ID, Type_AIDE, Type_Doc, N_Doc, Date_Doc, Montant, Notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (emp_id, type_aide, request.form.get("type_doc", "").strip(),
              request.form.get("n_doc", "").strip(), request.form.get("date_doc", "").strip(),
              float(montant), request.form.get("notes", "").strip()))
        aide_id = cur.lastrowid
        db.commit()
        flash("تم تسجيل المنحة", "success")
        return redirect(url_for("aide_certificate", id=aide_id))
    return render_template("aide_form.html", employees=employees, aide_types=aide_types, aide=None)


@app.route("/aides/edit/<int:id>", methods=["GET", "POST"])
def edit_aide(id):
    db = get_db()
    aide = db.execute("SELECT * FROM AIDE WHERE ID=?", (id,)).fetchone()
    if not aide:
        flash("المنحة غير موجودة", "danger")
        return redirect(url_for("aides"))
    employees = db.execute("SELECT ID, Name, Name_AR, RIP FROM Employee ORDER BY ID").fetchall()
    aide_types = db.execute("SELECT * FROM AIDE_TYPE ORDER BY Type_AIDE").fetchall()
    if request.method == "POST":
        db.execute("""
            UPDATE AIDE SET Employee_ID=?, Type_AIDE=?, Type_Doc=?, N_Doc=?, Date_Doc=?, Montant=?, Status=?, Notes=?
            WHERE ID=?
        """, (request.form.get("employee_id"), request.form.get("type_aide"),
              request.form.get("type_doc", "").strip(), request.form.get("n_doc", "").strip(),
              request.form.get("date_doc", "").strip(), float(request.form.get("montant") or 0),
              request.form.get("status"), request.form.get("notes", "").strip(), id))
        db.commit()
        flash("تم التعديل", "success")
        return redirect(url_for("aides"))
    return render_template("aide_form.html", employees=employees, aide_types=aide_types, aide=aide)


@app.route("/aides/delete/<int:id>")
def delete_aide(id):
    db = get_db()
    db.execute("DELETE FROM AIDE WHERE ID=?", (id,))
    db.commit()
    flash("تم الحذف", "success")
    return redirect(url_for("aides"))


# ==================== أنواع المنح ====================
@app.route("/aide-types")
def aide_types():
    db = get_db()
    rows = db.execute("SELECT * FROM AIDE_TYPE ORDER BY Type_AIDE").fetchall()
    return render_template("aide_types.html", types=rows)


@app.route("/aide-types/edit/<path:type_aide>", methods=["GET", "POST"])
def edit_aide_type(type_aide):
    db = get_db()
    t = db.execute("SELECT * FROM AIDE_TYPE WHERE Type_AIDE=?", (type_aide,)).fetchone()
    if not t:
        flash("النوع غير موجود", "danger")
        return redirect(url_for("aide_types"))
    if request.method == "POST":
        db.execute("UPDATE AIDE_TYPE SET Value=?, Description=? WHERE Type_AIDE=?",
                   (float(request.form.get("value") or 0), request.form.get("description", "").strip(), type_aide))
        db.commit()
        flash("تم التحديث", "success")
        return redirect(url_for("aide_types"))
    return render_template("aide_type_form.html", t=t)


@app.route("/health")
def health():
    return "OK", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("=" * 50)
    print("  الخدمات الاجتماعية - النسخة المتقدمة")
    print(f"  DB: {DATABASE}")
    print(f"  http://127.0.0.1:{port}")
    print("=" * 50)
    app.run(debug=False, host="0.0.0.0", port=port)
