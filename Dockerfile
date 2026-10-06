# syntax=docker/dockerfile:1

FROM python:3.12-slim

WORKDIR /rsvp-app

COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY . .

# Single worker on purpose: the JSON-file database cannot handle concurrent writers
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--access-logfile", "-", "app:app"]