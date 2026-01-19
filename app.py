from flask import Flask, render_template, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
from functools import wraps
import secrets
from werkzeug.utils import secure_filename
import uuid

app = Flask(__name__)

# Generate a secure secret key
if os.environ.get('SECRET_KEY'):
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
else:
    app.config['SECRET_KEY'] = secrets.token_hex(32)

# Database configuration
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(basedir, "chat.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# File upload configuration
UPLOAD_FOLDER = os.path.join(basedir, 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# Create upload folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

db = SQLAlchemy(app)

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    messages = db.relationship('Message', backref='author', lazy=True)
    rooms = db.relationship('Room', secondary='room_member', backref='members')
    contacts = db.relationship('Contact', foreign_keys='Contact.user_id', backref='user', lazy=True)

    def __repr__(self):
        return f'<User {self.username}>'

# Association table for many-to-many relationship between Room and User
room_member = db.Table('room_member',
    db.Column('room_id', db.Integer, db.ForeignKey('room.id'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('joined_at', db.DateTime, default=datetime.utcnow)
)

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    type = db.Column(db.String(20), default='public')  # 'public' or 'private'
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    messages = db.relationship('Message', backref='room', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Room {self.name}>'

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'member_count': len(self.members),
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }

class Contact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    contact_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    contact_user = db.relationship('User', foreign_keys='Contact.contact_user_id', backref='contacted_by')
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=True)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Contact {self.user_id} -> {self.contact_user_id}>'

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(255), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Message {self.id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'content': self.content,
            'image_url': self.image_url,
            'username': self.author.username,
            'user_id': self.user_id,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Login required'}), 401
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        return render_template('chat.html')
    return render_template('login.html')

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Username already exists'}), 400

    user = User(username=username, password=password)
    db.session.add(user)
    db.session.commit()

    session['user_id'] = user.id
    session['username'] = user.username
    return jsonify({'success': True, 'message': 'User registered successfully'})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    user = User.query.filter_by(username=username).first()

    if not user or user.password != password:
        return jsonify({'error': 'Invalid username or password'}), 401

    session['user_id'] = user.id
    session['username'] = user.username
    return jsonify({'success': True, 'message': 'Logged in successfully'})

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out successfully'})

# Public Room Management
@app.route('/api/rooms', methods=['GET'])
@login_required
def get_rooms():
    """Get all rooms the user is member of"""
    user = User.query.get(session['user_id'])
    return jsonify([room.to_dict() for room in user.rooms])

@app.route('/api/rooms/public', methods=['GET'])
@login_required
def get_public_rooms():
    """Get all public rooms"""
    public_rooms = Room.query.filter_by(type='public').all()
    return jsonify([room.to_dict() for room in public_rooms])

@app.route('/api/rooms', methods=['POST'])
@login_required
def create_room():
    """Create a new room"""
    data = request.get_json()
    room_name = data.get('name', '').strip()
    room_type = data.get('type', 'private')

    if not room_name:
        return jsonify({'error': 'Room name required'}), 400

    # Check if room already exists
    existing_room = Room.query.filter_by(name=room_name).first()
    if existing_room:
        return jsonify({'error': 'Room already exists'}), 400

    room = Room(name=room_name, type=room_type, creator_id=session['user_id'])
    db.session.add(room)
    db.session.flush()
    
    # Add creator to room members
    user = User.query.get(session['user_id'])
    user.rooms.append(room)
    db.session.commit()

    return jsonify({'success': True, 'room': room.to_dict()})

@app.route('/api/rooms/<int:room_id>/join', methods=['POST'])
@login_required
def join_room(room_id):
    """Join an existing room"""
    room = Room.query.get_or_404(room_id)
    user = User.query.get(session['user_id'])

    if room in user.rooms:
        return jsonify({'error': 'Already member of this room'}), 400

    user.rooms.append(room)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Joined room successfully'})

@app.route('/api/rooms/<int:room_id>/messages', methods=['GET'])
@login_required
def get_room_messages(room_id):
    """Get messages from a specific room"""
    room = Room.query.get_or_404(room_id)
    user = User.query.get(session['user_id'])

    # Check if user is member of room
    if room not in user.rooms:
        return jsonify({'error': 'Not member of this room'}), 403

    messages = Message.query.filter_by(room_id=room_id).order_by(Message.created_at).all()
    return jsonify([msg.to_dict() for msg in messages])

@app.route('/api/rooms/<int:room_id>/messages', methods=['POST'])
@login_required
def send_room_message(room_id):
    """Send message to a room"""
    room = Room.query.get_or_404(room_id)
    user = User.query.get(session['user_id'])

    # Check if user is member of room
    if room not in user.rooms:
        return jsonify({'error': 'Not member of this room'}), 403

    content = request.form.get('content', '').strip()
    image_file = request.files.get('image')
    image_url = None

    if not content and not image_file:
        return jsonify({'error': 'Message content or image required'}), 400

    # Handle image upload if provided
    if image_file:
        if not allowed_file(image_file.filename):
            return jsonify({'error': 'Invalid file type. Allowed: PNG, JPG, JPEG, GIF, WebP, BMP'}), 400

        image_file.seek(0, os.SEEK_END)
        file_size = image_file.tell()
        image_file.seek(0)

        if file_size > MAX_FILE_SIZE:
            return jsonify({'error': 'File size exceeds 10MB limit'}), 400

        filename = secure_filename(image_file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
        image_url = f"/static/uploads/{unique_filename}"

    message = Message(content=content, image_url=image_url, user_id=session['user_id'], room_id=room_id)
    db.session.add(message)
    db.session.commit()

    return jsonify({'success': True, 'message': message.to_dict()})

# Contact Management
@app.route('/api/contacts', methods=['GET'])
@login_required
def get_contacts():
    """Get user's contacts"""
    contacts = Contact.query.filter_by(user_id=session['user_id']).all()
    result = []
    for contact in contacts:
        result.append({
            'id': contact.id,
            'username': contact.contact_user.username,
            'user_id': contact.contact_user_id,
            'room_id': contact.room_id,
            'added_at': contact.added_at.strftime('%Y-%m-%d %H:%M:%S')
        })
    return jsonify(result)

@app.route('/api/contacts/search', methods=['GET'])
@login_required
def search_contact():
    """Search for a user by username"""
    username = request.args.get('username', '').strip()

    if not username:
        return jsonify({'error': 'Username required'}), 400

    user = User.query.filter_by(username=username).first()

    if not user:
        return jsonify({'error': 'User not found'}), 404

    if user.id == session['user_id']:
        return jsonify({'error': 'Cannot add yourself'}), 400

    return jsonify({
        'id': user.id,
        'username': user.username,
        'created_at': user.created_at.strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/api/contacts', methods=['POST'])
@login_required
def add_contact():
    """Add a new contact"""
    data = request.get_json()
    contact_username = data.get('username', '').strip()

    if not contact_username:
        return jsonify({'error': 'Username required'}), 400

    contact_user = User.query.filter_by(username=contact_username).first()

    if not contact_user:
        return jsonify({'error': 'User not found'}), 404

    if contact_user.id == session['user_id']:
        return jsonify({'error': 'Cannot add yourself'}), 400

    # Check if already a contact
    existing_contact = Contact.query.filter_by(
        user_id=session['user_id'],
        contact_user_id=contact_user.id
    ).first()

    if existing_contact:
        return jsonify({'error': 'Already in contacts'}), 400

    # Create private room for this contact
    room_name = f"{session['username']}-{contact_username}"
    existing_room = Room.query.filter_by(name=room_name).first()
    
    if not existing_room:
        room = Room(name=room_name, type='private', creator_id=session['user_id'])
        db.session.add(room)
        db.session.flush()
        
        user = User.query.get(session['user_id'])
        contact_user_obj = User.query.get(contact_user.id)
        user.rooms.append(room)
        contact_user_obj.rooms.append(room)
    else:
        room = existing_room
        user = User.query.get(session['user_id'])
        if room not in user.rooms:
            user.rooms.append(room)

    contact = Contact(user_id=session['user_id'], contact_user_id=contact_user.id, room_id=room.id)
    db.session.add(contact)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Added {contact_username} to contacts',
        'contact': {
            'id': contact.id,
            'username': contact_user.username,
            'user_id': contact_user.id,
            'room_id': room.id
        }
    })

# Initialize Public Room
@app.before_request
def init_public_room():
    """Create public room on first run"""
    try:
        if request.endpoint and not request.endpoint.startswith('static'):
            public_room = Room.query.filter_by(name='Public Room', type='public').first()
            if not public_room:
                admin_user = User.query.first()
                if admin_user:
                    public_room = Room(name='Public Room', type='public', creator_id=admin_user.id)
                    db.session.add(public_room)
                    db.session.commit()
    except:
        pass  # Ignore errors during init

@app.route('/api/user', methods=['GET'])
def get_user():
    if 'user_id' in session:
        return jsonify({
            'user_id': session['user_id'],
            'username': session['username']
        })
    return jsonify({'error': 'Not logged in'}), 401

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)
