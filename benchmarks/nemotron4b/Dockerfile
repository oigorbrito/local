FROM node:22.23.3-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 git ca-certificates && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/gabrielchasukjin/cloi.git /opt/cloi && cd /opt/cloi && git checkout --detach 1da62db7aa3aed8b1e65f1e3fb69a89cf00707b9 && npm ci --ignore-scripts --no-audit --no-fund
USER node
ENV HOME=/tmp/local-home CLOI_DATA_DIR=/tmp/local-home/cloi PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
ENTRYPOINT ["python3", "/app/benchmarks/nemotron4b/relay_guest.py"]
