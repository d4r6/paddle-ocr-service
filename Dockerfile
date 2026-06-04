FROM python:3.11-slim

# Installation des dépendances système corrigées pour l'OCR et OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copie des fichiers de dépendances Python
COPY pyproject.toml poetry.lock* requirements.txt* ./

# Installation des dépendances Python (s'adapte si vous utilisez pip classique)
RUN pip install --no-cache-dir --upgrade pip && \
    if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; \
    else pip install --no-cache-dir .; fi

# Copie du reste du code de l'application
COPY . .

# Commande de démarrage identique à votre railpack
CMD ["sh", "-c", "uvicorn galaxy_jarvis_crew.server:app --host 0.0.0.0 --port $PORT"]