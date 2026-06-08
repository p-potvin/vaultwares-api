import { useState } from 'react'
import { Check, Copy, Eye, Languages, ShieldCheck, Sparkles, X } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

const swatches = [
  { name: 'Base', token: 'vault.color.base', value: '#002B36', use: 'Deep dark background' },
  { name: 'Paper', token: 'vault.color.paper', value: '#FDF6E3', use: 'Warm light background' },
  { name: 'Gold', token: 'vault.color.gold', value: '#CC9B21', use: 'Primary brand accent' },
  { name: 'Cyan', token: 'vault.color.cyan', value: '#21B8CC', use: 'Interactive and focus states' },
  { name: 'Green', token: 'vault.color.green', value: '#4ECC21', use: 'Success and secured states' },
  { name: 'Burgundy', token: 'vault.color.burgundy', value: '#A63D40', use: 'Error and destructive states' },
  { name: 'Slate', token: 'vault.color.slate', value: '#4A5459', use: 'Secondary surfaces and text' },
  { name: 'Muted', token: 'vault.color.muted', value: '#586E75', use: 'Captions and metadata' },
]

const voiceRows = [
  ['Military-grade encryption keeps you safe.', 'Vault secured.'],
  ['Critical security warning!', 'We noticed something. Here is what to do.'],
  ['Proceed to authentication.', 'Continue.'],
  ['We collect this for your security.', 'This is optional and off by default.'],
]

const glassVariants = [
  {
    name: 'Liquid',
    text: 'Deep transparent layer with a soft glow for focused hero moments.',
    className: 'bg-white/10 border-white/30 text-vault-paper',
    backdrop: 'from-vault-base via-vault-slate to-vault-cyan',
  },
  {
    name: 'Solarized Frosted',
    text: 'Warm frosted panel tuned for VaultWares paper surfaces.',
    className: 'bg-vault-paper/55 border-vault-muted/20 text-vault-ink',
    backdrop: 'from-vault-paper via-vault-paper-bright to-vault-gold',
  },
  {
    name: 'Clear',
    text: 'Barely-there tint that preserves content readability.',
    className: 'bg-white/15 border-white/25 text-vault-paper',
    backdrop: 'from-vault-base via-vault-cyan to-vault-green',
  },
]

const summaryCards: Array<{ title: string; text: string; Icon: LucideIcon }> = [
  { title: 'Voice', text: 'Calm, precise, human. No fear copy.', Icon: Languages },
  { title: 'Visuals', text: 'Warm paper, deep teal, gold and cyan accents.', Icon: Eye },
  { title: 'Glass UI', text: 'Elevated overlays only, never whole-page blur.', Icon: Sparkles },
]

export function App() {
  const [copiedToken, setCopiedToken] = useState<string | null>(null)

  const handleCopy = (token: string, value: string) => {
    navigator.clipboard.writeText(value)
    setCopiedToken(token)
    setTimeout(() => setCopiedToken(null), 2000)
  }

  return (
    <main className="min-h-screen bg-vault-paper text-vault-ink">
      <section className="mx-auto max-w-6xl px-5 py-10 sm:px-8">
        <header className="grid gap-8 lg:grid-cols-[1fr_320px] lg:items-center">
          <div>
            <img src="/assets/vaultwares-logo.png" alt="VaultWares" className="mb-8 h-20 w-auto" />
            <p className="mb-3 text-sm font-medium uppercase tracking-wide text-vault-muted">Maintainable brand guide</p>
            <h1 className="max-w-3xl text-5xl font-light leading-tight text-vault-ink">Privacy first. Security in service.</h1>
            <p className="mt-5 max-w-2xl text-lg leading-8 text-vault-muted">
              A compact guide for humans and agents: what VaultWares should say, how it should look, and which tokens to use.
            </p>
          </div>

          <div className="glass-panel rounded-[20px] p-6 shadow-xl">
            <div className="flex items-center gap-3 text-vault-slate">
              <ShieldCheck className="h-6 w-6 text-vault-gold" aria-hidden="true" />
              <span className="text-sm font-medium uppercase tracking-wide">Brand priorities</span>
            </div>
            <ol className="mt-6 space-y-3 text-sm text-vault-muted list-decimal list-inside">
              <li>Privacy for individuals</li>
              <li>Security in service of privacy</li>
              <li>Functionality that stays understandable</li>
            </ol>
          </div>
        </header>

        <section className="mt-14 grid gap-4 md:grid-cols-3">
          {summaryCards.map(({ title, text, Icon }) => (
            <article key={title} className="rounded-[20px] border border-vault-muted/20 bg-vault-paper-bright p-6">
              <Icon className="h-5 w-5 text-vault-cyan" aria-hidden="true" />
              <h2 className="mt-4 text-xl font-normal text-vault-ink">{title}</h2>
              <p className="mt-2 text-sm leading-6 text-vault-muted">{text}</p>
            </article>
          ))}
        </section>

        <section className="mt-16">
          <div className="mb-6 flex items-center gap-3">
            <Copy className="h-5 w-5 text-vault-gold" aria-hidden="true" />
            <h2 className="text-3xl font-light">Token palette</h2>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {swatches.map((swatch) => (
              <article key={swatch.token} className="overflow-hidden rounded-[20px] border border-vault-muted/20 bg-vault-paper-bright">
                <div className="h-24 border-b border-vault-muted/10" style={{ backgroundColor: swatch.value }} />
                <div className="p-4">
                  <button
                    onClick={() => handleCopy(swatch.token, swatch.value)}
                    className="flex w-full items-center justify-between gap-3 rounded p-1 -m-1 hover:bg-vault-muted/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-vault-cyan transition-colors group cursor-pointer"
                    aria-label={`Copy hex code for ${swatch.name}`}
                    title={copiedToken === swatch.token ? "Copied!" : "Click to copy hex code"}
                  >
                    <h3 className="font-medium">{swatch.name}</h3>
                    <div className="flex items-center gap-2">
                      <code className="text-xs text-vault-muted">{swatch.value}</code>
                      {copiedToken === swatch.token ? <Check className="h-3.5 w-3.5 text-vault-green" aria-hidden="true" /> : <Copy className="h-3.5 w-3.5 text-vault-muted opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100 transition-opacity" aria-hidden="true" />}
                      <span aria-live="polite" className="sr-only">
                        {copiedToken === swatch.token ? 'Copied token to clipboard' : ''}
                      </span>
                    </div>
                  </button>
                  <p className="mt-1 text-xs text-vault-muted">{swatch.token}</p>
                  <p className="mt-3 text-sm text-vault-slate">{swatch.use}</p>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="mt-16 grid gap-8 lg:grid-cols-2">
          <div>
            <h2 className="text-3xl font-light">Voice replacement table</h2>
            <div className="mt-6 overflow-hidden rounded-[20px] border border-vault-muted/20 bg-vault-paper-bright">
              {voiceRows.map(([avoid, use]) => (
                <div key={avoid} className="grid gap-3 border-b border-vault-muted/10 p-4 last:border-b-0 sm:grid-cols-2">
                  <p className="text-sm text-vault-burgundy">
                    <span className="sr-only">Avoid saying: </span>
                    {avoid}
                  </p>
                  <p className="flex items-start gap-2 text-sm text-vault-slate">
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-vault-green" aria-hidden="true" />
                    <span>
                      <span className="sr-only">Instead use: </span>
                      {use}
                    </span>
                  </p>
                </div>
              ))}
            </div>
          </div>

          <div>
            <h2 className="text-3xl font-light">Glass UI examples</h2>
            <div className="mt-6 grid gap-4">
              {glassVariants.map((variant) => (
                <article key={variant.name} className={`rounded-[20px] bg-gradient-to-br ${variant.backdrop} p-4`}>
                  <div className={`rounded-[16px] border p-5 shadow-xl backdrop-blur-md ${variant.className}`}>
                    <h3 className="text-lg font-medium">{variant.name}</h3>
                    <p className="mt-2 text-sm opacity-85">{variant.text}</p>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>
      </section>
    </main>
  )
}
