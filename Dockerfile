FROM python:3.11-slim

WORKDIR /work
COPY pyproject.toml constraints.txt constraints.in README.md LICENSE ./
COPY src src
COPY scripts scripts
COPY tests tests
COPY configs configs
COPY paper paper
COPY docs docs
COPY metadata metadata
COPY Makefile Makefile

ENV PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu
RUN python -m pip install --upgrade pip \
    && python -m pip install --extra-index-url https://download.pytorch.org/whl/cpu \
       -c constraints.txt -e ".[dev]"

CMD ["make", "test"]
