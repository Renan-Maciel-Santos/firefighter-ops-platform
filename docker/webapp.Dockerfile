FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY _env.py _comum.py _log.py ./
COPY webapp ./webapp
COPY seed ./seed
COPY db/demo ./db/demo
RUN python webapp/modelos/gerar_modelo_padrao.py
WORKDIR /app/webapp
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
