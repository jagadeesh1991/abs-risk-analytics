import { NavLink, Outlet } from 'react-router-dom'

const NAV = [
  { section: 'Dashboards', items: [
    { to: '/', label: 'Overview', icon: '◧' },
    { to: '/surveillance', label: 'Surveillance', icon: '◉' },
    { to: '/performance', label: 'Performance', icon: '↗' },
    { to: '/vintage', label: 'Vintage & Cohort', icon: '◔' },
    { to: '/stratification', label: 'Stratification', icon: '▤' },
    { to: '/distributions', label: 'Distributions', icon: '▥' },
    { to: '/geography', label: 'Geography', icon: '◍' },
  ]},
  { section: 'Advanced', items: [
    { to: '/transitions', label: 'Transitions', icon: '⇄' },
    { to: '/prepayment', label: 'Prepayment', icon: '↻' },
    { to: '/comparison', label: 'Comparison', icon: '⚖' },
    { to: '/structuring', label: 'Structuring', icon: '▦' },
  ]},
  { section: 'Data', items: [
    { to: '/upload', label: 'Upload Tape', icon: '⇪' },
  ]},
]

export default function Layout() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="logo">STRA<span>TA</span></div>
        {NAV.map((group) => (
          <div key={group.section}>
            <div className="nav-section">{group.section}</div>
            {group.items.map((item) => (
              <NavLink key={item.to} to={item.to} end={item.to === '/'}
                className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
                <span className="icon">{item.icon}</span>{item.label}
              </NavLink>
            ))}
          </div>
        ))}
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  )
}
