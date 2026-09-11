# The web version

How the browser build at [offcrazyfreak.github.io/eBook-Metamend](https://offcrazyfreak.github.io/eBook-Metamend/) works and why it is built the way it is. Written on 2026-09-11, when it first went live.

## What it is

The same Python package as the desktop tool, running inside the page under Pyodide (CPython compiled to WebAssembly), in a Web Worker so the page stays responsive. The visitor drops files or a folder, the same safety model runs, and the repaired files either go back into the folder or come back as downloads. Nothing is uploaded anywhere: the only network calls are the catalogue searches, and they go straight from the browser to the catalogue.

## Hosting

GitHub Pages, static files only. There is no server to run, no account elsewhere, no key to keep secret and no place a file could be sent to. The Pages workflow builds the site from the same commit as the package, runs the Python test suite inside Pyodide, and deploys. Anything with a server would also have had to accept uploads of the visitor's books, and a 50 MB PDF is over the request limit of the usual serverless hosts anyway (4.5 MB on Vercel, 6 MB on Netlify and Lambda).

## Pyodide from our own site

The interpreter (about 13 MB in six files, most of it one wasm file) is copied out of the `pyodide` npm package into the site at build time. A CDN was the obvious alternative and was rejected: the visitor's browser would then talk to a third party, and the runtime could change under us. The package and pypdf ship as two wheels beside it, built by `web/scripts/wheels.sh` with pypdf pinned by hash; the worker installs both with `loadPackage`, so `micropip` and PyPI are never touched at runtime.

Nothing large enters git: the wheels and the copied interpreter are build products.

## One book at a time

The worker holds one book's bytes at a time. The page keeps the list; each book is sent over, written into the worker's in-memory file system, proposed or repaired, read back, and deleted. A folder of three hundred books never sits in memory at once. Pacing between books happens in JavaScript with a timer, from the same back-off the desktop pacer computes, because Python cannot sleep inside a worker without headers Pages cannot set.

A download of more than five files is one zip, built on the page by `client-zip` as the books are repaired: each repaired book is pulled into the archive and dropped, and the archive itself is a Blob the browser may keep on disk (Chromium pages blob storage out past a share of RAM, Firefox writes a response body to a temporary file past one megabyte), so the worker's memory does not grow with the selection.

## Catalogues from the browser

The web version asks Apple Books, Open Library and Inventaire. All three are keyless and answer browser calls (they send `Access-Control-Allow-Origin: *`). The requests are synchronous XMLHttpRequests made by the worker with a timeout, which is what lets the sources stay plain blocking Python. Browsers set their own `User-Agent`, so Open Library's anonymous rate applies.

Google Books is not asked: its keyless quota is shared by everyone in the world and is exhausted daily, and a key would tie the deployment to one person's Google account. Kobo cannot leave the desktop because it is scraped through a bot-check bypass. The desktop tool asks all five; see `sources.md` for the numbers behind the choice.

## Writing back, by browser

| Browser | Chosen how | Repairs go |
| ------- | ---------- | ---------- |
| Chrome, Edge | folder picker, file picker, or a drop | back into the same files after a permission prompt on Write (one per folder, one per loose file), or as downloads, the visitor's choice |
| Firefox, Safari | folder input, file input, or a drop | as downloads: each file when five or fewer, one zip beyond that |

The difference is the File System Access API, which only Chromium browsers ship. It is detected at runtime, never guessed from the browser name. Read access is all the check needs; write access is asked for on Write, so the dry run stays a dry run. A book already written or downloaded is not written again.

## What the page shows

Every verdict comes from `enrich.propose`, unchanged. The row shows which catalogues have answered as they answer, then the verdict, the fields that would be written, and in the detail view every catalogue's answer with its scores, including the ones that earned no say. Nothing is written until Write is pressed and confirmed, and only HIGH verdicts are ever written: the page gates on it and so does `web.apply`, so the page's gate is not the last word.

## Fonts

Chakra Petch (display), IBM Plex Sans (body) and IBM Plex Mono (figures), all under the SIL Open Font License 1.1, self-hosted through the `@fontsource` packages. Pyodide is MPL-2.0 and client-zip is MIT. No font or script is fetched from a third party.

## Checking a change

```sh
cd web && pnpm install && ./scripts/wheels.sh
pnpm typecheck && pnpm format:check && pnpm test && pnpm build && node scripts/pyodide-smoke.mjs
pnpm dev   # then open the page in the T3 preview
```

The smoke script runs the whole Python suite inside Pyodide against the wheels the site would ship. On the dev server `window.__metamend.begin(intake)` starts a run from a script, which is how write-back is checked against an OPFS folder without a native picker; the built site does not have it.
