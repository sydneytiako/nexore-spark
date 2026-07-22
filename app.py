"""
NEXORE Spark V3.0 — IFT Madagascar
Backend Flask complet — Version PostgreSQL (Neon) pour production
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_mail import Mail, Message as MailMessage
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
import psycopg2
import psycopg2.extras
import os, uuid, functools
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'nexore-ift-madagascar-secret-v3-2026')
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024
ALLOWED_EXT = {'png','jpg','jpeg','gif','webp','mp4','mov','avi','mkv','pdf','doc','docx','zip','pptx','xlsx','xls','txt','csv','mp3','wav','odt','ods'}

app.config['MAIL_SERVER']         = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT']           = int(os.environ.get('MAIL_PORT', '587'))
app.config['MAIL_USE_TLS']        = True
app.config['MAIL_USE_SSL']        = False
app.config['MAIL_USERNAME']       = os.environ.get('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD']       = os.environ.get('MAIL_PASSWORD', '')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'NEXORE IFT <noreply@nexore.mg>')

mail       = Mail(app)
serializer = URLSafeTimedSerializer(app.secret_key)
socketio = SocketIO(
    app,
    async_mode="gevent",
    cors_allowed_origins="*",
    manage_session=False
)

# ============ CONNEXION POSTGRESQL (NEON) ============
DATABASE_URL = os.environ.get('DATABASE_URL', '')

def get_db():
    """Retourne une connexion psycopg2 avec curseur en dictionnaire (comme sqlite3.Row)."""
    conn = psycopg2.connect(DATABASE_URL, sslmode='require', cursor_factory=psycopg2.extras.RealDictCursor)
    return conn

def init_db():
    db = get_db()
    c  = db.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY, uuid TEXT UNIQUE NOT NULL,
        nom TEXT NOT NULL, prenom TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'etudiant',
        filiere TEXT, niveau TEXT, matricule TEXT UNIQUE, avatar TEXT, cover TEXT,
        bio TEXT DEFAULT '', website TEXT DEFAULT '', phone TEXT DEFAULT '',
        theme TEXT DEFAULT 'dark', created_at TIMESTAMP DEFAULT NOW(),
        last_seen TIMESTAMP DEFAULT NOW(), is_online INTEGER DEFAULT 0, is_active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS posts (
        id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL,
        contenu TEXT NOT NULL, type TEXT DEFAULT 'general', media_url TEXT, media_type TEXT,
        filiere_target TEXT, niveau_target TEXT, visibility TEXT DEFAULT 'public',
        edited INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT NOW(),
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS reactions (
        id SERIAL PRIMARY KEY, post_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
        type TEXT NOT NULL DEFAULT 'like', created_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(post_id, user_id),
        FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS comments (
        id SERIAL PRIMARY KEY, post_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
        contenu TEXT NOT NULL, edited INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT NOW(),
        FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS follows (
        id SERIAL PRIMARY KEY, follower_id INTEGER NOT NULL, following_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(follower_id, following_id),
        FOREIGN KEY(follower_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(following_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS friend_requests (
        id SERIAL PRIMARY KEY, sender_id INTEGER NOT NULL, receiver_id INTEGER NOT NULL,
        status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(sender_id, receiver_id),
        FOREIGN KEY(sender_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(receiver_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS messages (
        id SERIAL PRIMARY KEY, client_id TEXT,
        sender_id INTEGER NOT NULL, receiver_id INTEGER, room_id TEXT,
        contenu TEXT NOT NULL, media_url TEXT, media_type TEXT,
        is_read INTEGER DEFAULT 0, edited INTEGER DEFAULT 0, deleted INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT NOW(),
        FOREIGN KEY(sender_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS rooms (
        id SERIAL PRIMARY KEY, room_id TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
        type TEXT DEFAULT 'group', filiere TEXT, niveau TEXT, creator_id INTEGER,
        avatar TEXT, description TEXT DEFAULT '', created_at TIMESTAMP DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS room_members (
        id SERIAL PRIMARY KEY, room_id TEXT NOT NULL, user_id INTEGER NOT NULL,
        role TEXT DEFAULT 'member', joined_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(room_id, user_id)
    );
    CREATE TABLE IF NOT EXISTS notes (
        id SERIAL PRIMARY KEY, etudiant_id INTEGER NOT NULL, prof_id INTEGER,
        matiere TEXT NOT NULL, note REAL NOT NULL CHECK(note>=0 AND note<=20),
        note_max REAL DEFAULT 20, coefficient INTEGER DEFAULT 1,
        semestre TEXT DEFAULT 'S1', annee_univ TEXT DEFAULT '2026-2027',
        filiere TEXT, niveau TEXT, commentaire TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT NOW(),
        FOREIGN KEY(etudiant_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS schedule (
        id SERIAL PRIMARY KEY, titre TEXT NOT NULL, prof_id INTEGER, prof_name TEXT,
        filiere TEXT NOT NULL, niveau TEXT NOT NULL, jour TEXT NOT NULL,
        heure_debut TEXT NOT NULL, heure_fin TEXT NOT NULL, salle TEXT,
        couleur TEXT DEFAULT '#00C896', created_at TIMESTAMP DEFAULT NOW(),
        FOREIGN KEY(prof_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS annonces (
        id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL,
        titre TEXT NOT NULL, contenu TEXT NOT NULL, type TEXT DEFAULT 'general',
        filiere_target TEXT, niveau_target TEXT, media_url TEXT,
        is_urgent INTEGER DEFAULT 0, is_pinned INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT NOW(),
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS documents (
        id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL,
        titre TEXT NOT NULL, fichier_url TEXT NOT NULL, type_fichier TEXT,
        taille TEXT, filiere TEXT, niveau TEXT, matiere TEXT,
        downloads INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT NOW(),
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS notifications (
        id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL, from_user_id INTEGER,
        type TEXT NOT NULL, message TEXT NOT NULL, link TEXT,
        is_read INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT NOW(),
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)
    db.commit()

    # Migrations (ajout colonnes si manquantes)
    for col_sql in [
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS client_id TEXT",
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS edited INTEGER DEFAULT 0",
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS deleted INTEGER DEFAULT 0",
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS media_type TEXT",
        "ALTER TABLE annonces ADD COLUMN IF NOT EXISTS is_pinned INTEGER DEFAULT 0",
    ]:
        try:
            c.execute(col_sql)
            db.commit()
        except Exception:
            db.rollback()

    filieres = ['BTP','INFO','DROIT','ICJ','ENVIRONNEMENT','GESTION']
    niveaux  = ['L1','L2','L3','M1','M2']
    for f in filieres:
        for n in niveaux:
            rid = f"room_{f}_{n}".lower()
            c.execute("INSERT INTO rooms (room_id,name,type,filiere,niveau) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (room_id) DO NOTHING",
                      (rid, f"{f} — {n}", 'class', f, n))
        rid = f"room_{f}_general".lower()
        c.execute("INSERT INTO rooms (room_id,name,type,filiere,niveau) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (room_id) DO NOTHING",
                  (rid, f"Groupe général {f}", 'filiere', f, None))
    c.execute("INSERT INTO rooms (room_id,name,type) VALUES (%s,%s,%s) ON CONFLICT (room_id) DO NOTHING",
              ('room_general', 'NEXORE — Général', 'global'))
    admin_pw = generate_password_hash('admin2025')
    c.execute("""INSERT INTO users (uuid,nom,prenom,email,password,role,matricule,bio)
                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (email) DO NOTHING""",
              (str(uuid.uuid4()),'IFT','Direction','direction@ift-mada.mg',
               admin_pw,'direction','DIR-2025-001','Direction Générale IFT Madagascar'))
    db.commit()
    db.close()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.',1)[1].lower() in ALLOWED_EXT

def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error':'Non connecté','redirect':'/'}), 401
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

def get_user(user_id):
    db = get_db()
    c  = db.cursor()
    c.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    u = c.fetchone()
    db.close()
    return dict(u) if u else None

def time_ago(dt):
    if not dt: return ""
    try:
        if isinstance(dt, str):
            dt = datetime.strptime(dt[:19], '%Y-%m-%d %H:%M:%S')
        diff = datetime.now() - dt.replace(tzinfo=None)
        secs = int(diff.total_seconds())
        if secs < 60:    return "À l'instant"
        if secs < 3600:  return f"Il y a {secs//60} min"
        if secs < 86400: return f"Il y a {secs//3600}h"
        if secs < 172800:return "Hier"
        return f"Il y a {diff.days} jours"
    except Exception:
        return str(dt)

def add_notification(db, user_id, type_, message, link=None, from_user_id=None):
    c = db.cursor()
    c.execute("INSERT INTO notifications (user_id,from_user_id,type,message,link) VALUES (%s,%s,%s,%s,%s)",
              (user_id, from_user_id, type_, message, link))

def save_file(file_obj, prefix='file'):
    if not file_obj or not file_obj.filename: return None, None
    if not allowed_file(file_obj.filename): return None, None
    ext = file_obj.filename.rsplit('.',1)[1].lower()
    fn  = f"{prefix}_{uuid.uuid4().hex}.{ext}"
    file_obj.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
    return f"/static/uploads/{fn}", ext

REACTION_TYPES = ['like','love','haha','wow','sad','angry']

@app.route('/')
def index():
    if 'user_id' in session: return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session: return redirect(url_for('index'))
    return render_template('app.html')

@app.route('/reset-password')
def reset_password_page():
    return render_template('reset_password.html', token=request.args.get('token',''))

@app.route('/static/uploads/<path:filename>')
def serve_upload(filename):
    return send_from_directory('static/uploads', filename)

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json(force=True)
    if not data: return jsonify({'error':'Données invalides'}), 400
    for f in ['nom','prenom','email','password','role']:
        if not data.get(f): return jsonify({'error':f'Champ manquant: {f}'}), 400
    if len(data['password']) < 6:
        return jsonify({'error':'Mot de passe trop court (min 6 caractères)'}), 400
    db = get_db(); c = db.cursor()
    c.execute("SELECT id FROM users WHERE email=%s", (data['email'].strip().lower(),))
    if c.fetchone():
        db.close(); return jsonify({'error':'Cet email est déjà utilisé'}), 409
    uid  = str(uuid.uuid4())
    year = datetime.now().year
    c.execute("SELECT COUNT(*)+1 as n FROM users")
    seq  = c.fetchone()['n']
    mat  = f"{data['role'].upper()[:3]}-{year}-{seq:04d}"
    pw   = generate_password_hash(data['password'])
    try:
        c.execute("""INSERT INTO users (uuid,nom,prenom,email,password,role,filiere,niveau,matricule)
                      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                   (uid, data['nom'].strip(), data['prenom'].strip(),
                    data['email'].strip().lower(), pw, data['role'],
                    data.get('filiere'), data.get('niveau'), mat))
        user_id = c.fetchone()['id']
        db.commit()
        add_notification(db, user_id, 'welcome', f"Bienvenue sur NEXORE Spark, {data['prenom']} ! 🎉")
        db.commit(); db.close()
        session['user_id'] = user_id; session['role'] = data['role']; session.permanent = True
        return jsonify({'success':True, 'matricule':mat})
    except Exception as e:
        db.rollback(); db.close(); return jsonify({'error':str(e)}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    data  = request.get_json(force=True)
    if not data: return jsonify({'error':'Données invalides'}), 400
    email = (data.get('email') or '').strip().lower()
    pw    = data.get('password') or ''
    if not email or not pw: return jsonify({'error':'Email et mot de passe requis'}), 400
    db = get_db(); c = db.cursor()
    c.execute("SELECT * FROM users WHERE email=%s AND is_active=1", (email,))
    user = c.fetchone()
    if not user or not check_password_hash(user['password'], pw):
        db.close(); return jsonify({'error':'Email ou mot de passe incorrect'}), 401
    c.execute("UPDATE users SET is_online=1, last_seen=NOW() WHERE id=%s", (user['id'],))
    db.commit(); db.close()
    session['user_id'] = user['id']; session['role'] = user['role']; session.permanent = True
    return jsonify({'success':True, 'role':user['role'], 'welcome':f"Bon retour {user['prenom']} ! 👋"})

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    if 'user_id' in session:
        db = get_db(); c = db.cursor()
        c.execute("UPDATE users SET is_online=0 WHERE id=%s", (session['user_id'],))
        db.commit(); db.close()
    session.clear()
    return jsonify({'success':True})

@app.route('/api/auth/forgot-password', methods=['POST'])
def forgot_password():
    data  = request.get_json(force=True)
    email = (data.get('email') or '').strip().lower()
    if not email: return jsonify({'error':'Email requis'}), 400
    db = get_db(); c = db.cursor()
    c.execute("SELECT id,nom,prenom,email FROM users WHERE email=%s AND is_active=1",(email,))
    user = c.fetchone()
    db.close()
    if not user: return jsonify({'success':True,'message':'Si cet email est enregistré, un lien vous a été envoyé.'})
    token     = serializer.dumps(email, salt='nexore-reset-password')
    base_url  = request.host_url.rstrip('/')
    reset_url = f"{base_url}/reset-password?token={token}"
    if not app.config.get('MAIL_USERNAME'):
        return jsonify({'success':True,'message':'Mode dev — lien généré.','dev_url':reset_url})
    html = f"<p>Bonjour {user['prenom']}, <a href='{reset_url}'>cliquez ici</a> pour réinitialiser votre mot de passe.</p>"
    try:
        msg = MailMessage(subject='Réinitialisation NEXORE',recipients=[email],html=html)
        mail.send(msg)
        return jsonify({'success':True,'message':f'Email envoyé à {email}.'})
    except: return jsonify({'error':"Erreur d'envoi email."}), 500

@app.route('/api/auth/reset-password', methods=['POST'])
def do_reset_password():
    data  = request.get_json(force=True)
    token = data.get('token',''); pw = data.get('password','')
    if len(pw) < 6: return jsonify({'error':'Mot de passe trop court'}), 400
    try: email = serializer.loads(token, salt='nexore-reset-password', max_age=3600)
    except SignatureExpired: return jsonify({'error':'Lien expiré.'}), 400
    except BadSignature: return jsonify({'error':'Lien invalide.'}), 400
    db = get_db(); c = db.cursor()
    c.execute("UPDATE users SET password=%s WHERE email=%s", (generate_password_hash(pw), email))
    db.commit(); db.close()
    return jsonify({'success':True,'message':'Mot de passe réinitialisé !'})

@app.route('/api/auth/me')
@login_required
def me():
    user = get_user(session['user_id'])
    if not user: return jsonify({'error':'Introuvable'}), 404
    user.pop('password',None)
    return jsonify(user)

@app.route('/api/users/profile', methods=['PUT'])
@login_required
def update_profile():
    data = request.get_json(force=True)
    if not data: return jsonify({'error':'Données invalides'}), 400
    db = get_db(); c = db.cursor()
    c.execute("""UPDATE users SET nom=%s,prenom=%s,bio=%s,website=%s,phone=%s,theme=%s,filiere=%s,niveau=%s WHERE id=%s""",
               (data.get('nom'), data.get('prenom'), data.get('bio',''),
                data.get('website',''), data.get('phone',''),
                data.get('theme','dark'), data.get('filiere'), data.get('niveau'),
                session['user_id']))
    db.commit(); db.close()
    return jsonify({'success':True})

@app.route('/api/users/avatar', methods=['POST'])
@login_required
def upload_avatar():
    if 'file' not in request.files: return jsonify({'error':'Aucun fichier'}), 400
    url, _ = save_file(request.files['file'], prefix=f"avatar_{session['user_id']}")
    if not url: return jsonify({'error':'Type non autorisé'}), 400
    db = get_db(); c = db.cursor()
    c.execute("UPDATE users SET avatar=%s WHERE id=%s", (url, session['user_id']))
    db.commit(); db.close()
    return jsonify({'success':True,'url':url})

@app.route('/api/users/cover', methods=['POST'])
@login_required
def upload_cover():
    if 'file' not in request.files: return jsonify({'error':'Aucun fichier'}), 400
    url, _ = save_file(request.files['file'], prefix=f"cover_{session['user_id']}")
    if not url: return jsonify({'error':'Type non autorisé'}), 400
    db = get_db(); c = db.cursor()
    c.execute("UPDATE users SET cover=%s WHERE id=%s", (url, session['user_id']))
    db.commit(); db.close()
    return jsonify({'success':True,'url':url})

@app.route('/api/users/change-password', methods=['POST'])
@login_required
def change_password():
    data = request.get_json(force=True)
    db = get_db(); c = db.cursor()
    c.execute("SELECT * FROM users WHERE id=%s", (session['user_id'],))
    user = c.fetchone()
    if not check_password_hash(user['password'], data.get('old_password','')):
        db.close(); return jsonify({'error':'Ancien mot de passe incorrect'}), 400
    new_pw = data.get('new_password','')
    if len(new_pw) < 6: db.close(); return jsonify({'error':'Mot de passe trop court'}), 400
    c.execute("UPDATE users SET password=%s WHERE id=%s", (generate_password_hash(new_pw), session['user_id']))
    db.commit(); db.close()
    return jsonify({'success':True})

@app.route('/api/users/theme', methods=['POST'])
@login_required
def update_theme():
    data = request.get_json(force=True)
    theme = data.get('theme','dark')
    db = get_db(); c = db.cursor()
    c.execute("UPDATE users SET theme=%s WHERE id=%s", (theme, session['user_id']))
    db.commit(); db.close()
    return jsonify({'success':True})

@app.route('/api/users/directory')
@login_required
def directory():
    db  = get_db(); c = db.cursor()
    q   = (request.args.get('q') or '').strip()
    pat = f'%{q}%'
    c.execute("""SELECT id,nom,prenom,role,filiere,niveau,avatar,is_online,matricule,bio
                 FROM users WHERE (nom ILIKE %s OR prenom ILIKE %s OR filiere ILIKE %s OR email ILIKE %s)
                   AND id != %s AND is_active=1 ORDER BY is_online DESC, nom""",
               (pat,pat,pat,pat,session['user_id']))
    users = c.fetchall()
    db.close()
    return jsonify([dict(u) for u in users])

@app.route('/api/users/<int:user_id>')
@login_required
def get_user_profile(user_id):
    db = get_db(); c = db.cursor()
    c.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    user = c.fetchone()
    if not user: db.close(); return jsonify({'error':'Introuvable'}), 404
    u = dict(user); u.pop('password',None)
    uid = session['user_id']
    c.execute("SELECT COUNT(*) as n FROM follows WHERE following_id=%s", (user_id,)); u['followers_count'] = c.fetchone()['n']
    c.execute("SELECT COUNT(*) as n FROM follows WHERE follower_id=%s", (user_id,)); u['following_count'] = c.fetchone()['n']
    c.execute("SELECT id FROM follows WHERE follower_id=%s AND following_id=%s", (uid,user_id))
    u['is_following'] = bool(c.fetchone())
    c.execute("SELECT COUNT(*) as n FROM posts WHERE user_id=%s", (user_id,)); u['posts_count'] = c.fetchone()['n']
    c.execute("""SELECT * FROM friend_requests WHERE (sender_id=%s AND receiver_id=%s) OR (sender_id=%s AND receiver_id=%s)""",
               (uid,user_id,user_id,uid))
    fr = c.fetchone()
    u['friend_status'] = fr['status'] if fr else None
    u['friend_request_sender'] = fr['sender_id'] if fr else None
    db.close()
    return jsonify(u)

@app.route('/api/users/<int:user_id>/follow', methods=['POST'])
@login_required
def toggle_follow(user_id):
    uid = session['user_id']
    if uid == user_id: return jsonify({'error':'Action impossible'}), 400
    db = get_db(); c = db.cursor()
    c.execute("SELECT id FROM follows WHERE follower_id=%s AND following_id=%s", (uid,user_id))
    ex = c.fetchone()
    if ex:
        c.execute("DELETE FROM follows WHERE follower_id=%s AND following_id=%s", (uid,user_id)); following = False
    else:
        c.execute("INSERT INTO follows (follower_id,following_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (uid,user_id))
        me = get_user(uid)
        add_notification(db, user_id, 'follow', f"{me['prenom']} {me['nom']} vous suit désormais.", from_user_id=uid)
        following = True
    db.commit()
    c.execute("SELECT COUNT(*) as n FROM follows WHERE following_id=%s", (user_id,))
    count = c.fetchone()['n']
    db.close()
    return jsonify({'success':True,'following':following,'count':count})

@app.route('/api/friends/request/<int:to_id>', methods=['POST'])
@login_required
def send_friend_request(to_id):
    uid = session['user_id']
    if uid == to_id: return jsonify({'error':'Action impossible'}), 400
    db = get_db(); c = db.cursor()
    c.execute("""SELECT * FROM friend_requests WHERE (sender_id=%s AND receiver_id=%s) OR (sender_id=%s AND receiver_id=%s)""",
               (uid,to_id,to_id,uid))
    if c.fetchone(): db.close(); return jsonify({'error':'Demande déjà existante'}), 409
    c.execute("INSERT INTO friend_requests (sender_id,receiver_id) VALUES (%s,%s)", (uid,to_id))
    me = get_user(uid)
    add_notification(db, to_id, 'friend_request', f"{me['prenom']} {me['nom']} vous a envoyé une demande d'ami.", from_user_id=uid)
    db.commit(); db.close()
    return jsonify({'success':True})

@app.route('/api/friends/accept/<int:from_id>', methods=['POST'])
@login_required
def accept_friend(from_id):
    uid = session['user_id']
    db = get_db(); c = db.cursor()
    c.execute("UPDATE friend_requests SET status='accepted' WHERE sender_id=%s AND receiver_id=%s", (from_id,uid))
    me = get_user(uid)
    add_notification(db, from_id, 'friend_accepted', f"{me['prenom']} {me['nom']} a accepté votre demande d'ami.", from_user_id=uid)
    db.commit(); db.close()
    return jsonify({'success':True})

@app.route('/api/friends/decline/<int:from_id>', methods=['POST'])
@login_required
def decline_friend(from_id):
    uid = session['user_id']
    db = get_db(); c = db.cursor()
    c.execute("DELETE FROM friend_requests WHERE sender_id=%s AND receiver_id=%s", (from_id,uid))
    db.commit(); db.close()
    return jsonify({'success':True})

@app.route('/api/friends/remove/<int:other_id>', methods=['DELETE'])
@login_required
def remove_friend(other_id):
    uid = session['user_id']
    db = get_db(); c = db.cursor()
    c.execute("DELETE FROM friend_requests WHERE (sender_id=%s AND receiver_id=%s) OR (sender_id=%s AND receiver_id=%s)",
               (uid,other_id,other_id,uid))
    db.commit(); db.close()
    return jsonify({'success':True})

@app.route('/api/friends')
@login_required
def my_friends():
    uid = session['user_id']
    db = get_db(); c = db.cursor()
    c.execute("""SELECT u.id,u.nom,u.prenom,u.avatar,u.role,u.filiere,u.is_online
                 FROM friend_requests fr
                 JOIN users u ON u.id = CASE WHEN fr.sender_id=%(uid)s THEN fr.receiver_id ELSE fr.sender_id END
                 WHERE (fr.sender_id=%(uid)s OR fr.receiver_id=%(uid)s) AND fr.status='accepted' ORDER BY u.nom""",
               {'uid':uid})
    rows = c.fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/friends/requests')
@login_required
def pending_requests():
    uid  = session['user_id']
    db = get_db(); c = db.cursor()
    c.execute("""SELECT fr.*,u.nom,u.prenom,u.avatar,u.role,u.filiere FROM friend_requests fr
                 JOIN users u ON fr.sender_id=u.id WHERE fr.receiver_id=%s AND fr.status='pending'
                 ORDER BY fr.created_at DESC""", (uid,))
    rows = c.fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/posts', methods=['GET'])
@login_required
def get_posts():
    db = get_db(); c = db.cursor(); uid = session['user_id']; user = get_user(uid)
    limit  = min(int(request.args.get('limit',30)), 100)
    offset = int(request.args.get('offset',0))
    feed   = request.args.get('feed','all')
    base = """SELECT p.*, u.nom, u.prenom, u.role, u.avatar, u.filiere as u_filiere,
               (SELECT type FROM reactions WHERE post_id=p.id AND user_id=%(uid)s) as my_reaction,
               (SELECT COUNT(*) FROM reactions WHERE post_id=p.id) as reactions_count,
               (SELECT COUNT(*) FROM comments WHERE post_id=p.id) as comments_count
        FROM posts p JOIN users u ON p.user_id=u.id """
    if feed == 'friends':
        q = base + """WHERE p.user_id IN (SELECT CASE WHEN sender_id=%(uid)s THEN receiver_id ELSE sender_id END
                        FROM friend_requests WHERE (sender_id=%(uid)s OR receiver_id=%(uid)s) AND status='accepted')
                      OR p.user_id=%(uid)s ORDER BY p.created_at DESC LIMIT %(lim)s OFFSET %(off)s"""
    elif feed == 'following':
        q = base + """WHERE p.user_id IN (SELECT following_id FROM follows WHERE follower_id=%(uid)s)
                      OR p.user_id=%(uid)s ORDER BY p.created_at DESC LIMIT %(lim)s OFFSET %(off)s"""
    elif feed == 'filiere' and user.get('filiere'):
        q = base + "WHERE p.filiere_target=%(fil)s OR p.filiere_target IS NULL ORDER BY p.created_at DESC LIMIT %(lim)s OFFSET %(off)s"
    else:
        q = base + "ORDER BY p.created_at DESC LIMIT %(lim)s OFFSET %(off)s"
    params = {'uid':uid,'lim':limit,'off':offset}
    if feed == 'filiere': params['fil'] = user.get('filiere')
    c.execute(q, params)
    posts = c.fetchall()
    db.close()
    return jsonify([{**dict(p),'time_ago':time_ago(p['created_at'])} for p in posts])

@app.route('/api/posts', methods=['POST'])
@login_required
def create_post():
    contenu = (request.form.get('contenu') or '').strip()
    if not contenu: return jsonify({'error':'Contenu requis'}), 400
    media_url = media_type = None
    if 'media' in request.files:
        f = request.files['media']
        url, ext = save_file(f, prefix='post')
        if url:
            media_url  = url
            media_type = 'video' if ext in {'mp4','mov','avi'} else ('pdf' if ext=='pdf' else 'image')
    db = get_db(); c = db.cursor()
    c.execute("""INSERT INTO posts (user_id,contenu,type,media_url,media_type,filiere_target,niveau_target,visibility)
                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
               (session['user_id'], contenu, request.form.get('type','general'),
                media_url, media_type, request.form.get('filiere_target') or None,
                request.form.get('niveau_target') or None, request.form.get('visibility','public')))
    pid = c.fetchone()['id']
    db.commit()
    user = get_user(session['user_id']); db.close()
    post_data = {'id':pid,'contenu':contenu,'type':request.form.get('type','general'),
        'media_url':media_url,'media_type':media_type,'user_id':session['user_id'],
        'nom':user['nom'],'prenom':user['prenom'],'role':user['role'],'avatar':user['avatar'],
        'u_filiere':user['filiere'],'reactions_count':0,'comments_count':0,
        'time_ago':"À l'instant",'my_reaction':None,'edited':0}
    socketio.emit('new_post', post_data, room='global_feed')
    return jsonify({'success':True,'post':post_data})

@app.route('/api/posts/<int:post_id>', methods=['PUT'])
@login_required
def edit_post(post_id):
    db = get_db(); c = db.cursor()
    c.execute("SELECT * FROM posts WHERE id=%s AND user_id=%s", (post_id, session['user_id']))
    post = c.fetchone()
    if not post: db.close(); return jsonify({'error':'Post introuvable ou non autorisé'}), 404
    data    = request.get_json(force=True)
    contenu = (data.get('contenu') or '').strip()
    if not contenu: db.close(); return jsonify({'error':'Contenu requis'}), 400
    c.execute("UPDATE posts SET contenu=%s,edited=1 WHERE id=%s", (contenu, post_id))
    db.commit(); db.close()
    socketio.emit('post_edited', {'post_id':post_id,'contenu':contenu}, room='global_feed')
    return jsonify({'success':True})

@app.route('/api/posts/<int:post_id>', methods=['DELETE'])
@login_required
def delete_post(post_id):
    db = get_db(); c = db.cursor(); user = get_user(session['user_id'])
    c.execute("SELECT * FROM posts WHERE id=%s", (post_id,))
    post = c.fetchone()
    if not post: db.close(); return jsonify({'error':'Post introuvable'}), 404
    if post['user_id'] != session['user_id'] and user['role'] not in ('direction','admin'):
        db.close(); return jsonify({'error':'Non autorisé'}), 403
    c.execute("DELETE FROM posts WHERE id=%s", (post_id,))
    db.commit(); db.close()
    socketio.emit('post_deleted', {'post_id':post_id}, room='global_feed')
    return jsonify({'success':True})

@app.route('/api/posts/<int:post_id>/react', methods=['POST'])
@login_required
def react_post(post_id):
    data      = request.get_json(force=True)
    react_type = data.get('type','like')
    if react_type not in REACTION_TYPES: return jsonify({'error':'Type invalide'}), 400
    uid = session['user_id']; db = get_db(); c = db.cursor()
    c.execute("SELECT * FROM reactions WHERE post_id=%s AND user_id=%s", (post_id,uid))
    ex = c.fetchone()
    if ex:
        if ex['type'] == react_type:
            c.execute("DELETE FROM reactions WHERE post_id=%s AND user_id=%s", (post_id,uid)); my_reaction = None
        else:
            c.execute("UPDATE reactions SET type=%s WHERE post_id=%s AND user_id=%s", (react_type,post_id,uid)); my_reaction = react_type
    else:
        c.execute("INSERT INTO reactions (post_id,user_id,type) VALUES (%s,%s,%s)", (post_id,uid,react_type)); my_reaction = react_type
        c.execute("SELECT user_id FROM posts WHERE id=%s", (post_id,))
        post_owner = c.fetchone()
        if post_owner and post_owner['user_id'] != uid:
            me = get_user(uid)
            add_notification(db, post_owner['user_id'], 'reaction', f"{me['prenom']} {me['nom']} a réagi à votre publication.", from_user_id=uid)
    db.commit()
    c.execute("SELECT type, COUNT(*) as n FROM reactions WHERE post_id=%s GROUP BY type", (post_id,))
    counts = c.fetchall()
    c.execute("SELECT COUNT(*) as n FROM reactions WHERE post_id=%s", (post_id,))
    total  = c.fetchone()['n']
    db.close()
    payload = {'post_id':post_id,'my_reaction':my_reaction,'total':total,'counts':{r['type']:r['n'] for r in counts}}
    socketio.emit('reaction_update', payload, room='global_feed')
    return jsonify({'success':True,**payload})

@app.route('/api/posts/<int:post_id>/reactions')
@login_required
def post_reactions(post_id):
    db = get_db(); c = db.cursor()
    c.execute("""SELECT r.type,u.id,u.nom,u.prenom,u.avatar FROM reactions r JOIN users u ON r.user_id=u.id
                 WHERE r.post_id=%s ORDER BY r.created_at DESC""", (post_id,))
    rows = c.fetchall()
    db.close(); return jsonify([dict(r) for r in rows])

@app.route('/api/posts/<int:post_id>/comments', methods=['GET','POST'])
@login_required
def post_comments(post_id):
    db = get_db(); c = db.cursor()
    if request.method == 'POST':
        data    = request.get_json(force=True)
        contenu = (data.get('contenu') or '').strip()
        if not contenu: db.close(); return jsonify({'error':'Commentaire vide'}), 400
        c.execute("INSERT INTO comments (post_id,user_id,contenu) VALUES (%s,%s,%s) RETURNING id", (post_id, session['user_id'], contenu))
        cid = c.fetchone()['id']
        db.commit()
        c.execute("SELECT user_id FROM posts WHERE id=%s", (post_id,))
        post_owner = c.fetchone()
        if post_owner and post_owner['user_id'] != session['user_id']:
            me = get_user(session['user_id'])
            add_notification(db, post_owner['user_id'], 'comment', f"{me['prenom']} {me['nom']} a commenté votre publication.", from_user_id=session['user_id'])
        db.commit()
        user   = get_user(session['user_id'])
        c_data = {'id':cid,'post_id':post_id,'contenu':contenu,'user_id':session['user_id'],
                  'nom':user['nom'],'prenom':user['prenom'],'avatar':user['avatar'],'time_ago':"À l'instant",'edited':0}
        socketio.emit('new_comment', c_data, room='global_feed')
        db.close(); return jsonify({'success':True,'comment':c_data})
    c.execute("""SELECT c.*,u.nom,u.prenom,u.avatar FROM comments c JOIN users u ON c.user_id=u.id
                 WHERE c.post_id=%s ORDER BY c.created_at""", (post_id,))
    coms = c.fetchall()
    db.close()
    return jsonify([{**dict(cm),'time_ago':time_ago(cm['created_at'])} for cm in coms])

@app.route('/api/comments/<int:cid>', methods=['PUT'])
@login_required
def edit_comment(cid):
    db = get_db(); c = db.cursor()
    c.execute("SELECT * FROM comments WHERE id=%s AND user_id=%s", (cid, session['user_id']))
    com = c.fetchone()
    if not com: db.close(); return jsonify({'error':'Non autorisé'}), 403
    data    = request.get_json(force=True); contenu = (data.get('contenu') or '').strip()
    if not contenu: db.close(); return jsonify({'error':'Vide'}), 400
    c.execute("UPDATE comments SET contenu=%s,edited=1 WHERE id=%s", (contenu,cid))
    db.commit(); db.close(); return jsonify({'success':True})

@app.route('/api/comments/<int:cid>', methods=['DELETE'])
@login_required
def delete_comment(cid):
    db = get_db(); c = db.cursor()
    c.execute("SELECT * FROM comments WHERE id=%s", (cid,))
    com = c.fetchone()
    if not com: db.close(); return jsonify({'error':'Introuvable'}), 404
    user = get_user(session['user_id'])
    if com['user_id'] != session['user_id'] and user['role'] not in ('direction','admin'):
        db.close(); return jsonify({'error':'Non autorisé'}), 403
    c.execute("DELETE FROM comments WHERE id=%s", (cid,))
    db.commit(); db.close(); return jsonify({'success':True})

@app.route('/api/messages/conversations')
@login_required
def conversations():
    uid  = session['user_id']; db = get_db(); c = db.cursor()
    c.execute("""
        SELECT CASE WHEN m.sender_id=%(uid)s THEN m.receiver_id ELSE m.sender_id END as other_id,
            u.nom, u.prenom, u.avatar, u.is_online, u.role, u.filiere,
            (SELECT contenu FROM messages WHERE ((sender_id=%(uid)s AND receiver_id=u.id) OR (sender_id=u.id AND receiver_id=%(uid)s))
               AND receiver_id IS NOT NULL AND deleted=0 ORDER BY created_at DESC LIMIT 1) as last_msg,
            (SELECT created_at FROM messages WHERE ((sender_id=%(uid)s AND receiver_id=u.id) OR (sender_id=u.id AND receiver_id=%(uid)s))
               AND receiver_id IS NOT NULL ORDER BY created_at DESC LIMIT 1) as last_time,
            (SELECT COUNT(*) FROM messages WHERE sender_id=u.id AND receiver_id=%(uid)s AND is_read=0 AND deleted=0) as unread
        FROM messages m JOIN users u ON u.id = CASE WHEN m.sender_id=%(uid)s THEN m.receiver_id ELSE m.sender_id END
        WHERE (m.sender_id=%(uid)s OR m.receiver_id=%(uid)s) AND m.receiver_id IS NOT NULL
        GROUP BY other_id, u.nom, u.prenom, u.avatar, u.is_online, u.role, u.filiere, u.id ORDER BY last_time DESC""", {'uid':uid})
    convs = c.fetchall()
    db.close(); return jsonify([dict(cv) for cv in convs])

@app.route('/api/messages/<int:other_id>', methods=['GET','POST'])
@login_required
def private_messages(other_id):
    uid = session['user_id']; db = get_db(); c = db.cursor()
    if request.method == 'POST':
        data      = request.get_json(force=True)
        contenu   = (data.get('contenu') or '').strip()
        client_id = data.get('client_id')
        if not contenu: db.close(); return jsonify({'error':'Message vide'}), 400
        if client_id:
            c.execute("SELECT id FROM messages WHERE client_id=%s AND sender_id=%s", (client_id, uid))
            if c.fetchone(): db.close(); return jsonify({'success':True,'duplicate':True})
        c.execute("INSERT INTO messages (client_id,sender_id,receiver_id,contenu) VALUES (%s,%s,%s,%s) RETURNING id",
                   (client_id, uid, other_id, contenu))
        mid = c.fetchone()['id']
        db.commit()
        user = get_user(uid)
        msg  = {'id':mid,'client_id':client_id,'sender_id':uid,'receiver_id':other_id,'contenu':contenu,
                'time_ago':"À l'instant",'nom':user['nom'],'prenom':user['prenom'],'avatar':user['avatar'],
                'is_read':0,'edited':0,'deleted':0}
        room = f"private_{min(uid,other_id)}_{max(uid,other_id)}"
        socketio.emit('new_message', msg, room=room)
        add_notification(db, other_id, 'message', f"💬 {user['prenom']} {user['nom']}: {contenu[:60]}", from_user_id=uid)
        db.commit(); db.close()
        return jsonify({'success':True,'message':msg})
    c.execute("UPDATE messages SET is_read=1 WHERE sender_id=%s AND receiver_id=%s", (other_id,uid))
    db.commit()
    c.execute("""SELECT m.*,u.nom,u.prenom,u.avatar FROM messages m JOIN users u ON m.sender_id=u.id
                 WHERE (m.sender_id=%s AND m.receiver_id=%s) OR (m.sender_id=%s AND m.receiver_id=%s)
                 ORDER BY m.created_at""", (uid,other_id,other_id,uid))
    msgs = c.fetchall()
    db.close()
    return jsonify([{**dict(m),'time_ago':time_ago(m['created_at'])} for m in msgs])

@app.route('/api/messages/<int:msg_id>/edit', methods=['PUT'])
@login_required
def edit_message(msg_id):
    db = get_db(); c = db.cursor()
    c.execute("SELECT * FROM messages WHERE id=%s AND sender_id=%s", (msg_id, session['user_id']))
    msg = c.fetchone()
    if not msg: db.close(); return jsonify({'error':'Non autorisé'}), 403
    data = request.get_json(force=True); contenu = (data.get('contenu') or '').strip()
    if not contenu: db.close(); return jsonify({'error':'Vide'}), 400
    c.execute("UPDATE messages SET contenu=%s,edited=1 WHERE id=%s", (contenu, msg_id))
    db.commit()
    uid   = session['user_id']
    other = msg['receiver_id'] if msg['sender_id']==uid else msg['sender_id']
    room  = f"private_{min(uid,other)}_{max(uid,other)}" if other else msg['room_id']
    socketio.emit('message_edited', {'msg_id':msg_id,'contenu':contenu}, room=room)
    db.close(); return jsonify({'success':True})

@app.route('/api/messages/<int:msg_id>/delete', methods=['DELETE'])
@login_required
def delete_message(msg_id):
    db = get_db(); c = db.cursor()
    c.execute("SELECT * FROM messages WHERE id=%s", (msg_id,))
    msg = c.fetchone()
    if not msg: db.close(); return jsonify({'error':'Introuvable'}), 404
    user = get_user(session['user_id'])
    if msg['sender_id'] != session['user_id'] and user['role'] not in ('direction','admin'):
        db.close(); return jsonify({'error':'Non autorisé'}), 403
    c.execute("UPDATE messages SET deleted=1,contenu='Message supprimé' WHERE id=%s", (msg_id,))
    db.commit()
    uid   = session['user_id']
    other = msg['receiver_id'] if msg['sender_id']==uid else msg['sender_id']
    room  = f"private_{min(uid,other)}_{max(uid,other)}" if other else msg['room_id']
    socketio.emit('message_deleted', {'msg_id':msg_id}, room=room)
    db.close(); return jsonify({'success':True})

@app.route('/api/messages/room/<room_id>', methods=['GET','POST'])
@login_required
def room_messages(room_id):
    uid = session['user_id']; db = get_db(); c = db.cursor()
    if request.method == 'POST':
        data = request.get_json(force=True); contenu = (data.get('contenu') or '').strip()
        client_id = data.get('client_id')
        if not contenu: db.close(); return jsonify({'error':'Message vide'}), 400
        if client_id:
            c.execute("SELECT id FROM messages WHERE client_id=%s AND sender_id=%s", (client_id, uid))
            if c.fetchone(): db.close(); return jsonify({'success':True,'duplicate':True})
        c.execute("INSERT INTO messages (client_id,sender_id,room_id,contenu) VALUES (%s,%s,%s,%s) RETURNING id",
                   (client_id, uid, room_id, contenu))
        mid = c.fetchone()['id']
        db.commit()
        user = get_user(uid)
        msg  = {'id':mid,'client_id':client_id,'sender_id':uid,'room_id':room_id,'contenu':contenu,
                'time_ago':"À l'instant",'nom':user['nom'],'prenom':user['prenom'],'avatar':user['avatar'],'edited':0,'deleted':0}
        socketio.emit('new_message', msg, room=room_id)
        db.close(); return jsonify({'success':True,'message':msg})
    c.execute("""SELECT m.*,u.nom,u.prenom,u.avatar FROM messages m JOIN users u ON m.sender_id=u.id
                 WHERE m.room_id=%s AND m.deleted=0 ORDER BY m.created_at DESC LIMIT 100""",
              (room_id,))
    msgs = c.fetchall()
    db.close()
    return jsonify([{**dict(m),'time_ago':time_ago(m['created_at'])} for m in reversed(msgs)])

@app.route('/api/messages/upload', methods=['POST'])
@login_required
def upload_message_media():
    if 'file' not in request.files: return jsonify({'error':'Aucun fichier'}), 400
    url, ext = save_file(request.files['file'], prefix='msg')
    if not url: return jsonify({'error':'Type non autorisé'}), 400
    media_type = 'image' if ext in {'png','jpg','jpeg','gif','webp'} else \
                 'video' if ext in {'mp4','mov','avi'} else 'file'
    return jsonify({'success':True,'url':url,'media_type':media_type})

@app.route('/api/messages/unread-count')
@login_required
def unread_count():
    db = get_db(); c = db.cursor()
    c.execute("SELECT COUNT(*) as n FROM messages WHERE receiver_id=%s AND is_read=0 AND deleted=0",
               (session['user_id'],))
    count = c.fetchone()['n']
    db.close(); return jsonify({'count':count})

@app.route('/api/groups', methods=['GET','POST'])
@login_required
def groups():
    db = get_db(); c = db.cursor()
    if request.method == 'POST':
        data = request.get_json(force=True); name = (data.get('name') or '').strip()
        if not name: db.close(); return jsonify({'error':'Nom requis'}), 400
        rid = f"group_{uuid.uuid4().hex[:12]}"
        c.execute("INSERT INTO rooms (room_id,name,type,description,creator_id) VALUES (%s,%s,%s,%s,%s)",
                   (rid, name, 'group', data.get('description',''), session['user_id']))
        c.execute("INSERT INTO room_members (room_id,user_id,role) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                   (rid, session['user_id'], 'admin'))
        db.commit(); db.close(); return jsonify({'success':True,'room_id':rid})
    c.execute("""SELECT r.*, rm.role as my_role FROM rooms r LEFT JOIN room_members rm
                 ON r.room_id=rm.room_id AND rm.user_id=%s
                 WHERE r.type='group' ORDER BY r.created_at DESC""", (session['user_id'],))
    rows = c.fetchall()
    db.close(); return jsonify([dict(r) for r in rows])

@app.route('/api/groups/<room_id>/join', methods=['POST'])
@login_required
def join_group(room_id):
    db = get_db(); c = db.cursor()
    c.execute("INSERT INTO room_members (room_id,user_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (room_id, session['user_id']))
    db.commit(); db.close(); return jsonify({'success':True})

@app.route('/api/rooms')
@login_required
def get_rooms():
    db = get_db(); c = db.cursor(); user = get_user(session['user_id'])
    if user['role'] == 'etudiant':
        c.execute("""SELECT * FROM rooms WHERE type='global'
                     OR (type='class' AND filiere=%s AND niveau=%s)
                     OR (type='filiere' AND filiere=%s) ORDER BY type, name""",
                   (user['filiere'], user['niveau'], user['filiere']))
    else:
        c.execute("SELECT * FROM rooms WHERE type IN ('class','filiere','global') ORDER BY type,name")
    rows = c.fetchall()
    db.close(); return jsonify([dict(r) for r in rows])

@app.route('/api/notes', methods=['GET','POST'])
@login_required
def notes():
    db = get_db(); c = db.cursor(); user = get_user(session['user_id'])
    if request.method == 'POST':
        if user['role'] == 'etudiant': db.close(); return jsonify({'error':'Accès refusé'}), 403
        data = request.get_json(force=True); note_val = data.get('note')
        if note_val is None or not (0 <= float(note_val) <= 20):
            db.close(); return jsonify({'error':'Note invalide (0-20)'}), 400
        c.execute("""INSERT INTO notes (etudiant_id,prof_id,matiere,note,coefficient,semestre,annee_univ,filiere,niveau,commentaire)
                      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                   (data['etudiant_id'], session['user_id'], data['matiere'], float(data['note']),
                    int(data.get('coefficient',1)), data.get('semestre','S1'), data.get('annee_univ','2026-2027'),
                    data.get('filiere'), data.get('niveau'), data.get('commentaire','')))
        db.commit()
        add_notification(db, int(data['etudiant_id']), 'note', f"Nouvelle note en {data['matiere']} : {data['note']}/20", from_user_id=session['user_id'])
        db.commit(); db.close(); return jsonify({'success':True})
    if user['role'] == 'etudiant':
        c.execute("SELECT * FROM notes WHERE etudiant_id=%s ORDER BY matiere", (session['user_id'],))
        ns = c.fetchall()
    else:
        fil = request.args.get('filiere'); niv = request.args.get('niveau'); eid = request.args.get('etudiant_id')
        q   = "SELECT n.*,u.nom,u.prenom FROM notes n JOIN users u ON n.etudiant_id=u.id WHERE 1=1"; prm = []
        if fil: q += " AND n.filiere=%s"; prm.append(fil)
        if niv: q += " AND n.niveau=%s"; prm.append(niv)
        if eid: q += " AND n.etudiant_id=%s"; prm.append(eid)
        c.execute(q + " ORDER BY u.nom,n.matiere", prm)
        ns = c.fetchall()
    db.close(); return jsonify([dict(n) for n in ns])

@app.route('/api/schedule', methods=['GET','POST'])
@login_required
def schedule():
    db = get_db(); c = db.cursor(); user = get_user(session['user_id'])
    if request.method == 'POST':
        data = request.get_json(force=True)
        if not data.get('titre'): db.close(); return jsonify({'error':'Titre requis'}), 400
        filiere = data.get('filiere') or user.get('filiere') or ''
        niveau  = data.get('niveau')  or user.get('niveau')  or ''
        c.execute("INSERT INTO schedule (titre,prof_id,prof_name,filiere,niveau,jour,heure_debut,heure_fin,salle,couleur) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                   (data['titre'], session['user_id'], f"{user['prenom']} {user['nom']}",
                    filiere, niveau, data.get('jour','Lundi'),
                    data.get('heure_debut','08:00'), data.get('heure_fin','09:00'),
                    data.get('salle'), data.get('couleur','#00C896')))
        db.commit()
        socketio.emit('schedule_update', data, room='global_feed')
        db.close(); return jsonify({'success':True})
    fil = request.args.get('filiere') or (user.get('filiere') if user['role']=='etudiant' else None)
    niv = request.args.get('niveau')  or (user.get('niveau')  if user['role']=='etudiant' else None)
    uid_filter = request.args.get('user_id')
    q = "SELECT * FROM schedule WHERE 1=1"; prm = []
    if fil: q += " AND filiere=%s"; prm.append(fil)
    if niv: q += " AND niveau=%s"; prm.append(niv)
    if uid_filter: q += " AND prof_id=%s"; prm.append(uid_filter)
    c.execute(q + " ORDER BY jour,heure_debut", prm)
    rows = c.fetchall()
    db.close(); return jsonify([dict(r) for r in rows])

@app.route('/api/schedule/<int:sid>', methods=['PUT'])
@login_required
def edit_schedule(sid):
    uid = session['user_id']; user = get_user(uid); db = get_db(); c = db.cursor()
    c.execute("SELECT * FROM schedule WHERE id=%s", (sid,))
    row = c.fetchone()
    if not row: db.close(); return jsonify({'error':'Introuvable'}), 404
    if row['prof_id'] != uid and user['role'] not in ('direction','admin'):
        db.close(); return jsonify({'error':'Non autorisé'}), 403
    data = request.get_json(force=True)
    c.execute("UPDATE schedule SET titre=%s,jour=%s,heure_debut=%s,heure_fin=%s,salle=%s,couleur=%s,filiere=%s,niveau=%s WHERE id=%s",
               (data.get('titre',row['titre']),data.get('jour',row['jour']),
                data.get('heure_debut',row['heure_debut']),data.get('heure_fin',row['heure_fin']),
                data.get('salle',row['salle']),data.get('couleur',row['couleur']),
                data.get('filiere',row['filiere']),data.get('niveau',row['niveau']),sid))
    db.commit(); db.close(); return jsonify({'success':True})

@app.route('/api/schedule/<int:sid>', methods=['DELETE'])
@login_required
def delete_schedule(sid):
    uid = session['user_id']; user = get_user(uid); db = get_db(); c = db.cursor()
    c.execute("SELECT * FROM schedule WHERE id=%s", (sid,))
    row = c.fetchone()
    if not row: db.close(); return jsonify({'error':'Introuvable'}), 404
    if row['prof_id'] != uid and user['role'] not in ('direction','admin'):
        db.close(); return jsonify({'error':'Non autorisé'}), 403
    c.execute("DELETE FROM schedule WHERE id=%s", (sid,)); db.commit(); db.close()
    return jsonify({'success':True})

@app.route('/api/annonces', methods=['GET','POST'])
@login_required
def annonces():
    db = get_db(); c = db.cursor(); user = get_user(session['user_id'])
    if request.method == 'POST':
        if user['role'] == 'etudiant': db.close(); return jsonify({'error':'Accès refusé'}), 403
        titre = (request.form.get('titre') or '').strip(); contenu = (request.form.get('contenu') or '').strip()
        if not titre or not contenu: db.close(); return jsonify({'error':'Titre et contenu requis'}), 400
        media_url = None
        if 'media' in request.files:
            url, _ = save_file(request.files['media'], prefix='ann'); media_url = url
        c.execute("""INSERT INTO annonces (user_id,titre,contenu,type,filiere_target,niveau_target,media_url,is_urgent,is_pinned)
                      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                   (session['user_id'], titre, contenu, request.form.get('type','general'),
                    request.form.get('filiere_target') or None, request.form.get('niveau_target') or None,
                    media_url, int(request.form.get('is_urgent',0)), int(request.form.get('is_pinned',0))))
        db.commit()
        socketio.emit('new_annonce', {'titre':titre,'contenu':contenu[:120],'is_urgent':int(request.form.get('is_urgent',0))}, room='global_feed')
        db.close(); return jsonify({'success':True})
    c.execute("""SELECT a.*,u.nom,u.prenom,u.role,u.avatar FROM annonces a
                 JOIN users u ON a.user_id=u.id ORDER BY a.is_pinned DESC, a.is_urgent DESC, a.created_at DESC""")
    rows = c.fetchall()
    db.close(); return jsonify([{**dict(r),'time_ago':time_ago(r['created_at'])} for r in rows])

@app.route('/api/annonces/<int:ann_id>', methods=['DELETE'])
@login_required
def delete_annonce(ann_id):
    user = get_user(session['user_id'])
    if user['role'] == 'etudiant': return jsonify({'error':'Accès refusé'}), 403
    db = get_db(); c = db.cursor()
    c.execute("SELECT * FROM annonces WHERE id=%s", (ann_id,))
    ann = c.fetchone()
    if not ann: db.close(); return jsonify({'error':'Introuvable'}), 404
    if ann['user_id'] != session['user_id'] and user['role'] not in ('direction','admin'):
        db.close(); return jsonify({'error':'Non autorisé'}), 403
    c.execute("DELETE FROM annonces WHERE id=%s", (ann_id,)); db.commit(); db.close()
    return jsonify({'success':True})

@app.route('/api/documents', methods=['GET','POST'])
@login_required
def documents():
    db = get_db(); c = db.cursor(); user = get_user(session['user_id'])
    if request.method == 'POST':
        if user['role'] == 'etudiant': db.close(); return jsonify({'error':'Accès refusé'}), 403
        if 'fichier' not in request.files: db.close(); return jsonify({'error':'Aucun fichier'}), 400
        f = request.files['fichier']; url, ext = save_file(f, prefix='doc')
        if not url: db.close(); return jsonify({'error':'Fichier non autorisé'}), 400
        path = os.path.join(app.config['UPLOAD_FOLDER'], url.split('/')[-1])
        size = f"{os.path.getsize(path)//1024} KB" if os.path.exists(path) else "?"
        c.execute("""INSERT INTO documents (user_id,titre,fichier_url,type_fichier,taille,filiere,niveau,matiere)
                      VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                   (session['user_id'], request.form.get('titre') or f.filename,
                    url, (ext or '').upper(), size, request.form.get('filiere') or None,
                    request.form.get('niveau') or None, request.form.get('matiere') or None))
        db.commit(); db.close(); return jsonify({'success':True})
    fil = request.args.get('filiere'); niv = request.args.get('niveau')
    q   = "SELECT d.*,u.nom,u.prenom FROM documents d JOIN users u ON d.user_id=u.id WHERE 1=1"; prm = []
    if fil: q += " AND d.filiere=%s"; prm.append(fil)
    if niv: q += " AND d.niveau=%s"; prm.append(niv)
    c.execute(q + " ORDER BY d.created_at DESC", prm)
    rows = c.fetchall()
    db.close(); return jsonify([{**dict(r),'time_ago':time_ago(r['created_at'])} for r in rows])

@app.route('/api/notifications')
@login_required
def get_notifications():
    db = get_db(); c = db.cursor()
    c.execute("""SELECT n.*,u.nom as from_nom,u.prenom as from_prenom,u.avatar as from_avatar
                 FROM notifications n LEFT JOIN users u ON n.from_user_id=u.id
                 WHERE n.user_id=%s ORDER BY n.created_at DESC LIMIT 50""",
              (session['user_id'],))
    ns = c.fetchall()
    db.close(); return jsonify([{**dict(n),'time_ago':time_ago(n['created_at'])} for n in ns])

@app.route('/api/notifications/read', methods=['POST'])
@login_required
def mark_notifs_read():
    db = get_db(); c = db.cursor()
    c.execute("UPDATE notifications SET is_read=1 WHERE user_id=%s", (session['user_id'],))
    db.commit(); db.close(); return jsonify({'success':True})

@app.route('/api/notifications/unread-count')
@login_required
def notif_unread():
    db = get_db(); c = db.cursor()
    c.execute("SELECT COUNT(*) as n FROM notifications WHERE user_id=%s AND is_read=0",
               (session['user_id'],))
    count = c.fetchone()['n']
    db.close(); return jsonify({'count':count})

@app.route('/api/users/online')
@login_required
def online_users():
    db = get_db(); c = db.cursor()
    c.execute(
        "SELECT id,nom,prenom,role,filiere,niveau,avatar,is_online,last_seen FROM users WHERE is_online=1 AND id!=%s AND is_active=1 ORDER BY nom",
        (session['user_id'],))
    rows = c.fetchall()
    db.close(); return jsonify([dict(r) for r in rows])

@app.route('/api/search')
@login_required
def search():
    q = (request.args.get('q') or '').strip(); type_ = request.args.get('type','all')
    if not q: return jsonify({'users':[],'posts':[],'groups':[]})
    pat = f'%{q}%'; db = get_db(); c = db.cursor(); result = {}
    if type_ in ('all','users'):
        c.execute("""SELECT id,nom,prenom,role,filiere,niveau,avatar,is_online FROM users
                     WHERE (nom ILIKE %s OR prenom ILIKE %s OR filiere ILIKE %s) AND id!=%s AND is_active=1 LIMIT 10""",
                   (pat,pat,pat,session['user_id']))
        result['users'] = [dict(u) for u in c.fetchall()]
    if type_ in ('all','posts'):
        c.execute("""SELECT p.*,u.nom,u.prenom,u.avatar FROM posts p JOIN users u ON p.user_id=u.id
                     WHERE p.contenu ILIKE %s ORDER BY p.created_at DESC LIMIT 10""", (pat,))
        result['posts'] = [{**dict(p),'time_ago':time_ago(p['created_at'])} for p in c.fetchall()]
    if type_ in ('all','groups'):
        c.execute("SELECT * FROM rooms WHERE name ILIKE %s AND type='group' LIMIT 10", (pat,))
        result['groups'] = [dict(g) for g in c.fetchall()]
    db.close(); return jsonify(result)

@app.route('/api/stats')
@login_required
def stats():
    user = get_user(session['user_id'])
    if user['role'] not in ('direction','admin'): return jsonify({'error':'Accès refusé'}), 403
    db = get_db(); c = db.cursor()
    def q1(sql, params=()):
        c.execute(sql, params); return c.fetchone()['n']
    data = {
        'total_etudiants': q1("SELECT COUNT(*) as n FROM users WHERE role='etudiant' AND is_active=1"),
        'total_profs':     q1("SELECT COUNT(*) as n FROM users WHERE role='professeur' AND is_active=1"),
        'total_posts':     q1("SELECT COUNT(*) as n FROM posts"),
        'total_messages':  q1("SELECT COUNT(*) as n FROM messages WHERE deleted=0"),
        'total_docs':      q1("SELECT COUNT(*) as n FROM documents"),
        'online_now':      q1("SELECT COUNT(*) as n FROM users WHERE is_online=1"),
        'total_annonces':  q1("SELECT COUNT(*) as n FROM annonces"),
    }
    c.execute("SELECT filiere, COUNT(*) as n FROM users WHERE role='etudiant' AND filiere IS NOT NULL GROUP BY filiere")
    data['by_filiere'] = [dict(r) for r in c.fetchall()]
    db.close(); return jsonify(data)

@socketio.on('connect')
def on_connect():
    if 'user_id' in session:
        join_room('global_feed')
        db = get_db(); c = db.cursor()
        c.execute("UPDATE users SET is_online=1 WHERE id=%s", (session['user_id'],))
        db.commit()
        c.execute("SELECT id,nom,prenom FROM users WHERE id=%s", (session['user_id'],))
        user = c.fetchone()
        db.close()
        if user: emit('user_online', {'user_id':user['id'],'nom':user['nom'],'prenom':user['prenom']}, room='global_feed')

@socketio.on('disconnect')
def on_disconnect():
    if 'user_id' in session:
        db = get_db(); c = db.cursor()
        c.execute("UPDATE users SET is_online=0, last_seen=NOW() WHERE id=%s", (session['user_id'],))
        db.commit(); db.close()

@socketio.on('join_room')
def on_join(data):
    room = data.get('room')
    if room: join_room(room)

@socketio.on('leave_room')
def on_leave(data):
    room = data.get('room')
    if room: leave_room(room)

@socketio.on('join_private')
def join_private(data):
    other_id = data.get('other_id')
    if other_id and 'user_id' in session:
        room = f"private_{min(session['user_id'],other_id)}_{max(session['user_id'],other_id)}"
        join_room(room)

@socketio.on('typing')
def on_typing(data):
    if 'user_id' in session:
        emit('user_typing', {'user_id':session['user_id'],'nom':data.get('nom','')},
             room=data.get('room'), include_self=False)

@socketio.on('stop_typing')
def on_stop_typing(data):
    if 'user_id' in session:
        emit('user_stop_typing', {'user_id':session['user_id']}, room=data.get('room'), include_self=False)

os.makedirs('static/uploads', exist_ok=True)
init_db()
if __name__ == '__main__':
    os.makedirs('static/uploads', exist_ok=True)
    init_db()
    print("""
╔══════════════════════════════════════════════════════╗
║   NEXORE Spark V3.0 — IFT Madagascar (PostgreSQL)  ║
║   http://localhost:5000                            ║
║   Admin: direction@ift-mada.mg / admin2025         ║
╚══════════════════════════════════════════════════════╝""")
socketio.run(
    app,
    host="0.0.0.0",
    port=int(os.environ.get("PORT", 5000)),
    debug=False
)
