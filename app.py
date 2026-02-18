from flask import Flask, render_template, request, redirect, session, url_for
from datetime import datetime, timezone
import psycopg2
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "opensolve_secret_key"

# Upload folder configuration
UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

def get_db_connection():
    # Database connection URL
    DATABASE_URL = "postgresql://postgres:Harpalsinh%40123@localhost:5432/website"
    return psycopg2.connect(DATABASE_URL)

def time_ago(post_time):
    if post_time is None: return "Just now"
    now = datetime.now(timezone.utc) if post_time.tzinfo else datetime.now()
    diff = now - post_time
    sec = diff.total_seconds()
    if sec < 60: return f"{int(sec)} sec ago"
    elif sec < 3600: return f"{int(sec//60)} min ago"
    elif sec < 86400: return f"{int(sec//3600)} hr ago"
    return f"{int(sec//86400)} days ago"

# Filter register
app.jinja_env.filters['time_ago'] = time_ago

# ---------- ROUTES ----------

@app.route("/")
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username")
        p = request.form.get("password")
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username=%s AND password=%s", (u, p))
        user = cur.fetchone()
        cur.close()
        conn.close()
        if user:
            session["username"] = u
            return redirect(url_for('home'))
        return render_template("login.html", error="Invalid login!")
    return render_template("login.html")

@app.route("/home")
def home():
    if "username" not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, title, description, lat, lng, image_file, votes, username, created_at 
        FROM problems ORDER BY id DESC
    """)
    probs = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("index.html", problems=probs)

@app.route("/post", methods=["GET", "POST"])
def post():
    if "username" not in session: return redirect(url_for('login'))
    if request.method == "POST":
        t = request.form.get("title")
        d = request.form.get("description")
        lat = request.form.get("lat")
        lng = request.form.get("lng")
        f = request.files.get("image")
        
        filename = secure_filename(f.filename) if f else ""
        if f: f.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO problems (title, description, lat, lng, image_file, username) 
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (t, d, lat, lng, filename, session["username"]))
        cur.execute("UPDATE users SET score = score + 10 WHERE username=%s", (session["username"],))
        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for('home'))
    return render_template("post.html")

@app.route("/vote/<int:id>")
def vote(id):
    if "username" not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO votes (user_id, problem_id) VALUES (%s, %s)", (session["username"], id))
        cur.execute("UPDATE problems SET votes = votes + 1 WHERE id=%s", (id,))
        conn.commit()
    except:
        conn.rollback()
    finally:
        cur.close()
        conn.close()
    return redirect(url_for('home'))

@app.route("/delete/<int:id>", methods=["POST"])
def delete_problem(id):
    if "username" not in session: 
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 1. Pehla check karo ke aa problem exist kare chhe ane user teno owner chhe?
    cur.execute("SELECT username FROM problems WHERE id=%s", (id,))
    problem = cur.fetchone()
    
    if problem and problem[0] == session["username"]:
        try:
            # 2. Problem delete karo
            cur.execute("DELETE FROM problems WHERE id=%s", (id,))
            
            # 3. User na points down (minus) karo (Post karva par 10 aapya hata, to delete par 10 minus)
            cur.execute("UPDATE users SET score = score - 10 WHERE username=%s", (session["username"],))
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Delete Error: {e}")
    
    cur.close()
    conn.close()
    return redirect(url_for('home'))
@app.route("/leaderboard")
def leaderboard():
    if "username" not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT username, score FROM users ORDER BY score DESC LIMIT 10")
    users = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("leaderboard.html", users=users)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route("/problem/<int:id>")
def problem_detail(id):
    if "username" not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM problems WHERE id=%s", (id,))
    p = cur.fetchone()
    cur.close()
    conn.close()
    if p:
        return render_template("problem_detail.html", problem=p)
    return "Problem Not Found", 404

# --- FIX: SOLUTION PAGE ROUTE ---
@app.route("/solution/<int:id>")
def solution_page(id):
    if "username" not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    # Problem details fetch karo
    cur.execute("SELECT * FROM problems WHERE id=%s", (id,))
    prob = cur.fetchone()
    # Related comments fetch karo
    cur.execute("SELECT * FROM comments WHERE problem_id=%s ORDER BY created_at DESC", (id,))
    comments = cur.fetchall()
    cur.close()
    conn.close()
    if prob:
        return render_template("solution.html", problem=prob, solutions=comments)
    return "Not Found", 404

# --- FIX: POST COMMENT ROUTE ---
@app.route("/post_comment/<int:id>", methods=["POST"])
def post_comment(id):
    if "username" not in session: return redirect(url_for('login'))
    comment_text = request.form.get("comment")
    if comment_text:
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO comments (problem_id, username, comment) VALUES (%s, %s, %s)", 
                        (id, session["username"], comment_text))
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Error: {e}")
        finally:
            cur.close()
            conn.close()
    # Redirect to solution_page function name
    return redirect(url_for('solution_page', id=id))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        u = request.form.get("username")
        p = request.form.get("password")
        m = request.form.get("mobile")
        
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            # User register karva mate
            cur.execute("INSERT INTO users (username, password, mobile, score) VALUES (%s, %s, %s, 0)", (u, p, m))
            conn.commit()
            return redirect(url_for('login'))
        except Exception as e:
            conn.rollback()
            return render_template("register.html", error="Username already exists!")
        finally:
            cur.close()
            conn.close()
            
    return render_template("register.html")

if __name__ == "__main__":
    app.run(debug=True)
