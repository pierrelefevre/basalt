FROM nginx
COPY * /usr/share/nginx/html
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/templates/default.conf.template
CMD ["nginx", "-g", "daemon off;"]