// Screenshot the running React board with one ticket selected.
//   node scripts/shot.mjs 101            -> ../output/screenshots/ticket_101.png (+ .json with what the board showed)
// Needs the dashboard on http://localhost:5173 (npm run dev) and Chrome installed.
import puppeteer from 'puppeteer-core'
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ticket = process.argv[2]
const outDir = process.argv[3] ?? join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'output', 'screenshots')
const url = process.env.BOARD_URL ?? 'http://localhost:5173'
const chrome = process.env.CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
if (!ticket) throw new Error('usage: node scripts/shot.mjs <ticket id> [output folder]')

mkdirSync(outDir, { recursive: true })
const browser = await puppeteer.launch({ executablePath: chrome, headless: true, args: ['--no-sandbox'], defaultViewport: { width: 1440, height: 1000 } })
try {
  const page = await browser.newPage()
  await page.goto(url, { waitUntil: 'networkidle0' })
  await page.waitForSelector('.ticket')
  for (const el of await page.$$('.ticket')) {
    if ((await el.evaluate((n) => n.innerText)).includes(`#${ticket}`)) { await el.click(); break }
  }
  await new Promise((r) => setTimeout(r, 2500)) // let the events for this ticket load
  const text = (sel) => page.$eval(sel, (e) => e.innerText).catch(() => null)
  const shown = {
    ticket: Number(ticket),
    taken_at: new Date().toISOString(),
    banner: await text('.banner .bhead'),
    balance_shown: await text('.balance .v'),
    ticket_card: (await page.$$eval('.ticket.on', (e) => e.map((x) => x.innerText.replace(/\n+/g, ' | '))))[0] ?? null,
  }
  const png = join(outDir, `ticket_${ticket}.png`)
  await page.screenshot({ path: png, fullPage: true })
  writeFileSync(join(outDir, `ticket_${ticket}.json`), JSON.stringify(shown, null, 2) + '\n')
  console.log(JSON.stringify(shown))
} finally {
  await browser.close()
}
