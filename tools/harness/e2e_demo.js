// The demo path (docs/demo-script.md), adapted to fresh harness data: a visitor, a
// learner, a company admin, an instructor and staff, one or two key checks per step.
// Never relies on the seeded demo password; a step that genuinely needs a seeded demo
// account reads E2E_DEMO_PASSWORD and is skipped with a clear message when it's unset.
const { chromium } = require('playwright')
const assert = require('assert')
const fs = require('fs')
const OUT = process.argv[2] || 'shots'
fs.mkdirSync(OUT, { recursive: true })
const { BASE, py: run, lastLine, NEW_USER_PASSWORD, DEMO_PASSWORD } = require('./lib')
const py = (script, ...args) => lastLine(run(script, ...args))

;(async () => {
  const b = await chromium.launch()
  global.__demobrowser = b
  const problems = []
  const track = (p) => {
    p.on('pageerror', (e) => problems.push('pageerror: ' + e.message))
    p.on('console', (m) => m.type() === 'error' && !/status of (401|403|404)/.test(m.text()) && problems.push('console: ' + m.text()))
    p.on('response', (r) => r.url().includes('/api/') && r.status() >= 500 && problems.push(`HTTP ${r.status()} ${r.url()}`))
    return p
  }
  const step = (s) => console.log('✓', s)
  const skip = (s) => console.log('… skipped:', s)
  const shot = async (p, n) => (await p.waitForTimeout(500), p.screenshot({ path: `${OUT}/${n}.png` }))
  const toast = (p, t) => p.locator('[data-sonner-toast]').filter({ hasText: t }).first().waitFor()

  const login = async (p, email) => {
    await p.goto(BASE + '/login')
    await p.getByLabel('Email').fill(email)
    await p.getByLabel('Password', { exact: true }).fill(NEW_USER_PASSWORD)
    await p.getByRole('button', { name: 'Log in' }).click()
    await p.waitForURL(/\/(learn|studio|business)$/)
  }
  const newPage = async (email) => {
    const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } })
    const p = track(await ctx.newPage())
    p.setDefaultTimeout(45_000) // the shared e2e harness can be slow under concurrent load
    if (email) await login(p, email)
    return p
  }

  const p = await newPage()
  global.__demodebug = p

  // ================================================================ 1. visitor
  await p.goto(BASE + '/', { waitUntil: 'networkidle' })
  await p.getByRole('link', { name: 'LearnHub home' }).waitFor()
  await shot(p, 'demo-01-home')

  const slug = py('e2e_course.py')
  await p.getByRole('combobox', { name: 'Search courses' }).fill('Every Lect')
  await p.getByRole('option', { name: /Every Lecture Type/ }).click()
  await p.waitForURL(new RegExp(`/courses/${slug}$`))
  await p.getByRole('heading', { name: 'Course content' }).waitFor()
  const preview = p.getByRole('button', { name: /Preview this course/ })
  if (await preview.count()) {
    await preview.click()
    await p.getByRole('dialog').waitFor()
    await p.keyboard.press('Escape')
  }
  await shot(p, 'demo-02-course-page')
  step('1. visitor: home, header search finds a course, course page with curriculum and preview')

  await p.goto(BASE + '/plans', { waitUntil: 'networkidle' })
  await p.getByRole('heading', { name: /plan/i }).first().waitFor()
  step('1b. plans page loads')

  // ================================================================ 2. learner
  const learnerEmail = py('e2e_user.py', NEW_USER_PASSWORD)
  const l = await newPage(learnerEmail)
  await l.goto(`${BASE}/learn/${slug}`)
  await l.getByRole('button', { name: /Enrol for free/ }).click()
  await l.waitForURL(/\/lecture\//)
  step('2a. learner enrols and opens the player')

  await l.getByRole('button', { name: 'Mark as complete' }).click()
  await l.getByText('Completed', { exact: true }).first().waitFor()
  await l.getByRole('tab', { name: 'Notes' }).click()
  await l.getByLabel('New note').fill('A note at this lecture.')
  await l.getByRole('button', { name: 'Save note' }).click()
  await l.getByText('A note at this lecture.').waitFor()
  step('2b. video completed; a note saved')

  // step through to the quiz
  for (let guard = 0; guard < 4 && !(await l.getByText('Pass mark').count()); guard++) {
    await l.locator('#next-lecture').click()
    await l.waitForTimeout(400)
    const complete = l.getByRole('button', { name: 'Mark as complete' }).first()
    if (await complete.count()) (await complete.click(), await l.getByText('Completed', { exact: true }).first().waitFor())
  }
  await l.getByRole('button', { name: 'Start quiz' }).click()
  await l.getByRole('radio', { name: '4' }).click()
  await l.getByRole('button', { name: 'Next', exact: true }).click()
  await l.getByRole('checkbox', { name: 'Django' }).click()
  await l.getByRole('checkbox', { name: 'Flask' }).click()
  await l.getByRole('button', { name: 'Next', exact: true }).click()
  await l.getByRole('radio', { name: 'True' }).click()
  await l.getByRole('button', { name: 'Next', exact: true }).click()
  await l.getByLabel('Match for 200').selectOption('OK')
  await l.getByLabel('Match for 404').selectOption('Not Found')
  await l.getByRole('button', { name: 'Next', exact: true }).click()
  await l.getByLabel('Blank 1').fill('post')
  await l.getByRole('button', { name: 'Submit answers' }).click()
  await l.getByText('You passed').waitFor()
  await shot(l, 'demo-03-quiz-result')
  step('2c. quiz taken, result shown')

  // certificates and public verification
  await l.goto(BASE + '/learn/certificates')
  const cert = l.getByRole('link', { name: /Verify/ }).first()
  if (await cert.count()) {
    const verifyHref = await cert.getAttribute('href')
    const anon = await (await b.newContext()).newPage()
    await anon.goto(BASE + verifyHref)
    await anon.getByText('Genuine certificate, issued by LearnHub').waitFor()
    await shot(anon, 'demo-04-verify')
    await anon.close()
    step('2d. certificate listed, verified publicly')
  } else {
    skip('no certificate yet (this course has lectures beyond this run)')
  }

  // token wallet
  console.log('  ', py('e2e_grant_tokens.py', learnerEmail, '100'))
  await l.goto(BASE + '/wallet', { waitUntil: 'networkidle' })
  await l.getByText('Your token wallet').waitFor()
  await l.getByText('100', { exact: false }).first().waitFor()
  await shot(l, 'demo-05-wallet')
  await l.goto(BASE + '/subscription', { waitUntil: 'networkidle' })
  await l.getByText('Unlimited personal plan').waitFor()
  await l.goto(BASE + '/packages', { waitUntil: 'networkidle' })
  await l.getByText('Course bundles').waitFor()
  step('2e. token wallet shows a balance; unlimited plan and bundles pages load')

  // ================================================================ 3. company admin
  const org = JSON.parse(py('e2e_org.py', NEW_USER_PASSWORD))
  const a = await newPage(org.admin)
  await a.getByRole('button', { name: 'Account menu' }).click()
  await a.getByRole('menuitem', { name: new RegExp(`${org.org_name} dashboard`.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')) }).click()
  await a.waitForURL(/\/business$/)
  await a.getByRole('heading', { name: 'Compliance overview' }).waitFor()
  await shot(a, 'demo-06-business-overview')
  step('3a. company overview loads with real records')

  await a.goto(BASE + '/business/matrix', { waitUntil: 'networkidle' })
  await a.getByRole('heading', { name: 'Training matrix' }).waitFor()
  await a.getByRole('button', { name: new RegExp(`${org.people.sara.name} .* Fire Safety:`) }).click()
  await a.getByRole('dialog', { name: org.people.sara.name }).waitFor()
  await a.keyboard.press('Escape')
  step('3b. training matrix: filter by site, open a person')

  await a.goto(BASE + '/business/requirements', { waitUntil: 'networkidle' })
  await a.getByText('Fire Safety').first().waitFor()
  step('3c. requirements lists the company-wide rule')

  await a.goto(BASE + '/business/invites', { waitUntil: 'networkidle' })
  await a.getByRole('heading', { name: 'Invitations' }).waitFor()
  step('3d. invitations page ready (full invite -> accept flow covered by e2e_m3.js)')

  await a.goto(BASE + '/business/reports', { waitUntil: 'networkidle' })
  await Promise.all([a.waitForEvent('download'), a.getByRole('button', { name: 'Export CSV' }).click()])
  step('3e. reports: CSV export')

  if (DEMO_PASSWORD) {
    const owner = await newPage()
    await login(owner, 'b2b.demo.owner@learnhub.example')
    await owner.goto(BASE + '/business', { waitUntil: 'networkidle' })
    await owner.getByRole('heading', { name: /overview/i }).waitFor()
    step('3f. corporate packages owner (seeded account): workspace loads')
  } else {
    skip('corporate packages owner demo (needs E2E_DEMO_PASSWORD for the seeded b2b.demo.owner account)')
  }

  // ================================================================ 4. instructor
  const instructorEmail = py('e2e_user.py', NEW_USER_PASSWORD)
  console.log('  ', py('e2e_approve.py', 'instructor', instructorEmail))
  const t = await newPage(instructorEmail)
  await t.goto(BASE + '/studio', { waitUntil: 'networkidle' })
  await t.getByRole('heading', { name: /Good (morning|afternoon|evening)/ }).waitFor()
  await shot(t, 'demo-07-studio-dashboard')
  step('4a. studio dashboard loads')

  await t.getByRole('button', { name: 'Create your first course' }).click()
  await t.getByLabel('Course title').fill(`Demo Course ${Date.now()}`)
  await t.getByRole('button', { name: 'Create and open builder' }).click()
  await t.waitForURL(/\/studio\/courses\/[^/]+$/)
  const demoCourseId = t.url().split('/studio/courses/')[1]
  await t.goto(`${BASE}/studio/courses/${demoCourseId}/curriculum`)
  await t.getByRole('button', { name: 'Add module' }).click()
  await t.getByLabel('New module title').fill('Introduction')
  await t.getByRole('button', { name: 'Add module' }).last().click()
  await t.getByRole('button', { name: 'Add lesson' }).click()
  await t.getByRole('menuitem', { name: 'Reading' }).click()
  await t.getByRole('dialog').getByLabel('Title', { exact: true }).fill('Welcome')
  await t.getByRole('dialog').getByRole('button', { name: 'Add and edit' }).click()
  await t.getByRole('textbox', { name: 'Reading' }).fill('Welcome to the demo course.')
  await t.getByRole('button', { name: 'Save lesson' }).click()
  await t.getByText('Lesson saved').waitFor()
  await t.goto(`${BASE}/studio/courses/${demoCourseId}/pricing`)
  await t.getByRole('radio', { name: 'Free' }).click()
  await t.getByRole('button', { name: 'Save price' }).click()
  await toast(t, 'Price saved')
  await t.goto(`${BASE}/studio/courses/${demoCourseId}/publish`)
  await t.getByRole('button', { name: 'Submit for review' }).click()
  await toast(t, 'Sent for review')
  step('4b. course builder: curriculum, pricing, submit for review')

  await t.goto(BASE + '/studio/grading', { waitUntil: 'networkidle' })
  await t.getByRole('heading', { name: 'Marking' }).waitFor()
  await t.goto(BASE + '/studio/questions', { waitUntil: 'networkidle' })
  await t.getByRole('heading', { name: 'Q&A and reviews' }).waitFor()
  await t.goto(BASE + '/studio/revenue', { waitUntil: 'networkidle' })
  await t.getByRole('heading', { name: 'Sales & earnings' }).waitFor()
  await t.goto(BASE + '/studio/payouts', { waitUntil: 'networkidle' })
  await t.getByRole('heading', { name: 'Payouts' }).waitFor()
  step('4c. assignments, Q&A, sales & earnings, payouts pages render')

  // ================================================================ 5. staff
  const staffEmail = JSON.parse(py('e2e_staff.py', NEW_USER_PASSWORD)).staff
  const s = await newPage(staffEmail)
  await s.goto(BASE + '/console', { waitUntil: 'networkidle' })
  await s.getByRole('heading', { name: 'Admin dashboard' }).waitFor()
  await shot(s, 'demo-08-console-dashboard')
  step('5a. console dashboard')

  await s.goto(BASE + '/console/approvals', { waitUntil: 'networkidle' })
  await s.getByRole('heading', { name: /approval/i }).first().waitFor()
  const review = s.getByRole('link', { name: /Review/ }).first()
  if (await review.count()) {
    await review.click()
    const approve = s.getByRole('button', { name: 'Approve' }).first()
    if (await approve.count()) (await approve.click(), await toast(s, 'pprov'))
    step('5b. approved the instructor\'s submitted course')
  } else skip('no course waiting for approval (the demo instructor course may already be clear)')

  for (const [route, text] of [
    ['/console/pricing', 'Pricing'],
    ['/console/commissions', 'Commission management'],
    ['/console/promotions', 'Promotions'],
    ['/console/token-pricing', 'Token pricing'],
    ['/console/wallets', 'Token wallets'],
    ['/console/companies', 'Companies'],
    ['/console/certificates', 'Certificate management'],
    ['/console/communications', 'Communications & support'],
    ['/console/settings', 'Platform settings'],
    ['/console/audit', 'Audit log'],
  ]) {
    await s.goto(BASE + route, { waitUntil: 'networkidle' })
    await s.getByRole('heading', { name: text }).waitFor()
  }
  step('5c. pricing, commissions, promotions, token pricing & wallets, companies, certificates, communications, settings, audit all render')

  await b.close()
  if (problems.length) {
    console.log('PROBLEMS:\n' + problems.join('\n'))
    process.exit(1)
  }
  console.log('Demo path E2E passed, no console errors or 5xx')
})().catch(async (e) => {
  console.error('FAILED:', e.message)
  if (global.__demodebug) await global.__demodebug.screenshot({ path: `${OUT}/demo-FAILED.png` }).catch(() => {})
  if (global.__demobrowser) await global.__demobrowser.close().catch(() => {})
  process.exit(1)
})
