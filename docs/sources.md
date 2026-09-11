# Metadata sources

Measured on 2026-09-11 against a 50-book sample of a private English-language library, with the tool's own yardstick: a source counts as strong when its best answer scores at least `TITLE_STRONG` on the title and `AUTHOR_STRONG` on the author against the filename. The scripts are not in the repository because their output names real books.

## Strong matches out of 50

- Apple Books (iTunes Search API): 36. Keyless, allows browser calls, about 20 calls a minute. Gives title, authors, description and genres; no publisher or ISBN.
- Kobo (Calibre plugin): 32. Scrapes kobo.com through a Cloudflare bot-check bypass; the plugin's own README documents lockouts. Desktop only, never to be hosted.
- Open Library: 32. Keyless, allows browser calls, 1 request a second (3 with a User-Agent that names a contact). Work-level ISBN lists, not edition-level.
- Google Books: 31. The keyless JSON API bills every anonymous request worldwide to one shared quota that is exhausted daily (HTTP 429 names the shared project). Calibre uses an old keyless Atom feed instead, which answered 3 of 6 attempts and refuses browser calls. A per-project key needs a Google Cloud account.
- Inventaire: 29. Keyless, allows browser calls, built on Wikidata plus its own entries. Always returns something, so its answers lean on the safety model to be rejected when wrong.
- Internet Archive: 20, mostly public-domain scans.
- Crossref: 1. Academic works.
- Deutsche Nationalbibliothek and Bibliothèque nationale de France: 0. They hold the German and French translations of the same books.
- Not usable: Hardcover (needs a token), BookBrainz (no CORS header on search), Library of Congress (Cloudflare challenge), Goodreads and Amazon (no API, scraping only).

## Decisions

- Desktop: Kobo, Google and Open Library through Calibre's plugins and a direct HTTP client. Apple Books and Inventaire are candidates to add; adding a source is an ask-first change.
- Web build: Apple Books, Open Library and Inventaire, called from the visitor's browser. No server, no key, no upload: the file never leaves the browser, which also sidesteps the 4.5 MB request limit of serverless hosts.
- Google is dropped from the web build rather than proxied, because a working key would tie the deployment to one person's Google account.
