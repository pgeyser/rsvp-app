docker build -t rsvp-app .

docker tag rsvp-app cbosacr.azurecr.io/rsvp-app:latest
docker push cbosacr.azurecr.io/rsvp-app:latest