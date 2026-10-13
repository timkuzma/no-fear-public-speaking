# Public customer interview results page

URL: https://no-fear-stage.157.22.172.204.nip.io/customer-development.html

This standalone, anonymous page contains 39 documents from the user-approved `CustDev PDF.zip` archive. Folder membership and document identifiers match the archive: `Идеальный клиент` contains 28 documents; `Другие сегменты` contains 11. Counts describe documents, not independently verified interviews or people. Document text and source qualifications are preserved; no aggregate research conclusions are invented.

## Content and source

- Published file: `public/customer-development.html` (self-contained CSS, reader JavaScript and escaped JSON content).
- Editable layout: `scripts/customer-development-template.html`.
- Builder: `scripts/build_customer_development.py`; it uses build-only `pdfplumber` from the bundled workspace Python runtime. It is not an application dependency.
- Original PDFs and extraction/audit caches stay outside `public/` and Git. Original files are unchanged. PDF downloads are not offered because they would expose the removed action sections.
- The reader provides both folders, text search within a folder, document links, a section outline and back navigation. No application JavaScript, authentication, private API, local storage or upload control is involved. Hash routes support direct links to a document or section.
- The builder removes named next-action sections, proposed experiments, future interview plans, planned product checks and corresponding `Как проверить` / `Критерий решения` fields. Nested action-plan headings do not prematurely end removal. Following transcripts, findings, related sources and research limitations survive. Source statements about respondents' past behavior remain intact.
- For this archive, 57 named action headings and 122 action fields were removed. All retained characters are checked against extracted source lines in order, allowing only PDF whitespace normalization and bullet-to-list formatting. This checks extraction/formatting preservation, not independent factual verification of source research.

Rebuild from an explicitly approved archive, using the workspace dependency Python executable:

```sh
python3 scripts/build_customer_development.py /absolute/path/to/CustDev\ PDF.zip --audit /tmp/customer-development-audit.json
python3 tests/test_customer_development_page.py
```

Review the audit and the rendered reader before publication. A different archive may contain new action headings; update removal boundaries deliberately rather than deleting every occurrence of words such as `следующий` from interview responses.

## Publication

The exact Nginx location `/customer-development.html` in `/etc/nginx/sites-available/no-fear-stage` serves `/var/www/no-fear-stage-pages/customer-development.html` with `Cache-Control: no-store`. The protected application checkout cannot be read by the Nginx worker, so this public copy is separate; do not loosen checkout permissions. The page stays `noindex, nofollow` but remains accessible to anyone with its URL.

Upload the reviewed source to `/opt/no-fear-stage/public/customer-development.html` and refresh the public copy atomically:

```sh
install -m 644 /opt/no-fear-stage/public/customer-development.html /var/www/no-fear-stage-pages/.customer-development.next.html
mv /var/www/no-fear-stage-pages/.customer-development.next.html /var/www/no-fear-stage-pages/customer-development.html
```

No application restart or Nginx reload is needed for content updates. Preserve the exact location when replacing proxy configuration; other routes continue to the existing application. The pre-route proxy configuration is retained privately at `/var/backups/no-fear-stage-customer-page-nginx-20261013.conf`. Back up the current public HTML privately before replacing content; restore that file atomically for a page-only rollback.

Verify anonymous HTTPS 200 and byte-for-byte equality with the reviewed file. Check both folders, search, document/section navigation, mobile reflow and console errors in the actual browser. These checks do not certify the underlying interviews or their conclusions.
