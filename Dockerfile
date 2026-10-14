# Headless core only (advanced users). The desktop app does not need Docker.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HUNTLY_DATA_DIR=/data HUNTLY_WATCH_PARENT=0
WORKDIR /app
COPY core/requirements.txt core/requirements.txt
RUN pip install --no-cache-dir -r core/requirements.txt
COPY core/ core/
RUN pip install --no-cache-dir --no-deps ./core && useradd -m huntly && mkdir /data && chown huntly /data
USER huntly
EXPOSE 8765
CMD ["python", "-m", "huntly", "--port", "8765"]
