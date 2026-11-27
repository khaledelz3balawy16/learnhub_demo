import { type ReactNode } from 'react'

import { Backdrop } from '@/components/art/backdrops'
import { usePublicSettings } from '@/features/platform/api'
import { Link } from '@/lib/router'

// Privacy policy and terms of use (client question 29). The wording describes what the
// platform really does: the data it keeps, the services it uses, its cookies, and the
// purchase rules set in console > Settings (refund window, VAT). The client's legal adviser
// reviews it before launch.

const UPDATED = '16 November 2026'

type Section = { id: string; title: string; body: ReactNode }

function LegalLayout({ eyebrow, title, intro, sections }: { eyebrow: string; title: string; intro: ReactNode; sections: Section[] }) {
  return (
    <div className="relative isolate">
      <Backdrop variant="folio" height={520} />
      <div className="relative mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-16">
        <header className="max-w-2xl animate-reveal">
          <p className="text-xs font-semibold tracking-[0.16em] text-primary uppercase">{eyebrow}</p>
          <h1 className="mt-3 text-3xl font-bold tracking-tight sm:text-4xl">{title}</h1>
          <p className="mt-3 text-sm text-subtle">Last updated {UPDATED}</p>
          <div className="mt-5 text-base leading-relaxed text-muted">{intro}</div>
        </header>

        <div className="mt-10 grid gap-10 lg:grid-cols-[220px_minmax(0,1fr)]">
          <nav aria-label="On this page" className="hidden lg:block">
            <div className="sticky top-24 rounded-xl border border-border bg-surface/80 p-4 backdrop-blur">
              <p className="text-xs font-semibold tracking-wide text-subtle uppercase">On this page</p>
              <ol className="mt-3 grid gap-1.5 text-sm">
                {sections.map((s, i) => (
                  <li key={s.id}>
                    <a href={`#${s.id}`} className="flex gap-2 rounded-md px-1.5 py-1 text-muted transition-colors hover:bg-surface-2 hover:text-text">
                      <span className="tabular text-subtle">{i + 1}.</span>
                      <span className="min-w-0">{s.title}</span>
                    </a>
                  </li>
                ))}
              </ol>
            </div>
          </nav>

          <div className="stagger grid max-w-3xl gap-5">
            {sections.map((s, i) => (
              <section key={s.id} id={s.id} aria-labelledby={`${s.id}-h`} className="scroll-mt-24 rounded-2xl border border-border bg-surface p-5 sm:p-7">
                <h2 id={`${s.id}-h`} className="flex items-baseline gap-3 text-lg font-semibold">
                  <span className="grid size-7 shrink-0 place-items-center rounded-full bg-primary-soft text-sm text-primary-soft-text tabular" aria-hidden>
                    {i + 1}
                  </span>
                  {s.title}
                </h2>
                <div className="mt-3 grid gap-3 text-sm leading-relaxed text-muted sm:pl-10 [&_li]:ml-4 [&_li]:list-disc [&_strong]:font-semibold [&_strong]:text-text [&_ul]:grid [&_ul]:gap-1.5">{s.body}</div>
              </section>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

/** "email us at x" when staff have set a contact address, otherwise the Help centre. */
function ContactLine({ contact }: { contact: string }) {
  return contact ? (
    <>
      email us at{' '}
      <a className="font-medium text-primary hover:underline" href={`mailto:${contact}`}>
        {contact}
      </a>{' '}
      or open a request in the <Link className="font-medium text-primary hover:underline" to="/support">Help centre</Link>
    </>
  ) : (
    <>
      open a request in the <Link className="font-medium text-primary hover:underline" to="/support">Help centre</Link> (sign in first)
    </>
  )
}

export function PrivacyPage() {
  const { settings } = usePublicSettings()
  const name = settings['general.platform_name']
  const contact = settings['general.contact_email']
  const sections: Section[] = [
    {
      id: 'who-we-are',
      title: 'Who we are',
      body: (
        <p>
          {name} is an online learning platform: a marketplace of courses for individuals, and a training workspace for companies. We decide how your personal
          information is used, so we are its controller under UK data protection law. To ask anything about your information, <ContactLine contact={contact} />.
        </p>
      ),
    },
    {
      id: 'what-we-collect',
      title: 'What we collect',
      body: (
        <ul>
          <li><strong>Your account:</strong> name, email address and password (stored only as a secure hash, never readable by anyone). If you turn on 2-step sign-in, the details your authenticator needs.</li>
          <li><strong>Checkout details:</strong> the phone number and country you give when you buy, and a record of each order, refund and subscription.</li>
          <li><strong>Your learning:</strong> the courses you join, your progress, quiz answers, assignments you hand in, questions and reviews you post, and the certificates you earn.</li>
          <li><strong>Company training:</strong> if your employer adds you to their workspace, your role, team or location, the training they require, and your completion records.</li>
          <li><strong>From your employer's HR system:</strong> only if your company connects one (Breathe HR). Your name, work email, job title, department, manager, employment status, start date, contracted hours, working pattern, training records and approved leave dates.</li>
          <li><strong>Support:</strong> the messages you send us through the Help centre.</li>
        </ul>
      ),
    },
    {
      id: 'how-we-use-it',
      title: 'How we use it',
      body: (
        <>
          <ul>
            <li>To run your account and give you the courses you bought or were given (our contract with you).</li>
            <li>To take payments, issue invoices and handle refunds (our contract with you, and the law on keeping financial records).</li>
            <li>To show your employer the training they asked you to complete (our contract with your employer, and their legitimate interest in keeping staff trained and compliant).</li>
            <li>To send the emails and notifications the platform needs, such as receipts, reminders and replies to your questions.</li>
            <li>To keep the platform secure, and to stop fraud and misuse (our legitimate interest).</li>
          </ul>
          <p>We do not sell your information, and we do not use it for advertising.</p>
        </>
      ),
    },
    {
      id: 'who-sees-it',
      title: 'Who can see it',
      body: (
        <ul>
          <li><strong>Your employer</strong> sees the training they assign and your progress on it. They never see courses you bought or joined yourself.</li>
          <li><strong>Instructors</strong> see the names and progress of learners on their own courses, and the questions, reviews and assignments sent to them.</li>
          <li><strong>Anyone with a certificate code</strong> can check that the certificate is genuine. The check shows the name on it, the course and the date.</li>
          <li><strong>Our staff</strong> see what they need to support you and keep the platform running. Every change they make is logged.</li>
        </ul>
      ),
    },
    {
      id: 'service-providers',
      title: 'Services we use',
      body: (
        <>
          <p>A few trusted companies process information for us, only on our instructions:</p>
          <ul>
            <li><strong>Stripe</strong> takes card payments on its own secure page. We never see or store your card number.</li>
            <li><strong>Bunny.net</strong> streams course videos.</li>
            <li><strong>Microsoft</strong> stores uploaded files (Azure) and sends our emails (Microsoft 365).</li>
            <li><strong>Neon</strong> hosts our database.</li>
            <li><strong>Breathe HR</strong>, only for companies that connect it. We read from it; we never write back.</li>
          </ul>
          <p>Where a provider handles information outside the UK, the transfer is protected by the safeguards UK law requires, such as approved contract terms.</p>
        </>
      ),
    },
    {
      id: 'cookies',
      title: 'Cookies and browser storage',
      body: (
        <>
          <p>We use only what the platform needs to work. There are no advertising or tracking cookies, and no analytics.</p>
          <ul>
            <li><strong>sessionid</strong> keeps you signed in. It lasts until you sign out, or for a set number of days.</li>
            <li><strong>csrftoken</strong> protects your forms from being sent by another website.</li>
            <li>Your browser also remembers a few choices on your device only: light or dark mode, your currency, the workspace you last used, and whether you closed the site banner.</li>
          </ul>
          <p>Stripe sets its own cookies on its payment page to prevent fraud. Its privacy policy explains them.</p>
        </>
      ),
    },
    {
      id: 'keeping-it',
      title: 'How long we keep it',
      body: (
        <p>
          We keep your information while your account is open. If you ask us to close your account, we delete your personal information, except the records the law
          says we must keep, such as invoices (normally six years). Certificates stay checkable for as long as they are valid, so an employer can still confirm them.
        </p>
      ),
    },
    {
      id: 'your-rights',
      title: 'Your rights',
      body: (
        <>
          <p>
            You can ask for a copy of your information, ask us to correct or delete it, object to how we use it, or ask us to limit its use. You can change your name and
            sign-in settings yourself on your <Link className="font-medium text-primary hover:underline" to="/account">Account</Link> page. For anything else,{' '}
            <ContactLine contact={contact} />. We reply within one month.
          </p>
          <p>
            If you are unhappy with our answer, you can complain to the Information Commissioner's Office at{' '}
            <a className="font-medium text-primary hover:underline" href="https://ico.org.uk/make-a-complaint/" target="_blank" rel="noreferrer">
              ico.org.uk
            </a>
            .
          </p>
        </>
      ),
    },
    {
      id: 'security',
      title: 'Keeping it safe',
      body: (
        <p>
          Everything travels over an encrypted connection. Passwords are hashed, 2-step sign-in is available, and each company's information is kept apart at
          database level, so one company can never read another's. Keys for our payment, video and file services stay on our servers and never reach your browser.
        </p>
      ),
    },
    {
      id: 'changes',
      title: 'Changes to this policy',
      body: <p>If we change how we use your information, we update this page and the date at the top. For important changes, we also tell you by email or notification.</p>,
    },
  ]
  return (
    <LegalLayout
      eyebrow="Privacy"
      title="Privacy policy"
      intro={<p>What information {name} keeps about you, why, who can see it, and the choices you have. We have kept it short and plain.</p>}
      sections={sections}
    />
  )
}

export function TermsPage() {
  const { settings } = usePublicSettings()
  const name = settings['general.platform_name']
  const contact = settings['general.contact_email']
  const refundDays = settings['payments.refund_window_days']
  const vat = settings['payments.prices_include_tax']
  const sections: Section[] = [
    {
      id: 'using',
      title: 'Using ' + name,
      body: (
        <p>
          By creating an account you agree to these terms. Keep your sign-in details to yourself and tell us straight away if you think someone else has used your
          account. You are responsible for what happens under your account. The details you give us must be accurate.
        </p>
      ),
    },
    {
      id: 'buying',
      title: 'Buying courses',
      body: (
        <>
          <p>
            Prices are shown before you pay{vat ? ' and include VAT' : ''}. Payment is taken by Stripe. Once paid, the course is yours to study for as long as the
            course page says. Most courses give lifetime access.
          </p>
          <p>
            {refundDays > 0 ? (
              <>
                Changed your mind? You can ask for a refund within <strong>{refundDays} days</strong> of buying, from your{' '}
                <Link className="font-medium text-primary hover:underline" to="/account/orders">purchase history</Link>. When a course is refunded, your access to it ends.
              </>
            ) : (
              <>Course purchases are not refundable, except where the law gives you a right to a refund.</>
            )}{' '}
            This does not affect your legal rights as a consumer.
          </p>
        </>
      ),
    },
    {
      id: 'subscriptions',
      title: 'Subscriptions',
      body: (
        <p>
          A subscription gives you every course marked "included" while it is active. It renews automatically at the price shown until you cancel. You can cancel at
          any time from your <Link className="font-medium text-primary hover:underline" to="/subscription">subscription page</Link>: you keep access until the end of the
          period you have paid for. If a free trial is offered, you are not charged when you cancel before it ends.
        </p>
      ),
    },
    {
      id: 'tokens',
      title: 'Tokens and course bundles',
      body: (
        <p>
          Tokens are bought in advance and spent to unlock a whole course or single lessons. They have no cash value and cannot be exchanged for money. A bundle is a
          set of courses sold together for one price. Unlocked lessons and bundle courses stay available for the period shown when you buy them.
        </p>
      ),
    },
    {
      id: 'companies',
      title: 'Company workspaces',
      body: (
        <p>
          If your employer gives you access, they decide which training you are asked to complete, and they can see your progress on it. They can remove you from their
          workspace. Training assigned by a company belongs to that company's account, not to yours. Your own purchases stay yours.
        </p>
      ),
    },
    {
      id: 'instructors',
      title: 'Teaching on ' + name,
      body: (
        <p>
          Instructors keep ownership of the courses they create. By publishing, you allow us to host, show and sell your course on the platform. New courses are
          reviewed before they go live. You must own, or have permission to use, everything you upload. Your earnings and payout dates are shown in your studio.
        </p>
      ),
    },
    {
      id: 'acceptable-use',
      title: 'Fair use',
      body: (
        <ul>
          <li>Course content is for your own learning. Do not copy, share or resell it, or share your account.</li>
          <li>Do not post anything unlawful, abusive, misleading or that infringes someone else's rights.</li>
          <li>Do not try to break, overload or get round the platform's security.</li>
        </ul>
      ),
    },
    {
      id: 'certificates',
      title: 'Certificates',
      body: (
        <p>
          A certificate shows that you completed a course on {name}. It is not a formal qualification unless the course page says so. We may withdraw a certificate
          that was earned by cheating.
        </p>
      ),
    },
    {
      id: 'ending',
      title: 'Ending your account',
      body: (
        <p>
          You can ask us to close your account at any time: <ContactLine contact={contact} />. We may suspend or close an account that breaks these terms. Where we
          can, we tell you why first.
        </p>
      ),
    },
    {
      id: 'liability',
      title: 'Our responsibility to you',
      body: (
        <p>
          We work hard to keep the platform available and accurate, but we cannot promise it will never be interrupted. We are not responsible for losses we could not
          reasonably foresee. Nothing in these terms limits our responsibility for anything the law does not allow us to limit.
        </p>
      ),
    },
    {
      id: 'law',
      title: 'Changes and the law',
      body: (
        <p>
          We may update these terms. If a change matters, we tell you before it applies. These terms are governed by the law of England and Wales. Our{' '}
          <Link className="font-medium text-primary hover:underline" to="/privacy">privacy policy</Link> explains how we use your information.
        </p>
      ),
    },
  ]
  return (
    <LegalLayout
      eyebrow="Terms"
      title="Terms of use"
      intro={<p>The rules for learning, buying and teaching on {name}, in plain English.</p>}
      sections={sections}
    />
  )
}
