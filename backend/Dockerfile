FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_HOME=/app

WORKDIR ${APP_HOME}

RUN addgroup --system growqr \
    && adduser --system --ingroup growqr --home ${APP_HOME} growqr

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY . .

RUN mkdir -p ${APP_HOME}/.local_storage ${APP_HOME}/.local_queue \
    && chown -R growqr:growqr ${APP_HOME}

USER growqr

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
