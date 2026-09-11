import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import '@/styles/base.css'

// The root page stays a plain index until a variation is chosen; then the
// winner moves here and the variations folder goes away.
const VARIATIONS = [
  ['blueprint', 'Blueprint', 'Dark navy drafting grid, the mark at home'],
  ['ledger', 'Ledger', 'Warm paper, index cards and rubber stamps'],
  ['terminal', 'Terminal', 'Log lines with a live cursor'],
  ['editorial', 'Editorial', 'Big type, one accent, magazine numbers'],
  ['foundry', 'Foundry', 'Thick rules, hard cuts, no rounded corners'],
] as const

function Index() {
  return (
    <main className="mx-auto max-w-xl px-6 py-16 font-sans">
      <h1 className="text-2xl font-semibold">eBook Metamend, design round</h1>
      <p className="mt-2 text-neutral-600">Five directions on invented books. Pick one.</p>
      <ul className="mt-8 space-y-3">
        {VARIATIONS.map(([slug, name, note]) => (
          <li key={slug}>
            <a
              className="block rounded-md border p-4 hover:bg-neutral-50"
              href={`variations/${slug}/`}
            >
              <span className="font-medium">{name}</span>
              <span className="block text-sm text-neutral-600">{note}</span>
            </a>
          </li>
        ))}
      </ul>
    </main>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Index />
  </StrictMode>,
)
