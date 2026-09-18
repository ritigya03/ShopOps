'use client'

import { useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Activity, ArrowUpRight, Bell, Check, ChevronDown, ChevronLeft, ChevronRight, CircleHelp, ClipboardCheck, Clock3, FileText, Filter, LayoutDashboard, Menu, MoreHorizontal, PackageSearch, PanelLeft, Plus, Search, Send, Settings2, ShieldCheck, Sparkles, Store, X } from 'lucide-react'
import { activity, auditEntries, navItems, orders, roles, sellers, timeline, volume } from '@/lib/mock-data'
import { AuthError, getSession, login, logout, type Role, type Session } from '@/lib/auth'
import { streamChat, type ChatDone } from '@/lib/chat'
import type { CompensationProposal, PolicyEvidence } from '@/lib/types'

const iconMap: Record<string, any> = { LayoutDashboard, Sparkles, PackageSearch, Store, ClipboardCheck, ScrollText: FileText }

function Logo() { return <div className="flex items-center gap-2.5"><div className="logo-mark"><span /></div><span className="text-[15px] font-semibold tracking-[-0.03em]">ShopOps <span className="text-[#5c8676]">AI</span></span></div> }

function StatusBadge({ status }: { status: string }) { const tone = status === 'Delivered' || status === 'Approved' ? 'mint' : status === 'Shipped' || status === 'Pending' ? 'yellow' : status === 'Cancelled' || status === 'Rejected' ? 'coral' : 'peach'; return <span className={`status-badge ${tone}`}><span className="status-dot" />{status}</span> }

function Sidebar({ path, role, email, onLogout, collapsed, setCollapsed }: { path: string; role: Role; email: string; onLogout: () => void; collapsed: boolean; setCollapsed: (v: boolean) => void }) {
  const [menuOpen, setMenuOpen] = useState(false)
  return <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}><div className="sidebar-top"><Logo /><button className="icon-btn sidebar-toggle" onClick={() => setCollapsed(!collapsed)} aria-label="Toggle sidebar"><PanelLeft size={16} /></button></div><div className="workspace-pill"><div className="workspace-avatar">S</div><div className="min-w-0"><div className="text-xs font-semibold truncate">ShopOps workspace</div><div className="text-[10px] text-muted">Production demo</div></div><ChevronDown size={14} className="ml-auto text-muted" /></div><nav className="nav-list">{navItems.filter((item) => item.roles.includes(role)).map((item) => { const Icon = iconMap[item.icon]; const active = path === item.href || (path === '/dashboard' && item.href === '/dashboard'); return <a key={item.href} href={item.href} className={`nav-item ${active ? 'active' : ''}`}><Icon size={17} strokeWidth={active ? 2.2 : 1.8} /><span>{item.label}</span>{item.label === 'Approvals' && <span className="nav-count">3</span>}</a> })}</nav><div className="sidebar-bottom"><a className="nav-item"><CircleHelp size={17} /><span>Help center</span></a><a className="nav-item"><Settings2 size={17} /><span>Settings</span></a><div className="role-switcher"><button className="role-button" onClick={() => setMenuOpen(!menuOpen)}><div className="avatar">{email.slice(0, 2).toUpperCase()}</div><div className="min-w-0 text-left"><div className="text-xs font-semibold truncate">{email}</div><div className="text-[10px] text-muted truncate">{roles.find((r) => r.key === role)?.label}</div></div><ChevronDown size={14} className="ml-auto text-muted" /></button>{menuOpen && <div className="role-menu"><button onClick={onLogout}>Sign out</button></div>}</div></div></aside>
}

function TopHeader({ title, subtitle, onMenu }: { title: string; subtitle?: string; onMenu: () => void }) { return <header className="top-header"><button className="mobile-menu icon-btn" onClick={onMenu}><Menu size={19} /></button><div><div className="breadcrumbs"><span>Workspace</span><ChevronRight size={12} /><span className="font-medium text-ink">{title}</span></div>{subtitle && <p className="header-subtitle">{subtitle}</p>}</div><div className="header-actions"><button className="search-btn"><Search size={16} /><span>Search anything</span><kbd>⌘ K</kbd></button><button className="icon-btn relative"><Bell size={17} /><i className="notification-dot" /></button><div className="avatar">AM</div></div></header> }

function StatCard({ label, value, delta, icon, tone }: { label: string; value: string; delta: string; icon: React.ReactNode; tone: string }) { return <div className="stat-card"><div className={`stat-icon ${tone}`}>{icon}</div><div className="stat-label">{label}</div><div className="stat-value">{value}</div><div className="stat-delta"><ArrowUpRight size={13} />{delta}</div></div> }

function Timeline() { return <div className="timeline">{timeline.map((step, i) => <div className="timeline-step" key={step.label}><div className={`timeline-node ${step.state}`}>{step.state === 'complete' ? <Check size={12} /> : step.state === 'current' ? <span /> : null}</div>{i < timeline.length - 1 && <div className={`timeline-line ${step.state === 'pending' ? 'pending' : ''}`} />}<div className="timeline-copy"><div className="text-xs font-semibold">{step.label}</div><div className="text-[10px] text-muted mt-1">{step.date}</div></div></div>)}</div> }

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

function OrdersPage() { const [selected, setSelected] = useState<any>(null); const [query, setQuery] = useState(''); const filtered = orders.filter((o) => o.id.includes(query.toLowerCase()) || o.seller.toLowerCase().includes(query.toLowerCase())); return <div className="page-content"><div className="page-intro compact"><div><div className="section-kicker">Operations / fulfillment</div><h1>Orders</h1><p>Investigate delivery status and customer outcomes.</p></div><button className="outline-btn"><Filter size={14} />Filters</button></div><div className="soft-card table-card"><div className="table-toolbar"><div className="table-search"><Search size={15} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search order or seller" /></div><div className="toolbar-right"><button className="filter-pill">All statuses <ChevronDown size={13} /></button><button className="icon-btn"><MoreHorizontal size={17} /></button></div></div><div className="table-wrap"><table><thead><tr><th>Order ID</th><th>Status</th><th>Purchase date</th><th>Estimated delivery</th><th>Seller</th><th>Value</th><th>State</th></tr></thead><tbody>{filtered.map((order) => <tr key={order.id} onClick={() => setSelected(order)}><td className="font-semibold">{order.id}</td><td><StatusBadge status={order.status} /></td><td>{order.purchase}</td><td>{order.eta}</td><td>{order.seller}</td><td className="font-medium">{order.value}</td><td><span className={order.state === 'Delayed' ? 'coral-text' : 'muted-state'}>{order.state}</span></td></tr>)}</tbody></table></div></div><AnimatePresence>{selected && <><motion.div className="drawer-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setSelected(null)} /><motion.aside className="order-drawer" initial={{ x: 420 }} animate={{ x: 0 }} exit={{ x: 420 }}><div className="drawer-head"><div><div className="section-kicker">Order investigation</div><h2>{selected.id}</h2></div><button className="icon-btn" onClick={() => setSelected(null)}><X size={17} /></button></div><StatusBadge status={selected.status} /><div className="drawer-section"><div className="section-kicker">Timeline</div><Timeline /></div><div className="drawer-section"><div className="section-kicker">Order details</div><div className="detail-list"><div><span>Seller</span><strong>{selected.seller}</strong></div><div><span>Order value</span><strong>{selected.value}</strong></div><div><span>Payment</span><strong>Pix</strong></div><div><span>Purchase date</span><strong>{selected.purchase}</strong></div><div><span>Estimated delivery</span><strong>{selected.eta}</strong></div></div></div><a href="/dashboard/chat" className="primary-btn w-full justify-center">Investigate with AI <Sparkles size={15} /></a></motion.aside></>}</AnimatePresence></div> }

function SellersPage() { return <div className="page-content"><div className="page-intro compact"><div><div className="section-kicker">Manager workspace</div><h1>Seller performance</h1><p>Aggregate performance signals across your marketplace.</p></div><button className="outline-btn"><Filter size={14} />Filters</button></div><div className="stat-grid seller-stats"><StatCard label="Total sellers" value="284" delta="12 new this month" icon={<Store size={17} />} tone="mint" /><StatCard label="Avg late delivery" value="12.8%" delta="1.4% improvement" icon={<Clock3 size={17} />} tone="yellow" /><StatCard label="Avg review score" value="4.6 / 5" delta="0.2 vs last month" icon={<Activity size={17} />} tone="peach" /></div><div className="soft-card table-card"><div className="card-heading"><div><div className="section-kicker">Marketplace health</div><h2>Seller directory</h2></div><div className="text-xs text-muted">Updated 12 min ago</div></div><div className="table-wrap"><table><thead><tr><th>Seller ID</th><th>City</th><th>State</th><th>Total orders</th><th>Late delivery</th><th>Review score</th><th /></tr></thead><tbody>{sellers.map((seller) => <tr key={seller.id}><td className="font-semibold">{seller.id}</td><td>{seller.city}</td><td>{seller.state}</td><td>{seller.orders}</td><td><span className={`rate ${seller.late > 20 ? 'high' : seller.late >= 10 ? 'medium' : 'low'}`}>{seller.late}%</span></td><td><span className="score">{seller.score}</span></td><td><a href="/dashboard/chat" className="ask-link">Ask AI <ArrowUpRight size={13} /></a></td></tr>)}</tbody></table></div></div></div> }

function ApprovalsPage() { const [approved, setApproved] = useState(false); return <div className="page-content"><div className="page-intro compact"><div><div className="section-kicker">Human in the loop</div><h1>Approval queue</h1><p>Review proposed customer compensation before any action is taken.</p></div><div className="queue-count"><span>3</span> pending review</div></div><div className="tabs"><button className="active">Pending <span>3</span></button><button>Approved</button><button>Rejected</button><button>Expired</button></div><div className="approval-list"><div className={`approval-card ${!approved ? 'expiring' : ''}`}><div className="approval-top"><div><div className="section-kicker">Compensation proposal</div><h3>e48151c <span>· submitted by Alex Morgan</span></h3></div><StatusBadge status={approved ? 'Approved' : 'Pending'} /></div><div className="approval-details"><div><span>Amount</span><strong>R$ 75</strong></div><div><span>Policy reference</span><strong>Refund Policy v2.1 §4.1</strong></div><div><span>Evidence</span><strong>3 sources</strong></div><div><span>Expires</span><strong className={!approved ? 'coral-text' : ''}>{approved ? '—' : '14:32'}</strong></div></div><div className="approval-reason">Delivery delay beyond policy threshold. Customer has no previous compensation claims.</div><div className="approval-actions"><button className="outline-btn"><FileText size={14} />View evidence</button>{!approved && <><button className="primary-btn" onClick={() => setApproved(true)}><Check size={14} />Approve proposal</button><button className="text-btn">Reject</button></>}</div></div><div className="approval-card"><div className="approval-top"><div><div className="section-kicker">Compensation proposal</div><h3>8f2a9d1 <span>· submitted by Jordan Lee</span></h3></div><StatusBadge status="Pending" /></div><div className="approval-details"><div><span>Amount</span><strong>R$ 120</strong></div><div><span>Policy reference</span><strong>Refund Policy v2.1 §4.1</strong></div><div><span>Evidence</span><strong>4 sources</strong></div><div><span>Expires</span><strong>2h 08m</strong></div></div><div className="approval-actions"><button className="outline-btn"><FileText size={14} />View evidence</button><button className="primary-btn">Review proposal <ArrowUpRight size={14} /></button></div></div></div></div> }

function AuditPage() { return <div className="page-content"><div className="page-intro compact"><div><div className="section-kicker">Governance & compliance</div><h1>Audit log</h1><p>An append-only record of agent actions and evidence access.</p></div><button className="outline-btn"><Filter size={14} />Filters</button></div><div className="audit-filters"><button className="filter-pill">Action type <ChevronDown size={13} /></button><button className="filter-pill">Outcome <ChevronDown size={13} /></button><button className="filter-pill">User <ChevronDown size={13} /></button><div className="ml-auto text-xs text-muted">Showing last 30 days</div></div><div className="soft-card audit-card"><div className="audit-header"><div className="section-kicker">Activity timeline</div><span className="text-xs text-muted">5 events</span></div>{auditEntries.map((entry, i) => <div className="audit-row" key={i}><div className={`audit-icon ${entry.outcome === 'Denied' ? 'denied' : ''}`}>{entry.outcome === 'Denied' ? <X size={13} /> : <Check size={13} />}</div><div className="audit-time">{entry.time}</div><div className="audit-main"><div><strong>{entry.action}</strong><span className="audit-arrow">→</span><code>{entry.tool}</code></div><div className="text-xs text-muted mt-1">{entry.user} · {entry.role}</div></div><span className={`outcome ${entry.outcome === 'Denied' ? 'denied-text' : ''}`}>{entry.outcome}</span></div>)}</div></div> }

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
