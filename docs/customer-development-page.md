# Public customer interview results page

## Repository distribution boundary (15 October 2026)

The user requested removal of interview pages from the GitHub repository, including its published branch history. `public/customer-development.html` and `docs/customer-development-conclusions.json` are private local/operator artifacts: they are ignored by Git and excluded from Docker build contexts. Do not re-add them. Preserve existing local copies and source archives. The builder, empty reader template and synthetic tests remain in source control; the real-archive inventory test skips in a clean clone without these artifacts.

Repository removal does not unpublish the separately hosted reader. The operational instructions below describe that separate publication; changing it requires an explicit request. The application can run without the interview artifacts.

This standalone, anonymous page contains 39 documents from the user-approved `CustDev PDF.zip` archive. Folder membership and document identifiers match the archive: `Идеальный клиент` contains 28 documents; `Другие сегменты` contains 11. Counts describe documents, not independently verified interviews or people. Interview answers and transcripts are preserved. Related-source sections and external links are removed from the public content at the user's request. Each document now has four authored findings and a product implication grounded in its source material.

## Content and source

- Published file: `public/customer-development.html` (self-contained CSS, reader JavaScript and escaped JSON content).
- Editable layout: `scripts/customer-development-template.html`.
- Editorial findings: `docs/customer-development-conclusions.json`. Each finding has source anchors; the builder verifies their presence and writes source block indices plus hashes into the optional private audit. Product implications are editorial interpretations of those findings, not descriptions of shipped functionality.
- Builder: `scripts/build_customer_development.py`; it uses build-only `pdfplumber` from the bundled workspace Python runtime. It is not an application dependency.
- Original PDFs and extraction/audit caches stay outside `public/` and Git. Original files are unchanged. PDF downloads are not offered because they would expose the removed action sections.
- The reader provides both folders, text search within a folder, document links, a section outline and back navigation. No application JavaScript, authentication, private API, local storage or upload control is involved. Hash routes support direct links to a document or section.
- Display names use one catalog sequence, `Интервью 1` through `Интервью 39`, sorted numerically within each folder. R001–R019 map to 1–19, the two result files to 20–21, and M001–M018 to 22–39. This is catalog numbering, not participant identity. Stable source IDs, original titles, filenames, evidence and existing hash URLs stay unchanged; search includes the old names and codes.
- The builder removes named next-action sections, proposed experiments, future interview plans, planned product checks and corresponding `Как проверить` / `Критерий решения` fields. Nested action-plan headings do not prematurely end removal. Following transcripts survive; related-material subsections are omitted. The user requested removal of research caveat boilerplate from public results: replace the entire old conclusion section and remove narrator-only methodological notes, without editing participant answers. Scientific qualifications inside participants' accounts of their own work are source content, not CustDev boilerplate.
- For this archive, 57 named action headings and 122 action fields were removed. All retained characters are checked against extracted source lines in order, allowing only PDF whitespace normalization and bullet-to-list formatting. This checks extraction/formatting before the explicitly requested editorial pass. The editorial pass rewrites 39 conclusion sections, covers every document exactly and rejects findings whose source anchors are missing.

Rebuild from an explicitly approved archive, using the workspace dependency Python executable:

```sh
python3 scripts/build_customer_development.py /absolute/path/to/CustDev\ PDF.zip --audit /tmp/customer-development-audit.json
python3 tests/test_customer_development_page.py
```

Review the audit and the rendered reader before publication. A different archive requires its own source-backed conclusion entries and may contain new action headings; update removal boundaries deliberately rather than deleting every occurrence of words such as `следующий` from interview responses.

## Publication

The exact Nginx location `/customer-development.html` in `/etc/no-fear-stage/nginx/no-fear-stage.conf.template` serves `/var/www/no-fear-stage-pages/customer-development.html` with `Cache-Control: no-store` through a read-only mount in the shared edge. The protected application checkout cannot be read by the Nginx worker, so this public copy is separate; do not loosen checkout permissions. The page stays `noindex, nofollow` but remains accessible to anyone with its URL. The original host's `/etc/nginx/sites-available/no-fear-stage` now redirects to the migrated origin; current deployment details are in `docs/production-deployment.md`.

Upload the reviewed source to `/opt/no-fear-stage/public/customer-development.html` and refresh the public copy atomically:

```sh
install -m 644 /opt/no-fear-stage/public/customer-development.html /var/www/no-fear-stage-pages/.customer-development.next.html
mv /var/www/no-fear-stage-pages/.customer-development.next.html /var/www/no-fear-stage-pages/customer-development.html
```

No application restart or Nginx reload is needed for content updates. Preserve the exact location when replacing proxy configuration; other routes continue to the existing application. The pre-route proxy configuration is retained privately at `/var/backups/no-fear-stage-customer-page-nginx-20261013.conf`. Back up the current public HTML privately before replacing content; restore that file atomically for a page-only rollback.

Verify anonymous HTTPS 200 and byte-for-byte equality with the reviewed file. Check both folders, search, document/section navigation, mobile reflow and console errors in the actual browser. Also check that each public conclusion contains the approved editorial text and that narrator-only research caveats do not remain in the reader.
