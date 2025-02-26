## Hướng dẫn cài đặt
### Tạo môi trường và kích hoạt môi trường
```python
conda create -n be_env python=3.11
conda activate be_env
```
### Tạo OPENAI API KEY
Tạo thư mục /.streamlit/secrets.toml, nhập thông tin API vào file này.
```python
[openai]
OPENAI_API_KEY = "sk-your-api-key"
```
### Cài đặt các thư viện
```python
pip install -r requirements.txt
```
### Khởi tạo database
```python
python init_db.py
```
### Chạy ứng dụng
```python
uvicorn app:app --host 0.0.0.0 --port 5601 --reload
```
