import os
import uuid
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix # <-- 新增导入

# 导入 SQLAlchemy
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

# 导入 boto3 (R2 存储)
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

# --- 配置 ---
# 从环境变量中读取配置
SECRET_KEY = os.environ.get('SECRET_KEY', 'default_secret_key_please_change')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '8888')
R2_ACCESS_KEY_ID = os.environ.get('R2_ACCESS_KEY_ID')
R2_SECRET_ACCESS_KEY = os.environ.get('R2_SECRET_ACCESS_KEY')
R2_ENDPOINT_URL = os.environ.get('R2_ENDPOINT_URL')
R2_BUCKET_NAME = os.environ.get('R2_BUCKET_NAME')
R2_PUBLIC_URL = os.environ.get('R2_PUBLIC_URL')

# 数据库配置：使用 Render 提供的 DATABASE_URL
DATABASE_URL = os.environ.get('DATABASE_URL')

# 文件上传配置
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'mov', 'webm'}
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_host=1, x_prefix=1) # <-- 新增应用 ProxyFix
app.secret_key = SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# --- 数据库模型 (SQLAlchemy) ---
Base = declarative_base()

class Video(Base):
    __tablename__ = 'videos'
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    video_key = Column(String, unique=True, nullable=False)
    thumbnail_key = Column(String, nullable=True)
    upload_date = Column(DateTime, default=func.now())

# --- 数据库初始化和连接 ---
if DATABASE_URL:
    # 适配 Render 的 PostgreSQL URL 格式
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    
    # 首次运行时创建表
    Base.metadata.create_all(engine)
else:
    # 如果没有提供 DATABASE_URL，则退回到本地 SQLite (仅用于本地开发测试)
    print("WARNING: DATABASE_URL not set. Falling back to local SQLite.")
    sqlite_db_path = os.path.join(os.getcwd(), 'videos.db')
    engine = create_engine(f'sqlite:///{sqlite_db_path}')
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    
def get_db_session():
    return Session()

# --- R2 客户端初始化 ---
s3_client = None
if R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY and R2_ENDPOINT_URL:
    try:
        s3_client = boto3.client(
            's3',
            endpoint_url=R2_ENDPOINT_URL,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            config=Config(signature_version='s3v4')
        )
    except Exception as e:
        print(f"R2 Client Initialization Error: {e}")

# --- 辅助函数 ---
def allowed_file(filename, allowed_extensions):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('请先登录', 'error')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def upload_to_r2(file_stream, key, content_type):
    if not s3_client:
        return False
    try:
        s3_client.upload_fileobj(
            file_stream,
            R2_BUCKET_NAME,
            key,
            ExtraArgs={'ContentType': content_type}
        )
        return True
    except ClientError as e:
        print(f"R2 Upload Failed: {e}")
        return False

def delete_from_r2(key):
    if not s3_client:
        return False
    try:
        s3_client.delete_object(Bucket=R2_BUCKET_NAME, Key=key)
        return True
    except ClientError as e:
        print(f"R2 Delete Failed: {e}")
        return False

# --- 路由 ---

@app.route('/')
def index():
    db_session = get_db_session()
    videos = db_session.query(Video).order_by(Video.upload_date.desc()).all()
    db_session.close()
    
    # 构造视频列表，使用 R2_PUBLIC_URL
    video_list = []
    for video in videos:
        video_list.append({
            'id': video.id,
            'title': video.title,
            'video_url': f"{R2_PUBLIC_URL}/{video.video_key}" if R2_PUBLIC_URL else "#",
            'thumbnail_url': f"{R2_PUBLIC_URL}/{video.thumbnail_key}" if video.thumbnail_key and R2_PUBLIC_URL else url_for('static', filename='placeholder.txt') # 使用占位符
        })
        
    return render_template('index.html', videos=video_list)

@app.route('/play/<int:video_id>')
def play(video_id):
    db_session = get_db_session()
    video = db_session.query(Video).filter_by(id=video_id).first()
    db_session.close()
    
    if video:
        video_data = {
            'title': video.title,
            'video_url': f"{R2_PUBLIC_URL}/{video.video_key}" if R2_PUBLIC_URL else "#"
        }
        return render_template('play.html', video=video_data)
    
    flash('视频未找到', 'error')
    return redirect(url_for('index'))

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if 'logged_in' in session:
        return redirect(url_for('admin_dashboard'))
        
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            session['logged_in'] = True
            flash('登录成功', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('密码错误', 'error')
            
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('logged_in', None)
    flash('已退出登录', 'success')
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard', methods=['GET', 'POST'])
@login_required
def admin_dashboard():
    db_session = get_db_session()
    
    if request.method == 'POST':
        # --- 处理视频上传 ---
        if 'video_file' not in request.files:
            flash('未选择视频文件', 'error')
            return redirect(url_for('admin_dashboard'))
            
        video_file = request.files['video_file']
        thumbnail_file = request.files.get('thumbnail_file')
        title = request.form.get('title') or secure_filename(video_file.filename)
        
        if video_file.filename == '':
            flash('未选择视频文件', 'error')
            return redirect(url_for('admin_dashboard'))
            
        if video_file and allowed_file(video_file.filename, ALLOWED_VIDEO_EXTENSIONS):
            # 1. 上传视频到 R2
            video_ext = video_file.filename.rsplit('.', 1)[1].lower()
            video_key = f"videos/{uuid.uuid4().hex}.{video_ext}"
            
            if not upload_to_r2(video_file.stream, video_key, video_file.content_type):
                flash('视频文件上传到 R2 失败。请检查 R2 环境变量和权限。', 'error')
                return redirect(url_for('admin_dashboard'))
                
            thumbnail_key = None
            
            # 2. 处理封面上传
            if thumbnail_file and thumbnail_file.filename != '' and allowed_file(thumbnail_file.filename, ALLOWED_IMAGE_EXTENSIONS):
                thumbnail_ext = thumbnail_file.filename.rsplit('.', 1)[1].lower()
                thumbnail_key = f"thumbnails/{uuid.uuid4().hex}.{thumbnail_ext}"
                
                if not upload_to_r2(thumbnail_file.stream, thumbnail_key, thumbnail_file.content_type):
                    flash('封面文件上传到 R2 失败。', 'error')
                    # 即使封面失败，视频也已上传，不回滚
            
            # 3. 记录到数据库
            new_video = Video(title=title, video_key=video_key, thumbnail_key=thumbnail_key)
            db_session.add(new_video)
            db_session.commit()
            
            flash(f'视频 "{title}" 上传成功！', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('不支持的文件格式或文件为空', 'error')
            
    # --- GET 请求：显示视频列表 ---
    videos = db_session.query(Video).order_by(Video.upload_date.desc()).all()
    
    video_list = []
    for video in videos:
        video_list.append({
            'id': video.id,
            'title': video.title,
            'video_url': f"{R2_PUBLIC_URL}/{video.video_key}" if R2_PUBLIC_URL else "#",
            'thumbnail_url': f"{R2_PUBLIC_URL}/{video.thumbnail_key}" if video.thumbnail_key and R2_PUBLIC_URL else url_for('static', filename='placeholder.txt')
        })
        
    db_session.close()
    return render_template('admin.html', videos=video_list)

@app.route('/admin/delete/<int:video_id>', methods=['POST'])
@login_required
def delete_video(video_id):
    db_session = get_db_session()
    video = db_session.query(Video).filter_by(id=video_id).first()
    
    if video:
        # 1. 从 R2 删除视频文件
        delete_from_r2(video.video_key)
        
        # 2. 从 R2 删除封面文件
        if video.thumbnail_key:
            delete_from_r2(video.thumbnail_key)
            
        # 3. 从数据库删除记录
        db_session.delete(video)
        db_session.commit()
        
        flash(f'视频 "{video.title}" 已删除。', 'success')
    else:
        flash('视频未找到', 'error')
        
    db_session.close()
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    app.run(debug=True)
