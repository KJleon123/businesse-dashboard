"""
Business Dashboard — app.py

Application Flask : authentification, lecture des transactions en base MySQL,
calcul des statistiques financières et rendu du tableau de bord.

Lancement en local :
    python app.py

Création d'un utilisateur :
    flask --app app create-user "Awa Koné" awa@exemple.com motdepasse
"""

from datetime import date, datetime
from functools import wraps

import pymysql
import pymysql.cursors
from flask import (
    Flask, flash, g, redirect, render_template,
    request, session, url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config


# ==========================================================================
# 1. Création de l'application
# ==========================================================================

app = Flask(__name__)
app.config.from_object(Config)

for _problem in Config.validate():
    app.logger.warning("Configuration : %s", _problem)

MOIS_COURTS = [
    "janv.", "févr.", "mars", "avr.", "mai", "juin",
    "juil.", "août", "sept.", "oct.", "nov.", "déc.",
]


# ==========================================================================
# 2. Filtres de template
# ==========================================================================

@app.template_filter("fcfa")
def format_fcfa(value):
    """2500000 -> '2 500 000 FCFA' (espaces insécables fines évitées)."""
    try:
        montant = int(round(float(value or 0)))
    except (TypeError, ValueError):
        montant = 0
    return f"{montant:,}".replace(",", " ") + f" {Config.CURRENCY}"


# ==========================================================================
# 3. Base de données
# ==========================================================================
# Vercel exécute l'application en mode serverless : aucune connexion ne peut
# rester ouverte entre deux requêtes. On ouvre donc une connexion par requête
# et on la referme systématiquement à la fin (teardown_appcontext).

def get_db():
    """Renvoie la connexion MySQL de la requête en cours, en la créant au besoin."""
    if "db" not in g:
        g.db = pymysql.connect(
            cursorclass=pymysql.cursors.DictCursor,
            **Config.db_params(),
        )
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        try:
            db.close()
        except Exception:  # noqa: BLE001 — la fermeture ne doit jamais casser la réponse
            pass


def query_all(sql, params=()):
    with get_db().cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def query_one(sql, params=()):
    with get_db().cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone()


def user_scope():
    """
    Restreint les requêtes aux données de l'utilisateur connecté lorsque la
    table transactions possède une colonne user_id (voir Config.SCOPE_BY_USER).
    Renvoie un fragment SQL et ses paramètres.
    """
    if Config.SCOPE_BY_USER and session.get("user_id"):
        return " AND user_id = %s", [session["user_id"]]
    return "", []


# ==========================================================================
# 4. Authentification
# ==========================================================================

def login_required(view):
    """Redirige vers la page de connexion si aucune session n'est ouverte."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Connectez-vous pour accéder au tableau de bord.", "info")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def current_user():
    """Informations d'affichage de l'utilisateur, lues depuis la session."""
    if not session.get("user_id"):
        return None
    return {
        "id": session["user_id"],
        "name": session.get("user_name", "Utilisateur"),
        "email": session.get("user_email", ""),
    }


@app.context_processor
def inject_user():
    """Rend `user` disponible dans tous les templates, y compris base.html."""
    return {"user": current_user()}


# ==========================================================================
# 5. Lecture des données et calculs financiers
# ==========================================================================
# Attention : PyMySQL utilise le caractère % pour ses paramètres. Dans les
# fonctions SQL comme DATE_FORMAT, le % littéral doit donc être doublé (%%Y).

def to_float(value):
    """Convertit les Decimal renvoyés par MySQL en nombres sérialisables en JSON."""
    return float(value) if value is not None else 0.0


def month_range(count):
    """
    Renvoie les `count` derniers mois sous forme de couples (clé, libellé) :
    [('2026-04', 'avr. 26'), ('2026-05', 'mai 26'), …]
    """
    today = date.today()
    months = []
    year, month = today.year, today.month

    for _ in range(count):
        months.append((f"{year:04d}-{month:02d}", f"{MOIS_COURTS[month - 1]} {year % 100:02d}"))
        month -= 1
        if month == 0:
            month, year = 12, year - 1

    return list(reversed(months))


def fetch_totals():
    """Chiffre d'affaires, dépenses, bénéfice et nombre de transactions."""
    scope_sql, params = user_scope()
    row = query_one(
        f"""
        SELECT
            COALESCE(SUM(CASE WHEN type = 'revenu'  THEN montant END), 0) AS revenus,
            COALESCE(SUM(CASE WHEN type = 'depense' THEN montant END), 0) AS depenses,
            COUNT(*) AS nb_transactions
        FROM transactions
        WHERE 1 = 1 {scope_sql}
        """,
        params,
    ) or {}

    revenus = to_float(row.get("revenus"))
    depenses = to_float(row.get("depenses"))

    return {
        "revenus": revenus,
        "depenses": depenses,
        "benefice": revenus - depenses,
        "transactions": int(row.get("nb_transactions") or 0),
    }


def fetch_monthly_series():
    """Séries mensuelles des revenus, des dépenses et du bénéfice."""
    months = month_range(Config.DASHBOARD_MONTHS)
    premier_mois = months[0][0] + "-01"

    scope_sql, params = user_scope()
    rows = query_all(
        f"""
        SELECT
            DATE_FORMAT(date_transaction, '%%Y-%%m') AS periode,
            COALESCE(SUM(CASE WHEN type = 'revenu'  THEN montant END), 0) AS revenus,
            COALESCE(SUM(CASE WHEN type = 'depense' THEN montant END), 0) AS depenses
        FROM transactions
        WHERE date_transaction >= %s {scope_sql}
        GROUP BY periode
        ORDER BY periode
        """,
        [premier_mois] + params,
    )

    par_periode = {row["periode"]: row for row in rows}

    labels, revenus, depenses, benefice = [], [], [], []
    for cle, libelle in months:
        ligne = par_periode.get(cle)
        r = to_float(ligne["revenus"]) if ligne else 0.0
        d = to_float(ligne["depenses"]) if ligne else 0.0

        labels.append(libelle)
        revenus.append(r)
        depenses.append(d)
        benefice.append(r - d)

    return {"mois": labels, "revenus": revenus, "depenses": depenses, "benefice": benefice}


def fetch_categories():
    """Répartition des dépenses par catégorie, des plus lourdes aux plus légères."""
    scope_sql, params = user_scope()
    rows = query_all(
        f"""
        SELECT
            COALESCE(NULLIF(TRIM(categorie), ''), 'Autres') AS categorie,
            SUM(montant) AS total
        FROM transactions
        WHERE type = 'depense' {scope_sql}
        GROUP BY categorie
        ORDER BY total DESC
        LIMIT {Config.MAX_CATEGORIES}
        """,
        params,
    )

    return {
        "labels": [row["categorie"] for row in rows],
        "montants": [to_float(row["total"]) for row in rows],
    }


def fetch_recent_transactions():
    """Dernières transactions affichées dans le tableau."""
    scope_sql, params = user_scope()
    return query_all(
        f"""
        SELECT id, type, description, categorie, montant, date_transaction
        FROM transactions
        WHERE 1 = 1 {scope_sql}
        ORDER BY date_transaction DESC, id DESC
        LIMIT {Config.RECENT_TRANSACTIONS}
        """,
        params,
    )


# ==========================================================================
# 6. Routes
# ==========================================================================

# =========================================================
# DONNÉES FICTIVES — TRANSACTIONS
# =========================================================

DEMO_TRANSACTIONS = [
    {
        "id": 1,
        "type": "revenu",
        "description": "Paiement client",
        "categorie": "Ventes",
        "montant": 750000,
        "date_transaction": "2026-09-05"
    },
    {
        "id": 2,
        "type": "depense",
        "description": "Campagne Facebook Ads",
        "categorie": "Marketing",
        "montant": 150000,
        "date_transaction": "2026-09-04"
    },
    {
        "id": 3,
        "type": "revenu",
        "description": "Prestation web",
        "categorie": "Services",
        "montant": 500000,
        "date_transaction": "2026-09-02"
    },
    {
        "id": 4,
        "type": "depense",
        "description": "Transport",
        "categorie": "Transport",
        "montant": 75000,
        "date_transaction": "2026-09-01"
    }
]

@app.route("/transactions")
@login_required
def transactions():

    filtre = request.args.get("type", "toutes")

    transactions_filtrees = DEMO_TRANSACTIONS

    if filtre in ["revenu", "depense"]:
        transactions_filtrees = [
            transaction
            for transaction in DEMO_TRANSACTIONS
            if transaction["type"] == filtre
        ]

    return render_template(
        "transactions.html",
        transactions=transactions_filtrees,
        filtre=filtre
    )

@app.route("/transactions/add", methods=["GET", "POST"])
@login_required
def add_transaction():

    if request.method == "POST":

        type_transaction = request.form.get("type")
        description = request.form.get("description", "").strip()
        categorie = request.form.get("categorie", "").strip()
        montant = request.form.get("montant")
        date_transaction = request.form.get("date_transaction")

        if not type_transaction or not description or not categorie or not montant or not date_transaction:
            flash("Veuillez remplir tous les champs.", "error")
            return render_template("transaction_form.html")

        try:
            montant = float(montant)
        except ValueError:
            flash("Le montant est invalide.", "error")
            return render_template("transaction_form.html")

        nouveau_id = max(
            [transaction["id"] for transaction in DEMO_TRANSACTIONS],
            default=0
        ) + 1

        nouvelle_transaction = {
            "id": nouveau_id,
            "type": type_transaction,
            "description": description,
            "categorie": categorie,
            "montant": montant,
            "date_transaction": date_transaction
        }

        DEMO_TRANSACTIONS.insert(0, nouvelle_transaction)

        flash("Transaction ajoutée avec succès.", "success")

        return redirect(url_for("transactions"))

    return render_template("transaction_form.html")


@app.route("/transactions/edit/<int:transaction_id>", methods=["GET", "POST"])
@login_required
def edit_transaction(transaction_id):

    transaction = next(
        (
            t for t in DEMO_TRANSACTIONS
            if t["id"] == transaction_id
        ),
        None
    )

    if transaction is None:
        flash("Transaction introuvable.", "error")
        return redirect(url_for("transactions"))

    if request.method == "POST":

        transaction["type"] = request.form.get("type")
        transaction["description"] = request.form.get("description", "").strip()
        transaction["categorie"] = request.form.get("categorie", "").strip()
        transaction["date_transaction"] = request.form.get("date_transaction")

        try:
            transaction["montant"] = float(request.form.get("montant"))
        except (TypeError, ValueError):
            flash("Le montant est invalide.", "error")
            return render_template(
                "transaction_form.html",
                transaction=transaction
            )

        flash("Transaction modifiée avec succès.", "success")

        return redirect(url_for("transactions"))

    return render_template(
        "transaction_form.html",
        transaction=transaction
    )

@app.route("/transactions/delete/<int:transaction_id>")
@login_required
def delete_transaction(transaction_id):

    transaction = next(
        (
            t for t in DEMO_TRANSACTIONS
            if t["id"] == transaction_id
        ),
        None
    )

    if transaction is None:
        flash("Transaction introuvable.", "error")
        return redirect(url_for("transactions"))

    DEMO_TRANSACTIONS.remove(transaction)

    flash("Transaction supprimée avec succès.", "success")

    return redirect(url_for("transactions"))

# =========================================================
# RAPPORTS — DONNÉES FICTIVES
# =========================================================

@app.route("/reports")
@login_required
def reports():

    # Revenus
    revenus = sum(
        t["montant"]
        for t in DEMO_TRANSACTIONS
        if t["type"] == "revenu"
    )

    # Dépenses
    depenses = sum(
        t["montant"]
        for t in DEMO_TRANSACTIONS
        if t["type"] == "depense"
    )

    # Bénéfice
    benefice = revenus - depenses

    # Marge
    marge = round((benefice / revenus) * 100, 1) if revenus > 0 else 0

    # Nombre de transactions
    nombre_transactions = len(DEMO_TRANSACTIONS)

    # Moyenne des revenus
    revenus_liste = [
        t["montant"]
        for t in DEMO_TRANSACTIONS
        if t["type"] == "revenu"
    ]

    revenu_moyen = (
        sum(revenus_liste) / len(revenus_liste)
        if revenus_liste else 0
    )

    # Moyenne des dépenses
    depenses_liste = [
        t["montant"]
        for t in DEMO_TRANSACTIONS
        if t["type"] == "depense"
    ]

    depense_moyenne = (
        sum(depenses_liste) / len(depenses_liste)
        if depenses_liste else 0
    )

    # Répartition des dépenses par catégorie
    categories = {}

    for transaction in DEMO_TRANSACTIONS:

        if transaction["type"] == "depense":

            categorie = transaction["categorie"]

            categories[categorie] = (
                categories.get(categorie, 0)
                + transaction["montant"]
            )

    charts = {
        "mois": [
            "avr. 26",
            "mai 26",
            "juin 26",
            "juil. 26",
            "août 26",
            "sept. 26"
        ],

        "revenus": [
            320000,
            450000,
            380000,
            520000,
            410000,
            370000
        ],

        "depenses": [
            180000,
            210000,
            160000,
            250000,
            190000,
            190000
        ],

        "categories": {
            "labels": list(categories.keys()),
            "montants": list(categories.values())
        }
    }

    stats = {
        "revenus": revenus,
        "depenses": depenses,
        "benefice": benefice,
        "marge": marge,
        "transactions": nombre_transactions,
        "revenu_moyen": revenu_moyen,
        "depense_moyenne": depense_moyenne
    }

    return render_template(
        "reports.html",
        stats=stats,
        charts=charts
    )

@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    if request.method == "GET":
        return render_template("login.html")

    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""

    # Compte fictif pour les tests
    if email == "admin@test.com" and password == "Admin1234":
        session.clear()
        session.permanent = True
        session["user_id"] = 1
        session["user_name"] = "Administrateur"
        session["user_email"] = email

        return redirect(url_for("dashboard"))

    return render_template(
        "login.html",
        email=email,
        error="E-mail ou mot de passe incorrect."
    ), 401


@app.route("/logout")
def logout():
    session.clear()
    flash("Vous êtes déconnecté.", "success")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():

    # Données fictives temporaires pour tester le dashboard
    stats = {
        "revenus": 2450000,
        "depenses": 1180000,
        "benefice": 1270000,
        "transactions": 18
    }

    charts = {
        "mois": [
            "avr. 26",
            "mai 26",
            "juin 26",
            "juil. 26",
            "août 26",
            "sept. 26"
        ],
        "revenus": [
            320000,
            450000,
            380000,
            520000,
            410000,
            370000
        ],
        "depenses": [
            180000,
            210000,
            160000,
            250000,
            190000,
            190000
        ],
        "benefice": [
            140000,
            240000,
            220000,
            270000,
            220000,
            180000
        ],
        "categories": {
            "labels": [
                "Salaires",
                "Marketing",
                "Transport",
                "Fournitures",
                "Autres"
            ],
            "montants": [
                450000,
                280000,
                180000,
                150000,
                120000
            ]
        }
    }

    transactions = [
        {
            "id": 1,
            "type": "revenu",
            "description": "Paiement client",
            "categorie": "Ventes",
            "montant": 750000,
            "date_transaction": "2026-09-05"
        },
        {
            "id": 2,
            "type": "depense",
            "description": "Campagne Facebook Ads",
            "categorie": "Marketing",
            "montant": 150000,
            "date_transaction": "2026-09-04"
        },
        {
            "id": 3,
            "type": "revenu",
            "description": "Prestation web",
            "categorie": "Services",
            "montant": 500000,
            "date_transaction": "2026-09-02"
        },
        {
            "id": 4,
            "type": "depense",
            "description": "Transport",
            "categorie": "Transport",
            "montant": 75000,
            "date_transaction": "2026-09-01"
        }
    ]

    return render_template(
        "dashboard.html",
        stats=stats,
        charts=charts,
        transactions=transactions,
        generated_at=datetime.now().strftime("%d/%m/%Y à %H:%M"),
    )


@app.errorhandler(404)
def page_introuvable(error):
    flash("Cette page n'existe pas.", "info")
    return redirect(url_for("dashboard" if session.get("user_id") else "login")), 302


# ==========================================================================
# 7. Commandes en ligne de commande
# ==========================================================================

@app.cli.command("create-user")
def create_user_command():
    """Crée un utilisateur avec un mot de passe correctement hashé."""
    import click

    name = click.prompt("Nom complet")
    email = click.prompt("Adresse e-mail").strip().lower()
    password = click.prompt("Mot de passe", hide_input=True, confirmation_prompt=True)

    if len(password) < 8:
        click.echo("Le mot de passe doit contenir au moins 8 caractères.")
        return

    hash_mdp = generate_password_hash(password)

    try:
        with get_db().cursor() as cursor:
            cursor.execute(
                "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
                [name, email, hash_mdp],
            )
        click.echo(f"Utilisateur créé : {email}")
    except pymysql.err.IntegrityError:
        click.echo("Cette adresse e-mail est déjà utilisée.")
    except pymysql.MySQLError as erreur:
        click.echo(f"Création impossible : {erreur}")



# =========================================================
# DÉMONSTRATION PUBLIQUE — PORTFOLIO
# =========================================================

@app.route("/demo/business-dashboard")
def demo_business_dashboard():

    stats = {
        "revenus": 2450000,
        "depenses": 1180000,
        "benefice": 1270000,
        "transactions": 18
    }

    charts = {
        "mois": [
            "Avr. 26",
            "Mai 26",
            "Juin 26",
            "Juil. 26",
            "Août 26",
            "Sept. 26"
        ],
        "revenus": [
            320000,
            450000,
            380000,
            520000,
            410000,
            370000
        ],
        "depenses": [
            180000,
            210000,
            160000,
            250000,
            190000,
            190000
        ],
        "benefice": [
            140000,
            240000,
            220000,
            270000,
            220000,
            180000
        ],
        "categories": {
            "labels": [
                "Marketing",
                "Transport",
                "Fournitures",
                "Salaires",
                "Autres"
            ],
            "montants": [
                280000,
                180000,
                150000,
                450000,
                120000
            ]
        }
    }

    return render_template(
        "demo_dashboard.html",
        stats=stats,
        charts=charts
    )

# ==========================================================================
# 8. Point d'entrée local (Vercel importe directement l'objet `app`)
# ==========================================================================

if __name__ == "__main__":
    app.run(debug=Config.DEBUG, port=5000)
