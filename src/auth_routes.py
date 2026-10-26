
from functools import wraps

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    session,
    url_for,
)
from sqlalchemy import select
from werkzeug.security import check_password_hash

from src.portal_models import User


auth_bp = Blueprint("auth", __name__)


def get_current_user():
    """Return the authenticated user, or None."""
    user_id = session.get("user_id")
    if user_id is None:
        return None

    session_factory = current_app.config["SESSION_FACTORY"]
    with session_factory() as db:
        user = db.get(User, user_id)
        if user is None:
            session.clear()
            return None

        # Return only simple values after the database session closes.
        return {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "student_id": user.student_id,
        }


def login_required(view):
    """Require a valid authenticated session."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if get_current_user() is None:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


def role_required(*allowed_roles):
    """Restrict a view to specific account roles."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = get_current_user()

            if user is None:
                return redirect(url_for("auth.login"))

            if user["role"] not in allowed_roles:
                flash("You are not authorized to access that page.", "error")
                return redirect(url_for("home"))

            return view(*args, **kwargs)

        return wrapped
    return decorator


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Authenticate an account using its username and password."""
    from flask import request

    if get_current_user() is not None:
        return redirect(url_for("home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")

        session_factory = current_app.config["SESSION_FACTORY"]
        with session_factory() as db:
            user = db.scalar(
                select(User).where(User.username == username)
            )

            if user is None or not check_password_hash(
                user.password_hash, password
            ):
                flash("Invalid username or password.", "error")
                return render_template("login.html"), 401

            session.clear()
            session["user_id"] = user.id

        flash("Welcome back.", "success")
        return redirect(url_for("home"))

    return render_template("login.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    """End the current authenticated session."""
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("auth.login"))
