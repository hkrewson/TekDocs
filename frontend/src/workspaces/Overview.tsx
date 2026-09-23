import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router'
import { translate } from '../i18n/localization'

const startingPoints = [
  { path: '/organizations', title: 'overview.organizations', description: 'overview.organizationsHelp' },
  { path: '/search', title: 'search.heading', description: 'overview.searchHelp' },
  { path: '/deadlines', title: 'capability.reminders', description: 'overview.remindersHelp' },
  { path: '/activity', title: 'capability.activity', description: 'overview.activityHelp' },
] as const

export default function Overview() {
  return (
    <>
      <header className="page-header"><div><h1>{translate('overview.heading')}</h1><p>{translate('overview.intro')}</p></div></header>
      <section className="content-section" aria-labelledby="overview-start-heading">
        <div className="section-heading"><div><h2 id="overview-start-heading">{translate('overview.start')}</h2><p>{translate('overview.startHelp')}</p></div></div>
        <ul className="search-result-list">
          {startingPoints.map((item) => <li key={item.path}><Link to={item.path}><span><strong>{translate(item.title)}</strong><span className="search-result-excerpt">{translate(item.description)}</span></span><ArrowRight size={16} aria-hidden="true" /></Link></li>)}
        </ul>
      </section>
    </>
  )
}
