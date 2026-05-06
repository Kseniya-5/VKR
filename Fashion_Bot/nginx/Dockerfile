FROM nginx:alpine

COPY nginx.conf /etc/nginx/nginx.conf

COPY index.html /usr/share/nginx/html/
COPY dashboard.html /usr/share/nginx/html/
COPY photos.html /usr/share/nginx/html/
COPY profile.html /usr/share/nginx/html/
COPY settings.html /usr/share/nginx/html/
COPY link-telegram.html /usr/share/nginx/html/
COPY from-telegram.html /usr/share/nginx/html/
COPY link-existing-web.html /usr/share/nginx/html/
COPY login-token.html /usr/share/nginx/html/
COPY recommendations.html /usr/share/nginx/html/
COPY outfits.html /usr/share/nginx/html/
COPY assets/ /usr/share/nginx/html/assets/

RUN mkdir -p /usr/share/nginx/media

EXPOSE 80
