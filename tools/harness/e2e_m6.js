// M6 end-to-end: polish + the 2026-11-15 B2C fixes (see the two newest sections of
// docs/build-status.md). Checks, in order:
//   1. footer links go to real routes, no "Privacy" link, /design is the 404 page (built site);
//   2. browser tab titles;
//   3. header search suggestions (type-ahead, arrow keys, escape);
//   4. My learning side column (counts, upcoming deadlines, certificates);
//   5. B2C token unlock opens the player (fresh unlock, and a pre-existing entitlement with
//      no enrolment yet -> "Start learning" calls the new enrol endpoint);
//   6. the course page access badge wording;
//   7. /wallet, /wallet/buy, /subscription, /packages: one backdrop each, no console errors.
const { chromium, devices } = require('playwright')
const assert = require('assert')
const fs = require('fs')
const OUT = process.argv[2] || 'shots'
fs.mkdirSync(OUT, { recursive: true })
const { BASE, py: run, lastLine, NEW_USER_PASSWORD } = require('./lib')
const py = (script, ...args) => lastLine(run(script, ...args))

;(async () => {
  const b = await chromium.launch()
  global.__m6browser = b
  const problems = []
  const track = (p) => {
    p.on('pageerror', (e) => problems.push('pageerror: ' + e.message))
    p.on('console', (m) => m.type() === 'error' && !/status of (401|403|404)/.test(m.text()) && problems.push('console: ' + m.text()))
    p.on('response', (r) => r.url().includes('/api/') && r.status() >= 500 && problems.push(`HTTP ${r.status()} ${r.url()}`))
    return p
  }
  const step = (s) => console.log('✓', s)
  const shot = async (p, n) => (await p.waitForTimeout(500), p.screenshot({ path: `${OUT}/${n}.png` }))
  const toast = (p, t) => p.locator('[data-sonner-toast]').filter({ hasText: t }).first().waitFor()
  const backdropCount = (p) => p.locator('div.pointer-events-none.absolute.inset-x-0.top-0').count()

  const login = async (p, email) => {
    await p.goto(BASE + '/login')
    await p.getByLabel('Email').fill(email)
    await p.getByLabel('Password', { exact: true }).fill(NEW_USER_PASSWORD)
    await p.getByRole('button', { name: 'Log in' }).click()
    await p.waitForURL(/\/(learn|business)$/)
  }
  const newPage = async (email) => {
    const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } })
    const p = track(await ctx.newPage())
    p.setDefaultTimeout(45_000) // the shared e2e harness can be slow under concurrent load
    if (email) await login(p, email)
    return p
  }

  const p = await newPage()
  global.__m6debug = p

  // ================================================================ 1. footer + 404
  await p.goto(BASE + '/', { waitUntil: 'networkidle' })
  const footer = p.locator('footer')
  await footer.waitFor()
  assert.strictEqual(await footer.getByRole('link', { name: 'Privacy' }).count(), 0, 'no "Privacy" link in the footer')
  const links = await footer.locator('a').evaluateAll((as) => as.map((a) => ({ text: a.textContent?.trim(), href: a.getAttribute('href') })))
  for (const l of links) {
    assert(l.href && l.href !== '#', `footer link "${l.text}" has a real href, got ${l.href}`)
  }
  await p.getByRole('link', { name: 'Teach on LearnHub' }).click()
  await p.waitForURL(/\/teach$/)
  await p.getByRole('heading', { name: 'Teach on LearnHub' }).waitFor()
  step('1a. footer links go to real routes; no "Privacy" link')

  await p.goto(BASE + '/design', { waitUntil: 'networkidle' })
  await p.getByText('Page not found').waitFor()
  await shot(p, 'm6-01-design-404')
  step('1b. /design is the 404 page in the built site')

  // ================================================================ 2. titles
  await p.goto(BASE + '/courses')
  await p.waitForFunction(() => document.title === 'Browse courses · LearnHub')
  step('2a. /courses title')

  const slug = py('e2e_course.py')
  await p.goto(`${BASE}/courses/${slug}`)
  await p.waitForFunction(() => document.title.endsWith('· LearnHub') && document.title !== 'Course · LearnHub')
  assert(/Every Lecture Type/.test(await p.title()), 'the course page title is the course name')
  step('2b. course page title is the course name')

  // ================================================================ 3. header search
  await p.goto(BASE + '/', { waitUntil: 'networkidle' })
  const search = p.getByRole('combobox', { name: 'Search courses' })
  await search.fill('Every Lect')
  const list = p.getByRole('listbox', { name: 'Suggestions' })
  await list.waitFor()
  await p.getByRole('option', { name: /Every Lecture Type/ }).waitFor()
  await shot(p, 'm6-02-search-suggestions')
  await p.keyboard.press('ArrowDown')
  await p.keyboard.press('Enter')
  await p.waitForURL(new RegExp(`/courses/${slug}$`))
  step('3a. search suggestions: type-ahead, ArrowDown + Enter opens the course')

  await search.fill('Every Lect')
  await list.waitFor()
  await p.keyboard.press('Escape')
  await list.waitFor({ state: 'hidden' })
  step('3b. Escape closes the suggestions')

  // ================================================================ 4. My learning side column
  const org = JSON.parse(py('e2e_org.py', NEW_USER_PASSWORD))
  const learner = await newPage(org.people.sara.email)
  // the compliance engine assigns the company-wide requirement asynchronously
  let sawDeadline = false
  for (let i = 0; i < 15 && !sawDeadline; i++) {
    await learner.goto(BASE + '/learn', { waitUntil: 'networkidle' })
    sawDeadline = (await learner.getByText('Upcoming deadlines').count()) > 0 && (await learner.getByText(/Fire Safety/).count()) > 0
    if (!sawDeadline) await learner.waitForTimeout(1500)
  }
  assert(sawDeadline, 'Upcoming deadlines shows the company requirement within the poll window')
  await learner.getByText('Courses', { exact: true }).waitFor()
  await learner.getByText('My certificates').waitFor()
  await shot(learner, 'm6-03-my-learning-side-column')
  step('4. My learning: counts, upcoming deadlines, my certificates')

  // ================================================================ 5+6. B2C token unlock
  const b2c = JSON.parse(py('e2e_b2c.py', NEW_USER_PASSWORD))
  const unlocker = await newPage(b2c.unlocker)
  await unlocker.goto(`${BASE}/courses/${b2c.slug}`, { waitUntil: 'networkidle' })
  await unlocker.getByText('Unlock the whole course with tokens').waitFor()
  await unlocker.getByRole('button', { name: new RegExp(`Unlock · ${b2c.token_price}`) }).click()
  await unlocker.getByRole('button', { name: 'Confirm unlock' }).click()
  await unlocker.waitForURL(new RegExp(`/learn/${b2c.slug}`))
  await unlocker.getByText(/of \d+ done|Mark as complete/).first().waitFor()
  await shot(unlocker, 'm6-04-unlock-opens-player')
  step('5a. a fresh token unlock opens the player with lectures (enrolment created on the fly)')

  const preenrolled = await newPage(b2c.preenrolled)
  await preenrolled.goto(`${BASE}/courses/${b2c.slug}`, { waitUntil: 'networkidle' })
  await preenrolled.getByText('Unlocked with tokens').waitFor()
  await shot(preenrolled, 'm6-05-access-badge')
  step('6. the course page access badge says "Unlocked with tokens"')

  const [enrolResponse] = await Promise.all([
    preenrolled.waitForResponse((r) => /\/commerce\/tokens\/access\/course\/.+\/enrol/.test(r.url())),
    preenrolled.getByRole('button', { name: 'Start learning' }).click(),
  ])
  assert.strictEqual(enrolResponse.status(), 200, 'the enrol endpoint succeeds for an existing entitlement with no enrolment')
  await preenrolled.waitForURL(new RegExp(`/learn/${b2c.slug}`))
  await preenrolled.getByText(/of \d+ done|Mark as complete/).first().waitFor()
  step('5b. "Start learning" on a pre-existing entitlement calls the enrol endpoint and opens the player')

  // ================================================================ 7. B2C pages: one backdrop, no console errors
  const w = await newPage(org.admin)
  for (const [route, text] of [['/wallet', 'Your token wallet'], ['/wallet/buy', 'Buy tokens'], ['/subscription', 'Unlimited personal plan'], ['/packages', 'Course bundles']]) {
    await w.goto(BASE + route, { waitUntil: 'networkidle' })
    await w.getByText(text).first().waitFor()
    await w.waitForTimeout(400)
    const n = await backdropCount(w)
    assert.strictEqual(n, 1, `${route} draws exactly one backdrop, found ${n}`)
    await shot(w, `m6-06-b2c${route.replace(/\//g, '-')}`)
  }
  step('7. /wallet, /wallet/buy, /subscription, /packages: one backdrop each')

  // ================================================================ 7b. a 404 inside a workspace layout doesn't double its backdrop
  await w.goto(BASE + '/business/not-a-real-page', { waitUntil: 'networkidle' })
  await w.getByText('Page not found').waitFor()
  await w.waitForTimeout(400)
  assert.strictEqual(await backdropCount(w), 1, 'a 404 inside the business workspace draws exactly one backdrop')
  step('7b. a 404 page inside a workspace layout does not double its backdrop')

  // ================================================================ 8. phone: the touched B2C routes, no overflow
  const phone = await b.newContext({ ...devices['iPhone 13'] })
  const mobile = track(await phone.newPage())
  await login(mobile, org.admin)
  let overflow = 0
  for (const route of ['/wallet', '/wallet/buy', '/subscription', '/packages', '/learn']) {
    await mobile.goto(BASE + route, { waitUntil: 'networkidle' })
    await mobile.waitForTimeout(600)
    await mobile.screenshot({ path: `${OUT}/m6-phone-${route.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '')}.png` })
    if (await mobile.evaluate(() => document.scrollingElement.scrollWidth > window.innerWidth + 1)) (overflow++, console.log('  OVERFLOW on', route))
  }
  assert.strictEqual(overflow, 0, 'no touched route scrolls sideways on a phone')
  step('8. phone: the B2C routes and My learning, no horizontal scroll')

  await b.close()
  if (problems.length) {
    console.log('PROBLEMS:\n' + problems.join('\n'))
    process.exit(1)
  }
  console.log('M6 E2E passed, no console errors or 5xx')
})().catch(async (e) => {
  console.error('FAILED:', e.message)
  if (global.__m6debug) await global.__m6debug.screenshot({ path: `${OUT}/m6-FAILED.png` }).catch(() => {})
  if (global.__m6browser) await global.__m6browser.close().catch(() => {})
  process.exit(1)
})
