from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'  # Замените на случайный ключ для продакшена
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['UPLOAD_FOLDER'] = 'uploads'
db = SQLAlchemy(app)

# Создайте папку uploads, если нет
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Модели БД
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'student' or 'teacher'
    approved = db.Column(db.Boolean, default=False)

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    description = db.Column(db.Text)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'))
    intending = db.Column(db.Boolean, default=False)  # Планирует ли студент
    present = db.Column(db.Boolean, default=False)   # Отметка присутствия учителем

class Content(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'))
    content = db.Column(db.Text)      # Текст конспекта
    description = db.Column(db.Text)

class ContentPhotos(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content_id = db.Column(db.Integer, db.ForeignKey('content.id'))
    photo_path = db.Column(db.Text)   # Путь к фото

class Access(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content_id = db.Column(db.Integer, db.ForeignKey('content.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

# Создание БД и тестового преподавателя
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='teacher').first():
        teacher = User(username='teacher', password=generate_password_hash('password'), role='teacher', approved=True)
        db.session.add(teacher)
        db.session.commit()

# Главная страница
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))

# Логин
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password) and user.approved:
            session['user_id'] = user.id
            session['role'] = user.role
            return redirect(url_for('dashboard'))
        flash('Неверные данные или аккаунт не подтвержден')
    return render_template('login.html')

# Регистрация (только для студентов)
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        if User.query.filter_by(username=username).first():
            flash('Пользователь существует')
        else:
            new_user = User(username=username, password=password, role='student', approved=False)
            db.session.add(new_user)
            db.session.commit()
            flash('Регистрация успешна. Ожидайте подтверждения.')
            return redirect(url_for('login'))
    return render_template('register.html')

# Выход
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Дашборд
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    events = Event.query.order_by(Event.date).all()
    return render_template('dashboard.html', events=events)

# Подтверждение регистраций (только teacher)
@app.route('/approve_users')
def approve_users():
    if session.get('role') != 'teacher':
        return redirect(url_for('dashboard'))
    pending = User.query.filter_by(approved=False).all()
    return render_template('approve_users.html', pending=pending)

@app.route('/approve/<int:user_id>')
def approve(user_id):
    if session.get('role') != 'teacher':
        return redirect(url_for('dashboard'))
    user = User.query.get(user_id)
    if not user:
        flash('Пользователь не найден')
        return redirect(url_for('approve_users'))
    user.approved = True
    db.session.commit()
    return redirect(url_for('approve_users'))

@app.route('/reject/<int:user_id>')
def reject(user_id):
    if session.get('role') != 'teacher':
        return redirect(url_for('dashboard'))
    user = User.query.get(user_id)
    if not user:
        flash('Пользователь не найден')
        return redirect(url_for('approve_users'))
    db.session.delete(user)
    db.session.commit()
    return redirect(url_for('approve_users'))

# Добавление события (teacher)
@app.route('/add_event', methods=['GET', 'POST'])
def add_event():
    if session.get('role') != 'teacher':
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        title = request.form['title']
        date_str = request.form['date']
        description = request.form['description']
        try:
            date = datetime.strptime(date_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash('Неверный формат даты')
            return redirect(url_for('add_event'))
        new_event = Event(title=title, date=date, description=description)
        db.session.add(new_event)
        db.session.commit()
        flash('Мероприятие успешно добавлено')
        return redirect(url_for('dashboard'))
    return render_template('add_event.html')

# Отметка намерения (student)
@app.route('/intend/<int:event_id>/<int:intend>')
def intend(event_id, intend):
    if session.get('role') != 'student':
        return redirect(url_for('dashboard'))
    event = Event.query.get(event_id)
    if not event:
        flash('Мероприятие не найдено')
        return redirect(url_for('dashboard'))
    att = Attendance.query.filter_by(user_id=session['user_id'], event_id=event_id).first()
    if not att:
        att = Attendance(user_id=session['user_id'], event_id=event_id)
        db.session.add(att)
    att.intending = bool(intend)
    db.session.commit()
    return redirect(url_for('dashboard'))

# Отметка присутствия (teacher)
@app.route('/mark_presence/<int:event_id>')
def mark_presence(event_id):
    if session.get('role') != 'teacher':
        return redirect(url_for('dashboard'))
    event = Event.query.get(event_id)
    if not event:
        flash('Мероприятие не найдено')
        return redirect(url_for('dashboard'))
    students = User.query.filter_by(role='student', approved=True).all()
    attendances = {s.id: Attendance.query.filter_by(user_id=s.id, event_id=event_id).first() for s in students}
    return render_template('mark_presence.html', event_id=event_id, students=students, attendances=attendances)

@app.route('/set_presence/<int:event_id>/<int:user_id>/<int:present>')
def set_presence(event_id, user_id, present):
    if session.get('role') != 'teacher':
        return redirect(url_for('dashboard'))
    event = Event.query.get(event_id)
    if not event:
        flash('Мероприятие не найдено')
        return redirect(url_for('dashboard'))
    att = Attendance.query.filter_by(user_id=user_id, event_id=event_id).first()
    if not att:
        att = Attendance(user_id=user_id, event_id=event_id)
        db.session.add(att)
    att.present = bool(present)
    db.session.commit()
    return redirect(url_for('mark_presence', event_id=event_id))

# Добавление контента (teacher)
@app.route('/add_content/<int:event_id>', methods=['GET', 'POST'])
def add_content(event_id):
    if session.get('role') != 'teacher':
        return redirect(url_for('dashboard'))
    event = Event.query.get(event_id)
    if not event:
        flash('Мероприятие не найдено')
        return redirect(url_for('dashboard'))
    students = User.query.filter_by(role='student', approved=True).all()
    if request.method == 'POST':
        description = request.form['description']
        content_text = request.form.get('content', '')
        files = request.files.getlist('files')  # Получаем список файлов
        new_content = Content(event_id=event_id, content=content_text, description=description)
        db.session.add(new_content)
        db.session.commit()
        # Сохранение фотографий
        for file in files:
            if file and file.filename:
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                new_photo = ContentPhotos(content_id=new_content.id, photo_path=filename)
                db.session.add(new_photo)
        # Доступ
        access_users = request.form.getlist('access')
        for user_id in access_users:
            access = Access(content_id=new_content.id, user_id=int(user_id))
            db.session.add(access)
        db.session.commit()
        flash('Контент успешно добавлен')
        return redirect(url_for('view_content', event_id=event_id))
    return render_template('add_content.html', event_id=event_id, students=students)

# Просмотр контента
@app.route('/view_content/<int:event_id>')
def view_content(event_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    event = Event.query.get(event_id)
    if not event:
        flash('Мероприятие не найдено')
        return redirect(url_for('dashboard'))
    contents = Content.query.filter_by(event_id=event_id).all()
    accessible = []
    for c in contents:
        if session['role'] == 'teacher' or Access.query.filter_by(content_id=c.id, user_id=session['user_id']).first():
            # Получаем фотографии для контента
            c.photos = ContentPhotos.query.filter_by(content_id=c.id).all()
            accessible.append(c)
    return render_template('view_content.html', event_id=event_id, contents=accessible)

# Удаление контента (только teacher)
@app.route('/delete_content/<int:content_id>')
def delete_content(content_id):
    if session.get('role') != 'teacher':
        return redirect(url_for('dashboard'))
    content = Content.query.get(content_id)
    if not content:
        flash('Контент не найден')
        return redirect(url_for('dashboard'))
    # Удаляем связанные фотографии
    photos = ContentPhotos.query.filter_by(content_id=content_id).all()
    for photo in photos:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], photo.photo_path))
        except OSError:
            pass  # Игнорируем, если файл не существует
        db.session.delete(photo)
    # Удаляем записи доступа
    Access.query.filter_by(content_id=content_id).delete()
    # Удаляем сам контент
    db.session.delete(content)
    db.session.commit()
    flash('Контент успешно удалён')
    return redirect(url_for('view_content', event_id=content.event_id))

# Статистика (только teacher)
@app.route('/statistics')
def statistics():
    if session.get('role') != 'teacher':
        return redirect(url_for('dashboard'))
    
    # Статистика по мероприятиям
    events = Event.query.order_by(Event.date).all()
    event_stats = []
    for event in events:
        intending_users = User.query.join(Attendance).filter(
            Attendance.event_id == event.id, Attendance.intending == True
        ).all()
        present_users = User.query.join(Attendance).filter(
            Attendance.event_id == event.id, Attendance.present == True
        ).all()
        event_stats.append({
            'event': event,
            'intending_count': len(intending_users),
            'intending_names': [u.username for u in intending_users],
            'present_count': len(present_users),
            'present_names': [u.username for u in present_users]
        })
    
    # Статистика по студентам
    students = User.query.filter_by(role='student', approved=True).all()
    student_stats = []
    for student in students:
        intending_count = Attendance.query.filter_by(
            user_id=student.id, intending=True
        ).count()
        present_count = Attendance.query.filter_by(
            user_id=student.id, present=True
        ).count()
        student_stats.append({
            'student': student,
            'intending_count': intending_count,
            'present_count': present_count
        })
    
    return render_template('statistics.html', event_stats=event_stats, student_stats=student_stats)

# Сервировка фото
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True)