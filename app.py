from flask import Flask, render_template, request, redirect, session
from datetime import datetime
import psycopg2
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "secret123"

# ---------- UPLOAD FOLDER ----------
UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ---------- DATABASE (PostgreSQL for Render) ----------
DATABASE_URL = os.environ.get("DATABASE_URL")
conn = psycopg2.connect(DATABASE_URL, sslmode="require")


def get_cursor():
    return conn.cursor()


# ---------- TIME AGO ----------
def time_ago(post_time):
    now = datetime.now()
    diff = now - post_time
    sec = diff.total_seconds()

    if sec < 60:
        return f"{int(sec)} sec ago"
    elif sec < 3600:
        return f"{int(sec//60)} min ago"
    elif sec < 86400:
        return f"{int(sec//3600)} hr ago"
    return f"{int(sec//86400)} days ago"


# ---------- LOGIN ----------
@app.route("/", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        try:
            u = request.form["username"]
            p = request.form["password"]

            cur.execute("SELECT * FROM users WHERE username=%s", (u,))
            user = cur.fetchone()

            if user and user[2] == p:
                session["username"] = u
                return redirect("/home")
            else:
                error = "Invalid username or password"

        except Exception as e:
            conn.rollback()   # 🔥 VERY IMPORTANT
            print("LOGIN ERROR =", e)
            error = "Server error, try again"

    return render_template("login.html", error=error)



# ---------- REGISTER ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    error = ""
    username_val = ""

    if request.method == "POST":
        username_val = request.form["username"]
        password = request.form["password"]
        mobile = request.form["mobile"]

        cur = get_cursor()
        cur.execute("SELECT * FROM users WHERE username=%s", (username_val,))
        if cur.fetchone():
            error = "Username not valid"
        else:
            cur.execute(
                "INSERT INTO users(username,password,mobile,score) VALUES(%s,%s,%s,0)",
                (username_val, password, mobile)
            )
            conn.commit()
            session["username"] = username_val
            cur.close()
            return redirect("/home")

        cur.close()

    return render_template("register.html", error=error, username=username_val)


# ---------- HOME ----------
@app.route("/home")
def home():
    if "username" not in session:
        return redirect("/")

    cur = get_cursor()
    cur.execute("""
        SELECT id,title,description,latitude,longitude,image,votes,username,created_at
        FROM problems ORDER BY id DESC
    """)
    rows = cur.fetchall()
    cur.close()

    problems = []
    for r in rows:
        problems.append(r + (time_ago(r[8]),))

    return render_template("index.html", problems=problems)


# ---------- POST ----------
@app.route("/post", methods=["GET", "POST"])
def post():
    if "username" not in session:
        return redirect("/")

    if request.method == "POST":
        title = request.form["title"]
        desc = request.form["description"]
        lat = request.form["lat"]
        lng = request.form["lng"]

        file = request.files["image"]
        filename = ""

        if file and file.filename != "":
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        cur = get_cursor()
        cur.execute("""
            INSERT INTO problems(title,description,latitude,longitude,image,votes,username)
            VALUES(%s,%s,%s,%s,%s,0,%s)
        """, (title, desc, lat, lng, filename, session["username"]))

        cur.execute("SELECT COUNT(*) FROM problems WHERE username=%s",
                    (session["username"],))
        total_posts = cur.fetchone()[0]

        cur.execute("UPDATE users SET score=%s WHERE username=%s",
                    (total_posts * 5, session["username"]))

        conn.commit()
        cur.close()

        return redirect("/home")

    return render_template("post.html")


# ---------- UPVOTE ----------
@app.route("/vote/<int:id>")
def vote(id):
    if "username" not in session:
        return redirect("/")

    cur = get_cursor()

    cur.execute("SELECT * FROM votes WHERE username=%s AND problem_id=%s",
                (session["username"], id))
    if cur.fetchone():
        cur.close()
        return redirect("/home")

    cur.execute("INSERT INTO votes(username,problem_id) VALUES(%s,%s)",
                (session["username"], id))
    cur.execute("UPDATE problems SET votes=votes+1 WHERE id=%s", (id,))
    conn.commit()
    cur.close()

    return redirect("/home")


# ---------- DELETE ----------
@app.route("/delete/<int:id>", methods=["POST"])
def delete(id):
    if "username" not in session:
        return redirect("/")

    cur = get_cursor()
    cur.execute("SELECT username FROM problems WHERE id=%s", (id,))
    post = cur.fetchone()

    if not post:
        cur.close()
        return redirect("/home")

    owner = post[0]

    if session["username"] == "Harpalsinh" or owner == session["username"]:
        cur.execute("DELETE FROM problems WHERE id=%s", (id,))

        cur.execute("SELECT COUNT(*) FROM problems WHERE username=%s", (owner,))
        total_posts = cur.fetchone()[0]

        cur.execute("UPDATE users SET score=%s WHERE username=%s",
                    (total_posts * 5, owner))

        conn.commit()

    cur.close()
    return redirect("/home")


# ---------- SOLUTION + COMMENTS ----------
@app.route("/solution/<int:id>", methods=["GET", "POST"])
def solution(id):
    if "username" not in session:
        return redirect("/")

    cur = get_cursor()

    if request.method == "POST":
        text = request.form["comment"]
        if text.strip():
            cur.execute(
                "INSERT INTO comments(problem_id,username,comment) VALUES(%s,%s,%s)",
                (id, session["username"], text)
            )
            conn.commit()

    cur.execute("SELECT title,description FROM problems WHERE id=%s", (id,))
    p = cur.fetchone()

    cur.execute("""
        SELECT username,comment,created_at
        FROM comments WHERE problem_id=%s ORDER BY id DESC
    """, (id,))
    comments = cur.fetchall()
    cur.close()

    solution_text = f"""
Problem: {p[0]}

Description: {p[1]}

Suggested Solution:
• Report to authority
• Temporary fix
• Community help
"""

    return render_template("solution.html",
                           solution=solution_text,
                           comments=comments,
                           problem_id=id)


# ---------- LEADERBOARD ----------
@app.route("/leaderboard")
def leaderboard():
    if "username" not in session:
        return redirect("/")

    cur = get_cursor()
    cur.execute("SELECT username,score FROM users ORDER BY score DESC")
    users = cur.fetchall()
    cur.close()

    return render_template("leaderboard.html", users=users)


# ---------- LOGOUT ----------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ---------- RUN ----------
if __name__ == "__main__":
    app.run(debug=True)

