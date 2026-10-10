# Loriini's website (docs/website.md): the static pages in site/, served by
# nginx. The current build's zip is not in the repository; the deploy script
# puts it in site/download/ first, so the Download button has something to
# give.
#
# Built from the repository's root:
#
#   fly deploy . --config deploy/site/fly.toml --dockerfile deploy/site/Dockerfile
#
FROM nginx:alpine
COPY deploy/site/default.conf /etc/nginx/conf.d/default.conf
COPY site/ /usr/share/nginx/html/
EXPOSE 80
