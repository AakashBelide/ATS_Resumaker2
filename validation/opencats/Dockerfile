# OpenCATS (real self-hosted ATS) for the Phase-3 manual validation test.
# PHP 7.4 + Apache serving the OpenCATS release; pair with MySQL 5.7 (compose).
FROM php:7.4-apache

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpng-dev libjpeg-dev libfreetype6-dev libzip-dev libicu-dev libonig-dev \
        unzip curl ca-certificates \
        poppler-utils antiword html2text unrtf \

    && docker-php-ext-configure gd --with-freetype --with-jpeg \
    && docker-php-ext-install mysqli pdo_mysql gd zip intl mbstring \
    && a2enmod rewrite \
    && rm -rf /var/lib/apt/lists/*

# Generous upload limits so resume files parse in the wizard/candidate upload.
RUN { \
      echo "file_uploads = On"; \
      echo "upload_max_filesize = 20M"; \
      echo "post_max_size = 25M"; \
      echo "memory_limit = 256M"; \
    } > /usr/local/etc/php/conf.d/opencats.ini

# 0.9.7.x uses mysqli (the legacy `mysql` ext was removed in PHP 7 - 0.9.4 fails its check).
ARG VER=0.9.7.4
RUN curl -fSL -o /tmp/oc.tar.gz \
        "https://github.com/opencats/OpenCATS/releases/download/${VER}/opencats-${VER}-full.tar.gz" \
    && tar xzf /tmp/oc.tar.gz -C /var/www/html --strip-components=1 \
    && rm /tmp/oc.tar.gz \
    && chown -R www-data:www-data /var/www/html \
    && chmod -R 775 /var/www/html/attachments /var/www/html/upload 2>/dev/null || true

EXPOSE 80
