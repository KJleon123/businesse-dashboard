"""
Business Dashboard — config.py

Centralise toute la configuration de l'application.
Aucune valeur sensible n'est écrite ici : tout provient des variables
d'environnement, chargées depuis le fichier .env en développement et
définies directement dans le tableau de bord Vercel en production.
"""

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# En local, .env alimente os.environ. Sur Vercel le fichier n'existe pas :
# load_dotenv ne fait alors rien et les variables de la plateforme sont utilisées.
load_dotenv(BASE_DIR / ".env")


def env(key, default=None):
    """Lit une variable d'environnement en ignorant les valeurs vides."""
    value = os.getenv(key)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def env_bool(key, default=False):
    """Lit un booléen écrit sous forme de texte (true/1/yes/on)."""
    value = env(key)
    if value is None:
        return default
    return value.lower() in ("1", "true", "yes", "on")


def env_int(key, default):
    try:
        return int(env(key, default))
    except (TypeError, ValueError):
        return default


class Config:
    """Configuration unique de l'application."""

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    DEBUG = env_bool("FLASK_DEBUG", False)

    # En développement une clé de repli évite de bloquer le démarrage.
    # En production, l'absence de SECRET_KEY lève une erreur (voir validate).
    SECRET_KEY = env("SECRET_KEY", "dev-only-change-me")

    # ------------------------------------------------------------------
    # Session et cookies
    # ------------------------------------------------------------------
    SESSION_COOKIE_HTTPONLY = True          # cookie inaccessible au JavaScript
    SESSION_COOKIE_SAMESITE = "Lax"         # limite les requêtes inter-sites
    SESSION_COOKIE_SECURE = not DEBUG       # HTTPS obligatoire en production
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    # ------------------------------------------------------------------
    # Base de données MySQL
    # ------------------------------------------------------------------
    DB_HOST = env("DB_HOST", "localhost")
    DB_USER = env("DB_USER", "root")
    DB_PASSWORD = env("DB_PASSWORD", "")
    DB_NAME = env("DB_NAME", "business_dashboard")
    DB_PORT = env_int("DB_PORT", 3306)

    # TLS : la plupart des bases MySQL managées (Aiven, Railway, PlanetScale…)
    # exigent une connexion chiffrée depuis Vercel.
    DB_SSL = env_bool("DB_SSL", False)
    DB_SSL_CA = env("DB_SSL_CA")            # chemin vers le certificat CA

    DB_CONNECT_TIMEOUT = env_int("DB_CONNECT_TIMEOUT", 10)

    # ------------------------------------------------------------------
    # Règles métier du tableau de bord
    # ------------------------------------------------------------------
    DASHBOARD_MONTHS = env_int("DASHBOARD_MONTHS", 12)        # profondeur des courbes
    RECENT_TRANSACTIONS = env_int("RECENT_TRANSACTIONS", 10)  # lignes du tableau
    MAX_CATEGORIES = env_int("MAX_CATEGORIES", 8)             # parts du camembert
    CURRENCY = env("CURRENCY", "FCFA")

    # Si la table transactions possède une colonne user_id, chaque utilisateur
    # ne voit que ses propres données. Mettre à false pour une base commune
    # de démonstration.
    SCOPE_BY_USER = env_bool("SCOPE_BY_USER", True)

    # ------------------------------------------------------------------
    # Méthodes utilitaires
    # ------------------------------------------------------------------
    @classmethod
    def db_params(cls):
        """Paramètres de connexion transmis à PyMySQL."""
        params = {
            "host": cls.DB_HOST,
            "user": cls.DB_USER,
            "password": cls.DB_PASSWORD,
            "database": cls.DB_NAME,
            "port": cls.DB_PORT,
            "charset": "utf8mb4",
            "connect_timeout": cls.DB_CONNECT_TIMEOUT,
            "autocommit": True,
        }

        if cls.DB_SSL_CA:
            # Vérification complète du certificat du serveur (recommandé).
            params["ssl_ca"] = cls.DB_SSL_CA
            params["ssl_verify_cert"] = True
        elif cls.DB_SSL:
            # Connexion chiffrée sans vérification du certificat :
            # dépannage uniquement, préférez DB_SSL_CA.
            params["ssl"] = {"check_hostname": False}

        return params

    @classmethod
    def validate(cls):
        """
        Vérifie que la configuration est utilisable.
        Renvoie la liste des problèmes détectés (vide si tout va bien).
        """
        problems = []

        if not cls.DEBUG and cls.SECRET_KEY == "dev-only-change-me":
            problems.append(
                "SECRET_KEY n'est pas définie. Générez-la avec : "
                "python -c \"import secrets; print(secrets.token_hex(32))\""
            )

        for name in ("DB_HOST", "DB_USER", "DB_NAME"):
            if not getattr(cls, name):
                problems.append(f"{name} est vide.")

        if not cls.DB_PASSWORD and not cls.DEBUG:
            problems.append("DB_PASSWORD est vide en production.")

        return problems
