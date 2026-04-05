from flask import Flask, render_template, request, redirect, session, url_for, jsonify
from flask_socketio import SocketIO
from sqlalchemy import func, case, and_
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime
import re
import random, time
from mparser import parse_media
import requests
import markdown
from datetime import timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

ALLOWED_DOMAINS = {
    "gmail.com",
    "yahoo.com",
    "outlook.com",
    "hotmail.com",
    "icloud.com",
    "proton.me",
    "protonmail.com",
    "aol.com",
    "live.com",
    "yahoo.in",
    "rediffmail.com",
    "indiatimes.com",
    "edu.in",
    "ac.in",
    "edu",
    "sspubhilai.com",
    "sstc.com",
    "sstc.ac.in"
}


app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default-secret')
app.config['SESSION_COOKIE_SECURE'] = True      # HTTPS only
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'   # Required for cross-origin
app.config['SESSION_COOKIE_HTTPONLY'] = True

# Load environment variables from .env
load_dotenv()

# Fetch variables
USER = os.getenv("DB_USER") 
PASSWORD = os.getenv("DB_PASSWORD")
HOST = os.getenv("DB_HOST")
PORT = os.getenv("DB_PORT")
DBNAME = os.getenv("DB_NAME")

BREVO_API_KEY = os.getenv("BREVO_API_KEY")

OTPEXPIRYSECONDS = int(os.getenv("OTP_EXPIRY_SECONDS", 300))


# Construct the SQLAlchemy connection string
DATABASE_URL = os.getenv("DATABASE_URL")

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL') 
app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER')
db = SQLAlchemy(app)
socketio = SocketIO(app, async_mode='threading',  cors_allowed_origins="*")

# -------------------- Models --------------------
class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(200), nullable=False)
    
    role = db.Column(db.String(20), default="user")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(IST))

    # Relationships
    posts = db.relationship("Post", backref="author", foreign_keys="Post.author_id", lazy=True)
    reviewed_posts = db.relationship("Post", backref="reviewer", foreign_keys="Post.reviewed_by", lazy=True)

    reactions = db.relationship("PostReaction", backref="user", lazy=True)
    comments = db.relationship("Comment", backref="user", lazy=True)

    followers = db.relationship(
        "Follow",
        foreign_keys="Follow.following_id",
        backref="following_user",
        lazy=True
    )

    following = db.relationship(
        "Follow",
        foreign_keys="Follow.follower_id",
        backref="follower_user",
        lazy=True
    )

class Post(db.Model):
    __tablename__ = "posts"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    link = db.Column(db.String(500), nullable=True)
    media_html = db.Column(db.Text, nullable=True)
    mediaType = db.Column(db.Text, nullable=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    status = db.Column(db.String(20), default="pending")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(IST))

    # Relationships
    reactions = db.relationship("PostReaction", backref="post", lazy=True)
    comments = db.relationship("Comment", backref="post", lazy=True)

class PostReaction(db.Model):
    __tablename__ = "post_reactions"

    id = db.Column(db.Integer, primary_key=True)

    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    reaction_type = db.Column(db.String(10), nullable=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(IST))

    __table_args__ = (
        db.UniqueConstraint('post_id', 'user_id', name='unique_user_post_reaction'),
    )

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(IST))

    __table_args__ = (
        db.UniqueConstraint('post_id', 'user_id', name='unique_report'),
    )

class Comment(db.Model):
    __tablename__ = "comments"

    id = db.Column(db.Integer, primary_key=True)

    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    content = db.Column(db.Text, nullable=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(IST))

class Follow(db.Model):
    __tablename__ = "follows"

    id = db.Column(db.Integer, primary_key=True)

    follower_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    following_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(IST))

    __table_args__ = (
        db.UniqueConstraint('follower_id', 'following_id', name='unique_follow'),
    )

#---------------send OTP------------------------------------------------------
def send_otp_email(recipient_email, otp, name=None):

    html = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="UTF-8">
        </head>
        <body style="margin:0; padding:0; font-family: Arial, sans-serif; background-color:#f4f4f4;">

        <table align="center" width="100%" style="max-width:600px; margin:auto; background:#ffffff; border-radius:10px; overflow:hidden; box-shadow:0 4px 10px rgba(0,0,0,0.1);">

            <!-- Header -->
            <tr>
            <td style="background:#F98025; padding:20px; text-align:center; color:white;">
                <h2 style="margin:0; font-weight:bold;">
                    Bench<span style="font-weight:lighter;">Newz</span>
                </h2>
                <p style="margin:5px 0 0;">Secure Email Verification</p>
            </td>
            </tr>

            <!-- Body -->
            <tr>
            <td style="padding:30px; text-align:center; color:#333;">
                <h3 style="margin-bottom:10px;">Your OTP Code</h3>
                <p style="font-size:14px; color:#777;">
                Use the following One-Time Password (OTP) to verify your email address.
                </p>

                <!-- OTP Box -->
                <div style="margin:25px 0;">
                <span style="
                    display:inline-block;
                    font-size:28px;
                    letter-spacing:6px;
                    font-weight:bold;
                    background:#f0f4ff;
                    padding:15px 25px;
                    border-radius:8px;
                    color:#F98025;
                ">
                    { otp }
                </span>
                </div>

                <p style="font-size:13px; color:#999;">
                This OTP is valid for 5 minutes. Do not share it with anyone.
                </p>
            </td>
            </tr>

            <!-- Footer -->
            <tr>
            <td style="background:#f9f9f9; padding:15px; text-align:center; font-size:12px; color:#aaa;">
                If you didn’t request this, you can safely ignore this email.
                <br><br>
                BenchNewz - Made with ❤️ by Code Monks!
            </td>
            </tr>

        </table>

        </body>
        </html>
    """

    payload = {
        "sender": {
            "name": "BenchNewz",
            "email": "benchnewz@gmail.com" 
        },
        "to": [
            {"email": recipient_email, "name": name or "User"}
        ],
        "subject": "Your Login OTP - BenchNewz",
        "htmlContent": html
    }

    response = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={
            "api-key": os.getenv("BREVO_API_KEY"),
            "Content-Type": "application/json"
        },
        json=payload
    )

    if response.status_code not in (200, 201):
        raise Exception(f"Brevo error {response.status_code}: {response.text}")

#---------------------------------------------------------------------------

def time_ago(dt):
    IST = timezone(timedelta(hours=5, minutes=30))
    now = datetime.now(timezone.utc)
    
    # make dt timezone aware as UTC if it isn't
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    diff = now - dt
    seconds = diff.total_seconds()
    minutes = seconds / 60
    hours = seconds / 3600

    if seconds < 60:
        return "just now"
    elif minutes < 60:
        m = int(minutes)
        return f"{m} minute{'s' if m > 1 else ''} ago"
    elif hours < 24:
        h = int(hours)
        return f"{h} hour{'s' if h > 1 else ''} ago"
    elif hours < 48:
        return f"Yesterday, {dt.astimezone(IST).strftime('%I:%M %p')}"
    else:
        return dt.astimezone(IST).strftime('%-d %B, %Y %I:%M %p')

app.jinja_env.filters['time_ago'] = time_ago

# short posts ------------------------------------------------

def sanitize_headings(text):
    return re.sub(r'^(#{1,3})\s+(.+?)\s*$', r'\1 \2', text, flags=re.MULTILINE)

MAX_CONTENT_LENGTH = 500

def process_post_content(content):
    clean = sanitize_headings(content)
    is_long = len(content) > MAX_CONTENT_LENGTH
    short = content[:MAX_CONTENT_LENGTH] + '...' if is_long else content
    return {
        'full': markdown.markdown(clean),
        'short': markdown.markdown(sanitize_headings(short)),
        'is_long': is_long
    }

# -------------------- Regex --------------------
EMAIL_REGEX = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

def is_valid_email(email):
    return re.fullmatch(EMAIL_REGEX, email) is not None

def validate_password(password):
    if len(password) < 8:
        return "Password must be at least 8 characters long"
    if not re.search(r'[A-Z]', password):
        return "Must include an uppercase letter"
    if not re.search(r'[a-z]', password):
        return "Must include a lowercase letter"
    if not re.search(r'\d', password):
        return "Must include a number"
    if not re.search(r'[@$!%*?&]', password):
        return "Must include a special character"
    return None

# -------------------- Routes --------------------
@app.route('/')
def index():
    if 'otp' in session:
        session.pop('otp', None)
        session.pop('otp_time', None)
        session.pop('pending_user', None)
    if 'username' in session:
        return redirect(url_for('feed'))
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    if 'otp' in session:
        session.pop('otp', None)
        session.pop('otp_time', None)
        session.pop('pending_user', None)
    try:
        username = request.form['username'].strip()
        user = User.query.filter(func.lower(User.username) == username.lower()).first()
    except KeyError:
        pass
    try:
        email = request.form['email'].strip().lower()
        user = User.query.filter_by(email=email).first()
    except KeyError:
        pass
    password = request.form['password']
    if user and check_password_hash(user.password_hash, password):
        session['username'] = user.username
        session['user_id'] = user.id
        session['role'] = user.role
        return redirect(url_for('feed'))
    return render_template('login.html', error = 'Invalid credentials')

@app.route('/signup', methods=['GET', 'POST'])
def signup():

    if 'otp' in session:

        if request.method == 'GET':
            return render_template('signup.html', verify=True)

        if request.method == 'POST':
            entered_otp = request.form['otp'].strip()
            stored_otp  = session.get('otp')
            otp_time    = session.get('otp_time', 0)

            if time.time() - otp_time > OTPEXPIRYSECONDS:
                session.pop('otp', None)
                session.pop('otp_time', None)
                session.pop('pending_user', None)
                return render_template('signup.html', verify=False, error='OTP expired. Please signup again.')

            if entered_otp == stored_otp:
                session.pop('otp', None)
                session.pop('otp_time', None)
                data = session.get('pending_user')

                user = User(**data)
                db.session.add(user)
                db.session.commit()
                return redirect(url_for('index'))
            else:
                session.pop('otp', None)
                session.pop('otp_time', None)
                session.pop('pending_user', None)
                return render_template('signup.html', verify=False, error='Invalid OTP. Please try again.')

    else:
        if request.method == 'POST':

            name = request.form['name']
            username = request.form['username'].strip()
            email = request.form['email'].strip().lower()

            domain = email.split('@')[-1].strip().lower()
            print("EMAIL:", email)
            print("DOMAIN:", domain)
            print("ALLOWED:", ALLOWED_DOMAINS)
            print("CHECK:", domain in ALLOWED_DOMAINS)
            if (email.split('@')[-1].lower().strip() not in ALLOWED_DOMAINS):
                return render_template('signup.html', error="Email domain not allowed")
            
            if not is_valid_email(email):
                return render_template('signup.html', error="Invalid email format")

            password_error = validate_password(request.form['password'])
            if password_error:
                return render_template('signup.html', error=password_error)

            password_hash = generate_password_hash(request.form['password'])

            if User.query.filter_by(email=email).first():
                return render_template('signup.html', error="User already exists")

            if User.query.filter_by(username=username).first():
                return render_template('signup.html', error="Username already taken")

            role = request.form.get('role')

            user = User(
                name=name,
                username=username,
                email=email,
                password_hash=password_hash,
                role=role
            )

            if role == "reporter":
                otp = str(random.randint(100000, 999999))
                session['otp'] = otp
                session['otp_time'] = time.time()
                session['pending_user'] = {
                    "name": name,
                    "username": username,
                    "email": email,
                    "password_hash": password_hash,
                    "role": role
                }

                try:
                    send_otp_email(user.email, otp, name=name)
                except Exception:
                    session.clear()
                    return render_template('signup.html', error='Unable to send OTP. Please contact Admin.')

                return render_template('signup.html', verify=True)

            else:
                db.session.add(user)
                db.session.commit()
                return redirect(url_for('index'))

        return render_template('signup.html')

@app.route('/signup/o')
def o():
    session.pop('otp', None)
    session.pop('otp_time', None)
    session.pop('pending_user', None)
    return redirect(url_for('signup'))
    

OTP_EXPIRY = 300

@app.route('/fp', methods=['GET', 'POST'])
def fp():

    # STEP 0 → Show email input
    if request.method == 'GET':
        return render_template('fp.html', verify=0)

    # STEP 1 → Email submitted → send OTP
    if 'otp' not in session and 'fp_user' not in session:
        email = request.form.get('email', '').strip().lower()

        user = User.query.filter_by(email=email).first()
        if not user:
            return render_template('fp.html', verify=0, error="Email not found")

        otp = str(random.randint(100000, 999999))

        session['otp'] = otp
        session['otp_time'] = time.time()
        session['fp_user'] = user.id

        try:
            send_otp_email(email, otp, name=user.name)
        except Exception:
            return render_template('fp.html', verify=0, error="Failed to send OTP")

        return render_template('fp.html', verify=1)

    # STEP 2 → OTP verification
    if 'otp' in session and 'fp_user' in session:
        entered_otp = request.form.get('otp')

        if time.time() - session['otp_time'] > OTP_EXPIRY:
            session.clear()
            return render_template('fp.html', verify=0, error="OTP expired")

        if entered_otp == session['otp']:
            session.pop('otp')  # OTP done
            return render_template('fp.html', verify=2)
        else:
            session.pop('otp')
            return render_template('fp.html', verify=1, error="Invalid OTP")

    # STEP 3 → Reset password
    if 'fp_user' in session:
        password = request.form.get('password')

        password_error = validate_password(password)
        if password_error:
            return render_template('fp.html', verify=2, error=password_error)

        user = User.query.get(session['fp_user'])
        user.password_hash = generate_password_hash(password)

        db.session.commit()
        session.clear()

        return redirect(url_for('index'))

    return redirect(url_for('index'))


@app.route('/cr', methods=['GET', 'POST'])
def cr():

    # STEP 0 → Show email input
    if request.method == 'GET':
        return render_template('cr.html', verify=0)

    # STEP 1 → Email submitted → send OTP
    if 'otp' not in session and 'cr_user' not in session:
        email = request.form.get('email', '').strip().lower()

        user = User.query.filter_by(email=email).first()
        if not user:
            return render_template('cr.html', verify=0, error="Email not found")

        otp = str(random.randint(100000, 999999))

        session['otp'] = otp
        session['otp_time'] = time.time()
        session['cr_user'] = user.id

        try:
            send_otp_email(email, otp, name=user.name)
        except Exception:
            return render_template('cr.html', verify=0, error="Failed to send OTP")

        return render_template('cr.html', verify=1)

    # STEP 2 → OTP verification
    if 'otp' in session and 'cr_user' in session:
        entered_otp = request.form.get('otp')

        if time.time() - session['otp_time'] > OTP_EXPIRY:
            session.clear()
            return render_template('cr.html', verify=0, error="OTP expired")

        if entered_otp == session['otp']:
            session.pop('otp')  # OTP done
            return render_template('cr.html', verify=2)
        else:
            session.pop('otp')
            return render_template('cr.html', verify=1, error="Invalid OTP")

    # STEP 3 → change role
    if 'cr_user' in session:
        role = request.form.get('role')

        user = User.query.get(session['cr_user'])
        user.role = role

        db.session.commit()
        session.clear()

        return redirect(url_for('cr'))

    return redirect(url_for('cr'))

@app.route('/deleteAcc', methods=['GET'])
def delete_account_page():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    return render_template('da.html')

@app.route('/da', methods=['POST'])
def da():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    password = request.form.get('password')

    user = User.query.get(session['user_id'])

    if not user or not check_password_hash(user.password_hash, password):
        return render_template('myprofile.html', error="Incorrect password")

    db.session.delete(user)
    db.session.commit()

    session.clear()

    return redirect(url_for('index'))

    
@app.route('/check-username')
def check_username():
    username = request.args.get('username', '').strip().lower()

    if not username:
        return {'available': False}

    user = User.query.filter(func.lower(User.username) == username.lower()).first()

    print("Checking username:", username)
    print("User found:", user)

    return {'available': user is None}

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/feed')
def feed():
    if 'username' not in session:
        return redirect(url_for('index'))

    user_id = session.get('user_id')

    posts = Post.query.filter_by(status="approved")\
        .order_by(Post.created_at.desc())\
        .all()

    like_counts = dict(
        db.session.query(
            PostReaction.post_id,
            func.count().label('count')
        )
        .filter(PostReaction.reaction_type == 'like')
        .group_by(PostReaction.post_id)
        .all()
    )

    liked_posts = set(
        r.post_id for r in PostReaction.query.filter_by(
            user_id=user_id,
            reaction_type='like'
        ).all()
    )

    posts_data = []
    for post in posts:
        processed = process_post_content(post.content)
        posts_data.append({
            'post': post,
            'like_count': like_counts.get(post.id, 0),
            'is_liked': post.id in liked_posts,
            'pcontent': processed['full'],
            'pcontent_short': processed['short'],
            'is_long': processed['is_long'],
            'ptitle': markdown.markdown(sanitize_headings(post.title))
        })

    role = User.query.get(session['user_id']).role
    return render_template(
        'feed.html',
        posts=posts_data,
        username=session['username'],
        role = role
    )

@app.route('/post', methods=['GET', 'POST'])
def post():
    if 'username' not in session:
        return redirect(url_for('index'))
    
    user = User.query.get(session['user_id'])

    if user.role not in ["reporter", "admin"]:
        return redirect(url_for('index'))

    # if not user.is_verified:
    #     return "Verify your account first", 403

    if request.method == 'POST':
        title = request.form['title']
        link = request.form.get('link')
        content = request.form['content']
        media_type = request.form.get('mediaType')
        media_html = parse_media(link, media_type) if link else None
        post = Post(title=title, link=link, content=content, media_html=media_html, mediaType=media_type, author_id=session['user_id'])
        db.session.add(post)
        db.session.commit()
        return redirect(url_for('feed'))
    return render_template('post.html', role=session['role'])

@app.route('/search', methods=['GET'])
def search():
    if 'username' not in session:
        return redirect(url_for('index'))

    query = request.args.get('q', '').strip()

    if not query:
        return render_template('search.html', role=session['role'])

    user_matches = User.query.filter(User.username.ilike(f'%{query}%')).order_by(case(
                    (User.username.ilike(f'{query}%'), 0),
                    else_=1
                ),
                User.username.asc()
            ).limit(10).all()

    posts = Post.query.filter(
        Post.status == "approved",
        and_(
            Post.title.ilike(f'%{query}%'),
            Post.content.ilike(f'%{query}%')
        )
    ).order_by(case(
                (Post.title.ilike(f'{query}%'), 0),   # title starts with query  → highest
                (Post.title.ilike(f'%{query}%'), 1),   # query in title           → second
                (Post.content.ilike(f'%{query}%'), 2), # query only in content    → third
                else_=3
            ), Post.created_at.desc()).limit(10).all()

    like_counts = dict(
        db.session.query(
            PostReaction.post_id,
            func.count().label('count')
        )
        .filter(PostReaction.reaction_type == 'like')
        .group_by(PostReaction.post_id)
        .all()
    )

    user = User.query.get(session['user_id'])

    liked_posts = set(
        r.post_id for r in PostReaction.query.filter_by(
            user_id=user.id,
            reaction_type='like'
        ).all()
    )

    posts_data = []
    for post in posts:
        processed = process_post_content(post.content)
        posts_data.append({
            'post': post,
            'like_count': like_counts.get(post.id, 0),
            'is_liked': post.id in liked_posts,
            'pcontent': processed['full'],
            'pcontent_short': processed['short'],
            'is_long': processed['is_long'],
            'ptitle': markdown.markdown(sanitize_headings(post.title))
        })

    if not posts and not user_matches:
        return render_template(
            'search.html',
            posts=0,
            username=session['username'],
            role=session['role'],
            query=query,
            user_matches=0
        )

    return render_template(
        'search.html',
        posts=posts_data,
        username=session['username'],
        role=session['role'],
        query=query,
        user_matches=user_matches
    )


@app.route('/post/<int:post_id>/react', methods=['POST'])
def react_post(post_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session['user_id']
    reaction_type = request.json.get('type')  # 'like' or 'report'

    reaction = PostReaction.query.filter_by(
        post_id=post_id,
        user_id=user_id
    ).first()

    if reaction:
        # SAME reaction → remove (toggle)
        if reaction.reaction_type == reaction_type:
            db.session.delete(reaction)
            action = 'removed'

        # DIFFERENT reaction → update
        else:
            reaction.reaction_type = reaction_type
            action = 'updated'
    else:
        # No reaction yet → create
        reaction = PostReaction(
            post_id=post_id,
            user_id=user_id,
            reaction_type=reaction_type
        )
        db.session.add(reaction)
        action = 'added'

    db.session.commit()

    # Count likes
    likes = PostReaction.query.filter_by(
        post_id=post_id,
        reaction_type='like'
    ).count()

    return jsonify({
        'status': action,
        'likes': likes
    })

@app.route('/post/<int:post_id>/report', methods=['POST'])
def report_post(post_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session['user_id']

    # Prevent duplicate reports
    existing = Report.query.filter_by(
        post_id=post_id,
        user_id=user_id
    ).first()

    if existing:
        return jsonify({'status': 'already_reported'})

    report = Report(post_id=post_id, user_id=user_id)
    db.session.add(report)

    # Count reports
    report_count = Report.query.filter_by(post_id=post_id).count()

    post = Post.query.get_or_404(post_id)

    # Threshold logic (IMPORTANT)
    if report_count >= 3:
        post.status = 'reported'

    db.session.commit()

    return jsonify({
        'status': 'reported',
        'reports': report_count
    })

@app.route('/post/<int:post_id>/comment', methods=['POST'])
def comment_on_post(post_id):
    if 'username' not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    content = request.form['content']
    comment = Comment(post_id=post_id, user_id=session['user_id'], content=content)
    db.session.add(comment)
    db.session.commit()
    return jsonify({"status": "success"})

@app.route('/profile/<string:username>')
def profile(username):
    user = User.query.filter_by(username=username).first()

    if not user:
        return "User not found", 404

    # Optional: fetch user's posts
    posts = Post.query.filter_by(author_id=user.id).order_by(Post.created_at.desc()).all()

    like_counts = dict(
        db.session.query(
            PostReaction.post_id,
            func.count().label('count')
        )
        .filter(PostReaction.reaction_type == 'like')
        .group_by(PostReaction.post_id)
        .all()
    )

    liked_posts = set(
        r.post_id for r in PostReaction.query.filter_by(
            user_id=user.id,
            reaction_type='like'
        ).all()
    )

    posts_data = []
    for post in posts:
        processed = process_post_content(post.content)
        posts_data.append({
            'post': post,
            'like_count': like_counts.get(post.id, 0),
            'is_liked': post.id in liked_posts,
            'pcontent': processed['full'],
            'pcontent_short': processed['short'],
            'is_long': processed['is_long'],
            'ptitle': markdown.markdown(sanitize_headings(post.title))
        })

    return render_template(
        'profile.html',
        user=user,
        posts=posts_data,
        username=session['username'],
        role=session['role']
    )

    # return render_template('profile.html', user=user, posts=posts)

@app.route('/myprofile')
def myprofile():
    if 'username' not in session:
        return redirect(url_for('index'))

    user = User.query.get(session['user_id'])
    posts = Post.query.filter_by(author_id=user.id).order_by(Post.created_at.desc()).all()
    like_counts = dict(
        db.session.query(
            PostReaction.post_id,
            func.count().label('count')
        )
        .filter(PostReaction.reaction_type == 'like')
        .group_by(PostReaction.post_id)
        .all()
    )

    liked_posts = set(
        r.post_id for r in PostReaction.query.filter_by(
            user_id=user.id,
            reaction_type='like'
        ).all()
    )

    posts_data = []
    for post in posts:
        processed = process_post_content(post.content)
        posts_data.append({
            'post': post,
            'like_count': like_counts.get(post.id, 0),
            'is_liked': post.id in liked_posts,
            'pcontent': processed['full'],
            'pcontent_short': processed['short'],
            'is_long': processed['is_long'],
            'ptitle': markdown.markdown(sanitize_headings(post.title))
        })

    return render_template('myprofile.html', user=user, name=user.name, username=user.username, email=user.email, role=user.role, date_joined=user.created_at.strftime('%d %b, %Y'), posts=posts_data, followers=len(user.followers), following=len(user.following), postUnderReview=Post.query.filter_by(author_id=user.id, status="pending").count(), postRejected=Post.query.filter_by(author_id=user.id, status="rejected").count(), postApproved=Post.query.filter_by(author_id=user.id, status="approved").count())

@app.route('/follow/<int:user_id>', methods=['POST'])
def follow_user(user_id):
    if 'username' not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    existing_follow = Follow.query.filter_by(follower_id=session['user_id'], following_id=user_id).first()
    if existing_follow:
        db.session.delete(existing_follow)
        db.session.commit()
        return jsonify({"status": "unfollowed"})
    else:
        new_follow = Follow(follower_id=session['user_id'], following_id=user_id)
        db.session.add(new_follow)
        db.session.commit()
        return jsonify({"status": "followed"})

@app.route('/adminPanel')
def adminPanel():
    if 'username' not in session or session.get('role') != 'admin':
        return redirect(url_for('index'))

    posts = Post.query.filter(Post.status.in_(["pending", "reported"])).order_by(Post.created_at.desc()).all()

    like_counts = dict(
        db.session.query(
            PostReaction.post_id,
            func.count().label('count')
        )
        .filter(PostReaction.reaction_type == 'like')
        .group_by(PostReaction.post_id)
        .all()
    )

    user = User.query.get(session['user_id'])

    liked_posts = set(
        r.post_id for r in PostReaction.query.filter_by(
            user_id=user.id,
            reaction_type='like'
        ).all()
    )

    posts_data = []
    for post in posts:
        processed = process_post_content(post.content)
        posts_data.append({
            'post': post,
            'like_count': like_counts.get(post.id, 0),
            'is_liked': post.id in liked_posts,
            'pcontent': processed['full'],
            'pcontent_short': processed['short'],
            'is_long': processed['is_long'],
            'ptitle': markdown.markdown(sanitize_headings(post.title))
        })

    return render_template('adminPanel.html', posts=posts_data, username=session['username'], role=session['role'])

@app.route('/adminPanel/approve/<int:id>', methods=['POST'])
def approve_post(id):
    if session.get('role') != 'admin':
        return redirect(url_for('feed'))

    post = Post.query.get_or_404(id)
    post.status = "approved"

    Report.query.filter_by(post_id=id).delete()

    db.session.commit()

    return redirect(url_for('adminPanel'))


@app.route('/adminPanel/reject/<int:id>', methods=['POST'])
def reject_post(id):
    if session.get('role') != 'admin':
        return redirect(url_for('feed'))

    post = Post.query.get_or_404(id)
    post.status = "rejected"

    Report.query.filter_by(post_id=id).delete()

    db.session.commit()

    return redirect(url_for('adminPanel'))

# -------------------- Create DB Tables --------------------
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)