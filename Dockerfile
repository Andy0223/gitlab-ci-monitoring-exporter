FROM python:3.11-slim

WORKDIR /app

COPY main.py pyproject.toml poetry.lock requirements.txt run_script.sh /app/
COPY gitlabApi /app/gitlabApi
COPY prometheus /app/prometheus

RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT ["/app/run_script.sh"]

RUN chmod +x /app/run_script.sh