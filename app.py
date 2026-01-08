from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
import os
from openai import OpenAI
from authlib.integrations.flask_client import OAuth
import secrets
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev')


# Configuración de Base de Datos para Render (PostgreSQL) o Local (SQLite)
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///finanzapp.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['GOOGLE_CLIENT_ID'] = os.environ.get('GOOGLE_CLIENT_ID')
app.config['GOOGLE_CLIENT_SECRET'] = os.environ.get('GOOGLE_CLIENT_SECRET')

oauth = OAuth(app)
oauth.register(
    name='google',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False) # Nombre real en lugar de username
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False) 
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    transactions = db.relationship('Transaction', backref='author', lazy=True)

    def __repr__(self):
        return f'<User {self.email}>'

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    type = db.Column(db.String(20), nullable=False)  # 'income' o 'expense'
    category = db.Column(db.String(50), nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    description = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f'<Transaction {self.title} - {self.amount}>'

class Subscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    billing_period = db.Column(db.String(20), nullable=False) # 'mensual', 'anual'
    start_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    next_due_date = db.Column(db.DateTime, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    active = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<Subscription {self.name}>'

def add_months(sourcedate, months):
    import calendar
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year,month)[1])
    return sourcedate.replace(year=year, month=month, day=day)

# Modelo para Metas de Ahorro
class SavingsGoal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    target_amount = db.Column(db.Float, nullable=False)
    current_amount = db.Column(db.Float, default=0.0)
    target_date = db.Column(db.DateTime, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f'<SavingsGoal {self.name}>'

# Modelo para Presupuestos
class Budget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Capitalizar nombre correctamente
        if name:
            name = name.title()

        user = User.query.filter_by(email=email).first()
        if user:
            return jsonify({'success': False, 'message': 'El correo electrónico ya está registrado.'})

        import re
        if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]{2,}$", email):
             return jsonify({'success': False, 'message': 'Por favor, ingresa un correo electrónico válido con un dominio real.'})

        new_user = User(name=name, email=email, password=generate_password_hash(password, method='scrypt'))
        db.session.add(new_user)
        db.session.commit()

        login_user(new_user)
        return jsonify({'success': True, 'redirect': url_for('dashboard')})

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()

        if not user:
            return jsonify({'success': False, 'message': 'El correo electrónico no se encuentra registrado.'})
            
        if not check_password_hash(user.password, password):
            return jsonify({'success': False, 'message': 'La contraseña ingresada no es correcta.'})

        login_user(user)
        return jsonify({'success': True, 'redirect': url_for('dashboard')})

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/login/google')
def google_login():
    redirect_uri = url_for('google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

@app.route('/login/google/callback')
def google_callback():
    try:
        token = oauth.google.authorize_access_token()
        user_info = token.get('userinfo')
        if not user_info:
            user_info = oauth.google.userinfo()
        
        email = user_info.get('email')
        name = user_info.get('name')
        
        if not email:
            flash("No se pudo obtener el correo de Google.", "error")
            return redirect(url_for('login'))

        user = User.query.filter_by(email=email).first()

        if not user:
            # Crear usuario nuevo con contraseña aleatoria segura
            random_pwd = secrets.token_urlsafe(32)
            # Capitalizar nombre si existe
            if name: name = name.title()
            
            user = User(
                name=name or email.split('@')[0], 
                email=email, 
                password=generate_password_hash(random_pwd, method='scrypt')
            )
            db.session.add(user)
            db.session.commit()
        
        login_user(user)
        return redirect(url_for('dashboard'))
    except Exception as e:
        # En producción usar logger
        print(f"Error en Google Login: {e}")
        flash("Ocurrió un error al iniciar sesión con Google. Verifique sus credenciales.", "error")
        return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    # --- PROCESAMIENTO DE SUSCRIPCIONES ---
    today = datetime.now()
    active_subscriptions = Subscription.query.filter_by(user_id=current_user.id, active=True).all()
    
    payments_processed = False
    
    for sub in active_subscriptions:
        if sub.next_due_date <= today:
            new_tx = Transaction(
                title=f"Pago recurrente: {sub.name}",
                amount=sub.amount,
                type='expense',
                category=sub.category,
                date=today,
                user_id=current_user.id
            )
            db.session.add(new_tx)
            
            if sub.billing_period == 'mensual':
                sub.next_due_date = add_months(sub.next_due_date, 1)
            elif sub.billing_period == 'anual':
                sub.next_due_date = add_months(sub.next_due_date, 12)
            
            payments_processed = True
    
    if payments_processed:
        db.session.commit()
    
    # 1. Obtener transacciones del mes actual
    now = datetime.utcnow()
    start_date = datetime(now.year, now.month, 1)
    if now.month == 12:
        end_date = datetime(now.year + 1, 1, 1)
    else:
        end_date = datetime(now.year, now.month + 1, 1)

    transactions = Transaction.query.filter_by(user_id=current_user.id).filter(
        Transaction.date >= start_date,
        Transaction.date < end_date
    ).order_by(Transaction.date.desc()).all()

    # 2. Calcular KPIs básicos
    total_income = sum(t.amount for t in transactions if t.type == 'income')
    total_expense = sum(t.amount for t in transactions if t.type == 'expense')
    balance = total_income - total_expense

    # 3. Datos para el reporte
    savings_rate = 0
    if total_income > 0:
        savings_rate = ((total_income - total_expense) / total_income) * 100
    savings_rate = round(max(savings_rate, 0), 1)

    expenses = [t for t in transactions if t.type == 'expense']
    cat_totals = {}
    for e in expenses:
        cat_totals[e.category] = cat_totals.get(e.category, 0) + e.amount
    
    top_category = "N/A"
    top_cat_percentage = 0
    if cat_totals:
        top_category = max(cat_totals, key=cat_totals.get)
        if total_expense > 0:
            top_cat_percentage = round((cat_totals[top_category] / total_expense) * 100, 1)
    
    days_in_month = (end_date - start_date).days
    daily_balances = {}
    for t in transactions:
        d = t.date.day
        if d not in daily_balances: daily_balances[d] = 0
        if t.type == 'income': daily_balances[d] += t.amount
        else: daily_balances[d] -= t.amount
    
    surplus_days = sum(1 for bal in daily_balances.values() if bal >= 0)

    # 5. Historial Mensual
    from datetime import timedelta
    six_months_ago = start_date - timedelta(days=180) 
    all_transactions = Transaction.query.filter_by(user_id=current_user.id).filter(
        Transaction.date >= six_months_ago
    ).order_by(Transaction.date.desc()).all()

    history_map = {}
    month_names = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

    for t in all_transactions:
        key = f"{t.date.year}-{t.date.month}"
        if key not in history_map:
            history_map[key] = {
                'year': t.date.year,
                'month': t.date.month,
                'name': f"{month_names[t.date.month - 1]} {t.date.year}",
                'total_income': 0,
                'total_expense': 0,
                'balance': 0
            }
        if t.type == 'income':
            history_map[key]['total_income'] += t.amount
        else:
            history_map[key]['total_expense'] += t.amount
        
        history_map[key]['balance'] = history_map[key]['total_income'] - history_map[key]['total_expense']
    
    monthly_history = list(history_map.values())


    transactions_data = [{
        'date': t.date.strftime('%Y-%m-%d'),
        'title': t.title,
        'amount': t.amount,
        'type': t.type,
        'category': t.category
    } for t in all_transactions]

    month_name = month_names[now.month - 1]
    
    # --- PRESUPUESTOS (SMART BUDGETS) ---
    budgets = Budget.query.filter_by(user_id=current_user.id).all()
    budgets_data = []
    
    # Calcular gasto actual vs presupuesto
    # Usamos expenses (transacciones del mes actual de tipo gasto) ya calculados arriba y cat_totals
    for budget in budgets:
        spent = cat_totals.get(budget.category, 0)
        percentage = 0
        if budget.amount > 0:
            percentage = min((spent / budget.amount) * 100, 100)
            
        status_color = "success"
        if percentage >= 100:
            status_color = "danger"
        elif percentage >= 80:
            status_color = "warning"
            
        budgets_data.append({
            'id': budget.id,
            'category': budget.category,
            'amount': budget.amount,
            'spent': spent,
            'remaining': max(budget.amount - spent, 0),
            'percentage': round(percentage, 1),
            'status_color': status_color
        })

    # --- METAS DE AHORRO ---
    savings_goals = SavingsGoal.query.filter_by(user_id=current_user.id).all()
    goals_data = []

    # --- CÁLCULO DE VIABILIDAD (PROMEDIO DE SUPERÁVIT) ---
    avg_monthly_surplus = 0
    if monthly_history:
        total_historic_surplus = sum(m['balance'] for m in monthly_history)
        avg_monthly_surplus = total_historic_surplus / len(monthly_history)
    
    # Fallback si el historial no es suficiente o es negativo, usar el balance actual conservadoramente
    if avg_monthly_surplus <= 100: 
         avg_monthly_surplus = max(balance, 100) # Asumimos al menos 100 de capacidad si el balance actual lo permite

    for goal in savings_goals:
        # Calcular progreso
        progress_percentage = 0
        if goal.target_amount > 0:
            progress_percentage = min((goal.current_amount / goal.target_amount) * 100, 100)
        
        # Estado de fechas
        is_due_today = goal.target_date.date() == today.date()
        is_past_due = goal.target_date.date() < today.date()
        days_remaining = (goal.target_date.date() - today.date()).days
        
        # Calcular ahorro mensual sugerido (Smart Pacing)
        monthly_saving_suggested = 0
        weekly_saving_suggested = 0
        daily_saving_suggested = 0
        amount_remaining = max(goal.target_amount - goal.current_amount, 0)

        # 1. Feature Smart Pacing
        if not is_past_due and not is_due_today and amount_remaining > 0:
             # Diferencia en meses aprox
             diff_months = (goal.target_date.year - today.year) * 12 + (goal.target_date.month - today.month)
             if diff_months < 1: diff_months = 1
             
             monthly_saving_suggested = amount_remaining / diff_months
             
             if days_remaining > 0:
                daily_saving_suggested = amount_remaining / days_remaining
                weekly_saving_suggested = daily_saving_suggested * 7
        
        # 2. Feature Viabilidad (Reality Check)
        feasibility = "viable" # viable, hard, imposible
        feasibility_color = "success"
        feasibility_msg = "Meta saludable"

        if amount_remaining > 0 and monthly_saving_suggested > 0:
            ratio = monthly_saving_suggested / avg_monthly_surplus if avg_monthly_surplus > 0 else 999
            
            if ratio > 1.2:
                feasibility = "retadora"
                feasibility_color = "danger"
                feasibility_msg = f"Requiere un esfuerzo extra de ${monthly_saving_suggested:,.0f}/mes. Considera extender el plazo."
            elif ratio > 0.8:
                feasibility = "ajustada"
                feasibility_color = "warning"
                feasibility_msg = f"Requiere disciplina. Usarás el {ratio*100:.0f}% de tu flujo libre."
            else:
                feasibility = "viable"
                feasibility_color = "success"
                feasibility_msg = "Tu flujo de caja actual soporta esta meta cómodamente."

        goals_data.append({
            'id': goal.id,
            'name': goal.name,
            'target_amount': goal.target_amount,
            'current_amount': goal.current_amount,
            'target_date': goal.target_date.strftime('%d/%m/%Y'),
            'progress': round(progress_percentage, 1),
            'monthly_contribution': round(monthly_saving_suggested, 2),
            'weekly_contribution': round(weekly_saving_suggested, 2),
            'daily_contribution': round(daily_saving_suggested, 2),
            'remaining_amount': amount_remaining,
            'is_due_today': is_due_today,
            'is_past_due': is_past_due,
            'days_remaining': days_remaining,
            'feasibility': feasibility,
            'feasibility_color': feasibility_color,
            'feasibility_msg': feasibility_msg
        })

    # --- DATOS PARA INSIGHTS (Asistente IA) ---
    subscriptions_total = sum(sub.amount for sub in active_subscriptions)

    goals_global_progress = 0
    if goals_data:
        total_p = sum(g['progress'] for g in goals_data)
        goals_global_progress = total_p / len(goals_data)

    return render_template('dashboard.html', 
                           name=current_user.name,
                           balance="{:,.2f}".format(balance),
                           total_income="{:,.2f}".format(total_income),
                           total_expense="{:,.2f}".format(total_expense),
                           current_month_income=total_income,
                           current_month_expenses=total_expense,
                           current_day=now.day,
                           days_in_month=days_in_month,
                           transactions=transactions, 
                           transactions_data=transactions_data,
                           report_month=f"{month_name} {now.year}",
                           savings_rate=savings_rate,
                           top_category=top_category,
                           top_cat_percentage=top_cat_percentage,
                           surplus_days=surplus_days,
                           total_days_month=days_in_month if days_in_month else 30,
                           monthly_history=monthly_history,
                           subscriptions=active_subscriptions,
                           subscriptions_total=subscriptions_total,
                           savings_goals=goals_data,
                           goals_global_progress=goals_global_progress,
                           budgets=budgets_data
                           )

@app.route('/download_report')
@login_required
def download_report():
    from xhtml2pdf import pisa
    from io import BytesIO
    import os

    try:
        req_month = int(request.args.get('month', datetime.now().month))
        req_year = int(request.args.get('year', datetime.now().year))
    except ValueError:
        req_month = datetime.now().month
        req_year = datetime.now().year

    # Filtrar transacciones del periodo solicitado
    transactions = Transaction.query.filter_by(user_id=current_user.id).filter(
        db.extract('month', Transaction.date) == req_month,
        db.extract('year', Transaction.date) == req_year
    ).order_by(Transaction.date.desc()).all()

    incomes = [t for t in transactions if t.type == 'income']
    expenses = [t for t in transactions if t.type == 'expense']

    total_income = sum(t.amount for t in incomes)
    total_expense = sum(t.amount for t in expenses)
    balance = total_income - total_expense

    month_names = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    month_name = month_names[req_month - 1]
    
    # Calcular último día del mes
    if req_month == 2:
        last_day = 29 if (req_year % 4 == 0 and req_year % 100 != 0) or (req_year % 400 == 0) else 28
    elif req_month in [4, 6, 9, 11]:
        last_day = 30
    else:
        last_day = 31
        
    period_name = f"Del 01 al {last_day} de {month_name.lower()} {req_year}"

    base_dir = os.path.abspath(os.path.dirname(__file__))
    logo_path = os.path.join(base_dir, 'static', 'multimedia', 'logo.png')
    
    # Colores de marca
    brand_color = "#1e3a8a" 
    text_main = "#1e293b"
    text_muted = "#64748b"

    html = f"""
    <html>
    <head>
        <style>
            @page {{ size: letter; margin: 1.5cm; }}
            body {{ font-family: 'Helvetica', sans-serif; color: {text_main}; line-height: 1.5; font-size: 12px; }}
            
            /* Header */
            .header {{ margin-bottom: 40px; border-bottom: 2px solid #f1f5f9; padding-bottom: 20px; }}
            .logo-img {{ width: 50px; height: auto; display: block; }}
            .user-details {{ text-align: right; font-size: 10px; color: {text_muted}; vertical-align: middle; }}
            .user-details strong {{ font-weight: bold; color: {text_main}; font-size: 11px; }}

            /* Títulos */
            .report-title {{ color: {brand_color}; font-size: 22px; font-weight: bold; margin-bottom: 5px; }}
            .report-subtitle {{ color: {text_muted}; font-size: 14px; margin-bottom: 30px; }}
            
            .section-header {{ margin-bottom: 15px; margin-top: 30px; border-bottom: 1px solid #e2e8f0; padding-bottom: 5px; }}
            .section-title {{ font-size: 14px; font-weight: bold; color: {brand_color}; text-transform: uppercase; letter-spacing: 0.5px; }}

            /* Resumen Tabla */
            .summary-table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
            .summary-row td {{ padding: 10px 0; border-bottom: 1px dashed #e2e8f0; }}
            .summary-label {{ font-size: 12px; color: {text_main}; }}
            .summary-value {{ font-size: 12px; font-weight: bold; text-align: right; }}
            
            /* Balance Row Fix: Completely Separate Style */
            .balance-container {{
                background-color: #f8fafc;
                border-top: 2px solid {text_main};
                border-bottom: 2px solid {text_main};
                padding: 20px 10px;
                margin-top: 20px;
            }}
            
            .balance-table {{ width: 100%; }}
            .balance-label {{ font-weight: bold; font-size: 14px; color: {brand_color}; }}
            .balance-value {{ font-weight: bold; font-size: 14px; color: {brand_color}; text-align: right; }}

            /* Detalle Movimientos */
            .movements-table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
            .movements-header th {{ 
                text-align: left; 
                font-size: 9px; 
                color: {text_muted}; 
                padding: 8px 5px; 
                border-bottom: 1px solid #cbd5e1; 
                background-color: #f1f5f9;
                text-transform: uppercase; 
            }}
            .movements-row td {{ padding: 10px 5px; border-bottom: 1px solid #f1f5f9; font-size: 11px; }}
            .badge-cat {{ background-color: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-size: 9px; color: {text_muted}; }}
            .footer {{ position: fixed; bottom: 0; width: 100%; text-align: center; font-size: 8px; color: #cbd5e1; border-top: 1px solid #f1f5f9; padding-top: 10px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <table style="width: 100%;">
                <tr>
                    <td style="vertical-align: middle;"><img src="{logo_path}" class="logo-img" /></td>
                    <td class="user-details">
                        Reporte generado para:<br/>
                        <strong>{current_user.name}</strong><br/>
                        <span style="font-size: 9px;">{period_name}</span>
                    </td>
                </tr>
            </table>
        </div>

        <div class="report-title">Estado financiero mensual</div>
        <div class="report-subtitle">Resumen de tu actividad en {month_name.lower()}</div>

        <div class="section-header">
            <span class="section-title">Resumen general</span>
        </div>

        <table class="summary-table">
            <tr class="summary-row">
                <td class="summary-label">Ingresos totales</td>
                <td class="summary-value" style="color: #10b981;">+${"{:,.2f}".format(total_income)}</td>
            </tr>
            <tr class="summary-row">
                <td class="summary-label">Gastos totales</td>
                <td class="summary-value" style="color: #ef4444;">-${"{:,.2f}".format(total_expense)}</td>
            </tr>
            <tr class="summary-row">
                <td class="summary-label">Resultado neto</td>
                <td class="summary-value" style="color: {text_muted};">${"{:,.2f}".format(max(total_income - total_expense, 0))}</td>
            </tr>
        </table>
        
        <!-- Bloque independiente para el balance para evitar overlap -->
        <div class="balance-container">
            <table class="balance-table">
                <tr>
                    <td class="balance-label">Balance global</td>
                    <td class="balance-value">${"{:,.2f}".format(balance)}</td>
                </tr>
            </table>
        </div>

        <div class="section-header">
            <span class="section-title">Detalle de operaciones</span>
        </div>
        
        <table class="movements-table">
            <tr class="movements-header">
                <th style="width: 15%;">Fecha</th>
                <th style="width: 45%;">Concepto</th>
                <th style="width: 25%;">Categoría</th>
                <th style="width: 15%; text-align: right;">Monto</th>
            </tr>
    """
    
    for t in transactions:
        amount_style = ""
        sign = "-"
        if t.type == 'income':
            sign = "+"
            amount_style = "color: #10b981;"
        else:
            amount_style = "color: #ef4444;"
        
        html += f"""
        <tr class="movements-row">
            <td style="color: #64748b;">{t.date.strftime('%d/%m')}</td>
            <td><strong>{t.title}</strong></td>
            <td><span class="badge-cat">{t.category}</span></td>
            <td style="text-align: right; {amount_style}">{sign}${"{:,.2f}".format(t.amount)}</td>
        </tr>
        """
        
    html += f"""
        </table>
        
        <div class="footer">
            FinanzApp &bull; Tu asistente financiero personal &bull; {datetime.now().year}
        </div>
    </body>
    </html>
    """
    
    buffer = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=buffer)
    
    if pisa_status.err:
        return "Error al generar PDF"
        
    buffer.seek(0)
    
    from flask import send_file
    filename = f'Reporte_FinanzApp_{month_name}_{req_year}.pdf'
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')

@app.route('/delete_transaction/<int:id>', methods=['POST'])
@login_required
def delete_transaction(id):
    transaction = Transaction.query.get_or_404(id)
    if transaction.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    
    db.session.delete(transaction)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/get_transaction/<int:id>')
@login_required
def get_transaction(id):
    transaction = Transaction.query.get_or_404(id)
    if transaction.user_id != current_user.id:
        return jsonify({'success': False}), 403
    
    return jsonify({
        'success': True,
        'id': transaction.id,
        'title': transaction.title,
        'amount': transaction.amount,
        'type': transaction.type,
        'category': transaction.category,
        'date': transaction.date.strftime('%Y-%m-%d')
    })

@app.route('/edit_transaction/<int:id>', methods=['POST'])
@login_required
def edit_transaction(id):
    transaction = Transaction.query.get_or_404(id)
    if transaction.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    
    transaction.title = request.form.get('title')
    transaction.amount = float(request.form.get('amount'))
    transaction.type = request.form.get('type')
    transaction.category = request.form.get('category')
    
    # Manejar fecha si se envía (asumimos formato YYYY-MM-DD del input date)
    date_str = request.form.get('date')
    if date_str:
        transaction.date = datetime.strptime(date_str, '%Y-%m-%d')
    
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/movements', methods=['GET', 'POST'])
@login_required
def movements():
    if request.method == 'POST':
        title = request.form.get('title')
        amount = float(request.form.get('amount'))
        type = request.form.get('type')
        category = request.form.get('category')

        date_str = request.form.get('date')
        if date_str:
            date = datetime.strptime(date_str, '%Y-%m-%d')
        else:
            date = datetime.utcnow()

        new_transaction = Transaction(
            title=title,
            amount=amount,
            type=type,
            category=category,
            user_id=current_user.id,
            date=date
        )
        db.session.add(new_transaction)
        db.session.commit()
        return redirect(url_for('dashboard'))

    return redirect(url_for('dashboard'))

@app.route('/update_password', methods=['POST'])
@login_required
def update_password():
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    if not current_password or not new_password or not confirm_password:
        flash('Todos los campos son obligatorios.', 'error')
        return redirect(url_for('dashboard'))

    if not check_password_hash(current_user.password, current_password):
        flash('La contraseña actual es incorrecta.', 'error')
        return redirect(url_for('dashboard'))

    if new_password != confirm_password:
        flash('Las contraseñas nuevas no coinciden.', 'error')
        return redirect(url_for('dashboard'))

    current_user.password = generate_password_hash(new_password)
    db.session.commit()
    flash('Contraseña actualizada correctamente.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/add_subscription', methods=['POST'])
@login_required
def add_subscription():
    name = request.form.get('name')
    amount = float(request.form.get('amount'))
    category = request.form.get('category')
    billing_period = request.form.get('billing_period')
    start_date_str = request.form.get('start_date')
    
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
    except ValueError:
        flash('Fecha inválida', 'error')
        return redirect(url_for('dashboard'))
        
    # La próxima fecha de cobro inicial es... ¿la fecha de inicio?
    # Asumimos que si pone fecha futura, es esa. Si pone fecha pasada, el sistema
    # cobrará lo pendiente al entrar al dashboard.
    
    new_sub = Subscription(
        name=name,
        amount=amount,
        category=category,
        billing_period=billing_period,
        start_date=start_date,
        next_due_date=start_date, # El primer cobro es en la fecha de inicio
        user_id=current_user.id
    )
    
    db.session.add(new_sub)
    db.session.commit()
    flash('Suscripción agregada correctamente.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/delete_subscription/<int:id>', methods=['POST'])
@login_required
def delete_subscription(id):
    sub = Subscription.query.get_or_404(id)
    if sub.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    
    db.session.delete(sub)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/add_savings_goal', methods=['POST'])
@login_required
def add_savings_goal():
    name = request.form.get('name')
    target_amount = float(request.form.get('target_amount'))
    initial_amount = float(request.form.get('initial_amount') or 0.0)
    target_date_str = request.form.get('target_date')
    
    try:
        target_date = datetime.strptime(target_date_str, '%Y-%m-%d')
        if target_date.date() < datetime.now().date():
            flash('La fecha objetivo no puede estar en el pasado.', 'error')
            return redirect(url_for('dashboard'))
    except ValueError:
        flash('Fecha inválida', 'error')
        return redirect(url_for('dashboard'))
        
    new_goal = SavingsGoal(
        name=name,
        target_amount=target_amount,
        current_amount=initial_amount,
        target_date=target_date,
        user_id=current_user.id
    )
    
    db.session.add(new_goal)
    db.session.commit()
    flash('Meta de ahorro creada correctamente.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/delete_savings_goal/<int:id>', methods=['POST'])
@login_required
def delete_savings_goal(id):
    goal = SavingsGoal.query.get_or_404(id)
    if goal.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    
    db.session.delete(goal)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/extend_savings_goal/<int:id>', methods=['POST'])
@login_required
def extend_savings_goal(id):
    goal = SavingsGoal.query.get_or_404(id)
    if goal.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    
    # Extender 30 días
    from datetime import timedelta
    goal.target_date += timedelta(days=30)
    db.session.commit()
    
    return jsonify({'success': True, 'new_date': goal.target_date.strftime('%d/%m/%Y')})

@app.route('/add_funds_to_goal/<int:id>', methods=['POST'])
@login_required
def add_funds_to_goal(id):
    goal = SavingsGoal.query.get_or_404(id)
    if goal.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
        
    amount = float(request.form.get('amount') or 0)
    
    if amount <= 0:
        return jsonify({'success': False, 'message': 'Monto inválido'}), 400
        
    goal.current_amount += amount
    db.session.commit()
    
    return jsonify({'success': True})

# --- RUTAS DE PRESUPUESTO (SMART BUDGETS) ---

@app.route('/add_budget', methods=['POST'])
@login_required
def add_budget():
    category = request.form.get('category')
    amount = float(request.form.get('amount'))
    
    # Check if budget for category already exists
    existing = Budget.query.filter_by(user_id=current_user.id, category=category).first()
    if existing:
        existing.amount = amount # Update instead of fail
        flash(f'Presupuesto para {category} actualizado.', 'success')
    else:
        new_budget = Budget(category=category, amount=amount, user_id=current_user.id)
        db.session.add(new_budget)
        flash('Presupuesto creado correctamente.', 'success')
        
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/delete_budget/<int:id>', methods=['POST'])
@login_required
def delete_budget(id):
    budget = Budget.query.get_or_404(id)
    if budget.user_id != current_user.id:
        return jsonify({'success': False}), 403
    
    db.session.delete(budget)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/edit_budget/<int:id>', methods=['POST'])
@login_required
def edit_budget(id):
    budget = Budget.query.get_or_404(id)
    if budget.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    
    amount = float(request.form.get('amount'))
    budget.amount = amount
    db.session.commit()
    
    flash(f'Presupuesto de {budget.category} actualizado.', 'success')
    return redirect(url_for('dashboard'))


# --- RUTA API AURELIUS (IA) ---
@app.route('/api/ask_aurelius', methods=['POST'])
@login_required
def ask_aurelius():
    data = request.json
    user_message = data.get('message', '')
    
    # 1. Recopilar Contexto Financiero del Usuario
    now = datetime.utcnow()
    start_date = datetime(now.year, now.month, 1)
    if now.month == 12:
        end_date = datetime(now.year + 1, 1, 1)
    else:
        end_date = datetime(now.year, now.month + 1, 1)

    transactions = Transaction.query.filter_by(user_id=current_user.id).filter(
        Transaction.date >= start_date,
        Transaction.date < end_date
    ).all()

    total_income = sum(t.amount for t in transactions if t.type == 'income')
    total_expense = sum(t.amount for t in transactions if t.type == 'expense')
    balance = float(str(total_income)) - float(str(total_expense)) # Safe float conversion
    
    expenses_by_cat = {}
    for t in transactions:
        if t.type == 'expense':
            expenses_by_cat[t.category] = expenses_by_cat.get(t.category, 0) + t.amount

    top_cat = max(expenses_by_cat, key=expenses_by_cat.get) if expenses_by_cat else "Ninguna"
    
    savings_goals = SavingsGoal.query.filter_by(user_id=current_user.id).all()
    goals_context = ", ".join([f"{g.name}: ${g.current_amount}/${g.target_amount}" for g in savings_goals])
    
    # 2. Configurar Cliente OpenAI (usando Groq - Gratis y Rápido)
    api_key = os.environ.get('GROQ_API_KEY')
    
    if not api_key:
         # Fallback si no hay clave
        return jsonify({
            'response': f"Hola {current_user.name}. He cambiado mi cerebro a <strong>Groq (Llama 3)</strong> para ser más rápido y gratuito.<br>Por favor configura tu <a href='https://console.groq.com/keys' target='_blank'>API Key de Groq</a> en el código para activarme."
        })

    client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")

    # 3. ADVANCED RAG (Search + LLM) - TAVILY IMPLEMENTATION
    search_context = ""

    # Configura aquí tu API Key de Tavily
    tavily_api_key = os.environ.get('TAVILY_API_KEY')  # REEMPLAZAR CON TU API KEY REAL
    
    if len(user_message) > 4:
        try:
            # Check for API key validity
            if not tavily_api_key:
                print("TAVILY WARNING: No API Key configured.")
                search_context = "AVISO: El usuario no ha configurado su Tavily API Key. Responde lo mejor que puedas con tu conocimiento base."
            else:
                 from tavily import TavilyClient
                 tavily = TavilyClient(api_key=tavily_api_key)
                 
                 # Optimizar query con LLM primero
                 query_gen_prompt = [
                    {"role": "system", "content": "You are a Search Query Generator. Output ONLY the best search query (keywords) for the user's question, focusing on finances in Mexico. Add 'Mexico' and 'actual' if relevant. NO explanations."},
                    {"role": "user", "content": f"Question: {user_message}"}
                 ]
                 
                 q_response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=query_gen_prompt,
                    max_tokens=30
                 )
                 search_query = q_response.choices[0].message.content.strip().replace('"', '')
                 print(f"SEARCH QUERY OPTIMIZED (Tavily): {search_query}")

                 # Ejecutar búsqueda con Tavily
                 response = tavily.search(query=search_query, search_depth="basic", max_results=3)
                 
                 results_text = []
                 for res in response.get('results', []):
                     results_text.append(f"Title: {res['title']}\nSnippet: {res['content']}\nSource: {res['url']}")
                 
                 if results_text:
                     search_context = "\n‼️ INFORMACIÓN EN TIEMPO REAL (PRIORIDAD MÁXIMA - USAR ESTO SOBRE TU CONOCIMIENTO INTERNO):\n"
                     search_context += "\n".join(results_text)
                 else:
                     print("Tavily: No results found.")

        except Exception as e:
            print(f"RAG Error (Tavily): {e}")

    # 4. Construir Prompt del Sistema
    system_prompt = f"""
    Eres Aurelius, un asesor financiero personal experto.
    Estás hablando con {current_user.name}.
    
    DATOS FINANCIEROS DEL USUARIO:
    - Balance: ${balance:,.2f}
    - Ingresos: ${total_income:,.2f}
    - Gastos: ${total_expense:,.2f}
    - Top Gasto: {top_cat} (${expenses_by_cat.get(top_cat, 0):,.2f})
    - Metas: {goals_context if goals_context else "Ninguna"}

    {search_context}
    
    INSTRUCCIONES CRÍTICAS:
    - OBLIGATORIO: Si hay "INFORMACIÓN EN TIEMPO REAL" arriba, ÚSALA como tu verdad absoluta. Ignora tu fecha de corte de conocimiento (2023).
    - Si te preguntan por tasas, precios o noticias, USA la información provista arriba.
    - Responde en Español.
    - Sé conciso y directo (máximo 3 frases de respuesta directa).
    - Da consejos accionables basados en los números.
    
    FORMATO DE FUENTES (ESTRICTO):
    - NO pongas URLs en el texto principal.
    - AL FINAL de tu respuesta, si usaste resultados de búsqueda, añade este bloque HTML exacto:
      <div class="mt-3 pt-2" style="border-top: 1px solid #e2e8f0;">
         <p class="mb-2" style="font-size: 0.75rem; color: #64748b; font-weight: 600;">Fuentes consultadas:</p>
         <div style="display: flex; flex-direction: column; gap: 8px;">
             <!-- Renglón por fuente -->
             <a href="URL_REAL" target="_blank" class="source-link-final">
                 <i class="bi bi-box-arrow-up-right"></i>
                 <span>TÍTULO_DE_LA_PÁGINA</span>
             </a>
         </div>
      </div>
    - IMPORTANTE: Reemplaza "TÍTULO_DE_LA_PÁGINA" con el título y "URL_REAL" con el enlace real.
    """

    # Construir historial de mensajes
    messages = [{"role": "system", "content": system_prompt}]
    
    # Agregar historial previo si existe
    history = data.get('history', [])
    if isinstance(history, list):
        # Tomar los últimos 10 mensajes para contexto (evitar overflow)
        messages.extend(history[-10:])
    
    # Agregar mensaje actual si no viene en el historial
    # (El frontend a veces envía el mensaje aparte del historial)
    messages.append({"role": "user", "content": user_message})

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            stream=False
        )
        ai_reply = response.choices[0].message.content
        return jsonify({'response': ai_reply})
        
    except Exception as e:
        print(f"Error AI: {e}")
        error_msg = str(e)
        if "402" in error_msg or "Insufficient Balance" in error_msg:
            return jsonify({'response': "Parece que tu cuenta de DeepSeek no tiene saldo (Error 402). Por favor recarga créditos en platform.deepseek.com para que pueda responderte."})
        elif "401" in error_msg:
             return jsonify({'response': "Error de autenticación (401). Verifica que tu API Key sea correcta."})
             
        return jsonify({'response': "Lo siento, tuve un problema conectando con mi red neuronal. Por favor verifica tu conexión o tu API Key."})


# --- RUTA CHATBOT SOPORTE (LANDING PAGE) ---
@app.route('/api/ask_support', methods=['POST'])
def ask_support():
    data = request.json
    user_message = data.get('message', '')
    
    # Contexto de la aplicación (Knowledge Base básico)
    app_context = """
    INFORMACIÓN SOBRE FINANZAPP:
    - Qué es: Una plataforma web para gestionar finanzas personales y empresariales.
    - Costo: Completamente GRATIS actualmente.
    - Funciones: Registro de ingresos/gastos, presupuestos mensuales, metas de ahorro, reportes PDF/Excel, dashboard con gráficos.
    - Inteligencia Artificial: Cuenta con "Aurelius", un asesor financiero IA disponible en el dashboard.
    - Privacidad: No conectamos con bancos. El registro es manual para mayor seguridad. Datos encriptados.
    - Soporte: Correo de contacto soporte@finanzapp.com.
    - Registro: Se requiere nombre, correo y contraseña.
    """
    
    system_prompt = f"""
    Eres Aurelius, el Asistente Inteligente de FinanzApp.
    NO eres un asesor financiero personal en este chat, eres un guía sobre la plataforma.
    
    {app_context}
    
    Reglas:
    1. Eres amable, profesional, inteligente y conciso.
    2. Tu objetivo es convencer al usuario de registrarse resolviendo sus dudas.
    3. Si preguntan algo técnico o financiero complejo, diles que "en el Dashboard" podrás analizar sus datos reales.
    4. Responde siempre en español.
    """
    
    try:
        # Usamos la misma configuración de Groq
        # NOTA: En producción, usar variables de entorno
        api_key = os.environ.get('GROQ_API_KEY')
        
        # Import OpenAI here just in case it wasn't imported globally or to ensure scope
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.6,
            max_tokens=300
        )
        response_text = completion.choices[0].message.content
        
        # Formato HTML
        response_text = response_text.replace("\n", "<br>").replace("**", "<b>").replace("**", "</b>")
        
        return jsonify({'response': response_text})

    except Exception as e:
        print(f"Error Support Bot: {e}")
        return jsonify({'response': "Hola, estoy teniendo problemas de conexión. Por favor escríbenos a soporte@finanzapp.com"})


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
