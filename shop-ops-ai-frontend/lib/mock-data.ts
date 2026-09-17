export const orders = [
  { id: 'e48151c', status: 'Shipped', purchase: '18 Jun 2025', eta: '24 Jun 2025', delivered: '—', seller: 'SP-1048', value: 'R$ 375', state: 'Delayed' },
  { id: '8f2a9d1', status: 'Delivered', purchase: '17 Jun 2025', eta: '22 Jun 2025', delivered: '21 Jun 2025', seller: 'RJ-2081', value: 'R$ 189', state: 'On time' },
  { id: 'c71b0e4', status: 'Processing', purchase: '20 Jun 2025', eta: '27 Jun 2025', delivered: '—', seller: 'BH-3310', value: 'R$ 642', state: 'On track' },
  { id: 'a930f21', status: 'Delivered', purchase: '15 Jun 2025', eta: '20 Jun 2025', delivered: '19 Jun 2025', seller: 'PR-1180', value: 'R$ 98', state: 'On time' },
  { id: 'd4408aa', status: 'Cancelled', purchase: '14 Jun 2025', eta: '—', delivered: '—', seller: 'SP-1048', value: 'R$ 214', state: 'Cancelled' },
  { id: 'f291ce0', status: 'Shipped', purchase: '19 Jun 2025', eta: '26 Jun 2025', delivered: '—', seller: 'RJ-2081', value: 'R$ 1,240', state: 'On track' },
  { id: 'b62c991', status: 'Delivered', purchase: '12 Jun 2025', eta: '18 Jun 2025', delivered: '18 Jun 2025', seller: 'BH-3310', value: 'R$ 74', state: 'On time' },
]

export const sellers = [
  { id: 'SP-1048', city: 'São Paulo', state: 'SP', orders: '2,480', late: 7.4, score: 4.8 },
  { id: 'RJ-2081', city: 'Rio de Janeiro', state: 'RJ', orders: '1,920', late: 14.8, score: 4.5 },
  { id: 'BH-3310', city: 'Belo Horizonte', state: 'MG', orders: '1,245', late: 9.1, score: 4.7 },
  { id: 'PR-1180', city: 'Curitiba', state: 'PR', orders: '876', late: 23.6, score: 4.1 },
]

export const activity = [
  { title: 'Order investigated', detail: 'e48151c · Support agent Alex', time: '8 min ago', tone: 'mint' },
  { title: 'Policy searched', detail: 'Refund Policy v2.1 · §4.1', time: '24 min ago', tone: 'yellow' },
  { title: 'Compensation proposal submitted', detail: 'R$ 75 · e48151c', time: '31 min ago', tone: 'peach' },
  { title: 'Manager approval completed', detail: 'R$ 120 · 8f2a9d1', time: '1 hr ago', tone: 'coral' },
]

export const auditEntries = [
  { time: 'Today, 09:42', user: 'Alex Morgan', role: 'support_agent', action: 'Query', tool: 'get_order', outcome: 'Success' },
  { time: 'Today, 09:41', user: 'Alex Morgan', role: 'support_agent', action: 'Query', tool: 'search_policy', outcome: 'Success' },
  { time: 'Today, 09:38', user: 'Alex Morgan', role: 'support_agent', action: 'Proposal', tool: 'calculate_compensation', outcome: 'Success' },
  { time: 'Today, 09:12', user: 'Maya Chen', role: 'ops_manager', action: 'Approval', tool: 'manager approval', outcome: 'Success' },
  { time: 'Yesterday, 17:20', user: 'Jordan Lee', role: 'support_agent', action: 'Query', tool: 'seller metrics', outcome: 'Denied' },
]

export const volume = [{ day: 'Mon', orders: 142 }, { day: 'Tue', orders: 188 }, { day: 'Wed', orders: 164 }, { day: 'Thu', orders: 226 }, { day: 'Fri', orders: 204 }, { day: 'Sat', orders: 248 }, { day: 'Sun', orders: 212 }]

export const timeline = [
  { label: 'Purchased', date: '18 Jun · 10:24', state: 'complete' },
  { label: 'Approved', date: '18 Jun · 10:25', state: 'complete' },
  { label: 'Shipped', date: '19 Jun · 14:08', state: 'complete' },
  { label: 'In transit', date: '20 Jun · 08:42', state: 'current' },
  { label: 'Delivered', date: 'Expected 24 Jun', state: 'pending' },
]

export const navItems = [
  { label: 'Dashboard', href: '/dashboard', icon: 'LayoutDashboard', roles: ['support_agent', 'ops_manager', 'admin'] },
  { label: 'AI Chat', href: '/dashboard/chat', icon: 'Sparkles', roles: ['support_agent', 'ops_manager', 'admin'] },
  { label: 'Orders', href: '/dashboard/orders', icon: 'PackageSearch', roles: ['support_agent', 'ops_manager', 'admin'] },
  { label: 'Sellers', href: '/dashboard/sellers', icon: 'Store', roles: ['ops_manager', 'admin'] },
  { label: 'Approvals', href: '/dashboard/approvals', icon: 'ClipboardCheck', roles: ['ops_manager', 'admin'] },
  { label: 'Audit Log', href: '/dashboard/audit', icon: 'ScrollText', roles: ['admin'] },
]

type Role = 'support_agent' | 'ops_manager' | 'admin'
export const roles: { key: Role; label: string }[] = [
  { key: 'support_agent', label: 'Support agent' },
  { key: 'ops_manager', label: 'Ops manager' },
  { key: 'admin', label: 'Admin' },
]
