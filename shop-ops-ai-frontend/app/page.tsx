'use client'

import { useEffect, useMemo, useState } from 'react'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Activity, ArrowUpRight, Bell, Check, ChevronDown, ChevronLeft, ChevronRight, CircleHelp, ClipboardCheck, Clock3, FileText, Filter, LayoutDashboard, Menu, MoreHorizontal, PackageSearch, PanelLeft, Plus, Search, Send, Settings2, ShieldCheck, Sparkles, Store, X } from 'lucide-react'
import { activity, navItems, roles, volume } from '@/lib/mock-data'
import { AuthError, getSession, login, logout, type Role, type Session } from '@/lib/auth'
import { streamChat, type ChatDone } from '@/lib/chat'
import type { CompensationProposal, PolicyEvidence } from '@/lib/types'
import { approveAction, listActions, rejectAction, type ActionSummary } from '@/lib/actions'
import { getOrder, type OrderTimelineResult } from '@/lib/orders'
import { getSellerMetrics, type SellerMetricsResult } from '@/lib/sellers'
import { listAuditEvents, type AuditEventSummary } from '@/lib/audit'

const iconMap: Record<string, any> = { LayoutDashboard, Sparkles, PackageSearch, Store, ClipboardCheck, ScrollText: FileText }

function Logo() { return <div className="flex items-center gap-2.5"><div className="logo-mark"><span /></div><span className="text-[15px] font-semibold tracking-[-0.03em]">ShopOps <span className="text-[#5c8676]">AI</span></span></div> }

function StatusBadge({ status }: { status: string }) { const tone = status === 'Delivered' || status === 'Approved' ? 'mint' : status === 'Shipped' || status === 'Pending' ? 'yellow' : status === 'Cancelled' || status === 'Rejected' ? 'coral' : 'peach'; return <span className={`status-badge ${tone}`}><span className="status-dot" />{status}</span> }

function Sidebar({ path, role, email, onLogout, collapsed, setCollapsed }: { path: string; role: Role; email: string; onLogout: () => void; collapsed: boolean; setCollapsed: (v: boolean) => void }) {
  const [menuOpen, setMenuOpen] = useState(false)
  return <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}><div className="sidebar-top"><Logo /><button className="icon-btn sidebar-toggle" onClick={() => setCollapsed(!collapsed)} aria-label="Toggle sidebar"><PanelLeft size={16} /></button></div><div className="workspace-pill"><div className="workspace-avatar">S</div><div className="min-w-0"><div className="text-xs font-semibold truncate">ShopOps workspace</div><div className="text-[10px] text-muted">Production demo</div></div><ChevronDown size={14} className="ml-auto text-muted" /></div><nav className="nav-list">{navItems.filter((item) => item.roles.includes(role)).map((item) => { const Icon = iconMap[item.icon]; const active = path === item.href || (path === '/dashboard' && item.href === '/dashboard'); return <a key={item.href} href={item.href} className={`nav-item ${active ? 'active' : ''}`}><Icon size={17} strokeWidth={active ? 2.2 : 1.8} /><span>{item.label}</span></a> })}</nav><div className="sidebar-bottom"><a className="nav-item"><CircleHelp size={17} /><span>Help center</span></a><a className="nav-item"><Settings2 size={17} /><span>Settings</span></a><div className="role-switcher"><button className="role-button" onClick={() => setMenuOpen(!menuOpen)}><div className="avatar">{email.slice(0, 2).toUpperCase()}</div><div className="min-w-0 text-left"><div className="text-xs font-semibold truncate">{email}</div><div className="text-[10px] text-muted truncate">{roles.find((r) => r.key === role)?.label}</div></div><ChevronDown size={14} className="ml-auto text-muted" /></button>{menuOpen && <div className="role-menu"><button onClick={onLogout}>Sign out</button></div>}</div></div></aside>
}

function TopHeader({ title, subtitle, onMenu }: { title: string; subtitle?: string; onMenu: () => void }) { return <header className="top-header"><button className="mobile-menu icon-btn" onClick={onMenu}><Menu size={19} /></button><div><div className="breadcrumbs"><span>Workspace</span><ChevronRight size={12} /><span className="font-medium text-ink">{title}</span></div>{subtitle && <p className="header-subtitle">{subtitle}</p>}</div><div className="header-actions"><button className="search-btn"><Search size={16} /><span>Search anything</span><kbd>⌘ K</kbd></button><button className="icon-btn relative"><Bell size={17} /><i className="notification-dot" /></button><div className="avatar">AM</div></div></header> }

function StatCard({ label, value, delta, icon, tone }: { label: string; value: string; delta: string; icon: React.ReactNode; tone: string }) { return <div className="stat-card"><div className={`stat-icon ${tone}`}>{icon}</div><div className="stat-label">{label}</div><div className="stat-value">{value}</div><div className="stat-delta"><ArrowUpRight size={13} />{delta}</div></div> }

function Citation({ citation }: { citation: PolicyEvidence }) {
  const [open, setOpen] = useState(false)
  return <div className="citation-wrap">
    <button className="citation" onClick={() => setOpen(!open)}><FileText size={13} />{citation.doc_id} <span>· {citation.section}</span></button>
    {open && <div className="citation-popover">
      <div className="flex justify-between"><span className="text-[10px] uppercase tracking-wider text-muted font-semibold">Policy evidence</span><button onClick={() => setOpen(false)}><X size={14} /></button></div>
      <div className="font-semibold text-sm mt-2">{citation.doc_id} <span className="text-muted font-normal">v{citation.version}</span></div>
      <div className="text-xs text-muted mt-1">{citation.section}</div>
      <p className="excerpt">&ldquo;{citation.excerpt}&rdquo;</p>
    </div>}
  </div>
}

function Proposal({ proposal }: { proposal: CompensationProposal }) {
  return <div className="proposal-card">
    <div className="proposal-head"><div><div className="section-kicker coral-text">Human approval required</div><h3>Compensation proposal</h3></div><span className="proposal-status">Submitted</span></div>
    <div className="proposal-grid">
      <div><span>Order</span><strong>{proposal.order_id}</strong></div>
      <div><span>Amount</span><strong>R$ {proposal.proposed_amount}</strong></div>
      <div><span>Policy</span><strong>{proposal.policy_doc_id} v{proposal.policy_version}</strong></div>
      <div><span>Severity</span><strong>{proposal.severity}</strong></div>
    </div>
    <div className="proposal-reason">Reason: {proposal.reason}</div>
    <div className="proposal-actions"><button className="primary-btn" disabled><Check size={15} />Awaiting manager approval</button></div>
  </div>
}

interface ChatMessageItem {
  role: 'user' | 'assistant'
  content: string
  citations?: PolicyEvidence[]
  proposal?: CompensationProposal | null
  error?: boolean
}

function ChatPage({ session }: { session: Session }) {
  const [messages, setMessages] = useState<ChatMessageItem[]>([])
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)

  const updateLastMessage = (updater: (m: ChatMessageItem) => ChatMessageItem) => {
    setMessages((prev) => {
      const next = [...prev]
      next[next.length - 1] = updater(next[next.length - 1])
      return next
    })
  }

  const sendMessage = async () => {
    const text = input.trim()
    if (!text || sending) return
    setInput('')
    setSending(true)
    setMessages((prev) => [...prev, { role: 'user', content: text }, { role: 'assistant', content: '' }])

    await streamChat(conversationId, text, {
      onChunk: (delta) => updateLastMessage((m) => ({ ...m, content: m.content + delta })),
      onDone: (result: ChatDone) => {
        setConversationId(result.conversationId)
        updateLastMessage((m) => ({ ...m, citations: result.citations, proposal: result.proposal }))
        setSending(false)
      },
      onError: (message) => {
        updateLastMessage(() => ({ role: 'assistant', content: message, error: true }))
        setSending(false)
      },
    })
  }

  const newChat = () => { setMessages([]); setConversationId(null) }

  return <div className="chat-layout">
    <div className="conversation-list">
      <div className="section-kicker">Investigations</div>
      <button className="new-chat" onClick={newChat}><Plus size={15} /> New investigation</button>
      <div className="conversation-footer">
        <div className="text-[10px] text-muted">Evidence-first operations</div>
        <div className="text-xs mt-2 leading-relaxed">Every answer is grounded in confirmed order data and policy evidence.</div>
      </div>
    </div>
    <div className="chat-main">
      <div className="chat-title"><div><div className="section-kicker">AI operations workspace</div><h1>Order investigation</h1></div></div>
      <div className="messages">
        {messages.length === 0 && <div className="text-sm text-muted px-2">Ask about an order, seller, policy, or delivery to get started.</div>}
        {messages.map((m, i) => m.role === 'user'
          ? <div className="user-message" key={i}>
              <div className="avatar small">{session.email.slice(0, 2).toUpperCase()}</div>
              <div><div className="message-meta">{session.email} · {session.role}</div><div className="user-bubble">{m.content}</div></div>
            </div>
          : <div className="ai-message" key={i}>
              <div className="ai-avatar"><Sparkles size={15} /></div>
              <div className="ai-content">
                <div className="message-meta">ShopOps AI <span className="live-dot" /> {m.error ? 'Error' : 'Evidence grounded'}</div>
                <p className="message-text">{m.content || (sending && i === messages.length - 1 ? '…' : '')}</p>
                {!!m.citations?.length && <div className="evidence-row"><div className="section-kicker">Policy evidence</div>{m.citations.map((c, ci) => <Citation key={ci} citation={c} />)}</div>}
                {m.proposal && <Proposal proposal={m.proposal} />}
              </div>
            </div>
        )}
      </div>
      <div className="chat-composer">
        <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && sendMessage()} placeholder="Ask about an order, seller, policy, or delivery…" disabled={sending} />
        <button className="send-btn" onClick={sendMessage} disabled={sending}><Send size={16} /></button>
      </div>
    </div>
  </div>
}

function Dashboard() { return <div className="page-content"><div className="page-intro"><div><div className="section-kicker">Tuesday, June 24, 2025</div><h1>Good morning, Alex</h1><p>Here&apos;s what&apos;s happening across operations.</p></div><a href="/dashboard/chat" className="primary-btn"><Sparkles size={15} />Ask ShopOps AI</a></div><div className="stat-grid"><StatCard label="Total orders" value="12,842" delta="8.2% vs last week" icon={<PackageSearch size={17} />} tone="mint" /><StatCard label="Pending approvals" value="3" delta="2 need attention" icon={<ClipboardCheck size={17} />} tone="yellow" /><StatCard label="Avg delivery time" value="3.4d" delta="0.3d faster" icon={<Clock3 size={17} />} tone="peach" /><StatCard label="Active sellers" value="284" delta="12 new this month" icon={<Store size={17} />} tone="coral" /></div><div className="dashboard-grid"><div className="soft-card chart-card"><div className="card-heading"><div><div className="section-kicker">Operations pulse</div><h2>Order volume</h2></div><button className="filter-pill">Last 7 days <ChevronDown size={13} /></button></div><ResponsiveContainer width="100%" height={250}><AreaChart data={volume} margin={{ left: -25, right: 8, top: 20 }}><defs><linearGradient id="mintArea" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#a8e6cf" stopOpacity={0.55} /><stop offset="95%" stopColor="#a8e6cf" stopOpacity={0.03} /></linearGradient></defs><CartesianGrid vertical={false} stroke="#e9efec" /><XAxis dataKey="day" tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: '#85938e' }} /><YAxis tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: '#85938e' }} /><Tooltip contentStyle={{ borderRadius: 10, border: '1px solid #e2ebe6', fontSize: 12 }} /><Area type="monotone" dataKey="orders" stroke="#559c83" strokeWidth={2.5} fill="url(#mintArea)" /></AreaChart></ResponsiveContainer></div><div className="soft-card activity-card"><div className="card-heading"><div><div className="section-kicker">Live feed</div><h2>Recent activity</h2></div><button className="icon-btn"><MoreHorizontal size={17} /></button></div><div>{activity.map((item) => <div className="activity-row" key={item.title}><div className={`activity-marker ${item.tone}`}><Check size={12} /></div><div className="flex-1 min-w-0"><div className="text-xs font-semibold">{item.title}</div><div className="text-[11px] text-muted mt-1 truncate">{item.detail}</div></div><time>{item.time}</time></div>)}</div><a href="/dashboard/audit" className="view-all">View audit log <ArrowUpRight size={13} /></a></div></div></div> }

function OrdersPage() {
  const [query, setQuery] = useState('')
  const [order, setOrder] = useState<OrderTimelineResult | null | undefined>(undefined)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const search = async () => {
    const id = query.trim()
    if (!id) return
    setLoading(true)
    setError(null)
    try {
      setOrder(await getOrder(id))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load order.')
      setOrder(undefined)
    } finally {
      setLoading(false)
    }
  }

  return <div className="page-content">
    <div className="page-intro compact">
      <div><div className="section-kicker">Operations / fulfillment</div><h1>Orders</h1><p>Look up an order by ID to investigate delivery status.</p></div>
    </div>
    <div className="soft-card table-card">
      <div className="table-toolbar">
        <div className="table-search"><Search size={15} /><input value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && search()} placeholder="Enter an order ID…" /></div>
        <button className="primary-btn" onClick={search} disabled={loading}>{loading ? 'Searching…' : 'Search'}</button>
      </div>
      {error && <p className="text-xs coral-text mt-2">{error}</p>}
      {order === null && <p className="text-sm text-muted mt-2">No order found with that ID.</p>}
    </div>
    {order && <div className="soft-card p-4 mt-4">
      <div className="flex items-center justify-between mb-3">
        <div><div className="section-kicker">Order</div><div className="font-semibold mt-1">{order.order_id} <span className="text-muted font-normal">· {order.seller_count} seller(s)</span></div></div>
        <StatusBadge status={order.order_status} />
      </div>
      <div className="detail-list">
        <div><span>Order value</span><strong>R$ {Number(order.order_value).toFixed(2)}</strong></div>
        <div><span>Purchase date</span><strong>{new Date(order.purchase_timestamp).toLocaleString()}</strong></div>
        <div><span>Estimated delivery</span><strong>{new Date(order.estimated_delivery_date).toLocaleString()}</strong></div>
        <div><span>Delivered</span><strong>{order.delivered_customer_date ? new Date(order.delivered_customer_date).toLocaleString() : '—'}</strong></div>
      </div>
      <a href="/dashboard/chat" className="primary-btn w-full justify-center mt-4">Investigate with AI <Sparkles size={15} /></a>
    </div>}
  </div>
}

function SellersPage() {
  const [query, setQuery] = useState('')
  const [seller, setSeller] = useState<SellerMetricsResult | null | undefined>(undefined)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const search = async () => {
    const id = query.trim()
    if (!id) return
    setLoading(true)
    setError(null)
    try {
      setSeller(await getSellerMetrics(id))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load seller.')
      setSeller(undefined)
    } finally {
      setLoading(false)
    }
  }

  return <div className="page-content">
    <div className="page-intro compact">
      <div><div className="section-kicker">Manager workspace</div><h1>Seller performance</h1><p>Look up a seller by ID for their performance metrics.</p></div>
    </div>
    <div className="soft-card table-card">
      <div className="table-toolbar">
        <div className="table-search"><Search size={15} /><input value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && search()} placeholder="Enter a seller ID…" /></div>
        <button className="primary-btn" onClick={search} disabled={loading}>{loading ? 'Searching…' : 'Search'}</button>
      </div>
      {error && <p className="text-xs coral-text mt-2">{error}</p>}
      {seller === null && <p className="text-sm text-muted mt-2">No seller found with that ID.</p>}
    </div>
    {seller && <div className="soft-card p-4 mt-4">
      <div className="font-semibold mb-3">{seller.seller_id}</div>
      <div className="detail-list">
        <div><span>Total orders</span><strong>{seller.order_count}</strong></div>
        <div><span>Late delivery rate</span><strong>{(seller.late_delivery_rate * 100).toFixed(1)}%</strong></div>
        <div><span>Avg review score</span><strong>{seller.avg_review_score != null ? seller.avg_review_score.toFixed(1) : '—'}</strong></div>
      </div>
    </div>}
  </div>
}

type ApprovalTab = 'pending' | 'approved' | 'rejected' | 'expired'

function ApprovalsPage() {
  const [tab, setTab] = useState<ApprovalTab>('pending')
  const [proposed, setProposed] = useState<ActionSummary[]>([])
  const [succeeded, setSucceeded] = useState<ActionSummary[]>([])
  const [rejected, setRejected] = useState<ActionSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actingOn, setActingOn] = useState<string | null>(null)

  const loadAll = async () => {
    setLoading(true)
    setError(null)
    try {
      const [p, s, r] = await Promise.all([listActions('PROPOSED'), listActions('SUCCEEDED'), listActions('REJECTED')])
      setProposed(p)
      setSucceeded(s)
      setRejected(r)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load approvals.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadAll() }, [])

  const pending = proposed.filter((a) => !a.is_expired)
  const expired = proposed.filter((a) => a.is_expired)
  const byTab: Record<ApprovalTab, ActionSummary[]> = { pending, approved: succeeded, rejected, expired }

  const act = async (actionId: string, fn: (id: string) => Promise<void>, failMessage: string) => {
    setActingOn(actionId)
    setError(null)
    try {
      await fn(actionId)
      await loadAll()
    } catch (err) {
      setError(err instanceof Error ? err.message : failMessage)
    } finally {
      setActingOn(null)
    }
  }

  const list = byTab[tab]

  return <div className="page-content">
    <div className="page-intro compact">
      <div><div className="section-kicker">Human in the loop</div><h1>Approval queue</h1><p>Review proposed customer compensation before any action is taken.</p></div>
      <div className="queue-count"><span>{pending.length}</span> pending review</div>
    </div>
    <div className="tabs">
      <button className={tab === 'pending' ? 'active' : ''} onClick={() => setTab('pending')}>Pending <span>{pending.length}</span></button>
      <button className={tab === 'approved' ? 'active' : ''} onClick={() => setTab('approved')}>Approved</button>
      <button className={tab === 'rejected' ? 'active' : ''} onClick={() => setTab('rejected')}>Rejected</button>
      <button className={tab === 'expired' ? 'active' : ''} onClick={() => setTab('expired')}>Expired</button>
    </div>
    {error && <p className="text-xs coral-text mt-2">{error}</p>}
    {loading
      ? <p className="text-sm text-muted mt-4">Loading…</p>
      : <div className="approval-list">
          {list.length === 0 && <p className="text-sm text-muted mt-4">Nothing here.</p>}
          {list.map((a) => <div className={`approval-card ${tab === 'pending' ? 'expiring' : ''}`} key={a.action_id}>
            <div className="approval-top">
              <div><div className="section-kicker">Compensation proposal</div><h3>{a.order_id} <span>· submitted by {a.requested_by}</span></h3></div>
              <StatusBadge status={a.status === 'SUCCEEDED' ? 'Approved' : a.status === 'REJECTED' ? 'Rejected' : a.is_expired ? 'Cancelled' : 'Pending'} />
            </div>
            <div className="approval-details">
              <div><span>Amount</span><strong>{a.proposed_amount ? `R$ ${Number(a.proposed_amount).toFixed(2)}` : '—'}</strong></div>
              <div><span>Policy</span><strong>v{a.policy_version}</strong></div>
              <div><span>Severity</span><strong>{a.severity ?? '—'}</strong></div>
              <div><span>Expires</span><strong className={tab === 'pending' ? 'coral-text' : ''}>{a.status === 'PROPOSED' && a.expires_at ? new Date(a.expires_at).toLocaleString() : '—'}</strong></div>
            </div>
            {a.reason && <div className="approval-reason">{a.reason}</div>}
            {tab === 'pending' && <div className="approval-actions">
              <button className="primary-btn" onClick={() => act(a.action_id, approveAction, 'Approve failed.')} disabled={actingOn === a.action_id}><Check size={14} />Approve proposal</button>
              <button className="text-btn" onClick={() => act(a.action_id, rejectAction, 'Reject failed.')} disabled={actingOn === a.action_id}>Reject</button>
            </div>}
          </div>)}
        </div>}
  </div>
}

function AuditPage() {
  const [events, setEvents] = useState<AuditEventSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listAuditEvents()
      .then(setEvents)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load audit events.'))
      .finally(() => setLoading(false))
  }, [])

  return <div className="page-content">
    <div className="page-intro compact">
      <div><div className="section-kicker">Governance &amp; compliance</div><h1>Audit log</h1><p>An append-only record of agent actions and evidence access.</p></div>
    </div>
    {error && <p className="text-xs coral-text mb-2">{error}</p>}
    <div className="soft-card audit-card">
      <div className="audit-header"><div className="section-kicker">Activity timeline</div><span className="text-xs text-muted">{events.length} events</span></div>
      {loading && <p className="text-sm text-muted py-2">Loading…</p>}
      {!loading && events.length === 0 && <p className="text-sm text-muted py-2">No activity yet.</p>}
      {events.map((entry) => <div className="audit-row" key={entry.event_id}>
        <div className={`audit-icon ${entry.outcome === 'denied' ? 'denied' : ''}`}>{entry.outcome === 'denied' ? <X size={13} /> : <Check size={13} />}</div>
        <div className="audit-time">{new Date(entry.occurred_at).toLocaleString()}</div>
        <div className="audit-main"><div><code>{entry.tool_name}</code></div><div className="text-xs text-muted mt-1">{entry.user_id} · {entry.role_snapshot}</div></div>
        <span className={`outcome ${entry.outcome === 'denied' ? 'denied-text' : ''}`}>{entry.outcome}</span>
      </div>)}
    </div>
  </div>
}

function Login({ onLogin }: { onLogin: () => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async () => {
    setError(null)
    setLoading(true)
    try {
      await login(email, password)
      onLogin()
    } catch (err) {
      setError(err instanceof AuthError ? err.message : 'Something went wrong. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return <main className="login-page"><div className="login-grid" /><div className="login-card"><Logo /><div className="login-copy"><div className="section-kicker">Operations, with evidence.</div><h1>Welcome back</h1><p>Sign in to your operations workspace.</p></div><label>Email<input value={email} onChange={(e) => setEmail(e.target.value)} type="email" /></label><label>Password<input value={password} onChange={(e) => setPassword(e.target.value)} type="password" onKeyDown={(e) => e.key === 'Enter' && handleSubmit()} /></label>{error && <p className="text-xs coral-text">{error}</p>}<button className="primary-btn w-full justify-center" onClick={handleSubmit} disabled={loading}>{loading ? 'Signing in…' : <>Sign in <ArrowUpRight size={15} /></>}</button><div className="login-foot"><ShieldCheck size={14} /> Secure workspace</div></div></main>
}

export default function Page() {
  const [path, setPath] = useState('/login')
  const [session, setSession] = useState<Session | null>(null)
  const [checked, setChecked] = useState(false)
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => {
    const existing = getSession()
    setSession(existing)
    const requestedPath = window.location.pathname === '/' ? '/dashboard' : window.location.pathname
    setPath(existing ? requestedPath : '/login')
    setChecked(true)
  }, [])

  const navigate = (href: string) => { window.history.pushState({}, '', href); setPath(href); setMobileOpen(false) }

  const handleLogin = () => {
    setSession(getSession())
    navigate('/dashboard')
  }

  const handleLogout = () => {
    logout()
    setSession(null)
    navigate('/login')
  }

  if (!checked) return null
  if (!session || path === '/login') return <Login onLogin={handleLogin} />

  const page = path === '/dashboard/chat' ? <ChatPage session={session} /> : path === '/dashboard/orders' ? <OrdersPage /> : path === '/dashboard/sellers' ? <SellersPage /> : path === '/dashboard/approvals' ? <ApprovalsPage /> : path === '/dashboard/audit' ? <AuditPage /> : <Dashboard />
  const title = path === '/dashboard/chat' ? 'AI Chat' : path.split('/').pop()?.replace('-', ' ') || 'Dashboard'
  return <div className="app-shell"><div className={`sidebar-mobile-overlay ${mobileOpen ? 'open' : ''}`} onClick={() => setMobileOpen(false)} /><div className={`sidebar-wrap ${mobileOpen ? 'mobile-open' : ''}`}><Sidebar path={path} role={session.role} email={session.email} onLogout={handleLogout} collapsed={collapsed} setCollapsed={setCollapsed} /></div><div className="main-shell"><TopHeader title={title} onMenu={() => setMobileOpen(!mobileOpen)} /><main>{page}</main></div></div>
}
