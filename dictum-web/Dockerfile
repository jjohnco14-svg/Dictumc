FROM ubuntu:24.04

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# ── System deps + QEMU + cross-compilers ──────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    gcc g++ make \
    gcc-aarch64-linux-gnu g++-aarch64-linux-gnu \
    gcc-riscv64-linux-gnu g++-riscv64-linux-gnu \
    gcc-mips-linux-gnu g++-mips-linux-gnu \
    gcc-mipsel-linux-gnu g++-mipsel-linux-gnu \
    gcc-powerpc64le-linux-gnu g++-powerpc64le-linux-gnu \
    qemu-user \
    libcurl4-openssl-dev libssl-dev \
    curl git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── Python deps ───────────────────────────────────────────────────────────
WORKDIR /app
COPY requirements.txt .
RUN pip3 install --break-system-packages -r requirements.txt

# ── App source ────────────────────────────────────────────────────────────
COPY . .

# ── Static files served by FastAPI ────────────────────────────────────────
RUN mkdir -p /app/static
COPY index.html /app/static/index.html

# ── Entrypoint ────────────────────────────────────────────────────────────
EXPOSE 8080
CMD ["python3", "server.py"]
