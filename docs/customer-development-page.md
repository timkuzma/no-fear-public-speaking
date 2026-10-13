# Public customer interview results page

URL: https://no-fear-stage.157.22.172.204.nip.io/customer-development.html

Editable source: `public/customer-development.html`. The page is standalone, has no authentication or application JavaScript, and currently contains an empty state rather than invented interview results. Its typography and colors match the maintained site.

On 13 October 2026 it was published without restarting the application. The exact Nginx location `/customer-development.html` in `/etc/nginx/sites-available/no-fear-stage` serves `/var/www/no-fear-stage-pages/customer-development.html` with `Cache-Control: no-store`. The protected application checkout cannot be read by the Nginx worker, so this public copy is separate; do not loosen checkout permissions.

For future content updates, upload the revised source to the application checkout and refresh the public copy:

```sh
install -m 644 /opt/no-fear-stage/public/customer-development.html /var/www/no-fear-stage-pages/customer-development.html
```

No Nginx reload is needed for content updates. Preserve the exact location when replacing the proxy configuration; other routes continue to the existing application. The pre-change proxy configuration is retained privately at `/var/backups/no-fear-stage-customer-page-nginx-20261013.conf`.

Publication checks confirmed anonymous HTTPS 200 and byte-for-byte equality with the editable source. No interview content, participant data or upload functionality has been added yet.
