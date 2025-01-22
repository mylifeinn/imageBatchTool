import os
from flask import Flask, request, send_file, jsonify, render_template
from werkzeug.utils import secure_filename
from PIL import Image
import zipfile
import uuid
import shutil
from datetime import datetime
import random
import string
import re

app = Flask(__name__)

# 配置上传和处理目录
UPLOAD_FOLDER = '/app/uploads'
PROCESSED_FOLDER = '/app/processed'
DOWNLOAD_FOLDER = '/app/downloads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff', 'webp'}

# 从环境变量获取最大文件大小和总大小限制
MAX_SINGLE_FILE_SIZE = int(os.environ.get('MAX_SINGLE_FILE_SIZE', 10)) * 1024 * 1024  # 默认10MB
MAX_TOTAL_SIZE = int(os.environ.get('MAX_TOTAL_SIZE', 500)) * 1024 * 1024  # 默认500MB

# 设置最大文件大小为10MB
app.config['MAX_CONTENT_LENGTH'] = MAX_TOTAL_SIZE

# 确保所需目录存在
for folder in [UPLOAD_FOLDER, PROCESSED_FOLDER, DOWNLOAD_FOLDER]:
    os.makedirs(folder, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# 图片处理函数（从原脚本保留，稍作修改）
def resize_image(input_path, output_path, max_size):
    with Image.open(input_path) as img:
        original_width, original_height = img.size
        if original_width > max_size or original_height > max_size:
            if original_width > original_height:
                new_width = max_size
                new_height = int((max_size / original_width) * original_height)
            else:
                new_height = max_size
                new_width = int((max_size / original_height) * original_width)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        img.save(output_path, quality=85, optimize=True)

def convert_image_format(input_path, output_path, new_format):
    new_format = new_format.upper()
    if new_format == 'JPG':
        new_format = 'JPEG'
    
    with Image.open(input_path) as img:
        if img.mode == 'RGBA':
            img = img.convert('RGB')
        img.save(output_path, format=new_format)

def create_zip_file(source_dir, output_path):
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(source_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, source_dir)
                zipf.write(file_path, arcname)

def generate_random_filename(extension):
    random_name = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    return f"{random_name}.{extension}"

def replace_chinese_with_numbers(filename):
    # 用于替换中文字符的计数器
    counter = 1
    def replace(match):
        nonlocal counter
        replacement = str(counter)
        counter += 1
        return replacement

    # 替换中文字符
    return re.sub(r'[\u4e00-\u9fa5]', replace, filename)

@app.route('/process', methods=['POST'])
def process_images():
    if 'files[]' not in request.files:
        return jsonify({'error': '没有上传文件'}), 400
    
    files = request.files.getlist('files[]')
    if not files or files[0].filename == '':
        return jsonify({'error': '没有选择文件'}), 400

    process_type = request.form.get('process_type')
    if not process_type:
        return jsonify({'error': '未指定处理类型'}), 400

    date_str = datetime.now().strftime('%Y%m%d')
    session_id = str(uuid.uuid4())
    upload_dir = os.path.join(UPLOAD_FOLDER, date_str, session_id)
    os.makedirs(upload_dir, exist_ok=True)

    processed_files = []
    uploaded_filenames = []
    total_size = 0

    try:
        for file in files:
            if file:
                if not allowed_file(file.filename):
                    return jsonify({'error': f'未知文件扩展名: {file.filename}'}), 400

                # 替换文件名中的中文字符为数字
                cleaned_filename = replace_chinese_with_numbers(file.filename)

                if cleaned_filename.strip() == '':
                    extension = file.content_type.split('/')[-1]
                    filename = generate_random_filename(extension)
                else:
                    filename = secure_filename(cleaned_filename)

                uploaded_filenames.append(filename)

                if file.content_length > MAX_SINGLE_FILE_SIZE:
                    return jsonify({'error': f'文件 {filename} 超过最大限制 {MAX_SINGLE_FILE_SIZE / (1024 * 1024)}MB'}), 400

                total_size += file.content_length
                if total_size > MAX_TOTAL_SIZE:
                    return jsonify({'error': '所有文件总大小超过最大限制 500MB'}), 400

                upload_path = os.path.join(upload_dir, filename)
                file.save(upload_path)

                if process_type == 'resize':
                    max_size = int(request.form.get('max_size', 800))
                    output_path = os.path.join(PROCESSED_FOLDER, f"{session_id}_{filename}")
                    resize_image(upload_path, output_path, max_size)
                    processed_files.append(output_path)
                
                elif process_type == 'convert':
                    new_format = request.form.get('new_format', 'jpg')
                    base_name = os.path.splitext(filename)[0]
                    output_path = os.path.join(PROCESSED_FOLDER, f"{session_id}_{base_name}.{new_format}")
                    convert_image_format(upload_path, output_path, new_format)
                    processed_files.append(output_path)

        zip_filename = f"processed_{date_str}_{session_id}.zip"
        zip_path = os.path.join(DOWNLOAD_FOLDER, zip_filename)
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in processed_files:
                filename = os.path.basename(file_path)
                zipf.write(file_path, filename)

        for file_path in processed_files:
            if os.path.exists(file_path):
                os.remove(file_path)

        return jsonify({
            'success': True,
            'download_url': f'/download/{zip_filename}',
            'uploaded_filenames': uploaded_filenames
        })

    except Exception as e:
        for file_path in processed_files:
            if os.path.exists(file_path):
                os.remove(file_path)
        return jsonify({'error': str(e)}), 500

@app.route('/download/<filename>')
def download_file(filename):
    return send_file(
        os.path.join(DOWNLOAD_FOLDER, filename),
        as_attachment=True,
        download_name=filename
    )

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
