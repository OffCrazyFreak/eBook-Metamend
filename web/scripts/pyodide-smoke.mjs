// Runs the Python test suite inside Pyodide against the wheels the site ships,
// so a deploy cannot carry a package that only works on CPython.
//
// Usage: node scripts/pyodide-smoke.mjs   (after scripts/wheels.sh)

import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { loadPyodide } from 'pyodide'

const web = fileURLToPath(new URL('..', import.meta.url))
const wheels = join(web, 'public', 'wheels')
const tests = join(web, '..', 'tests')

const py = await loadPyodide()
console.log(`pyodide ${py.version}, python ${py.runPython('import sys; sys.version.split()[0]')}`)

for (const wheel of JSON.parse(readFileSync(join(wheels, 'manifest.json'), 'utf8'))) {
  await py.loadPackage(join(wheels, wheel))
}
// pytest is not part of the site; micropip fetches it from PyPI for this run only.
await py.loadPackage('micropip')
await py.runPythonAsync('import micropip; await micropip.install("pytest")')

py.FS.mkdirTree('/work/tests')
for (const name of readdirSync(tests).filter((n) => n.endsWith('.py'))) {
  py.FS.writeFile(`/work/tests/${name}`, readFileSync(join(tests, name)))
}

const code = py.runPython(`
import os, pytest
os.chdir('/work')
os.environ['EBOOK_LIBRARY'] = '/work/library'
pytest.main(['-q', '-p', 'no:cacheprovider', 'tests'])
`)
if (code !== 0) {
  console.error(`pytest exit ${code}`)
  process.exit(1)
}
console.log('pytest passed under Pyodide')
