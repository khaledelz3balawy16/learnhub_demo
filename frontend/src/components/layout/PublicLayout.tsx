import { BookOpen, Building2, LayoutGrid, Search, ShoppingCart } from 'lucide-react'
import { type FormEvent, type KeyboardEvent, useCallback, useEffect, useId, useState } from 'react'
import { Outlet, useSearchParams } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Logo } from '@/components/ui/logo'
import { ThemeToggle } from '@/components/ui/theme-toggle'
import { useCategories, useSearchSuggestions } from '@/features/catalog/api'
import { useCartCount } from '@/features/commerce/api'
import { useMe } from '@/features/identity/auth'
import { usePublicSettings } from '@/features/platform/api'
import { cn } from '@/lib/cn'
import { useOn } from '@/lib/motion'

import { AdminButtons } from './AdminButtons'
import { BottomNav } from './BottomNav'
import { CurrencyMenu } from './CurrencyMenu'
import { NotificationBell } from './NotificationBell'
import { UserMenu } from './UserMenu'
import { Link, NavLink, useNavigate } from '@/lib/router'

const YEAR = new Date().getFullYear()

/** The cart icon shows how many courses are in it, and bounces when one is added. */
function CartButton() {
  const [n, setN] = useState(0)
  useOn('cart:added', useCallback(() => setN((x) => x + 1), []))
  const { data } = useCartCount()
  const count = data?.count ?? 0
  return (
    <Button variant="ghost" size="icon" asChild aria-label={count ? `Cart, ${count} ${count === 1 ? 'course' : 'courses'}` : 'Cart'} className="relative">
      <Link to="/cart">
        <ShoppingCart key={n} className={n ? 'animate-bounce-once' : undefined} />
        {count ? (
          <span key={`c${count}`} className="absolute top-1 right-0.5 flex h-[18px] min-w-[18px] animate-pop items-center justify-center rounded-full bg-primary px-1 text-[10px] font-bold text-on-primary ring-2 ring-surface tabular">
            {count}
          </span>
        ) : null}
      </Link>
    </Button>
  )
}

type Suggestion = { key: string; label: string; kind: string; to: string; thumb?: string | null }

/** Header search with instant suggestions (mockup 37): matching categories and courses as you
 * type, plus "Search for …". A combobox: arrows move, Enter opens, Escape closes. */
function SearchBox({ className, autoFocus }: { className?: string; autoFocus?: boolean }) {
  const [params] = useSearchParams()
  const [q, setQ] = useState(params.get('q') ?? '')
  const [debounced, setDebounced] = useState(q.trim())
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const navigate = useNavigate()
  const listId = useId()
  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 200)
    return () => clearTimeout(t)
  }, [q])
  const { data: cats } = useCategories()
  const courses = useSearchSuggestions(debounced)
  // new results can reorder the list: never keep a highlight that now points at something else
  useEffect(() => setActive(-1), [debounced, courses.data])
  const term = q.trim()
  const needle = debounced.toLowerCase()
  const options: Suggestion[] =
    term.length < 2
      ? []
      : [
          ...(cats ?? []).filter((c) => needle.length >= 2 && c.name.toLowerCase().includes(needle)).slice(0, 2).map((c) => ({ key: `cat-${c.slug}`, label: c.name, kind: 'Category', to: `/courses?category=${encodeURIComponent(c.slug)}` })),
          ...(courses.data?.items ?? []).map((c) => ({ key: c.id, label: c.title, kind: 'Course', to: `/courses/${c.slug}`, thumb: c.thumbnail_url })),
          { key: 'search', label: `Search for “${term}”`, kind: '', to: `/courses?q=${encodeURIComponent(term)}` },
        ]
  const show = open && options.length > 0
  const go = (to: string) => {
    setOpen(false)
    setActive(-1)
    navigate(to)
  }
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (show && active >= 0) return go(options[active]!.to)
    go(term ? `/courses?q=${encodeURIComponent(term)}` : '/courses')
  }
  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') return setOpen(false)
    if (!options.length || (e.key !== 'ArrowDown' && e.key !== 'ArrowUp')) return
    e.preventDefault()
    setOpen(true)
    setActive((i) => (e.key === 'ArrowDown' ? (i + 1) % options.length : (i <= 0 ? options.length : i) - 1))
  }
  return (
    <form role="search" onSubmit={submit} className={cn('relative', className)}>
      <Input
        icon={<Search />}
        value={q}
        onChange={(e) => {
          setQ(e.target.value)
          setOpen(true)
          setActive(-1)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
        placeholder="Search for courses, topics or instructors"
        aria-label="Search courses"
        role="combobox"
        aria-expanded={show}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={show && active >= 0 ? `${listId}-${active}` : undefined}
        autoComplete="off"
        autoFocus={autoFocus}
        className="rounded-full bg-surface-2/60"
      />
      {show ? (
        <ul id={listId} role="listbox" aria-label="Suggestions" className="absolute inset-x-0 top-full z-50 mt-2 animate-reveal overflow-hidden rounded-xl border border-border bg-surface py-1 shadow-lg">
          {options.map((o, i) => (
            <li
              key={o.key}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              // mousedown, not click: it fires before the input's blur closes the list
              onMouseDown={(e) => {
                e.preventDefault()
                go(o.to)
              }}
              onMouseEnter={() => setActive(i)}
              className={cn('flex cursor-pointer items-center gap-3 px-3 py-2 text-sm', i === active && 'bg-primary-soft text-primary-soft-text', o.key === 'search' && 'border-t border-border text-muted')}
            >
              {o.kind === 'Course' ? (
                o.thumb ? <img src={o.thumb} alt="" loading="lazy" className="h-8 w-12 shrink-0 rounded object-cover" /> : <BookOpen className="size-4 shrink-0 text-subtle" aria-hidden />
              ) : o.kind === 'Category' ? (
                <LayoutGrid className="size-4 shrink-0 text-primary" aria-hidden />
              ) : (
                <Search className="size-4 shrink-0" aria-hidden />
              )}
              <span className="min-w-0 flex-1 truncate font-medium">{o.label}</span>
              {o.kind ? <span className="shrink-0 text-xs text-subtle">{o.kind}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </form>
  )
}

type FooterLink = { label: string; to: string }

/** Footer columns. Mail links use the contact email from console > Settings and are left
 * out while it is empty, so no link ever points at an address nobody reads. */
function footerColumns(contact: string): { title: string; links: FooterLink[] }[] {
  const mail = (subject: string) => (contact ? `mailto:${contact}?subject=${encodeURIComponent(subject)}` : '')
  const keep = (links: FooterLink[]) => links.filter((l) => l.to)
  return [
    { title: 'Learn', links: [{ label: 'Browse courses', to: '/courses' }, { label: 'Plans and pricing', to: '/plans' }, { label: 'Verify a certificate', to: '/verify' }] },
    { title: 'Business', links: keep([{ label: 'Training for teams', to: '/plans#teams' }, { label: 'Book a demo', to: mail('LearnHub demo') }]) },
    { title: 'LearnHub', links: keep([{ label: 'Teach on LearnHub', to: '/teach' }, { label: 'Help centre', to: '/support' }, { label: 'Contact us', to: mail('Hello') }]) },
    { title: 'Legal', links: [{ label: 'Privacy policy', to: '/privacy' }, { label: 'Terms of use', to: '/terms' }, { label: 'Cookies', to: '/privacy#cookies' }] },
  ]
}

/** Marketplace pages: top navigation, footer; phones get the learner bottom bar. */
export function PublicLayout() {
  const { data: me, isLoading } = useMe()
  const { settings } = usePublicSettings()
  const footer = footerColumns(settings['general.contact_email'])
  const [searchOpen, setSearchOpen] = useState(false)
  const link = ({ isActive }: { isActive: boolean }) => cn('rounded-md px-3 py-2 text-sm font-medium transition-colors', isActive ? 'text-primary' : 'text-muted hover:text-text')

  return (
    <div className="flex min-h-dvh flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2">
        Skip to content
      </a>
      <header className="vt-header sticky top-0 z-40 border-b border-border bg-surface/90 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-3 px-4 sm:px-6">
          <Link to="/" aria-label="LearnHub home" className="shrink-0">
            <Logo />
          </Link>
          <nav className="ml-4 hidden items-center lg:flex" aria-label="Primary">
            <NavLink to="/courses" className={link}>Courses</NavLink>
            <NavLink to="/plans" className={link}>Plans</NavLink>
            {me ? <NavLink to="/learn" className={link}>My learning</NavLink> : null}
          </nav>
          <SearchBox className="mx-4 hidden max-w-md flex-1 md:block" />
          <div className="ml-auto flex items-center gap-1">
            <Button variant="ghost" size="icon" className="md:hidden" aria-label="Search" onClick={() => setSearchOpen((v) => !v)}>
              <Search />
            </Button>
            <span className="hidden sm:inline-flex">
              <CurrencyMenu />
            </span>
            <ThemeToggle />
            <CartButton />
            {me ? <AdminButtons /> : null}
            {me ? <NotificationBell /> : null}
            {isLoading ? null : me ? (
              <UserMenu />
            ) : (
              <>
                {/* companies have their own way in: the log-in page opens on its organisation side */}
                <Button variant="secondary" size="sm" asChild className="mr-1 hidden lg:inline-flex">
                  <Link to="/login?as=org">
                    <Building2 /> For organisations
                  </Link>
                </Button>
                <Button variant="ghost" asChild className="hidden sm:inline-flex">
                  <Link to="/login">Log in</Link>
                </Button>
                <Button asChild size="sm" className="sm:h-10 sm:px-4 sm:text-sm">
                  <Link to="/signup">Sign up</Link>
                </Button>
              </>
            )}
          </div>
        </div>
        {searchOpen ? <SearchBox className="border-t border-border px-4 py-3 md:hidden" autoFocus /> : null}
      </header>

      <main id="main" className={cn('flex-1', me && 'pb-16 md:pb-0')}>
        <Outlet />
      </main>

      <footer className={cn('border-t border-border bg-surface', me && 'pb-16 md:pb-0')}>
        <div className="mx-auto grid max-w-7xl gap-8 px-4 py-10 sm:px-6 sm:grid-cols-2 md:grid-cols-[1.5fr_1fr_1fr_1fr_1fr]">
          <div>
            <Logo />
            <p className="mt-3 max-w-xs text-sm text-muted">Courses from expert instructors, and compliance training your whole team can keep up with.</p>
          </div>
          {footer.map(({ title, links }) => (
            <div key={title}>
              <p className="text-sm font-semibold">{title}</p>
              <ul className="mt-3 grid gap-2 text-sm text-muted">
                {links.map(({ label, to }) => (
                  <li key={label}>
                    {to.startsWith('mailto:') ? (
                      <a href={to} className="rounded-sm transition-colors hover:text-text">{label}</a>
                    ) : (
                      <Link to={to} className="rounded-sm transition-colors hover:text-text">{label}</Link>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <p className="border-t border-border py-4 text-center text-xs text-subtle">© {YEAR} {settings['general.platform_name']}. All rights reserved.</p>
      </footer>
      {me ? <BottomNav /> : null}
    </div>
  )
}
