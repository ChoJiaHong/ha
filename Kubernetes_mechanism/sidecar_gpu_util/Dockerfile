FROM python:3.10-slim
RUN pip install flask
COPY gpu_util_exporter.py /app/gpu_util_exporter.py
WORKDIR /app
CMD ["python", "gpu_util_exporter.py"]
