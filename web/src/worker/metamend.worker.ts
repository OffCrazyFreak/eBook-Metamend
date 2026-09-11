/// <reference lib="webworker" />
// Runs the Python package under Pyodide. Everything the page sends is bytes and
// plain objects; everything back is the same. The worker never sees the DOM.

import { loadPyodide, type PyodideAPI } from 'pyodide'
import type { PyProxy } from 'pyodide/ffi'

import type { FileBytes, FromWorker, ToWorker } from './protocol'

// The interpreter, then the two wheels the site ships beside it.
const LIBRARY = '/library'
const STEPS = [
  'Fetching the Python runtime',
  'Unpacking the standard library',
  'Installing pypdf',
  'Installing eBook Metamend',
] as const

// A module worker's own scope, typed as such so postMessage takes a transfer list.
const scope = self as unknown as DedicatedWorkerGlobalScope
const post = (message: FromWorker, transfer: Transferable[] = []) =>
  scope.postMessage(message, transfer)

let ready: Promise<PyodideAPI> | null = null
// The Python module, bound once so no proxy is made per request.
let web: PyProxy | null = null

// The catalogues are reached with a synchronous request, which a worker may
// make and the plain blocking Python sources need. A timeout is legal on a
// synchronous request inside a worker, unlike on the main thread.
function fetchSync(url: string, headersJson: string, timeout: number): Uint8Array {
  const request = new XMLHttpRequest()
  request.open('GET', url, false)
  request.responseType = 'arraybuffer'
  request.timeout = Math.round(timeout * 1000)
  for (const [name, value] of Object.entries(JSON.parse(headersJson) as Record<string, string>)) {
    request.setRequestHeader(name, value)
  }
  request.send()
  if (request.status < 200 || request.status >= 400) {
    throw new Error(`HTTP ${request.status || 'error'} for ${url}`)
  }
  return new Uint8Array(request.response as ArrayBuffer)
}

async function boot(base: string): Promise<PyodideAPI> {
  post({ type: 'loading', progress: 0, label: STEPS[0] })
  const py = await loadPyodide({ indexURL: `${base}pyodide/` })
  post({ type: 'loading', progress: 0.5, label: STEPS[1] })
  const wheels: string[] = JSON.parse(await (await fetch(`${base}wheels/manifest.json`)).text())
  // pypdf first: loadPackage from a URL does no dependency resolution.
  for (const [i, wheel] of wheels.entries()) {
    post({ type: 'loading', progress: 0.5 + (0.5 * i) / wheels.length, label: STEPS[2 + i] })
    await py.loadPackage(`${base}wheels/${wheel}`)
  }
  py.FS.mkdirTree(LIBRARY)
  py.runPython(`
from ebook_metamend import web

def _bytes(js_files):
    return {ext: bytes(data) for ext, data in js_files.to_py().items()}

def propose(stem, js_files, on_answer):
    return web.propose(stem, _bytes(js_files), ${JSON.stringify(LIBRARY)}, on_answer)

def apply(stem, js_files, proposal):
    return web.apply(stem, _bytes(js_files), ${JSON.stringify(LIBRARY)}, proposal.to_py())

def bundle(js_files):
    return web.bundle(_bytes(js_files))
`)
  web = py.globals.get('web') as PyProxy
  web.install_transport(fetchSync)
  post({ type: 'loading', progress: 1, label: 'Ready' })
  return py
}

const toPlain = { dict_converter: Object.fromEntries }

// toJs already copied each buffer out of the wasm heap; hand those over as is.
function toBytes(files: Record<string, Uint8Array>): [FileBytes, ArrayBuffer[]] {
  const out: FileBytes = {}
  const buffers: ArrayBuffer[] = []
  for (const [ext, data] of Object.entries(files)) {
    out[ext as keyof FileBytes] = data.buffer as ArrayBuffer
    buffers.push(data.buffer as ArrayBuffer)
  }
  return [out, buffers]
}

scope.onmessage = async (event: MessageEvent<ToWorker>) => {
  const message = event.data
  if (message.type === 'init') {
    ready = boot(message.base)
    try {
      await ready
      post({ type: 'ready' })
    } catch (error) {
      ready = null
      post({ type: 'failed', message: describe(error) })
    }
    return
  }
  if (message.type === 'reset') {
    if (ready) (await ready, web?.begin_run())
    return
  }
  if (!ready || !web) {
    post({ type: 'error', id: message.id, message: 'The runtime is not loaded.' })
    return
  }
  const py = await ready
  try {
    switch (message.type) {
      case 'propose': {
        const fn = py.globals.get('propose')
        const onAnswer = (source: string, _hadIt: boolean) =>
          post({ type: 'answer', stem: message.stem, source: source as never })
        const result = fn(message.stem, views(message.files), onAnswer)
        fn.destroy()
        const proposal = result === undefined ? null : result.toJs(toPlain)
        result?.destroy?.()
        const factsProxy = web.facts(message.stem)
        const facts = factsProxy.toJs(toPlain)
        factsProxy.destroy()
        const pause: number = web.pause_after()
        const unavailable = proposal?.unavailable ?? []
        post({ type: 'proposed', id: message.id, facts, proposal, pause, unavailable })
        return
      }
      case 'apply': {
        const fn = py.globals.get('apply')
        const result = fn(message.stem, views(message.files), message.proposal)
        fn.destroy()
        const plain = result.toJs(toPlain)
        result.destroy()
        const [files, buffers] = toBytes(plain.files)
        post({ type: 'applied', id: message.id, files, writes: plain.writes }, buffers)
        return
      }
      case 'bundle': {
        const fn = py.globals.get('bundle')
        const result = fn(views(message.files))
        fn.destroy()
        const zip = (result.toJs() as Uint8Array).buffer as ArrayBuffer
        result.destroy()
        post({ type: 'bundled', id: message.id, zip }, [zip])
        return
      }
    }
  } catch (error) {
    post({ type: 'error', id: message.id, message: describe(error) })
  }
}

function views(files: Record<string, ArrayBuffer>): Record<string, Uint8Array> {
  return Object.fromEntries(Object.entries(files).map(([k, v]) => [k, new Uint8Array(v)]))
}

function describe(error: unknown): string {
  if (error instanceof Error) {
    // Pyodide's message is the whole traceback; the last line says what happened.
    const lines = error.message.trim().split('\n')
    return lines[lines.length - 1] || error.name
  }
  return String(error)
}
