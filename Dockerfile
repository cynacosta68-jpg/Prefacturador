# Imagen oficial de Playwright: trae Chromium y sus dependencias.
# La versión DEBE coincidir con playwright== de requirements.txt.
FROM mcr.microsoft.com/playwright/python:v1.55.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=America/Argentina/Buenos_Aires \
    DATA_DIR=/data \
    HEADLESS=true \
    PORT=8000

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

COPY app ./app
COPY assets ./assets

# La base (SQLite) y las copias de seguridad viven en /data: montar ahí un volumen persistente.
RUN mkdir -p /data && chown pwuser:pwuser /data
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=4).status==200 else 1)"

# Arranca como root solo para dar al usuario sin privilegios el volumen recién montado;
# el servicio corre como pwuser. Un solo proceso y una sola réplica (el bot corre en un hilo).
ENV HOME=/home/pwuser
CMD ["sh", "-c", "chown -R pwuser:pwuser /data && chmod 700 /data && exec setpriv --reuid=pwuser --regid=pwuser --init-groups uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*' --workers 1"]
