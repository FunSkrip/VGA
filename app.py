import os
import uuid
from flask import Flask, render_template, redirect, url_for, flash, request, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from ultralytics import YOLO
import cv2
import imageio

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ef78f8ae12c9585b22cc7273b2bd52b0f3447a8fdd037e69b7dcb04886181a06'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///VKR_YOLO.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/processed'


@app.route('/upload', methods=['POST'])
@login_required
def upload():
    file = request.files['file']
    model_name = request.form['model']

    ext = secure_filename(file.filename).rsplit('.',1)[-1].lower()
    uid = uuid.uuid4().hex
    src = os.path.join(app.config['UPLOAD_FOLDER'], f"src_{uid}.{ext}")
    file.save(src)
    res_ext = 'mp4' if ext in ['mp4','avi','mov'] else ext
    res = os.path.join(app.config['UPLOAD_FOLDER'], f"res_{uid}.{res_ext}")

    # Загрузка модели
    yolo = YOLO(model_name)

    # mapping id -> номер метки
    id_map = {}
    next_label = 1

    if ext in ['jpg','jpeg','png']:
        img = cv2.imread(src)
        result = yolo(img)[0]
        for i, box in enumerate(result.boxes):
            x1,y1,x2,y2 = map(int, box.xyxy[0].cpu().numpy())
            label = str(i+1)
            cv2.rectangle(img,(x1,y1),(x2,y2),(0,255,0),2)
            cv2.putText(img, label, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)
        cv2.imwrite(res, img)
        people = sum(1 for b in result.boxes if int(b.cls)==0)
        cars   = sum(1 for b in result.boxes if int(b.cls)==2)

    elif ext == 'gif':
        frames = imageio.mimread(src)
        processed = []
        counts = {'person': set(), 'car': set()}
        for frame in frames:
            img = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            detections = yolo.track(img, classes=[0,2], tracker='bytetrack.yaml', verbose=False)[0]
            for box in detections.boxes:
                obj_id = int(box.id.cpu().numpy()) if hasattr(box,'id') else None
                if obj_id is not None:
                    if obj_id not in id_map:
                        id_map[obj_id] = next_label; next_label += 1
                    label = str(id_map[obj_id])
                else:
                    label = ''
                x1,y1,x2,y2 = map(int, box.xyxy[0].cpu().numpy())
                cv2.rectangle(img,(x1,y1),(x2,y2),(0,255,0),2)
                if label:
                    cv2.putText(img,label,(x1,y1-10),cv2.FONT_HERSHEY_SIMPLEX,0.6,(0,255,0),2)
                cls = int(box.cls)
                if cls==0: counts['person'].add(obj_id)
                if cls==2: counts['car'].add(obj_id)
            cv2.putText(img, f"People: {len(counts['person'])} Cars: {len(counts['car'])}", (10,30), cv2.FONT_HERSHEY_SIMPLEX,1,(0,0,255),2)
            processed.append(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        imageio.mimsave(res, processed, fps=10)
        people, cars = len(counts['person']), len(counts['car'])

    else:  # видео
        cap = cv2.VideoCapture(src)
        fourcc = cv2.VideoWriter_fourcc(*'avc1')
        fps = cap.get(cv2.CAP_PROP_FPS)
        w = int(cap.get(3)); h = int(cap.get(4))
        out = cv2.VideoWriter(res, fourcc, fps, (w,h))
        counts = {'person': set(), 'car': set()}
        while True:
            ret, frame = cap.read()
            if not ret: break
            det = yolo.track(frame, classes=[0,2], tracker='bytetrack.yaml', verbose=False)[0]
            for box in det.boxes:
                # безопасное извлечение ID
                raw_id = getattr(box, 'id', None)
                if raw_id is not None:
                    try:
                        obj_id = int(raw_id.cpu().numpy())
                    except Exception:
                        obj_id = None
                else:
                    obj_id = None

                if obj_id is not None:
                    if obj_id not in id_map:
                        id_map[obj_id] = next_label
                        next_label += 1
                    label = str(id_map[obj_id])
                else:
                    label = ''

                # координаты и отрисовка
                x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                if label:
                    cv2.putText(frame, label, (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

                # подсчет по классам
                cls = int(box.cls)
                if cls == 0 and obj_id is not None:
                    counts['person'].add(obj_id)
                if cls == 2 and obj_id is not None:
                    counts['car'].add(obj_id)
            text = f"People: {len(counts['person'])} Cars: {len(counts['car'])}"
            cv2.putText(frame,text,(10,30),cv2.FONT_HERSHEY_SIMPLEX,1,(0,0,255),2)
            out.write(frame)
        cap.release(); out.release()
        people, cars = len(counts['person']), len(counts['car'])

    return render_template('result.html', url=os.path.basename(res), people=people, cars=cars)


db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


# Модели базы данных
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


# Формы
class RegistrationForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Пароль', validators=[DataRequired()])
    confirm_password = PasswordField('Повторите пароль',
                                     validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Зарегистрироваться')


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Пароль', validators=[DataRequired()])
    submit = SubmitField('Войти')


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# Инициализация базы данных
def create_db():
    with app.app_context():
        db.create_all()


# Маршруты
@app.route('/')
@app.route('/index')
def index():
    return render_template('index.html')


@app.route('/analysis')
def analysis():
    models = [('yolov8n.pt', 'YOLOv8 Nano'), ('yolov8m.pt', 'YOLOv8 Medium'), ('yolov8l.pt', 'YOLOv8 Large')]
    return render_template('analysis.html', models=models)


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = RegistrationForm()
    if form.validate_on_submit():
        try:
            user = User(
                username=form.username.data,
                email=form.email.data
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash('Регистрация прошла успешно! Теперь вы можете войти.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash('Ошибка регистрации. Возможно, email или имя уже заняты.', 'danger')

    return render_template('register.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            return redirect(url_for('index'))
        flash('Неверный email или пароль', 'danger')

    return render_template('login.html', form=form)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/download/<filename>')
@login_required
def download_file(filename):
    # Если нужно — проверяйте, что filename есть в ваших результатах
    return send_from_directory(
        directory=app.config['UPLOAD_FOLDER'],
        path=filename,
        as_attachment=True
    )


if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    create_db()  # Создаем таблицы при первом запуске
    app.run(debug=True)