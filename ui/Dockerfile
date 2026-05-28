# Dictum v5 — VibeCoder Docker Image
# Usage:
#   docker build -t dictum-vibecoder .
#   docker run -p 8765:8765 dictum-vibecoder
#
# The VibeCoder UI is then available at http://localhost:8765

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# ── System dependencies ───────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        make \
        libcurl4-openssl-dev \
        libssl-dev \
        python3 \
        python3-pip \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

# ── Copy project ──────────────────────────────────────────────────────────────
WORKDIR /dictum
COPY . /dictum

# ── Install Python package ────────────────────────────────────────────────────
RUN pip3 install --break-system-packages -e ".[server]"

# ── Build stdlib ──────────────────────────────────────────────────────────────
RUN make -C stdlib lib

# ── Expose VibeCoder port ─────────────────────────────────────────────────────
EXPOSE 8765

# ── Start backend server ──────────────────────────────────────────────────────
CMD ["python3", "ui/backend_server.py"]
