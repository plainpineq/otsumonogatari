from flask import request, render_template, redirect, session
from db import get_user_conn
from security import verify_password

def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        with get_user_conn() as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE email=?", (email,)
            ).fetchone()

        if user and verify_password(password, user["password_hash"]):
            session["user_id"] = email
            return redirect("/dashboard")

        return render_template("login.html", error="ログイン失敗")

    return render_template("login.html")
